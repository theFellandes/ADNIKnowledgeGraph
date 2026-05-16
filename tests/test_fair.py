"""Tests for metrics.fair."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from metrics.fair import (  # noqa: E402
    LEVEL_TO_SCORE,
    YES,
    PARTIAL,
    NO,
    FairReport,
    PrincipleResult,
    diff,
    load_rubric,
    score_fair,
    write_json,
    _eval_cypher,
    _eval_file,
    _eval_manual,
)


RUBRIC_PATH = REPO_ROOT / "metrics" / "fair_principles.yaml"


# ---------------------------------------------------------------------------
# Fake connector
# ---------------------------------------------------------------------------


class FakeConnector:
    """Returns canned per-query responses keyed by an iterating index, since the
    FAIR scorer fires one Cypher per principle in YAML insertion order."""

    def __init__(self, responses):
        # responses: list of rows OR list of (predicate, rows)
        self.responses = responses
        self.calls = []

    def run_query(self, query, parameters=None):
        self.calls.append((query, parameters))
        for predicate, rows in self.responses:
            if callable(predicate):
                if predicate(query, parameters or {}):
                    return rows
            elif isinstance(predicate, str):
                if predicate in query:
                    return rows
            else:
                raise TypeError(predicate)
        # Default: empty rows (causes a NO score)
        return []


def _matchany():
    return lambda q, p: True


# ---------------------------------------------------------------------------
# Per-evaluator tests
# ---------------------------------------------------------------------------


def test_eval_cypher_coverage_full():
    fake = FakeConnector([(_matchany(), [{"coverage": 0.99}])])
    level, measured, threshold, notes = _eval_cypher(
        fake, {"query": "MATCH ..."}, defaults={"partial_threshold": 0.5, "full_threshold": 0.95}
    )
    assert level == YES
    assert measured["value"] == 0.99


def test_eval_cypher_coverage_partial():
    fake = FakeConnector([(_matchany(), [{"coverage": 0.6}])])
    level, *_ = _eval_cypher(
        fake, {"query": "..."}, defaults={"partial_threshold": 0.5, "full_threshold": 0.95}
    )
    assert level == PARTIAL


def test_eval_cypher_coverage_no():
    fake = FakeConnector([(_matchany(), [{"coverage": 0.2}])])
    level, *_ = _eval_cypher(
        fake, {"query": "..."}, defaults={"partial_threshold": 0.5, "full_threshold": 0.95}
    )
    assert level == NO


def test_eval_cypher_count_with_thresholds():
    fake = FakeConnector([(_matchany(), [{"index_count": 10}])])
    level, measured, threshold, _ = _eval_cypher(
        fake,
        {"query": "...", "partial_threshold": 8, "full_threshold": 15},
        defaults={"partial_threshold": 0.5, "full_threshold": 0.95},
    )
    assert level == PARTIAL
    assert measured["value"] == 10.0
    assert threshold["full_threshold"] == 15.0


def test_eval_cypher_no_rows_is_no():
    fake = FakeConnector([(_matchany(), [])])
    level, *_ = _eval_cypher(
        fake, {"query": "..."}, defaults={"partial_threshold": 0.5, "full_threshold": 0.95}
    )
    assert level == NO


def test_eval_cypher_no_connector_is_no():
    level, measured, *_ = _eval_cypher(
        None, {"query": "..."}, defaults={"partial_threshold": 0.5, "full_threshold": 0.95}
    )
    assert level == NO
    assert "no connector" in measured["error"]


def test_eval_file_all_present(tmp_path):
    (tmp_path / "a").write_text("a")
    (tmp_path / "b").write_text("b")
    level, measured, *_ = _eval_file(
        {"paths": ["a", "b"], "full_if_all": True, "partial_if_any": True},
        tmp_path,
    )
    assert level == YES
    assert measured["missing"] == []


def test_eval_file_some_present(tmp_path):
    (tmp_path / "a").write_text("a")
    level, measured, *_ = _eval_file(
        {"paths": ["a", "b"], "full_if_all": True, "partial_if_any": True},
        tmp_path,
    )
    assert level == PARTIAL
    assert "b" in measured["missing"]


def test_eval_file_none_present(tmp_path):
    level, *_ = _eval_file(
        {"paths": ["a", "b"], "full_if_all": True, "partial_if_any": True},
        tmp_path,
    )
    assert level == NO


def test_eval_manual_yes():
    level, *_ = _eval_manual({"default": "yes"})
    assert level == YES


def test_eval_manual_partial_token():
    level, *_ = _eval_manual({"default": "partial"})
    assert level == PARTIAL


def test_eval_manual_numeric():
    assert _eval_manual({"default": 1.0})[0] == YES
    assert _eval_manual({"default": 0.5})[0] == PARTIAL
    assert _eval_manual({"default": 0.0})[0] == NO


def test_eval_manual_unrecognised_is_no():
    level, *_ = _eval_manual({"default": "definitely-not"})
    assert level == NO


# ---------------------------------------------------------------------------
# Whole-rubric scoring
# ---------------------------------------------------------------------------


def _passing_responses() -> list:
    """Every Cypher principle returns coverage=1.0; manual & file checks
    return their default (yes) and the existing project files."""

    # Order matters — first matching predicate wins. Put F2 (avg_properties)
    # *before* F1 / R1.2 because F1's WHERE clause overlaps with F2's.
    return [
        # F2 — avg properties per data node
        (lambda q, p: "RETURN avg(size(keys(n)))" in q, [{"avg_properties": 9.0}]),
        # F4 — index count
        (lambda q, p: "SHOW INDEXES" in q, [{"index_count": 20}]),
        # F3 — OntologyConcept code+uri pair
        (lambda q, p: "o.code IS NOT NULL AND o.uri IS NOT NULL" in q, [{"coverage": 1.0}]),
        # I1 — edge-level URI coverage (rev: was type-level "annotated" check)
        (
            lambda q, p: (
                "MATCH ()-[r]->()" in q
                and "count(r) AS total" in q
                and "with_uri" in q
                and "type(r)" not in q
            ),
            [{"coverage": 1.0}],
        ),
        # I2 / R1.3 — five FAIR-aligned vocabularies present
        (lambda q, p: "['SNOMED-CT','LOINC','UBERON','HPO','ICD-10']" in q, [{"coverage": 1.0}]),
        # I3 — the four qualified-reference edge types
        (lambda q, p: "['MAPS_TO','IS_A','CLASSIFIED_AS','SAME_AS']" in q, [{"coverage": 1.0}]),
        # R1.2 — provenance (BatchIngestion / batch_id / source_table)
        (lambda q, p: "BATCH_INGESTED_BY" in q or "n.batch_id IS NOT NULL" in q, [{"coverage": 1.0}]),
        # F1 — generic enriched-node ontology coverage (broadest predicate, last)
        (lambda q, p: "n.snomed_code IS NOT NULL" in q and "n.loinc_code IS NOT NULL" in q, [{"coverage": 1.0}]),
    ]


def test_score_fair_full_pass():
    """All Cypher-checked principles return full coverage; manual / file
    checks resolve to their rubric defaults. R1.1 defaults to 'partial' per
    the rubric (licence clarity needs human review), so the maximum
    achievable overall score under defaults is < 1.0."""

    rubric = load_rubric(RUBRIC_PATH)
    fake = FakeConnector(_passing_responses())
    report = score_fair(fake, rubric, graph_uri="test://mini", project_root=REPO_ROOT)
    # 12 principles at YES + 1 (R1.1) at PARTIAL = 12.5 / 13 ≈ 0.9615
    assert report.overall_score == pytest.approx(12.5 / 13, abs=1e-3)
    assert set(report.by_dimension) <= {"Findable", "Accessible", "Interoperable", "Reusable"}
    # Every Cypher principle should be YES; only R1.1 is partial.
    for pid, principle in report.principles.items():
        if pid == "R1.1":
            assert principle.level == PARTIAL, f"{pid} expected PARTIAL"
        else:
            assert principle.level == YES, f"{pid} expected YES, got {principle.level}"


def test_score_fair_no_connector_runs_only_manual_and_file():
    rubric = load_rubric(RUBRIC_PATH)
    report = score_fair(None, rubric, project_root=REPO_ROOT)
    # All Cypher principles will be NO; A1.1, A1.2, A2 (file) should still be evaluable
    assert report.principles["A1.1"].level == YES
    assert report.principles["A1.2"].level == YES
    # Cypher principles fall to NO since connector is None
    assert report.principles["F1"].level == NO


def test_to_dict_shape_and_dimension_aggregation():
    rubric = load_rubric(RUBRIC_PATH)
    fake = FakeConnector(_passing_responses())
    report = score_fair(fake, rubric, project_root=REPO_ROOT)
    d = report.to_dict()
    assert "by_dimension" in d
    # All four FAIR dimensions should appear
    assert {"Findable", "Accessible", "Interoperable", "Reusable"} <= set(d["by_dimension"])


def test_write_json_round_trip(tmp_path):
    rubric = load_rubric(RUBRIC_PATH)
    fake = FakeConnector(_passing_responses())
    report = score_fair(fake, rubric, project_root=REPO_ROOT)
    out = tmp_path / "fair.json"
    write_json(report, out)
    import json

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["overall_score"] == pytest.approx(12.5 / 13, abs=1e-3)


def test_diff_overall_and_per_principle():
    rubric = load_rubric(RUBRIC_PATH)
    fake_pass = FakeConnector(_passing_responses())
    fake_fail = FakeConnector([])  # everything → NO
    baseline = score_fair(fake_fail, rubric, project_root=REPO_ROOT)
    post = score_fair(fake_pass, rubric, project_root=REPO_ROOT)
    d = diff(baseline, post)
    assert d["overall_delta"] > 0
    # Every principle has a delta entry
    assert {row["id"] for row in d["per_principle"]} == set(rubric["principles"].keys())


def test_principle_check_exception_becomes_no():
    """If a Cypher check raises, the principle records NO with notes — never crashes."""

    class Boom:
        def run_query(self, query, parameters=None):
            raise RuntimeError("boom")

    rubric = load_rubric(RUBRIC_PATH)
    report = score_fair(Boom(), rubric, project_root=REPO_ROOT)
    # F1 is a cypher principle → its check raises → score NO
    assert report.principles["F1"].level == NO
    notes = " ".join(report.principles["F1"].notes)
    assert "RuntimeError" in notes or "raised" in notes


def test_load_rubric_rejects_malformed(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("foo: bar", encoding="utf-8")
    with pytest.raises(ValueError):
        load_rubric(bad)


def test_level_to_score_table():
    assert LEVEL_TO_SCORE[YES] == 1.0
    assert LEVEL_TO_SCORE[PARTIAL] == 0.5
    assert LEVEL_TO_SCORE[NO] == 0.0
