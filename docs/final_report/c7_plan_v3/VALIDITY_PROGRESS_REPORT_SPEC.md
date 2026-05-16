# Validity Progress-Report Spec — Sultan's Deliverable (Phase 1)

> **Owner.** Oğuzhan Güngör (implementation), Dr. Sultan Nezihe Turhan (acceptance).
> **Position in pipeline.** Phase 1 of [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Builds on the existing seven-assertion validity gate.
> **Anchor task.** [TASKS.md §S1](TASKS.md).
> **Underlying spec.** [c7_plan_v2/VALIDITY_CHECK_SPEC.md](../c7_plan_v2/VALIDITY_CHECK_SPEC.md) — the 7-assertion Cypher + thresholds. v3 does **not** modify the assertions; it adds a presentation layer on top.

---

## 1. Why this spec exists

The existing `metrics/validity.py` already produces a JSON + a markdown report. The markdown is machine-flavored — it lists assertion IDs, raw counts, and threshold checks. That format is fine for engineering reviewers; it is unsuitable for Sultan's progress report.

Sultan's Turkish-language feedback on the prior progress report:

> *"Bu ilerleme raporuna metrikleri koymasan bile hiç olmazsa ontolojileri bitirip graphın KG haline dönüşmüş halini koymak lazım."*

Translation: "Even if you don't put metrics in this progress report, at the very least the ontologies must be finished and the KG-converted state of the graph must be in there."

So the goal is **not** to add metrics — those are out of scope per Sultan's instruction — but to **demonstrate that the LPG → KG transition is complete**. The seven-assertion gate already proves that. This spec turns that proof into a one-page progress-report insert.

---

## 2. Deliverable

### Primary file
**`outputs/validity_reports/kg_validity_progress_report.md`** — the canonical, latest version (overwritten on each run; the timestamped versions are kept as `kg_validity_progress_report_<ts>.md`).

### Derived PDF
**`outputs/validity_reports/kg_validity_progress_report.pdf`** — same content, rendered by `metrics/thesis_pdf.py`.

### Audience and size
- **Primary audience.** Dr. Sultan Nezihe Turhan (Co-Investigator).
- **Secondary audiences.** Asst. Prof. Özgün Pınarer (PI), Dr. Hajer Baazaoui (external collaborator).
- **Target length.** 1–2 printed pages. No more.

---

## 3. Content sections

Five sections, in order. Each marked with the header level it should render at.

### Section (a) — One-paragraph plain-English summary (H2)

Format: a single paragraph, 3–5 sentences. Mentions the four facts Sultan asked to see:

1. The graph is now in KG state (no longer plain LPG).
2. All ontology integrations are complete (Steps 17–34).
3. Seven validity assertions all PASS.
4. The transition is reproducible (`metrics/validity.py` re-runs on demand; snapshot ID cited).

**Template (variables in `{...}`):**

```markdown
## Özet / Summary

The ADNI knowledge graph has completed the labeled-property-graph (LPG) → knowledge-graph (KG) transition.
The graph contains **{N_nodes}** nodes and **{N_edges}** edges across {N_node_types} labels and {N_rel_types}
relationship types. Ontology grounding spans **{N_sources}** vocabularies (SNOMED-CT, LOINC, UBERON, ICD-10, HPO{', MONDO, DOID' if post_phase_3 else ''})
via **{N_concepts}** OntologyConcept nodes. All **seven** structural-validity assertions PASS at the agreed
0.95 threshold. The full state is captured by the canonical snapshot `{snapshot_id}` taken on {snapshot_ts}.
```

### Section (a-tr) — Turkish preamble (H2, before Section (a))

A single sentence in Turkish — mirrors Sultan's request language so the artifact reads cleanly for her.

**Fixed content:**

```markdown
## Özet (Türkçe)

Bu rapor, ADNI bilgi grafının LPG'den KG'ye dönüşümünün tamamlandığını ve yedi
doğrulama testinin başarıyla geçildiğini belgeler.
```

### Section (b) — Per-assertion table (H2)

Format: a Markdown table, one row per assertion (A1–A7), three columns: **Assertion**, **Measured value**, **Threshold / PASS**.

**Example post-Phase-3:**

| Assertion | What it checks | Measured | Threshold | Result |
|---|---|---|---|---|
| A1 | Constraints + indexes complete | 12 / 15 | ≥ 12 / 15 | ✅ PASS |
| A2 | Ontology-code coverage on data labels | min 0.962 (Biomarker), max 0.997 (Diagnosis) | ≥ 0.95 each | ✅ PASS |
| A3 | OntologyConcept layer covers ≥ 5 sources | 7 sources present | ≥ 5 | ✅ PASS |
| A4 | MAPS_TO / IS_A / CLASSIFIED_AS edges with `uri` | MAPS_TO 1.000, IS_A 1.000, CLASSIFIED_AS 1.000 | ≥ 0.95 each | ✅ PASS |
| A5 | Relationship-type URI coverage | 0.97 of types annotated | ≥ 0.95 | ✅ PASS |
| A6 | No orphan OntologyConcept nodes | 1.000 reachable | ≥ 0.95 | ✅ PASS |
| A7 | PTID hygiene (no `381_S_*`) | 0 violations | 0 | ✅ PASS |

Values are pulled from `outputs/validity_reports/kg_validity_<ts>.json` produced by `metrics/validity.py`.

### Section (c) — Ontology completeness summary (H2)

Format: a Markdown table, one row per (node label, ontology) pair the migration steps explicitly target.

**Example:**

| Node label | Target ontology | Coverage | Notes |
|---|---|---|---|
| `:Diagnosis` | SNOMED-CT | 99.7 % | Per Step 18 |
| `:CognitiveAssessment` | LOINC | 98.4 % | Per Step 18 |
| `:Biomarker` (CSF subset) | LOINC | 96.2 % | Per Step 18 (CSF only; broader pool 78.84 %) |
| `:BrainRegion` | UBERON | 99.1 % | Per Step 18 |
| `:Patient` | Biolink Model | 100 % | Per Step 33 (post-Phase-3) |
| `:Comorbidity` | SNOMED-CT (category) | 100 % | Per Step 32 (post-Phase-3, new label) |

The pre-Phase-3 version of this table has only the first four rows; post-Phase-3 adds Patient (Biolink) and Comorbidity. Other Biolink-categorized labels can be appended.

### Section (d) — Before / after counts (H2)

Format: a small table with three columns: **Item**, **Pre-Steps-17–20 (baseline)**, **Post-Steps-17–34 (current)**.

**Example post-Phase-3:**

| Item | Baseline | Current |
|---|---|---|
| Total nodes | 407 K | 443 K + comorbidity nodes |
| Total edges | 1.16 M | 1.51 M + HAS_COMORBIDITY |
| Distinct ontology sources | 0 (LPG) | **7** (SNOMED-CT, LOINC, UBERON, HPO, ICD-10, MONDO, DOID) |
| OntologyConcept nodes | 0 | ~55 + Comorbidity SNOMED categories |
| Relationship types with URI | 0 % | ≥ 95 % |
| FAIR aggregate | — (not measured) | 0.92 → ~0.96 (post-Biolink) |

If the baseline snapshot is not yet captured (Phase 2 not complete), the "Baseline" column is marked **"baseline pending"** with a footnote linking to P2.4 in [TASKS.md](TASKS.md). The post column is always populated from the latest canonical snapshot.

### Section (e) — KG schema diagram (H2)

Format: a single inline image link. The diagram itself is generated by `figures/_mermaid.py` from a Mermaid spec; output: `outputs/validity_reports/kg_schema_<ts>.svg`.

The diagram shows the 17 node types + the `:OntologyConcept` layer + the `:AlzKBConcept` external bridge. Edges shown as labeled arrows.

```markdown
## KG Schema

![KG Schema](kg_schema_2026-05-16T14-30-00.svg)
```

If Mermaid rendering fails (e.g. no `mmdc` on the runner), the report falls back to a Mermaid code block — still readable in a Markdown viewer that renders Mermaid.

### Section (f) — Footer (H3)

Format: small italic line. Cites the timestamp, the validity rubric version, the canonical snapshot ID.

```markdown
---

*Generated by `metrics/validity.py::render_progress_report()` on 2026-05-16 14:30:00 +03:00.
Rubric: `metrics/validity_rubric.yaml` v1.
Snapshot: `metrics/output/canonical_snapshot.json` (sha1 prefix `a3b9c2…`).
Reproduce: `python -m metrics --all`.*
```

---

## 4. Implementation hooks

### Code change
Add this function signature to `metrics/validity.py`:

```python
def render_progress_report(
    json_path: Path,
    canonical_snapshot_path: Path | None = None,
    schema_svg_path: Path | None = None,
    *,
    output_path: Path = Path("outputs/validity_reports/kg_validity_progress_report.md"),
    rubric_version: int = 1,
    locale_preamble: bool = True,
) -> Path:
    """Render the Sultan-facing progress report from a validity JSON.

    See docs/final_report/c7_plan_v3/VALIDITY_PROGRESS_REPORT_SPEC.md for the section layout.
    """
```

Behaviour:
1. Read the JSON at `json_path`.
2. If `canonical_snapshot_path` is provided, read totals (nodes, edges, concept count, source distinct count). Otherwise mark as "baseline pending" + log a warning.
3. If `schema_svg_path` is provided, embed the relative SVG link in Section (e). Otherwise embed a Mermaid code block fallback.
4. Render sections (a-tr) → (a) → (b) → (c) → (d) → (e) → footer in that order.
5. Write the markdown to `output_path`.
6. Return the `output_path`.

### Caller change
`metrics/runner.py` should call `render_progress_report()` after `validity.run_validity()` succeeds:

```python
from metrics.validity import run_validity, render_progress_report
# ...
validity_json = run_validity(connector, rubric_path)
# ...
render_progress_report(
    validity_json,
    canonical_snapshot_path=output_dir / "canonical_snapshot.json",
    schema_svg_path=mermaid_render(...),
)
```

### PDF rendering
`metrics/thesis_pdf.py` already converts MD → PDF using reportlab + svglib. Add a thin wrapper:

```python
def render_progress_report_pdf(md_path: Path) -> Path:
    """Render the Sultan progress-report MD to PDF using the existing thesis PDF pipeline."""
    return convert_markdown_to_pdf(md_path, output_path=md_path.with_suffix(".pdf"))
```

---

## 5. Acceptance criteria (S1.2 + S1.5)

The generated MD must:
- ✅ Contain all sections (a-tr), (a), (b), (c), (d), (e), (f) in the order above.
- ✅ Render cleanly in GitHub Markdown, in Obsidian, and in a basic Markdown PDF converter (no exotic syntax).
- ✅ Embed the validity timestamp in both ISO-8601 (footer) and a human-friendly Turkish date format (section (a-tr) if Sultan asks).
- ✅ Compile via `metrics/thesis_pdf.py` to a 1–2 page PDF.
- ✅ Be reviewed and accepted by Sultan in writing in `meeting_notes.md`.
- ✅ Be regenerated automatically when `python -m metrics --all` runs end-to-end.

The unit test `tests/test_validity.py::test_render_progress_report` (S1.5):
- ✅ Runs against the synthetic mini-KG fixture.
- ✅ Asserts presence of each section header.
- ✅ Asserts the Turkish preamble paragraph is present verbatim.
- ✅ Asserts the result line says "PASS" when all assertions PASS.
- ✅ Asserts a FAIL run renders a header line saying "FAIL" and lists the failed assertion IDs.

---

## 6. Open question for Sultan (Q.6 — to be confirmed before S1.2 lands)

1. Are A2 thresholds 0.95 across the board, or label-specific (e.g., 0.99 for Diagnosis)? Default 0.95.
2. Should A3 enforce the per-source count tolerance bands (e.g., HPO 25–35), or only the presence of the seven source names? Default: presence only after Phase 3.
3. Is A5's `type_coverage_threshold` of 0.95 acceptable, or 1.00 minus an explicit allowlist? Default 0.95.
4. Should the MD include offending node IDs on FAIL (helpful for debugging, but larger file)? Default: summary counts only.
5. PDF — letter, A4, or both? Default A4 (Turkish standard).
