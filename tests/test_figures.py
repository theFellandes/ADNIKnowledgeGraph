"""Smoke tests for the figures package.

These verify that each figure script:
  - parses the JSON shape it expects
  - returns a matplotlib Figure (or writes a Mermaid file)
  - writes SVG / PDF to disk

The actual visual correctness is left to manual review of the rendered
SVGs in paper_outputs/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Skip the whole module if matplotlib is missing — figures are optional in
# minimal environments.
matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")  # no display

import matplotlib.pyplot as plt  # noqa: E402

from figures import f1_dependency, f2_schema, f3_fair, f4_density, f5_alignment  # noqa: E402


# ---------------------------------------------------------------------------
# F1 / F2 — Mermaid emitters
# ---------------------------------------------------------------------------


def test_f1_writes_mermaid(tmp_path):
    out = tmp_path / "f1.mmd"
    written = f1_dependency.write_mermaid(out)
    assert written.exists()
    body = written.read_text(encoding="utf-8")
    assert "flowchart" in body
    assert "C7" in body
    assert "REMOVED" in body  # C4 box should be marked as removed


def test_f2_writes_mermaid_with_before_after(tmp_path):
    out = tmp_path / "f2.mmd"
    f2_schema.write_mermaid(out)
    body = out.read_text(encoding="utf-8")
    assert "Before" in body and "After" in body
    assert "MAPS_TO" in body
    # Must visibly differ from step29 fig 15 — we mark this by including
    # explicit subgraphs (delta framing) which step 29's single-state schema
    # doesn't have.
    assert "subgraph Before" in body
    assert "subgraph After" in body


# ---------------------------------------------------------------------------
# F3 — FAIR scorecard
# ---------------------------------------------------------------------------


def _fair_payload(score_per_principle: dict[str, float]) -> dict:
    return {
        "schema_version": 1,
        "timestamp": "test",
        "graph_uri": "test",
        "rubric_version": 1,
        "overall_score": sum(score_per_principle.values()) / max(len(score_per_principle), 1),
        "by_dimension": {},
        "principles": {
            pid: {"id": pid, "name": pid, "level": "yes" if s >= 0.95 else "partial",
                  "score": s, "measured": {}, "threshold": {}, "notes": []}
            for pid, s in score_per_principle.items()
        },
        "duration_seconds": 0.1,
        "config": {},
    }


def test_f3_renders_with_baseline_and_post(tmp_path):
    baseline = tmp_path / "fair_baseline.json"
    post = tmp_path / "fair_post.json"
    baseline.write_text(json.dumps(_fair_payload(
        {"F1": 0.0, "F2": 0.5, "F3": 0.0, "F4": 0.5,
         "A1.1": 1.0, "A1.2": 1.0, "A2": 0.5,
         "I1": 0.0, "I2": 0.0, "I3": 0.0,
         "R1.1": 0.5, "R1.2": 0.5, "R1.3": 0.0}
    )), encoding="utf-8")
    post.write_text(json.dumps(_fair_payload(
        {"F1": 1.0, "F2": 1.0, "F3": 1.0, "F4": 1.0,
         "A1.1": 1.0, "A1.2": 1.0, "A2": 1.0,
         "I1": 1.0, "I2": 1.0, "I3": 1.0,
         "R1.1": 0.5, "R1.2": 1.0, "R1.3": 1.0}
    )), encoding="utf-8")

    baseline_scores = f3_fair._load_principle_scores(baseline)
    post_scores = f3_fair._load_principle_scores(post)
    fig, ax = f3_fair.render_scorecard(baseline_scores, post_scores)
    written = f3_fair.save_outputs(fig, tmp_path / "f3_fair.svg")
    plt.close(fig)
    suffixes = sorted(p.suffix for p in written)
    # save_outputs writes SVG + PDF + PNG (PNG added so reportlab can embed
    # a raster fallback when svglib chokes on matplotlib stroke-dasharray).
    assert suffixes == [".pdf", ".png", ".svg"]
    for p in written:
        assert p.stat().st_size > 0


def test_f3_renders_post_only_when_baseline_missing(tmp_path):
    post = tmp_path / "fair_post.json"
    post.write_text(
        json.dumps(_fair_payload({"F1": 1.0, "F2": 1.0, "F3": 1.0, "F4": 1.0})),
        encoding="utf-8",
    )
    baseline_scores = f3_fair._load_principle_scores(tmp_path / "missing.json")
    post_scores = f3_fair._load_principle_scores(post)
    assert baseline_scores == {}
    fig, _ = f3_fair.render_scorecard(baseline_scores, post_scores)
    f3_fair.save_outputs(fig, tmp_path / "f3.svg")
    plt.close(fig)


def test_f3_raises_when_no_data():
    with pytest.raises(ValueError):
        f3_fair.render_scorecard({}, {})


# ---------------------------------------------------------------------------
# F4 — Semantic density progression
# ---------------------------------------------------------------------------


def test_f4_renders_progression(tmp_path):
    payload = {
        "per_step": {
            "pre": {"node_density": 0.10, "edge_density": 0.12},
            "17":  {"node_density": 0.18, "edge_density": 0.21},
            "18":  {"node_density": 0.42, "edge_density": 0.48},
            "19":  {"node_density": 0.55, "edge_density": 0.62},
            "20":  {"node_density": 0.85, "edge_density": 0.95},
        }
    }
    p = tmp_path / "density.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    per_step = f4_density._load_per_step(p)
    assert "pre" in per_step and "20" in per_step

    fig, _ = f4_density.render_progression(per_step)
    written = f4_density.save_outputs(fig, tmp_path / "f4.svg")
    plt.close(fig)
    assert any(p.suffix == ".svg" for p in written)


def test_f4_accepts_aggregate_shape(tmp_path):
    """Density JSON can also have an `aggregate` sub-dict (semantic_density.write_json shape)."""

    payload = {
        "per_step": {
            "pre": {"aggregate": {"node_density": 0.10, "edge_density": 0.20}},
            "20":  {"aggregate": {"node_density": 0.85, "edge_density": 0.95}},
        }
    }
    p = tmp_path / "density.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    per_step = f4_density._load_per_step(p)
    assert per_step["pre"]["node_density"] == 0.10
    assert per_step["20"]["edge_density"] == 0.95


def test_f4_missing_input_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        f4_density._load_per_step(tmp_path / "missing.json")


# ---------------------------------------------------------------------------
# F5 — AlzKB alignment matrix
# ---------------------------------------------------------------------------


def _alignment_payload(per_category):
    return {
        "schema_version": 1,
        "timestamp": "test",
        "graph_uri": "x",
        "alzkb_concept_total": 0,
        "same_as_edge_total": 0,
        "categories": [
            {"name": name, **data} for name, data in per_category.items()
        ],
    }


def test_f5_renders_with_baseline_and_post(tmp_path):
    baseline = _alignment_payload({
        "Disease":   {"total": 5, "strong_matches": 0, "match_rate": 0.0, "not_implemented": False},
        "Anatomy":   {"total": 4, "strong_matches": 4, "match_rate": 1.0, "not_implemented": False},
        "Phenotype": {"total": 3, "strong_matches": 0, "match_rate": 0.0, "not_implemented": False},
        "Gene":      {"total": 0, "strong_matches": 0, "match_rate": 0.0, "not_implemented": True},
    })
    post = _alignment_payload({
        "Disease":   {"total": 5, "strong_matches": 5, "match_rate": 1.0, "not_implemented": False},
        "Anatomy":   {"total": 4, "strong_matches": 4, "match_rate": 1.0, "not_implemented": False},
        "Phenotype": {"total": 3, "strong_matches": 3, "match_rate": 1.0, "not_implemented": False},
        "Gene":      {"total": 0, "strong_matches": 0, "match_rate": 0.0, "not_implemented": True},
    })
    bp = tmp_path / "baseline.json"
    pp = tmp_path / "post.json"
    bp.write_text(json.dumps(baseline), encoding="utf-8")
    pp.write_text(json.dumps(post), encoding="utf-8")

    base = f5_alignment._load_alignment(bp)
    pst = f5_alignment._load_alignment(pp)
    fig, _ = f5_alignment.render_alignment_matrix(base, pst)
    written = f5_alignment.save_outputs(fig, tmp_path / "f5.svg")
    plt.close(fig)
    assert all(p.exists() for p in written)


def test_f5_band_helper():
    assert f5_alignment._band({"not_implemented": True})[0] == "N/A"
    assert f5_alignment._band({"match_rate": 0.6, "not_implemented": False})[0] == "strong"
    assert f5_alignment._band({"match_rate": 0.3, "not_implemented": False})[0] == "weak"
    assert f5_alignment._band({"match_rate": 0.0, "not_implemented": False})[0] == "none"


def test_f5_missing_alignment_returns_empty_dict(tmp_path):
    out = f5_alignment._load_alignment(tmp_path / "no.json")
    assert out == {}
