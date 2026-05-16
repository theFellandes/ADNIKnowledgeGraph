# Tasks — KG Validity, Metrics, Figures (C7 + Thesis)

> **Purpose.** Granular, resumable task list for the validity gate, metric pipeline, and visualisation work that backs the C7 paper. Every task has an ID, a verification command, and a dependency note. **No scripts are written by completing this task list — these tasks are the *plan* for that work; the work itself happens in a follow-up session once Sultan and Özgün approve the plan.**
>
> **Convention.**
> - `[ ]` = open, `[x]` = done, `[~]` = partially done (existing repo work that this plan extends).
> - IDs prefixed `Q*` for approval gates, `V*` for validity, `M*` for metrics, `F*` for figures, `T*` for tables, `R*` for reproducibility, `P*` for paper integration, `TH*` for thesis hand-off.
> - Each task lists its dependencies in parentheses after the description.
> - **Status legend** (right column):
>   - 🆕 *Added in this revision* (new vs `task_metrics.md`)
>   - ✅ *Completed* (already in repo; do not duplicate)
>   - ❌ *Missing* (must be built)
>   - ⏸️ *Paused* (intentionally deferred — see [CAUSALITY_NOTE.md](CAUSALITY_NOTE.md))
>
> See [STATUS.md](STATUS.md) for the at-a-glance ledger that reorganises every row below by status.

---

## Q — Approval gates (do these first)

- [ ] **Q.1** — Walk through this `IMPLEMENTATION_PLAN.md` and `TASKS.md` with Asst. Prof. Özgün Pınarer and Dr. Sultan Nezihe Turhan. Capture revisions in `meeting_notes/`. (no deps) ❌
- [ ] **Q.2** — Send the revised plan to Dr. Hajer Baazaoui for the FAIR / semantic density additions and the column-to-concept reproducibility table. Wait for confirmation. (Q.1) ❌
- [ ] **Q.3** — Per Hajer's note, the baseline is the pre-enrichment graph (rollback of Steps 17–20 on a copy). Confirm the rollback strategy with Özgün; document the decision in `metrics/BASELINE_DECISION.md`. (Q.1) ❌
- [ ] **Q.4** — Pin the AlzKB CYPHERL dump version used by `steps/step24_alzkb_bridge.py`; archive the exact file in `data/alzkb/<version>/`. (Q.1) ❌
- [ ] **Q.5** — Confirm the FAIR scoring rubric (three-level scale: no / partial / yes) with Hajer before any code is written. (Q.2) ❌
- [ ] **Q.6** — 🆕 Confirm validity-rubric thresholds with Sultan. Default ≥ 95 % per assertion; some hard-fail conditions binary. (Q.1) ❌
- [ ] **Q.7** — 🆕 Schedule offline-snapshot downtime windows on the Galatasaray Neo4j instance with Özgün. (Q.1, Q.3) ❌

---

## P0 — Pre-flight infrastructure

- [ ] **P0.1** — Verify Neo4j 5.x connectivity from a clean shell: `cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "RETURN 1"`. (Q.1) ❌
- [ ] **P0.2** — Confirm `headers.json` and existing ontology data files are readable. (Q.1) ❌
- [ ] **P0.3** — Create the directory tree: `mkdir -p metrics/ figures/ tests/fixtures/ paper_outputs/ outputs/validity_reports/ data/snapshots/ data/alzkb/`. (Q.1) ❌
- [ ] **P0.4** — Create `requirements-metrics.txt` (neo4j, rdflib, pandas, matplotlib, seaborn, graphviz, mermaid-cli, pyyaml). (Q.1) ❌
- [ ] **P0.5** — 🆕 Create `ontology/mappings/` directory (currently absent — original plan referenced it as if it exists). (Q.1) ❌

---

## V — KG validity gate (NEW — Sultan's feedback)

> Full assertion set + Cypher queries in [VALIDITY_CHECK_SPEC.md](VALIDITY_CHECK_SPEC.md).

- [ ] **V1.1** — 🆕 Author `metrics/validity_rubric.yaml` with assertions A1–A7 and the per-assertion thresholds confirmed in Q.6. (Q.6, P0.3) ❌
- [ ] **V1.2** — 🆕 Implement `metrics/validity.py`. Reads the YAML, runs each Cypher assertion, emits `outputs/validity_reports/kg_validity_<timestamp>.json` and `.md`. Non-zero exit on any FAIL. (V1.1, P0.3) ❌
- [ ] **V1.3** — 🆕 Author `tests/fixtures/mini_kg.cypher` — synthetic ~50-node graph with known FAIR / density / validity scores. Used by every metric unit test. (P0.3) ❌
- [ ] **V1.4** — 🆕 Unit tests in `tests/test_validity.py` against the fixture, asserting expected pass/fail per assertion. (V1.2, V1.3) ❌
- [ ] **V1.5** — 🆕 Run `metrics/validity.py` on the current production graph; commit JSON + Markdown under `outputs/validity_reports/`. **This is the artefact Sultan asked for.** (V1.2) ❌
- [ ] **V1.6** — 🆕 Add a runner gate so M2–M5 tasks fail fast if validity has not passed. (V1.5, R2.1) ❌

---

## M1 — Baseline + per-step snapshots (foundation for all metrics)

- [ ] **M1.0** — 🆕 Implement `metrics/snapshots.py` wrapping `neo4j-admin database dump` and `database load`. Includes start/stop helpers and a verification step that the dump round-trips cleanly. (P0.3) ❌
- [ ] **M1.1** — Snapshot the current Neo4j graph: `neo4j-admin database dump → data/snapshots/post_steps_17_20.dump`. (Q.3, P0.1, M1.0) ❌
- [ ] **M1.2** — Restore the dump into a separate Neo4j instance, run `metrics/scripts/rollback_steps_17_20.cypher` to remove property additions and `:OntologyConcept` nodes from steps 17–20. Output: `data/snapshots/pre_steps_17_20.dump`. (M1.1, Q.3) ❌
- [ ] **M1.3** — Take an intermediate snapshot after each individual step (17, 18, 19, 20). Output: `data/snapshots/post_step_{17,18,19,20}.dump`. (M1.2) ❌

---

## M2 — FAIR scoring

- [ ] **M2.1** — Author `metrics/fair_principles.yaml` with one entry per FAIR principle (F1, F2, F3, F4, A1.1, A1.2, A2, I1, I2, I3, R1.1, R1.2, R1.3) per the rubric agreed in Q.5. (Q.5) ❌
- [ ] **M2.2** — Implement `metrics/fair.py`. Reads YAML, runs each check (Cypher / file presence / manual flag), produces JSON. (M2.1, P0.3) ❌
- [ ] **M2.3** — Unit tests in `tests/test_fair.py` against the mini-KG fixture. (M2.2, V1.3) ❌
- [ ] **M2.4** — Run on baseline snapshot. Output: `metrics/output/fair_score_baseline.json`. (M2.3, M1.2) ❌
- [ ] **M2.5** — Run on post-Steps-17–20 snapshot. Output: `metrics/output/fair_score_post.json`. (M2.3, M1.1) ❌
- [ ] **M2.6** — Run on each intermediate snapshot. Aggregate into `metrics/output/fair_score_per_step.json`. (M2.3, M1.3) ❌
- [ ] **M2.7** — Compute per-step FAIR deltas, write `metrics/output/fair_delta_per_step.json`. (M2.6) ❌

---

## M3 — Semantic density

- [ ] **M3.1** — Implement `metrics/semantic_density.py`. Computes node-URI coverage and edge-URI coverage, broken down per node label and per edge type, plus aggregate. (P0.3) ❌
- [ ] **M3.2** — Unit tests in `tests/test_semantic_density.py` against the mini-KG fixture. (M3.1, V1.3) ❌
- [ ] **M3.3** — Run on baseline. Output: `metrics/output/semantic_density_baseline.json`. (M3.2, M1.2) ❌
- [ ] **M3.4** — Run on post-Steps-17–20 snapshot. Output: `metrics/output/semantic_density_post.json`. (M3.2, M1.1) ❌
- [ ] **M3.5** — Run on each intermediate snapshot. Aggregate into `metrics/output/semantic_density_per_step.json`. (M3.2, M1.3) ❌
- [ ] **M3.6** — Compute per-step density deltas, write `metrics/output/density_delta_per_step.json`. (M3.5) ❌

---

## M4 — AlzKB alignment

> ⚠️ `steps/step24_alzkb_bridge.py` already creates `:AlzKBConcept` + `:SAME_AS` edges. The metric module **extends** this; it does not re-implement loading. See IMPLEMENTATION_PLAN.md Risk #2.

- [x] **M4.0** — `steps/step24_alzkb_bridge.py` exists and downloads / parses the AlzKB CYPHERL dump. ✅
- [ ] **M4.1** — Confirm AlzKB CYPHERL dump version pinned in Q.4 lives at `data/alzkb/<version>/alzkb.cypherl` and is the input to step 24. (Q.4) ❌
- [ ] **M4.2** — Implement `metrics/alzkb_alignment.py`. Reads `:AlzKBConcept` + `:SAME_AS` edges from the live graph; computes strong-match counts for the four in-scope categories (Disease, Anatomy, Phenotype, Gene). (M4.0, P0.3) ❌
- [ ] **M4.3** — Run on the post-Steps-17–20 snapshot. Output: `metrics/output/alzkb_alignment.json`. Include a Gene row with `not_implemented: true` and a docstring pointer to Future Work. (M4.2, M1.1) ❌
- [ ] **M4.4** — Materialise additional alignment edges if the existing step 24 SAME_AS coverage is insufficient. **Only run if M4.3 reveals gaps.** (M4.3) ❌

---

## M5 — Step audit (engineering metrics)

- [ ] **M5.1** — Implement `metrics/step_audit.py`. For each migration step: nodes touched, edges added, properties added, runtime in seconds. Combines log-parsing with diff-based Cypher counts on snapshot pairs. (M1.3) ❌
- [ ] **M5.2** — Output: `metrics/output/step_audit.csv` with columns `step, nodes_touched, edges_added, properties_added, runtime_s, fair_delta_overall, density_delta_node, density_delta_edge`. FAIR + density columns joined from M2.7 / M3.6. (M5.1, M2.7, M3.6) ❌

---

## R1 — Column-to-concept mapping (reproducibility artefact for Step C)

- [ ] **R1.0** — 🆕 Create `ontology/mappings/` directory (currently absent). Sub-task of P0.5 but listed here for traceability. (P0.5) ❌
- [ ] **R1.1** — Inventory every column-to-concept mapping currently used by Steps 18 and 20. One source-column per row. (P0.3, R1.0) ❌
- [ ] **R1.2** — Write each mapping as a CSV under `ontology/mappings/`, one CSV per source table (`adsxlist_to_hpo.csv`, `medhist_to_snomed.csv`, `vitals_to_loinc.csv`, etc.). (R1.1) ❌
- [ ] **R1.3** — Each CSV row contains: `source_table, source_column, source_value_pattern, target_ontology, target_uri, target_label, mapping_rule, test_fixture_id, last_verified_date`. (R1.2) ❌
- [ ] **R1.4** — Build `ontology/mappings/index.csv` consolidating all CSVs into one master file for the paper's supplementary material. (R1.2, R1.3) ❌
- [ ] **R1.5** — `tests/test_column_to_concept.py` loads each CSV, applies the rule to the fixture, asserts the expected target URI. (R1.3, V1.3) ❌

---

## F — Figures

> Guardrail: figures must visibly differ from `outputs/eda_figures/` outputs from `steps/step29_kg_eda.py`. See IMPLEMENTATION_PLAN.md §7.1.

### F1 — Functional dependency diagram (revised)

- [ ] **F1.1** — Sketch the new layout: C7 at centre, Steps A–D feeding in from the left and bottom, C6 (future work) on the right, the dropped C4 box shown faded as "removed". (Q.1) ❌
- [ ] **F1.2** — Implement in Mermaid in `figures/f1_dependency.mmd`. (F1.1) ❌
- [ ] **F1.3** — Render to SVG and PDF: `mmdc -i f1_dependency.mmd -o paper_outputs/f1_dependency.svg`. (F1.2) ❌
- [ ] **F1.4** — Verify the figure renders correctly in the paper LaTeX preview. (F1.3) ❌

### F2 — Schema before / after

- [ ] **F2.1** — Render the pre-Steps-17–20 schema as a Graphviz diagram from the baseline snapshot. (M1.2 or M1.3) ❌
- [ ] **F2.2** — Render the post-Steps-17–20 schema (including the `:OntologyConcept` layer) the same way. (M1.1) ❌
- [ ] **F2.3** — Side-by-side composition in `paper_outputs/f2_schema.svg`. **Must be visibly distinct from `outputs/eda_figures/15_relationship_schema.svg`** (step 29 single-state schema). Same node positioning where possible to make the diff visually obvious. (F2.1, F2.2) ❌

### F3 — FAIR scorecard

- [ ] **F3.1** — Implement `figures/f3_fair.py`. Reads `fair_score_baseline.json` and `fair_score_post.json`, produces a per-principle bar / heatmap with two bars per principle (baseline vs post). 13 FAIR principles on the x-axis, score on the y-axis. (M2.4, M2.5) ❌
- [ ] **F3.2** — Apply GSU palette (dark blue / pink accent) for the thesis version; produce a separate greyscale-friendly version for the journal paper. (F3.1) ❌
- [ ] **F3.3** — Output: `paper_outputs/f3_fair.svg` and `f3_fair.pdf`. (F3.2) ❌

### F4 — Semantic density progression

- [ ] **F4.1** — Implement `figures/f4_density.py`. Reads `semantic_density_per_step.json`. Stacked area / waterfall chart: node-URI and edge-URI coverage growing per step. X-axis: pre, post-17, post-18, post-19, post-20. **Must be visibly distinct from `outputs/eda_figures/10_ontology_coverage.svg`** (step 29 static heatmap). (M3.5, M3.6) ❌
- [ ] **F4.2** — Output: `paper_outputs/f4_density.svg`. (F4.1) ❌

### F5 — AlzKB alignment matrix

- [ ] **F5.1** — Implement `figures/f5_alignment.py`. Reads `alzkb_alignment.json`, produces a 4 × 2 heatmap (categories × pre/post) with cell shading for none / weak / strong, plus the strong-match count as cell text. (M4.3) ❌
- [ ] **F5.2** — Mark the Gene row visually distinct ("N/A — see Future Work") so reviewers cannot misread it as a measured zero. (F5.1) ❌
- [ ] **F5.3** — Output: `paper_outputs/f5_alignment.svg`. (F5.2) ❌

---

## T — Tables

- [ ] **T1.1** — Take the existing ontology / tool / standard assessment summary from `c7_unified_contribution.md` and trim it to fit a single-page paper table. Final form: `paper_outputs/t1_assessment.tex` (LaTeX `tabular`). (Q.1) ❌
- [ ] **T2.1** — Generate `paper_outputs/t2_step_audit.tex` from `step_audit.csv` via a Pandas-to-LaTeX shim. (M5.2) ❌
- [ ] **T3.1** — Generate `paper_outputs/t3_column_to_concept.tex` from `ontology/mappings/index.csv`, paginated to fit the supplementary material section. (R1.4) ❌
- [ ] **T4.1** — Generate `paper_outputs/t4_alignment.tex` from `alzkb_alignment.json`. (M4.3) ❌

---

## R2 — Reproducibility

- [ ] **R2.1** — Implement `metrics/runner.py` exposing `python -m metrics --all` to run V1, M2, M3, M4, M5 in sequence (V1 first per §5 of IMPLEMENTATION_PLAN.md), writing every JSON / CSV under `metrics/output/`. (V1.5, M2.7, M3.6, M4.3, M5.2) ❌
- [ ] **R2.2** — Write a `Makefile` target `make paper-figures` that runs every figure script against the JSON outputs and writes SVG / PDF under `paper_outputs/`. (F1.3, F2.3, F3.3, F4.2, F5.3) ❌
- [ ] **R2.3** — Write `Dockerfile.metrics` pinning Python, Neo4j driver, rdflib, matplotlib, mermaid-cli versions. (P0.4) ❌
- [ ] **R2.4** — End-to-end reproducibility check: fresh container, restore baseline snapshot, run `python -m metrics --all && make paper-figures`, hash-compare outputs against committed versions. Expected: byte-identical SVGs, deterministic JSONs. (R2.1, R2.2, R2.3) ❌
- [ ] **R2.5** — Tag the repo at `paper-submission-v1` once R2.4 passes. (R2.4) ❌

---

## P — Paper integration

- [ ] **P1.1** — Update the methods section of the C7 paper draft with the FAIR scoring rubric and semantic density definition. (M2.1, Q.5) ❌
- [ ] **P1.2** — Insert F1–F5 into the paper at the agreed sections. (F1.4, F2.3, F3.3, F4.2, F5.3) ❌
- [ ] **P1.3** — Insert T1–T4 with `\input{paper_outputs/...}` references. (T1.1, T2.1, T3.1, T4.1) ❌
- [ ] **P1.4** — Cross-check every numeric claim in the paper against the JSON outputs. Flag any "tentative" / "target" number from `c7_unified_contribution.md` that has not been replaced with a measured value. (M2.5, M3.4, M4.3) ❌
- [ ] **P1.5** — Update the limitations section to acknowledge the Gene category gap (consequence of removing C4) explicitly. (M4.3) ❌

---

## TH — Hand-off to thesis

- [ ] **TH.0** — 🆕 Mirror the validity-check report (`outputs/validity_reports/kg_validity_<timestamp>.md`) into the thesis evaluation chapter as evidence of the LPG → KG transition Sultan asked for. (V1.5) ❌
- [ ] **TH.1** — Mirror F3 (FAIR scorecard), F4 (density progression), F5 (alignment matrix) into the thesis with GSU-themed colours. (F3.3, F4.2, F5.3) ❌
- [ ] **TH.2** — Mirror T2 and T3 into the thesis methodology chapter. (T2.1, T3.1) ❌
- [ ] **TH.3** — Update `docs/infrastructure/IMPLEMENTATION_PLAN.md` to mark the metrics-and-visualisation block as complete. (R2.5, P1.5) ❌

---

## Causality (paused — do not remove code)

> Full rationale: [CAUSALITY_NOTE.md](CAUSALITY_NOTE.md).

- [~] **CAU.0** — `steps/step21_extract_causal_features.py` through `steps/step26_dowhy_inference.py` exist; `causal/` directory exists. ⏸️
- [ ] **CAU.1** — All causal `run_*` toggles in `config.yaml` remain `false`. ⏸️
- [ ] **CAU.2** — No deletion of causal code by any task in this list. Cleanup passes must leave `steps/step21*..step26*.py`, `causal/`, and `steps/step25_validate_causal.py` untouched. ⏸️
- [ ] **CAU.3** — Resume after C7 paper submission and thesis defense (post-May 2026). Out of scope for this plan. ⏸️

---

## Notes on what is *not* in this task list

- **No causal-discovery metric tasks.** Causality is paused; see CAUSALITY_NOTE.md.
- **No pipeline performance benchmarks.** Already covered in the IEEE Big Data 2025 paper and `steps/step16_create_metrics.py`.
- **No Gene Ontology integration tasks.** Removed per Hajer's meeting note; documented as a known limitation only.
- **No ontology integration beyond Steps 17–20.** New ontologies are not in scope until C6 (future work, post-June 2026).
- **No edits to existing `docs/final_report/implementation_plan.md` or `task_metrics.md`.** Those are preserved as the historical record. All evolved content is under `c7_plan_v2/`.
