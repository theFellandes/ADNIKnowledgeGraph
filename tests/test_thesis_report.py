"""Tests for metrics.thesis_report (B-13).

These exercise the report renderer with a mix of present and missing
inputs, verifying graceful degradation in each section.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from metrics.thesis_report import (  # noqa: E402
    ReportInputs,
    SECTION_FNS,
    gather_inputs,
    render_full_report,
    render_per_section,
    write_report,
)


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------


def _make_inputs(tmp_path: Path, *, populate: bool = True) -> ReportInputs:
    """Build a ReportInputs with synthetic JSONs / figures."""

    metrics_root = tmp_path / "outputs"
    paper = tmp_path / "paper_outputs"
    eda = tmp_path / "eda_figures"
    mappings = tmp_path / "mappings"
    for d in (metrics_root / "metrics", metrics_root / "validity_reports", paper, eda, mappings):
        d.mkdir(parents=True, exist_ok=True)

    if populate:
        (metrics_root / "validity_reports" / "kg_validity_test.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "timestamp": "2026-05-09T00:00:00+00:00",
                    "graph_uri": "bolt://test",
                    "rubric_version": 1,
                    "result": "PASS",
                    "assertions": {},
                    "warnings": [],
                    "duration_seconds": 0.1,
                }
            ),
            encoding="utf-8",
        )
        (metrics_root / "validity_reports" / "kg_validity_test.md").write_text(
            "# KG Validity Report — test — RESULT: PASS\n\nbody body body\n",
            encoding="utf-8",
        )
        (metrics_root / "metrics" / "semantic_density.json").write_text(
            json.dumps(
                {
                    "aggregate": {
                        "node_density": 0.31,
                        "edge_density": 0.99,
                        "node_total": 100,
                        "node_with_uri": 31,
                        "edge_total": 200,
                        "edge_with_uri": 198,
                    },
                    "per_label": [
                        {"name": "Diagnosis", "total": 25, "with_uri": 25, "coverage": 1.0},
                        {"name": "FamilyMember", "total": 50, "with_uri": 0, "coverage": 0.0},
                    ],
                    "per_edge_type": [
                        {"name": "MAPS_TO", "total": 100, "with_uri": 100, "coverage": 1.0},
                    ],
                    "config": {},
                }
            ),
            encoding="utf-8",
        )
        (metrics_root / "metrics" / "fair_score.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "timestamp": "t",
                    "graph_uri": "x",
                    "rubric_version": 1,
                    "overall_score": 0.92,
                    "by_dimension": {"Findable": 1.0, "Accessible": 1.0,
                                     "Interoperable": 0.83, "Reusable": 0.67},
                    "principles": {
                        "F1": {"id": "F1", "name": "Findable 1", "level": "yes",
                                "score": 1.0, "measured": {}, "threshold": {}, "notes": []},
                        "R1.1": {"id": "R1.1", "name": "License", "level": "partial",
                                 "score": 0.5, "measured": {}, "threshold": {}, "notes": []},
                    },
                    "duration_seconds": 0.1,
                    "config": {},
                }
            ),
            encoding="utf-8",
        )
        (metrics_root / "metrics" / "alzkb_alignment.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "timestamp": "t",
                    "graph_uri": "x",
                    "alzkb_concept_total": 46,
                    "same_as_edge_total": 5,
                    "categories": [
                        {"name": "Disease", "total": 17, "strong_matches": 2,
                         "match_rate": 0.118, "not_implemented": False, "note": ""},
                        {"name": "Gene", "total": 0, "strong_matches": 0,
                         "match_rate": 0.0, "not_implemented": True, "note": "C4 deferred"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (eda / "eda_statistics.json").write_text(
            json.dumps(
                {
                    "total_nodes": 1234,
                    "total_relationships": 5678,
                    "node_labels": {"Diagnosis": 25, "Patient": 100},
                    "relationship_types": {"MAPS_TO": 50},
                }
            ),
            encoding="utf-8",
        )
        # SVG file marker
        (eda / "01_node_distribution.svg").write_bytes(b"<svg/>")
        (eda / "10_ontology_coverage.svg").write_bytes(b"<svg/>")
        (eda / "14_kg_summary_dashboard.svg").write_bytes(b"<svg/>")
        (eda / "15_relationship_schema.svg").write_bytes(b"<svg/>")
        (paper / "f1_dependency.svg").write_bytes(b"<svg/>")
        (paper / "f3_fair.svg").write_bytes(b"<svg/>")
        (paper / "f5_alignment.svg").write_bytes(b"<svg/>")
        (mappings / "index.csv").write_text(
            "source_csv,source_table,source_column,source_value_pattern,"
            "target_ontology,target_uri,target_label,mapping_rule,test_fixture_id,last_verified_date\n"
            "diagnosis_to_snomed_icd10.csv,DXSUM,DIAGNOSIS,AD,SNOMED-CT,snomed:26929004,Alzheimer's disease,exact_match,,2026-05-09\n",
            encoding="utf-8",
        )

    return gather_inputs(
        project_root=tmp_path,
        metrics_output_dir=metrics_root,
        paper_output_dir=paper,
        eda_figures_dir=eda,
        ontology_mappings_dir=mappings,
        include_eda=True,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_gather_with_full_inputs(tmp_path):
    inputs = _make_inputs(tmp_path)
    assert inputs.validity_json is not None
    assert inputs.fair["overall_score"] == 0.92
    assert inputs.alignment["alzkb_concept_total"] == 46
    assert inputs.density["aggregate"]["edge_density"] == 0.99
    assert len(inputs.eda_figures) >= 4
    assert len(inputs.paper_figures) == 3
    assert len(inputs.column_to_concept_rows) == 1


def test_gather_with_missing_inputs_does_not_raise(tmp_path):
    inputs = _make_inputs(tmp_path, populate=False)
    # All payloads should be None / empty
    assert inputs.validity_json is None
    assert inputs.fair is None
    assert inputs.alignment is None
    assert inputs.density is None
    assert inputs.column_to_concept_rows == []
    assert inputs.eda_figures == []


def test_render_full_report_produces_eleven_sections(tmp_path):
    inputs = _make_inputs(tmp_path)
    md = render_full_report(inputs)
    assert "# Evaluation of the MAKO Knowledge Graph" in md
    for i in range(1, 12):
        assert f"## {i}." in md, f"Section {i} missing"
    # Embedded SVG references
    assert "f3_fair.svg" in md
    assert "01_node_distribution.svg" in md
    # Headline numbers
    assert "0.92" in md  # FAIR
    assert "46" in md    # AlzKBConcept count


def test_render_full_report_with_missing_inputs(tmp_path):
    """Even if every input is missing, the renderer should not crash; it
    emits placeholder sections explaining what's missing."""

    inputs = _make_inputs(tmp_path, populate=False)
    md = render_full_report(inputs)
    assert "# Evaluation of the MAKO Knowledge Graph" in md
    # All 11 sections still emitted
    for i in range(1, 12):
        assert f"## {i}." in md
    # Includes "missing" hint
    assert "missing" in md.lower() or "not yet" in md.lower()


def test_per_section_slices(tmp_path):
    inputs = _make_inputs(tmp_path)
    sections = render_per_section(inputs)
    assert len(sections) == len(SECTION_FNS)
    expected_names = [name for name, _ in SECTION_FNS]
    assert list(sections.keys()) == expected_names
    for name, body in sections.items():
        assert isinstance(body, str)
        assert body, f"Section {name} produced empty body"


def test_write_report_creates_files(tmp_path):
    inputs = _make_inputs(tmp_path)
    out = tmp_path / "report"
    written = write_report(inputs, out, write_pdf=False)
    assert "markdown" in written
    assert written["markdown"].exists()
    assert written["markdown"].stat().st_size > 1000
    sections_dir = written["sections_dir"]
    assert sections_dir.is_dir()
    section_files = list(sections_dir.glob("*.md"))
    assert len(section_files) == len(SECTION_FNS)


def test_write_report_falls_back_to_html_without_pdf_backends(tmp_path, monkeypatch):
    """If no PDF backend is installed, --pdf should fall back to a styled
    HTML file (not silently drop the request, not raise)."""

    import tools.md_to_pdf as md_mod

    monkeypatch.setattr(md_mod, "_have_pandoc", lambda: None)
    monkeypatch.setattr(md_mod, "_have_weasyprint", lambda: False)
    monkeypatch.setattr(md_mod, "_have_xhtml2pdf", lambda: False)

    inputs = _make_inputs(tmp_path)
    written = write_report(inputs, tmp_path / "report", write_pdf=True)
    assert "markdown" in written
    # Fallback puts an .html file under the 'pdf' key — caller can
    # detect via the suffix.
    assert "pdf" in written
    assert written["pdf"].suffix == ".html"
    assert written["pdf"].exists()


def test_executive_summary_uses_alignment_in_scope_count(tmp_path):
    inputs = _make_inputs(tmp_path)
    md = render_per_section(inputs)["01_executive_summary"]
    # The fixture has 1 in-scope category (Disease, with strong=2 > 0).
    # The summary should report "1 of 1 ... strong match" somewhere.
    assert "1 of 1" in md
    # Headline title (case-insensitive)
    assert "summary of findings" in md.lower()


def test_alignment_section_marks_gene_as_na(tmp_path):
    inputs = _make_inputs(tmp_path)
    md = render_per_section(inputs)["06_alignment"]
    assert "Gene" in md
    assert "N/A" in md


def test_eda_section_lists_present_panels(tmp_path):
    """The exploratory data analysis section embeds figures that are NOT
    already shown in the earlier composition / density sections (which
    pull from the same set). Confirm the de-duplication is honoured."""
    inputs = _make_inputs(tmp_path)
    md = render_per_section(inputs)["09_eda_panels"]
    # 01_node_distribution is unique to §9
    assert "01_node_distribution" in md
    # 10_ontology_coverage is shown in §4, 14/15 in §2 — not duplicated in §9
    assert "10_ontology_coverage" not in md
    assert "14_kg_summary_dashboard" not in md
    assert "15_relationship_schema" not in md


def test_kg_state_embeds_dashboard_and_schema(tmp_path):
    """§2 (Knowledge graph composition) is where the dashboard + schema
    figures live, not §9."""
    inputs = _make_inputs(tmp_path)
    md = render_per_section(inputs)["02_kg_state"]
    assert "14_kg_summary_dashboard" in md
    assert "15_relationship_schema" in md


def test_density_section_embeds_ontology_coverage(tmp_path):
    inputs = _make_inputs(tmp_path)
    md = render_per_section(inputs)["04_density"]
    assert "10_ontology_coverage" in md


def test_no_eda_skips_panels(tmp_path):
    inputs = _make_inputs(tmp_path)
    inputs.include_eda = False
    inputs.eda_figures = []
    md = render_per_section(inputs)["09_eda_panels"]
    assert "not embedded" in md.lower()
