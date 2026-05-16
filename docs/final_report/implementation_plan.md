# Implementation Plan — Metrics, Graphs, and Visualizations

> **Scope.** This plan covers everything needed to (a) compute the metrics that back the C7 paper's claims, (b) produce the figures and tables for the paper and the thesis, and (c) publish the reproducibility artefacts alongside both. **No scripts are written by this plan.** Scripts are owned by the corresponding tasks in `TASKS_METRICS.md`, executed in a later session.
>
> **Status.** Planning. Approval expected from Sultan and Özgün before any code lands.

---

## Why this plan exists

The C7 paper makes four quantitative claims:

1. The four-step methodology improves FAIR and semantic density scores.
2. The methodology produces strong AlzKB alignment in 3 of 4 in-scope entity categories.
3. The pipeline is reproducible end-to-end on a fresh container.
4. The procedure generalises (deferred to future work; this plan only ensures the methodology is documented well enough to support that claim).

Each claim must be backed by a measured number, a figure, or both. The current state of the repo has the computation scripts for none of these. Per Hajer's meeting note, FAIR and semantic density are the chosen evaluation methods; OntoQA is not used. The baseline reference is the pre-enrichment CauAD graph, with deltas reported per step. This plan turns the placeholder targets in the contribution document into measured values and produces the visual assets that go into the paper.

---

## Out of scope for this plan

- Causal discovery metrics (PC / FCI / GES / DAG-GNN). Causality is not in the C7 paper.
- Live inference benchmarks against external SPARQL endpoints. The AlzKB alignment uses a downloaded RDF dump for reproducibility.
- New ontology integrations. Gene Ontology integration (the removed C4) is documented as a known limitation, not measured.
- Pipeline performance benchmarks. Already published in the IEEE Big Data 2025 paper.

---

## Deliverables

### Metrics outputs

| Output | Format | Purpose |
|---|---|---|
| `fair_score_baseline.json` | JSON | FAIR principle-by-principle scoring on the pre-Steps-17–20 graph |
| `fair_score_post.json` | JSON | FAIR scoring after Steps 17–20 |
| `fair_score_per_step.json` | JSON | FAIR delta attributable to each individual step |
| `semantic_density_baseline.json` | JSON | Node-level and edge-level URI coverage on the pre-Steps-17–20 graph |
| `semantic_density_post.json` | JSON | Same after Steps 17–20 |
| `semantic_density_per_step.json` | JSON | Per-step semantic density delta |
| `alzkb_alignment.json` | JSON | Strong-match count per AlzKB entity category |
| `step_audit.csv` | CSV | One row per migration step: nodes touched, edges added, runtime, FAIR delta, density delta |
| `column_to_concept_mapping.csv` | CSV | One row per source column → target ontology concept |

### Figures for the paper

| Figure | Type | What it shows |
|---|---|---|
| F1 | Functional dependency diagram (revised) | C7 at centre; Steps A–D as feeders; C6 as future work |
| F2 | Schema before / after | LPG schema vs ontology-grounded KG schema |
| F3 | FAIR scorecard | Per-principle bar chart or heatmap, baseline vs post |
| F4 | Semantic density progression | Node-URI and edge-URI coverage growing per step (waterfall or stacked area) |
| F5 | AlzKB alignment matrix | 4 × 2 heatmap (in-scope categories × pre/post) |

### Tables for the paper

| Table | Content |
|---|---|
| T1 | Ontology / tool / standard assessment (the existing summary table, light edits) |
| T2 | Per-step migration audit (nodes touched, edges added, FAIR delta, density delta) |
| T3 | Column-to-concept mapping (source column → ontology URI) |
| T4 | AlzKB alignment results (with method per row) |

### Reproducibility artefacts

- All scripts under a single entrypoint: `python -m metrics --all` recomputes every metric and regenerates every figure.
- Dockerfile pin and `requirements-metrics.txt` for the metrics pipeline.
- A `make paper-figures` target that takes the JSON outputs and produces SVGs / PDFs for the paper.

---

## Architecture

```
ADNIKnowledgeGraph/
├── metrics/
│   ├── __init__.py
│   ├── fair.py               # FAIR principle scorer
│   ├── semantic_density.py   # URI coverage on nodes and edges
│   ├── alzkb_alignment.py    # AlzKB RDF dump loader + matching
│   ├── step_audit.py         # Per-step audit replay
│   └── runner.py             # Single entrypoint, writes JSON + CSV
├── figures/
│   ├── f1_dependency.py      # graphviz / mermaid → SVG
│   ├── f2_schema.py          # before/after schema diagrams
│   ├── f3_fair.py            # FAIR scorecard
│   ├── f4_density.py         # density progression chart
│   └── f5_alignment.py       # alignment heatmap
├── ontology/
│   └── mappings/             # column_to_concept CSVs (existing data)
└── tests/
    └── fixtures/              # synthetic miniature graph for unit tests
```

The `metrics/` package depends only on a Neo4j connection and the AlzKB RDF dump. The `figures/` package depends only on the JSON outputs of `metrics/`. This separation lets the metrics run on the Galatasaray Neo4j server while figures regenerate offline from the JSONs.

---

## Metric definitions (precise)

Per Hajer's meeting note, the schema-quality evaluation uses **FAIR** and **semantic density** only. OntoQA (Tartir et al., 2005) is not used.

### FAIR

The FAIR maturity model is applied at the principle level (F1–F4, A1–A2, I1–I3, R1.1–R1.3). Each principle scored on a binary or three-level scale (no / partial / yes) following the FAIR Implementation Profile guidance. The score sheet is `metrics/fair_principles.yaml`; the scorer reads it plus inspection queries against the live graph and outputs `fair_score.json`.

### Semantic density

```
node_density   = count(n WHERE n has ontology_uri or n is OntologyConcept) / count(n)
edge_density   = count(r WHERE r.ro_uri IS NOT NULL or r.biolink_predicate IS NOT NULL) / count(r)
```

Reported per node label and per edge type, plus aggregate.

### AlzKB alignment (in-scope categories only)

For each AlzKB category `K` in {Disease, Anatomy, Phenotype, Gene}:

```
strong_match(K) = |{e in CauAD_K : exists e' in AlzKB_K with shared_uri(e, e')}|
total(K)        = |CauAD_K|
match_rate(K)   = strong_match(K) / total(K)
```

The Gene row reports zero with a methodology note ("Gene Ontology integration not in scope for this paper; see Future Work").

---

## Visualisation principles

The thesis template uses GSU institutional colours: dark blue `#184A7C`, pink accent `#B5397D`, yellow accent `#B8B90C`. Every figure that goes into the thesis uses this palette. Figures destined for the journal paper use a more conservative greyscale-friendly palette so that print copies remain readable.

All figures published as SVG (vector) plus PDF (for LaTeX `\includegraphics`). Figures generated with matplotlib use the `seaborn-v0_8-whitegrid` style with the GSU colour overrides. Diagrams (F1, F2) use either Graphviz with a custom theme or hand-edited Mermaid exported to SVG. Mermaid is preferred where the diagram is small enough that the cost of touching up SVG by hand is manageable.

Bar charts always show absolute numbers labelled on top of bars and use error bars only where the metric has stochastic variation. FAIR principle scores and semantic density are deterministic given a fixed graph snapshot, so no error bars on F3 or F4.

---

## Risks

- **Pre-enrichment graph state.** Hajer's chosen baseline is the pre-enrichment CauAD graph (per meeting note). Some node types already carry ontology codes from earlier pipeline steps, so the baseline is not a true zero. Action: snapshot the current production graph and roll back Steps 17–20 on a copy, then document in the methods section that the baseline is "pre-Steps-17–20" rather than "no ontology". **Owner: Oğuzhan, with Özgün's confirmation on the snapshot strategy.**
- **AlzKB version pin.** The AlzKB RDF dump must be pinned to a specific release for reproducibility. Recent Romano et al. updates may shift identifiers. **Action:** archive the exact RDF file used in the paper alongside the metrics.
- **FAIR principle subjectivity.** Some FAIR principles (R1.1 licence clarity, R1.2 provenance) require human judgement, not a pure graph query. Action: use a written rubric in `metrics/fair_principles.yaml` so two reviewers can score independently and the disagreement rate is reportable.
- **Figure regeneration drift.** If figures are produced once and then the underlying JSON changes, the paper figures and the paper text fall out of sync. The `make paper-figures` target plus a CI check that compares SVG hashes of the most recent run against the committed SVGs catches this.

---

## Sequencing (no script work in this plan; sequencing only)

1. **Approval round** — review this plan and `TASKS_METRICS.md` with Sultan and Özgün, then circulate to Hajer for the parts that touch the paper (Step C reproducibility table, FAIR / semantic density addition).
2. **Baseline snapshot** — decide and execute the pre-Steps-17–20 graph snapshot strategy.
3. **Metric computation** — implement `metrics/` package, run end-to-end, produce JSON / CSV outputs.
4. **Figure generation** — implement `figures/` package, regenerate from JSON, commit SVG / PDF.
5. **Methodology section update** — write the FAIR scoring rubric and the semantic density definition into the paper's methods section.
6. **Reproducibility check** — fresh container, run `python -m metrics --all && make paper-figures`, confirm outputs match committed versions.

Estimated calendar time: 3 weeks of part-time effort, contingent on no rework loops with the supervisors.

---

## Cross-references

- `C7_UNIFIED_CONTRIBUTION.md` — what the metrics back up.
- `TASKS_METRICS.md` — granular task list executing this plan.
- `PHASE5_EXPLORATION_ANALYSIS.md` — existing exploration analysis. The baseline graph snapshot work reuses the EDA infrastructure where possible.
- `IMPLEMENTATION_PLAN.md` — the master implementation plan. This metrics plan is a sub-plan under it.