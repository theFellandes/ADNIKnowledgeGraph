# ADNI Knowledge Graph — Task List

> **Purpose:** Granular task breakdown for Claude Code execution. Each task is self-contained and resumable after token cooldown. Tasks are ordered by dependency. Check off as completed.

---

## How to Use This File

1. **Claude Code reads this file** at the start of each session
2. **Find the first unchecked task** → execute it
3. **Check it off** when done (change `[ ]` to `[x]`)
4. **If token limit approaches**, save progress and note where you stopped
5. **Next session:** Claude Code reads this file again, picks up from the first unchecked task

**Convention:** Each task has a unique ID (e.g., `T17.1`), estimated complexity, and verification command.

---

## PRE-FLIGHT CHECKS

- [ ] **T0.1** — Verify Neo4j version: `CALL dbms.components()` → Must be 5.x for composite constraints
- [ ] **T0.2** — Verify Neo4j connectivity: count nodes, labels, relationship types
- [ ] **T0.3** — Verify current graph state: `MATCH (n) RETURN labels(n)[0] as label, count(n) ORDER BY count(n) DESC`
- [ ] **T0.4** — Check existing constraints: `SHOW CONSTRAINTS`
- [ ] **T0.5** — Check existing indexes: `SHOW INDEXES`
- [ ] **T0.6** — Verify Python environment: `pip list | grep -E "neo4j|rdflib|causal-learn|dowhy"`
- [ ] **T0.7** — Install missing deps: `pip install rdflib SPARQLWrapper causal-learn dowhy glymur`
- [ ] **T0.8** — Verify headers.json accessible and has 108 tables
- [ ] **T0.9** — Verify config.yaml readable and has correct Neo4j credentials
- [ ] **T0.10** — Create output directories: `mkdir -p ontology causal thesis_output`

---

## PHASE 1: SCHEMA MIGRATION (Steps 17–20)

### Step 17: Apply Composite Unique Constraints

- [ ] **T17.1** — Read `step9_knowledge_graph_enhancer.py` to understand the connector pattern and function signature
- [ ] **T17.2** — Read `step1_database_setup.py` to understand how constraints are currently created
- [ ] **T17.3** — Create `steps/step17_apply_constraints.py` with:
  - All 6 core uniqueness constraints (patient_ptid, visit_id, mri_image_id, pet_image_id, brain_region, ontology_uri)
  - All 6 composite observation constraints (assess_unique, csf_unique, blood_unique, vol_unique, atn_unique, dx_unique)
  - All 15 performance indexes
  - IF NOT EXISTS clause on all statements
  - Graceful "already exists" error handling
  - Logging of created vs. skipped constraints
- [ ] **T17.4** — Register step17 in `pipeline.py` (add import + execution block)
- [ ] **T17.5** — Run step17 and verify: `SHOW CONSTRAINTS` should list all 12 constraints
- [ ] **T17.6** — Verify indexes: `SHOW INDEXES` should list all 15+ indexes
- [ ] **T17.7** — Test duplicate prevention: try inserting a duplicate CognitiveAssessment and confirm it's rejected

### Step 18: Add Ontology Properties (In-Place Upgrade)

- [ ] **T18.1** — Create mapping dictionaries for:
  - Diagnosis → SNOMED, ICD-10, MONDO codes
  - CognitiveAssessment → LOINC codes (MMSE, CDR, ADAS, MOCA, FAQ, GDS, NPI, NPIQ, ECOG, NEUROBAT, STAIAD)
  - CSFBiomarker → LOINC codes (Abeta42, Abeta40, tau, ptau)
  - BloodBiomarker → LOINC codes per analyte
  - BrainRegion → UBERON codes (hippocampus, entorhinal, etc.)
  - Medication → RxNorm codes (from BACKMEDS/RECCMEDS)
- [ ] **T18.2** — Create `steps/step18_add_ontology_properties.py` with:
  - Function to SET ontology properties on Diagnosis nodes
  - Function to SET loinc_code on CognitiveAssessment by test_name
  - Function to SET loinc_code on CSFBiomarker
  - Function to SET uberon_code on BrainRegion (if BrainRegion nodes exist; if not, create them)
  - Function to SET rdf_type on Patient nodes (ncit:C16960)
  - Function to SET rdf_type on Visit nodes (ncit:C159705)
  - Summary report of how many nodes enriched per label
- [ ] **T18.3** — Add URI properties to relationships:
  - `MATCH ()-[r:HAS_VISIT]->() SET r.uri = 'ro:RO_0000056'`
  - `MATCH ()-[r:FOLLOWED_BY]->() SET r.uri = 'time:intervalBefore'`
  - `MATCH ()-[r:HAS_DIAGNOSIS]->() SET r.uri = 'ro:RO_0000091'`
  - `MATCH ()-[r:YIELDED_ASSESSMENT]->() SET r.uri = 'ro:RO_0002234'`
  - All 20+ relationship types from Blueprint v2 Section 5
- [ ] **T18.4** — Register step18 in pipeline.py
- [ ] **T18.5** — Run step18 and verify:
  ```cypher
  MATCH (d:Diagnosis) WHERE d.snomed_code IS NOT NULL RETURN d.dx_label, d.snomed_code, d.icd10_code LIMIT 10
  MATCH (c:CognitiveAssessment) WHERE c.loinc_code IS NOT NULL RETURN c.test_name, c.loinc_code LIMIT 10
  MATCH (p:Patient) WHERE p.rdf_type IS NOT NULL RETURN count(p)
  ```
- [ ] **T18.6** — Generate coverage report: % of nodes per label that have ontology properties

### Step 19: ICD-10 Integration

- [ ] **T19.1** — Create `ontology/` directory and `ontology/icd10_mappings.json` with static mapping:
  ```json
  {"G30.9": {"label": "AD unspecified", "parent": "G30"},
   "G30": {"label": "Alzheimer disease", "parent": "G30-G32"},
   "G30.0": {"label": "AD early onset", "parent": "G30"},
   "G30.1": {"label": "AD late onset", "parent": "G30"},
   "G30-G32": {"label": "Other degenerative diseases of NS", "parent": "G20-G26"},
   "F06.7": {"label": "Mild cognitive disorder", "parent": "F06"},
   "F06": {"label": "Other mental disorders due to brain damage", "parent": "F00-F09"},
   "Z03.89": {"label": "No diagnosis", "parent": "Z03"},
   "F03.9": {"label": "Unspecified dementia", "parent": "F03"}}
  ```
- [ ] **T19.2** — Implement WHO ICD REST API client:
  - OAuth2 token acquisition (client_credentials flow)
  - GET /icd/release/10/{release}/codeSystems/ICD10CM/codes/{code}
  - Parse parent codes from response
  - Cache all responses to `ontology/icd10_cache.json`
- [ ] **T19.3** — Implement rdflib fallback:
  - Download FBK ICD-10 OWL from `https://github.com/nicola/icd10-ontology` (or ICDO)
  - Load with `rdflib.Graph().parse('icd10.owl')`
  - SPARQL query: `SELECT ?parent WHERE { <code> rdfs:subClassOf ?parent }`
- [ ] **T19.4** — Create `steps/step19_icd10_integration.py`:
  - Resolve all 6 diagnosis ICD-10 codes
  - Create OntologyConcept nodes for each ICD-10 code (MERGE on uri)
  - Create IS_A edges between ICD-10 concepts
  - Create CLASSIFIED_AS edges from Diagnosis to ICD-10 OntologyConcept
  - Properties: `{source: 'ICD-10', resolved_via: 'WHO_API' or 'rdflib_local'}`
- [ ] **T19.5** — Register in pipeline.py
- [ ] **T19.6** — Verify:
  ```cypher
  MATCH (o:OntologyConcept {source_ontology: 'ICD-10'}) RETURN o.code, o.label ORDER BY o.code
  MATCH (d:Diagnosis)-[:CLASSIFIED_AS]->(o) RETURN d.dx_label, o.code, o.label
  MATCH path = (:OntologyConcept {code: 'G30.9'})-[:IS_A*]->(p) RETURN [n in nodes(path) | n.code + ': ' + n.label]
  ```

### Step 20: OntologyConcept Layer + MAPS_TO

- [ ] **T20.1** — Create SNOMED-CT concept import (~50 concepts):
  - AD (26929004), MCI (386806002), Dementia (52448006), CN (17621005)
  - IS_A hierarchy: AD → Dementia → Neurodegenerative disorder
- [ ] **T20.2** — Create LOINC concept import (~30 concepts):
  - All assessment LOINC codes from T18.1
  - All biomarker LOINC codes
- [ ] **T20.3** — Create UBERON concept import (~20 concepts):
  - Hippocampus (0002421), Entorhinal cortex (0002728), Amygdala (0001876)
  - Frontal lobe, Temporal lobe, Parietal lobe, etc.
- [ ] **T20.4** — Create HPO concept import (~10 concepts):
  - Dementia (HP:0000726), Memory impairment (HP:0002354)
- [ ] **T20.5** — Build IS_A hierarchies within each ontology
- [ ] **T20.6** — Create MAPS_TO relationships:
  - For each Diagnosis node → find matching SNOMED OntologyConcept → MERGE MAPS_TO
  - For each CognitiveAssessment with loinc_code → MAPS_TO LOINC OntologyConcept
  - For each CSFBiomarker with loinc_code → MAPS_TO
  - For each BrainRegion with uberon_code → MAPS_TO
  - For each Medication with rxnorm_code → MAPS_TO
- [ ] **T20.7** — Create `steps/step20_ontology_layer.py` implementing all above
- [ ] **T20.8** — Register in pipeline.py
- [ ] **T20.9** — Verify coverage:
  ```cypher
  MATCH (n)-[:MAPS_TO]->(o:OntologyConcept)
  RETURN labels(n)[0] as nodeType, count(n) as mapped
  ORDER BY mapped DESC
  ```
- [ ] **T20.10** — Verify IS_A hierarchy:
  ```cypher
  MATCH path = (a:OntologyConcept)-[:IS_A*]->(b:OntologyConcept)
  WHERE a.code = '26929004'
  RETURN [n in nodes(path) | n.label]
  ```

---

## PHASE 1.5: IMAGE & INSERTION ENHANCEMENTS

### Step 5b: JPEG2000/HTJ2K Support

- [ ] **T5b.1** — Research available JPEG2000 libraries: `glymur`, `pillow` (with openjpeg), `imagecodecs`
- [ ] **T5b.2** — Add JPEG2000 conversion function to step5:
  - Input: numpy array (from DICOM/NIfTI)
  - Output: `.j2k` file with lossless compression
  - Preserve 16-bit depth where applicable
- [ ] **T5b.3** — Add HTJ2K option (if supported by chosen library)
- [ ] **T5b.4** — Update config.yaml `output_formats` section:
  ```yaml
  output_formats:
    jpeg2000: true        # Lossless archival
    htj2k: false          # Optional: faster decode
    tiff: true            # Existing
    png: true             # Existing
    thumbnail: true       # Existing
  ```
- [ ] **T5b.5** — Update Elasticsearch index mapping to include j2k format metadata
- [ ] **T5b.6** — Test with 10 sample DICOM files, verify lossless roundtrip

### Step 7b: Hash-Based Change Detection

- [ ] **T7b.1** — Add `compute_row_hash()` function to batch inserter:
  ```python
  def compute_row_hash(row: dict, key_columns: list) -> str:
      values = '|'.join(str(row.get(c, '')) for c in key_columns)
      return hashlib.sha256(values.encode()).hexdigest()
  ```
- [ ] **T7b.2** — Modify MERGE queries to use hash comparison:
  - ON CREATE SET `data_hash`, `created_at`, `batch_id`, `source_table`
  - ON MATCH: compare hash → skip if same, update if different
- [ ] **T7b.3** — Create BatchIngestion meta-node after each batch:
  ```cypher
  CREATE (b:BatchIngestion {batch_id: $id, source_table: $table, start_time: datetime(),
          rows_processed: $count, nodes_created: $created, nodes_updated: $updated, nodes_skipped: $skipped})
  ```
- [ ] **T7b.4** — Add `updated_at`, `data_hash`, `batch_id`, `source_table` properties to all observation node types
- [ ] **T7b.5** — Test idempotency: run same CSV twice, verify 0 creates on second run

---

## PHASE 2: CAUSAL DISCOVERY (Steps 21–23)

### Step 21: Extract Causal Feature Matrix

- [ ] **T21.1** — Write Cypher query to extract baseline features for all patients:
  - Demographics: age_at_baseline, sex, education_years, APOE_e4_count
  - Cognitive: MMSE, CDR_global, ADAS-Cog13, MoCA
  - CSF: Abeta42, tau, ptau, ratio_42_40
  - Volumetric: hippocampal_volume (if available)
  - PET: amyloid_centiloids (if available)
  - ATN: a_status, t_status, n_status
  - Diagnosis: dx_label (as target/outcome)
- [ ] **T21.2** — Create `steps/step21_extract_causal_features.py`:
  - Execute query, collect into pandas DataFrame
  - Report completeness per variable
  - Drop patients with >50% missing values
  - Impute remaining with median (continuous) or mode (categorical)
  - Encode categorical variables (sex, APOE, dx_label)
  - Save to `causal/causal_features.csv`
- [ ] **T21.3** — Generate correlation matrix heatmap → `causal/correlation_matrix.png`
- [ ] **T21.4** — Register in pipeline.py
- [ ] **T21.5** — Verify: load CSV, check shape, confirm no NaN in required columns

### Step 22: Run Causal Discovery Algorithms

- [ ] **T22.1** — Implement PC algorithm:
  ```python
  from causallearn.search.ConstraintBased.PC import pc
  cg = pc(data, alpha=0.05, indep_test='fisherz')
  ```
- [ ] **T22.2** — Implement FCI algorithm (PRIORITY — handles latent confounders):
  ```python
  from causallearn.search.ConstraintBased.FCI import fci
  G, edges = fci(data, independence_test_method='fisherz', alpha=0.05)
  ```
- [ ] **T22.3** — Implement GES algorithm:
  ```python
  from causallearn.search.ScoreBased.GES import ges
  Record = ges(data, score_func='local_score_BIC')
  ```
- [ ] **T22.4** — (Optional) Implement DAG-GNN if time permits
- [ ] **T22.5** — Generate consensus: edges found by ≥2 algorithms
- [ ] **T22.6** — Save results:
  - `causal/pc_graph.json` + `causal/pc_graph.png`
  - `causal/fci_graph.json` + `causal/fci_graph.png`
  - `causal/ges_graph.json` + `causal/ges_graph.png`
  - `causal/consensus_edges.json`
- [ ] **T22.7** — Create `steps/step22_causal_discovery.py` wrapping all above
- [ ] **T22.8** — Register in pipeline.py

### Step 23: Embed CAUSES Edges

- [ ] **T23.1** — Load consensus_edges.json
- [ ] **T23.2** — For each edge, create Cypher to add CAUSES relationship:
  ```cypher
  MATCH (a {variable_name: $source}), (b {variable_name: $target})
  MERGE (a)-[r:CAUSES]->(b)
  SET r.algorithm = $algorithms, r.p_value = $pval,
      r.effect_size = $effect, r.uri = 'ro:RO_0002411',
      r.discovered_at = datetime()
  ```
- [ ] **T23.3** — Handle variable-to-node mapping (e.g., "MMSE" → CognitiveAssessment {test_name: 'MMSE'})
- [ ] **T23.4** — Create `steps/step23_embed_causal_edges.py`
- [ ] **T23.5** — Register in pipeline.py
- [ ] **T23.6** — Verify:
  ```cypher
  MATCH ()-[r:CAUSES]->() RETURN count(r)
  MATCH (a)-[r:CAUSES]->(b) RETURN a.variable_name, r.algorithm, b.variable_name LIMIT 20
  ```

---

## PHASE 3: VALIDATION & INTEGRATION (Steps 24–26)

### Step 24: AlzKB Bridge

- [ ] **T24.1** — Check AlzKB availability: `https://github.com/EpistasisLab/AlzKB`
- [ ] **T24.2** — If downloadable: import subset of ~200 overlapping concepts
- [ ] **T24.3** — If not downloadable: create 50 key concepts manually from paper tables
- [ ] **T24.4** — Create AlzKB nodes with `alzkb:` prefix namespace
- [ ] **T24.5** — Create SAME_AS edges: OntologyConcept → AlzKB entity
- [ ] **T24.6** — Create `steps/step24_alzkb_bridge.py`
- [ ] **T24.7** — Register in pipeline.py
- [ ] **T24.8** — Verify cross-graph traversal:
  ```cypher
  MATCH (p:Patient)-[:HAS_VISIT]->()-[:HAS_CSF_BIOMARKER]->(csf)
        -[:MAPS_TO]->(o:OntologyConcept)-[:SAME_AS]->(alz)
  RETURN p.ptid, o.label, alz.label LIMIT 5
  ```

### Step 25: Validate Causal Edges

- [ ] **T25.1** — Define ground truth edges from literature:
  - amyloid → tau (A→T)
  - tau → neurodegeneration (T→N)
  - APOE_e4 → amyloid
  - age → all biomarkers
  - education → cognitive reserve
- [ ] **T25.2** — Cross-reference CAUSES edges with ground truth
- [ ] **T25.3** — Cross-reference with AlzKB relationships (if available)
- [ ] **T25.4** — Compute precision, recall, F1 vs. known AD biology
- [ ] **T25.5** — Mark validated edges: `SET r.validated_by_literature = true`
- [ ] **T25.6** — Create `steps/step25_validate_causal.py`
- [ ] **T25.7** — Generate `thesis_output/validation_report.md`
- [ ] **T25.8** — Register in pipeline.py

### Step 26: DoWhy Causal Inference

- [ ] **T26.1** — Build causal model from FCI DAG:
  ```python
  import dowhy
  model = dowhy.CausalModel(data=df, treatment='amyloid_positive',
                             outcome='mmse_score', graph=fci_dag_dot)
  ```
- [ ] **T26.2** — Identify estimand (backdoor criterion)
- [ ] **T26.3** — Estimate causal effect
- [ ] **T26.4** — Run refutation tests: placebo_treatment, data_subset, random_common_cause
- [ ] **T26.5** — Create `steps/step26_dowhy_inference.py`
- [ ] **T26.6** — Save results to `causal/dowhy_results.json`
- [ ] **T26.7** — Register in pipeline.py

---

## PHASE 4: DOCUMENTATION & DEFENSE PREP (Steps 27–28)

### Step 27: Final Statistics

- [ ] **T27.1** — Node counts by label
- [ ] **T27.2** — Relationship counts by type
- [ ] **T27.3** — OntologyConcept coverage: % of data nodes with MAPS_TO
- [ ] **T27.4** — ICD-10 hierarchy depth
- [ ] **T27.5** — Causal edge summary: count, algorithms, validation rate
- [ ] **T27.6** — Graph metrics: density, average degree, connected components
- [ ] **T27.7** — Create `steps/step27_final_stats.py`
- [ ] **T27.8** — Output: `thesis_output/final_stats.json` + `thesis_output/final_stats.md`
- [ ] **T27.9** — Register in pipeline.py

### Step 28: Thesis Figures

- [ ] **T28.1** — KG schema diagram using graphviz → SVG + PNG
- [ ] **T28.2** — Causal graph overlay on schema
- [ ] **T28.3** — Before/after: LPG query vs. KG semantic query
- [ ] **T28.4** — ATN biomarker cascade with causal annotations
- [ ] **T28.5** — ICD-10 hierarchy tree
- [ ] **T28.6** — Create `steps/step28_thesis_figures.py`
- [ ] **T28.7** — Output: all figures in `thesis_output/` as SVG and PNG
- [ ] **T28.8** — Register in pipeline.py

---

## PIPELINE INTEGRATION

- [ ] **T_PIPE.1** — Update pipeline.py imports for steps 17–28
- [ ] **T_PIPE.2** — Add step execution blocks with config flags:
  ```python
  run_apply_constraints: true        # Step 17
  run_ontology_properties: true      # Step 18
  run_icd10_integration: true        # Step 19
  run_ontology_layer: true           # Step 20
  run_causal_feature_extraction: true # Step 21
  run_causal_discovery: true         # Step 22
  run_embed_causal_edges: true       # Step 23
  run_alzkb_bridge: true             # Step 24
  run_validate_causal: true          # Step 25
  run_dowhy_inference: true          # Step 26
  run_final_stats: true              # Step 27
  run_thesis_figures: true           # Step 28
  ```
- [ ] **T_PIPE.3** — Update config.yaml with new sections:
  ```yaml
  who_icd:
    client_id: "YOUR_CLIENT_ID"
    client_secret: "YOUR_CLIENT_SECRET"
    release: "2019"
  bioportal:
    api_key: "YOUR_API_KEY"
  causal:
    alpha: 0.05
    algorithms: ["PC", "FCI", "GES"]
    consensus_threshold: 2
  ```
- [ ] **T_PIPE.4** — Full pipeline dry run: steps 17–28 end-to-end
- [ ] **T_PIPE.5** — Verify final graph state matches success criteria

---

## PROGRESS TRACKING

| Phase | Tasks Total | Tasks Done | Status |
|-------|-------------|------------|--------|
| Pre-flight | 10 | 0 | Not started |
| Phase 1: Schema Migration | 33 | 0 | Not started |
| Phase 1.5: Enhancements | 11 | 0 | Not started |
| Phase 2: Causal Discovery | 20 | 0 | Not started |
| Phase 3: Validation | 18 | 0 | Not started |
| Phase 4: Documentation | 17 | 0 | Not started |
| Pipeline Integration | 5 | 0 | Not started |
| **TOTAL** | **114** | **0** | **Not started** |

**Last updated:** 2026-02-23
**Last task completed:** None
**Next task to execute:** T0.1
