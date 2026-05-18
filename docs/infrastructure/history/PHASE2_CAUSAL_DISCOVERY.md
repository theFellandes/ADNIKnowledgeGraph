# Phase 2: Causal Discovery — History

**Completed:** 2026-02-25  
**Pipeline:** `pipeline.py` (Steps 21–23, config.yaml-driven)

---

> **Historical document — captured 2026-02-25. Code is paused.**
> The causal-discovery prototypes (steps 21–26 and the `causal/` directory) are intentionally retained but not run, per [`docs/final_report/c7_plan_v2/CAUSALITY_NOTE.md`](../../final_report/c7_plan_v2/CAUSALITY_NOTE.md). Causal claims appear in the thesis only in Chapter 2 (literature review) and §5.4 (Future Work). Causal layer will resume post-defence. For current canonical state see [`outputs/metrics/canonical_snapshot.json`](../../../outputs/metrics/canonical_snapshot.json).

---

## What Was Done

### Step 21: Extract Causal Feature Matrix
- Created `steps/step21_extract_causal_features.py` (~370 lines)
- **7 Cypher queries** for baseline features (`viscode IN ['bl', 'sc']`):
  - Demographics: age, gender, education, APOE e4 count
  - Cognitive: MMSE, CDR, ADAS-Cog, MoCA, FAQ, Logical Memory (pivoted by test_name)
  - CSF Biomarkers: Aβ42, Tau, pTau (pivoted by analyte)
  - Volumetric: Hippocampus, Entorhinal, Ventricles, WholeBrain, ICV (pivoted by region)
  - PET: AV45, FDG, AV1451 SUVR (averaged across regions per tracer)
  - ATN Profile: A/T/N binary status (+→1, -→0)
  - Diagnosis: CN=0, MCI=1, AD=2 (ordinal encoding)
- **Preprocessing pipeline**:
  1. Drop columns with >50% missing (configurable threshold)
  2. Impute continuous with median, categorical with mode
  3. Encode gender → 0/1, APOE genotype → e4 allele count
  4. Z-score standardization (excludes binary/ordinal variables)
- **Outputs**: `causal/causal_features.csv`, `causal/causal_features_raw.csv`, `causal/completeness_report.json`, `causal/correlation_matrix.png`

### Step 22: Causal Discovery Algorithms
- Created `steps/step22_causal_discovery.py` (~340 lines)
- **3 algorithms** via `causal-learn` library:
  - **PC** (Peter-Clark): constraint-based, assumes causal sufficiency
  - **FCI** (Fast Causal Inference): constraint-based, handles latent confounders
  - **GES** (Greedy Equivalence Search): score-based, BIC scoring
- **Edge extraction** from causal-learn's GeneralGraph adjacency matrix:
  - Handles directed (`-->`), undirected (`---`), and partially directed (`o->`) edge types
  - Maps causal-learn's matrix encoding: -1/1 = directed, -1/-1 = undirected, 2 = circle endpoint
- **Consensus logic**: edge included if found by ≥ `consensus_threshold` (default: 2) algorithms
  - Direction resolved by majority vote among directed edges
  - Confidence = fraction of algorithms agreeing
- **Outputs**: per-algorithm `{algo}_adjacency.json` + `{algo}_graph.png`, `consensus_edges.json`, `consensus_graph.png`

### Step 23: Embed CAUSES Edges in Neo4j
- Created `steps/step23_embed_causal_edges.py` (~290 lines)
- **Variable → OntologyConcept mapping** (40+ variables):
  - Cognitive → LOINC codes (e.g., MMSE → `loinc:72106-8`)
  - CSF → LOINC codes (e.g., Aβ42 → `loinc:49325-0`)
  - Brain regions → UBERON codes (e.g., Hippocampus → `uberon:UBERON:0002421`)
  - Demographics → NCI Thesaurus (e.g., Age → `ncit:C25150`)
  - PET/ATN → NCI codes
- **CausalVariable nodes**: created for each variable, linked to OntologyConcept via `MAPS_TO`
- **CAUSES relationships** with properties:
  - `algorithms`: list of algorithms that found the edge
  - `confidence`: fraction of algorithms
  - `edge_type`: `-->` or `---`
  - `uri`: `ro:RO_0002411` (causally_upstream_of from Relation Ontology)
  - `discovery_method`: `causal_learn`
  - `discovered_at`: timestamp
- **Outputs**: CAUSES edges in Neo4j, `causal/causes_embedding_report.json`

---

## Pipeline Integration

- All 3 steps registered in `pipeline.py` with config toggles:
  - `run_causal_feature_extraction`, `run_causal_discovery`, `run_embed_causal_edges`
- Config defaults to `False` — set `true` in `config.yaml` to enable
- Each step runs standalone: `python steps/step21_extract_causal_features.py`, etc.
- Steps 21 and 23 accept a Neo4j connector from the pipeline; Step 22 is self-contained (reads CSV)

---

## Configuration

Located in `config.yaml` under the `causal:` section:

```yaml
causal:
  alpha: 0.05           # Significance level for CI tests
  algorithms: ["PC", "FCI", "GES"]
  consensus_threshold: 2 # Edges found by ≥N algorithms are kept
  independence_test: "kci"
  max_missing_pct: 0.5
  imputation_method: "mice"
  feature_selection: true
  output_dir: "causal"
```

---

## Expected Graph Changes After Phase 2

| Metric | Expected |
|---|---|
| CausalVariable nodes | ~15–20 (one per feature column) |
| CAUSES edges | Depends on data — typically 10–30 consensus edges |
| MAPS_TO edges (new) | ~15–20 (CausalVariable → OntologyConcept) |
| Expected causal chain | Amyloid → Tau → Neurodegeneration → Cognitive decline |
| Relationship URI | `ro:RO_0002411` (causally_upstream_of) |

---

## Files Created

| File | Lines | Purpose |
|---|---|---|
| `steps/step21_extract_causal_features.py` | ~370 | 7 Cypher queries → feature matrix |
| `steps/step22_causal_discovery.py` | ~340 | PC/FCI/GES + consensus |
| `steps/step23_embed_causal_edges.py` | ~290 | CAUSES edges + CausalVariable nodes |

## Files Modified

| File | Changes |
|---|---|
| `pipeline.py` | 3 imports + 3 run blocks + 3 wrapper methods |

## Dependencies Added

| Package | Version | Purpose |
|---|---|---|
| `causal-learn` | latest | PC, FCI, GES causal discovery algorithms |

---

## What's Next

### Phase 3: Validation & Integration (Steps 24-26)
- [ ] AlzKB Bridge — external knowledge base alignment via SAME_AS edges
- [ ] Validate causal edges against known AD biology (precision/recall)
- [ ] DoWhy causal inference — effect estimation + refutation tests

### Phase 4: Documentation & Defense Prep (Steps 27-28)
- [ ] Final statistics report (JSON + Markdown)
- [ ] Thesis figures (schema diagram, causal graph, ICD-10 tree)
