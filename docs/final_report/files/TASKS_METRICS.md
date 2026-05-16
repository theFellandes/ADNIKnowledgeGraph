# Tasks — Metrics, Graphs, and Visualizations

> **Purpose.** Granular, resumable task list for the metrics and visualisation work that backs the C7 paper. Every task has an ID, a verification command, and a dependency note. **No scripts are written by completing this task list — these tasks are the *plan* for that work; the work itself happens in a follow-up session once Sultan and Özgün approve the plan.**
>
> **Convention.**
> - `[ ]` = open, `[x]` = done.
> - IDs prefixed `M*` for metrics, `F*` for figures, `T*` for tables, `R*` for reproducibility, `P*` for paper integration, `Q*` for quality / approval gates.
> - Each task lists its dependencies in parentheses after the description.

---

## Quality / approval gates (do these first)

- [ ] **Q.1** — Walk through `IMPLEMENTATION_PLAN_METRICS.md` and `C7_UNIFIED_CONTRIBUTION.md` with Asst. Prof. Özgün Pınarer and Dr. Sultan Nezihe Turhan. Capture revisions in `meeting_notes/`. (no deps)
- [ ] **Q.2** — Send the revised plan to Dr. Hajer Baazaoui for the FAIR / semantic density additions and the column-to-concept reproducibility table. Wait for confirmation. (Q.1)
- [ ] **Q.3** — Per Hajer's note, the baseline is the pre-enrichment CauAD graph (rollback of Steps 17–20 on a copy). Confirm the rollback strategy with Özgün and document the decision in `metrics/BASELINE_DECISION.md`. (Q.1)
- [ ] **Q.4** — Pin the AlzKB RDF dump version to use; archive the exact file in `data/alzkb/<version>/`. (Q.1)
- [ ] **Q.5** — Confirm the FAIR scoring rubric (binary vs three-level, scoring sheet structure) with Hajer before any code is written. (Q.2)

---

## Pre-flight infrastructure

- [ ] **P0.1** — Verify Neo4j 5.x connectivity from a clean shell: `cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "RETURN 1"`. (Q.1)
- [ ] **P0.2** — Confirm `headers.json` and the `ontology/mappings/` directory exist and are readable. (Q.1)
- [ ] **P0.3** — Create the directory tree from the plan: `mkdir -p metrics/ figures/ tests/fixtures/ paper_outputs/`. (Q.1)
- [ ] **P0.4** — Create `requirements-metrics.txt` with the metric/figure dependencies (neo4j, rdflib, pandas, matplotlib, seaborn, graphviz, mermaid-cli). (Q.1)

---

## Baseline snapshot (foundation for all metrics)

- [ ] **M1.1** — Snapshot the current Neo4j graph using `neo4j-admin database dump`. Store in `data/snapshots/post_steps_17_20.dump`. (Q.3, P0.1)
- [ ] **M1.2** — Restore the dump into a separate Neo4j instance, then run a `metrics/scripts/rollback_steps_17_20.cypher` script to remove the property additions and OntologyConcept nodes introduced by Steps 17–20. Output: `data/snapshots/pre_steps_17_20.dump`. (M1.1, Q.3)
- [ ] **M1.3** — Take an intermediate snapshot after each individual step (17, 18, 19, 20). Output: `data/snapshots/post_step_{17,18,19,20}.dump`. Used by per-step audits below. (M1.2)

---

## FAIR scoring

- [ ] **M2.1** — Write `metrics/fair_principles.yaml` with one entry per FAIR principle (F1, F2, F3, F4, A1.1, A1.2, A2, I1, I2, I3, R1.1, R1.2, R1.3) and a check description per principle. The structure follows the rubric agreed in Q.5. (Q.5)
- [ ] **M2.2** — Write `metrics/fair.py` that reads the YAML, runs the corresponding check (Cypher query, file presence check, or manual-flag review), produces a JSON output. (M2.1, P0.3)
- [ ] **M2.3** — Add unit tests in `tests/test_fair.py` against a synthetic 10-node fixture where each principle's expected score is known by hand. (M2.2)
- [ ] **M2.4** — Run on baseline snapshot. Output: `metrics/output/fair_score_baseline.json`. (M2.3, M1.2)
- [ ] **M2.5** — Run on post-Steps-17–20 snapshot. Output: `metrics/output/fair_score_post.json`. (M2.3, M1.1)
- [ ] **M2.6** — Run on each intermediate snapshot. Aggregate into `metrics/output/fair_score_per_step.json`. (M2.3, M1.3)
- [ ] **M2.7** — Compute per-step FAIR deltas, write to `metrics/output/fair_delta_per_step.json`. (M2.6)

---

## Semantic density

- [ ] **M3.1** — Write `metrics/semantic_density.py` computing node URI coverage and edge URI coverage, broken down per node label and per edge type, plus the aggregate. (P0.3)
- [ ] **M3.2** — Add unit tests in `tests/test_semantic_density.py` against the same fixture used for FAIR. (M3.1)
- [ ] **M3.3** — Run on baseline. Output: `metrics/output/semantic_density_baseline.json`. (M3.2, M1.2)
- [ ] **M3.4** — Run on post-Steps-17–20 snapshot. Output: `metrics/output/semantic_density_post.json`. (M3.2, M1.1)
- [ ] **M3.5** — Run on each intermediate snapshot. Aggregate into `metrics/output/semantic_density_per_step.json`. (M3.2, M1.3)
- [ ] **M3.6** — Compute per-step density deltas, write to `metrics/output/density_delta_per_step.json`. (M3.5)

---

## AlzKB alignment

- [ ] **M4.1** — Download AlzKB RDF dump (version pinned in Q.4) into `data/alzkb/<version>/alzkb.ttl`. (Q.4)
- [ ] **M4.2** — Write `metrics/alzkb_alignment.py` that loads the AlzKB dump with rdflib, extracts the four in-scope category indexes (Disease/DOID, Anatomy/UBERON, Phenotype/HPO, Gene/NCBI Gene), and matches against MAKO `OntologyConcept` URIs. (M4.1, P0.3)
- [ ] **M4.3** — Run on the post-Steps-17–20 snapshot. Output: `metrics/output/alzkb_alignment.json`. Include a Gene row with explicit `not_implemented: true` flag and a docstring pointer to the future-work section. (M4.2, M1.1)
- [ ] **M4.4** — Materialise the alignment edges back into the post-snapshot as `(:Diagnosis)-[:SAME_AS_ALZKB]->(:AlzKBEntity)` etc. for downstream traversal. (M4.3)

---

## Step audit (engineering metrics)

- [ ] **M5.1** — Write `metrics/step_audit.py` that, for each migration step, reports nodes touched, edges added, properties added, runtime in seconds. Combines log-parsing of the existing step scripts with diff-based Cypher counts on the snapshot pairs. (M1.3)
- [ ] **M5.2** — Output: `metrics/output/step_audit.csv` with columns `step, nodes_touched, edges_added, properties_added, runtime_s, fair_delta_overall, density_delta_node, density_delta_edge`. The FAIR and density columns are joined in from M2.7 and M3.6. (M5.1, M2.7, M3.6)

---

## Column-to-concept mapping (reproducibility artefact for Step C)

- [ ] **R1.1** — Inventory every column-to-concept mapping currently used by Steps 18 and 20. One source-column per row. (P0.3)
- [ ] **R1.2** — Write each mapping as a CSV under `ontology/mappings/`, one CSV per source table (`adsxlist_to_hpo.csv`, `medhist_to_snomed.csv`, `vitals_to_loinc.csv`, etc.). (R1.1)
- [ ] **R1.3** — Each CSV row contains: `source_table, source_column, source_value_pattern, target_ontology, target_uri, target_label, mapping_rule, test_fixture_id, last_verified_date`. (R1.2)
- [ ] **R1.4** — Build a top-level `ontology/mappings/index.csv` consolidating all CSVs into one master file for the paper's supplementary material. (R1.2, R1.3)
- [ ] **R1.5** — Add a `tests/test_column_to_concept.py` that loads each CSV, applies the rule to the test fixture, and asserts the expected target URI. (R1.3)

---

## Figures

### F1 — Functional dependency diagram (revised)

- [ ] **F1.1** — Sketch the new layout: C7 at centre, Steps A–D feeding in from the left and bottom, C6 (future work) on the right, the dropped C4 box shown faded as "removed". (Q.1)
- [ ] **F1.2** — Implement in Mermaid in `figures/f1_dependency.mmd`. (F1.1)
- [ ] **F1.3** — Render to SVG and PDF: `mmdc -i f1_dependency.mmd -o paper_outputs/f1_dependency.svg`. (F1.2)
- [ ] **F1.4** — Verify the figure renders correctly in the paper LaTeX preview. (F1.3)

### F2 — Schema before / after

- [ ] **F2.1** — Render the pre-Steps-17–20 schema as a Graphviz diagram from the baseline snapshot. (M1.2 or M1.3)
- [ ] **F2.2** — Render the post-Steps-17–20 schema (including the `OntologyConcept` layer) the same way. (M1.1)
- [ ] **F2.3** — Side-by-side composition in `paper_outputs/f2_schema.svg`. Same node positioning where possible to make the diff visually obvious. (F2.1, F2.2)

### F3 — FAIR scorecard

- [ ] **F3.1** — Write `figures/f3_fair.py` reading `fair_score_baseline.json` and `fair_score_post.json`, producing a per-principle bar chart or heatmap with two bars per principle (baseline vs post). 13 FAIR principles on the x-axis, score on the y-axis. (M2.4, M2.5)
- [ ] **F3.2** — Apply the GSU palette (dark blue / pink accent) for the thesis version; produce a separate greyscale-friendly version for the journal paper. (F3.1)
- [ ] **F3.3** — Output: `paper_outputs/f3_fair.svg` and `f3_fair.pdf`. (F3.2)

### F4 — Semantic density progression

- [ ] **F4.1** — Write `figures/f4_density.py` reading `semantic_density_per_step.json`. Produce a stacked area chart (or waterfall) showing node URI coverage and edge URI coverage growing per step. Each step on the x-axis: pre, post-17, post-18, post-19, post-20. (M3.5, M3.6)
- [ ] **F4.2** — Output: `paper_outputs/f4_density.svg`. (F4.1)

### F5 — AlzKB alignment matrix

- [ ] **F5.1** — Write `figures/f5_alignment.py` reading `alzkb_alignment.json`, producing a 4 × 2 heatmap (categories × pre/post) with cell shading for none / weak / strong, plus the strong-match count as cell text. (M4.3)
- [ ] **F5.2** — Mark the Gene row visually distinct ("N/A — see Future Work") so reviewers cannot misread it as a measured zero. (F5.1)
- [ ] **F5.3** — Output: `paper_outputs/f5_alignment.svg`. (F5.2)

---

## Tables

- [ ] **T1.1** — Take the existing ontology / tool / standard assessment summary table from the contribution document and trim it to fit a single-page paper table. Final form in `paper_outputs/t1_assessment.tex` (LaTeX `tabular`). (Q.1)
- [ ] **T2.1** — Generate `paper_outputs/t2_step_audit.tex` from `step_audit.csv` via a small Pandas-to-LaTeX shim. (M5.2)
- [ ] **T3.1** — Generate `paper_outputs/t3_column_to_concept.tex` from `ontology/mappings/index.csv`, paginated to fit the supplementary material section. (R1.4)
- [ ] **T4.1** — Generate `paper_outputs/t4_alignment.tex` from `alzkb_alignment.json`. (M4.3)

---

## Reproducibility

- [ ] **R2.1** — Write a top-level `metrics/runner.py` exposing `python -m metrics --all` to run M2, M3, M4, M5 in one shot, writing every JSON / CSV under `metrics/output/`. (M2.7, M3.6, M4.3, M5.2)
- [ ] **R2.2** — Write a `Makefile` target `make paper-figures` that runs every figure script against the JSON outputs and writes SVG / PDF under `paper_outputs/`. (F1.3, F2.3, F3.3, F4.2, F5.3)
- [ ] **R2.3** — Write a `Dockerfile.metrics` pinning Python, Neo4j driver, rdflib, matplotlib, mermaid-cli versions. (P0.4)
- [ ] **R2.4** — End-to-end reproducibility check: fresh container, restore baseline snapshot, run `python -m metrics --all && make paper-figures`, hash-compare the outputs against the committed versions. Expected: byte-identical SVGs, deterministic JSONs. (R2.1, R2.2, R2.3)
- [ ] **R2.5** — Tag the repo at `paper-submission-v1` once R2.4 passes. (R2.4)

---

## Paper integration

- [ ] **P1.1** — Update the methods section of the C7 paper draft with the FAIR scoring rubric and the semantic density definition. (M2.1, Q.5)
- [ ] **P1.2** — Insert F1–F5 into the paper at the agreed sections. (F1.4, F2.3, F3.3, F4.2, F5.3)
- [ ] **P1.3** — Insert T1–T4 with `\input{paper_outputs/...}` references. (T1.1, T2.1, T3.1, T4.1)
- [ ] **P1.4** — Cross-check every numeric claim in the paper against the JSON outputs. Flag any "tentative" or "target" number from the contribution document that has not been replaced with a measured value. (M2.5, M3.4, M4.3)
- [ ] **P1.5** — Update the limitations section to acknowledge the Gene category gap (consequence of removing the original C4) explicitly. (M4.3)

---

## Hand-off to thesis

- [ ] **TH.1** — Mirror F3 (FAIR scorecard), F4 (density progression), F5 (alignment matrix) into the thesis with GSU-themed colours. (F3.3, F4.2, F5.3)
- [ ] **TH.2** — Mirror T2 and T3 into the thesis methodology chapter. (T2.1, T3.1)
- [ ] **TH.3** — Update `IMPLEMENTATION_PLAN.md` to mark the metrics-and-visualisation block as complete. (R2.5, P1.5)

---

## Notes on what is *not* in this task list

- No causal-discovery metric tasks. Causality is not in C7.
- No pipeline performance benchmarks. Already covered in the IEEE Big Data 2025 paper.
- No Gene Ontology integration tasks. Removed per Hajer's meeting notes; documented as a known limitation only.
- No ontology integration beyond Steps 17–20 work already implemented. New ontologies are not in scope until C6 (future work, after June 2026).
