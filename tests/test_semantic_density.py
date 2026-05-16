"""Tests for metrics.semantic_density.

Strategy mirrors test_validity.py: a FakeConnector returns canned rows that
imitate the responses validity / density would get from the synthetic
fixture, plus deliberately-poisoned variants for the failure paths.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from metrics.semantic_density import (  # noqa: E402
    CoverageEntry,
    DensityReport,
    compute_density,
    diff,
    write_json,
)


# ---------------------------------------------------------------------------
# Shared FakeConnector
# ---------------------------------------------------------------------------


class FakeConnector:
    def __init__(self, query_responses):
        # query_responses: list of (predicate_callable_or_substring, rows)
        self.query_responses = query_responses
        self.calls = []

    def run_query(self, query, parameters=None):
        self.calls.append((query, parameters))
        for predicate, rows in self.query_responses:
            if callable(predicate):
                if predicate(query, parameters or {}):
                    return rows
            elif isinstance(predicate, str):
                if predicate in query:
                    return rows
        raise AssertionError(f"no handler for query: {query!r}")


_DEFAULT_LABELS = [
    {"label": "Diagnosis", "total": 4, "with_uri": 4},
    {"label": "CognitiveAssessment", "total": 4, "with_uri": 4},
    {"label": "Biomarker", "total": 3, "with_uri": 3},
    {"label": "BrainRegion", "total": 3, "with_uri": 3},
    {"label": "Patient", "total": 4, "with_uri": 4},
    {"label": "Visit", "total": 4, "with_uri": 4},
    {"label": "OntologyConcept", "total": 7, "with_uri": 7},
]
_DEFAULT_EDGES = [
    {"rel_type": "MAPS_TO", "total": 12, "with_uri": 12},
    {"rel_type": "HAS_VISIT", "total": 4, "with_uri": 4},
    {"rel_type": "HAS_DIAGNOSIS", "total": 4, "with_uri": 4},
    {"rel_type": "HAS_ASSESSMENT", "total": 4, "with_uri": 4},
    {"rel_type": "HAS_BIOMARKER", "total": 3, "with_uri": 3},
    {"rel_type": "HAS_REGION", "total": 3, "with_uri": 3},
    {"rel_type": "CLASSIFIED_AS", "total": 4, "with_uri": 4},
    {"rel_type": "IS_A", "total": 2, "with_uri": 2},
]
_SENTINEL = object()


def _density_handlers(
    label_rows=_SENTINEL,
    edge_rows=_SENTINEL,
    node_total=20,
    node_with_uri=18,
    edge_total=40,
    edge_with_uri=36,
):
    """Build the four handlers compute_density expects, in the right order.

    Pass ``label_rows=[]`` or ``edge_rows=[]`` to simulate an empty graph;
    omit them to use the default mini-KG-like response set.
    """

    if label_rows is _SENTINEL:
        label_rows = _DEFAULT_LABELS
    if edge_rows is _SENTINEL:
        edge_rows = _DEFAULT_EDGES

    return [
        # 1) per-label query
        ("UNWIND labels(n) AS label", label_rows),
        # 2) per-edge-type query  — use lambda to discriminate from the agg edge query
        (lambda q, p: "WITH type(r) AS rel_type, r" in q, edge_rows),
        # 3) aggregate node query
        (
            lambda q, p: q.startswith("MATCH (n) WITH n"),
            [{"total": node_total, "with_uri": node_with_uri}],
        ),
        # 4) aggregate edge query
        (
            lambda q, p: q.startswith("MATCH ()-[r]->() RETURN"),
            [{"total": edge_total, "with_uri": edge_with_uri}],
        ),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_compute_density_full_coverage():
    report = compute_density(FakeConnector(_density_handlers()), graph_uri="test://mini")
    assert report.node_total == 20
    assert report.node_with_uri == 18
    assert report.edge_total == 40
    assert report.edge_with_uri == 36
    assert report.node_density == pytest.approx(0.9)
    assert report.edge_density == pytest.approx(0.9)
    # Per-label and per-edge-type breakdowns preserved
    assert {e.name for e in report.per_label} >= {"Diagnosis", "OntologyConcept"}
    assert {e.name for e in report.per_edge_type} >= {"MAPS_TO", "IS_A"}


def test_compute_density_zero_graph():
    report = compute_density(
        FakeConnector(
            _density_handlers(
                label_rows=[],
                edge_rows=[],
                node_total=0,
                node_with_uri=0,
                edge_total=0,
                edge_with_uri=0,
            )
        )
    )
    assert report.node_density == 0.0
    assert report.edge_density == 0.0
    assert report.per_label == []


def test_compute_density_partial_coverage():
    report = compute_density(
        FakeConnector(
            _density_handlers(
                node_total=100, node_with_uri=42, edge_total=200, edge_with_uri=160
            )
        )
    )
    assert report.node_density == pytest.approx(0.42)
    assert report.edge_density == pytest.approx(0.8)


def test_to_dict_shape():
    report = compute_density(FakeConnector(_density_handlers()))
    d = report.to_dict()
    assert d["schema_version"] == 1
    assert "aggregate" in d
    assert d["aggregate"]["node_density"] == 0.9
    assert isinstance(d["per_label"], list)
    assert isinstance(d["per_edge_type"], list)


def test_write_json_round_trip(tmp_path):
    report = compute_density(FakeConnector(_density_handlers()))
    path = tmp_path / "density.json"
    write_json(report, path)
    assert path.exists()
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["aggregate"]["node_density"] == 0.9


def test_diff_per_label_and_aggregate():
    baseline = compute_density(
        FakeConnector(
            _density_handlers(
                node_total=100, node_with_uri=10, edge_total=200, edge_with_uri=20
            )
        )
    )
    post = compute_density(
        FakeConnector(
            _density_handlers(
                node_total=100, node_with_uri=80, edge_total=200, edge_with_uri=180
            )
        )
    )
    d = diff(baseline, post)
    assert d["aggregate"]["node_density_delta"] == pytest.approx(0.7)
    assert d["aggregate"]["edge_density_delta"] == pytest.approx(0.8)
    # Per-label entries each have baseline + post + delta
    for entry in d["per_label"]:
        assert "baseline" in entry and "post" in entry and "delta_coverage" in entry


def test_coverage_entry_zero_denominator():
    e = CoverageEntry("Empty", 0, 0)
    assert e.coverage == 0.0
    assert e.to_dict()["coverage"] == 0.0


def test_diff_handles_missing_label_in_one_side():
    """If a label exists in baseline but not post (or vice versa) the diff
    should still produce a row with the missing side as None."""

    base = DensityReport(
        schema_version=1,
        timestamp="t1",
        graph_uri="x",
        node_total=10,
        node_with_uri=5,
        edge_total=10,
        edge_with_uri=5,
        per_label=[CoverageEntry("Old", 5, 5)],
        per_edge_type=[],
    )
    post = DensityReport(
        schema_version=1,
        timestamp="t2",
        graph_uri="x",
        node_total=10,
        node_with_uri=10,
        edge_total=10,
        edge_with_uri=10,
        per_label=[CoverageEntry("New", 7, 7)],
        per_edge_type=[],
    )
    d = diff(base, post)
    by_name = {row["name"]: row for row in d["per_label"]}
    assert by_name["Old"]["post"] is None
    assert by_name["New"]["baseline"] is None
