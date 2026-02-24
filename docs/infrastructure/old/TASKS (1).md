# ADNI Knowledge Graph — Task List v3

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

- [ ] **T0.1** — Verify Neo4j connectivity and version: `CALL dbms.components()` → Must be 5.x for composite constraints
- [ ] **T0.2** — Verify current graph state: `MATCH (n) RETURN labels(n)[0] as label, count(n) ORDER BY count(n) DESC`
- [ ] **T0.3** — Verify current relationships: `MATCH ()-[r]->() RETURN type(r), count(r) ORDER BY count(r) DESC`
- [ ] **T0.4** — Inspect actual property names on key node types:
  ```cypher
  MATCH (p:Patient) RETURN keys(p) LIMIT 3
  MATCH (v:Visit) RETURN keys(v) LIMIT 3
  MATCH (d:Diagnosis) RETURN keys(d) LIMIT 3
  MATCH (c:CognitiveAssessment) RETURN keys(c) LIMIT 3
  MATCH (b:Biomarker) RETURN keys(b) LIMIT 3
  MATCH (m:Medication) RETURN keys(m) LIMIT 3
  MATCH (f:FamilyMember) RETURN keys(f) LIMIT 3
  ```
  **WHY:** The Blueprint assumes property names that may differ from what step7 actually created. We must adapt all Cypher to actual property names.
- [ ] **T0.5** — Check existing constraints: `SHOW CONSTRAINTS`
- [ ] **T0.6** — Check existing indexes: `SHOW INDEXES`
- [ ] **T0.7** — Verify Python environment: `pip list | grep -E "neo4j|rdflib|causal-learn|dowhy|glymur"`
- [ ] **T0.8** — Install missing deps: `pip install rdflib SPARQLWrapper causal-learn dowhy glymur imagecodecs`
- [ ] **T0.9** — Verify headers.json accessible: `python -c "import json; d=json.load(open('headers.json')); print(f'{len(d)} tables, {sum(len(v) for v in d.values())} columns')"`  → Should show 108 tables, 5608 columns
- [ ] **T0.10** — Verify config.yaml readable and has correct Neo4j credentials
- [ ] **T0.11** — Create output directories: `mkdir -p ontology causal thesis_output`
- [ ] **T0.12** — Document actual node labels and property names in `PRE_FLIGHT_RESULTS.md` for reference in all subsequent steps

---

## INSERTION MECHANISM (insertion_main.py)

### Step INS: Create Standalone Insertion Entry Point

- [ ] **TINS.1** — Read `pipeline.py` to understand the ADNIPipeline class and execution pattern (lines 54–196)
- [ ] **TINS.2** — Read `config.yaml` to understand all configuration sections
- [ ] **TINS.3** — Create `insertion_main.py` with:
  - `STEP_REGISTRY` dict mapping step numbers to (name, module, function) tuples
  - `PHASE_MAP` dict mapping phase names to step number lists
  - `StepRunner` class that:
    - Accepts `--step N`, `--step N-M`, `--step N,M,O` for specific steps
    - Accepts `--from-step N` to run from step N to the end
    - Accepts `--phase NAME` to run all steps in a phase
    - Accepts `--list-steps` to show all available steps and their status
    - Uses lazy imports via `importlib.import_module` so missing step files don't crash
    - Loads config from `config.yaml` (same as pipeline.py)
    - Logs each step's result (success/failure/skip/duration) to `insertion_log.json`
    - Provides `--dry-run` flag to show what would run without executing
  - Main function with argparse
- [ ] **TINS.4** — Add skip logic:
  - If `--from-step 17`, skip steps 1-16 entirely
  - If Neo4j is empty and `--from-step > 2`, warn user that setup steps should run first
  - If step file doesn't exist yet, log as "NOT IMPLEMENTED" and skip gracefully
- [ ] **TINS.5** — Test with: `python insertion_main.py --list-steps`
- [ ] **TINS.6** — Test with: `python insertion_main.py --config config.yaml --step 17 --dry-run`
- [ ] **TINS.7** — Test with: `python insertion_main.py --config config.yaml --phase semantic --dry-run`
- [ ] **TINS.8** — Document usage in CLAUDE_CODE_GUIDE.md

---

## PHASE 1: SCHEMA MIGRATION (Steps 17–20)

### Step 17: Apply Composite Unique Constraints

- [ ] **T17.1** — Read `step1_database_setup.py` to understand how constraints are currently created (find existing constraint patterns)
- [ ] **T17.2** — Read `step9_knowledge_graph_enhancer.py` to understand the `Neo4jConnector` usage pattern
- [ ] **T17.3** — Read PRE_FLIGHT_RESULTS.md to know actual property names and node labels
- [ ] **T17.4** — Create `steps/step17_apply_constraints.py` with:
  - All 6 core uniqueness constraints (adapt property names from T0.4 results)
  - All 6 composite observation constraints (adapt to actual names)
  - All 15+ performance indexes
  - `IF NOT EXISTS` clause on all statements (Neo4j 5.x syntax)
  - Graceful "already exists" error handling (catch ClientError)
  - Logging of created vs. skipped constraints
  - `execute_apply_constraints(config)` function matching pipeline pattern
- [ ] **T17.5** — Register step17 in `insertion_main.py` STEP_REGISTRY
- [ ] **T17.6** — Run step17: `python insertion_main.py --config config.yaml --step 17`
- [ ] **T17.7** — Verify: `SHOW CONSTRAINTS` should list all 12 constraints
- [ ] **T17.8** — Verify: `SHOW INDEXES` should list all 15+ indexes
- [ ] **T17.9** — Test duplicate prevention: try inserting a duplicate and confirm constraint catches it

### Step 18: Add Ontology Properties (In-Place Upgrade)

- [ ] **T18.1** — Create mapping dictionaries in step file (hardcoded, verified against standards):
  - Diagnosis → SNOMED, ICD-10, MONDO codes
  - CognitiveAssessment → LOINC codes (all 14 assessment types)
  - CSFBiomarker → LOINC codes (Abeta42, Abeta40, tau, ptau)
  - BrainRegion → UBERON codes (12 brain regions)
  - Medication → RxNorm codes (if compound names available)
- [ ] **T18.2** — Create `steps/step18_add_ontology_properties.py` with:
  - Function to SET ontology properties on Diagnosis nodes (adapt to actual dx property names from T0.4)
  - Function to SET loinc_code on CognitiveAssessment by test_name
  - Function to SET loinc_code on CSFBiomarker/Biomarker nodes
  - Function to SET uberon_code on BrainRegion nodes (create if they don't exist)
  - Function to SET rdf_type on Patient (ncit:C16960) and Visit (ncit:C159705)
  - Summary report of how many nodes enriched per label
- [ ] **T18.3** — Add URI properties to all relationship types:
  - `MATCH ()-[r:HAS_VISIT]->() SET r.uri = 'ro:RO_0000056'`
  - `MATCH ()-[r:FOLLOWED_BY]->() SET r.uri = 'time:intervalBefore'`
  - All 20+ relationship types from Blueprint v2 Section 5
  - **NOTE:** Check actual relationship type names from T0.3 results first!
- [ ] **T18.4** — Register step18 in `insertion_main.py`
- [ ] **T18.5** — Run step18: `python insertion_main.py --config config.yaml --step 18`
- [ ] **T18.6** — Verify:
  ```cypher
  MATCH (d:Diagnosis) WHERE d.snomed_code IS NOT NULL RETURN d.dx_label, d.snomed_code, d.icd10_code LIMIT 10
  MATCH (c:CognitiveAssessment) WHERE c.loinc_code IS NOT NULL RETURN c.test_name, c.loinc_code LIMIT 10
  MATCH (p:Patient) WHERE p.rdf_type IS NOT NULL RETURN count(p)
  ```
- [ ] **T18.7** — Generate coverage report: % of nodes per label that have ontology properties

### Step 19: ICD-10 Integration

- [ ] **T19.1** — Create `ontology/icd10_mappings.json` with static ICD-10 hierarchy:
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
- [ ] **T19.2** — Create `steps/step19_icd10_integration.py`:
  - Load static mapping from JSON (primary — always works, no external dependency)
  - Resolve all 6 ADNI diagnosis ICD-10 codes
  - Create OntologyConcept nodes for each ICD-10 code (MERGE on uri)
  - Create IS_A edges between ICD-10 concepts
  - Create CLASSIFIED_AS edges from Diagnosis to ICD-10 OntologyConcept
  - Properties on edges: `{source: 'ICD-10', resolved_via: 'static_mapping'}`
- [ ] **T19.3** — (Optional) Implement WHO ICD REST API client for live hierarchy enrichment:
  - OAuth2 token acquisition (client_credentials flow)
  - `GET /icd/release/10/{release}/codeSystems/ICD10CM/codes/{code}`
  - Cache all responses to `ontology/icd10_api_cache.json`
  - Falls back to static mapping if API is down
- [ ] **T19.4** — (Optional) Implement rdflib fallback:
  - Download FBK ICD-10 OWL from `https://github.com/nicola/icd10-ontology`
  - Load with `rdflib.Graph().parse('icd10.owl')`
  - SPARQL query: `SELECT ?parent WHERE { <code> rdfs:subClassOf ?parent }`
- [ ] **T19.5** — Register in `insertion_main.py`
- [ ] **T19.6** — Run: `python insertion_main.py --config config.yaml --step 19`
- [ ] **T19.7** — Verify:
  ```cypher
  MATCH (o:OntologyConcept {source_ontology: 'ICD-10'}) RETURN o.code, o.label ORDER BY o.code
  MATCH (d:Diagnosis)-[:CLASSIFIED_AS]->(o) RETURN d.dx_label, o.code, o.label
  MATCH path = (:OntologyConcept {code: 'G30.9'})-[:IS_A*]->(p) RETURN [n in nodes(path) | n.code + ': ' + n.label]
  ```

### Step 20: OntologyConcept Layer + MAPS_TO

- [ ] **T20.1** — Create SNOMED-CT concept import (~50 concepts):
  - AD (26929004), MCI (386806002), Dementia (52448006), CN (17621005)
  - IS_A hierarchy: AD → Dementia → Neurodegenerative disorder → Disease
- [ ] **T20.2** — Create LOINC concept import (~30 concepts):
  - All assessment + biomarker LOINC codes from step18 mappings
- [ ] **T20.3** — Create UBERON concept import (~20 concepts):
  - 12 brain regions from step18 mappings
- [ ] **T20.4** — Create HPO concept import (~10 concepts):
  - Dementia (HP:0000726), Memory impairment (HP:0002354)
- [ ] **T20.5** — Build IS_A hierarchies within each ontology in Neo4j
- [ ] **T20.6** — Create MAPS_TO relationships:
  - Diagnosis nodes → matching SNOMED OntologyConcept
  - CognitiveAssessment with loinc_code → LOINC OntologyConcept
  - CSFBiomarker with loinc_code → LOINC OntologyConcept
  - BrainRegion with uberon_code → UBERON OntologyConcept
  - Medication with rxnorm_code → RxNorm OntologyConcept
- [ ] **T20.7** — Create `steps/step20_ontology_layer.py` implementing all above
- [ ] **T20.8** — Register in `insertion_main.py`
- [ ] **T20.9** — Run: `python insertion_main.py --config config.yaml --step 20`
- [ ] **T20.10** — Verify coverage:
  ```cypher
  MATCH (n)-[:MAPS_TO]->(o:OntologyConcept) RETURN labels(n)[0] as nodeType, count(n) as mapped ORDER BY mapped DESC
  MATCH path = (a:OntologyConcept)-[:IS_A*]->(b:OntologyConcept) WHERE a.code = '26929004' RETURN [n in nodes(path) | n.label]
  ```

---

## PHASE 1.5: IMAGE & INSERTION ENHANCEMENTS

### Step 5b: JPEG2000/HTJ2K Support

- [ ] **T5b.1** — Research available JPEG2000 libraries: test `glymur`, `imagecodecs`, `pillow` (with openjpeg plugin)
- [ ] **T5b.2** — Read `step5_improved_process_images.py` to understand the current image processing pipeline (classes, functions, output structure)
- [ ] **T5b.3** — Create `steps/step5b_jpeg2k_conversion.py` with:
  - JPEG2000 conversion function: numpy array → `.j2k` file (lossless)
  - Preserve 16-bit depth for medical images
  - Optional HTJ2K if OpenJPEG ≥ 2.5 available
  - Can process existing TIFF/PNG files → J2K (batch conversion mode)
  - Can hook into step5 pipeline for new images
- [ ] **T5b.4** — Update config.yaml `output_formats` section:
  ```yaml
  output_formats:
    jpeg2000: true
    htj2k: false
    tiff: true
    png: true
    thumbnail: true
  ```
- [ ] **T5b.5** — Update Elasticsearch index mapping to include j2k format metadata
- [ ] **T5b.6** — Register in `insertion_main.py`
- [ ] **T5b.7** — Test on 10 sample images, verify lossless round-trip

### Step 7b: Hash-Based Change Detection + Audit Trail

- [ ] **T7b.1** — Read `step7_batch_insert.py` to understand the BatchInserter class pattern
- [ ] **T7b.2** — Create `steps/step7b_hash_detection.py` (or modify step7) with:
  - `compute_row_hash(row, key_columns) -> str` using SHA-256
  - ON CREATE SET `data_hash`, `created_at`, `batch_id`, `source_table`
  - ON MATCH: compare hashes, skip if same, update if different
  - `BatchIngestion` meta-node creation per ingestion run
  - Stats: rows_processed, nodes_created, nodes_updated, nodes_skipped
- [ ] **T7b.3** — Register in `insertion_main.py`
- [ ] **T7b.4** — Test idempotency: run same data twice, verify 0 new nodes on second run

---

## PHASE 2: CAUSAL DISCOVERY (Steps 21–23)

### Step 21: Extract Causal Feature Matrix

- [ ] **T21.1** — Design Cypher query to extract baseline-visit features for all patients
- [ ] **T21.2** — Create `steps/step21_extract_causal_features.py`:
  - Connect to Neo4j, run feature extraction query
  - Features: MMSE, CDR, ADAS-Cog, Abeta42, tau, ptau, ratio_42_40, APOE genotype, ATN status, age, education, sex, hippocampal volume
  - Handle missing data: drop patients with >50% missing, impute remainder with median
  - Normalize continuous variables
  - Output: `causal/causal_features.csv`
  - Report: completeness per variable, sample size, correlation matrix
- [ ] **T21.3** — Register in `insertion_main.py`
- [ ] **T21.4** — Run and verify: check CSV has expected columns and ≥500 rows
- [ ] **T21.5** — Save data summary to `causal/feature_summary.json`

### Step 22: Causal Discovery Algorithms

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
- [ ] **T22.6** — Save results: `causal/pc_graph.json`, `causal/fci_graph.json`, `causal/ges_graph.json`, `causal/consensus_edges.json`, visualization PNGs
- [ ] **T22.7** — Create `steps/step22_causal_discovery.py` wrapping all above
- [ ] **T22.8** — Register in `insertion_main.py`

### Step 23: Embed CAUSES Edges

- [ ] **T23.1** — Load consensus_edges.json
- [ ] **T23.2** — Map variable names to node types (e.g., "MMSE" → CognitiveAssessment, "Abeta42" → CSFBiomarker)
- [ ] **T23.3** — Create CAUSES relationships with metadata:
  ```cypher
  MERGE (a)-[r:CAUSES]->(b)
  SET r.algorithm = $algorithms, r.p_value = $pval,
      r.effect_size = $effect, r.uri = 'ro:RO_0002411',
      r.discovered_at = datetime()
  ```
- [ ] **T23.4** — Create `steps/step23_embed_causal_edges.py`
- [ ] **T23.5** — Register in `insertion_main.py`
- [ ] **T23.6** — Verify:
  ```cypher
  MATCH ()-[r:CAUSES]->() RETURN count(r)
  MATCH (a)-[r:CAUSES]->(b) RETURN labels(a)[0], r.algorithm, labels(b)[0] LIMIT 20
  ```

---

## PHASE 3: VALIDATION & INTEGRATION (Steps 24–26)

### Step 24: AlzKB Bridge

- [ ] **T24.1** — Check AlzKB availability: `https://github.com/EpistasisLab/AlzKB`
- [ ] **T24.2** — If downloadable: import subset of ~200 overlapping concepts
- [ ] **T24.3** — If not downloadable: create 50 key concepts manually from published paper tables
- [ ] **T24.4** — Create AlzKB entity nodes with `alzkb:` prefix namespace
- [ ] **T24.5** — Create SAME_AS edges: OntologyConcept → AlzKB entity
- [ ] **T24.6** — Create `steps/step24_alzkb_bridge.py`
- [ ] **T24.7** — Register in `insertion_main.py`
- [ ] **T24.8** — Verify cross-graph traversal:
  ```cypher
  MATCH (p:Patient)-[:HAS_VISIT]->()-[:HAS_CSF_BIOMARKER|HAS_BIOMARKER]->(csf)
        -[:MAPS_TO]->(o:OntologyConcept)-[:SAME_AS]->(alz)
  RETURN p.ptid, o.label, alz.label LIMIT 5
  ```

### Step 25: Validate Causal Edges

- [ ] **T25.1** — Define ground truth edges from literature (Jack et al. 2013, Shen et al. 2020):
  - amyloid → tau (A→T), tau → neurodegeneration (T→N), APOE_e4 → amyloid, age → all, education → cognitive reserve
- [ ] **T25.2** — Cross-reference CAUSES edges with ground truth
- [ ] **T25.3** — Cross-reference with AlzKB relationships (if available)
- [ ] **T25.4** — Compute precision, recall, F1 vs. known AD biology
- [ ] **T25.5** — Mark validated edges: `SET r.validated_by_literature = true`
- [ ] **T25.6** — Create `steps/step25_validate_causal.py`
- [ ] **T25.7** — Generate `thesis_output/validation_report.md`
- [ ] **T25.8** — Register in `insertion_main.py`

### Step 26: DoWhy Causal Inference

- [ ] **T26.1** — Build causal model from FCI DAG
- [ ] **T26.2** — Identify estimand (backdoor criterion)
- [ ] **T26.3** — Estimate causal effect of amyloid positivity on MMSE decline
- [ ] **T26.4** — Run refutation tests: placebo_treatment, data_subset, random_common_cause
- [ ] **T26.5** — Create `steps/step26_dowhy_inference.py`
- [ ] **T26.6** — Save results to `causal/dowhy_results.json`
- [ ] **T26.7** — Register in `insertion_main.py`

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
- [ ] **T27.9** — Register in `insertion_main.py`

### Step 28: Thesis Figures

- [ ] **T28.1** — KG schema diagram using graphviz or matplotlib → SVG + PNG
- [ ] **T28.2** — Causal graph overlay on schema
- [ ] **T28.3** — Before/after: LPG query vs. KG semantic query comparison
- [ ] **T28.4** — ATN biomarker cascade with causal annotations
- [ ] **T28.5** — ICD-10 hierarchy tree visualization
- [ ] **T28.6** — Create `steps/step28_thesis_figures.py`
- [ ] **T28.7** — Output: all figures in `thesis_output/` as SVG and PNG
- [ ] **T28.8** — Register in `insertion_main.py`

---

## PIPELINE INTEGRATION

- [ ] **T_PIPE.1** — Update `pipeline.py` imports for steps 17–28 (with try/except for missing steps)
- [ ] **T_PIPE.2** — Add step execution blocks for steps 17–28 with config flags
- [ ] **T_PIPE.3** — Update config.yaml with new sections (who_icd, bioportal, causal, new run flags)
- [ ] **T_PIPE.4** — Full pipeline dry run: `python insertion_main.py --config config.yaml --phase semantic --dry-run`
- [ ] **T_PIPE.5** — Full pipeline execution: `python insertion_main.py --config config.yaml --from-step 17`
- [ ] **T_PIPE.6** — Verify final graph state matches success criteria

---

## PROGRESS TRACKING

| Phase | Tasks Total | Tasks Done | Status |
|-------|-------------|------------|--------|
| Pre-flight | 12 | 0 | Not started |
| Insertion Mechanism | 8 | 0 | Not started |
| Phase 1: Schema Migration | 34 | 0 | Not started |
| Phase 1.5: Enhancements | 11 | 0 | Not started |
| Phase 2: Causal Discovery | 19 | 0 | Not started |
| Phase 3: Validation | 18 | 0 | Not started |
| Phase 4: Documentation | 17 | 0 | Not started |
| Pipeline Integration | 6 | 0 | Not started |
| **TOTAL** | **125** | **0** | **Not started** |

**Last updated:** 2026-02-23
**Last task completed:** None
**Next task to execute:** T0.1

---

## SESSION NOTES

> Claude Code: Write notes here about progress, issues, or decisions made during each session.

### Session 1 (Date: ______)
- Started: Task ___
- Completed: Tasks ___
- Issues: ___
- Next: Task ___
