# MAKO Evaluation Review — Session History

**Date:** 2026-05-16
**Author:** Oğuzhan Güngör
**Reviewer role:** Deep evaluation of the MAKO knowledge-graph evaluation report against meeting decisions and project data
**Status:** Review complete — remediation items open

---

## 1. Request

The session brief asked for a deep evaluation of `MAKO_evaluation.pdf` against three questions:

1. Is the report correct?
2. Does it support the revised contribution structure and Hajer's additions?
3. Is the underlying data correct?

The brief supplied the comprehensive project instructions (ADNI Knowledge Graph project,
supervisors Dr. Sultan Turhan & Asst. Prof. Özgün Pinarer, CY Cergy collaborators),
the three-phase research plan, repository architecture, headers.json schema reference,
ontology mapping reference, and the full paper-repository reading guide. It also included
the **meeting notes** that redefine the contribution set.

### Meeting notes (decision summary used as the evaluation rubric)

- **C7** is the full / main contribution.
- **C1** — FAIR and semantic density are the methods (replacing OntoQA emphasis).
  Use the pre-enrichment CauAD graph as the baseline; report before/after per step.
  Caveat: the "before" already carries some ontology codes on a few node types, so it
  is not a true zero.
- **C3** — reproducibility mapping to show originality; show the mapping in detail.
  Rename to *column-to-concept mapping*.
- **C4** — removed (Gene Ontology, no implementation).
- **C5** — a step in the process, not a contribution. Check the literature on whether
  normalization counts as a contribution.
- **C7** — finish first, submit the paper.
- **C6** — after C7; future work, post-June.
- Finish the master's thesis with metrics; change the acronym; causality is the next step.
- Contribution list to report: **C1, C2, C3 (renamed), C7**; C2–C3 can be called steps.
- Redraw contribution diagram; detail each section, experimental setup, methodologies,
  metrics; describe how experimental results will be presented.
- **Title:** remove "Enrichment"; add "Evaluation" or "Metrics".

---

## 2. Inputs Reviewed

### Uploaded documents

| File | Role in review |
|---|---|
| `MAKO_evaluation.pdf` | Primary artefact under evaluation (27 pp.) — structural validity, semantic density, FAIR, AlzKB alignment, column-to-concept mapping, EDA, discussion |
| `Contribution_Table_updated_HB.pdf` | Contribution table with Hajer's additions; OntoQA baseline proposal; ontology/tool assessment; functional-dependency figure |

### Project files cross-checked

`PHASE1_SCHEMA_MIGRATION.md`, `IMPLEMENTATION_PLAN.md`, `TASKS.md`, `PERSONA.md`,
`config.yaml`, `headers.json`, `step13_graph_eda.py`, `IEEE_Big_Data_2025_Oguzhan.pdf`,
and the paper-repository PDFs (Jack 2010, Bilgel 2022, Shen 2020, Romano 2024 AlzKB,
Spassov 2023, Gomez 2025, etc.).

---

## 3. Findings

### 3.1 Alignment with the revised contribution structure

| Contribution | Report support | Note |
|---|---|---|
| C1 (FAIR + semantic density) | Partial | Sections 4–5 deliver FAIR (0.923) and semantic density (node 31.0% / edge 99.6%). **No OntoQA measurements at all** — report and contribution table currently describe two different frameworks. |
| C2 (in-place migration) | Qualitative only | A1–A7 all PASS; before/after per-step delta (Hajer's request) **not delivered** — Section 8 explicitly defers it. |
| C3 (column-to-concept mapping) | Supported | Section 7 documents 100 rules across 5 mapping files; representative 15-row table present. Rename consistent. |
| C4 (Gene Ontology) | Correctly removed | Marked n/a in Sections 6, 11.2, 12. Consistent with removal decision. |
| C5 (relation normalisation) | Inconsistent | 99.6% edge coverage is the single largest claim and rests entirely on C5. If C5 is demoted to a step, the figure must be reattributed to C2. Literature supports Hajer: RO normalisation is a methodological step, not a standalone contribution. |
| C6 (comparative benchmark) | Correctly deferred | Sections 8, 11.4, 12 defer to future work. |
| C7 (AlzKB alignment) | Structurally supported, weak numbers | 2/17 Disease, 2/14 Anatomy, 1/5 Phenotype; 7 SAME_AS edges. Defence valid but thin for the headline contribution. |

### 3.2 Data validity — discrepancies found

**Reconciles cleanly:** Patients 2,638; Diagnosis 25,946; CognitiveAssessment 65,345;
MAPS_TO 100,770; CLASSIFIED_AS 25,946; BrainRegion 12; demographics N=2,638 (age 73,
education 16, APOE distribution).

**Does not reconcile — action required:**

1. **Visit count** — report 33,800 vs `PHASE1` 30,267. Pick one source of truth; record snapshot date.
2. **Biomarker / LOINC coverage** — `PHASE1` says 9,467 nodes at 100%; report Figure 4.1 shows 79%; Figure 2.2 implies ≈9.5K / 23.8K ≈ 40%. **Most concrete data error.** Biomarker pool grew beyond originally mapped LOINC subset; the 100% and 79% claims are both stale/incorrect.
3. **OntologyConcept count** — dashboard 51, Section 6 says 46 AlzKBConcept, Figure 9.1 ≈22, `PHASE1` ground truth 52 (47 + 5 ICD-10). Internally inconsistent; pick canonical count.
4. **IS_A edges** — report 27 vs `PHASE1` 25. Minor; flag growth.
5. **URI-coverage denominators** — 1,509,297 (Section 4.1) vs 1,430,527 (dashboard) vs ~1.2M (`PHASE1`). Denominators not internally consistent across the report.

### 3.3 Meeting decisions not yet reflected

- **Title** still contains "Enrichment". Suggested: *"Ontology Selection and Evaluation for a
  Multimodal Alzheimer's Disease Knowledge Graph"*.
- **Thesis acronym change** pending; decide whether the paper's KG name stays "MAKO".
- **Before/after per-step baseline** (Hajer) — highest-leverage open task; would move
  Claim 1 from "qualitatively supported" to "fully supported".
- **OntoQA vs FAIR** — substitution not formalised; contribution table and paper describe
  different frameworks.
- **Causal layer** — correctly framed as post-defence work (Section 12). Aligned.

---

## 4. Bottom Line

The report is broadly consistent with the revised structure (C1, C2, C3, C7 main;
C4 removed; C5 demoted; C6 deferred) but is **not yet a clean paper-ready evaluation
artefact** because of: weak C7 numbers relative to its headline status, multiple internal
numerical inconsistencies, the missing before/after baseline Hajer requested, and the
unresolved OntoQA/FAIR framework duplication. All issues are fixable; the
Biomarker-coverage error and the per-step baseline are the two highest priorities.

---

## 5. Open Remediation Items

- [ ] Reconcile Biomarker node count and LOINC coverage; update `PHASE1` and contribution table.
- [ ] Produce one canonical Cypher snapshot; cite the same numbers in every figure/table.
- [ ] Generate per-step before/after deltas (revert Steps 17–20 in a DB clone or use earlier git state).
- [ ] Decide OntoQA: drop, or keep as complementary table per Hajer's question 2.
- [ ] Reattribute the 99.6% edge-coverage claim from C5 to C2.
- [ ] Strengthen the AlzKB curated crosswalk before submission, or reframe Section 6 to avoid overclaim.
- [ ] Apply the title change; resolve the thesis acronym.
- [ ] Redraw the contribution diagram for the C1/C2/C3/C7 set.

---

*This document records a single review session. It supersedes no prior PHASE history file
and should sit alongside them as a review log.*