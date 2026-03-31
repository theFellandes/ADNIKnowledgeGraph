# Phase 1: Schema Migration — History

**Completed:** 2026-02-24  
**Pipeline:** `pipeline.py` (modular orchestrator, config.yaml-driven)

---

## What Was Done

### Step 17: Apply Composite Unique Constraints
- Created `steps/step17_apply_constraints.py` (373 lines)
- **12 uniqueness constraints** (5 core + 7 composite for observation nodes)
  - Core: Patient(ptid), Patient(rid), Visit(visit_id), Diagnosis(diagnosis_id), CognitiveAssessment(assessment_id)
  - Composite: Biomarker(patient_id, test_name, visit_code), VolumetricMeasure(patient_id, region, visit_code), etc.
- **15 performance indexes** for lookup patterns
- All use `IF NOT EXISTS` — fully idempotent
- Neo4j 5.x composite constraint support verified

### Step 18: Add Ontology Properties (In-Place Upgrade)
- Created `steps/step18_add_ontology_properties.py` (414 lines)
- Enriched existing nodes with ontology codes (no new nodes created):
  - **Diagnosis** (25,946 nodes): `snomed_code`, `icd10_code`, `mondo_code`, `rdf_type`
  - **CognitiveAssessment** (65,345 nodes): `loinc_code`, `rdf_type`
  - **Biomarker** (9,467 nodes): `loinc_code`, `rdf_type`
  - **BrainRegion** (12 nodes): `uberon_code`, `rdf_type`
  - **Patient** (2,638 nodes): `rdf_type` = ncit:Patient
  - **Visit** (30,267 nodes): `rdf_type` = ncit:Visit
- Added `uri` property to **30 relationship types** (1,235,651 relationships total)
- 100% coverage across all node types

### Step 19: ICD-10 Integration
- Created `steps/step19_icd10_integration.py` (323 lines)
- Created `ontology/icd10_mappings.json` (11 ICD-10 codes, static fallback)
- WHO ICD REST API client with OAuth2 (implemented, falls back to static when creds unavailable)
- **5 OntologyConcept nodes** for ICD-10 (G30.9, F06.7, Z03.89 + parent codes G30, F06)
- **2 IS_A edges** (G30.9→G30, F06.7→F06)
- **25,946 CLASSIFIED_AS edges** (Diagnosis → ICD-10 OntologyConcept)

### Step 20: Ontology Layer + MAPS_TO
- Created `steps/step20_ontology_layer.py` (380 lines)
- **47 OntologyConcept nodes** (total, across 4 ontologies):
  - 18 SNOMED-CT (disease hierarchy: Disease→Neurodegenerative→Dementia→AD, clinical findings, biomarkers, demographics)
  - 10 LOINC (6 cognitive assessments + 4 CSF biomarker codes)
  - 14 UBERON (brain regions: cortex, hippocampal, entorhinal, amygdala, ventricle, etc.)
  - 5 HPO (cognitive impairment, dementia, memory impairment, behavioral abnormality)
- **25 IS_A hierarchy edges** (9 SNOMED + 13 UBERON + 3 HPO)
- **100,770 MAPS_TO edges**:
  - 25,946 Diagnosis → SNOMED-CT
  - 65,345 CognitiveAssessment → LOINC
  - 9,467 Biomarker → LOINC
  - 12 BrainRegion → UBERON
- Fixed UBERON URI mismatch (BrainRegion.uberon_code stores `UBERON:` prefix, OntologyConcept uses `uberon:`)

---

## Pipeline Integration

- All 4 steps registered in `pipeline.py` with config toggles:
  - `run_apply_constraints`, `run_ontology_properties`, `run_icd10_integration`, `run_ontology_layer`
- Config defaults to `False` — set `true` in `config.yaml` to enable
- Each step runs standalone: `python -m steps.step{17,18,19,20}_...`

---

## Graph State After Phase 1

| Metric | Count |
|---|---|
| OntologyConcept nodes (ICD-10) | 5 |
| OntologyConcept nodes (SNOMED/LOINC/UBERON/HPO) | 47 |
| CLASSIFIED_AS edges | 25,946 |
| MAPS_TO edges | 100,770 |
| IS_A edges | 27 |
| Relationship types with URI property | 30 |
| Total relationships with URI | ~1.2M |

---

## Files Created

| File | Lines | Purpose |
|---|---|---|
| `steps/step17_apply_constraints.py` | 373 | Composite constraints + indexes |
| `steps/step18_add_ontology_properties.py` | 414 | In-place ontology code enrichment |
| `steps/step19_icd10_integration.py` | 323 | ICD-10 concepts + CLASSIFIED_AS |
| `steps/step20_ontology_layer.py` | 380 | SNOMED/LOINC/UBERON/HPO + MAPS_TO |
| `ontology/icd10_mappings.json` | 70 | Static ICD-10 mapping fallback |

## Files Modified

| File | Changes |
|---|---|
| `pipeline.py` | 4 imports + 4 run blocks + 4 wrapper methods |
| `config.yaml` | WHO ICD, BioPortal, causal config sections |

---

## What's Missing / Next Phases

### Phase 1.5: Image & Insertion Enhancements (Optional)
- [ ] JPEG2000/HTJ2K support (Step 5b)
- [ ] Hash-based change detection for incremental ingestion (Step 7b)

### Phase 2: Causal Discovery (Steps 21-23)
- [x] Extract causal feature matrix from graph (demographics, cognitive, CSF, volumetric, PET, ATN)
- [x] Run PC, FCI, GES algorithms (`causal-learn` installed)
- [x] Embed CAUSES edges back into the graph
- See [PHASE2_CAUSAL_DISCOVERY.md](PHASE2_CAUSAL_DISCOVERY.md) for details

### Phase 3: Validation & Integration (Steps 24-26)
- [x] AlzKB Bridge (external knowledge base alignment)
- [x] Validate causal edges against literature ground truth
- [x] DoWhy causal inference
- See [PHASE3_VALIDATION_INTEGRATION.md](PHASE3_VALIDATION_INTEGRATION.md) for details
- ⏳ Pending live Neo4j verification

### Phase 4: Documentation & Defense Prep (Steps 27-28)
- [x] Final statistics report (JSON + Markdown)
- [x] Thesis figures (schema diagram, causal graph, ICD-10 tree, before/after queries)
- See [PHASE4_DOCUMENTATION_DEFENSE.md](PHASE4_DOCUMENTATION_DEFENSE.md) for details
- ⏳ Pending live Neo4j verification

### Phase 5: Exploration & Analysis (Step 29)
- [x] KG EDA — 15 publication-quality figures
- [x] Cypher explorer — 50+ guided queries
- See [PHASE5_EXPLORATION_ANALYSIS.md](PHASE5_EXPLORATION_ANALYSIS.md) for details
