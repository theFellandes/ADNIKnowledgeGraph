"""AlzKB cross-vocabulary alignment metric.

Reads the live ``:AlzKBConcept`` + ``:SAME_AS`` graph state populated by
``steps/step24_alzkb_bridge.py`` and computes per-category strong-match
counts for the four in-scope AlzKB categories.

Per IMPLEMENTATION_PLAN.md §6.3 / decision #2: this module **extends** step
24 — it does not re-load the AlzKB CYPHERL dump. Reproducibility comes from
re-running step 24 against the dump pinned in ``data/alzkb/<version>/``.

Categories
----------

In-scope (reported with measured numbers)::

    Disease    — CauAD :OntologyConcept(source_ontology='SNOMED-CT')
                 ↔ AlzKB :AlzKBConcept(source_type='Disease')
    Anatomy    — CauAD :OntologyConcept(source_ontology='UBERON')
                 ↔ AlzKB :AlzKBConcept(source_type='Anatomy')
    Phenotype  — CauAD :OntologyConcept(source_ontology='HPO')
                 ↔ AlzKB :AlzKBConcept(source_type='Symptom')   # MeSH-coded; GO
                   BiologicalProcess dropped 2026-06-17 (a process is not a phenotype)

Out-of-scope (reported with ``not_implemented: true``)::

    Gene       — Gene Ontology integration was deferred (the removed C4)
                 No measurement; row exists for reviewer transparency.

Strong match
------------

A CauAD concept is a "strong match" iff there is a ``:SAME_AS`` edge
connecting it to an AlzKBConcept whose ``source_type`` matches the
category. The match direction in step 24 is ``(AlzKBConcept)-[:SAME_AS]->(OntologyConcept)``.

CLI::

    python -m metrics.alzkb_alignment
    python -m metrics.alzkb_alignment --output metrics/output/alzkb_alignment.json
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
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Category specifications
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CategorySpec:
    name: str
    cauad_source_ontology: str | None  # None ⇒ not_implemented
    alzkb_source_types: tuple[str, ...]
    note: str = ""


IN_SCOPE_CATEGORIES: tuple[CategorySpec, ...] = (
    CategorySpec(
        name="Disease",
        cauad_source_ontology="SNOMED-CT",
        alzkb_source_types=("Disease",),
        note="SNOMED-CT diagnoses ↔ AlzKB Disease nodes",
    ),
    CategorySpec(
        name="Anatomy",
        cauad_source_ontology="UBERON",
        alzkb_source_types=("Anatomy",),
        note="UBERON brain regions ↔ AlzKB Anatomy nodes",
    ),
    CategorySpec(
        name="Phenotype",
        cauad_source_ontology="HPO",
        alzkb_source_types=("Symptom",),
        note=("HPO phenotypes ↔ AlzKB Symptom (MeSH-coded) nodes. "
              "GO BiologicalProcess was dropped from this category on 2026-06-17 (M3): "
              "a GO process is not a phenotype, and the only such 'match' was an invalid "
              "proxy (GO:0150076 → HP:0002354). AlzKB exposes no HPO-coded phenotype node, "
              "so this category is 0 until a real MeSH Symptom node is bridged via a "
              "verified UMLS CUI crosswalk."),
    ),
    # Gene category — closed by Step 35 (Gene Ontology integration).
    # Uses cauad_source_ontology=None as a marker that the CauAD-side
    # entity is the :Gene node label rather than an OntologyConcept;
    # compute_alignment() handles this specially.
    CategorySpec(
        name="Gene",
        cauad_source_ontology=None,
        alzkb_source_types=("Gene",),
        note="AlzKB Gene entities ↔ MAKO :Gene nodes (Step 35)",
    ),
)

OUT_OF_SCOPE_CATEGORIES: tuple[CategorySpec, ...] = ()


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CategoryResult:
    name: str
    total: int
    strong_matches: int
    match_rate: float
    not_implemented: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "total": self.total,
            "strong_matches": self.strong_matches,
            "match_rate": round(self.match_rate, 4),
            "not_implemented": self.not_implemented,
            "note": self.note,
        }


@dataclass
class AlignmentReport:
    schema_version: int
    timestamp: str
    graph_uri: str
    alzkb_concept_total: int
    same_as_edge_total: int
    categories: list[CategoryResult] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "graph_uri": self.graph_uri,
            "alzkb_concept_total": self.alzkb_concept_total,
            "same_as_edge_total": self.same_as_edge_total,
            "categories": [c.to_dict() for c in self.categories],
            "duration_seconds": round(self.duration_seconds, 3),
        }

    @property
    def in_scope_strong_count(self) -> int:
        return sum(1 for c in self.categories if not c.not_implemented and c.strong_matches > 0)

    @property
    def in_scope_total_count(self) -> int:
        return sum(1 for c in self.categories if not c.not_implemented)


# ---------------------------------------------------------------------------
# Connector protocol
# ---------------------------------------------------------------------------


class Connector:
    def run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Cypher helpers
# ---------------------------------------------------------------------------

_TOTAL_QUERY = (
    "MATCH (o:OntologyConcept) "
    "WHERE toUpper(o.source_ontology) = toUpper($source_ontology) "
    "RETURN count(DISTINCT o) AS total"
)

_STRONG_MATCH_QUERY = (
    "MATCH (a:AlzKBConcept)-[:SAME_AS]->(o:OntologyConcept) "
    "WHERE toUpper(o.source_ontology) = toUpper($source_ontology) "
    "  AND a.source_type IN $alzkb_types "
    "RETURN count(DISTINCT o) AS strong"
)

# Gene-specific queries — Step 35 materialises Gene as its own node label
# (not as an OntologyConcept), so the Disease/Anatomy/Phenotype pattern of
# routing via :OntologyConcept does not apply. The Gene category uses
# :Gene on the MAKO side directly.
_GENE_TOTAL_QUERY = "MATCH (g:Gene) RETURN count(DISTINCT g) AS total"

_GENE_STRONG_QUERY = (
    "MATCH (a:AlzKBConcept)-[:SAME_AS]->(g:Gene) "
    "WHERE a.source_type = 'Gene' "
    "RETURN count(DISTINCT g) AS strong"
)

_ALZKB_COUNT_QUERY = "MATCH (a:AlzKBConcept) RETURN count(a) AS n"
_SAME_AS_COUNT_QUERY = "MATCH ()-[r:SAME_AS]->() RETURN count(r) AS n"


def _scalar(rows: list[dict[str, Any]], key: str, default: int = 0) -> int:
    if not rows:
        return default
    val = rows[0].get(key, default)
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_alignment(
    connector: Connector,
    *,
    in_scope: tuple[CategorySpec, ...] = IN_SCOPE_CATEGORIES,
    out_of_scope: tuple[CategorySpec, ...] = OUT_OF_SCOPE_CATEGORIES,
    graph_uri: str = "(unknown)",
) -> AlignmentReport:
    """Run the alignment query battery and produce a report."""

    started = time.time()

    alzkb_total = _scalar(connector.run_query(_ALZKB_COUNT_QUERY), "n")
    same_as_total = _scalar(connector.run_query(_SAME_AS_COUNT_QUERY), "n")

    categories: list[CategoryResult] = []

    for spec in in_scope:
        # Gene category — uses :Gene node label, not :OntologyConcept.
        # Identified by cauad_source_ontology=None + alzkb_types containing
        # 'Gene'. Falls back to "not_implemented" if no :Gene nodes exist
        # (i.e. Step 35 has not run yet).
        if spec.cauad_source_ontology is None and "Gene" in spec.alzkb_source_types:
            total = _scalar(connector.run_query(_GENE_TOTAL_QUERY), "total")
            if total == 0:
                categories.append(
                    CategoryResult(
                        name=spec.name, total=0, strong_matches=0, match_rate=0.0,
                        not_implemented=True,
                        note=spec.note + " (no :Gene nodes — run Step 35 to enable).",
                    )
                )
                continue
            strong = _scalar(connector.run_query(_GENE_STRONG_QUERY), "strong")
            rate = (strong / total) if total > 0 else 0.0
            categories.append(
                CategoryResult(
                    name=spec.name,
                    total=total,
                    strong_matches=strong,
                    match_rate=rate,
                    note=spec.note,
                )
            )
            continue
        # Normal ontology-routed categories (Disease, Anatomy, Phenotype)
        if spec.cauad_source_ontology is None:
            continue
        total = _scalar(
            connector.run_query(_TOTAL_QUERY, {"source_ontology": spec.cauad_source_ontology}),
            "total",
        )
        strong = _scalar(
            connector.run_query(
                _STRONG_MATCH_QUERY,
                {
                    "source_ontology": spec.cauad_source_ontology,
                    "alzkb_types": list(spec.alzkb_source_types),
                },
            ),
            "strong",
        )
        rate = (strong / total) if total > 0 else 0.0
        categories.append(
            CategoryResult(
                name=spec.name,
                total=total,
                strong_matches=strong,
                match_rate=rate,
                note=spec.note,
            )
        )

    for spec in out_of_scope:
        categories.append(
            CategoryResult(
                name=spec.name,
                total=0,
                strong_matches=0,
                match_rate=0.0,
                not_implemented=True,
                note=spec.note,
            )
        )

    return AlignmentReport(
        schema_version=1,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        graph_uri=graph_uri,
        alzkb_concept_total=alzkb_total,
        same_as_edge_total=same_as_total,
        categories=categories,
        duration_seconds=time.time() - started,
    )


def write_json(report: AlignmentReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)


def diff(baseline: AlignmentReport, post: AlignmentReport) -> dict[str, Any]:
    """Per-category baseline / post comparison."""

    base_idx = {c.name: c for c in baseline.categories}
    post_idx = {c.name: c for c in post.categories}
    keys = sorted(set(base_idx) | set(post_idx))

    rows = []
    for k in keys:
        b = base_idx.get(k)
        p = post_idx.get(k)
        rows.append(
            {
                "name": k,
                "baseline": b.to_dict() if b else None,
                "post": p.to_dict() if p else None,
                "delta_strong_matches": (p.strong_matches if p else 0)
                - (b.strong_matches if b else 0),
                "delta_match_rate": round(
                    (p.match_rate if p else 0.0) - (b.match_rate if b else 0.0), 4
                ),
            }
        )
    return {
        "schema_version": 1,
        "baseline_timestamp": baseline.timestamp,
        "post_timestamp": post.timestamp,
        "alzkb_concept_total_delta": post.alzkb_concept_total - baseline.alzkb_concept_total,
        "same_as_edge_total_delta": post.same_as_edge_total - baseline.same_as_edge_total,
        "in_scope_strong_count_baseline": baseline.in_scope_strong_count,
        "in_scope_strong_count_post": post.in_scope_strong_count,
        "per_category": rows,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics.alzkb_alignment",
        description="Compute AlzKB cross-vocabulary alignment from the live graph.",
    )
    p.add_argument("--output", default="outputs/metrics/alzkb_alignment.json")
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
        raise RuntimeError("Neo4j credentials missing")
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
        report = compute_alignment(connector, graph_uri=uri)
    finally:
        connector.close()

    out = Path(args.output)
    if not out.is_absolute():
        out = Path(__file__).resolve().parents[1] / out
    write_json(report, out)
    logger.info("Wrote %s", out)
    print(json.dumps(
        {
            "alzkb_concept_total": report.alzkb_concept_total,
            "same_as_edge_total": report.same_as_edge_total,
            "in_scope_strong_count": f"{report.in_scope_strong_count} of {report.in_scope_total_count}",
            "per_category": [
                {"name": c.name, "match_rate": round(c.match_rate, 3),
                 "strong": c.strong_matches, "total": c.total,
                 "not_implemented": c.not_implemented}
                for c in report.categories
            ],
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
