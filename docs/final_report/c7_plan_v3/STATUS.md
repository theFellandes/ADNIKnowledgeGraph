# Status Ledger — c7_plan_v3

> **Purpose.** Scannable companion to [TASKS.md](TASKS.md). Each row in TASKS.md falls into one of the buckets below.
> **Last reviewed.** 2026-05-16 (plan-write date — to be bumped on each execution session).
> **Reading order.** Skim ✅ first to know what's already done; then ❌ to know what's left; then 🆕 to know what v3 added vs v2.

---

## ✅ Completed (already in the repo — do not duplicate)

| ID | Item | Evidence | Status note |
|---|---|---|---|
| step17 | 12 uniqueness constraints + 15 indexes | `steps/step17_apply_constraints.py` | Idempotent via `IF NOT EXISTS` |
| step18 | Ontology code properties on data nodes | `steps/step18_add_ontology_properties.py` | Sets `snomed_code`, `loinc_code`, `uberon_code`, `icd10_code`, `mondo_code`, `rdf_type`, `source_ontology`, plus `uri` on rels |
| step19 | ICD-10 `:OntologyConcept` nodes + `IS_A`, `CLASSIFIED_AS` | `steps/step19_icd10_integration.py` | WHO REST API + offline JSON fallback |
| step20 | SNOMED / LOINC / UBERON / HPO `:OntologyConcept` + `MAPS_TO` + `IS_A` | `steps/step20_ontology_layer.py` | ~47 concept nodes, ~100k MAPS_TO edges |
| step24 | AlzKB CYPHERL ingestion + `:AlzKBConcept` + `:SAME_AS` | `steps/step24_alzkb_bridge.py` | C7 alignment metric **extends** this; does not re-implement |
| step28 | Thesis-specific figures | `steps/step28_thesis_figures.py` | |
| step29 | 15 EDA figures + 3 Mermaid diagrams | `steps/step29_kg_eda.py`, `outputs/eda_figures/` | New figures must visibly differ — see IMPLEMENTATION_PLAN §6 |
| metrics.fair | FAIR scorer | `metrics/fair.py` + `metrics/fair_principles.yaml` | 13 principles, 3-level rubric |
| metrics.density | Semantic density | `metrics/semantic_density.py` | node + edge URI coverage per label/type |
| metrics.validity | 7-assertion validity gate | `metrics/validity.py` + `metrics/validity_rubric.yaml` | Per [c7_plan_v2/VALIDITY_CHECK_SPEC.md](../c7_plan_v2/VALIDITY_CHECK_SPEC.md) |
| metrics.snapshots | Offline dump/load wrapper | `metrics/snapshots.py` | Wraps `neo4j-admin database dump` |
| metrics.reconcile | Canonical Cypher snapshot | `metrics/reconcile.py` | Single-transaction in-process counts |
| metrics.alzkb | AlzKB alignment scorer | `metrics/alzkb_alignment.py` | Reads `:AlzKBConcept` + `:SAME_AS` |
| metrics.step_audit | Per-step diff helper | `metrics/step_audit.py` | Needs wiring to per-step snapshots (P2.8) |
| metrics.runner | `python -m metrics --all` | `metrics/runner.py` + `metrics/__main__.py` | Orchestrates validity → density → FAIR → alignment → audit |
| metrics.thesis_report | Thesis MD generator | `metrics/thesis_report.py` | |
| metrics.thesis_pdf | Thesis PDF generator | `metrics/thesis_pdf.py` | reportlab + svglib |
| figures.style | GSU palette | `figures/_style.py` | |
| figures.mermaid | Mermaid → SVG | `figures/_mermaid.py` | |
| figures.f1 | Functional dependency diagram | `figures/f1_dependency.py` → `paper_outputs/f1_dependency.{svg,png,mmd}` | |
| figures.f2 | Schema before/after | `figures/f2_schema.py` → `paper_outputs/f2_schema.{svg,png,mmd}` | |
| figures.f3 | FAIR scorecard | `figures/f3_fair.py` → `paper_outputs/f3_fair.{svg,pdf,png}` | |
| figures.f5 | AlzKB alignment matrix | `figures/f5_alignment.py` → `paper_outputs/f5_alignment.{svg,pdf,png}` | |
| util.neo4j | Reusable connector | `utils/neo4j_connector.py` | All metric scripts reuse this |
| util.validator | `DataValidator` with 381_S_ exclusion | `utils/batch_processor.py` | Validity assertion A7 reuses this |
| util.logger | Quality-aware logging | `utils/quality_aware_logger.py` | Metric scripts adopt the same convention |
| tests | Existing test suite | `tests/test_{validity,fair,semantic_density,alzkb_alignment,step_audit,snapshots,runner,column_to_concept,figures,idempotency}.py` + fixtures | Add tests as Phase 3 lands |

---

## ⚠️ Partial — needs verification or finishing in v3

| ID | Item | Owning task | Why partial |
|---|---|---|---|
| F4 figure | `figures/f4_density.py` exists; no SVG/PDF committed | P2.9 | Needs `semantic_density_per_step.json` which needs per-step snapshots |
| Per-step snapshots | None captured yet | P2.2 / P2.4 / P2.5 | Awaiting Q.7 (Özgün downtime) |
| Step audit deltas | `step_audit.py` exists; `step_audit.csv` not generated | P2.8 | Needs P2.7 per-step deltas |
| Canonical-snapshot reconciliation | Older docs disagree on visit count / LOINC coverage / concept count | A0.2 / A0.3 | Run `python -m metrics --all` once and re-source |
| AlzKB SAME_AS coverage | Step 24 ran but counts not documented in canonical snapshot | A0.4 | Audit + re-run if empty |

---

## ❌ Missing — must be built (full task list in [TASKS.md](TASKS.md))

| Module / artefact | Files | Owning task |
|---|---|---|
| Sultan progress-report renderer | `metrics/validity.py::render_progress_report()` | S1.2 |
| Phase 0 audit document | `docs/final_report/c7_plan_v3/AUDIT_2026-05-16.md` | A0.3 |
| Rollback Cypher | `metrics/scripts/rollback_steps_17_20.cypher` | P2.3 |
| Snapshots data | `data/snapshots/*.dump` × 6 | P2.2 / P2.4 / P2.5 |
| Per-step metric JSONs | `metrics/output/{fair,semantic_density,alzkb_alignment}_per_step.json` | P2.6 / P2.7 |
| Step-audit CSV | `metrics/output/step_audit.csv` | P2.8 |
| F4 rendered | `paper_outputs/f4_density.{svg,pdf,png}` | P2.9 |
| Re-render F1/F2/F3/F5 | `paper_outputs/{f1,f2,f3,f5}.*` (refreshed timestamps) | P2.10 / P4.3 / P4.4 |
| Makefile / PS1 | `scripts/make_paper_figures.{sh,ps1}` | P2.11 |
| Hook / CI | pre-commit or CI workflow | P2.12 |
| **B-17 HPO expansion step** | `steps/step30_hpo_expansion.py` | P3.10 |
| **B-18 LOINC vitals step** | `steps/step31_loinc_vital_signs.py` | P3.20 |
| **B-19 MEDHIST comorbidity step** | `steps/step32_medhist_comorbidity.py` | P3.30 |
| **B-20 Biolink categories step** | `steps/step33_biolink_categories.py` | P3.40 |
| **B-21 MONDO/DOID wiring step** | `steps/step34_mondo_doid_wiring.py` | P3.50 |
| HPO cache | `ontology/hpo_concepts_cache.json` | P3.11 |
| Mappings | `ontology/mappings/*.csv` × 7 + `index.csv` | P3.3 |
| Per-step tests | `tests/test_step{30..34}.py` | P3.2 |
| AlzKB version pin | `data/alzkb/<version>/alzkb.cypherl` | Q.4 / P4.1 |
| Paper tables | `paper_outputs/t{1..4}.tex` | T1.1 / T2.1 / T3.1 / T4.1 |
| Thesis patches | LaTeX edits in `Thesis/OğuzhanGüngör_Tez (1)/*.tex` + `Thesis/Article/article.tex` | TH.1–TH.13 |

---

## 🆕 Added in v3 (vs v2)

These are net-new items vs `c7_plan_v2/TASKS.md`.

| ID | Item | Why added |
|---|---|---|
| Q.8 | Hajer scope confirmation for B-17 to B-21 closure | User decided full closure (not deferral) on 2026-05-16 |
| Q.9 | Hajer Biolink-class ambiguity sign-off | B-20 has ~5 ambiguous node-type mappings |
| A0.1 – A0.5 | Phase 0 audit + reconciliation | Counts disagree across documents; need single source of truth |
| S1.* | Polished Sultan progress-report | Sultan's Turkish-language feedback requires KG-state demonstration |
| P3.10 / P3.20 / P3.30 / P3.40 / P3.50 | B-17 to B-21 step implementations | Contribution-table promises now in scope |
| P3.3 / P3.4 | Mapping CSVs + validity rubric extension | Reproducibility supplementary + 7-source recognition |
| P3.5 / P3.6 | Per-enrichment-step snapshots + re-run | Per-step delta reporting consistency |
| P4.* | Re-measure on enriched graph | After Phase 3, all metrics shift |
| TH.* (13 tasks) | Thesis patches | User explicit: "patch the thesis after we implement" |
| R6.3 / R6.4 | Master docs + memory update | New steps 30–34 need to be discoverable for next session |
| README, STATUS, IMPLEMENTATION_PLAN, TASKS, VALIDITY_PROGRESS_REPORT_SPEC, GAP_CLOSURE_SPEC, THESIS_PATCH_PLAN | Seven v3 planning documents | User asked for "good IMPLEMENTATION_PLAN.md, TASKS.md and documents like these" |

---

## ⏸️ Paused (do not remove — see [c7_plan_v2/CAUSALITY_NOTE.md](../c7_plan_v2/CAUSALITY_NOTE.md))

| File / item | What it does | Status |
|---|---|---|
| `steps/step21_extract_causal_features.py` | Extract features for causal discovery | Code retained, not run |
| `steps/step22_causal_discovery.py` | PC / FCI / GES / DAG-GNN | Code retained, not run |
| `steps/step23_embed_causal_edges.py` | Embed discovered causal edges back into the KG | Code retained, not run |
| `steps/step24_alzkb_bridge.py` | AlzKB `:AlzKBConcept` + `:SAME_AS` | **Active** — used by P4.* (does not pause) |
| `steps/step25_validate_causal.py` | Validate causal edges against literature ground truth | Code retained, not run |
| `steps/step26_dowhy_inference.py` | DoWhy refutation tests | Code retained, not run |
| `causal/` directory | Supporting causal modules | Retained |
| `config.yaml` causal toggles | `run_causal_*` flags | Default `false`, not flipped |

> Note: step 24 is **not** paused. It is part of the active C7 alignment work — the `:AlzKBConcept` / `:SAME_AS` outputs are the data source for `metrics/alzkb_alignment.py`.

---

## Summary by bucket

| Bucket | Count |
|---|---|
| ✅ Completed (anchors) | 26 modules / artefacts |
| ⚠️ Partial | 5 items |
| ❌ Missing (work to do) | ~30 modules / files |
| 🆕 Added (vs v2) | 12 + 13 thesis tasks |
| ⏸️ Paused | 6 step files + `causal/` + config toggles |

When this ledger is mirrored into the thesis or the progress report, only the ✅ and ⏸️ buckets need narrative explanation; the ❌ bucket reduces to "the gap-closure + thesis-patch work in [TASKS.md](TASKS.md)".

---

## Update protocol

After each execution session:

1. Flip task statuses in this file (move ❌ rows up to ⚠️ → ✅).
2. Bump "Last reviewed" at the top.
3. If a new task surfaces, add it to [TASKS.md](TASKS.md) first, then mirror its status here.
4. Do not edit closed historical entries (preserve the trail).
