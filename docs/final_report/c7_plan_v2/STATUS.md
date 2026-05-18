# Status Ledger — c7_plan_v2

> **⚠️ Continuation note (2026-05-16).** Defense-prep work continued in [`docs/final_report/c7_plan_v3/`](../c7_plan_v3/) — see [`DEFENSE_TASKS.md`](../c7_plan_v3/DEFENSE_TASKS.md) for the active May-22 checklist and [`history/IMPLEMENTATION_HISTORY_2026-05-16.md`](../c7_plan_v3/history/IMPLEMENTATION_HISTORY_2026-05-16.md) for the May-16 enrichment landing (steps 30/33/34: HPO partial + Biolink + MONDO/DOID; LOINC vitals and MEDHIST Comorbidity remain data-blocked). Backlog items **B-17 partial, B-20, B-21 are now ✅ closed**; **B-18 and B-19 remain ⏸️ pending source-data ingestion**. This file is retained as the May-9 baseline.
>
> **Purpose.** Scannable companion to [TASKS.md](TASKS.md). Every row in TASKS.md falls into one of four buckets below. A row appears here only if it has changed status (e.g. is new or already done) — open work that's "expected to be missing" is not duplicated unless it adds clarity.
>
> **Last reviewed.** 2026-05-09 (matches conversation date).

---

## ✅ Completed (already in the repo — do not duplicate)

| ID | Item | Evidence | Status note |
|---|---|---|---|
| step17 | 12 uniqueness constraints + 15 indexes | `steps/step17_apply_constraints.py` | Idempotent via `IF NOT EXISTS` |
| step18 | Ontology code properties on data nodes | `steps/step18_add_ontology_properties.py` | Sets `snomed_code`, `loinc_code`, `uberon_code`, `icd10_code`, `mondo_code`, `rdf_type`, `source_ontology`, plus `uri` on rels. **Does not** set `source_table` / `source_column` (corrected from earlier draft). |
| step19 | ICD-10 `:OntologyConcept` nodes + `IS_A`, `CLASSIFIED_AS` | `steps/step19_icd10_integration.py` | WHO REST API + offline JSON fallback |
| step20 | SNOMED / LOINC / UBERON / HPO `:OntologyConcept` + `MAPS_TO` + `IS_A` | `steps/step20_ontology_layer.py` | 47 concept nodes, ~100k MAPS_TO edges |
| M4.0 | AlzKB CYPHERL ingestion + `:AlzKBConcept` + `:SAME_AS` | `steps/step24_alzkb_bridge.py` | The C7 alignment metric **extends** this; does not re-implement |
| step29 | 15 EDA figures + 3 Mermaid diagrams | `steps/step29_kg_eda.py`, `outputs/eda_figures/` | New figures must visibly differ — see IMPLEMENTATION_PLAN.md §7.1 |
| util | `Neo4jConnector` reusable connector | `utils/neo4j_connector.py` | All metric scripts reuse this; no new connection helper |
| util | `DataValidator` with 381_S_ exclusion | `utils/batch_processor.py` | Validity assertion A7 reuses this |
| util | Quality-aware logging | `utils/quality_aware_logger.py` | Metric scripts adopt the same convention |
| test | Idempotency tests | `tests/test_idempotency.py` | Pattern reused by new metric tests |
| step16 | Cypher query performance metrics | `steps/step16_create_metrics.py` | **Not** FAIR / density. Naming is historical; out of scope for this plan |

---

## ❌ Missing (to be built — full task list in [TASKS.md](TASKS.md))

| Module | Files | Owning task |
|---|---|---|
| Validity gate | `metrics/validity.py`, `metrics/validity_rubric.yaml` | V1.* |
| FAIR scorer | `metrics/fair.py`, `metrics/fair_principles.yaml` | M2.* |
| Semantic density | `metrics/semantic_density.py` | M3.* |
| AlzKB alignment | `metrics/alzkb_alignment.py` | M4.* |
| Step audit | `metrics/step_audit.py` | M5.* |
| Snapshots | `metrics/snapshots.py` | M1.0 |
| Runner | `metrics/runner.py` (`python -m metrics --all`) | R2.1 |
| Figures | `figures/f1_dependency.py` … `figures/f5_alignment.py` | F1–F5 |
| Mappings | `ontology/mappings/` directory + per-source CSVs + `index.csv` | R1.* |
| Tests | `tests/test_validity.py`, `test_fair.py`, `test_semantic_density.py`, `test_alzkb_alignment.py`, `test_column_to_concept.py` | V1.4, M2.3, M3.2, M4.*, R1.5 |
| Fixtures | `tests/fixtures/mini_kg.cypher` | V1.3 |
| Build | `Dockerfile.metrics`, `requirements-metrics.txt`, `Makefile` paper-figures target | P0.4, R2.2, R2.3 |
| Snapshots data | `data/snapshots/post_steps_17_20.dump` + per-step intermediates | M1.1, M1.3 |
| Validity reports | `outputs/validity_reports/kg_validity_<timestamp>.{json,md}` | V1.5 |

---

## 🆕 Added in this revision (vs `task_metrics.md`)

These are net-new items introduced by the c7_plan_v2 documents — they were not in the original `implementation_plan.md` / `task_metrics.md`.

| ID | Item | Why it was added |
|---|---|---|
| Q.6 | Validity-rubric threshold approval gate | Sultan's feedback requires a formal validity check; thresholds need her sign-off |
| Q.7 | Snapshot downtime scheduling with Özgün | Offline `neo4j-admin` dump strategy needs a coordination slot |
| V1.* (six tasks) | KG validity gate implementation + tests + reporting | Sultan's gate; precedes all metric work |
| TH.0 | Mirror validity report into thesis | Sultan asked for the KG-converted state in the progress report / thesis |
| M1.0 | `metrics/snapshots.py` wrapper for `neo4j-admin` | Original plan referenced snapshots without owning a tool |
| P0.5 / R1.0 | Create `ontology/mappings/` directory | Original plan referenced it as if it existed; it does not |
| F2.3 / F4.1 (guardrail) | Banned-overlap notes vs `outputs/eda_figures/15_*` and `10_*` | Step 29 already produces overlapping-looking figures |
| STATUS.md | This ledger | User asked for a status doc |
| CAUSALITY_NOTE.md | Paused-but-retained note | User asked for a causality status reminder |
| `c7_plan_v2/` folder | Versioned plan folder | User asked to preserve old documents |

---

## ⏸️ Paused (do not remove — see [CAUSALITY_NOTE.md](CAUSALITY_NOTE.md))

| File / item | What it does | Status |
|---|---|---|
| `steps/step21_extract_causal_features.py` | Extract features for causal discovery | Code retained, not run |
| `steps/step22_causal_discovery.py` | PC / FCI / GES / DAG-GNN | Code retained, not run |
| `steps/step23_embed_causal_edges.py` | Embed discovered causal edges back into the KG | Code retained, not run |
| `steps/step24_alzkb_bridge.py` | AlzKB `:AlzKBConcept` + `:SAME_AS` | **Active** — used by M4.* (does not pause) |
| `steps/step25_validate_causal.py` | Validate causal edges against literature ground truth | Code retained, not run |
| `steps/step26_dowhy_inference.py` | DoWhy refutation tests | Code retained, not run |
| `causal/` directory | Supporting causal modules | Retained |
| `config.yaml` causal toggles | `run_causal_*` flags | Default `false`, not flipped |

> Note: step 24 is **not** paused. It is part of the active C7 alignment work — the `:AlzKBConcept` / `:SAME_AS` outputs are the data source for `metrics/alzkb_alignment.py`.

---

## Summary by bucket

| Bucket | Count |
|---|---|
| ✅ Completed (anchors) | 11 modules / artefacts |
| ❌ Missing (work) | 13 modules / files |
| 🆕 Added (vs original) | 9 items |
| ⏸️ Paused | 7 step files + causal/ + config toggles |

When this ledger is mirrored into the thesis or the progress report, only the ✅ and ⏸️ buckets need narrative explanation; the ❌ bucket reduces to "the metrics-and-validity work in TASKS.md".
