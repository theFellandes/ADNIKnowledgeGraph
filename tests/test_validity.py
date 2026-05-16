"""Unit tests for metrics.validity.

Strategy: validity.run_validity() takes any object exposing ``run_query``.
We use a ``FakeConnector`` that pattern-matches on query substrings and
returns canned rows that mirror what the synthetic fixture
(``tests/fixtures/mini_kg.cypher``) would produce. Test cases flip individual
results to drive each assertion's PASS / FAIL paths without needing a live
Neo4j.

For end-to-end coverage against the live database, see V1.5 in
``docs/final_report/c7_plan_v2/TASKS.md``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from metrics.validity import (  # noqa: E402  (import after path tweak)
    PASS,
    FAIL,
    ValidityReport,
    load_rubric,
    render_markdown,
    run_validity,
    write_json,
    write_markdown,
)


RUBRIC_PATH = REPO_ROOT / "metrics" / "validity_rubric.yaml"


# ---------------------------------------------------------------------------
# Fake connector
# ---------------------------------------------------------------------------


class FakeConnector:
    """Dispatches queries to a list of (predicate, rows) handlers.

    The first handler whose predicate matches the (query, params) pair wins.
    Predicates are callables ``(query: str, params: dict) -> bool`` — typically
    a substring check on the query text.
    """

    def __init__(self, handlers: list[tuple[Any, list[dict[str, Any]]]] | None = None):
        self.handlers: list[tuple[Any, list[dict[str, Any]]]] = handlers or []
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        self.calls.append((query, parameters))
        for predicate, rows in self.handlers:
            if callable(predicate):
                if predicate(query, parameters or {}):
                    return rows
            elif isinstance(predicate, str):
                if predicate in query:
                    return rows
            else:
                raise TypeError(f"Unsupported predicate: {type(predicate)}")
        raise AssertionError(f"No handler matched query: {query!r}")


def _passing_handlers() -> list[tuple[Any, list[dict[str, Any]]]]:
    """Canned responses that make every assertion PASS against the mini-KG."""

    return [
        # A1
        ("SHOW CONSTRAINTS", [{"n": 12}]),
        ("SHOW INDEXES", [{"n": 15}]),
        # A2 — per label
        (
            lambda q, p: "MATCH (n:Diagnosis)" in q,
            [{"total": 4, "with_code": 4, "coverage": 1.0}],
        ),
        (
            lambda q, p: "MATCH (n:CognitiveAssessment)" in q,
            [{"total": 4, "with_code": 4, "coverage": 1.0}],
        ),
        (
            lambda q, p: "MATCH (n:Biomarker)" in q,
            [{"total": 3, "with_code": 3, "coverage": 1.0}],
        ),
        (
            lambda q, p: "MATCH (n:BrainRegion)" in q,
            [{"total": 3, "with_code": 3, "coverage": 1.0}],
        ),
        # A3 — five sources present
        (
            "MATCH (o:OntologyConcept) RETURN coalesce",
            [
                {"source": "SNOMED-CT", "n": 2},
                {"source": "LOINC", "n": 2},
                {"source": "UBERON", "n": 1},
                {"source": "HPO", "n": 1},
                {"source": "ICD-10", "n": 1},
            ],
        ),
        # A4 — per edge type
        (
            "[r:MAPS_TO]",
            [{"total": 12, "with_uri": 12, "coverage": 1.0}],
        ),
        (
            "[r:IS_A]",
            [{"total": 2, "with_uri": 2, "coverage": 1.0}],
        ),
        (
            "[r:CLASSIFIED_AS]",
            [{"total": 4, "with_uri": 4, "coverage": 1.0}],
        ),
        # A5 — relationship-type breakdown
        (
            "WITH type(r) AS rel_type",
            [
                {"rel_type": "HAS_VISIT", "n": 4, "with_uri": 4, "coverage": 1.0},
                {"rel_type": "HAS_DIAGNOSIS", "n": 4, "with_uri": 4, "coverage": 1.0},
                {"rel_type": "HAS_ASSESSMENT", "n": 4, "with_uri": 4, "coverage": 1.0},
                {"rel_type": "HAS_BIOMARKER", "n": 3, "with_uri": 3, "coverage": 1.0},
                {"rel_type": "HAS_REGION", "n": 3, "with_uri": 3, "coverage": 1.0},
                {"rel_type": "MAPS_TO", "n": 12, "with_uri": 12, "coverage": 1.0},
                {"rel_type": "IS_A", "n": 2, "with_uri": 2, "coverage": 1.0},
                {"rel_type": "CLASSIFIED_AS", "n": 4, "with_uri": 4, "coverage": 1.0},
            ],
        ),
        # A6 — orphans (per-concept rows; reachability computed in Python)
        (
            "MATCH (o:OntologyConcept) OPTIONAL MATCH",
            [
                {"uri": f"snomed:test{i}", "in_degree": 1, "hierarchy_flag": False}
                for i in range(7)
            ],
        ),
        # A7 — forbidden-prefix patient count
        (
            "MATCH (p:Patient) WHERE p.ptid STARTS WITH",
            [{"violation_count": 0, "sample": []}],
        ),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_rubric_loads_and_has_seven_assertions():
    rubric = load_rubric(RUBRIC_PATH)
    assert rubric["version"] == 1
    assert set(rubric["assertions"].keys()) == {"A1", "A2", "A3", "A4", "A5", "A6", "A7"}


def test_passing_graph_overall_pass():
    rubric = load_rubric(RUBRIC_PATH)
    report = run_validity(FakeConnector(_passing_handlers()), rubric, graph_uri="test://mini-kg")
    assert report.result == PASS, report.assertions
    assert all(a.result == PASS for a in report.assertions.values())


def test_a1_zero_constraints_is_hard_fail():
    rubric = load_rubric(RUBRIC_PATH)
    handlers = _passing_handlers()
    # Replace the SHOW CONSTRAINTS handler with one returning zero
    handlers = [(p, [{"n": 0}] if p == "SHOW CONSTRAINTS" else r) for p, r in handlers]
    report = run_validity(FakeConnector(handlers), rubric)
    assert report.result == FAIL
    assert report.assertions["A1"].result == FAIL
    assert report.assertions["A1"].hard_fail is True


def test_a1_below_thresholds_fails_softly():
    rubric = load_rubric(RUBRIC_PATH)
    handlers = _passing_handlers()
    handlers = [
        (p, [{"n": 5}] if p == "SHOW CONSTRAINTS" else r) for p, r in handlers
    ]
    report = run_validity(FakeConnector(handlers), rubric)
    assert report.assertions["A1"].result == FAIL
    assert report.assertions["A1"].hard_fail is False


def test_a2_diagnosis_below_threshold_fails():
    rubric = load_rubric(RUBRIC_PATH)
    handlers = _passing_handlers()
    new = []
    for p, r in handlers:
        if callable(p) and p("MATCH (n:Diagnosis) WHERE 1=1 ", {}):
            new.append((p, [{"total": 4, "with_code": 3, "coverage": 0.75}]))
        else:
            new.append((p, r))
    report = run_validity(FakeConnector(new), rubric)
    assert report.assertions["A2"].result == FAIL
    notes = " ".join(report.assertions["A2"].notes)
    assert "Diagnosis" in notes


def test_a2_missing_label_is_hard_fail():
    rubric = load_rubric(RUBRIC_PATH)
    handlers = _passing_handlers()
    new = []
    for p, r in handlers:
        if callable(p) and p("MATCH (n:BrainRegion) WHERE 1=1 ", {}):
            new.append((p, [{"total": 0, "with_code": 0, "coverage": 0.0}]))
        else:
            new.append((p, r))
    report = run_validity(FakeConnector(new), rubric)
    assert report.assertions["A2"].result == FAIL
    assert report.assertions["A2"].hard_fail is True


def test_a3_missing_required_source():
    rubric = load_rubric(RUBRIC_PATH)
    handlers = _passing_handlers()
    handlers = [
        (
            p,
            [
                # Drop HPO
                {"source": "SNOMED-CT", "n": 2},
                {"source": "LOINC", "n": 2},
                {"source": "UBERON", "n": 1},
                {"source": "ICD-10", "n": 1},
            ]
            if isinstance(p, str) and p == "MATCH (o:OntologyConcept) RETURN coalesce"
            else r,
        )
        for p, r in handlers
    ]
    report = run_validity(FakeConnector(handlers), rubric)
    assert report.assertions["A3"].result == FAIL
    assert "HPO" in " ".join(report.assertions["A3"].notes)


def test_a3_zero_concepts_is_hard_fail():
    rubric = load_rubric(RUBRIC_PATH)
    handlers = _passing_handlers()
    handlers = [
        (p, [] if isinstance(p, str) and p == "MATCH (o:OntologyConcept) RETURN coalesce" else r)
        for p, r in handlers
    ]
    report = run_validity(FakeConnector(handlers), rubric)
    assert report.assertions["A3"].result == FAIL
    assert report.assertions["A3"].hard_fail is True


def test_a4_maps_to_zero_is_hard_fail():
    rubric = load_rubric(RUBRIC_PATH)
    handlers = _passing_handlers()
    handlers = [
        (
            p,
            [{"total": 0, "with_uri": 0, "coverage": 0.0}]
            if isinstance(p, str) and p == "[r:MAPS_TO]"
            else r,
        )
        for p, r in handlers
    ]
    report = run_validity(FakeConnector(handlers), rubric)
    assert report.assertions["A4"].result == FAIL
    assert report.assertions["A4"].hard_fail is True


def test_a4_uri_coverage_below_threshold():
    rubric = load_rubric(RUBRIC_PATH)
    handlers = _passing_handlers()
    handlers = [
        (
            p,
            [{"total": 12, "with_uri": 6, "coverage": 0.5}]
            if isinstance(p, str) and p == "[r:MAPS_TO]"
            else r,
        )
        for p, r in handlers
    ]
    report = run_validity(FakeConnector(handlers), rubric)
    assert report.assertions["A4"].result == FAIL
    assert report.assertions["A4"].hard_fail is False


def test_a5_drops_unannotated_type_below_threshold():
    rubric = load_rubric(RUBRIC_PATH)
    handlers = _passing_handlers()
    new = []
    for p, r in handlers:
        if isinstance(p, str) and p == "WITH type(r) AS rel_type":
            new.append(
                (
                    p,
                    [
                        {"rel_type": "HAS_VISIT", "n": 4, "with_uri": 4, "coverage": 1.0},
                        # 5 of the 8 types have no uri — drops below 95% type coverage
                        {"rel_type": "HAS_DIAGNOSIS", "n": 4, "with_uri": 0, "coverage": 0.0},
                        {"rel_type": "HAS_ASSESSMENT", "n": 4, "with_uri": 0, "coverage": 0.0},
                        {"rel_type": "HAS_BIOMARKER", "n": 3, "with_uri": 0, "coverage": 0.0},
                        {"rel_type": "HAS_REGION", "n": 3, "with_uri": 0, "coverage": 0.0},
                        {"rel_type": "MAPS_TO", "n": 12, "with_uri": 12, "coverage": 1.0},
                        {"rel_type": "IS_A", "n": 2, "with_uri": 0, "coverage": 0.0},
                        {"rel_type": "CLASSIFIED_AS", "n": 4, "with_uri": 4, "coverage": 1.0},
                    ],
                )
            )
        else:
            new.append((p, r))
    report = run_validity(FakeConnector(new), rubric)
    assert report.assertions["A5"].result == FAIL
    measured = report.assertions["A5"].measured
    assert measured["annotated_types"] == 3
    assert measured["total_types"] == 8
    assert measured["type_coverage"] < 0.95


def test_a5_allowlist_excuses_unannotated_provenance_edges():
    rubric = load_rubric(RUBRIC_PATH)
    handlers = _passing_handlers()
    new = []
    for p, r in handlers:
        if isinstance(p, str) and p == "WITH type(r) AS rel_type":
            new.append(
                (
                    p,
                    [
                        {"rel_type": "HAS_VISIT", "n": 4, "with_uri": 4, "coverage": 1.0},
                        {"rel_type": "HAS_DIAGNOSIS", "n": 4, "with_uri": 4, "coverage": 1.0},
                        {"rel_type": "HAS_ASSESSMENT", "n": 4, "with_uri": 4, "coverage": 1.0},
                        {"rel_type": "HAS_BIOMARKER", "n": 3, "with_uri": 3, "coverage": 1.0},
                        {"rel_type": "HAS_REGION", "n": 3, "with_uri": 3, "coverage": 1.0},
                        {"rel_type": "MAPS_TO", "n": 12, "with_uri": 12, "coverage": 1.0},
                        {"rel_type": "IS_A", "n": 2, "with_uri": 2, "coverage": 1.0},
                        {"rel_type": "CLASSIFIED_AS", "n": 4, "with_uri": 4, "coverage": 1.0},
                        # Provenance edge with no uri — should be allowlisted
                        {"rel_type": "BATCH_INGESTED_BY", "n": 5, "with_uri": 0, "coverage": 0.0},
                    ],
                )
            )
        else:
            new.append((p, r))
    report = run_validity(FakeConnector(new), rubric)
    assert report.assertions["A5"].result == PASS


def test_a6_orphan_concepts_below_threshold():
    rubric = load_rubric(RUBRIC_PATH)
    handlers = _passing_handlers()
    # 100 concepts, 80 with non-zero in-degree, 20 orphans → 0.80 < 0.95
    orphan_rows = (
        [{"uri": f"snomed:r{i}", "in_degree": 1, "hierarchy_flag": False} for i in range(80)]
        + [{"uri": f"snomed:orphan{i}", "in_degree": 0, "hierarchy_flag": False} for i in range(20)]
    )
    handlers = [
        (p, orphan_rows if isinstance(p, str) and p == "MATCH (o:OntologyConcept) OPTIONAL MATCH" else r)
        for p, r in handlers
    ]
    report = run_validity(FakeConnector(handlers), rubric)
    assert report.assertions["A6"].result == FAIL
    # Sample of orphan URIs should be reported
    assert "orphan_uris" in report.assertions["A6"].measured


def test_a6_exempt_uris_recover_orphans():
    """If the rubric's hierarchy_roots list includes an URI, that node passes
    even with in_degree=0."""

    rubric = load_rubric(RUBRIC_PATH)
    # Use one of the URIs the rubric already lists as exempt.
    exempt_uri = "icd10:G30"
    handlers = _passing_handlers()
    rows = (
        [{"uri": f"snomed:r{i}", "in_degree": 1, "hierarchy_flag": False} for i in range(99)]
        + [{"uri": exempt_uri, "in_degree": 0, "hierarchy_flag": False}]
    )
    handlers = [
        (p, rows if isinstance(p, str) and p == "MATCH (o:OntologyConcept) OPTIONAL MATCH" else r)
        for p, r in handlers
    ]
    report = run_validity(FakeConnector(handlers), rubric)
    assert report.assertions["A6"].result == PASS
    assert report.assertions["A6"].measured["reachable"] == 100


def test_a7_forbidden_patient_is_hard_fail():
    rubric = load_rubric(RUBRIC_PATH)
    handlers = _passing_handlers()
    handlers = [
        (
            p,
            [{"violation_count": 3, "sample": ["381_S_0001", "381_S_0002", "381_S_0003"]}]
            if isinstance(p, str) and p == "MATCH (p:Patient) WHERE p.ptid STARTS WITH"
            else r,
        )
        for p, r in handlers
    ]
    report = run_validity(FakeConnector(handlers), rubric)
    assert report.assertions["A7"].result == FAIL
    assert report.assertions["A7"].hard_fail is True
    assert report.assertions["A7"].measured["violation_count"] == 3


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def test_render_markdown_pass(tmp_path):
    rubric = load_rubric(RUBRIC_PATH)
    report = run_validity(FakeConnector(_passing_handlers()), rubric, graph_uri="test://mini")
    md = render_markdown(report)
    assert "RESULT: PASS" in md
    assert "## Per-assertion summary" in md
    # Every assertion should appear in the table
    for aid in ("A1", "A2", "A3", "A4", "A5", "A6", "A7"):
        assert aid in md


def test_write_json_and_markdown(tmp_path):
    rubric = load_rubric(RUBRIC_PATH)
    report = run_validity(FakeConnector(_passing_handlers()), rubric, graph_uri="test://mini")
    json_path = tmp_path / "kg_validity_test.json"
    md_path = tmp_path / "kg_validity_test.md"
    write_json(report, json_path)
    write_markdown(report, md_path)
    assert json_path.exists()
    assert md_path.exists()
    assert json_path.stat().st_size > 0
    assert md_path.stat().st_size > 0


def test_validityreport_to_dict_roundtrips():
    rubric = load_rubric(RUBRIC_PATH)
    report = run_validity(FakeConnector(_passing_handlers()), rubric)
    d = report.to_dict()
    assert d["result"] == PASS
    assert set(d["assertions"].keys()) == {"A1", "A2", "A3", "A4", "A5", "A6", "A7"}
    assert d["schema_version"] == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_missing_rubric_entry_emits_warning():
    rubric = load_rubric(RUBRIC_PATH)
    rubric["assertions"].pop("A7")
    report = run_validity(FakeConnector(_passing_handlers()), rubric)
    assert any("A7" in w for w in report.warnings)
    # Without A7 the result should still be PASS provided all present assertions pass
    assert report.result == PASS


def test_rubric_load_rejects_malformed(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("nothing: here", encoding="utf-8")
    with pytest.raises(ValueError):
        load_rubric(bad)


def test_assertion_runtime_error_becomes_fail():
    """If an assertion's Cypher raises, the assertion records FAIL — never crashes the run."""

    class Boom(FakeConnector):
        def run_query(self, query, parameters=None):
            raise RuntimeError("Cypher exploded")

    rubric = load_rubric(RUBRIC_PATH)
    report = run_validity(Boom([]), rubric)
    assert report.result == FAIL
    assert all(a.result == FAIL for a in report.assertions.values())
