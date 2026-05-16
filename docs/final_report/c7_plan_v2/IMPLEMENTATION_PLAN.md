# Implementation Plan — KG Validity, Metrics, Figures (C7 + Thesis)

> **Scope.** This plan covers (a) a formal **KG validity check** that proves the LPG → KG transition is complete, (b) the **FAIR + semantic density** metric pipeline that backs the C7 paper's quantitative claims, (c) the **figure / diagram generator** for the paper and thesis, and (d) the **AlzKB alignment** scorer. **No scripts are written by this plan.** Scripts are owned by the corresponding tasks in `TASKS.md`, executed in a later session once Sultan and Özgün approve the plan.
>
> **Versioning.** This file lives under `docs/final_report/c7_plan_v2/` so the original `docs/final_report/implementation_plan.md` and `task_metrics.md` remain untouched as the historical record. Cross-references in this folder use relative links.
>
> **Status.** Planning. Approval expected from Sultan (validity gate first), then Özgün (full plan), then Hajer (paper-side parts).

---

## 1. Why this plan exists

The C7 paper makes four quantitative claims:

1. The four-step methodology improves **FAIR** and **semantic density** scores.
2. The methodology produces strong AlzKB alignment in 3 of 4 in-scope entity categories.
3. The pipeline is reproducible end-to-end on a fresh container.
4. The procedure generalises (deferred to future work; this plan only ensures the methodology is documented well enough to support that claim).

Each claim must be backed by a measured number, a figure, or both. The current state of the repo has the migration code (steps 17–20) and an existing AlzKB bridge (step 24), but **no FAIR scorer, no semantic density module, no validity gate, no per-step audit, and no snapshot tooling**. The placeholder targets in `c7_unified_contribution.md` need to be replaced with measured values, and Sultan's most recent feedback adds an upstream non-negotiable: even if metrics don't make the next progress report, the KG-converted state of the graph must be demonstrable. That is what the validity gate in §5 does.

Per Hajer's meeting note, FAIR and semantic density are the chosen evaluation methods. **OntoQA is not used.** The baseline reference is the pre-Steps-17–20 graph, with deltas reported per step.

---

## 2. Out of scope for this plan

- **Causal discovery** (PC / FCI / GES / DAG-GNN, dowhy). Not part of C7. Code under `steps/step21..step26*.py` and `causal/` is paused but **retained** — see [CAUSALITY_NOTE.md](CAUSALITY_NOTE.md).
- **Live SPARQL inference** against external endpoints. AlzKB alignment uses the dump pinned by step 24 for reproducibility.
- **New ontology integrations.** Gene Ontology integration (the removed C4) is documented as a known limitation, not measured.
- **Pipeline performance benchmarks.** Already published in the IEEE Big Data 2025 paper; `steps/step16_create_metrics.py` covers query-time performance, which is unrelated to FAIR / density.

---

## 3. Deliverables

### 3.1 Validity outputs (NEW — Sultan's gate)

| Output | Format | Purpose |
|---|---|---|
| `metrics/validity_rubric.yaml` | YAML | Configurable thresholds + assertion list; reviewable by Sultan without reading code |
| `outputs/validity_reports/kg_validity_<timestamp>.json` | JSON | Machine-readable pass/fail per assertion |
| `outputs/validity_reports/kg_validity_<timestamp>.md` | Markdown | Human-readable summary for the progress report |

### 3.2 Metrics outputs

| Output | Format | Purpose |
|---|---|---|
| `metrics/output/fair_score_baseline.json` | JSON | FAIR scoring on the pre-Steps-17–20 graph |
| `metrics/output/fair_score_post.json` | JSON | FAIR scoring after Steps 17–20 |
| `metrics/output/fair_score_per_step.json` | JSON | FAIR delta per individual step |
| `metrics/output/semantic_density_baseline.json` | JSON | Node / edge URI coverage on pre-Steps-17–20 graph |
| `metrics/output/semantic_density_post.json` | JSON | Same after Steps 17–20 |
| `metrics/output/semantic_density_per_step.json` | JSON | Per-step density delta |
| `metrics/output/alzkb_alignment.json` | JSON | Strong-match count per AlzKB entity category |
| `metrics/output/step_audit.csv` | CSV | One row per migration step: nodes touched, edges added, runtime, FAIR delta, density delta |
| `ontology/mappings/index.csv` | CSV | One row per source-column → target ontology concept (consolidated) |

### 3.3 Snapshots (NEW — needed to compute "per-step delta")

| Snapshot | Source | Notes |
|---|---|---|
| `data/snapshots/post_steps_17_20.dump` | Current production graph | Baseline of "after migration" state |
| `data/snapshots/pre_steps_17_20.dump` | Above + rollback Cypher | The "before" reference for FAIR + density |
| `data/snapshots/post_step_{17,18,19,20}.dump` | Re-run pipeline against rolled-back copy | Per-step intermediate states |

### 3.4 Figures for the paper

| Figure | Type | What it shows |
|---|---|---|
| F1 | Functional dependency diagram (revised) | C7 at centre; Steps A–D as feeders; C6 as future work |
| F2 | Schema before / after | LPG schema vs ontology-grounded KG schema. **Must visibly differ from `outputs/eda_figures/15_relationship_schema.svg`** (step 29). |
| F3 | FAIR scorecard | Per-principle bar / heatmap, baseline vs post |
| F4 | Semantic density progression | Node-URI + edge-URI coverage growing per step (waterfall or stacked area). **Must not duplicate `outputs/eda_figures/10_ontology_coverage.svg`** (step 29 is a static post-state heatmap; F4 is a per-step progression). |
| F5 | AlzKB alignment matrix | 4 × 2 heatmap (in-scope categories × pre/post) |

### 3.5 Tables for the paper

| Table | Content |
|---|---|
| T1 | Ontology / tool / standard assessment (existing summary, light edits) |
| T2 | Per-step migration audit (nodes touched, edges added, FAIR delta, density delta) |
| T3 | Column-to-concept mapping (source column → ontology URI) |
| T4 | AlzKB alignment results (with method per row) |

### 3.6 Reproducibility artefacts

- Single entrypoint: `python -m metrics --all` recomputes every metric and regenerates every figure.
- `Dockerfile.metrics` + `requirements-metrics.txt` for the metrics pipeline.
- `make paper-figures` target that takes JSON outputs and produces SVG / PDF.

---

## 4. Architecture

```
ADNIKnowledgeGraph/
├── metrics/
│   ├── __init__.py
│   ├── validity.py            # NEW — KG-vs-LPG validity gate (Sultan)
│   ├── validity_rubric.yaml   # NEW — thresholds + assertions
│   ├── fair.py                # FAIR principle scorer
│   ├── fair_principles.yaml   # FAIR scoring rubric
│   ├── semantic_density.py    # node-URI + edge-URI coverage
│   ├── alzkb_alignment.py     # extends steps/step24_alzkb_bridge.py
│   ├── step_audit.py          # per-step replay audit
│   ├── snapshots.py           # neo4j-admin dump/restore wrappers
│   └── runner.py              # `python -m metrics --all` entrypoint
├── figures/                   # NEW directory
│   ├── f1_dependency.py
│   ├── f2_schema.py
│   ├── f3_fair.py
│   ├── f4_density.py
│   └── f5_alignment.py
├── ontology/
│   └── mappings/              # NEW (currently absent) — column-to-concept CSVs
└── tests/
    ├── test_validity.py       # NEW
    ├── test_fair.py           # NEW
    ├── test_semantic_density.py # NEW
    ├── test_alzkb_alignment.py # NEW
    └── fixtures/
        └── mini_kg.cypher     # NEW — synthetic ~50-node graph for unit tests
```

The `metrics/` package depends only on `utils/neo4j_connector.py::Neo4jConnector` and the pinned AlzKB dump consumed by `steps/step24_alzkb_bridge.py`. The `figures/` package depends only on the JSON outputs of `metrics/` so figures regenerate offline from JSON without a live Neo4j.

---

## 5. KG validity gate (NEW — Sultan's feedback)

Sultan: *"even if metrics don't make the progress report, the ontologies have to be finished and the KG-converted state of the graph has to be in there."* That translates to a formal validity check that runs **before** any FAIR / density work and **fails loud** if the graph is still effectively an LPG.

The full assertion list, Cypher queries, and YAML rubric schema live in [VALIDITY_CHECK_SPEC.md](VALIDITY_CHECK_SPEC.md). Summary of the seven assertions:

| # | Assertion | Source of truth | Threshold (default) |
|---|---|---|---|
| A1 | All step-17 constraints + indexes present | `SHOW CONSTRAINTS`, `SHOW INDEXES` | 12 / 15 (binary) |
| A2 | Ontology-code coverage on enriched node labels | `MATCH (n:Diagnosis) WHERE n.snomed_code IS NOT NULL …` | ≥ 95 % per label |
| A3 | `:OntologyConcept` layer materialised across 5 ontologies | `MATCH (o:OntologyConcept) RETURN DISTINCT o.source_ontology` | ≥ 5 distinct sources |
| A4 | Ontology edges (`MAPS_TO`, `IS_A`, `CLASSIFIED_AS`) present with `uri` | per-edge counts | ≥ 95 % `uri` populated |
| A5 | Relationship-type URI annotation coverage | every relationship type has `uri` | ≥ 95 % rel types annotated |
| A6 | No orphan `:OntologyConcept` nodes | every concept reachable from a data node or flagged hierarchy root | ≥ 95 % reachable |
| A7 | PTID hygiene (no `381_S_*` patients) | `utils/batch_processor.py::DataValidator` reapplied | binary (0 violations) |

Threshold-based scoring (default 95 %) per the user decision. Hard-fail conditions (no `:OntologyConcept` label at all, zero constraints, zero `MAPS_TO` edges) are still binary asserts even under the threshold scheme — see VALIDITY_CHECK_SPEC.md §"Hard fails".

The runner in `metrics/runner.py` calls `metrics/validity.py` first; on FAIL it short-circuits, prints the offending assertions, and exits non-zero. Subsequent metric runs only proceed on PASS.

---

## 6. Metric definitions (precise)

Per Hajer's meeting note, schema-quality evaluation uses **FAIR** and **semantic density** only. OntoQA (Tartir et al., 2005) is not used.

### 6.1 FAIR

Applied at the principle level (F1–F4, A1–A2, I1–I3, R1.1–R1.3). Each principle scored on a three-level scale (no / partial / yes) per the FAIR Implementation Profile guidance. The rubric is `metrics/fair_principles.yaml`. The scorer reads the YAML, runs the corresponding check (Cypher query, file presence check, or manual-flag review), and outputs `metrics/output/fair_score_<scope>.json`.

### 6.2 Semantic density

```
node_density   = count(n WHERE n has any ontology_uri property OR n is :OntologyConcept) / count(n)
edge_density   = count(r WHERE r.uri IS NOT NULL OR r.ro_uri IS NOT NULL OR r.biolink_predicate IS NOT NULL) / count(r)
```

Reported per node label and per edge type, plus the aggregate.

### 6.3 AlzKB alignment (in-scope categories only)

For each AlzKB category K ∈ {Disease, Anatomy, Phenotype, Gene}:

```
strong_match(K) = |{ e ∈ MAKO_K : ∃ e' ∈ AlzKB_K with shared identifier }|
total(K)        = |MAKO_K|
match_rate(K)   = strong_match(K) / total(K)
```

The data source is the live `:AlzKBConcept` nodes + `:SAME_AS` edges produced by `steps/step24_alzkb_bridge.py` (per the user decision). Reproducibility comes from re-running step 24 against the dump pinned in `data/alzkb/<version>/`. The Gene row reports zero with an explicit `not_implemented: true` flag and a docstring pointer to Future Work.

### 6.4 Correction note (vs the original `implementation_plan.md`)

The earlier draft listed `source_table` and `source_column` as Step 18 properties. **Step 18 does not actually set them.** They are dropped from the deliverables. If column-to-concept mapping (Step C) ever needs source-row provenance, that becomes a task under R1, not a step-18 fix.

The earlier draft also referenced `metrics/` as if empty. It is empty in the current repo; this plan establishes the package.

`steps/step16_create_metrics.py` is named "create metrics" but measures **Cypher query performance** (`ADNIMetricsCollector`, latency percentiles). It is unrelated to FAIR / density. The naming is a historical artefact and is not changed by this plan.

---

## 7. Visualisation principles

The thesis template uses GSU institutional colours: dark blue `#184A7C`, pink accent `#B5397D`, yellow accent `#B8B90C`. Every figure for the thesis uses this palette. Figures destined for the journal paper use a more conservative greyscale-friendly palette so print copies remain readable.

All figures published as SVG (vector) plus PDF (LaTeX `\includegraphics`). Matplotlib figures use `seaborn-v0_8-whitegrid` with GSU overrides. Diagrams (F1, F2) use Graphviz with a custom theme **or** Mermaid exported to SVG.

Bar charts always show absolute numbers labelled on top of bars. FAIR principle scores and semantic density are deterministic given a fixed graph snapshot, so no error bars on F3 or F4.

### 7.1 Banned overlap (step 29 figures)

The new figures must not duplicate the 15 figures already in `outputs/eda_figures/`. Specifically:

- F2 (schema before / after) must visibly differ from `15_relationship_schema.svg` — F2 is a side-by-side delta, not a single-state schema.
- F4 (density progression) must not be confused with `10_ontology_coverage.svg` — F4 is a per-step time series; the step 29 figure is a single-state heatmap.

The figure scripts include the step 29 file paths in a banned-input list and a docstring that explains the difference.

---

## 8. Risks

1. **Pre-enrichment graph state.** Per Hajer's note, the baseline is the pre-enrichment CauAD graph, but some node types already carry ontology codes from earlier pipeline steps so the baseline is not a true zero. **Mitigation:** snapshot the production graph and roll back Steps 17–20 on a copy; document in the methods section that the baseline is "pre-Steps-17–20" rather than "no ontology". Owner: Oğuzhan, with Özgün's confirmation on the snapshot strategy.
2. **AlzKB integration is not green field.** `steps/step24_alzkb_bridge.py` already creates `:AlzKBConcept` and `:SAME_AS`. The C7 alignment metric must read from those nodes/edges; otherwise the reported alignment numbers won't match what is actually in the graph. **Mitigation:** `metrics/alzkb_alignment.py` reuses step 24 outputs; M4 task list cites step 24 explicitly.
3. **Step 29 figure overlap.** Static post-state coverage exists in `outputs/eda_figures/10_ontology_coverage.svg`. Easy to confuse with the per-step progression in F4. **Mitigation:** banned-input list + figure-script docstrings (§7.1).
4. **Snapshot tooling is brand new.** No existing `neo4j-admin database dump` machinery. Offline dump requires stopping the DB on the Galatasaray instance. **Mitigation:** Q.7 schedules brief downtime windows with Özgün; `metrics/snapshots.py` wraps the dump / restore commands.
5. **AlzKB version pin.** The dump must be pinned to a specific release for reproducibility. Recent Romano et al. updates may shift identifiers. **Mitigation:** archive the exact CYPHERL file used in the paper alongside the metrics under `data/alzkb/<version>/`.
6. **FAIR principle subjectivity.** Some principles (R1.1 licence clarity, R1.2 provenance) require human judgement, not a pure Cypher query. **Mitigation:** rubric `metrics/fair_principles.yaml` so two reviewers can score independently; disagreement rate is reportable.
7. **Figure regeneration drift.** Figures are produced once, then the underlying JSON changes, then paper figures fall out of sync with paper text. **Mitigation:** `make paper-figures` target plus a CI check that compares SVG hashes against the committed SVGs.

---

## 9. Sequencing (no script work in this plan)

1. **Approval round** — review IMPLEMENTATION_PLAN.md, TASKS.md, VALIDITY_CHECK_SPEC.md with Sultan first (validity gate), then Özgün (full plan), then Hajer (paper-side parts).
2. **Validity gate execution** — implement `metrics/validity.py`, run on the production graph, commit the JSON / Markdown report. **This is the gate Sultan asked for.** No further work proceeds until this passes.
3. **Baseline snapshot** — execute the pre-Steps-17–20 snapshot strategy (offline `neo4j-admin database dump`).
4. **Metric computation** — implement `metrics/` package, run end-to-end, produce JSON / CSV outputs.
5. **Figure generation** — implement `figures/`, regenerate from JSON, commit SVG / PDF.
6. **Methodology section update** — write the FAIR scoring rubric and semantic density definition into the paper's methods section.
7. **Reproducibility check** — fresh container, run `python -m metrics --all && make paper-figures`, confirm outputs match committed versions.

Estimated calendar time: 3 weeks of part-time effort, contingent on no rework loops with the supervisors. The validity gate (step 2) is the prerequisite for the progress report Sultan asked for and is on the critical path.

---

## 10. Decisions captured

1. **Validity rubric — threshold-based (≥ 95 %).** Configurable per assertion in `metrics/validity_rubric.yaml`. Hard-fail conditions stay binary.
2. **AlzKB alignment — live `:AlzKBConcept` nodes** populated by `steps/step24_alzkb_bridge.py`. No separate RDF-dump-loader task. The pinned dump is the upstream input to step 24, not a parallel data source.
3. **Snapshots — offline `neo4j-admin database dump`.** Stop DB → dump → restart. Q.7 coordinates downtime with Özgün.
4. **`source_table` / `source_column` — dropped.** Not implemented by step 18; not added in this revision. If column-to-concept mapping needs source-row provenance, that becomes a separate R1 task.

---

## 11. Cross-references

- [TASKS.md](TASKS.md) — granular task list executing this plan
- [VALIDITY_CHECK_SPEC.md](VALIDITY_CHECK_SPEC.md) — Sultan's gate, full Cypher + YAML schema
- [STATUS.md](STATUS.md) — completed / missing / added / paused ledger
- [CAUSALITY_NOTE.md](CAUSALITY_NOTE.md) — paused-but-retained code notice
- [../c7_unified_contribution.md](../c7_unified_contribution.md) — what the metrics back up
- [../meeting_notes.md](../meeting_notes.md) — Hajer / Sultan source of truth
- [../implementation_plan.md](../implementation_plan.md) — original plan (preserved as historical record)
- [../task_metrics.md](../task_metrics.md) — original task list (preserved as historical record)
- [../../infrastructure/IMPLEMENTATION_PLAN.md](../../infrastructure/IMPLEMENTATION_PLAN.md) — master implementation plan
- [../../infrastructure/TASKS.md](../../infrastructure/TASKS.md) — master tasks
- [../../infrastructure/history/PHASE1_SCHEMA_MIGRATION.md](../../infrastructure/history/PHASE1_SCHEMA_MIGRATION.md) — Steps 17–20 history
