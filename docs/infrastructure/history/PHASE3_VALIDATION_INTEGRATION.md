# Phase 3: Validation & Integration — History

## Overview

Phase 3 adds external knowledge integration (AlzKB), causal edge validation against literature ground truth, and quantitative causal effect estimation using DoWhy.

## Steps Implemented

### Step 24: AlzKB Bridge (`step24_alzkb_bridge.py`)

- Downloads AlzKB v2.0.0 CYPHERL dump from GitHub Releases
- Parses CREATE statements via regex to extract AD-relevant concepts (Gene, Disease, Anatomy, BiologicalProcess, Pathway, Drug)
- Falls back to 50 manually curated concepts if download fails
- Creates `AlzKBConcept` nodes with `alzkb:` namespace prefix
- Creates `SAME_AS` edges to `OntologyConcept` and `CausalVariable` nodes
- Matching methods: manual mapping (11 rules) + fuzzy label matching

### Step 25: Validate Causal Edges (`step25_validate_causal.py`)

- Defines 18 ground-truth causal edges from the amyloid cascade hypothesis and published AD literature
- Compares discovered CAUSES edges against ground truth
- Computes: precision, recall, F1, SHD (Structural Hamming Distance)
- Cross-references with AlzKB relationships via SAME_AS paths
- Marks validated edges: `SET r.validated_by_literature = true`
- Generates `thesis_output/validation_report.md` and `thesis_output/validation_metrics.json`

### Step 26: DoWhy Causal Inference (`step26_dowhy_inference.py`)

- Builds `CausalModel` from consensus DAG (GML format) + feature CSV
- Runs 5 treatment-outcome pairs: ABETA→TAU, TAU→Hippocampus, APOE→ABETA, age→Hippocampus, education→MMSE
- Estimates causal effects via backdoor linear regression
- Runs 3 refutation tests per pair: placebo_treatment, data_subset, random_common_cause
- Outputs: `causal/dowhy_results.json`

## Pipeline Integration

- 3 imports added to `pipeline.py`
- 3 run blocks guarded by config flags: `run_alzkb_bridge`, `run_evaluate_causality`, `run_dowhy_inference`
- 3 execution methods: `_execute_alzkb_bridge`, `_execute_validate_causal`, `_execute_dowhy_inference`

## Config

Config flags at lines 183-188 of `config.yaml` (pre-existing).
AlzKB config at lines 211-215 (`alzkb.github_url`, `alzkb.max_concepts`, `alzkb.cache_dir`).

## Dependencies

- `dowhy` (v0.14) — installed via pip

## Expected Graph Changes

| Element | Count | Node/Rel |
|---|---|---|
| `:AlzKBConcept` nodes | 50-200 | Node |
| `:ALZKB_RELATES_TO` rels | ~18 | Rel |
| `:SAME_AS` edges | ≥10 | Rel |
| Updated `:CAUSES` properties | all | Rel (validated_by_literature) |

## Status

- ✅ All scripts compile
- ✅ DoWhy import verified
- ⏳ Live Neo4j verification pending (T24.8)

## Next Phase

Phase 4: Documentation & Defense Prep (Steps 27-28)
