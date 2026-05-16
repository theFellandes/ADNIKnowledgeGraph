"""Semantic density metric — node and edge URI coverage.

Definitions (see ``docs/final_report/c7_plan_v2/IMPLEMENTATION_PLAN.md`` §6.2)::

    node_density(label) = |{ n in label : n has any ontology code OR n is :OntologyConcept }| / |label|
    edge_density(type)  = |{ r in type : r.uri OR r.ro_uri OR r.biolink_predicate set }| / |type|

A node "carries an ontology code" iff at least one of these properties is set:
``ontology_uri``, ``snomed_code``, ``loinc_code``, ``uberon_code``, ``icd10_code``,
``mondo_code``, ``hpo_code``, ``rdf_type``. The list is configurable via the
``node_uri_properties`` argument.

Aggregates are computed over all nodes / all edges (a single ratio) and broken
down per node label / per edge type.

CLI::

    python -m metrics.semantic_density                 # uses .env credentials
    python -m metrics.semantic_density --output metrics/output/semantic_density_post.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# Default ontology-code properties that "count" as a URI on a data node.
DEFAULT_NODE_URI_PROPERTIES: tuple[str, ...] = (
    "ontology_uri",
    "snomed_code",
    "loinc_code",
    "uberon_code",
    "icd10_code",
    "mondo_code",
    "hpo_code",
    "rdf_type",
    "uri",
)

# Edge URI-bearing properties.
DEFAULT_EDGE_URI_PROPERTIES: tuple[str, ...] = (
    "uri",
    "ro_uri",
    "biolink_predicate",
)

# A node is also "ontology-grounded" if it carries this label.
DEFAULT_ONTOLOGY_LABEL = "OntologyConcept"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CoverageEntry:
    name: str
    total: int
    with_uri: int

    @property
    def coverage(self) -> float:
        return (self.with_uri / self.total) if self.total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "total": self.total,
            "with_uri": self.with_uri,
            "coverage": round(self.coverage, 4),
        }


@dataclass
class DensityReport:
    schema_version: int
    timestamp: str
    graph_uri: str
    node_total: int
    node_with_uri: int
    edge_total: int
    edge_with_uri: int
    per_label: list[CoverageEntry] = field(default_factory=list)
    per_edge_type: list[CoverageEntry] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def node_density(self) -> float:
        return (self.node_with_uri / self.node_total) if self.node_total > 0 else 0.0

    @property
    def edge_density(self) -> float:
        return (self.edge_with_uri / self.edge_total) if self.edge_total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "graph_uri": self.graph_uri,
            "aggregate": {
                "node_density": round(self.node_density, 4),
                "edge_density": round(self.edge_density, 4),
                "node_total": self.node_total,
                "node_with_uri": self.node_with_uri,
                "edge_total": self.edge_total,
                "edge_with_uri": self.edge_with_uri,
            },
            "per_label": [e.to_dict() for e in self.per_label],
            "per_edge_type": [e.to_dict() for e in self.per_edge_type],
            "config": self.config,
        }


# ---------------------------------------------------------------------------
# Connector protocol (compatible with metrics.validity.Connector)
# ---------------------------------------------------------------------------


class Connector:
    def run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Cypher query builders
# ---------------------------------------------------------------------------


def _exists_clause(properties: Iterable[str], var: str) -> str:
    """Build a Cypher OR-chain that's true if any of the listed props is set."""

    parts = [f"{var}.{p} IS NOT NULL" for p in properties]
    return "(" + " OR ".join(parts) + ")"


def _build_node_per_label_query(
    node_uri_properties: Iterable[str], ontology_label: str
) -> str:
    expr = _exists_clause(node_uri_properties, "n")
    return (
        "MATCH (n) "
        "UNWIND labels(n) AS label "
        f"WITH label, n, ({expr} OR label = $ontology_label) AS uri_ok "
        "WITH label, count(n) AS total, "
        "     count(CASE WHEN uri_ok THEN 1 END) AS with_uri "
        "RETURN label, total, with_uri "
        "ORDER BY total DESC"
    )


def _build_aggregate_node_query(
    node_uri_properties: Iterable[str], ontology_label: str
) -> str:
    expr = _exists_clause(node_uri_properties, "n")
    return (
        "MATCH (n) "
        f"WITH n, ({expr} OR $ontology_label IN labels(n)) AS uri_ok "
        "RETURN count(n) AS total, count(CASE WHEN uri_ok THEN 1 END) AS with_uri"
    )


def _build_edge_per_type_query(edge_uri_properties: Iterable[str]) -> str:
    expr = _exists_clause(edge_uri_properties, "r")
    return (
        "MATCH ()-[r]->() "
        "WITH type(r) AS rel_type, r "
        f"WITH rel_type, count(r) AS total, count(CASE WHEN {expr} THEN 1 END) AS with_uri "
        "RETURN rel_type, total, with_uri "
        "ORDER BY total DESC"
    )


def _build_aggregate_edge_query(edge_uri_properties: Iterable[str]) -> str:
    expr = _exists_clause(edge_uri_properties, "r")
    return (
        "MATCH ()-[r]->() "
        f"RETURN count(r) AS total, count(CASE WHEN {expr} THEN 1 END) AS with_uri"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_density(
    connector: Connector,
    *,
    node_uri_properties: Iterable[str] = DEFAULT_NODE_URI_PROPERTIES,
    edge_uri_properties: Iterable[str] = DEFAULT_EDGE_URI_PROPERTIES,
    ontology_label: str = DEFAULT_ONTOLOGY_LABEL,
    graph_uri: str = "(unknown)",
) -> DensityReport:
    """Compute node + edge density on the connected graph.

    The two aggregate counts (node and edge) are taken from *separate* queries
    rather than summed from the per-label / per-type breakdowns, because nodes
    with multiple labels would otherwise be counted more than once.
    """

    node_uri_properties = tuple(node_uri_properties)
    edge_uri_properties = tuple(edge_uri_properties)

    started = time.time()

    label_rows = connector.run_query(
        _build_node_per_label_query(node_uri_properties, ontology_label),
        {"ontology_label": ontology_label},
    )
    edge_rows = connector.run_query(
        _build_edge_per_type_query(edge_uri_properties),
    )
    agg_node = connector.run_query(
        _build_aggregate_node_query(node_uri_properties, ontology_label),
        {"ontology_label": ontology_label},
    )
    agg_edge = connector.run_query(_build_aggregate_edge_query(edge_uri_properties))

    per_label = [
        CoverageEntry(
            name=str(r["label"]),
            total=int(r["total"]),
            with_uri=int(r["with_uri"]),
        )
        for r in label_rows
    ]
    per_edge_type = [
        CoverageEntry(
            name=str(r["rel_type"]),
            total=int(r["total"]),
            with_uri=int(r["with_uri"]),
        )
        for r in edge_rows
    ]

    node_row = agg_node[0] if agg_node else {"total": 0, "with_uri": 0}
    edge_row = agg_edge[0] if agg_edge else {"total": 0, "with_uri": 0}

    duration = time.time() - started
    logger.debug("compute_density finished in %.2f s", duration)

    return DensityReport(
        schema_version=1,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        graph_uri=graph_uri,
        node_total=int(node_row.get("total") or 0),
        node_with_uri=int(node_row.get("with_uri") or 0),
        edge_total=int(edge_row.get("total") or 0),
        edge_with_uri=int(edge_row.get("with_uri") or 0),
        per_label=per_label,
        per_edge_type=per_edge_type,
        config={
            "node_uri_properties": list(node_uri_properties),
            "edge_uri_properties": list(edge_uri_properties),
            "ontology_label": ontology_label,
            "duration_seconds": round(duration, 3),
        },
    )


def write_json(report: DensityReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)


def diff(baseline: DensityReport, post: DensityReport) -> dict[str, Any]:
    """Compute per-label / per-edge / aggregate density deltas (post − baseline).

    Output mirrors the shape consumed by ``figures/f4_density.py``.
    """

    def _index(entries: list[CoverageEntry]) -> dict[str, CoverageEntry]:
        return {e.name: e for e in entries}

    base_labels = _index(baseline.per_label)
    post_labels = _index(post.per_label)
    base_edges = _index(baseline.per_edge_type)
    post_edges = _index(post.per_edge_type)

    label_keys = sorted(set(base_labels) | set(post_labels))
    edge_keys = sorted(set(base_edges) | set(post_edges))

    def _pair(name: str, base_idx: dict[str, CoverageEntry], post_idx: dict[str, CoverageEntry]) -> dict[str, Any]:
        b = base_idx.get(name)
        p = post_idx.get(name)
        return {
            "name": name,
            "baseline": b.to_dict() if b else None,
            "post": p.to_dict() if p else None,
            "delta_coverage": round(
                (p.coverage if p else 0.0) - (b.coverage if b else 0.0), 4
            ),
        }

    return {
        "schema_version": 1,
        "baseline_timestamp": baseline.timestamp,
        "post_timestamp": post.timestamp,
        "aggregate": {
            "node_density_delta": round(post.node_density - baseline.node_density, 4),
            "edge_density_delta": round(post.edge_density - baseline.edge_density, 4),
        },
        "per_label": [_pair(k, base_labels, post_labels) for k in label_keys],
        "per_edge_type": [_pair(k, base_edges, post_edges) for k in edge_keys],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics.semantic_density",
        description="Compute node and edge URI coverage on a Neo4j graph.",
    )
    p.add_argument(
        "--output",
        default="outputs/metrics/semantic_density.json",
        help="Path for the JSON output.",
    )
    p.add_argument("--neo4j-uri", default=None)
    p.add_argument("--user", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--quiet", action="store_true")
    return p


def _resolve_credentials(args: argparse.Namespace) -> tuple[str, str, str]:
    uri, user, pw = args.neo4j_uri, args.user, args.password
    if not (uri and user and pw):
        from utils.env_loader import load_config

        cfg = load_config()
        uri = uri or cfg.get("neo4j_uri")
        user = user or cfg.get("neo4j_user", "neo4j")
        pw = pw or cfg.get("neo4j_password")
    if not (uri and user and pw):
        raise RuntimeError("Neo4j credentials missing — set NEO4J_URI/USER/PASSWORD or pass flags")
    return uri, user, pw


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        uri, user, pw = _resolve_credentials(args)
    except Exception as exc:
        logger.error("%s", exc)
        return 2

    from utils.neo4j_connector import Neo4jConnector

    connector = Neo4jConnector(uri=uri, user=user, password=pw)
    try:
        report = compute_density(connector, graph_uri=uri)
    finally:
        connector.close()

    out = Path(args.output)
    if not out.is_absolute():
        out = Path(__file__).resolve().parents[1] / out
    write_json(report, out)
    logger.info("Wrote %s", out)
    print(json.dumps(
        {
            "node_density": round(report.node_density, 4),
            "edge_density": round(report.edge_density, 4),
            "node_total": report.node_total,
            "edge_total": report.edge_total,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
