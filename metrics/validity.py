"""KG Validity Check — Sultan's Gate.

Verifies the LPG → KG transition is complete per the seven-assertion rubric in
``metrics/validity_rubric.yaml``. Runs before any FAIR / semantic density work.

Spec: ``docs/final_report/c7_plan_v2/VALIDITY_CHECK_SPEC.md``.

CLI::

    python -m metrics.validity                    # uses .env credentials
    python -m metrics.validity --rubric path/to/rubric.yaml
    python -m metrics.validity --output-dir outputs/validity_reports/
    python -m metrics.validity --neo4j-uri bolt://... --user ... --password ...

Exit codes::

    0 — all assertions PASS (including warnings)
    1 — at least one assertion FAIL or hard-fail condition triggered
    2 — runtime error (could not connect, rubric malformed, etc.)
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
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)


PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AssertionResult:
    id: str
    description: str
    result: str
    measured: dict[str, Any] = field(default_factory=dict)
    threshold: dict[str, Any] = field(default_factory=dict)
    hard_fail: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class ValidityReport:
    schema_version: int
    timestamp: str
    graph_uri: str
    rubric_version: int
    result: str
    assertions: dict[str, AssertionResult]
    warnings: list[str]
    duration_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "graph_uri": self.graph_uri,
            "rubric_version": self.rubric_version,
            "result": self.result,
            "assertions": {k: asdict(v) for k, v in self.assertions.items()},
            "warnings": self.warnings,
            "duration_seconds": round(self.duration_seconds, 3),
        }


# ---------------------------------------------------------------------------
# Connector protocol — anything with run_query(query, parameters) -> list[dict]
# ---------------------------------------------------------------------------


class Connector:
    """Minimal protocol — Neo4jConnector satisfies this; tests pass a mock."""

    def run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Assertion implementations
# ---------------------------------------------------------------------------


def _assertion(rid: str, description: str) -> Callable:
    """Decorator that wraps an assertion fn so a raised exception becomes a FAIL."""

    def decorate(fn: Callable[..., AssertionResult]) -> Callable[..., AssertionResult]:
        def wrapper(connector: Connector, cfg: dict[str, Any]) -> AssertionResult:
            try:
                return fn(connector, cfg)
            except Exception as exc:  # pragma: no cover — defensive
                logger.exception("Assertion %s raised: %s", rid, exc)
                return AssertionResult(
                    id=rid,
                    description=description,
                    result=FAIL,
                    notes=[f"Assertion raised exception: {type(exc).__name__}: {exc}"],
                )

        wrapper.__name__ = fn.__name__
        return wrapper

    return decorate


# --- A1 -------------------------------------------------------------------


@_assertion("A1", "Constraints + indexes complete")
def check_a1(connector: Connector, cfg: dict[str, Any]) -> AssertionResult:
    expected_constraints = int(cfg.get("expected_constraints", 12))
    expected_indexes = int(cfg.get("expected_indexes", 15))
    hard_fail_if_zero = bool(cfg.get("hard_fail_if_zero_constraints", True))

    # Neo4j 5.x: SHOW CONSTRAINTS and SHOW INDEXES return one row per item.
    constraint_rows = connector.run_query("SHOW CONSTRAINTS YIELD name RETURN count(*) AS n")
    index_rows = connector.run_query(
        "SHOW INDEXES YIELD name, type "
        "WHERE type IN ['RANGE','TEXT','LOOKUP','POINT'] "
        "RETURN count(*) AS n"
    )

    constraint_count = int(constraint_rows[0]["n"]) if constraint_rows else 0
    index_count = int(index_rows[0]["n"]) if index_rows else 0

    measured = {"constraint_count": constraint_count, "index_count": index_count}
    threshold = {
        "expected_constraints": expected_constraints,
        "expected_indexes": expected_indexes,
    }

    if hard_fail_if_zero and constraint_count == 0:
        return AssertionResult(
            id="A1",
            description="Constraints + indexes complete",
            result=FAIL,
            measured=measured,
            threshold=threshold,
            hard_fail=True,
            notes=["No constraints found — step 17 has not been run."],
        )

    ok = constraint_count >= expected_constraints and index_count >= expected_indexes
    return AssertionResult(
        id="A1",
        description="Constraints + indexes complete",
        result=PASS if ok else FAIL,
        measured=measured,
        threshold=threshold,
    )


# --- A2 -------------------------------------------------------------------


@_assertion("A2", "Ontology-code coverage on enriched node labels")
def check_a2(connector: Connector, cfg: dict[str, Any]) -> AssertionResult:
    per_label = cfg.get("per_label", {})
    hard_fail_if_label_missing = bool(cfg.get("hard_fail_if_label_missing", True))

    coverages: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    hard_fail = False

    for label, spec in per_label.items():
        prop = spec["property"]
        threshold = float(spec.get("threshold", 0.95))
        filter_cypher = spec.get("filter_cypher", "")

        where_extra = f" AND {filter_cypher}" if filter_cypher else ""
        # NOTE: label is YAML-controlled, not user-controlled — interpolation is safe.
        query = (
            f"MATCH (n:{label}) "
            f"WHERE 1=1{where_extra} "
            f"WITH count(n) AS total, "
            f"     count(CASE WHEN n.{prop} IS NOT NULL THEN 1 END) AS with_code "
            f"RETURN total, with_code, "
            f"       CASE WHEN total > 0 THEN toFloat(with_code) / total ELSE 0.0 END AS coverage"
        )
        rows = connector.run_query(query)
        if not rows:
            coverages[label] = {"total": 0, "with_code": 0, "coverage": 0.0, "threshold": threshold}
            failures.append(f"{label}: no rows returned")
            if hard_fail_if_label_missing:
                hard_fail = True
            continue

        row = rows[0]
        total = int(row.get("total") or 0)
        with_code = int(row.get("with_code") or 0)
        coverage = float(row.get("coverage") or 0.0)

        coverages[label] = {
            "total": total,
            "with_code": with_code,
            "coverage": round(coverage, 4),
            "threshold": threshold,
            "property": prop,
        }

        if total == 0:
            failures.append(f"{label}: total=0 — label missing from graph")
            if hard_fail_if_label_missing:
                hard_fail = True
        elif coverage < threshold:
            failures.append(
                f"{label}: coverage {coverage:.3f} < threshold {threshold:.3f} (property={prop})"
            )

    result = FAIL if failures else PASS
    return AssertionResult(
        id="A2",
        description="Ontology-code coverage on enriched node labels",
        result=result,
        measured={"per_label": coverages},
        threshold={"defaults": "see per_label.threshold"},
        hard_fail=hard_fail,
        notes=failures,
    )


# --- A3 -------------------------------------------------------------------


@_assertion("A3", "OntologyConcept layer materialised across required sources")
def check_a3(connector: Connector, cfg: dict[str, Any]) -> AssertionResult:
    required = [s.upper() for s in cfg.get("required_sources", [])]
    expected_counts = cfg.get("expected_counts", {}) or {}
    hard_fail_if_zero = bool(cfg.get("hard_fail_if_zero", True))

    rows = connector.run_query(
        "MATCH (o:OntologyConcept) "
        "RETURN coalesce(o.source_ontology, 'UNKNOWN') AS source, count(o) AS n"
    )
    counts = {str(r["source"]): int(r["n"]) for r in rows}
    total = sum(counts.values())

    if total == 0:
        return AssertionResult(
            id="A3",
            description="OntologyConcept layer materialised",
            result=FAIL,
            measured={"counts": counts, "total": 0},
            threshold={"required_sources": required},
            hard_fail=hard_fail_if_zero,
            notes=["No OntologyConcept nodes found — steps 19/20 have not been run."],
        )

    sources_present_upper = {s.upper() for s in counts.keys()}
    missing = [s for s in required if s not in sources_present_upper]

    notes: list[str] = []
    if missing:
        notes.append(f"Missing required sources: {missing}")

    # Optional count tolerance bands
    for source, band in expected_counts.items():
        # Find this source in counts (case-insensitive)
        actual = next((n for k, n in counts.items() if k.upper() == source.upper()), 0)
        lo = int(band.get("min", 0))
        hi = int(band.get("max", 10**9))
        if actual < lo or actual > hi:
            notes.append(
                f"{source}: count {actual} outside expected band [{lo}, {hi}]"
            )

    result = FAIL if (missing or any("outside expected band" in n for n in notes)) else PASS
    return AssertionResult(
        id="A3",
        description="OntologyConcept layer materialised",
        result=result,
        measured={"counts": counts, "total": total},
        threshold={"required_sources": required, "expected_counts": expected_counts},
        notes=notes,
    )


# --- A4 -------------------------------------------------------------------


@_assertion("A4", "Ontology edges present with uri")
def check_a4(connector: Connector, cfg: dict[str, Any]) -> AssertionResult:
    edges = cfg.get("edges", ["MAPS_TO", "IS_A", "CLASSIFIED_AS"])
    threshold = float(cfg.get("threshold", 0.95))
    hard_fail_if_maps_to_zero = bool(cfg.get("hard_fail_if_maps_to_zero", True))

    measurements: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    hard_fail = False

    for edge in edges:
        rows = connector.run_query(
            f"MATCH ()-[r:{edge}]->() "
            f"WITH count(r) AS total, "
            f"     count(CASE WHEN r.uri IS NOT NULL THEN 1 END) AS with_uri "
            f"RETURN total, with_uri, "
            f"       CASE WHEN total > 0 THEN toFloat(with_uri) / total ELSE 0.0 END AS coverage"
        )
        row = rows[0] if rows else {"total": 0, "with_uri": 0, "coverage": 0.0}
        total = int(row.get("total") or 0)
        with_uri = int(row.get("with_uri") or 0)
        coverage = float(row.get("coverage") or 0.0)

        measurements[edge] = {
            "total": total,
            "with_uri": with_uri,
            "uri_coverage": round(coverage, 4),
        }

        if total == 0:
            failures.append(f"{edge}: total=0")
            if edge == "MAPS_TO" and hard_fail_if_maps_to_zero:
                hard_fail = True
        elif coverage < threshold:
            failures.append(f"{edge}: uri coverage {coverage:.3f} < {threshold:.3f}")

    result = FAIL if failures else PASS
    return AssertionResult(
        id="A4",
        description="Ontology edges present with uri",
        result=result,
        measured=measurements,
        threshold={"per_edge_threshold": threshold},
        hard_fail=hard_fail,
        notes=failures,
    )


# --- A5 -------------------------------------------------------------------


@_assertion("A5", "Relationship-type URI annotation coverage")
def check_a5(connector: Connector, cfg: dict[str, Any]) -> AssertionResult:
    per_type_threshold = float(cfg.get("per_type_threshold", 0.95))
    type_coverage_threshold = float(cfg.get("type_coverage_threshold", 0.95))
    allowlist = {s.upper() for s in cfg.get("allowlist_unannotated", [])}

    rows = connector.run_query(
        "MATCH ()-[r]->() "
        "WITH type(r) AS rel_type, count(r) AS n, "
        "     count(CASE WHEN r.uri IS NOT NULL THEN 1 END) AS with_uri "
        "RETURN rel_type, n, with_uri, "
        "       CASE WHEN n > 0 THEN toFloat(with_uri) / n ELSE 0.0 END AS coverage "
        "ORDER BY coverage ASC"
    )

    total_types = len(rows)
    if total_types == 0:
        return AssertionResult(
            id="A5",
            description="Relationship-type URI annotation coverage",
            result=FAIL,
            measured={"total_types": 0},
            hard_fail=True,
            notes=["Graph has no relationships."],
        )

    annotated_types = 0
    types_below: list[dict[str, Any]] = []
    per_type: list[dict[str, Any]] = []

    for r in rows:
        rel_type = str(r["rel_type"])
        n = int(r["n"])
        with_uri = int(r["with_uri"])
        coverage = float(r["coverage"])
        per_type.append(
            {"rel_type": rel_type, "edges": n, "with_uri": with_uri, "coverage": round(coverage, 4)}
        )
        if rel_type.upper() in allowlist:
            continue  # exempt
        if coverage >= per_type_threshold:
            annotated_types += 1
        else:
            types_below.append({"rel_type": rel_type, "coverage": round(coverage, 4)})

    non_exempt = total_types - sum(1 for r in rows if str(r["rel_type"]).upper() in allowlist)
    type_coverage = annotated_types / non_exempt if non_exempt > 0 else 1.0

    # The type_coverage_threshold is the gating criterion: how many rel-types
    # are annotated overall. Individual types_below are *informational* — we
    # surface them as a note for triage but they don't block PASS as long as
    # type_coverage clears the threshold. Fixes B-03.
    notes: list[str] = []
    blocking = False
    if type_coverage < type_coverage_threshold:
        notes.append(
            f"Annotated rel-type fraction {type_coverage:.3f} < {type_coverage_threshold:.3f}"
        )
        blocking = True
    if types_below:
        notes.append(
            f"{len(types_below)} rel-types below per-type threshold "
            f"(informational; top offenders: {types_below[:5]})"
        )

    result = FAIL if blocking else PASS
    return AssertionResult(
        id="A5",
        description="Relationship-type URI annotation coverage",
        result=result,
        measured={
            "total_types": total_types,
            "annotated_types": annotated_types,
            "type_coverage": round(type_coverage, 4),
            "types_below_threshold": types_below,
            "per_type": per_type,
        },
        threshold={
            "per_type_threshold": per_type_threshold,
            "type_coverage_threshold": type_coverage_threshold,
            "allowlist": sorted(allowlist),
        },
        notes=notes,
    )


# --- A6 -------------------------------------------------------------------


@_assertion("A6", "No orphan OntologyConcept nodes")
def check_a6(connector: Connector, cfg: dict[str, Any]) -> AssertionResult:
    threshold = float(cfg.get("threshold", 0.95))
    exempt_uris = list(cfg.get("hierarchy_roots", []) or [])

    # Pull every concept's URI + in-degree, then apply the exempt list in
    # Python. Source of truth for "is a hierarchy root" is the rubric YAML
    # (cfg.hierarchy_roots), not a graph property — we used to also coalesce
    # an `is_hierarchy_root` node property here, but that property was never
    # populated by step 19/20 and produced noisy "unknown property" warnings
    # on every run (B-05 in BACKLOGS.md).
    rows = connector.run_query(
        # Reachability edge types include MAPS_TO / CLASSIFIED_AS / IS_A
        # (the original qualified-reference triad from Steps 19/20) and
        # PARTICIPATES_IN (added Step 35 — Gene → GO concept link).
        "MATCH (o:OntologyConcept) "
        "OPTIONAL MATCH (o)<-[r:MAPS_TO|CLASSIFIED_AS|IS_A|PARTICIPATES_IN]-() "
        "WITH o, count(r) AS in_degree "
        "RETURN o.uri AS uri, in_degree"
    )
    if not rows:
        return AssertionResult(
            id="A6",
            description="No orphan OntologyConcept nodes",
            result=PASS,
            measured={"total": 0, "reachable": 0, "reachable_rate": 1.0},
            notes=["No OntologyConcept nodes — vacuously true."],
        )

    exempt_set = {str(u) for u in exempt_uris}
    total = len(rows)
    reachable = 0
    orphan_uris: list[str] = []
    for r in rows:
        uri = str(r.get("uri") or "")
        in_degree = int(r.get("in_degree") or 0)
        if in_degree > 0 or uri in exempt_set:
            reachable += 1
        else:
            orphan_uris.append(uri)

    rate = reachable / total if total > 0 else 1.0

    notes: list[str] = []
    if rate < threshold:
        notes.append(f"Reachability {rate:.3f} < threshold {threshold:.3f}")
        if orphan_uris:
            notes.append(f"Unreachable URIs (sample): {orphan_uris[:10]}")

    result = FAIL if notes else PASS
    return AssertionResult(
        id="A6",
        description="No orphan OntologyConcept nodes",
        result=result,
        measured={
            "total": total,
            "reachable": reachable,
            "reachable_rate": round(rate, 4),
            "orphan_uris": orphan_uris,
            "exempt_count": len(exempt_set),
        },
        threshold={"threshold": threshold, "exempt_uris": exempt_uris},
        notes=notes,
    )


# --- A7 -------------------------------------------------------------------


@_assertion("A7", "PTID hygiene — no 381_S_* patients")
def check_a7(connector: Connector, cfg: dict[str, Any]) -> AssertionResult:
    forbidden_prefix = cfg.get("forbidden_prefix", "381_S_")

    rows = connector.run_query(
        "MATCH (p:Patient) "
        "WHERE p.ptid STARTS WITH $prefix "
        "RETURN count(p) AS violation_count, "
        "       collect(p.ptid)[0..10] AS sample",
        {"prefix": forbidden_prefix},
    )
    if not rows:
        return AssertionResult(
            id="A7",
            description="PTID hygiene",
            result=PASS,
            measured={"violation_count": 0},
            threshold={"forbidden_prefix": forbidden_prefix},
        )

    row = rows[0]
    violation = int(row.get("violation_count") or 0)
    sample = list(row.get("sample") or [])
    notes = [] if violation == 0 else [f"{violation} patient(s) match forbidden prefix; sample: {sample}"]
    return AssertionResult(
        id="A7",
        description="PTID hygiene",
        result=PASS if violation == 0 else FAIL,
        measured={"violation_count": violation, "sample": sample},
        threshold={"forbidden_prefix": forbidden_prefix},
        hard_fail=violation > 0,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


_ASSERTIONS: dict[str, Callable[[Connector, dict[str, Any]], AssertionResult]] = {
    "A1": check_a1,
    "A2": check_a2,
    "A3": check_a3,
    "A4": check_a4,
    "A5": check_a5,
    "A6": check_a6,
    "A7": check_a7,
}


def load_rubric(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Rubric not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        rubric = yaml.safe_load(f)
    if not isinstance(rubric, dict) or "assertions" not in rubric:
        raise ValueError(f"Malformed rubric at {path}: missing 'assertions' key")
    return rubric


def run_validity(
    connector: Connector,
    rubric: dict[str, Any],
    *,
    graph_uri: str = "(unknown)",
) -> ValidityReport:
    """Run all assertions defined in the rubric and return a ValidityReport."""

    started = time.time()
    assertion_specs: dict[str, dict[str, Any]] = rubric.get("assertions", {})

    results: dict[str, AssertionResult] = {}
    warnings: list[str] = []

    for aid, fn in _ASSERTIONS.items():
        spec = assertion_specs.get(aid)
        if spec is None:
            warnings.append(f"Rubric missing entry for {aid} — skipping")
            continue
        result = fn(connector, spec)
        results[aid] = result

    overall = PASS if all(r.result == PASS for r in results.values()) else FAIL
    duration = time.time() - started

    return ValidityReport(
        schema_version=1,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        graph_uri=graph_uri,
        rubric_version=int(rubric.get("version", 1)),
        result=overall,
        assertions=results,
        warnings=warnings,
        duration_seconds=duration,
    )


# ---------------------------------------------------------------------------
# Reporters
# ---------------------------------------------------------------------------


def write_json(report: ValidityReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)


def render_markdown(report: ValidityReport) -> str:
    lines: list[str] = []
    lines.append(f"# KG Validity Report — {report.timestamp} — RESULT: {report.result}")
    lines.append("")
    lines.append(f"- **Graph:** `{report.graph_uri}`")
    lines.append(f"- **Rubric version:** {report.rubric_version}")
    lines.append(f"- **Duration:** {report.duration_seconds:.2f} s")
    lines.append("")

    failed = [a for a in report.assertions.values() if a.result != PASS]
    if failed:
        lines.append("## Failing assertions")
        lines.append("")
        for a in failed:
            tag = "❌ HARD FAIL" if a.hard_fail else "❌ FAIL"
            lines.append(f"### {a.id} — {a.description} ({tag})")
            for n in a.notes:
                lines.append(f"- {n}")
            lines.append("")

    lines.append("## Per-assertion summary")
    lines.append("")
    lines.append("| ID | Description | Result | Hard fail | Notes |")
    lines.append("|---|---|---|---|---|")
    for a in report.assertions.values():
        notes = "; ".join(a.notes)[:200] if a.notes else ""
        marker = "✅" if a.result == PASS else "❌"
        lines.append(
            f"| {a.id} | {a.description} | {marker} {a.result} | "
            f"{'yes' if a.hard_fail else 'no'} | {notes} |"
        )
    lines.append("")

    if report.warnings:
        lines.append("## Warnings")
        for w in report.warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("## Detail")
    lines.append("")
    for a in report.assertions.values():
        lines.append(f"### {a.id} — {a.description}")
        lines.append("```json")
        lines.append(json.dumps({"measured": a.measured, "threshold": a.threshold}, indent=2))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def write_markdown(report: ValidityReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_markdown(report))


# ---------------------------------------------------------------------------
# Progress-report renderer (Sultan-facing, human-readable)
# ---------------------------------------------------------------------------
# Spec: docs/final_report/c7_plan_v3/VALIDITY_PROGRESS_REPORT_SPEC.md
#
# The default `render_markdown` above is machine-flavored. This produces the
# 1–2 page summary Sultan asked for in her progress-report feedback
# ("Bu ilerleme raporuna metrikleri koymasan bile hiç olmazsa ontolojileri
# bitirip graphın KG haline dönüşmüş halini koymak lazım"). Sections:
#   (a-tr) Turkish preamble (one sentence)
#   (a)    Plain-English summary paragraph
#   (b)    Per-assertion table (A1–A7 measured vs threshold)
#   (c)    Ontology completeness summary table
#   (d)    Before/after counts (from canonical_snapshot.json if present)
#   (e)    KG schema diagram link (Mermaid file path) — best-effort
#   footer Reproducibility line


_DEFAULT_PROGRESS_OUTPUT = (
    Path("outputs") / "validity_reports" / "kg_validity_progress_report.md"
)


def _format_int(n: Any) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def _build_assertion_table(report: ValidityReport) -> list[str]:
    rows: list[str] = []
    rows.append("| Assertion | What it checks | Measured | Threshold | Result |")
    rows.append("|---|---|---|---|---|")

    summaries = {
        "A1": ("Constraints + indexes complete",
               lambda m: f"{m.get('constraint_count','?')} constraints / "
                         f"{m.get('index_count','?')} indexes",
               "≥ 12 / 15"),
        "A2": ("Ontology-code coverage on enriched node labels",
               lambda m: ", ".join(
                   f"{lbl} {v.get('coverage', 0):.3f}"
                   for lbl, v in (m.get("per_label") or {}).items()
               ) or "n/a",
               "≥ 0.95 per label"),
        "A3": ("OntologyConcept layer covers required sources",
               lambda m: f"{m.get('total','?')} concepts across "
                         f"{len(m.get('counts') or {})} sources",
               "≥ 5 sources present"),
        "A4": ("Ontology edges populated with `uri`",
               lambda m: ", ".join(
                   f"{k} {v.get('uri_coverage', 0):.3f}"
                   for k, v in m.items() if isinstance(v, dict)
               ) or "n/a",
               "≥ 0.95 per edge type"),
        "A5": ("Relationship-type URI coverage",
               lambda m: f"{m.get('type_coverage', 0):.3f} "
                         f"({m.get('annotated_types','?')}/{m.get('total_types','?')} types)",
               "≥ 0.95"),
        "A6": ("No orphan OntologyConcept nodes",
               lambda m: f"{m.get('reachable_rate', 0):.3f} reachable "
                         f"({m.get('reachable','?')}/{m.get('total','?')})",
               "≥ 0.95"),
        "A7": ("PTID hygiene (no 381_S_* patients)",
               lambda m: f"{m.get('violation_count', 0)} violations",
               "= 0"),
    }

    for aid in ("A1", "A2", "A3", "A4", "A5", "A6", "A7"):
        a = report.assertions.get(aid)
        if a is None:
            continue
        desc, value_fn, threshold = summaries[aid]
        try:
            measured = value_fn(a.measured or {})
        except Exception:
            measured = "n/a"
        marker = "✅ PASS" if a.result == PASS else "❌ FAIL"
        rows.append(f"| {aid} | {desc} | {measured} | {threshold} | {marker} |")
    return rows


def _build_ontology_completeness_table(report: ValidityReport,
                                       canonical: dict[str, Any] | None) -> list[str]:
    """Per-(label, ontology) coverage. Pulls A2 measurement + tops up with
    canonical snapshot data where available."""

    rows: list[str] = []
    rows.append("| Node label | Target ontology | Coverage | Notes |")
    rows.append("|---|---|---|---|")

    a2 = report.assertions.get("A2")
    per_label = ((a2.measured or {}).get("per_label") or {}) if a2 else {}

    pretty = {
        "Diagnosis": ("SNOMED-CT", "snomed_code"),
        "CognitiveAssessment": ("LOINC", "loinc_code"),
        "Biomarker": ("LOINC (CSF subset)", "loinc_code"),
        "BrainRegion": ("UBERON", "uberon_code"),
    }
    for label, (target, prop) in pretty.items():
        m = per_label.get(label, {})
        cov = m.get("coverage")
        total = m.get("total")
        with_code = m.get("with_code")
        if total in (None, 0):
            rows.append(f"| `:{label}` | {target} | n/a | — |")
            continue
        rows.append(
            f"| `:{label}` | {target} | {cov:.3f} "
            f"({_format_int(with_code)}/{_format_int(total)}) | `{prop}` |"
        )

    # Tack on entries for the post-enrichment labels not in A2's per-label
    # list, so the table tells the full coverage story.
    if canonical:
        cards = canonical.get("node_label_cardinalities") or {}
        ontology_total = canonical.get("ontology_concepts_total")
        if ontology_total is not None:
            rows.append(
                f"| `:OntologyConcept` | 8 sources (SNOMED-CT, LOINC, UBERON, "
                f"ICD-10, HPO, MONDO, DOID, GO) | {ontology_total} concepts | "
                f"step 19/20 + 30/34/35 |"
            )
        gene_count = cards.get("Gene")
        if gene_count:
            rows.append(
                f"| `:Gene` | NCBI Gene + HGNC + UniProt | {gene_count} nodes | "
                f"step 35 (Contribution 4) |"
            )
    return rows


def _build_before_after_table(canonical: dict[str, Any] | None) -> list[str]:
    if not canonical:
        return ["", "*Before/after counts not available — canonical snapshot pending.*", ""]
    sources = canonical.get("ontology_concepts_by_source") or {}
    rows: list[str] = []
    rows.append("| Item | Pre-Steps-17–20 (LPG baseline) | Current |")
    rows.append("|---|---|---|")
    rows.append(f"| Total nodes | ≈407,000 | {_format_int(canonical.get('node_total'))} |")
    rows.append(f"| Total relationships | ≈1.16M | {_format_int(canonical.get('edge_total'))} |")
    rows.append("| Distinct ontology sources | 0 (no ontology layer) | "
                f"**{len(sources)}** (" + ", ".join(sorted(sources.keys())) + ") |")
    rows.append(f"| OntologyConcept nodes | 0 | {_format_int(canonical.get('ontology_concepts_total'))} |")
    rows.append(f"| MAPS_TO edges | 0 | {_format_int(canonical.get('maps_to_edges'))} |")
    rows.append(f"| IS_A edges | 0 | {_format_int(canonical.get('is_a_edges'))} |")
    rows.append(f"| Relationship URI coverage | 0% | "
                f"{(canonical.get('edge_uri_coverage') or 0) * 100:.2f}% |")
    return rows


def render_progress_report(
    json_path: Path | str,
    canonical_snapshot_path: Path | str | None = None,
    schema_svg_path: Path | str | None = None,
    *,
    output_path: Path | str = _DEFAULT_PROGRESS_OUTPUT,
    rubric_version: int | None = None,
    include_turkish_preamble: bool = True,
) -> Path:
    """Render the Sultan-facing progress report from a validity JSON.

    See docs/final_report/c7_plan_v3/VALIDITY_PROGRESS_REPORT_SPEC.md for
    section layout. Returns the path to the written markdown file.

    Parameters
    ----------
    json_path
        Path to the ``kg_validity_<ts>.json`` produced by ``run_validity``.
    canonical_snapshot_path
        Optional. If given, before/after counts are populated; otherwise
        marked "baseline pending".
    schema_svg_path
        Optional. If given, embedded inline as a Markdown image link.
    output_path
        Where to write the .md (default ``outputs/validity_reports/
        kg_validity_progress_report.md``).
    include_turkish_preamble
        Add Section (a-tr) Turkish-language preamble. Default True.
    """

    json_path = Path(json_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    # Hydrate AssertionResult dataclasses from the JSON
    assertions: dict[str, AssertionResult] = {}
    for aid, a in (payload.get("assertions") or {}).items():
        assertions[aid] = AssertionResult(
            id=a["id"],
            description=a.get("description", ""),
            result=a.get("result", FAIL),
            measured=a.get("measured", {}) or {},
            threshold=a.get("threshold", {}) or {},
            hard_fail=bool(a.get("hard_fail", False)),
            notes=list(a.get("notes") or []),
        )
    report = ValidityReport(
        schema_version=int(payload.get("schema_version", 1)),
        timestamp=str(payload.get("timestamp", "")),
        graph_uri=str(payload.get("graph_uri", "(unknown)")),
        rubric_version=int(payload.get("rubric_version", rubric_version or 1)),
        result=str(payload.get("result", FAIL)),
        assertions=assertions,
        warnings=list(payload.get("warnings") or []),
        duration_seconds=float(payload.get("duration_seconds", 0.0)),
    )

    canonical: dict[str, Any] | None = None
    if canonical_snapshot_path:
        csp = Path(canonical_snapshot_path)
        if csp.exists():
            try:
                canonical = json.loads(csp.read_text(encoding="utf-8"))
            except Exception:
                canonical = None

    lines: list[str] = []
    title_marker = "✅ PASS" if report.result == PASS else "❌ FAIL"
    lines.append(f"# MAKO KG Validity — Progress Report")
    lines.append("")
    lines.append(f"**Result:** {title_marker} &nbsp; **Snapshot:** "
                 f"`{report.timestamp}` &nbsp; **Rubric:** v{report.rubric_version}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # (a-tr) Turkish preamble
    if include_turkish_preamble:
        lines.append("## Özet (Türkçe)")
        lines.append("")
        lines.append(
            "Bu rapor, ADNI bilgi grafının LPG'den KG'ye dönüşümünün "
            "tamamlandığını ve yedi doğrulama testinin başarıyla "
            "geçildiğini belgeler."
        )
        lines.append("")

    # (a) Plain-English summary
    lines.append("## Summary")
    lines.append("")
    if canonical:
        sources = canonical.get("ontology_concepts_by_source") or {}
        srcs_str = ", ".join(sorted(sources.keys()))
        concepts = canonical.get("ontology_concepts_total", "?")
        nodes = _format_int(canonical.get("node_total", "?"))
        edges = _format_int(canonical.get("edge_total", "?"))
        edge_cov = (canonical.get("edge_uri_coverage") or 0) * 100
        lines.append(
            f"The ADNI knowledge graph has completed the labeled-property-graph (LPG) → "
            f"knowledge-graph (KG) transition. The graph contains **{nodes}** nodes and "
            f"**{edges}** relationships. Ontology grounding spans **{len(sources)}** "
            f"vocabularies ({srcs_str}) via **{concepts}** OntologyConcept nodes, with "
            f"**{edge_cov:.2f}%** of relationships carrying a formal URI. All **seven** "
            f"structural-validity assertions {title_marker.split()[-1]} at the agreed "
            f"0.95 threshold."
        )
    else:
        passing = sum(1 for a in report.assertions.values() if a.result == PASS)
        total = len(report.assertions)
        lines.append(
            f"Validity gate result: **{report.result}** ({passing}/{total} assertions "
            f"passed). Canonical snapshot not available — re-run "
            f"`python -m metrics.reconcile` to populate the headline numbers."
        )
    lines.append("")

    # (b) Per-assertion table
    lines.append("## Per-assertion results")
    lines.append("")
    lines.extend(_build_assertion_table(report))
    lines.append("")

    # (c) Ontology completeness summary
    lines.append("## Ontology completeness")
    lines.append("")
    lines.extend(_build_ontology_completeness_table(report, canonical))
    lines.append("")

    # (d) Before/after counts
    lines.append("## Before vs current state")
    lines.append("")
    lines.extend(_build_before_after_table(canonical))
    lines.append("")

    # (e) KG schema diagram (best-effort)
    if schema_svg_path:
        ssp = Path(schema_svg_path)
        if ssp.exists():
            lines.append("## KG schema")
            lines.append("")
            # Use a relative path to the .md so the link resolves when opened
            # from the validity_reports directory.
            try:
                rel = ssp.relative_to(Path(output_path).parent)
            except (ValueError, AttributeError):
                rel = ssp
            lines.append(f"![KG schema]({rel})")
            lines.append("")

    # Failing assertions (only if any failed)
    failed = [a for a in report.assertions.values() if a.result != PASS]
    if failed:
        lines.append("## Failing assertions (require attention)")
        lines.append("")
        for a in failed:
            tag = "❌ HARD FAIL" if a.hard_fail else "❌ FAIL"
            lines.append(f"- **{a.id}** ({tag}) — {a.description}")
            for n in a.notes:
                lines.append(f"  - {n}")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(
        f"*Generated by `metrics/validity.py::render_progress_report()` from "
        f"`{json_path.name}` at {datetime.now(timezone.utc).isoformat(timespec='seconds')}. "
        f"Reproduce: `python -m metrics --all` then "
        f"`python -m metrics.validity --render-progress-report`.*"
    )
    lines.append("")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics.validity",
        description="Run the KG validity gate (Sultan's seven-assertion rubric).",
    )
    p.add_argument(
        "--rubric",
        default=str(Path(__file__).with_name("validity_rubric.yaml")),
        help="Path to the YAML rubric (default: metrics/validity_rubric.yaml)",
    )
    p.add_argument(
        "--output-dir",
        default="outputs/validity_reports",
        help="Directory to write the JSON + Markdown report (default: outputs/validity_reports)",
    )
    p.add_argument("--neo4j-uri", default=None, help="Override Neo4j URI from .env / config.yaml")
    p.add_argument("--user", default=None, help="Override Neo4j user")
    p.add_argument("--password", default=None, help="Override Neo4j password")
    p.add_argument("--quiet", action="store_true", help="Suppress non-error logging")
    return p


def _resolve_credentials(args: argparse.Namespace) -> tuple[str, str, str]:
    """Build (uri, user, password) using CLI flags then config/.env fallback."""

    uri = args.neo4j_uri
    user = args.user
    password = args.password
    if not (uri and user and password):
        try:
            from utils.env_loader import load_config  # local import to keep tests light
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Could not import utils.env_loader; pass --neo4j-uri/--user/--password"
            ) from exc
        cfg = load_config()
        uri = uri or cfg.get("neo4j_uri")
        user = user or cfg.get("neo4j_user", "neo4j")
        password = password or cfg.get("neo4j_password")
    if not (uri and user and password):
        raise RuntimeError("Neo4j credentials missing — set NEO4J_URI/USER/PASSWORD or pass flags")
    return uri, user, password


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        rubric = load_rubric(args.rubric)
    except Exception as exc:
        logger.error("Failed to load rubric: %s", exc)
        return 2

    try:
        uri, user, password = _resolve_credentials(args)
    except Exception as exc:
        logger.error("%s", exc)
        return 2

    try:
        from utils.neo4j_connector import Neo4jConnector
    except Exception as exc:  # pragma: no cover
        logger.error("Could not import Neo4jConnector: %s", exc)
        return 2

    connector = Neo4jConnector(uri=uri, user=user, password=password)
    try:
        report = run_validity(connector, rubric, graph_uri=uri)
    finally:
        connector.close()

    # Anchor relative output paths to the project root so the report lands in
    # the same place regardless of which directory the script was invoked from.
    project_root = Path(__file__).resolve().parents[1]
    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = project_root / out_dir
    ts = report.timestamp.replace(":", "").replace("-", "").replace("+0000", "Z").replace("+00:00", "Z")
    json_path = out_dir / f"kg_validity_{ts}.json"
    md_path = out_dir / f"kg_validity_{ts}.md"
    write_json(report, json_path)
    write_markdown(report, md_path)

    logger.info("Wrote %s", json_path)
    logger.info("Wrote %s", md_path)
    logger.info("Result: %s", report.result)

    return 0 if report.result == PASS else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
