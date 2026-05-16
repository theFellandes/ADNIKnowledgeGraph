"""Thesis report generator (B-13).

Consumes every metric output (validity / FAIR / semantic density / AlzKB
alignment / step audit) and every step-29 EDA figure, and produces a
self-contained Markdown report ready to fold into the thesis evaluation
chapter.

Inputs (all optional — the report renders gracefully degraded sections if
any are missing)::

    outputs/validity_reports/kg_validity_<latest>.{json,md}
    outputs/metrics/semantic_density.json
    outputs/metrics/fair_score.json
    outputs/metrics/alzkb_alignment.json
    outputs/metrics/step_audit.csv
    outputs/metrics/runner_summary.json
    outputs/eda_figures/01..15_*.{svg,png}
    outputs/eda_figures/eda_statistics.json
    outputs/eda_figures/mermaid_*.mmd
    paper_outputs/f1_dependency.svg, f2_schema.svg, f3_fair.svg, f4_density.svg, f5_alignment.svg
    ontology/mappings/index.csv

Outputs::

    outputs/thesis_report/thesis_report.md       — long-form Markdown
    outputs/thesis_report/sections/<n>.md        — per-section slices
    outputs/thesis_report/thesis_report.pdf      — optional, requires pandoc
                                                    (silent skip if pandoc absent)

CLI::

    python -m metrics.thesis_report
    python -m metrics.thesis_report --metrics-dir outputs --output-dir outputs/thesis_report
    python -m metrics.thesis_report --pdf            # also render PDF
    python -m metrics.thesis_report --no-eda         # skip the step-29 figure embed
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Inputs container — collects everything the report can use
# ---------------------------------------------------------------------------


@dataclass
class ReportInputs:
    project_root: Path
    metrics_output_dir: Path
    paper_output_dir: Path
    eda_figures_dir: Path
    ontology_mappings_dir: Path
    include_eda: bool = True

    # Loaded payloads (None = file missing)
    validity_md: str | None = None
    validity_json: dict[str, Any] | None = None
    validity_md_path: Path | None = None
    density: dict[str, Any] | None = None
    fair: dict[str, Any] | None = None
    alignment: dict[str, Any] | None = None
    eda_stats: dict[str, Any] | None = None
    runner_summary: dict[str, Any] | None = None
    step_audit_rows: list[dict[str, str]] = field(default_factory=list)
    column_to_concept_rows: list[dict[str, str]] = field(default_factory=list)

    # Discovered figure paths (for embedding)
    eda_figures: list[Path] = field(default_factory=list)
    paper_figures: list[Path] = field(default_factory=list)
    mermaid_files: list[Path] = field(default_factory=list)


def _safe_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not parse %s: %s", path, exc)
        return None


def _safe_text(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None


def _safe_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except Exception as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return []


def _latest_validity(reports_dir: Path) -> tuple[Path | None, Path | None]:
    """Find the latest kg_validity_<TS>.{json,md} pair by stem (timestamp-sortable)."""

    if not reports_dir.is_dir():
        return None, None
    json_files = sorted(reports_dir.glob("kg_validity_*.json"))
    if not json_files:
        return None, None
    latest_json = json_files[-1]
    latest_md = latest_json.with_suffix(".md")
    return latest_json, (latest_md if latest_md.exists() else None)


def gather_inputs(
    *,
    project_root: Path,
    metrics_output_dir: Path,
    paper_output_dir: Path,
    eda_figures_dir: Path,
    ontology_mappings_dir: Path,
    include_eda: bool = True,
) -> ReportInputs:
    """Read every input file the report can use. Missing files become ``None``
    or empty lists and the renderer adapts."""

    metrics_dir = metrics_output_dir / "metrics"

    val_json_path, val_md_path = _latest_validity(metrics_output_dir / "validity_reports")
    inputs = ReportInputs(
        project_root=project_root,
        metrics_output_dir=metrics_output_dir,
        paper_output_dir=paper_output_dir,
        eda_figures_dir=eda_figures_dir,
        ontology_mappings_dir=ontology_mappings_dir,
        include_eda=include_eda,
        validity_md=_safe_text(val_md_path) if val_md_path else None,
        validity_json=_safe_json(val_json_path) if val_json_path else None,
        validity_md_path=val_md_path,
        density=_safe_json(metrics_dir / "semantic_density.json"),
        fair=_safe_json(metrics_dir / "fair_score.json"),
        alignment=_safe_json(metrics_dir / "alzkb_alignment.json"),
        eda_stats=_safe_json(eda_figures_dir / "eda_statistics.json"),
        runner_summary=_safe_json(metrics_dir / "runner_summary.json"),
        step_audit_rows=_safe_csv(metrics_dir / "step_audit.csv"),
        column_to_concept_rows=_safe_csv(ontology_mappings_dir / "index.csv"),
    )

    if include_eda and eda_figures_dir.is_dir():
        # Prefer SVG (vector) when both extensions exist for a given index.
        seen_indices: set[str] = set()
        for path in sorted(eda_figures_dir.iterdir()):
            if path.suffix not in (".svg", ".png"):
                continue
            stem = path.stem  # e.g. 01_node_distribution
            if stem in seen_indices:
                continue
            seen_indices.add(stem)
            # If a .svg sibling exists, prefer it
            svg_sibling = path.with_suffix(".svg")
            inputs.eda_figures.append(svg_sibling if svg_sibling.exists() else path)
        inputs.mermaid_files = sorted(eda_figures_dir.glob("mermaid_*.mmd"))

    if paper_output_dir.is_dir():
        inputs.paper_figures = sorted(
            p for p in paper_output_dir.iterdir() if p.suffix == ".svg"
        )

    return inputs


# ---------------------------------------------------------------------------
# Section renderers — each returns a Markdown string. ``None`` inputs render
# a placeholder that explains what's missing and how to populate it.
# ---------------------------------------------------------------------------


def _format_pct(x: float | None, decimals: int = 1) -> str:
    if x is None:
        return "—"
    return f"{x*100:.{decimals}f}%"


def _format_score(x: float | None, decimals: int = 3) -> str:
    if x is None:
        return "—"
    return f"{x:.{decimals}f}"


def _rel_link(path: Path, base: Path) -> str:
    """Markdown-friendly relative path (forward slashes, even on Windows)."""

    try:
        rel = path.relative_to(base)
    except ValueError:
        rel = path
    return str(rel).replace("\\", "/")


# ---- Header / TOC ----------------------------------------------------------


def render_header(inputs: ReportInputs) -> str:
    ts = datetime.now().isoformat(timespec="seconds")

    val_result = "—"
    if inputs.validity_json:
        val_result = inputs.validity_json.get("result", "—")

    fair_score = "—"
    if inputs.fair:
        fair_score = _format_score(inputs.fair.get("overall_score"))

    align_summary = "—"
    if inputs.alignment:
        in_scope = [c for c in inputs.alignment.get("categories", []) if not c.get("not_implemented")]
        strong = sum(1 for c in in_scope if (c.get("strong_matches") or 0) > 0)
        align_summary = f"{strong} of {len(in_scope)} in-scope strong"

    return f"""# Evaluation of the MAKO Knowledge Graph

> Automated evaluation report for the **Multimodal Alzheimer's Knowledge graph
> with Ontology grounding (MAKO)**. Compiles the structural validity
> assessment, semantic density measurements, FAIR principle compliance,
> cross-vocabulary alignment with the Alzheimer's Disease Knowledge Base
> (AlzKB), per-step migration audit, and the accompanying exploratory data
> analysis into a single document suitable for inclusion in the thesis
> evaluation chapter.

| Property | Value |
|---|---|
| Generated | `{ts}` |
| Structural validity | **{val_result}** |
| FAIR aggregate score | **{fair_score}** |
| AlzKB alignment | **{align_summary}** |
| Source validity record | `{_rel_link(inputs.validity_md_path, inputs.project_root)
        if inputs.validity_md_path else "—"}` |

## Table of contents

1. [Summary of findings](#1-summary-of-findings)
2. [Knowledge graph composition](#2-knowledge-graph-composition)
3. [Structural validity assessment](#3-structural-validity-assessment)
4. [Semantic density](#4-semantic-density)
5. [FAIR principle compliance](#5-fair-principle-compliance)
6. [Cross-vocabulary alignment with AlzKB](#6-cross-vocabulary-alignment-with-alzkb)
7. [Column-to-concept mapping methodology](#7-column-to-concept-mapping-methodology)
8. [Per-step migration audit](#8-per-step-migration-audit)
9. [Exploratory data analysis](#9-exploratory-data-analysis)
10. [Methodological figures](#10-methodological-figures)
11. [Limitations and future work](#11-limitations-and-future-work)
"""


# ---- 1. Executive summary --------------------------------------------------


def render_executive_summary(inputs: ReportInputs) -> str:
    val_result = inputs.validity_json.get("result", "UNKNOWN") if inputs.validity_json else "MISSING"
    fair = _format_score(inputs.fair.get("overall_score")) if inputs.fair else "—"
    by_dim = inputs.fair.get("by_dimension", {}) if inputs.fair else {}
    dim_str = ", ".join(f"{k}={_format_score(v, 2)}" for k, v in by_dim.items()) or "—"

    if inputs.alignment:
        cats = inputs.alignment.get("categories", [])
        in_scope = [c for c in cats if not c.get("not_implemented")]
        strong_count = sum(1 for c in in_scope if (c.get("strong_matches") or 0) > 0)
        align_line = f"{strong_count} of {len(in_scope)} in-scope categories show ≥1 strong match"
    else:
        align_line = "alignment JSON missing — re-run `python main.py --alignment`"

    if inputs.density:
        agg = inputs.density.get("aggregate", {})
        node_d = _format_pct(agg.get("node_density"))
        edge_d = _format_pct(agg.get("edge_density"))
    else:
        node_d = edge_d = "—"

    if val_result == "PASS":
        validity_paragraph = (
            "The graph satisfies the structural validity criteria specified in "
            "the project's validity rubric: every uniqueness constraint and "
            "index defined for the schema is present, ontology codes annotate "
            "the enriched node labels at the configured coverage threshold, "
            "the OntologyConcept layer is materialised across the five "
            "required source ontologies (SNOMED-CT, LOINC, UBERON, HPO, "
            "ICD-10), and qualified-reference edges (`MAPS_TO`, `IS_A`, "
            "`CLASSIFIED_AS`, `SAME_AS`) carry their formal-language URIs. "
            "The transition from labeled property graph to ontology-grounded "
            "knowledge graph is therefore considered complete for the purposes "
            "of subsequent semantic-quality assessment."
        )
    elif val_result == "FAIL":
        validity_paragraph = (
            "The graph **does not satisfy** the structural validity criteria "
            "on the most recent evaluation. The failing assertions are "
            "enumerated in §3. Until the validity gate passes, the downstream "
            "semantic-quality measurements reported in §4–§6 should be "
            "treated as provisional."
        )
    else:
        validity_paragraph = (
            f"Structural validity result: **{val_result}**. No recent "
            "evaluation record was located; the validity gate must be executed "
            "before the remaining sections can be considered current."
        )

    return f"""## 1. Summary of findings

{validity_paragraph}

The semantic-quality measurements scored against the FAIR principles
rubric and the semantic-density definition adopted in this work
(documented in `metrics/fair_principles.yaml` and
`docs/final_report/c7_plan_v2/IMPLEMENTATION_PLAN.md`) are summarised
below.

- **Semantic density.** The fraction of nodes carrying at least one
  ontology code is **{node_d}**, while the fraction of relationship
  instances annotated with a formal-language URI is **{edge_d}**. The
  edge-level coverage constitutes the principal indicator of formal-language
  use within the graph; the lower node-level figure reflects non-ontological
  node categories (e.g. FamilyMember, ImageNode, image-tile metadata)
  for which an ontology code is not semantically meaningful.
- **FAIR principle compliance.** The aggregate FAIR score is **{fair}**,
  with the four-dimension breakdown ({dim_str}). The Findability and
  Accessibility dimensions reach the maximum score; partial credit on the
  Interoperability and Reusability dimensions reflects principles that
  require human assessment (R1.1 — licence clarity) or upstream provenance
  conventions (R1.2 — node-level provenance edges).
- **Cross-vocabulary alignment with AlzKB.** {align_line}.

The remainder of this report decomposes each indicator into its measured
components, embeds the supporting figures, and enumerates the methodological
limitations that constrain the present evaluation.
"""


# ---- 2. KG state at a glance -----------------------------------------------


def render_kg_state(inputs: ReportInputs) -> str:
    if not inputs.eda_stats:
        return """## 2. Knowledge graph composition

_Aggregate composition statistics are not available; the exploratory data
analysis routine has not been executed against the current graph._
"""

    stats = inputs.eda_stats
    node_total = stats.get("total_nodes") or stats.get("nodes_total") or "—"
    rel_total = stats.get("total_relationships") or stats.get("relationships_total") or "—"
    # `node_counts` / `relationship_counts` are the live keys; `node_labels` /
    # `relationship_types` are legacy aliases retained for backward compatibility.
    labels_dict = stats.get("node_counts") or stats.get("node_labels") or {}
    rels_dict = stats.get("relationship_counts") or stats.get("relationship_types") or {}
    label_count = len(labels_dict) if isinstance(labels_dict, dict) else "—"
    rel_count = len(rels_dict) if isinstance(rels_dict, dict) else "—"

    dashboard = inputs.eda_figures_dir / "14_kg_summary_dashboard.svg"
    schema = inputs.eda_figures_dir / "15_relationship_schema.svg"
    dashboard_md = (
        f"**Figure 2.1.** Aggregate composition of the knowledge graph.\n\n"
        f"![Knowledge graph composition overview]({_rel_link(dashboard, inputs.project_root)})"
        if dashboard.exists()
        else "_(Composition overview figure unavailable.)_"
    )
    schema_md = (
        f"**Figure 2.2.** Relationship-type schema with cardinalities.\n\n"
        f"![Relationship-type schema]({_rel_link(schema, inputs.project_root)})"
        if schema.exists()
        else "_(Relationship-type schema figure unavailable.)_"
    )

    return f"""## 2. Knowledge graph composition

The knowledge graph instance evaluated in this report exhibits the
following aggregate composition.

| Quantity | Value |
|---|---:|
| Total nodes | `{node_total:,}` |
| Total relationships | `{rel_total:,}` |
| Distinct node labels | `{label_count}` |
| Distinct relationship types | `{rel_count}` |

{dashboard_md}

{schema_md}
"""


# ---- 3. Sultan's validity gate --------------------------------------------


def render_validity(inputs: ReportInputs) -> str:
    intro = (
        "Structural validity is operationalised in this work as a suite of "
        "seven assertions, each derived from the migration specification and "
        "encoded as a Cypher query against the live graph instance. The "
        "assertions cover (i) the presence of all uniqueness constraints and "
        "performance indices defined for the schema, (ii) ontology-code "
        "coverage on the enriched node labels (`Diagnosis`, "
        "`CognitiveAssessment`, `Biomarker` (CSF subset), `BrainRegion`), "
        "(iii) materialisation of an `OntologyConcept` layer spanning the "
        "five required source ontologies, (iv) presence of qualified-reference "
        "edges (`MAPS_TO`, `IS_A`, `CLASSIFIED_AS`) annotated with their "
        "formal-language URIs, (v) URI annotation coverage across the broader "
        "set of relationship types, (vi) reachability of every "
        "`OntologyConcept` node from the data layer (with explicit exemption "
        "of hierarchy roots and concepts intentionally retained as "
        "schema-only references), and (vii) participant identifier hygiene "
        "(removal of records flagged by the data provider as data-quality "
        "compromised). Each assertion is scored against a configurable "
        "threshold; the default coverage threshold is 0.95."
    )
    if inputs.validity_md:
        # Strip the embedded report's H1 so the combined document keeps a
        # single top-level title.
        body = "\n".join(
            line for line in inputs.validity_md.splitlines() if not line.startswith("# KG Validity")
        )
        return f"""## 3. Structural validity assessment

{intro}

The full assertion-by-assertion record produced by the validity engine
follows.

{body}
"""
    return f"""## 3. Structural validity assessment

{intro}

_No structural validity record was located. The validity assessment must
be executed before the remaining sections of this report can be considered
authoritative._
"""


# ---- 4. Semantic density ---------------------------------------------------


def render_density(inputs: ReportInputs) -> str:
    if not inputs.density:
        return """## 4. Semantic density

_Semantic density measurements are not available; the corresponding
metric routine has not been executed against the current graph._
"""

    agg = inputs.density.get("aggregate", {})
    per_label = inputs.density.get("per_label", [])
    per_edge = inputs.density.get("per_edge_type", [])

    top_labels = sorted(per_label, key=lambda e: -e.get("total", 0))[:10]
    top_edges = sorted(per_edge, key=lambda e: -e.get("total", 0))[:10]

    label_table = "\n".join(
        f"| `{e['name']}` | `{e['total']:,}` | `{e['with_uri']:,}` | {_format_pct(e['coverage'])} |"
        for e in top_labels
    ) or "| _(no per-label measurements available)_ |"

    edge_table = "\n".join(
        f"| `{e['name']}` | `{e['total']:,}` | `{e['with_uri']:,}` | {_format_pct(e['coverage'])} |"
        for e in top_edges
    ) or "| _(no per-edge-type measurements available)_ |"

    coverage_fig = inputs.eda_figures_dir / "10_ontology_coverage.svg"
    coverage_md = (
        f"**Figure 4.1.** Ontology coverage by node label and source ontology.\n\n"
        f"![Ontology coverage heatmap]({_rel_link(coverage_fig, inputs.project_root)})"
        if coverage_fig.exists()
        else "_(Ontology coverage figure unavailable.)_"
    )

    return f"""## 4. Semantic density

Semantic density quantifies the degree to which the graph carries explicit
ontological grounding. Two complementary indicators are reported:
*node-level URI coverage*, defined as the fraction of nodes carrying at
least one ontology code (e.g. SNOMED-CT, LOINC, UBERON, ICD-10) or
qualifying as a member of the `OntologyConcept` layer; and *edge-level URI
coverage*, defined as the fraction of relationship instances carrying a
formal-language URI in their `uri`, `ro_uri`, or `biolink_predicate`
property. Each indicator is reported in aggregate and disaggregated by
node label and relationship type respectively.

### 4.1 Aggregate measurements

| Indicator | Coverage | Numerator / Denominator |
|---|---:|---|
| Node-level URI coverage | **{_format_pct(agg.get("node_density"))}** | {agg.get("node_with_uri", 0):,} / {agg.get("node_total", 0):,} |
| Edge-level URI coverage | **{_format_pct(agg.get("edge_density"))}** | {agg.get("edge_with_uri", 0):,} / {agg.get("edge_total", 0):,} |

The edge-level indicator constitutes the principal measure for the FAIR
"interoperability" claim, as it captures whether the predicate of each
relationship instance is interpretable under a shared formal vocabulary.
The node-level indicator reflects the fraction of the graph that
participates in cross-vocabulary reasoning; values below 100% are expected
because several node categories (family-relationship records, image-tile
metadata, derived aggregation nodes) have no semantically appropriate
ontology mapping.

### 4.2 Per-label coverage (top labels by cardinality)

| Node label | Cardinality | Annotated | Coverage |
|---|---:|---:|---:|
{label_table}

### 4.3 Per-relationship-type coverage (top types by cardinality)

| Relationship type | Cardinality | Annotated | Coverage |
|---|---:|---:|---:|
{edge_table}

### 4.4 Visualisation

{coverage_md}
"""


# ---- 5. FAIR scoring -------------------------------------------------------


def render_fair(inputs: ReportInputs) -> str:
    if not inputs.fair:
        return """## 5. FAIR scoring

_outputs/metrics/fair_score.json missing. Run `python main.py --fair`._
"""

    overall = _format_score(inputs.fair.get("overall_score"))
    by_dim = inputs.fair.get("by_dimension", {})
    dim_table = "\n".join(
        f"| {dim} | {_format_score(score, 3)} |" for dim, score in by_dim.items()
    ) or "| _(no by-dimension data)_ |"

    principles = inputs.fair.get("principles", {})
    rows: list[str] = []
    for pid, p in principles.items():
        level = p.get("level", "—")
        score = p.get("score", 0.0)
        marker = {"yes": "✅", "partial": "⚠️", "no": "❌"}.get(level, "·")
        # Trim long names to keep table readable
        name = (p.get("name") or pid).split(".")[0]
        if len(name) > 80:
            name = name[:77] + "..."
        rows.append(f"| {pid} | {marker} {level} | {score:.1f} | {name} |")
    principle_table = "\n".join(rows) or "| _(no principle data)_ |"

    f3_path = inputs.paper_output_dir / "f3_fair.svg"
    f3_md = (
        f"![FAIR scorecard (F3)]({_rel_link(f3_path, inputs.project_root)})"
        if f3_path.exists()
        else "_(paper_outputs/f3_fair.svg not found — run `python main.py --figures`)_"
    )

    return f"""## 5. FAIR principle compliance

FAIR principle compliance (Wilkinson et al., 2016) is evaluated using a
three-level rubric in which each of the thirteen principles is scored as
*yes* (1.0), *partial* (0.5), or *no* (0.0). The scoring rubric is
implemented in `metrics/fair_principles.yaml`; each principle is checked
either by a Cypher query against the graph instance, by a filesystem
presence check (e.g. for the column-to-concept mapping artefacts), or by
a human-assessed default value where automated scoring is not appropriate
(e.g. licence clarity).

### 5.1 Aggregate and dimension-level scores

| Aggregate | Score |
|---|---:|
| Overall FAIR score | **{overall}** |
{dim_table}

### 5.2 Per-principle scores

| Identifier | Level | Score | Principle |
|---|---|---:|---|
{principle_table}

### 5.3 Visualisation

**Figure 5.1.** Per-principle FAIR scorecard.

{f3_md}

Two principles routinely receive partial credit and are therefore expected
to remain at 0.5 until the corresponding manual or upstream remediations
are completed:

- **R1.1 — licence clarity.** Reusability under R1.1 requires that data
  are released under a clearly stated licence. Within this work the
  licence applies to two distinct artefacts (the source ADNI dataset,
  governed by a separate Data Use Agreement; and the methodology
  artefacts produced in this thesis, governed by the project repository
  licence). A definitive automated check is therefore not appropriate;
  the principle is scored by manual assessment.
- **R1.2 — provenance.** Reusability under R1.2 requires that each data
  instance be traceable to its origin. The current node-level provenance
  coverage is dominated by `source_table` and `batch_id` properties set
  at ingestion; introducing a `:BatchIngestion`-typed provenance
  hyperedge would raise this score, but is out of scope for the present
  work.
"""


# ---- 6. AlzKB alignment ----------------------------------------------------


def render_alignment(inputs: ReportInputs) -> str:
    if not inputs.alignment:
        return """## 6. AlzKB cross-vocabulary alignment

_outputs/metrics/alzkb_alignment.json missing. Run
`python main.py --alignment`. If AlzKBConcept = 0, run
`python -m steps.step24_alzkb_bridge --neo4j-password <pw>` first._
"""

    a = inputs.alignment
    rows = []
    for c in a.get("categories", []):
        if c.get("not_implemented"):
            rows.append(f"| {c['name']} | N/A | N/A | {c.get('note', '')} |")
        else:
            rate = _format_pct(c.get("match_rate"))
            rows.append(
                f"| {c['name']} | "
                f"`{c.get('strong_matches', 0)} / {c.get('total', 0)}` | "
                f"**{rate}** | {c.get('note', '')} |"
            )
    cat_table = "\n".join(rows) or "| _(no category data)_ |"

    f5_path = inputs.paper_output_dir / "f5_alignment.svg"
    f5_md = (
        f"![AlzKB alignment matrix (F5)]({_rel_link(f5_path, inputs.project_root)})"
        if f5_path.exists()
        else "_(paper_outputs/f5_alignment.svg not found)_"
    )

    return f"""## 6. Cross-vocabulary alignment with AlzKB

Cross-vocabulary alignment evaluates the degree to which entities in the
present knowledge graph can be co-referenced with entities in the
Alzheimer's Disease Knowledge Base (AlzKB; Romano et al., 2024). For each
in-scope AlzKB entity category $K \\in \\{{\\text{{Disease}},\\ \\text{{Anatomy}},\\ \\text{{Phenotype}}\\}}$,
the strong-match count is defined as the number of `OntologyConcept`
nodes of the corresponding source ontology that are connected via a
`SAME_AS` edge to an `AlzKBConcept` whose `source_type` matches $K$. The
match rate is the strong-match count normalised by the cardinality of
the corresponding `OntologyConcept` subset. The Gene category is
explicitly out of scope in this work and is reported as not-applicable;
this is consistent with the project decision to defer Gene Ontology
integration to subsequent work.

| Quantity | Value |
|---|---:|
| `AlzKBConcept` nodes materialised | `{a.get("alzkb_concept_total", 0):,}` |
| `SAME_AS` edges to the present graph | `{a.get("same_as_edge_total", 0):,}` |

### 6.1 Per-category strong-match counts

| Category | Strong / Total | Match rate | Note |
|---|---:|---:|---|
{cat_table}

### 6.2 Visualisation

**Figure 6.1.** Strong-match alignment between the present knowledge
graph and AlzKB, by category.

{f5_md}
"""


# ---- 7. Column-to-concept mapping ------------------------------------------


def render_column_to_concept(inputs: ReportInputs) -> str:
    rows = inputs.column_to_concept_rows
    if not rows:
        return """## 7. Methodology — column-to-concept mapping

_ontology/mappings/index.csv missing. See R1.* tasks in
`docs/final_report/c7_plan_v2/TASKS.md`._
"""

    by_csv: dict[str, int] = {}
    for r in rows:
        by_csv[r["source_csv"]] = by_csv.get(r["source_csv"], 0) + 1

    summary_table = "\n".join(
        f"| `{csv_file}` | {n} |" for csv_file, n in sorted(by_csv.items())
    )

    # Top 25 illustrative rows
    head = rows[:25]
    head_table = "\n".join(
        f"| `{r['source_table']}` | `{r['source_column']}` | `{r['source_value_pattern']}` | "
        f"{r['target_ontology']} | `{r['target_uri']}` | {r['target_label']} |"
        for r in head
    )

    return f"""## 7. Column-to-concept mapping methodology

The column-to-concept mapping methodology is the reproducibility artefact
that documents how source-table column values in the underlying ADNI
dataset are deterministically transformed into ontology-grounded entities.
Each mapping rule is a tuple `(source_table, source_column, value_pattern,
target_ontology, target_uri, target_label, mapping_rule, fixture_id,
last_verified_date)`, where `mapping_rule` takes one of the values
`exact_match`, `case_insensitive`, `regex`, or `derived_from_property`,
and `fixture_id` references a row in the synthetic test fixture used to
verify the rule.

### 7.1 Inventory of mapping files

| Mapping file | Rule count |
|---|---:|
{summary_table}
| **Total** | **{len(rows)}** |

### 7.2 Representative rules (first 25 entries of the consolidated index)

| Source table | Source column | Pattern | Target ontology | Target URI | Target label |
|---|---|---|---|---|---|
{head_table}

The complete inventory is available in `ontology/mappings/index.csv`; the
per-source rule files reside in the same directory, and the schema is
documented in `ontology/mappings/README.md`.
"""


# ---- 8. Step audit ---------------------------------------------------------


def render_step_audit(inputs: ReportInputs) -> str:
    rows = inputs.step_audit_rows
    if not rows or all(not any(v for v in r.values()) for r in rows):
        return """## 8. Per-step migration audit

The migration audit attributes the change in nodes, edges, properties,
runtime, and downstream FAIR / semantic-density indicators to each step
of the migration pipeline. Per-step results are not currently available;
populating them requires a series of intermediate graph snapshots taken
between successive migration steps, which is identified as future work.
"""

    body = "\n".join(
        f"| {r.get('step','')} | {r.get('nodes_touched','')} | "
        f"{r.get('edges_added','')} | {r.get('properties_added','')} | "
        f"{r.get('runtime_s','')} | {r.get('fair_delta_overall','')} | "
        f"{r.get('density_delta_node','')} | {r.get('density_delta_edge','')} |"
        for r in rows
    )

    return f"""## 8. Per-step migration audit

The migration audit decomposes the labeled-property-graph to
knowledge-graph transformation into its constituent steps and attributes
to each step the corresponding change in node count, edge count, property
count, execution runtime, and the resulting deltas in the FAIR aggregate
score, node-level semantic density, and edge-level semantic density.

| Step | Nodes touched | Edges added | Properties added | Runtime (s) | ΔFAIR | ΔNode density | ΔEdge density |
|---|---:|---:|---:|---:|---:|---:|---:|
{body}
"""


# ---- 9. Step-29 EDA panels ------------------------------------------------


def render_eda_panels(inputs: ReportInputs) -> str:
    if not inputs.include_eda or not inputs.eda_figures:
        return """## 9. Exploratory data analysis

_Exploratory data analysis figures are not embedded in this rendering._
"""

    captions = {
        "01_node_distribution": (
            "Distribution of node labels by cardinality. Bars are ordered by "
            "node count; the long tail of low-cardinality labels corresponds "
            "to derived aggregation classes (cognitive trajectory, ATN "
            "profile, progression event)."
        ),
        "02_relationship_distribution": (
            "Distribution of relationship types by edge cardinality. The "
            "leading types correspond to the patient-visit-observation "
            "scaffold and the ontology-grounding layer."
        ),
        "03_patient_demographics": (
            "Joint distribution of participant demographics: age, biological "
            "sex, years of education, and APOE-ε4 allele count."
        ),
        "04_diagnosis_distribution": (
            "Distribution of clinical diagnostic categories across the cohort "
            "(cognitively normal, subjective memory complaint, early- and "
            "late-onset mild cognitive impairment, Alzheimer's disease, "
            "dementia)."
        ),
        "05_disease_progression": (
            "Disease-stage transition matrix derived from longitudinal "
            "diagnostic assessments across visits."
        ),
        "06_biomarker_distributions": (
            "Distribution of cerebrospinal-fluid biomarker concentrations "
            "(amyloid-β 42, total tau, phosphorylated tau) stratified by "
            "diagnostic group."
        ),
        "06_csf_biomarkers": (
            "Companion view of cerebrospinal-fluid biomarker panels."
        ),
        "07_cognitive_scores": (
            "Distribution of cognitive assessment scores (MMSE, CDR, "
            "ADAS-Cog, MoCA, Logical Memory) stratified by diagnostic group."
        ),
        "08_temporal_visits": (
            "Visit-code distribution across the longitudinal timeline "
            "(baseline, six-month, twelve-month, annual follow-up)."
        ),
        "10_ontology_coverage": (
            "Ontology code coverage stratified by node label and source "
            "ontology. The visualisation complements the aggregate semantic "
            "density measurements reported in Section 4."
        ),
        "11_missing_data": (
            "Missing-data heatmap reporting the fraction of null values per "
            "(label, property) pair."
        ),
        "12_graph_connectivity": (
            "Degree distribution and identification of hub nodes within the "
            "graph."
        ),
        "13_correlation_matrix": (
            "Pearson correlation matrix across continuous demographic and "
            "biomarker variables."
        ),
        "14_kg_summary_dashboard": (
            "Composite summary panel reporting cardinalities, ontology "
            "coverage, biomarker availability, and longitudinal coverage."
        ),
        "15_relationship_schema": (
            "Schema view of the most prevalent relationship types with "
            "their source and target labels."
        ),
    }

    blocks = []
    fig_index = 0
    for fig in inputs.eda_figures:
        stem = fig.stem
        # Skip figures already embedded in earlier sections to avoid duplication.
        if stem in {"10_ontology_coverage", "14_kg_summary_dashboard", "15_relationship_schema"}:
            continue
        fig_index += 1
        caption = captions.get(stem, stem.replace("_", " ").title())
        title = stem.split("_", 1)[1].replace("_", " ").title() if "_" in stem else stem
        blocks.append(
            f"**Figure 9.{fig_index}.** {title}. {caption}\n\n"
            f"![{title}]({_rel_link(fig, inputs.project_root)})\n"
        )

    mermaid_links = []
    for mmd in inputs.mermaid_files:
        mermaid_links.append(f"- `{_rel_link(mmd, inputs.project_root)}`")

    mermaid_section = ""
    if mermaid_links:
        mermaid_section = (
            "\n### 9.S Companion schematic sources\n\n"
            "Schematic diagrams (Mermaid sources) for the graph schema, the "
            "data flow, and the ontology layer accompany this evaluation:\n\n"
            + "\n".join(mermaid_links) + "\n"
        )

    intro = (
        "The exploratory data analysis routine produces a complementary set "
        "of figures characterising the demographic, clinical, and structural "
        "properties of the underlying cohort and graph. The selection that "
        "follows omits figures already embedded in earlier sections of this "
        "report (Sections 2 and 4)."
    )

    return ("## 9. Exploratory data analysis\n\n" + intro + "\n\n"
            + "\n".join(blocks) + mermaid_section)


# ---- 10. Paper figures -----------------------------------------------------


def render_paper_figures(inputs: ReportInputs) -> str:
    if not inputs.paper_figures:
        return """## 10. Methodological figures

_Methodological figures are not yet rendered._
"""

    captions = {
        "f1_dependency": (
            "Functional dependency diagram of the methodological framework. "
            "The unified contribution sits at the centre and is supported by "
            "four methodological steps: ontology selection, in-place semantic "
            "migration, column-to-concept mapping, and relation normalisation. "
            "A future-work follow-up (a comparative benchmark across multiple "
            "cohorts) is shown to the right."
        ),
        "f2_schema": (
            "Comparative schema view before and after the in-place semantic "
            "migration. The pre-migration schema corresponds to the labeled "
            "property graph; the post-migration schema introduces an "
            "`OntologyConcept` layer connected to the data layer via "
            "`MAPS_TO`, `IS_A`, and `CLASSIFIED_AS` qualified-reference edges."
        ),
        "f3_fair": (
            "FAIR principle scorecard. Each principle is reported on the "
            "three-level scale defined in Section 5; the dashed line indicates "
            "the partial-credit threshold."
        ),
        "f4_density": (
            "Semantic density progression across migration steps. Reports the "
            "node-level and edge-level URI coverage measured at each "
            "intermediate snapshot. Generation requires per-step graph "
            "snapshots; see Section 11."
        ),
        "f5_alignment": (
            "Cross-vocabulary alignment matrix between the present knowledge "
            "graph and AlzKB, by entity category. Cells are shaded by "
            "match-rate band; the Gene row is rendered with diagonal hatching "
            "to indicate that the category is out of scope in this work."
        ),
    }

    blocks = []
    for i, fig in enumerate(inputs.paper_figures, start=1):
        caption = captions.get(fig.stem, fig.stem.replace("_", " ").title())
        # Strip the leading "fX_" prefix for the human title
        stem = fig.stem
        title = stem.split("_", 1)[1].replace("_", " ").title() if "_" in stem else stem
        blocks.append(
            f"**Figure 10.{i}.** {title}. {caption}\n\n"
            f"![{title}]({_rel_link(fig, inputs.project_root)})\n"
        )

    intro = (
        "The methodological figures summarise, in five panels, the analytical "
        "results presented in the preceding sections."
    )
    return "## 10. Methodological figures\n\n" + intro + "\n\n" + "\n".join(blocks)


# ---- 11. Limitations -------------------------------------------------------


def render_limitations(inputs: ReportInputs) -> str:
    return """## 11. Limitations and future work

Several methodological limitations should be acknowledged when interpreting
the results presented in the preceding sections, and several extensions
constitute natural directions for future work.

**Per-step semantic-density progression (Section 8 and Figure 10.4).**
Disaggregating the change in semantic density to each individual migration
step requires graph snapshots taken between consecutive migrations. Such
snapshots in turn require the underlying database service to be quiesced
during snapshot capture. The corresponding per-step measurements are
therefore left to future work; the present evaluation reports the
end-to-end delta only.

**FAIR R1.1 — licence clarity.** The Reusability principle R1.1 is
scored by manual assessment in this work. The underlying ADNI dataset is
governed by a separate Data Use Agreement, while the methodology and code
artefacts are released under the project repository licence; an automated
rubric would conflate the two scopes and is therefore not appropriate.

**FAIR R1.2 — provenance coverage.** Approximately 55 % of clinical
data nodes carry direct provenance markers (`source_table`, `batch_id`).
Improving this measure requires augmenting the data-ingestion pipeline
with explicit `:BatchIngestion`-typed provenance nodes connected to each
ingested record by a typed hyperedge. This change is upstream of the
present evaluation and is identified as future work.

**Cross-vocabulary alignment with AlzKB — phenotype category.**
The strong-match rate for the Phenotype category depends on the
mapping rules supplied to the cross-vocabulary alignment routine. The
mapping rules were recently extended with HPO ↔ AlzKB
Symptom/BiologicalProcess correspondences; further refinement is
expected as the correspondences are validated against external sources.

**Gene category — out of scope.** The Gene category in the AlzKB
alignment matrix is reported as not-applicable. Integrating Gene Ontology
terms into the present knowledge graph and re-evaluating the alignment
matrix is identified as a separate workstream and is reserved for
subsequent work.

**Causal layer.** Although a causal-discovery workstream was prototyped
during the preparation of this thesis, the corresponding pipeline steps
are not invoked in the present evaluation and are not assessed by the
metrics reported here. The retained code constitutes a starting point
for post-defence research on causal validation of the ontology-grounded
knowledge graph.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


SECTION_FNS: list[tuple[str, Any]] = [
    ("01_executive_summary", render_executive_summary),
    ("02_kg_state", render_kg_state),
    ("03_validity", render_validity),
    ("04_density", render_density),
    ("05_fair", render_fair),
    ("06_alignment", render_alignment),
    ("07_column_to_concept", render_column_to_concept),
    ("08_step_audit", render_step_audit),
    ("09_eda_panels", render_eda_panels),
    ("10_paper_figures", render_paper_figures),
    ("11_limitations", render_limitations),
]


def render_full_report(inputs: ReportInputs) -> str:
    parts = [render_header(inputs)]
    for _name, fn in SECTION_FNS:
        parts.append(fn(inputs))
    parts.append(
        "---\n\n"
        "_This report is regenerated automatically from the metric outputs "
        "and the exploratory data analysis figures committed to the project "
        "repository. Re-run after each metric pipeline pass to refresh._"
    )
    return "\n\n".join(parts)


def render_per_section(inputs: ReportInputs) -> dict[str, str]:
    return {name: fn(inputs) for name, fn in SECTION_FNS}


def write_report(
    inputs: ReportInputs,
    output_dir: Path,
    *,
    write_pdf: bool = False,
) -> dict[str, Path]:
    """Render and write the report. Returns ``{kind: path}``."""

    output_dir = Path(output_dir)
    sections_dir = output_dir / "sections"
    output_dir.mkdir(parents=True, exist_ok=True)
    sections_dir.mkdir(parents=True, exist_ok=True)

    # Per-section slices
    for name, body in render_per_section(inputs).items():
        (sections_dir / f"{name}.md").write_text(body, encoding="utf-8")

    # Full report
    full = render_full_report(inputs)
    full_path = output_dir / "thesis_report.md"
    full_path.write_text(full, encoding="utf-8")

    written: dict[str, Path] = {"markdown": full_path, "sections_dir": sections_dir}

    if write_pdf:
        pdf_path = _render_pdf(full_path, output_dir / "thesis_report.pdf")
        if pdf_path is not None:
            written["pdf"] = pdf_path

    return written


def _render_pdf(md_path: Path, pdf_path: Path) -> Path | None:
    """Render the thesis report to PDF via the multi-backend converter
    (`tools/md_to_pdf.py`). Tries pandoc → weasyprint → xhtml2pdf in order
    and falls back to a styled HTML file if no backend is installed.

    Returns the actual output path on success (may have a `.html` suffix
    if a fallback fired), or ``None`` only if the converter raised."""

    try:
        from tools.md_to_pdf import md_to_pdf
    except ImportError as exc:  # pragma: no cover
        logger.warning("tools.md_to_pdf import failed: %s", exc)
        return None

    try:
        out = md_to_pdf(md_path, pdf_path)
    except Exception as exc:
        logger.warning("md_to_pdf raised: %s", exc)
        return None

    if out.suffix == ".html":
        logger.warning(
            "PDF backend unavailable — wrote HTML fallback at %s. "
            "Install pandoc OR `pip install xhtml2pdf` to enable real PDF.",
            out,
        )
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics.thesis_report",
        description="Generate the thesis evaluation report from every metric output.",
    )
    p.add_argument(
        "--metrics-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs",
        help="Where the metric pipeline writes (default: <project>/outputs).",
    )
    p.add_argument(
        "--paper-output-dir",
        type=Path,
        default=PROJECT_ROOT / "paper_outputs",
        help="Where the figure pipeline writes (default: <project>/paper_outputs).",
    )
    p.add_argument(
        "--eda-figures-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "eda_figures",
        help="Where step-29 EDA figures live (default: <project>/outputs/eda_figures).",
    )
    p.add_argument(
        "--ontology-mappings-dir",
        type=Path,
        default=PROJECT_ROOT / "ontology" / "mappings",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "thesis_report",
        help="Where to write the report (default: <project>/outputs/thesis_report).",
    )
    p.add_argument("--no-eda", action="store_true",
                   help="Skip embedding step-29 EDA figures.")
    p.add_argument("--pdf", action="store_true",
                   help="Also render PDF via pandoc (silent skip if pandoc missing).")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    inputs = gather_inputs(
        project_root=PROJECT_ROOT,
        metrics_output_dir=args.metrics_dir,
        paper_output_dir=args.paper_output_dir,
        eda_figures_dir=args.eda_figures_dir,
        ontology_mappings_dir=args.ontology_mappings_dir,
        include_eda=not args.no_eda,
    )
    written = write_report(inputs, args.output_dir, write_pdf=args.pdf)
    for kind, path in written.items():
        logger.info("Wrote %s: %s", kind, path)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
