# ADNI Knowledge Graph — Implementation Plan

## Executive Summary

**Project:** Transform the ADNI Labeled Property Graph (LPG) into a Semantic Knowledge Graph (KG) with causal discovery capabilities.

**Current State (as of Feb 2026):**
- 16 pipeline steps implemented (step1–step16)
- Neo4j LPG: ~407K nodes, ~1.16M relationships
- 108 ADNI tables ingested (~5,800 columns)
- Elasticsearch + Redis integrated
- Multi-tier image storage (DICOM → TIFF/PNG → thumbnails)
- GitHub repo: `github.com/theFellandes/ADNIKnowledgeGraph`

**Target State (by May 2026 defense):**
- Semantic KG with formal ontology grounding (SNOMED-CT, LOINC, UBERON, ICD-10)
- Hybrid architecture: Neo4j (in-place ontology) + SPARQL (disease classification)
- Composite unique constraints on all observation nodes
- Causal discovery overlay (PC, FCI, GES algorithms)
- AlzKB bridge for literature validation
- JPEG2000/HTJ2K lossless image pipeline
- Dynamic graph with hash-based change detection

**Timeline:** February 24 – May 2026 (defense)

---

## Gap Analysis: What Exists vs. What's Missing

### ✅ COMPLETED (Steps 1–16)

| Step | File | Status | Description |
|------|------|--------|-------------|
| 1 | `step1_database_setup.py` | ✅ Done | Neo4j + Elasticsearch setup |
| 2 | `step2_load_tables.py` | ✅ Done | Load 108 ADNI CSV tables |
| 3 | `step3_create_patients.py` | ✅ Done | Create Patient nodes from PTDEMOG |
| 4 | `step4_extract_family.py` | ✅ Done | Family history extraction |
| 5 | `step5_improved_process_images.py` | ✅ Done | DICOM/NIfTI → TIFF/PNG/thumbnails |
| 6 | `step6_extract_findings_robust.py` | ✅ Done | Clinical findings extraction |
| 7 | `step7_batch_insert.py` | ✅ Done | Batch insert patients, visits, assessments |
| 8 | `step8_create_relationships.py` | ✅ Done | HAS_VISIT, HAS_DIAGNOSIS, etc. |
| 9 | `step9_knowledge_graph_enhancer.py` | ✅ Done | Basic graph enrichment |
| 10 | `step10_execute_queries.py` | ✅ Done | Query execution & reporting |
| 11 | `step11_biomarker_analysis.py` | ✅ Done | Biomarker analysis |
| 12 | `step12_complete_graph_enhancement.py` | ✅ Done | Graph enhancement |
| 13 | `step13_graph_eda.py` | ✅ Done | Exploratory data analysis |
| 14 | `step14_test_queries.py` | ✅ Done | Research query testing |
| 15 | `step15_event_based_model.py` | ✅ Done | Event-based graph model |
| 16 | `step16_create_metrics.py` | ✅ Done | Performance metrics |

### ❌ MISSING — Must Be Built

| Priority | Step | What | Why It Matters |
|----------|------|------|----------------|
| **P0** | step17 | Composite unique constraints | Prevents duplicates — Prof. Turhan's feedback |
| **P0** | step18 | Ontology properties (in-place) | Transforms LPG→KG. Adds SNOMED, LOINC, UBERON codes |
| **P0** | step19 | ICD-10 via WHO API + rdflib | Disease classification hierarchy — hybrid architecture |
| **P0** | step20 | OntologyConcept + MAPS_TO layer | The semantic backbone — enables machine reasoning |
| **P1** | step21 | Extract causal feature matrix | Flat CSV from KG for causal algorithms |
| **P1** | step22 | Causal discovery (PC/FCI/GES) | Core thesis contribution |
| **P1** | step23 | Embed CAUSES edges | Discovered edges become native KG relationships |
| **P2** | step24 | AlzKB bridge (SAME_AS) | Literature validation layer |
| **P2** | step25 | Validate causal edges | Precision/recall vs. known AD biology |
| **P2** | step26 | DoWhy causal inference | Estimate causal effects + refutation tests |
| **P3** | step27 | Final statistics & report | Thesis methodology section data |
| **P3** | step28 | Thesis figures (SVG/PNG) | Publication-quality diagrams |

### ⚠️ PARTIALLY DONE — Needs Completion

| Component | Current State | What's Missing |
|-----------|---------------|----------------|
| **Image pipeline (step5)** | DICOM→TIFF/PNG/thumbnail | JPEG2000/HTJ2K lossless conversion not implemented |
| **Batch insertion (step7)** | Basic upsert | No hash-based change detection, no SHA-256 dedup |
| **Dynamic graph** | MERGE-based upsert exists | No BatchIngestion audit trail nodes |
| **Relationship URIs** | String-typed edges | No `uri` properties on relationships (e.g., `ro:RO_0000056`) |
| **Node `rdf_type`** | Not present | Patient, Visit nodes lack `rdf_type` property |

---

## Phase 1: Schema Migration (LPG → KG)

**Duration:** ~2 weeks
**Goal:** Transform existing LPG into a semantically grounded KG without rebuilding.

### Step 17: Apply Composite Unique Constraints

**File:** `steps/step17_apply_constraints.py`
**Dependencies:** Neo4j 5.x (check with `CALL dbms.components()`)
**What it does:**
1. Create uniqueness constraints on all observation nodes (CognitiveAssessment, CSFBiomarker, BloodBiomarker, VolumetricMeasure, ATNProfile, Diagnosis)
2. Create performance indexes on frequently queried properties
3. Handle "already exists" errors gracefully

**Constraints to apply:**
```
Core: patient_ptid, visit_id, mri_image_id, pet_image_id, brain_region, ontology_uri
Composite: assess_unique(visit_id,test_name), csf_unique(visit_id,assay),
           blood_unique(visit_id,analyte,assay), vol_unique(visit_id,region_name,hemisphere),
           atn_unique(visit_id), dx_unique(visit_id,dx_label)
```

**Indexes to create:** 15 indexes on query-anchor properties (see Blueprint v2 Section 6).

**Verification query:**
```cypher
SHOW CONSTRAINTS
SHOW INDEXES
```

### Step 18: Add Ontology Properties (In-Place Upgrade)

**File:** `steps/step18_add_ontology_properties.py`
**Dependencies:** Step 17 complete
**What it does:**
1. Add `snomed_code`, `icd10_code`, `mondo_code` to Diagnosis nodes
2. Add `loinc_code` to CognitiveAssessment nodes (MMSE→72106-8, CDR→72172-0, etc.)
3. Add `loinc_code` to CSFBiomarker nodes (Abeta42→72333-6)
4. Add `uberon_code` to BrainRegion nodes (Hippocampus→0002421)
5. Add `rxnorm_code` to Medication nodes
6. Add `rdf_type` to Patient (ncit:C16960) and Visit (ncit:C159705) nodes
7. Add `uri` properties to all relationship types (e.g., HAS_VISIT→ro:RO_0000056)

**Mapping tables (hardcoded — verified against standards):**
```python
DIAGNOSIS_ONTOLOGY = {
    "AD":  {"snomed_code": "26929004", "icd10_code": "G30.9", "mondo_code": "MONDO:0004975"},
    "MCI": {"snomed_code": "386806002", "icd10_code": "F06.7", "mondo_code": "MONDO:0024647"},
    "CN":  {"snomed_code": "17621005", "icd10_code": "Z03.89"},
}
ASSESSMENT_LOINC = {
    "MMSE": "72106-8", "CDR": "72172-0", "ADAS": "72194-4",
    "MOCA": "72133-2", "FAQ": "72107-6", "GDS": "72166-2",
}
CSF_LOINC = {"Abeta42": "72333-6", "tau": "72332-8", "ptau": "72334-4"}
```

**Verification:**
```cypher
MATCH (d:Diagnosis) WHERE d.snomed_code IS NOT NULL RETURN d.dx_label, d.snomed_code LIMIT 5
MATCH (c:CognitiveAssessment) WHERE c.loinc_code IS NOT NULL RETURN c.test_name, c.loinc_code LIMIT 5
```

### Step 19: ICD-10 Integration via WHO API + rdflib

**File:** `steps/step19_icd10_integration.py`
**Dependencies:** WHO ICD API credentials, FBK ICD-10 OWL file (fallback)
**What it does:**
1. Query WHO ICD REST API for ICD-10 code hierarchy (G30.9 → G30 → G30-G32 → G20-G26)
2. Cache responses in `ontology/icd10_cache.json`
3. Fallback: Load FBK ICD-10 OWL file, query with rdflib SPARQL locally
4. Create OntologyConcept nodes for each ICD-10 code
5. Create IS_A relationships between ICD-10 concepts
6. Create CLASSIFIED_AS edges from Diagnosis nodes to ICD-10 concepts

**IMPORTANT:** BioPortal SPARQL endpoint is **SHUT DOWN**. Use WHO REST API (primary) + local rdflib (fallback).

**ICD-10 Mapping:**
```
AD → G30.9 (Alzheimer disease, unspecified) → G30 → G30-G32 → G20-G26
AD early → G30.0 → G30 → ...
AD late → G30.1 → G30 → ...
MCI → F06.7 (Mild cognitive disorder)
CN → Z03.89 (No diagnosis)
Dementia other → F03.9 (Unspecified dementia)
```

### Step 20: OntologyConcept Layer + MAPS_TO

**File:** `steps/step20_ontology_layer.py`
**Dependencies:** Steps 18, 19 complete
**What it does:**
1. Import ~200–300 curated concepts from SNOMED-CT, LOINC, UBERON, HPO
2. Build IS_A hierarchies within Neo4j (e.g., AD IS_A Dementia IS_A Neurodegeneration)
3. Create MAPS_TO relationships from data nodes to OntologyConcept nodes
4. Every data node with an ontology code gets a MAPS_TO edge

**Coverage targets:**
- Diagnosis → SNOMED-CT concepts → IS_A hierarchy
- CognitiveAssessment → LOINC concepts
- CSFBiomarker → LOINC concepts
- BrainRegion → UBERON concepts
- Medication → RxNorm concepts
- FamilyMember → HPO concepts

**Verification:**
```cypher
MATCH (n)-[:MAPS_TO]->(o:OntologyConcept) RETURN labels(n)[0], count(n) ORDER BY count(n) DESC
MATCH path = (:OntologyConcept {code: 'G30.9'})-[:IS_A*]->(p) RETURN [n in nodes(path) | n.label]
```

---

## Phase 1.5: Image Pipeline Enhancement

### Step 5b: JPEG2000/HTJ2K Lossless Conversion

**File:** Modify `steps/step5_improved_process_images.py` or create `step5b_jpeg2k_conversion.py`
**Dependencies:** `pip install pillow-heif openjpeg` or `glymur` for JPEG2000
**What it does:**
1. Add JPEG2000 (.j2k, .jp2) lossless output alongside existing TIFF/PNG
2. Add HTJ2K (High Throughput JPEG 2000) for faster decode
3. Update Elasticsearch image index with new format metadata
4. Maintain backward compatibility — existing TIFF/PNG pipeline unchanged

**Why:** The v2 Blueprint mentions multi-tier image storage. JPEG2000 provides better lossless compression than TIFF (~30–40% smaller) while maintaining diagnostic quality.

**Format tier:**
```
Tier 1: DICOM originals (preserved)
Tier 2: JPEG2000 lossless (.j2k) — archival quality
Tier 3: PNG lossless — web-compatible
Tier 4: JPEG thumbnails (256×256) — UI previews
```

### Step 7b: Hash-Based Change Detection + Audit Trail

**File:** Modify `steps/step7_batch_insert.py`
**What it adds:**
1. SHA-256 hash computation per row (key columns only)
2. ON CREATE SET `data_hash`, `created_at`, `batch_id`
3. ON MATCH: skip if hash matches, update if changed
4. BatchIngestion meta-nodes for audit trail
5. `source_table` property on all observation nodes

---

## Phase 2: Causal Discovery

**Duration:** ~2 weeks
**Goal:** Extract features from KG, run causal algorithms, embed results.

### Step 21: Extract Causal Feature Matrix

**File:** `steps/step21_extract_causal_features.py`
**What it does:**
1. Cypher query pulls baseline-visit data for all patients
2. Features: MMSE, CDR, ADAS-Cog, Abeta42, tau, ptau, ratio_42_40, APOE genotype, ATN status, age, education, sex, hippocampal volume
3. Handle missing data: drop patients with >50% missing, impute remainder
4. Output: `causal/causal_features.csv` (flat tabular format)
5. Report: completeness per variable, sample size, covariance matrix

**Feature extraction query:**
```cypher
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit {viscode: 'bl'})
OPTIONAL MATCH (v)-[:YIELDED_ASSESSMENT]->(c:CognitiveAssessment)
OPTIONAL MATCH (v)-[:HAS_CSF_BIOMARKER]->(csf:CSFBiomarker)
OPTIONAL MATCH (v)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
OPTIONAL MATCH (p)-[:HAS_GENETIC_PROFILE]->(g:GeneticProfile)
RETURN p.ptid, p.sex, p.birth_year, p.education_years,
       c.test_name, c.total_score, csf.abeta42, csf.tau, csf.ptau,
       d.dx_label, g.apoe_genotype
```

### Step 22: Causal Discovery Algorithms

**File:** `steps/step22_causal_discovery.py`
**Dependencies:** `pip install causal-learn`
**What it does:**
1. Load feature matrix from step21
2. Run PC algorithm (Fisher's Z, α=0.05)
3. Run FCI algorithm (handles latent confounders — PRIORITY per Shen et al. 2020)
4. Run GES algorithm (score-based)
5. Optionally run DAG-GNN (deep learning approach)
6. Generate consensus edges (found by ≥2 algorithms)
7. Output: `causal/consensus_edges.json`, visualization PNGs

**Expected results (based on Shen et al. 2020):**
- FCI should recover A→T→N cascade with expert priors
- Unguided FCI: ~71% precision
- Key edges: amyloid→tau, tau→neurodegeneration, APOE→amyloid

### Step 23: Embed CAUSES Edges in KG

**File:** `steps/step23_embed_causal_edges.py`
**What it does:**
1. Load consensus edges from step22
2. Create CAUSES relationships in Neo4j with metadata:
   - `algorithm` (which algorithms found it)
   - `p_value`, `effect_size`, `confidence`
   - `uri: "ro:RO_0002411"` (causally_upstream_of)
3. Connect to existing data nodes (e.g., CSFBiomarker→CognitiveAssessment)

---

## Phase 3: Validation & Integration

**Duration:** ~2 weeks

### Step 24: AlzKB Bridge

**File:** `steps/step24_alzkb_bridge.py`
**What it does:**
1. Import ~200 overlapping concepts from AlzKB (Romano et al. 2024)
2. Genes: APOE, APP, PSEN1, PSEN2, MAPT, BACE1
3. Biomarkers: Abeta42, tau, ptau, NfL
4. Brain regions: hippocampus, entorhinal cortex
5. Create SAME_AS (owl:sameAs) edges to OntologyConcept nodes

### Step 25: Validate Causal Edges

**File:** `steps/step25_validate_causal.py`
**What it does:**
1. Compare discovered CAUSES edges vs. AlzKB relationships
2. Compare vs. canonical A→T→N cascade (Jack et al. 2013)
3. Mark edges as `validated_by_literature=true/false`
4. Compute precision/recall vs. known AD biology
5. Output: `thesis_output/validation_report.md`

### Step 26: DoWhy Causal Inference

**File:** `steps/step26_dowhy_inference.py`
**Dependencies:** `pip install dowhy`
**What it does:**
1. Use causal DAG from step22 as structural model
2. Estimate causal effect of amyloid positivity on MMSE decline
3. Run refutation tests: placebo, data subset, random common cause
4. Report estimated effect sizes and p-values

---

## Phase 4: Documentation & Defense Prep

**Duration:** ~1 week

### Step 27: Final Statistics & Report

**File:** `steps/step27_final_stats.py`
**Output:** Node counts by label, relationship counts by type, OntologyConcept coverage, ICD-10 hierarchy depth, causal edge summary, graph density.

### Step 28: Thesis Figures

**File:** `steps/step28_thesis_figures.py`
**Output:** KG schema diagram (SVG), causal graph overlay, before/after LPG vs KG comparison, ATN cascade with causal annotations, ICD-10 hierarchy tree.

---

## Execution Order & Dependencies

```
Phase 1 (LPG→KG):
  step17_apply_constraints ──┐
                             ├── step18_add_ontology_properties ──┐
                             │                                     ├── step19_icd10_integration
                             │                                     ├── step20_ontology_layer
                             │                                     │
  step5b_jpeg2k_conversion   │   (can run in parallel)             │
  step7b_hash_detection ─────┘                                     │
                                                                   │
Phase 2 (Causal Discovery):                                        │
  step21_extract_causal_features ◄─────────────────────────────────┘
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

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| WHO ICD API downtime | Low | Medium | FBK ICD-10 OWL fallback + rdflib |
| Neo4j < 5.x (no composite constraints) | Medium | High | Check version first; use node key constraints as fallback |
| Causal-learn empty graph | Medium | Medium | Lower α to 0.1; use KCI for mixed data |
| AlzKB dump not downloadable | Medium | Low | Use published paper tables; create 50 key concepts manually |
| Incomplete baseline data | Low | Medium | ADNI has ~2,400 patients; 30% completeness → 700+ rows |
| BioPortal SPARQL down | **Confirmed** | High | **Already mitigated**: using WHO REST API + local rdflib |

---

## Success Criteria

By thesis defense, the KG must have:

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
