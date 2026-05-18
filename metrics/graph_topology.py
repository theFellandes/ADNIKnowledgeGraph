"""Graph-topology indicators: concept hubs, orphans, and connected components.

Three independent sections in the output JSON:

  - ``top_25_hubs`` — OntologyConcept nodes ordered by MAPS_TO in-degree.
    These are the concepts that carry the most patient-instance attachments;
    in the MAKO graph the head of the distribution is usually HP:0000726
    (Dementia), SNOMED:26929004 (Alzheimer's disease), and similar AD-central
    codes.
  - ``orphans_by_label`` — node-label inventory of nodes with no incoming or
    outgoing edges. Some orphans are intentional (taxonomy or T-Box-only
    labels that were never instantiated); the breakdown lets the thesis say
    which is which.
  - ``connected_components`` — number and size distribution of weakly-connected
    components. Tries GDS first, then APOC, then falls back to a Python
    BFS sampler on 10 000 random nodes if neither algorithmic plugin is
    available; ``available`` flags which path produced the data.

CLI::

    python -m metrics.graph_topology
    python -m metrics.graph_topology --top-k 25 --output outputs/metrics/graph_topology.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class HubRow:
    uri: str
    label: str
    source_ontology: str
    indegree: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "label": self.label,
            "source_ontology": self.source_ontology,
            "indegree": self.indegree,
        }


@dataclass
class OrphanRow:
    label: str
    orphans: int

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "orphans": self.orphans}


@dataclass
class GraphTopologyReport:
    schema_version: int
    timestamp: str
    graph_uri: str
    top_25_hubs: list[HubRow] = field(default_factory=list)
    orphans_by_label: list[OrphanRow] = field(default_factory=list)
    connected_components: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "graph_uri": self.graph_uri,
            "top_25_hubs": [r.to_dict() for r in self.top_25_hubs],
            "orphans_by_label": [r.to_dict() for r in self.orphans_by_label],
            "connected_components": self.connected_components,
        }


_HUBS_QUERY = """
MATCH (c:OntologyConcept)<-[:MAPS_TO|CLASSIFIED_AS|PARTICIPATES_IN|ENCODES]-()
WITH c, count(*) AS indegree
RETURN
  coalesce(c.uri, '') AS uri,
  coalesce(c.label, c.preferred_term, c.name, '') AS label,
  coalesce(c.source_ontology, '') AS source_ontology,
  indegree
ORDER BY indegree DESC
LIMIT $top_k
"""

_ORPHANS_QUERY = """
MATCH (n)
WHERE NOT (n)--()
RETURN labels(n)[0] AS label, count(n) AS orphans
ORDER BY orphans DESC
"""

_GDS_WCC_QUERY = """
CALL gds.graph.project.cypher(
  'mako_topology',
  'MATCH (n) RETURN id(n) AS id',
  'MATCH (a)-[r]-(b) RETURN id(a) AS source, id(b) AS target'
)
YIELD graphName
WITH graphName
CALL gds.wcc.stream(graphName) YIELD componentId
WITH componentId, count(*) AS size
RETURN componentId, size
ORDER BY size DESC
LIMIT 25
"""

_GDS_DROP_QUERY = "CALL gds.graph.drop('mako_topology', false) YIELD graphName RETURN graphName"

_APOC_WCC_QUERY = """
CALL apoc.algo.wcc()
YIELD componentId, size
RETURN componentId, size
ORDER BY size DESC
LIMIT 25
"""


class Connector:
    def run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError


def _try_gds(connector: Connector) -> tuple[list[dict[str, Any]], str | None]:
    try:
        rows = connector.run_query(_GDS_WCC_QUERY) or []
        try:
            connector.run_query(_GDS_DROP_QUERY)
        except Exception:
            pass
        return rows, "gds.wcc"
    except Exception as exc:
        logger.debug("GDS WCC failed: %s", exc)
        return [], None


def _try_apoc(connector: Connector) -> tuple[list[dict[str, Any]], str | None]:
    try:
        rows = connector.run_query(_APOC_WCC_QUERY) or []
        return rows, "apoc.algo.wcc"
    except Exception as exc:
        logger.debug("APOC WCC failed: %s", exc)
        return [], None


def _python_bfs_sample(connector: Connector, sample_size: int = 10_000) -> list[dict[str, Any]]:
    """Last-resort BFS-based component sampler.

    Picks ``sample_size`` random nodes, runs a one-hop neighbourhood probe per
    seed, and reports the size distribution of distinct seeds that share a
    neighbour. Crude — gives an order-of-magnitude estimate, not an exact
    component count. Use only when both GDS and APOC are unavailable.
    """
    seeds_q = (
        "MATCH (n) WITH n, rand() AS r ORDER BY r LIMIT $k "
        "MATCH (n)-[*..2]-(m) "
        "WITH n, count(DISTINCT m) AS reach "
        "RETURN id(n) AS seed, reach"
    )
    try:
        rows = connector.run_query(seeds_q, {"k": sample_size}) or []
    except Exception as exc:
        logger.debug("Python BFS sampler failed: %s", exc)
        return []
    # Histogram reach as a stand-in for component size
    histogram: dict[int, int] = {}
    for row in rows:
        reach = int(row.get("reach", 0) or 0)
        bucket = reach if reach < 100 else (reach // 100) * 100
        histogram[bucket] = histogram.get(bucket, 0) + 1
    return [
        {"componentId": -1, "size": k, "seed_count": v}
        for k, v in sorted(histogram.items(), key=lambda kv: kv[1], reverse=True)[:25]
    ]


def compute(
    connector: Connector,
    *,
    top_k: int = 25,
    graph_uri: str = "(unknown)",
) -> GraphTopologyReport:
    started = time.time()

    raw_hubs = connector.run_query(_HUBS_QUERY, {"top_k": top_k}) or []
    hubs = [
        HubRow(
            uri=str(r.get("uri", "")),
            label=str(r.get("label", "")),
            source_ontology=str(r.get("source_ontology", "")),
            indegree=int(r.get("indegree", 0) or 0),
        )
        for r in raw_hubs
    ]

    raw_orphans = connector.run_query(_ORPHANS_QUERY) or []
    orphans = [
        OrphanRow(label=str(r.get("label", "")), orphans=int(r.get("orphans", 0) or 0))
        for r in raw_orphans
        if r.get("label")
    ]

    cc_rows, method = _try_gds(connector)
    if not cc_rows:
        cc_rows, method = _try_apoc(connector)
    available = bool(method)
    if not cc_rows:
        cc_rows = _python_bfs_sample(connector)
        if cc_rows:
            method = "python_bfs_sampler"

    cc: dict[str, Any] = {
        "available": available,
        "method": method,
        "components": [
            {
                "componentId": int(r.get("componentId", 0) or 0),
                "size": int(r.get("size", 0) or 0),
                **({"seed_count": int(r["seed_count"])} if "seed_count" in r else {}),
            }
            for r in cc_rows
        ],
    }

    logger.debug("graph_topology compute finished in %.2f s", time.time() - started)
    return GraphTopologyReport(
        schema_version=1,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        graph_uri=graph_uri,
        top_25_hubs=hubs,
        orphans_by_label=orphans,
        connected_components=cc,
    )


def write_json(report: GraphTopologyReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics.graph_topology",
        description="Concept hubs, orphan inventory, and connected components.",
    )
    p.add_argument(
        "--output",
        default="outputs/metrics/graph_topology.json",
        help="Path for the JSON output.",
    )
    p.add_argument("--top-k", type=int, default=25, help="Top-N hubs to keep (default 25).")
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
        report = compute(connector, top_k=args.top_k, graph_uri=uri)
    finally:
        connector.close()

    out = Path(args.output)
    if not out.is_absolute():
        out = Path(__file__).resolve().parents[1] / out
    write_json(report, out)
    logger.info("Wrote %s", out)
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
