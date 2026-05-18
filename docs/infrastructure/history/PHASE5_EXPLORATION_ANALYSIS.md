# Phase 5: Exploration & Analysis — History

**Completed:** 2026-03-31
**Pipeline:** `pipeline.py` (modular orchestrator, config.yaml-driven)

---

> **Historical document — captured 2026-03-31.**
> For current canonical state (post the 2026-05-16 enrichment that added Biolink + MONDO + DOID + partial HPO expansion via steps 30/33/34) see [`outputs/metrics/canonical_snapshot.json`](../../../outputs/metrics/canonical_snapshot.json) and [`docs/final_report/c7_plan_v3/history/IMPLEMENTATION_HISTORY_2026-05-16.md`](../../final_report/c7_plan_v3/history/IMPLEMENTATION_HISTORY_2026-05-16.md). The step-29 EDA figures captured below were generated from the pre-enrichment graph; the underlying counts have since shifted.

---

## What Was Done

### Step 29: Knowledge Graph EDA (`step29_kg_eda.py`)
- Created `steps/step29_kg_eda.py` (1,171 lines)
- Generates **15 publication-quality figures** from live Neo4j queries
- All outputs in `outputs/eda_figures/` as SVG + 300 DPI PNG

| # | Figure | Description |
|---|---|---|
| 1 | Node type distribution | Horizontal bar chart of all node labels with counts |
| 2 | Relationship type distribution | Horizontal bar chart of all relationship types |
| 3 | Diagnosis breakdown | CN / MCI / EMCI / LMCI / AD distribution |
| 4 | Cognitive score distributions | MMSE, CDR-SB, ADAS-Cog box plots by diagnosis |
| 5 | Biomarker distributions | CSF Abeta42, Tau, pTau by diagnosis group |
| 6 | Visit frequency | Longitudinal visit code histogram |
| 7 | Patient degree distribution | Connectivity histogram (how many edges per patient) |
| 8 | Ontology coverage | SNOMED, LOINC, UBERON, ICD-10, HPO mapping rates |
| 9 | Imaging modality breakdown | MRI vs PET scan distribution |
| 10 | Graph density heatmap | Node-type-to-node-type adjacency density |
| 11 | Top hub nodes | Most connected nodes by degree centrality |
| 12 | Temporal coverage | Visit timeline coverage across cohorts |
| 13 | Data completeness | Missing property rates per node type |
| 14 | KG summary dashboard | Single-page infographic with key metrics |
| 15 | Multi-panel thesis figure | Combined figure for thesis defense |

**Bug fixed:** Node count inflation (542.2K → 421K). The original code summed per-label counts from `db.labels()`, which double-counts multi-labeled nodes. Fixed to use `MATCH (n) RETURN count(n)` for the true total.

### Cypher Explorer (`docs/cypher_explorer.cypher`)
- Created `docs/cypher_explorer.cypher` (633 lines)
- **12 sections** with 50+ guided Cypher queries for Neo4j Browser:
  1. Overview & Schema Discovery
  2. Patient Demographics
  3. Diagnosis & Disease Progression
  4. Cognitive Assessments
  5. Biomarkers (CSF, PET, ATN)
  6. Medical Imaging
  7. Family History & Genetics
  8. Ontology & Semantic Layer
  9. Temporal Patterns (Visits)
  10. Graph Topology & Connectivity
  11. Cross-Domain Queries
  12. Data Quality & Completeness
- Queries return `p, r, n` (not `path`) for proper graph bubble rendering in Neo4j Browser

---

## Pipeline Integration

- 1 import added to `pipeline.py`
- 1 run block: `run_kg_eda`
- 1 execution method: `_execute_kg_eda`
- Config flag: `run_kg_eda` in `config.yaml`

---

## Files Created

| File | Lines | Purpose |
|---|---|---|
| `steps/step29_kg_eda.py` | 1,171 | EDA figure generation from Neo4j |
| `docs/cypher_explorer.cypher` | 633 | Guided Cypher query reference |

## Files Modified

| File | Changes |
|---|---|
| `pipeline.py` | 1 import + 1 run block + 1 wrapper method |
| `config.yaml` | `run_kg_eda` toggle |

---

## Output Directory

`outputs/eda_figures/` — 15 figures, each in SVG + PNG format.

---

## Pipeline Idempotency Fixes

### step15_event_based_model.py — CREATE → MERGE
- Changed **11 CREATE statements** to MERGE for idempotent event creation
- All Event, EventChain, PatientTimeline, EventPattern, ProgressionPattern nodes now use MERGE on deterministic IDs
- Added `ON CREATE SET created_at`, `SET updated_at` pattern

### step4_extract_family.py — Deterministic member_id
- Replaced `uuid.uuid4()` with `hashlib.md5(ptid + relationship_type + column)` for deterministic FamilyMember IDs
- Added `ptid` parameter to `_extract_family_member_from_column()`

### step7_batch_insert.py — Deterministic batch_id
- Replaced `timestamp + uuid` batch_id with date-only `batch_YYYYMMDD`

### step5_improved_process_images.py — J2K Diagnostic
- Added end-of-processing diagnostic check for JPEG2000 conversion status
- Logs warning if glymur is available but no J2K files were generated

---

## Thesis Figure Improvements

### lpg_vs_kg_query Redesign (step28_thesis_figures.py)
- Replaced plain-text code boxes with visual graph diagrams
- Left panel: LPG with 3 nodes (Patient→Visit→Diagnosis)
- Right panel: KG with full semantic layer (MAPS_TO, SAME_AS, CAUSES edges)
- Uses FancyBboxPatch for nodes, annotate with arrowprops for edges

### Mermaid Versions (thesis_output/mermaid/)
Created 5 Overleaf-compatible Mermaid diagrams:

| File | Description |
|---|---|
| `kg_schema.mmd` | Full KG schema, 17 node types, color-coded by category |
| `lpg_vs_kg.mmd` | Side-by-side LPG vs KG comparison |
| `atn_cascade.mmd` | ATN biomarker cascade with CAUSES edges |
| `icd10_tree.mmd` | ICD-10 hierarchy (G30 + F00 branches) |
| `causal_overlay.mmd` | Consensus causal discovery graph |

### ICD-10 Cypher Queries (docs/cypher_explorer.cypher)
Added queries 8.6–8.9:
- 8.6: CLASSIFIED_AS → OntologyConcept mapping
- 8.7: IS_A hierarchy traversal
- 8.8: Coverage gap analysis (unmapped diagnoses)
- 8.9: Full semantic chain (Patient → Diagnosis → ICD-10)

---

## Files Created

| File | Lines | Purpose |
|---|---|---|
| `steps/step29_kg_eda.py` | 1,171 | EDA figure generation from Neo4j |
| `docs/cypher_explorer.cypher` | 660+ | Guided Cypher query reference |
| `thesis_output/mermaid/kg_schema.mmd` | — | KG schema (Mermaid) |
| `thesis_output/mermaid/lpg_vs_kg.mmd` | — | LPG vs KG comparison (Mermaid) |
| `thesis_output/mermaid/atn_cascade.mmd` | — | ATN cascade (Mermaid) |
| `thesis_output/mermaid/icd10_tree.mmd` | — | ICD-10 hierarchy (Mermaid) |
| `thesis_output/mermaid/causal_overlay.mmd` | — | Causal graph (Mermaid) |

## Files Modified

| File | Changes |
|---|---|
| `pipeline.py` | 1 import + 1 run block + 1 wrapper method |
| `config.yaml` | `run_kg_eda` toggle |
| `steps/step15_event_based_model.py` | 11 CREATE → MERGE for idempotency |
| `steps/step4_extract_family.py` | Deterministic member_id (hashlib) |
| `steps/step7_batch_insert.py` | Deterministic batch_id (date-only) |
| `steps/step5_improved_process_images.py` | J2K diagnostic check |
| `steps/step28_thesis_figures.py` | Redesigned lpg_vs_kg_query figure |

---

## Output Directories

- `outputs/eda_figures/` — 15 EDA figures (SVG + PNG)
- `thesis_output/` — 5 thesis figures (SVG + PNG + DOT source)
- `thesis_output/mermaid/` — 5 Mermaid diagrams for Overleaf
- `thesis_output/overleaf/` — Rendered SVGs for LaTeX import

---

## Status

- ✅ Step 29 compiles and generates all figures
- ✅ Cypher explorer tested against live Neo4j
- ✅ Node count bug fixed (multi-label inflation)
- ✅ Graph bubble rendering fixed (return nodes, not paths)
- ✅ Pipeline idempotency fixed (step15, step4, step7)
- ✅ ICD-10 queries added to cypher explorer
- ✅ lpg_vs_kg_query redesigned as visual graph diagram
- ✅ 5 Mermaid diagrams created for Overleaf
- ✅ J2K diagnostic check added to step5
- ⏳ System Graphviz needed to render DOT → SVG for overleaf/
