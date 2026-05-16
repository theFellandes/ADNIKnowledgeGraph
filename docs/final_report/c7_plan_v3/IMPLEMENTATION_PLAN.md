# Implementation Plan — MAKO Finishing (v3)

> **Plan ID.** `mako-c7-finishing-2026-05-16`
> **Project.** MAKO — Multimodal Alzheimer's Knowledge graph with Ontology grounding (formerly CauAD)
> **Working dir.** `D:\Programming\Python\ADNIKnowledgeGraph`
> **Thesis defense.** May 2026, Galatasaray University
> **Status.** Planning approved 2026-05-16; awaiting Sultan / Özgün / Hajer sign-off on §8 items before Phase 3.
>
> **Supersedes.** [c7_plan_v2/IMPLEMENTATION_PLAN.md](../c7_plan_v2/IMPLEMENTATION_PLAN.md). Open work items from v2 are re-numbered into v3's six-phase structure. Already-done items are marked ✅ in [STATUS.md](STATUS.md).

---

## 1. Context

The MAKO project has three deliverables converging on May–June 2026 and a fourth in the pipeline:

1. **Sultan's progress-report artifact.** Per her Turkish-language feedback (*"Bu ilerleme raporuna metrikleri koymasan bile hiç olmazsa ontolojileri bitirip graphın KG haline dönüşmüş halini koymak lazım"*) — even if metrics aren't included, the KG-converted state of the graph must be demonstrable. Anchored by `metrics/validity.py`'s seven-assertion gate.
2. **C7 paper.** Working title: *"A three-axis framework for ontology-guided enrichment of multimodal clinical knowledge graphs: application to Alzheimer's disease."* Backed by FAIR + semantic density + AlzKB alignment metrics. **OntoQA is dropped** per Hajer's Friday meeting decision.
3. **Thesis.** *"Ontology-Driven Construction of a Knowledge Graph from Multimodal Medical Data."* MSc, GSU. Already uses MAKO naming + FAIR/semantic density; contains placeholder measurements from a 2026-05-09 snapshot.
4. **Future (post-June 2026).** C6 comparative benchmark + causal-discovery resumption — not in scope for this plan.

**The "we said we'd do it" promise.** [Contribution_Table_updated HB.pdf](file:///C:/Users/Fellandes/Downloads/Contribution_Table_updated%20HB.pdf) explicitly commits to five enrichment items that are **not yet implemented**: HPO expansion (5→30 concepts), LOINC vital signs (6 new codes), MEDHIST comorbidity nodes, MONDO/DOID concept wiring, and Biolink Model alignment. Per user decision, this plan closes all five, then patches the thesis to reflect the post-enrichment state.

**The "what's already done" anchor.** Substantial code exists and must be preserved (do NOT rewrite — extend):

| Module | Path | What it does |
|---|---|---|
| FAIR scorer | `metrics/fair.py` + `metrics/fair_principles.yaml` | 13 principles, 3-level rubric, aggregate ~0.92 |
| Semantic density | `metrics/semantic_density.py` | node-URI + edge-URI coverage per label/type |
| Validity gate | `metrics/validity.py` + `metrics/validity_rubric.yaml` | 7 assertions (A1–A7) per [c7_plan_v2/VALIDITY_CHECK_SPEC.md](../c7_plan_v2/VALIDITY_CHECK_SPEC.md) |
| Snapshots | `metrics/snapshots.py` | wraps `neo4j-admin database dump/load` |
| Reconcile | `metrics/reconcile.py` | canonical in-process Cypher snapshot |
| AlzKB alignment | `metrics/alzkb_alignment.py` | reads `:AlzKBConcept` + `:SAME_AS` from step 24 |
| Step audit | `metrics/step_audit.py` | per-step nodes/edges/properties diff |
| Runner | `metrics/runner.py` + `metrics/__main__.py` | `python -m metrics --all` orchestrator |
| Thesis report/PDF | `metrics/thesis_report.py`, `metrics/thesis_pdf.py` | markdown + reportlab PDF |
| Figures F1, F2, F3, F5 | `figures/f{1,2,3,5}_*.py` | rendered to `paper_outputs/` |
| Figure F4 | `figures/f4_density.py` | **code exists; no SVG/PDF committed yet** |
| Style | `figures/_style.py`, `figures/_mermaid.py` | GSU palette + Mermaid pipeline |
| Tests | `tests/test_{validity,fair,semantic_density,alzkb_alignment,step_audit,snapshots,runner,column_to_concept,figures}.py` | broad coverage |

So this plan is **finishing**, not **starting from zero**.

---

## 2. Goals (three parallel tracks)

| Track | Owner | Deliverable | Target milestone |
|---|---|---|---|
| **T-Sultan** | Oğuzhan + Sultan review | `outputs/validity_reports/kg_validity_progress_report.md` (+ PDF) — polished, with KG-state summary + per-ontology completeness; suitable for direct insertion into the next progress report | Sultan's next meeting |
| **T-Paper** | Oğuzhan + Hajer review | `paper_outputs/{f1..f5}.{svg,pdf}` + `t1..t4.tex` tables + paper methods text update | C7 paper submission (post-thesis) |
| **T-Thesis** | Oğuzhan + Özgün review | Updated `Thesis/OğuzhanGüngör_Tez (1)/*.tex` chapters 3.10, 4.3–4.6, 5.3–5.4 with measured values + validity report + new figures | Defense May 2026 |

**Shared substrate.**
- `metrics/output/canonical_snapshot.json` (produced by `metrics/reconcile.py`) — every number in every deliverable traces back here.
- `outputs/validity_reports/kg_validity_<ts>.json` — machine-readable validity result; every reference cites the timestamp.

---

## 3. Current state audit (what's done vs missing)

See [STATUS.md](STATUS.md) for the full ledger. Brief:

### ✅ Done — preserve and reuse
- All migration steps 17–20 + step 24 (AlzKB) + step 28 (thesis figures) + step 29 (15 EDA figures in `outputs/eda_figures/`).
- The `metrics/` package per §1 table.
- F1, F2, F3, F5 figures committed to `paper_outputs/`.
- Utilities: `utils/neo4j_connector.py`, `utils/batch_processor.py` (with `DataValidator.validate_ptid` for `381_S_` exclusion), `utils/quality_aware_logger.py`.
- All `c7_plan_v2/*` planning documents (historical reference).

### ⚠️ Partial — needs verification or finishing
- **F4 figure** rendered SVG/PDF not yet committed (code at `figures/f4_density.py` exists). Requires `semantic_density_per_step.json` which requires per-step snapshots.
- **Per-step snapshots** (`data/snapshots/post_step_{17,18,19,20}.dump`) — not captured. Required for F4 + per-step audit + step_audit.csv FAIR/density delta columns.
- **Baseline snapshot** (`data/snapshots/pre_steps_17_20.dump`) — not captured.
- **Canonical-snapshot numerical reconciliation.** Documents disagree: visit count 33,800 vs 30,267; biomarker LOINC coverage 100% (CSF only) vs 78.84% (all biomarkers); OntologyConcept count 51 vs 46 vs 52. Need fresh `metrics/reconcile.py` run as ground truth.
- **AlzKB SAME_AS coverage** — step 24 exists and creates `:AlzKBConcept` + `:SAME_AS`, but the resulting match counts for Disease/Phenotype/Anatomy/Gene are not yet documented in canonical_snapshot.

### ❌ Missing — must be built (this plan owns)
The five **contribution-table gaps** the user committed to closing:
- **B-17**: HPO expansion from 5 to ~30 concepts. Map ADSXLIST's 15 binary symptom columns + FamilyMember flags to HPO terms.
- **B-18**: LOINC vital signs (6 new codes): systolic BP 8480-6, diastolic 8462-4, weight 29463-7, height 8302-2, heart rate 8867-4, BMI 39156-5. Source: `VITALS`.
- **B-19**: MEDHIST → `:Comorbidity` nodes at category granularity. Edge `HAS_COMORBIDITY`. SNOMED-CT category-level codes only.
- **B-20**: Biolink Model `biolink_category` on all 17 node types + `biolink_predicate` on the 30 relationship types.
- **B-21**: MONDO/DOID concept wiring. Wire existing `mondo_code` properties on `:Diagnosis` to `:OntologyConcept(source_ontology='MONDO')`; add three DOID nodes (AD, dementia, MCI) per the table.

Also missing:
- Column-to-concept reproducibility CSVs at `ontology/mappings/` (referenced by R1 tasks in v2). Consolidated `index.csv`.
- Polished Sultan-facing validity report at `outputs/validity_reports/kg_validity_progress_report.md`.
- F4 SVG/PDF + density progression plot rendered against per-step snapshots.

---

## 4. The six-phase plan

Phases 0–1 are prerequisites. Phases 2–5 run in parallel where dependencies allow. Phase 6 closes out.

### Phase 0 — Audit + reconcile (~0.5 day)

**Goal.** Single source of truth for every measured number. No new code; just running existing tooling and resolving discrepancies.

**Outputs.** `metrics/output/canonical_snapshot.json` (fresh) + `docs/final_report/c7_plan_v3/AUDIT_2026-05-16.md`.

**Detailed tasks.** See [TASKS.md §A0](TASKS.md).

### Phase 1 — Sultan's progress-report artifact (~0.5 day)

**Goal.** A clean Markdown + PDF report Sultan can paste into her next progress report. Backed by the existing seven-assertion validity gate.

The existing `metrics/validity.py` output is machine-flavored; this phase adds a human-readable rendering layer.

**Outputs.** `outputs/validity_reports/kg_validity_progress_report.md` (+ PDF via `metrics/thesis_pdf.py`).

**Spec.** [VALIDITY_PROGRESS_REPORT_SPEC.md](VALIDITY_PROGRESS_REPORT_SPEC.md).

**Detailed tasks.** See [TASKS.md §S1](TASKS.md).

### Phase 2 — Snapshot + figures infrastructure (~1.5 days)

**Goal.** Per-step snapshots captured; F4 rendered; F1–F5 all reproducible from JSON; figures distinct from `outputs/eda_figures/*` per the guardrails.

**Outputs.**
- `data/snapshots/{pre_steps_17_20,post_steps_17_20,post_step_17,post_step_18,post_step_19,post_step_20}.dump`
- `metrics/output/{fair,semantic_density,alzkb_alignment}_per_step.json`
- `metrics/output/step_audit.csv`
- `paper_outputs/f4_density.{svg,pdf,png}`
- `scripts/make_paper_figures.{sh,ps1}` (Windows-friendly Makefile equivalent)

**Detailed tasks.** See [TASKS.md §P2](TASKS.md).

### Phase 3 — Close contribution-table gaps B-17 → B-21 (~3.5–4 days)

**Goal.** Implement the five enrichment promises the contribution table commits to. Each is a new pipeline step with config toggle, validity hook, and idempotency.

**Outputs.**
- `steps/step30_hpo_expansion.py` (B-17)
- `steps/step31_loinc_vital_signs.py` (B-18)
- `steps/step32_medhist_comorbidity.py` (B-19)
- `steps/step33_biolink_categories.py` (B-20)
- `steps/step34_mondo_doid_wiring.py` (B-21)
- `ontology/mappings/*.csv` (seven CSVs)
- `ontology/hpo_concepts_cache.json` (B-17 offline fallback)
- Updated `metrics/validity_rubric.yaml` (A3 sources list + count bands)
- Updated `config.yaml` (5 new toggles, defaulted to `false`)
- Updated `pipeline.py` (5 new step registrations)
- `tests/test_step{30..34}.py` (idempotency tests)

**Spec.** [GAP_CLOSURE_SPEC.md](GAP_CLOSURE_SPEC.md) — full per-step technical detail including Cypher, mappings, edge counts, ambiguous decisions for Hajer review.

**Detailed tasks.** See [TASKS.md §P3](TASKS.md).

#### B-22 (no-op confirmation): No Gene Ontology integration

The contribution table marks C4 (Gene Ontology) as **proposed but not implemented**. This plan **does not** add a Gene node, GO concepts, or `ENCODES`/`PARTICIPATES_IN` edges. The thesis Future Work section already documents this gap (Section 4.4 / 5.4). This is the only contribution-table item left explicitly open.

### Phase 4 — Re-measure on the enriched graph + AlzKB alignment refresh (~1 day)

**Goal.** Final measured numbers across the enriched graph; AlzKB alignment matrix updated to reflect the new Disease+Phenotype identifier overlap.

**Outputs.**
- Updated `metrics/output/canonical_snapshot.json` (post-enrichment)
- Re-rendered F3 (FAIR), F4 (density), F5 (alignment) figures
- Updated `metrics/output/alzkb_alignment.json` — Disease weak→strong, Phenotype none→strong (target)
- Updated [c7_plan_v2/STATUS.md](../c7_plan_v2/STATUS.md) and [STATUS.md](STATUS.md) with ✅ for B-17 to B-21
- Updated [c7_plan_v2/CONTRIBUTION_TABLE_GAP_ANALYSIS.md](../c7_plan_v2/CONTRIBUTION_TABLE_GAP_ANALYSIS.md) — gap items flipped to "done"

**Detailed tasks.** See [TASKS.md §P4](TASKS.md).

### Phase 5 — Thesis patches (~1 day)

**Goal.** Thesis chapters reflect the post-enrichment state. **Strictly no causality, no OntoQA, no scope expansion.**

**Outputs.**
- Updated LaTeX in `Thesis/OğuzhanGüngör_Tez (1)/*.tex` (Sections 3.5–3.10, 4.2–4.6, 5.3–5.4)
- Mirror updates in `Thesis/Article/article.tex`
- New bibliography entries (Biolink, MONDO, DOID)
- Appendix with consolidated `ontology/mappings/index.csv`
- Rebuilt thesis PDF

**Spec.** [THESIS_PATCH_PLAN.md](THESIS_PATCH_PLAN.md) — chapter-by-chapter edit instructions with concrete LaTeX snippets.

**Detailed tasks.** See [TASKS.md §TH](TASKS.md).

### Phase 6 — Reproducibility, hand-off, sign-off (~0.5 day)

**Goal.** One-command reproduction; supervisors signed off; repo tagged.

**Outputs.**
- `make paper-figures` / `scripts/make_paper_figures.ps1` reproduces F1–F5 byte-identically
- `python -m metrics --all` reproduces all metric JSONs and CSV
- Updated [docs/infrastructure/CLAUDE_CODE_GUIDE.md](../../infrastructure/CLAUDE_CODE_GUIDE.md), [docs/infrastructure/TASKS.md](../../infrastructure/TASKS.md), [docs/infrastructure/IMPLEMENTATION_PLAN.md](../../infrastructure/IMPLEMENTATION_PLAN.md)
- Updated project memory (`memory/MEMORY.md`)
- Git tags `paper-submission-v1` and `thesis-defense-v1`

**Detailed tasks.** See [TASKS.md §R6](TASKS.md).

---

## 5. Metric definitions (precise)

Per Hajer's meeting note, schema-quality evaluation uses **FAIR + semantic density only**. OntoQA (Tartir et al., 2005) is not used.

### 5.1 FAIR

13 principles (F1, F2, F3, F4, A1.1, A1.2, A2, I1, I2, I3, R1.1, R1.2, R1.3). Three-level rubric (no = 0.0 / partial = 0.5 / yes = 1.0) per the FAIR Implementation Profile. Rubric in `metrics/fair_principles.yaml`; scorer `metrics/fair.py` reads YAML, runs each check (Cypher / file presence / manual flag), outputs `metrics/output/fair_score_<scope>.json`.

### 5.2 Semantic density

```
node_density(L)  = count(n: L WHERE n has any ontology_uri property OR n is :OntologyConcept) / count(n: L)
edge_density(T)  = count(r: T WHERE r.uri IS NOT NULL OR r.ro_uri IS NOT NULL OR r.biolink_predicate IS NOT NULL) / count(r: T)
aggregate_node   = sum_L node_density(L) weighted by |L|
aggregate_edge   = sum_T edge_density(T) weighted by |T|
```

Reported per node label, per edge type, and aggregate. After Phase 3, node density rises on `:Patient` / `:Visit` (Biolink categories) and `:Comorbidity` (fully URI-annotated new label).

### 5.3 AlzKB alignment (in-scope categories only)

For each AlzKB category K ∈ {Disease, Anatomy, Phenotype, Gene}:

```
strong_match(K) = | { e ∈ MAKO_K : ∃ e' ∈ AlzKB_K with shared identifier } |
total(K)        = | MAKO_K |
match_rate(K)   = strong_match(K) / total(K)
```

Data source: live `:AlzKBConcept` nodes + `:SAME_AS` edges produced by [steps/step24_alzkb_bridge.py](../../../steps/step24_alzkb_bridge.py). Reproducibility comes from re-running step 24 against the dump pinned in `data/alzkb/<version>/`. The Gene row reports zero with an explicit `not_implemented: true` flag and a docstring pointer to Future Work.

### 5.4 Validity gate (seven assertions)

A1–A7 per [c7_plan_v2/VALIDITY_CHECK_SPEC.md](../c7_plan_v2/VALIDITY_CHECK_SPEC.md). v3 extends only:
- **A3 sources list** grows from `[SNOMED-CT, LOINC, UBERON, HPO, ICD-10]` to `[SNOMED-CT, LOINC, UBERON, HPO, ICD-10, MONDO, DOID]` after Phase 3.
- **A5 allowlist** may need `HAS_COMORBIDITY` if that relationship is intentionally not URI-annotated.
- **Count bands** (A3 `expected_counts`) updated for HPO (30) and LOINC (16) after Phase 3.

The Cypher and threshold structure remains unchanged — those are authoritative in v2's spec.

---

## 6. Critical files — DO NOT REWRITE; extend

### Code that MUST NOT change
- `steps/step17_apply_constraints.py` … `steps/step20_ontology_layer.py` — already done; modifications would invalidate the per-step audit
- `steps/step21_extract_causal_features.py` … `steps/step26_dowhy_inference.py` — paused per [c7_plan_v2/CAUSALITY_NOTE.md](../c7_plan_v2/CAUSALITY_NOTE.md)
- `steps/step29_kg_eda.py` — EDA figures already generated; F1–F5 are separate
- `causal/` directory — paused
- Anything under `outputs/eda_figures/` — distinct from `paper_outputs/`

### Code to extend (not rewrite)
- `metrics/validity.py` — add `render_progress_report()` (Phase 1 / S1.2)
- `metrics/validity_rubric.yaml` — extend A3 sources list, allowlist `HAS_COMORBIDITY` (Phase 3 / P3.4)
- `metrics/step_audit.py` — wire to snapshot dumps (Phase 2 / P2.8)
- `figures/f4_density.py` — confirm renders against per-step JSONs; commit the SVG/PDF (Phase 2 / P2.9)
- `pipeline.py` — register steps 30–34 (Phase 3 / P3.1)
- `config.yaml` — add 5 new toggles (Phase 3 / P3.0)

### New files
- `steps/step{30..34}_*.py` (B-17 to B-21)
- `metrics/scripts/rollback_steps_17_20.cypher` (P2.3)
- `tests/test_step{30..34}.py` (P3.2)
- `ontology/mappings/*.csv` (P3.3) — see [GAP_CLOSURE_SPEC.md](GAP_CLOSURE_SPEC.md) for column schema
- `ontology/hpo_concepts_cache.json` (B-17 offline fallback)
- `data/snapshots/*.dump` (P2.2, P2.4, P2.5, P3.5)
- `docs/final_report/c7_plan_v3/AUDIT_2026-05-16.md` (A0.3)
- LaTeX edits in `Thesis/OğuzhanGüngör_Tez (1)/*.tex` and `Thesis/Article/article.tex` (Phase 5)

### Reusable utilities (use, don't replicate)
- `utils/neo4j_connector.py` — `Neo4jConnector` for all DB access
- `utils/batch_processor.py` — `OptimizedBatchProcessor` for memory tracking; `DataValidator.validate_ptid` for A7 hygiene
- `utils/quality_aware_logger.py` — pipeline-wide quality logging
- `figures/_style.py` — GSU palette
- `figures/_mermaid.py` — Mermaid → SVG renderer

---

## 7. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Neo4j downtime for offline `neo4j-admin database dump`** | Blocks per-step snapshots (P2.2–P2.5) → F4 (P2.9) and step_audit deltas (P2.8) | Schedule with Özgün in advance (P2.1). Fallback: in-process Cypher snapshots via `metrics/reconcile.py`; document the trade-off if used. |
| **HPO REST endpoint instability** (BioPortal / EBI OLS) | B-17 step fails on remote calls | Reuse `steps/step19_icd10_integration.py`'s retry+fallback pattern; cache HPO labels in `ontology/hpo_concepts_cache.json` for offline reproducibility |
| **Biolink Model class mapping ambiguity** | B-20 row labels ambiguous (e.g., `:Biomarker` → `ChemicalEntity` or `BiologicalProcess`) | Document each mapping decision in the mapping CSV's `mapping_rule` column; flag the ~5 ambiguous cases for Hajer review before committing |
| **AlzKB version drift** | F5 alignment numbers change between runs because AlzKB updates | Pin the AlzKB CYPHERL dump version in `data/alzkb/<version>/` (Q.4 gate); cite the version in the paper methods + thesis §4.6 |
| **Thesis numerical inconsistency** after enrichment | LaTeX still cites pre-enrichment numbers somewhere | Single source of truth: `canonical_snapshot.json`. Before final LaTeX build, run `grep` for every numeric claim and verify against the JSON |
| **Figure regeneration drift** | Committed SVGs don't match what scripts produce | Pre-commit / CI hook that runs `make paper-figures` and fails on hash mismatch (P2.12) |
| **Validity gate weakens after enrichment** | New `:Comorbidity` nodes lack a SNOMED code → A2 falls below threshold | B-19 ensures every `:Comorbidity` carries `snomed_code` before commit; `tests/test_step32.py` enforces it |
| **OntoQA bleed-through** in thesis/paper drafts | Reviewer asks "where's OntoQA" or supervisor sees stale text | `grep -ri ontoqa Thesis/ docs/final_report/c7_plan_v3/ paper_outputs/` before sign-off. The historical record (`docs/final_report/implementation_plan.md`, `task_metrics.md`, contribution table itself) may keep the term as context |
| **Causality reappears** in patched docs/thesis by accident | User explicitly excluded — could derail review | Patch only the sections listed in [THESIS_PATCH_PLAN.md](THESIS_PATCH_PLAN.md). Do not touch Chapters 1–2, Sections 3.1–3.4, or any "future work" causal sentence already present (it stays) |

---

## 8. Open coordination items (cannot resolve without supervisors)

These are not blockers for the plan documents but must be resolved before Phase 3 starts:

1. **Q.6 — Sultan signs off validity-rubric thresholds.** Default 0.95 per assertion; confirm or adjust per-label (e.g., 0.99 for Diagnosis/SNOMED).
2. **Q.7 — Özgün schedules Neo4j downtime** for offline `neo4j-admin database dump`. Roughly 30 min for the full sequence (P2.2–P2.5).
3. **Hajer FAIR rubric confirmation** — three-level vs binary scoring. Current plan assumes three-level (no / partial / yes).
4. **AlzKB dump version pin** — confirm with Hajer which Romano-et-al. release to cite.
5. **Biolink Model class assignment** for the ~5 ambiguous node types — async review by Hajer before committing the mapping CSV. List of ambiguities is enumerated in [GAP_CLOSURE_SPEC.md](GAP_CLOSURE_SPEC.md) §B-20.

---

## 9. Verification — how I know each phase is done

| Phase | Done when |
|---|---|
| 0 (Audit) | `metrics/output/canonical_snapshot.json` exists with timestamp ≤ 24 h; `AUDIT_2026-05-16.md` reconciles all three count disagreements |
| 1 (Sultan) | `outputs/validity_reports/kg_validity_progress_report.md` reviewed and accepted by Sultan in writing |
| 2 (Snapshots + figures) | 6 dump files in `data/snapshots/`; F4 SVG+PDF committed; `step_audit.csv` has 4 rows for steps 17–20 |
| 3 (B-17 to B-21) | 5 new pipeline steps committed + registered + idempotency-tested; 7 ontology sources in `:OntologyConcept` (was 5); HPO MAPS_TO count > 3,000 (was 0); validity gate still PASS |
| 4 (Re-measure) | AlzKB alignment 3/4 strong (was 1/4); FAIR aggregate higher; canonical snapshot updated; STATUS.md ✅ across the board |
| 5 (Thesis) | LaTeX builds clean; numbers traceable to canonical_snapshot.json; OntoQA references absent (except historical record); MAKO naming consistent; F3/F4/F5 embedded |
| 6 (Repro + sign-off) | `python -m metrics --all` reproduces all outputs; SVG hashes stable; tags pushed; supervisors signed off |

---

## 10. Effort estimate

| Phase | Effort (person-days) | Critical path? |
|---|---|---|
| 0 — Audit + reconcile | 0.5 | yes (prerequisite to all) |
| 1 — Sultan progress report | 0.5 | yes (earliest delivery, T-Sultan track) |
| 2 — Snapshots + figures | 1.5 | partial (P2.2–P2.5 blocked on Özgün; P2.9 needs P2.7) |
| 3 — B-17 → B-21 closure | 3.5–4 | no — parallel to Phase 2 once mapping CSVs (P3.3) are drafted |
| 4 — Re-measure post-enrichment | 1 | yes (depends on Phase 3) |
| 5 — Thesis patches | 1 | yes (depends on Phase 4 measurements) |
| 6 — Repro + sign-off | 0.5 | yes (final) |
| **Total** | **8–8.5** person-days | |

Calendar time: ~3 weeks at 50 % allocation, contingent on supervisor turnaround on §8 items. If Özgün downtime (Q.7) is delayed by a week, the critical path is the snapshot capture for F4 — but the thesis can still be patched against the canonical snapshot if F4 is published with the "before-vs-after endpoints only" framing instead of per-step.

---

## 11. What this plan does NOT change

Per the user's explicit exclusions:

- **No OntoQA implementation.** Tartir 2005 not cited; OntoQA metrics not computed. FAIR + semantic density only.
- **No causal-discovery work.** Steps 21–26 remain paused. `causal/` untouched. Config toggles remain `false`. Thesis Chapter 2 / §5.4 causal future-work paragraph stays as-is.
- **No Gene Ontology integration.** C4 is the one contribution-table item left explicitly open in thesis Future Work and paper Limitations.
- **No C6 comparative benchmark.** Future work, post-June 2026. Out of scope.
- **No new ontologies beyond MONDO + DOID + Biolink + expanded HPO/LOINC.** UMLS, ICD-11, FOAM, BioPortal Annotator, HL7 FHIR, OpenEHR remain explicitly excluded.
- **No deletion of v2 documents.** Preserved as historical record per the c7_plan_v2 convention.
- **No edits to `outputs/eda_figures/`** — step 29's 15 figures are the EDA artifact and are distinct from `paper_outputs/F1–F5`.

---

## 12. Cross-references

- [README.md](README.md) — entry point
- [TASKS.md](TASKS.md) — granular task list executing this plan
- [STATUS.md](STATUS.md) — state ledger
- [VALIDITY_PROGRESS_REPORT_SPEC.md](VALIDITY_PROGRESS_REPORT_SPEC.md) — Phase 1 deliverable spec
- [GAP_CLOSURE_SPEC.md](GAP_CLOSURE_SPEC.md) — Phase 3 technical spec (B-17 to B-21)
- [THESIS_PATCH_PLAN.md](THESIS_PATCH_PLAN.md) — Phase 5 chapter-by-chapter edits
- [c7_plan_v2/VALIDITY_CHECK_SPEC.md](../c7_plan_v2/VALIDITY_CHECK_SPEC.md) — authoritative seven-assertion validity spec (unchanged by v3)
- [c7_plan_v2/CAUSALITY_NOTE.md](../c7_plan_v2/CAUSALITY_NOTE.md) — paused-but-retained causal code
- [c7_plan_v2/CONTRIBUTION_TABLE_GAP_ANALYSIS.md](../c7_plan_v2/CONTRIBUTION_TABLE_GAP_ANALYSIS.md) — gap analysis to flip to ✅ during execution
- [c7_unified_contribution.md](../c7_unified_contribution.md) — paper's contribution doc
- [meeting_notes.md](../meeting_notes.md) — Friday meeting decisions
