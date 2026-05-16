# Tasks — MAKO Finishing (v3)

> **Purpose.** Granular, resumable task list backing [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Every task has an ID, a verification command, and a dependency note.
>
> **Convention.**
> - `[ ]` = open, `[x]` = done, `[~]` = partially done (existing repo work that v3 extends).
> - IDs prefixed `Q*` for approval gates, `A0*` for Phase 0 audit, `S1*` for Sultan deliverable, `P2*` for snapshot+figures, `P3*` for gap closure, `P4*` for re-measure, `TH*` for thesis, `R6*` for reproducibility.
> - Each task lists its dependencies in parentheses after the description.
> - **Status legend** (right column):
>   - 🆕 *Added in v3* (net new vs v2)
>   - ✅ *Completed* (already in repo; do not duplicate)
>   - ❌ *Missing* (must be built)
>   - 🚧 *In progress* (work started, not done)
>   - ⏸️ *Paused* (intentionally deferred — see [c7_plan_v2/CAUSALITY_NOTE.md](../c7_plan_v2/CAUSALITY_NOTE.md))
>
> See [STATUS.md](STATUS.md) for the at-a-glance ledger.

---

## Q — Approval gates (do these first)

- [ ] **Q.1** — Walk through this `IMPLEMENTATION_PLAN.md` and `TASKS.md` with Asst. Prof. Özgün Pınarer and Dr. Sultan Nezihe Turhan. Capture revisions in `meeting_notes.md`. (no deps) 🆕
- [ ] **Q.2** — Send the revised plan to Dr. Hajer Baazaoui for the FAIR / semantic density + B-17 to B-21 scope confirmation. (Q.1) 🆕
- [ ] **Q.3** — Per Hajer's prior note, the baseline is the pre-enrichment graph (rollback of Steps 17–20 on a copy). Confirm the rollback strategy with Özgün; document the decision in `metrics/BASELINE_DECISION.md`. (Q.1) ❌
- [ ] **Q.4** — Pin the AlzKB CYPHERL dump version used by `steps/step24_alzkb_bridge.py`; archive the exact file in `data/alzkb/<version>/`. (Q.1) ❌
- [ ] **Q.5** — Confirm the FAIR scoring rubric (three-level scale: no / partial / yes) with Hajer before any code is written. (Q.2) ❌
- [ ] **Q.6** — Confirm validity-rubric thresholds with Sultan. Default ≥ 95 % per assertion; some hard-fail conditions binary. (Q.1) ❌
- [ ] **Q.7** — Schedule offline-snapshot downtime windows on the Galatasaray Neo4j instance with Özgün (P2.1 prereq). (Q.1, Q.3) ❌
- [ ] **Q.8** — Send the contribution-gap closure plan (B-17 to B-21) to Hajer for scope confirmation. Especially: are HPO terms 15 / 30 / both? Is MEDHIST comorbidity at category granularity the agreed scope? (Q.2) 🆕
- [ ] **Q.9** — Confirm Biolink Model ambiguous mappings with Hajer — see [GAP_CLOSURE_SPEC.md §B-20](GAP_CLOSURE_SPEC.md) for the list of node types whose Biolink class is non-obvious. (Q.2) 🆕

---

## P0 — Pre-flight infrastructure

- [ ] **P0.1** — Verify Neo4j 5.x connectivity from a clean shell. (Q.1) ✅ Already running locally; reconfirm before Phase 0.
- [ ] **P0.2** — Confirm `headers.json` and existing ontology data files are readable. (Q.1) ✅
- [ ] **P0.3** — Verify directory tree exists: `metrics/`, `figures/`, `tests/`, `paper_outputs/`, `outputs/validity_reports/`, `data/snapshots/`, `data/alzkb/`, `ontology/mappings/`. (Q.1) ❌ (`ontology/mappings/` and `data/snapshots/` likely missing)
- [ ] **P0.4** — Create `requirements-metrics.txt` if not present (neo4j, rdflib, pandas, matplotlib, seaborn, graphviz, mermaid-cli, pyyaml). (Q.1) ✅ (likely already present)
- [ ] **P0.5** — Create `ontology/mappings/` directory and stub `index.csv` with the column header. (Q.1) ❌

---

## A0 — Phase 0: Audit + reconcile

- [ ] **A0.1** — Run `python -m metrics --all` against the live Galatasaray Neo4j. Capture: validity report, FAIR score, semantic density, AlzKB alignment, canonical snapshot.
  - **Verify.** `outputs/validity_reports/kg_validity_<ts>.{json,md}` exists; `metrics/output/canonical_snapshot.json` exists with timestamp ≤ 24 h old; all 7 validity assertions PASS.
  - **Deps.** P0.1, P0.3
  - ❌
- [ ] **A0.2** — Reconcile the three disagreeing counts:
  - **visit count** (33,800 vs 30,267)
  - **biomarker LOINC coverage** (100 % CSF vs 78.84 % all biomarkers)
  - **OntologyConcept count** (51 vs 46 vs 52)
  - Resolution rule: the canonical snapshot from A0.1 wins; older docs must be aligned.
  - **Verify.** Single set of numbers used in `STATUS.md` update.
  - **Deps.** A0.1
  - ❌
- [ ] **A0.3** — Update [c7_plan_v2/STATUS.md](../c7_plan_v2/STATUS.md) and create `docs/final_report/c7_plan_v3/AUDIT_2026-05-16.md` with the reconciled numbers + diff vs prior docs.
  - **Verify.** New file committed; STATUS.md "Last reviewed" date bumped.
  - **Deps.** A0.2
  - 🆕
- [ ] **A0.4** — Verify the AlzKB integration is alive: confirm `(:AlzKBConcept)` and `(:Diagnosis)-[:SAME_AS]->(:AlzKBConcept)` (and equivalents for Anatomy / Phenotype) are populated. If empty, re-run [steps/step24_alzkb_bridge.py](../../../steps/step24_alzkb_bridge.py).
  - **Verify.** Cypher: `MATCH (:AlzKBConcept) RETURN count(*) > 0`.
  - **Deps.** A0.1
  - ❌
- [ ] **A0.5** — Confirm no `381_S_*` PTIDs exist (`utils/batch_processor.py::DataValidator.validate_ptid`).
  - **Verify.** `MATCH (p:Patient) WHERE p.ptid STARTS WITH '381_S_' RETURN count(p)` returns 0.
  - **Deps.** A0.1
  - ❌

---

## S1 — Phase 1: Sultan's progress-report artifact

> Spec: [VALIDITY_PROGRESS_REPORT_SPEC.md](VALIDITY_PROGRESS_REPORT_SPEC.md)

- [ ] **S1.1** — Confirm thresholds in `metrics/validity_rubric.yaml` with Sultan (Q.6 — currently default 0.95). Capture the decision in `metrics/validity_rubric.yaml` comments + the audit doc.
  - **Verify.** Sultan sign-off in `meeting_notes.md`.
  - **Deps.** Q.6, A0.1
  - 🆕
- [ ] **S1.2** — Add a `render_progress_report()` helper in `metrics/validity.py` that, given the JSON output, produces `outputs/validity_reports/kg_validity_progress_report.md`. Spec defines sections (a)–(e); see [VALIDITY_PROGRESS_REPORT_SPEC.md](VALIDITY_PROGRESS_REPORT_SPEC.md).
  - **Verify.** Generated MD opens cleanly; renders to PDF via `metrics/thesis_pdf.py`.
  - **Deps.** S1.1
  - 🆕
- [ ] **S1.3** — Add a Turkish-language preamble paragraph to the MD: *"Bu rapor, ADNI bilgi grafının LPG'den KG'ye dönüşümünün tamamlandığını ve yedi doğrulama testinin başarıyla geçildiğini belgeler."* Sultan asked in Turkish; mirroring removes friction.
  - **Verify.** Visible in the generated MD.
  - **Deps.** S1.2
  - 🆕
- [ ] **S1.4** — Regenerate the report after Phase 3 enrichment lands so Sultan sees the final enriched graph state. Versioned: `kg_validity_progress_report_<ts>.md`; latest copied / symlinked to `kg_validity_progress_report.md`.
  - **Verify.** New timestamp present; counts reflect post-B17–B21 graph.
  - **Deps.** P4.6
  - 🆕
- [ ] **S1.5** — Unit test in `tests/test_validity.py` for `render_progress_report()` — runs against the mini-KG fixture, asserts presence of sections (a)–(e) and the Turkish preamble.
  - **Verify.** `pytest tests/test_validity.py::test_render_progress_report` green.
  - **Deps.** S1.2
  - 🆕

---

## P2 — Phase 2: Snapshot + figures infrastructure

- [ ] **P2.1** — Coordinate offline downtime window with Özgün on the GSU Neo4j instance (Q.7 prereq).
  - **Verify.** Calendar invite confirmed; downtime block of ~30 min secured.
  - **Deps.** Q.7
  - ❌
- [ ] **P2.2** — Use `metrics/snapshots.py` to capture `data/snapshots/post_steps_17_20.dump` (current state — baseline of "after migration").
  - **Verify.** Dump file exists; loads cleanly on a sibling Neo4j instance.
  - **Deps.** P2.1
  - ❌
- [ ] **P2.3** — Author `metrics/scripts/rollback_steps_17_20.cypher` — removes property additions (`snomed_code`, `loinc_code`, `uberon_code`, `icd10_code`, `mondo_code`, `rdf_type`, `source_ontology`, edge `uri`) and `:OntologyConcept` nodes + `MAPS_TO` / `IS_A` / `CLASSIFIED_AS` edges. Idempotent.
  - **Verify.** Round-trip: restore post-dump → run rollback → run steps 17–20 → result matches original post-dump (count parity).
  - **Deps.** P2.2
  - ❌
- [ ] **P2.4** — Capture `data/snapshots/pre_steps_17_20.dump` (post-rollback state).
  - **Verify.** Dump file exists; node/edge counts match the rolled-back graph.
  - **Deps.** P2.3
  - ❌
- [ ] **P2.5** — Capture intermediate snapshots: restore pre-dump → step 17 → dump → step 18 → dump → step 19 → dump → step 20 → dump. Output: `post_step_{17,18,19,20}.dump`.
  - **Verify.** Four dump files exist with monotonically growing node/edge counts.
  - **Deps.** P2.4
  - ❌
- [ ] **P2.6** — Run `metrics/runner.py` against each snapshot. Persist per-snapshot JSON: `metrics/output/{fair,semantic_density,alzkb_alignment}_{pre,post17,post18,post19,post20}.json`.
  - **Verify.** 5 × 3 = 15 JSON files exist; each has the structure of the post-state JSON.
  - **Deps.** P2.5
  - ❌
- [ ] **P2.7** — Compute deltas: `metrics/output/fair_delta_per_step.json`, `metrics/output/density_delta_per_step.json`.
  - **Verify.** Deltas non-zero for at least F3-relevant principles (I1, I2, I3) and edge-URI density.
  - **Deps.** P2.6
  - ❌
- [ ] **P2.8** — Extend `metrics/step_audit.py` to read the per-step JSONs + the dump pair Cypher diffs and emit `metrics/output/step_audit.csv` with columns: `step, nodes_touched, edges_added, properties_added, runtime_s, fair_delta_overall, density_delta_node, density_delta_edge`.
  - **Verify.** CSV has 4 rows (steps 17–20) with numeric deltas.
  - **Deps.** P2.7
  - 🚧 (step_audit.py exists; needs wiring to per-step JSONs)
- [ ] **P2.9** — Run `figures/f4_density.py` against `semantic_density_per_step.json`. Output: `paper_outputs/f4_density.{svg,pdf,png}`. **Must visibly differ from `outputs/eda_figures/10_ontology_coverage.svg`** — F4 is a per-step time series; the step-29 figure is a single-state heatmap. Add a docstring assertion.
  - **Verify.** F4 files exist; visual diff confirms distinct.
  - **Deps.** P2.7
  - 🚧 (code exists; needs JSON input + render commit)
- [ ] **P2.10** — Re-render F1, F2, F3, F5 from the latest JSON outputs so they reflect post-enrichment numbers (they will shift after Phase 3).
  - **Verify.** Updated `paper_outputs/{f1,f2,f3,f5}.{svg,pdf}` with fresh timestamps.
  - **Deps.** P4.3, P4.4
  - ❌
- [ ] **P2.11** — Add a Makefile / `scripts/make_paper_figures.ps1` (Windows-friendly) target `paper-figures` that runs all five F-scripts and writes outputs deterministically.
  - **Verify.** `make paper-figures` (or PS1 equivalent) succeeds; SVG hashes match committed versions.
  - **Deps.** P2.9, P2.10
  - ❌
- [ ] **P2.12** — Add a pre-commit hook entry (or CI workflow) that runs `make paper-figures` and fails if any SVG drifts from the committed version.
  - **Verify.** Hook runs locally without errors; drifted SVG triggers a fail.
  - **Deps.** P2.11
  - ❌ (optional but cheap)

---

## P3 — Phase 3: Close contribution-table gaps (B-17 → B-21)

> Spec: [GAP_CLOSURE_SPEC.md](GAP_CLOSURE_SPEC.md). All new steps follow the pipeline pattern: `execute_step_n(neo4j_uri, user, password)` exported, registered in `pipeline.py` under a `config.yaml` toggle, uses `MERGE` / `IF NOT EXISTS` for idempotency.

### Cross-cutting

- [ ] **P3.0** — Add new toggles to `config.yaml` under "PIPELINE STEP CONTROL": `run_hpo_expansion`, `run_loinc_vitals`, `run_medhist_comorbidity`, `run_biolink_categories`, `run_mondo_doid_wiring`. Default all `false` (opt-in).
  - **Verify.** `python pipeline.py --help` shows the new toggles.
  - **Deps.** P0.3
  - 🆕
- [ ] **P3.1** — Register the five new steps in `pipeline.py` following the `_execute_*` + `_run_step` pattern.
  - **Verify.** `python pipeline.py --dry-run` lists steps 30–34.
  - **Deps.** P3.0
  - 🆕
- [ ] **P3.2** — Author per-step idempotency tests in `tests/test_step30.py` … `test_step34.py` modeled on `tests/test_idempotency.py`.
  - **Verify.** `pytest tests/test_step30.py tests/test_step31.py tests/test_step32.py tests/test_step33.py tests/test_step34.py` green.
  - **Deps.** P3.6
  - 🆕
- [ ] **P3.3** — Author the column-to-concept reproducibility CSVs (was R1 in v2): `adsxlist_to_hpo.csv`, `vitals_to_loinc.csv`, `medhist_to_snomed.csv`, `diagnosis_to_doid.csv`, `biolink_categories.csv`, `biolink_predicates.csv` under `ontology/mappings/`. Plus consolidated `index.csv`.
  - **Verify.** All seven CSVs exist; each row has: `source_table, source_column, source_value_pattern, target_ontology, target_uri, target_label, mapping_rule, test_fixture_id, last_verified_date`.
  - **Deps.** P0.5
  - 🆕
- [ ] **P3.4** — Update `metrics/validity_rubric.yaml`: extend A3 `required_sources` to `[SNOMED-CT, LOINC, UBERON, HPO, ICD-10, MONDO, DOID]`; update A5 allowlist if `HAS_COMORBIDITY` is intentionally not URI-annotated; add count-band hints for HPO (30) and LOINC (16). Sultan signs off via Q.6.
  - **Verify.** Validity report shows 7 sources; all PASS.
  - **Deps.** P3.6, Q.6
  - 🆕

### B-17 — HPO expansion (5 → ~30 concepts) — Step 30

- [ ] **P3.10** — Author `steps/step30_hpo_expansion.py`. See [GAP_CLOSURE_SPEC.md §B-17](GAP_CLOSURE_SPEC.md) for the full HPO term list, ADSXLIST column mapping, and REST handling. Idempotent.
  - **Verify.** Running twice produces same node/edge counts; HPO `:OntologyConcept` count ≥ 25; new MAPS_TO ≥ 3,000.
  - **Deps.** P0.5, P3.0
  - ❌
- [ ] **P3.11** — Cache HPO labels in `ontology/hpo_concepts_cache.json` from a known-good lookup (EBI OLS or BioPortal). Used as offline fallback by step 30.
  - **Verify.** File present; step 30 succeeds even if REST is offline.
  - **Deps.** P3.10
  - ❌
- [ ] **P3.12** — Author `ontology/mappings/adsxlist_to_hpo.csv` per P3.3 schema. ~15 rows.
  - **Verify.** `tests/test_column_to_concept.py::test_adsxlist_hpo` green.
  - **Deps.** P3.10
  - 🆕

### B-18 — LOINC vital signs (10 → 16 codes) — Step 31

- [ ] **P3.20** — Author `steps/step31_loinc_vital_signs.py`. See [GAP_CLOSURE_SPEC.md §B-18](GAP_CLOSURE_SPEC.md). Creates 6 new `:OntologyConcept(source_ontology='LOINC')` + MAPS_TO from `:Visit` (or appropriate vital-sign carrier).
  - **Verify.** OntologyConcept count for LOINC: 10 → 16. New MAPS_TO count matches VITALS row × 6 − nulls.
  - **Deps.** P3.0, A0.1
  - ❌
- [ ] **P3.21** — Author `ontology/mappings/vitals_to_loinc.csv`. 6 rows.
  - **Verify.** `tests/test_column_to_concept.py::test_vitals_loinc` green.
  - **Deps.** P3.20
  - 🆕

### B-19 — MEDHIST → Comorbidity nodes — Step 32

- [ ] **P3.30** — Author `steps/step32_medhist_comorbidity.py`. See [GAP_CLOSURE_SPEC.md §B-19](GAP_CLOSURE_SPEC.md). Creates `:Comorbidity` nodes at category granularity + `HAS_COMORBIDITY` edges.
  - **Verify.** `:Comorbidity` count > 0; each has `snomed_code`; HAS_COMORBIDITY count matches MEDHIST flag count.
  - **Deps.** P3.0, A0.1
  - ❌
- [ ] **P3.31** — Author `ontology/mappings/medhist_to_snomed.csv`. ≥ 5 category rows.
  - **Verify.** `tests/test_column_to_concept.py::test_medhist_snomed` green.
  - **Deps.** P3.30
  - 🆕

### B-20 — Biolink Model — Step 33

- [ ] **P3.40** — Author `steps/step33_biolink_categories.py`. Sets `biolink_category` on all 17 node labels + `biolink_predicate` on 30 relationship types. See [GAP_CLOSURE_SPEC.md §B-20](GAP_CLOSURE_SPEC.md).
  - **Verify.** ≥ 12 / 17 node types have `biolink_category`; ≥ 12 / 30 relationship types have `biolink_predicate`.
  - **Deps.** P3.0, Q.9
  - ❌
- [ ] **P3.41** — Author `ontology/mappings/biolink_categories.csv` (17 rows) and `biolink_predicates.csv` (30 rows). Document ambiguous decisions in `mapping_rule` column.
  - **Verify.** `tests/test_column_to_concept.py::test_biolink_*` green.
  - **Deps.** P3.40
  - 🆕

### B-21 — MONDO/DOID concept wiring — Step 34

- [ ] **P3.50** — Author `steps/step34_mondo_doid_wiring.py`. See [GAP_CLOSURE_SPEC.md §B-21](GAP_CLOSURE_SPEC.md). Creates `:OntologyConcept(source_ontology='MONDO')` + `:OntologyConcept(source_ontology='DOID')` (3 nodes) + MAPS_TO edges.
  - **Verify.** OntologyConcept source distinct count = 7 (was 5).
  - **Deps.** P3.0
  - ❌
- [ ] **P3.51** — Author `ontology/mappings/diagnosis_to_doid.csv` (3 rows: AD, dementia, MCI).
  - **Verify.** `tests/test_column_to_concept.py::test_diagnosis_doid` green.
  - **Deps.** P3.50
  - 🆕

### Post-execution

- [ ] **P3.5** — Re-run Phase 2 snapshot capture (P2.2–P2.5) for steps 30–34 individually: `post_step_{30,31,32,33,34}.dump`.
  - **Verify.** Five additional dumps committed.
  - **Deps.** P3.10, P3.20, P3.30, P3.40, P3.50, P2.1
  - 🆕
- [ ] **P3.6** — Re-run `metrics/runner.py` on the final post-step-34 graph. Confirm: validity PASS; HPO A-Box coverage > 80 %; LOINC count = 16; MONDO+DOID OntologyConcept counts > 0; Biolink-categorized node count ≥ 12 / 17. Update `canonical_snapshot.json`.
  - **Verify.** New JSON has these properties; A1–A7 PASS.
  - **Deps.** P3.5
  - 🆕

---

## P4 — Phase 4: Re-measure on enriched graph + AlzKB refresh

- [ ] **P4.1** — Re-run `steps/step24_alzkb_bridge.py` so the AlzKB mapping picks up the new DOID, MONDO, expanded HPO codes. Pin the AlzKB CYPHERL dump version in `data/alzkb/<version>/` (Q.4 gate).
  - **Verify.** `:AlzKBConcept` + `:SAME_AS` counts increase; pinned dump file committed.
  - **Deps.** P3.6, Q.4
  - ❌
- [ ] **P4.2** — Run `metrics/alzkb_alignment.py` on the final graph. Expected jumps: **Disease** weak → strong (via SNOMED→MONDO→DOID); **Phenotype** none → strong (HPO expansion); **Anatomy** strong → strong (unchanged); **Gene** none → not-applicable (flagged).
  - **Verify.** `metrics/output/alzkb_alignment.json` shows 3 / 4 strong matches.
  - **Deps.** P4.1
  - ❌
- [ ] **P4.3** — Regenerate F5 (alignment matrix) figure. The Gene row stays distinct ("N/A — see Future Work").
  - **Verify.** `paper_outputs/f5_alignment.{svg,pdf}` updated.
  - **Deps.** P4.2
  - ❌
- [ ] **P4.4** — Re-run `metrics/fair.py` — expect I1 and I2 to score higher post-Biolink and post-MONDO/DOID. Aggregate may rise toward 0.96.
  - **Verify.** `fair_score_post.json` reflects new score; F3 figure regenerated.
  - **Deps.** P3.6
  - ❌
- [ ] **P4.5** — Re-run `metrics/semantic_density.py` — expect node-URI coverage on `:Patient` (Biolink), `:Visit`, `:Comorbidity` to climb. Aggregate node-URI > 50 % likely.
  - **Verify.** `semantic_density_post.json` reflects new coverage.
  - **Deps.** P3.6
  - ❌
- [ ] **P4.6** — Update [STATUS.md](STATUS.md) — flip all ❌ rows for B-17 to B-21 to ✅. Move [c7_plan_v2/CONTRIBUTION_TABLE_GAP_ANALYSIS.md](../c7_plan_v2/CONTRIBUTION_TABLE_GAP_ANALYSIS.md) gap items from "missing" to "done".
  - **Verify.** All status badges accurate against the latest canonical snapshot.
  - **Deps.** P4.2, P4.4, P4.5
  - 🆕

---

## T — Tables (paper)

- [ ] **T1.1** — Take the existing ontology / tool / standard assessment summary from `c7_unified_contribution.md` and trim to single-page paper table. Final form: `paper_outputs/t1_assessment.tex` (LaTeX `tabular`).
  - **Verify.** Compiles standalone in a minimal `\documentclass{article}` test file.
  - **Deps.** Q.2
  - ❌
- [ ] **T2.1** — Generate `paper_outputs/t2_step_audit.tex` from `step_audit.csv` via a Pandas-to-LaTeX shim.
  - **Deps.** P2.8
  - ❌
- [ ] **T3.1** — Generate `paper_outputs/t3_column_to_concept.tex` from `ontology/mappings/index.csv`, paginated.
  - **Deps.** P3.3
  - ❌
- [ ] **T4.1** — Generate `paper_outputs/t4_alignment.tex` from `alzkb_alignment.json`.
  - **Deps.** P4.2
  - ❌

---

## TH — Phase 5: Thesis patches

> Spec: [THESIS_PATCH_PLAN.md](THESIS_PATCH_PLAN.md) — chapter-by-chapter LaTeX snippets.

- [ ] **TH.1** — **Chapter 3 — §3.10 (Quality Assurance and Validation).** Replace "intermediate snapshots not yet captured" caveat with per-step snapshot description + validity gate ref. (P2.5, S1.5) 🆕
- [ ] **TH.2** — **Chapter 3 — Add Steps 30–34 descriptions** in §3.5–3.9 (or after the §3.X covering Step 20). Each gets ~150 words + a mapping-table reference. (P3.6) 🆕
- [ ] **TH.3** — **Chapter 4 — §4.2 (Graph Composition).** Update node count, edge count, OntologyConcept count to match the new canonical snapshot. (P4.6) 🆕
- [ ] **TH.4** — **Chapter 4 — §4.3 (Structural Validity).** Insert the Sultan-facing validity report as a table or appendix figure. Include all 7 assertions with pass status. (S1.4) 🆕
- [ ] **TH.5** — **Chapter 4 — §4.4 (Semantic Density).** Add per-step density progression table + reference Figure F4. Replace placeholders with measured values. (P2.9, P4.5) 🆕
- [ ] **TH.6** — **Chapter 4 — §4.5 (FAIR Compliance).** Update aggregate FAIR score + per-principle scores + before/after delta. Reference F3 figure. (P4.4) 🆕
- [ ] **TH.7** — **Chapter 4 — §4.6 (AlzKB Alignment).** Update alignment matrix: Disease weak→strong, Phenotype none→strong, Anatomy strong, Gene N/A. Reference F5. Note Gene gap explicitly. (P4.3) 🆕
- [ ] **TH.8** — **Chapter 5 — §5.3 (Threats to Validity / Limitations).** Remove "per-step progression deferred" (now done). Add: *"Gene Ontology integration is deferred to future work; see Section 5.4."* (TH.5) 🆕
- [ ] **TH.9** — **Chapter 5 — §5.4 (Future Work).** Remove "snapshot programme". Keep "Gene Ontology integration", "C6 comparative benchmark", "Causal layer (post-defense)". (TH.5) 🆕
- [ ] **TH.10** — **Bibliography.** Add Biolink Model (Bizon et al. 2019 / Unni et al. 2022), MONDO (Vasilevsky et al. 2022), DOID (Schriml et al. 2012/2022) if not already in `thesis_references.bib`. Confirm Wilkinson 2016, Romano 2024, Yang 2025 present. **Do not** add Tartir 2005 (OntoQA). (P5 prereq) 🆕
- [ ] **TH.11** — **Appendix — Column-to-concept supplementary.** Insert consolidated `ontology/mappings/index.csv` as Appendix A. (P3.3) 🆕
- [ ] **TH.12** — **Mirror updates to `Thesis/Article/article.tex`.** Update FAIR aggregate, AlzKB matrix, MAKO naming, figure references. (TH.6, TH.7) 🆕
- [ ] **TH.13** — **Re-run thesis LaTeX build.** `pdflatex → bibtex → pdflatex → pdflatex` end-to-end; no unresolved refs; figures embed cleanly. (TH.1–TH.12) 🆕

---

## R6 — Phase 6: Reproducibility + hand-off

- [ ] **R6.1** — Single-entrypoint check: clean venv, run `python -m metrics --all` end-to-end. Validity gate first; downstream metrics on PASS; non-zero exit on FAIL.
  - **Verify.** All JSON + CSV + figures regenerated; no manual steps.
  - **Deps.** P4.6, P3.6
  - ❌
- [ ] **R6.2** — One-command paper figures: `make paper-figures` (or PS1) reproduces F1–F5 byte-identically.
  - **Verify.** SVG hashes match.
  - **Deps.** P2.11, P4.3
  - ❌
- [ ] **R6.3** — Update master docs: [docs/infrastructure/CLAUDE_CODE_GUIDE.md](../../infrastructure/CLAUDE_CODE_GUIDE.md), [docs/infrastructure/TASKS.md](../../infrastructure/TASKS.md), [docs/infrastructure/IMPLEMENTATION_PLAN.md](../../infrastructure/IMPLEMENTATION_PLAN.md) — record steps 30–34, metrics pipeline status, artifact locations.
  - **Verify.** Master docs mention steps 30–34; sources of truth align.
  - **Deps.** P3.6
  - 🆕
- [ ] **R6.4** — Update project memory: `memory/MEMORY.md` "Phase 1 (Steps 17–20)" → "Phase 1 + 1.5 (Steps 17–20 + 30–34)". Add post-enrichment counts.
  - **Verify.** `memory/MEMORY.md` reflects current state.
  - **Deps.** P4.6
  - 🆕
- [ ] **R6.5** — Sign-off circulation: Sultan (S1.4 MD), Özgün (this plan executed), Hajer (paper section updates). Capture responses in `meeting_notes.md`.
  - **Verify.** All three confirm in writing.
  - **Deps.** TH.13, R6.1
  - 🆕
- [ ] **R6.6** — Tag the repo `paper-submission-v1` and `thesis-defense-v1` after R6.1 + R6.2 pass + Phase 5 LaTeX builds.
  - **Verify.** `git tag -l 'paper-submission-v1'` returns the tag.
  - **Deps.** R6.5
  - 🆕

---

## Causality (paused — do not remove code)

> Full rationale: [c7_plan_v2/CAUSALITY_NOTE.md](../c7_plan_v2/CAUSALITY_NOTE.md).

- [~] **CAU.0** — `steps/step21..step26*.py` and `causal/` retained. ⏸️
- [ ] **CAU.1** — All causal `run_*` toggles in `config.yaml` remain `false`. ⏸️
- [ ] **CAU.2** — No deletion of causal code by any v3 task. ⏸️
- [ ] **CAU.3** — Resume after C7 paper submission and thesis defense (post-May 2026). Out of scope for this plan. ⏸️

---

## What is *not* in this list

- **No OntoQA tasks.** FAIR + semantic density only.
- **No causal-discovery tasks.** See `c7_plan_v2/CAUSALITY_NOTE.md`.
- **No pipeline performance benchmarks.** Already covered in the IEEE Big Data 2025 paper and `steps/step16_create_metrics.py`.
- **No Gene Ontology integration.** Removed per Hajer's note; documented as known limitation in the thesis.
- **No ontology integration beyond MONDO + DOID + Biolink + expanded HPO/LOINC.** Future work, post-June 2026.
- **No edits to v2 documents** beyond the STATUS.md cross-reference update.
