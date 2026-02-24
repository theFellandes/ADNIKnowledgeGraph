# ADNI Knowledge Graph — Implementation Plan v3

## Executive Summary

**Project:** Transform the ADNI Labeled Property Graph (LPG) into a Semantic Knowledge Graph (KG) with causal discovery capabilities.

**Current State (as of Feb 2026):**
- 16 pipeline steps implemented (step1–step16) in `pipeline.py`
- Neo4j LPG: ~407K nodes, ~1.16M relationships
- 108 ADNI tables ingested (5,608 columns across 108 tables in `headers.json`)
- Elasticsearch + Redis integrated
- Multi-tier image storage (DICOM → TIFF/PNG → JPEG thumbnails)
- GitHub repo: `github.com/theFellandes/ADNIKnowledgeGraph`

**Target State (by May 2026 defense):**
- Semantic KG with formal ontology grounding (SNOMED-CT, LOINC, UBERON, ICD-10)
- Hybrid architecture: Neo4j (in-place ontology) + SPARQL (disease classification)
- Composite unique constraints on all observation nodes
- Causal discovery overlay (PC, FCI, GES algorithms)
- AlzKB bridge for literature validation
- JPEG2000/HTJ2K lossless image pipeline
- Dynamic graph with hash-based change detection + audit trail
- Standalone insertion mechanism for incremental data loading

**Timeline:** February 24 – May 2026 (defense)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ADNI Data Sources                               │
│   108 CSV Tables (5,608 cols)    DICOM Images (MRI, PET)           │
└───────────────┬────────────────────────────┬────────────────────────┘
                │                            │
    ┌───────────▼────────────┐   ┌──────────▼───────────────┐
    │  insertion_main.py     │   │  step5 Image Pipeline    │
    │  (NEW: Standalone      │   │  DICOM→J2K/TIFF/PNG/JPG │
    │   entry point)         │   └──────────┬───────────────┘
    │  Skips steps 1-4 if    │              │
    │  graph already exists  │              │
    └───────────┬────────────┘              │
                │                            │
    ┌───────────▼────────────────────────────▼──────────────────┐
    │                Multi-Tier Storage                          │
    │  ┌──────────┐  ┌────────────┐  ┌───────┐  ┌───────────┐ │
    │  │ Neo4j KG │  │Elasticsearch│  │ Redis │  │ File Sys  │ │
    │  │ 407K+    │  │  Metadata   │  │ Cache │  │ DICOM/J2K │ │
    │  │ nodes    │  │  Index      │  │       │  │ TIFF/PNG  │ │
    │  └──────────┘  └────────────┘  └───────┘  └───────────┘ │
    └──────────────────────────────────────────────────────────┘
                │
    ┌───────────▼──────────────────────────────────────────────┐
    │  Semantic Enhancement (Steps 17–20)                       │
    │  Constraints → Ontology Props → ICD-10 → MAPS_TO Layer   │
    └───────────┬──────────────────────────────────────────────┘
                │
    ┌───────────▼──────────────────────────────────────────────┐
    │  Causal Discovery (Steps 21–23)                           │
    │  Feature Extract → PC/FCI/GES → CAUSES Edges in KG       │
    └───────────┬──────────────────────────────────────────────┘
                │
    ┌───────────▼──────────────────────────────────────────────┐
    │  Validation (Steps 24–26)                                 │
    │  AlzKB Bridge → Validate Causal → DoWhy Inference         │
    └──────────────────────────────────────────────────────────┘
```

---

## Gap Analysis: What Exists vs. What's Missing

### ✅ COMPLETED (Steps 1–16)

| Step | File | Description |
|------|------|-------------|
| 1 | `step1_database_setup.py` | Neo4j + Elasticsearch setup, basic constraints |
| 2 | `step2_load_tables.py` | Load 108 ADNI CSV tables into staging |
| 3 | `step3_create_patients.py` | Patient node creation from PTDEMOG |
| 4 | `step4_extract_family.py` | Family history extraction (FAMHXPAR, FAMHXSIB, FHQ) |
| 5 | `step5_improved_process_images.py` | DICOM/NIfTI → TIFF/PNG/thumbnails (**NO JPEG2K**) |
| 6 | `step6_extract_findings_robust.py` | Clinical findings extraction |
| 7 | `step7_batch_insert.py` | Batch insert (**NO hash detection, NO audit trail**) |
| 8 | `step8_create_relationships.py` | HAS_VISIT, HAS_DIAGNOSIS, FOLLOWED_BY etc. |
| 9 | `step9_knowledge_graph_enhancer.py` | Semantic relationship enrichment (ATN, risk factors) |
| 10 | `step10_execute_queries.py` | Query execution & reporting |
| 11 | `step11_biomarker_analysis.py` | Biomarker analysis |
| 12 | `step12_complete_graph_enhancement.py` | Graph enhancement |
| 13 | `step13_graph_eda.py` | Exploratory data analysis |
| 14 | `step14_test_queries.py` | Research query testing |
| 15 | `step15_event_based_model.py` | Event-based graph model |
| 16 | `step16_create_metrics.py` | Performance metrics |

### ❌ MISSING — Must Be Built

| Priority | Component | What | Why It Matters |
|----------|-----------|------|----------------|
| **P0** | `insertion_main.py` | Standalone insertion entry point | Allows incremental data loading without rerunning full pipeline |
| **P0** | step17 | Composite unique constraints | Prevents duplicates — Prof. Turhan's feedback |
| **P0** | step18 | Ontology properties (in-place) | Transforms LPG→KG. Adds SNOMED, LOINC, UBERON codes |
| **P0** | step19 | ICD-10 via WHO API + rdflib | Disease classification hierarchy — hybrid architecture |
| **P0** | step20 | OntologyConcept + MAPS_TO layer | Semantic backbone — enables machine reasoning |
| **P1** | step5b | JPEG2000/HTJ2K conversion | Lossless archival format, better compression than TIFF |
| **P1** | step7b | Hash-based change detection | Dynamic graph per Dr. Baazaoui's requirement |
| **P1** | step21 | Extract causal feature matrix | Flat CSV from KG for causal algorithms |
| **P1** | step22 | Causal discovery (PC/FCI/GES) | Core thesis contribution |
| **P1** | step23 | Embed CAUSES edges | Discovered edges become native KG relationships |
| **P2** | step24 | AlzKB bridge (SAME_AS) | Literature validation layer |
| **P2** | step25 | Validate causal edges | Precision/recall vs. known AD biology |
| **P2** | step26 | DoWhy causal inference | Estimate causal effects + refutation tests |
| **P3** | step27 | Final statistics & report | Thesis methodology section data |
| **P3** | step28 | Thesis figures (SVG/PNG) | Publication-quality diagrams |

### ⚠️ PARTIALLY DONE — Needs Improvement

| Component | Current State | What's Missing |
|-----------|---------------|----------------|
| **Image pipeline (step5)** | DICOM→TIFF/PNG/JPEG thumbnail | JPEG2000/HTJ2K lossless conversion |
| **Batch insertion (step7)** | Basic MERGE upsert | SHA-256 hash detection, BatchIngestion audit nodes |
| **Relationship semantics** | String-typed edges (HAS_VISIT etc.) | No `uri` properties (e.g., `ro:RO_0000056`) |
| **Node type annotations** | No `rdf_type` on any nodes | Patient→ncit:C16960, Visit→ncit:C159705 |
| **pipeline.py** | Steps 1–15 registered | Steps 16–28 not registered, no insertion mode |

---

## NEW: Standalone Insertion Mechanism (`insertion_main.py`)

### Design Rationale

The current `pipeline.py` runs all 16 steps sequentially. For incremental data loading (new ADNI data releases, corrections, additions), we need a standalone entry point that:
1. **Skips** infrastructure steps (1-2) if Neo4j + ES are already running
2. **Skips** patient/family creation (3-4) if patients already exist
3. **Runs** only the data insertion and enhancement steps
4. **Runs** the new semantic steps (17-20) on demand
5. **Provides** a `--step` flag to run individual steps or ranges

### Architecture

```python
# insertion_main.py — Standalone insertion entry point
#
# Usage:
#   python insertion_main.py --config config.yaml                    # Run all insertable steps
#   python insertion_main.py --config config.yaml --step 7           # Run only step 7
#   python insertion_main.py --config config.yaml --step 7-9         # Run steps 7 through 9
#   python insertion_main.py --config config.yaml --step 17,18,19    # Run specific steps
#   python insertion_main.py --config config.yaml --from-step 17     # Run from step 17 onward
#   python insertion_main.py --config config.yaml --phase semantic   # Run all semantic steps
#   python insertion_main.py --config config.yaml --phase causal     # Run all causal steps
#
# Phases:
#   setup       = steps 1-2   (database + table loading)
#   ingest      = steps 3-8   (patient creation through relationships)
#   enhance     = steps 9-16  (knowledge graph enhancement + analysis)
#   semantic    = steps 17-20 (ontology properties, ICD-10, MAPS_TO)
#   causal      = steps 21-23 (feature extraction, discovery, embedding)
#   validate    = steps 24-26 (AlzKB, validation, DoWhy)
#   report      = steps 27-28 (statistics, figures)
#   image_extra = step 5b     (JPEG2000 conversion)
#   hash_detect = step 7b     (hash-based change detection upgrade)
```

### Step Registry Pattern

```python
STEP_REGISTRY = {
    # Phase: setup
    1:  ("Database Setup",           "step1_database_setup",          "execute_database_setup"),
    2:  ("Load Tables",              "step2_load_tables",             "execute_table_loading"),
    # Phase: ingest
    3:  ("Create Patients",          "step3_create_patients",         "execute_patient_creation"),
    4:  ("Extract Family",           "step4_extract_family",          "execute_family_extraction_fixed"),
    5:  ("Process Images",           "step5_improved_process_images", "execute_enhanced_image_processing"),
    6:  ("Extract Findings",         "step6_extract_findings_robust", "execute_findings_extraction_fixed"),
    7:  ("Batch Insert",             "step7_batch_insert",            "execute_batch_insertion_fixed"),
    8:  ("Create Relationships",     "step8_create_relationships",    "execute_comprehensive_relationship_creation"),
    # Phase: enhance
    9:  ("Enhance KG",               "step9_knowledge_graph_enhancer","enhance_knowledge_graph"),
    10: ("Execute Queries",          "step10_execute_queries",        "execute_adni_queries"),
    11: ("Biomarker Analysis",       "step11_biomarker_analysis",     "execute_biomarker_analysis_fixed"),
    12: ("Graph Enhancement",        "step12_complete_graph_enhancement","execute_complete_graph_enhancement"),
    13: ("Graph EDA",                "step13_graph_eda",              "execute_graph_eda"),
    14: ("Research Queries",         "step14_test_queries",           "execute_research_queries"),
    15: ("Event-Based Model",        "step15_event_based_model",      "execute_event_based_model"),
    16: ("Metrics",                  "step16_create_metrics",         "execute_metrics"),
    # Phase: semantic (NEW)
    17: ("Apply Constraints",        "step17_apply_constraints",      "execute_apply_constraints"),
    18: ("Ontology Properties",      "step18_add_ontology_properties","execute_add_ontology_properties"),
    19: ("ICD-10 Integration",       "step19_icd10_integration",      "execute_icd10_integration"),
    20: ("Ontology Layer",           "step20_ontology_layer",         "execute_ontology_layer"),
    # Phase: causal (NEW)
    21: ("Causal Features",          "step21_extract_causal_features","execute_causal_feature_extraction"),
    22: ("Causal Discovery",         "step22_causal_discovery",       "execute_causal_discovery"),
    23: ("Embed CAUSES",             "step23_embed_causal_edges",     "execute_embed_causal_edges"),
    # Phase: validate (NEW)
    24: ("AlzKB Bridge",             "step24_alzkb_bridge",           "execute_alzkb_bridge"),
    25: ("Validate Causal",          "step25_validate_causal",        "execute_validate_causal"),
    26: ("DoWhy Inference",          "step26_dowhy_inference",        "execute_dowhy_inference"),
    # Phase: report (NEW)
    27: ("Final Stats",              "step27_final_stats",            "execute_final_stats"),
    28: ("Thesis Figures",           "step28_thesis_figures",         "execute_thesis_figures"),
}

PHASE_MAP = {
    "setup":       [1, 2],
    "ingest":      [3, 4, 5, 6, 7, 8],
    "enhance":     [9, 10, 11, 12, 13, 14, 15, 16],
    "semantic":    [17, 18, 19, 20],
    "causal":      [21, 22, 23],
    "validate":    [24, 25, 26],
    "report":      [27, 28],
    "image_extra": ["5b"],
    "hash_detect": ["7b"],
}
```

### Key Design Decisions

1. **Lazy imports**: Steps are imported only when needed via `importlib`, so missing step files don't crash the whole runner
2. **Config inheritance**: `insertion_main.py` reads `config.yaml` just like `pipeline.py`
3. **Progress tracking**: Each step records success/failure/skip in a JSON log
4. **Resumable**: On failure, the runner logs which step failed; next run with `--from-step N` resumes
5. **Backward compatible**: `pipeline.py` remains unchanged — `insertion_main.py` is additive

---

## Phase 1: Schema Migration (LPG → KG)

**Duration:** ~2 weeks  
**Goal:** Transform existing LPG into a semantically grounded KG without rebuilding.

### Step 17: Apply Composite Unique Constraints

**File:** `steps/step17_apply_constraints.py`  
**Dependencies:** Neo4j 5.x (composite constraints require it)

Creates:
- 6 core uniqueness constraints: patient_ptid, visit_id, mri_image_id, pet_image_id, brain_region, ontology_uri
- 6 composite observation constraints: assess_unique(visit_id, test_name), csf_unique(visit_id, assay), blood_unique(visit_id, analyte, assay), vol_unique(visit_id, region_name, hemisphere), atn_unique(visit_id), dx_unique(visit_id, dx_label)
- 15+ performance indexes on query-anchor properties

**IMPORTANT:** Must verify Neo4j version first. If < 5.x, composite constraints are not supported — use node key constraints as fallback. Check actual property names on nodes before creating constraints (existing nodes may use different names than Blueprint assumes).

### Step 18: Add Ontology Properties (In-Place Upgrade)

**File:** `steps/step18_add_ontology_properties.py`  
**Dependencies:** Step 17 complete

Adds ontology codes to existing nodes via Cypher `SET`:
- Diagnosis → `snomed_code`, `icd10_code`, `mondo_code`
- CognitiveAssessment → `loinc_code` (MMSE→72106-8, CDR→72172-0, etc.)
- CSFBiomarker → `loinc_code` (Abeta42→72333-6, tau→72335-1, etc.)
- BrainRegion → `uberon_code` (Hippocampus→0002421, etc.)
- Patient → `rdf_type: ncit:C16960`
- Visit → `rdf_type: ncit:C159705`
- All relationship types → `uri` property (e.g., HAS_VISIT → `ro:RO_0000056`)

**CRITICAL:** Must first check what property names and node labels actually exist in the current graph. The existing `step7_batch_insert.py` and `step8_create_relationships.py` may use different property names than the Blueprint assumes. Run exploration queries first.

### Step 19: ICD-10 Integration via WHO API + rdflib

**File:** `steps/step19_icd10_integration.py`  
**Dependencies:** WHO ICD API credentials or FBK ICD-10 OWL file

**IMPORTANT:** BioPortal SPARQL endpoint is SHUT DOWN. Use:
1. **Primary:** Static mapping from `ontology/icd10_mappings.json` (fastest, no external dependency)
2. **Secondary:** WHO ICD REST API with OAuth2 (live hierarchy resolution)
3. **Tertiary:** Local rdflib on downloaded FBK ICD-10 OWL file

ICD-10 mapping for ADNI diagnoses:
- AD → G30.9, MCI → F06.7, CN → Z03.89, Dementia → F03.9
- Creates OntologyConcept nodes + IS_A hierarchy + CLASSIFIED_AS edges

### Step 20: OntologyConcept Layer + MAPS_TO

**File:** `steps/step20_ontology_layer.py`  
**Dependencies:** Steps 18, 19 complete

Imports ~200 curated concepts from SNOMED-CT, LOINC, UBERON, HPO into OntologyConcept nodes with IS_A hierarchies. Creates MAPS_TO edges from every data node with an ontology code to its corresponding OntologyConcept.

---

## Phase 1.5: Image Pipeline & Insertion Enhancements

### Step 5b: JPEG2000/HTJ2K Support

**File:** Extend `step5_improved_process_images.py` or create `step5b_jpeg2k_conversion.py`

Adds a new tier to the multi-tier image storage:
- **Tier 1:** DICOM originals (preserved)
- **Tier 2:** JPEG2000 lossless (.j2k) via `glymur` or `imagecodecs` — **NEW**
- **Tier 3:** TIFF lossless (existing)
- **Tier 4:** PNG lossless (existing)
- **Tier 5:** JPEG thumbnails 256×256 (existing)

**Library choice:** `glymur` (Python binding for OpenJPEG) for J2K. HTJ2K support depends on OpenJPEG version ≥2.5.

### Step 7b: Hash-Based Change Detection + Audit Trail

**File:** Enhance `step7_batch_insert.py` or create wrapper

Adds to the batch insertion process:
1. SHA-256 hash computation per row (key columns only)
2. ON CREATE SET `data_hash`, `created_at`, `batch_id`, `source_table`
3. ON MATCH: skip if hash matches, update if changed
4. `BatchIngestion` meta-nodes logging each run (rows_processed, created, updated, skipped)

---

## Phase 2: Causal Discovery

**Duration:** ~2 weeks

### Step 21: Extract Causal Feature Matrix

**File:** `steps/step21_extract_causal_features.py`

Cypher query extracts baseline-visit data: MMSE, CDR, ADAS-Cog, Abeta42, tau, ptau, ratio_42_40, APOE genotype, ATN status, age, education, sex, hippocampal volume. Output: `causal/causal_features.csv`.

### Step 22: Causal Discovery Algorithms

**File:** `steps/step22_causal_discovery.py`  
**Dependencies:** `pip install causal-learn`

Runs PC, FCI (priority — handles latent confounders), GES in parallel. Generates consensus edges (found by ≥2 algorithms). FCI is prioritized based on Shen et al. (2020) validation on ADNI data.

### Step 23: Embed CAUSES Edges in KG

**File:** `steps/step23_embed_causal_edges.py`

Creates native CAUSES relationships in Neo4j with metadata: algorithm, p_value, effect_size, uri (`ro:RO_0002411`).

---

## Phase 3: Validation & Integration

**Duration:** ~2 weeks

### Step 24: AlzKB Bridge → Step 25: Validate Causal → Step 26: DoWhy Inference

Import ~200 AlzKB concepts, create SAME_AS edges, validate causal edges against known AD biology, run DoWhy for causal effect estimation.

---

## Phase 4: Documentation & Defense Prep

### Step 27: Final Statistics → Step 28: Thesis Figures

Generate publication-quality SVG figures and comprehensive statistics for thesis.

---

## Execution Order & Dependencies

```
Phase 1 (LPG→KG):
  step17_apply_constraints ─────┐
                                ├── step18_add_ontology_properties ──┐
                                │                                     ├── step19_icd10_integration
                                │                                     ├── step20_ontology_layer
  step5b_jpeg2k_conversion      │   (parallel)                       │
  step7b_hash_detection ────────┘                                    │
                                                                     │
Phase 2 (Causal Discovery):                                          │
  step21_extract_causal_features ◄──────────────────────────────────┘
  step22_causal_discovery ◄── step21
  step23_embed_causal_edges ◄── step22

Phase 3 (Validation):
  step24_alzkb_bridge ◄── step20
  step25_validate_causal ◄── step23, step24
  step26_dowhy_inference ◄── step22

Phase 4 (Documentation):
  step27_final_stats ◄── all above
  step28_thesis_figures ◄── all above
```

---

## Success Criteria

By thesis defense:
- [ ] ~407K+ data nodes + ~200 OntologyConcept nodes + ICD-10 hierarchy
- [ ] Composite unique constraints on ALL observation nodes
- [ ] MAPS_TO edges: ≥80% of data nodes with ontology codes linked
- [ ] CLASSIFIED_AS edges: All Diagnosis nodes → ICD-10
- [ ] IS_A hierarchy: ICD-10 + SNOMED-CT concepts
- [ ] Causal discovery from ≥3 algorithms (PC, FCI, GES)
- [ ] CAUSES edges with metadata (algorithm, p_value, confidence)
- [ ] AlzKB bridge with SAME_AS edges
- [ ] Validation report: precision/recall vs. known AD biology
- [ ] Publication-quality SVG figures for thesis
- [ ] Hash-based change detection + BatchIngestion audit trail
- [ ] JPEG2000 lossless tier in image pipeline
- [ ] Standalone `insertion_main.py` with step-level control

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| WHO ICD API downtime | Low | Medium | Static JSON mapping as primary; API as enrichment |
| Neo4j < 5.x (no composite constraints) | Medium | High | Check version first; node key constraints fallback |
| Existing property names differ from Blueprint | **High** | Medium | Run exploration queries FIRST, adapt all Cypher |
| Causal-learn empty graph | Medium | Medium | Lower α to 0.1; use KCI for mixed data |
| AlzKB dump not downloadable | Medium | Low | Use paper tables; create 50 key concepts manually |
| BioPortal SPARQL down | **Confirmed** | High | Already mitigated: WHO REST API + local rdflib |
| Incomplete baseline data | Low | Medium | ADNI has ~2,400+ patients; even 30% → 700+ rows |

**Last updated:** 2026-02-23
