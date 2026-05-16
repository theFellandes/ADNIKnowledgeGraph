"""Tests for metrics.step_audit."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from metrics.step_audit import (  # noqa: E402
    AuditRow,
    StepDiff,
    build_audit_rows,
    diff_snapshots,
    load_density_per_step,
    load_fair_per_step,
    parse_runtime_log,
    snapshot_counts,
    write_csv,
)


# ---------------------------------------------------------------------------
# Fake connector
# ---------------------------------------------------------------------------


class FakeConnector:
    def __init__(self, **counts):
        # counts keyed by query substring → row dict
        self.counts = counts
        self.calls = []

    def run_query(self, query, parameters=None):
        self.calls.append(query)
        for fragment, n in self.counts.items():
            if fragment in query:
                return [{"n": n}]
        return [{"n": 0}]


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def test_snapshot_counts_extracts_all_four_metrics():
    fake = FakeConnector(**{
        "MATCH (n) RETURN count(n)": 100,
        "MATCH ()-[r]->() RETURN count(r)": 200,
        "UNWIND labels(n) AS lbl": 7,
        "MATCH ()-[r]->() WITH DISTINCT type(r)": 5,
    })
    counts = snapshot_counts(fake, label="post_step_17")
    assert counts == {
        "label": "post_step_17",
        "nodes": 100,
        "edges": 200,
        "distinct_labels": 7,
        "distinct_rel_types": 5,
    }


def test_diff_snapshots_growth_only():
    before = {"nodes": 10, "edges": 20, "distinct_labels": 3, "distinct_rel_types": 4}
    after = {"nodes": 25, "edges": 45, "distinct_labels": 5, "distinct_rel_types": 6}
    d = diff_snapshots(before, after, "17")
    assert d.nodes_added == 15
    assert d.edges_added == 25
    assert d.distinct_labels_after == 5


def test_diff_snapshots_clamped_at_zero():
    """If something shrinks (rollback weirdness) we report zero, not negative."""

    before = {"nodes": 100, "edges": 200, "distinct_labels": 10, "distinct_rel_types": 12}
    after = {"nodes": 50, "edges": 100, "distinct_labels": 8, "distinct_rel_types": 10}
    d = diff_snapshots(before, after, "rollback")
    assert d.nodes_added == 0
    assert d.edges_added == 0


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def test_load_fair_per_step(tmp_path):
    p = tmp_path / "fair.json"
    payload = {
        "per_step": {
            "17": {"overall_score": 0.50},
            "18": {"overall_score": 0.65},
        }
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    out = load_fair_per_step(p)
    assert out == {"17": 0.50, "18": 0.65}


def test_load_fair_per_step_handles_flat_dict(tmp_path):
    p = tmp_path / "fair.json"
    p.write_text(json.dumps({"17": 0.50, "18": 0.65}), encoding="utf-8")
    out = load_fair_per_step(p)
    assert out == {"17": 0.50, "18": 0.65}


def test_load_fair_per_step_missing_file_returns_empty(tmp_path):
    out = load_fair_per_step(tmp_path / "no.json")
    assert out == {}


def test_load_density_per_step(tmp_path):
    p = tmp_path / "density.json"
    payload = {
        "per_step": {
            "17": {"node_density": 0.40, "edge_density": 0.30},
            "18": {"aggregate": {"node_density": 0.55, "edge_density": 0.50}},
        }
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    out = load_density_per_step(p)
    assert out["17"]["node_density"] == 0.40
    assert out["18"]["edge_density"] == 0.50


# ---------------------------------------------------------------------------
# Runtime parsing
# ---------------------------------------------------------------------------


def test_parse_runtime_log_basic_units(tmp_path):
    log = tmp_path / "pipeline.log"
    log.write_text(
        "Starting Step 17\nStep 17 completed in 12.3s\n"
        "Step 18 done in 4500ms\nStep 19 took 1 min\n",
        encoding="utf-8",
    )
    runtimes = parse_runtime_log(log)
    assert runtimes["17"] == pytest.approx(12.3)
    assert runtimes["18"] == pytest.approx(4.5)
    assert runtimes["19"] == pytest.approx(60.0)


def test_parse_runtime_log_missing_file_returns_empty(tmp_path):
    assert parse_runtime_log(tmp_path / "nope.log") == {}


# ---------------------------------------------------------------------------
# Audit assembly
# ---------------------------------------------------------------------------


def _diffs():
    return [
        StepDiff(step="17", nodes_before=100, nodes_after=100, edges_before=200, edges_after=212),
        StepDiff(step="18", nodes_before=100, nodes_after=100, edges_before=212, edges_after=212),
        StepDiff(step="19", nodes_before=100, nodes_after=105, edges_before=212, edges_after=237),
        StepDiff(step="20", nodes_before=105, nodes_after=152, edges_before=237, edges_after=337),
    ]


def test_build_audit_rows_with_full_inputs():
    fair_per_step = {"17": 0.50, "18": 0.62, "19": 0.74, "20": 0.85}
    density_per_step = {
        "17": {"node_density": 0.20, "edge_density": 0.30},
        "18": {"node_density": 0.40, "edge_density": 0.45},
        "19": {"node_density": 0.55, "edge_density": 0.60},
        "20": {"node_density": 0.85, "edge_density": 0.95},
    }
    runtimes = {"17": 12.3, "18": 4.5, "19": 60.0, "20": 30.0}

    rows = build_audit_rows(
        _diffs(),
        fair_per_step=fair_per_step,
        density_per_step=density_per_step,
        runtimes=runtimes,
    )
    by_step = {r.step: r for r in rows}

    # First step has no prior reference → deltas are None
    assert by_step["17"].fair_delta_overall is None
    assert by_step["17"].density_delta_node is None
    # Subsequent steps compute deltas
    assert by_step["18"].fair_delta_overall == pytest.approx(0.12)
    assert by_step["19"].density_delta_edge == pytest.approx(0.15)
    # Counts come from diffs
    assert by_step["20"].nodes_touched == 47
    assert by_step["20"].edges_added == 100
    # Runtimes attach correctly
    assert by_step["17"].runtime_s == pytest.approx(12.3)


def test_build_audit_rows_handles_partial_inputs():
    """If FAIR / density are absent for some steps, deltas stay None instead of crashing."""

    rows = build_audit_rows(_diffs(), fair_per_step={"17": 0.50}, density_per_step={})
    by_step = {r.step: r for r in rows}
    assert by_step["17"].fair_delta_overall is None
    assert by_step["18"].fair_delta_overall is None  # no value for 18 → no delta
    assert by_step["18"].density_delta_node is None


def test_write_csv_round_trip(tmp_path):
    rows = [
        AuditRow(step="17", nodes_touched=0, edges_added=12, properties_added=0,
                 runtime_s=12.3, fair_delta_overall=None,
                 density_delta_node=None, density_delta_edge=None),
        AuditRow(step="18", nodes_touched=0, edges_added=0, properties_added=0,
                 runtime_s=4.5, fair_delta_overall=0.12,
                 density_delta_node=0.20, density_delta_edge=0.15),
    ]
    out = tmp_path / "audit.csv"
    write_csv(rows, out)
    with open(out, "r", encoding="utf-8", newline="") as f:
        reader = list(csv.DictReader(f))
    assert reader[0]["step"] == "17"
    assert reader[1]["fair_delta_overall"] == "0.12"
    assert reader[0]["fair_delta_overall"] == ""  # None serialises empty
