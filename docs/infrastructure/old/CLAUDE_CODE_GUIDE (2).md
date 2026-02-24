# ADNI Knowledge Graph — Claude Code Execution Guide (Extended v3)

## Overview

This guide is your step-by-step playbook for transforming the existing ADNI Labeled Property Graph into a true Knowledge Graph with causal discovery capabilities. It is designed for **Claude Code** (Anthropic's CLI agent) so you can execute each step directly from your terminal — and **resume after token cooldowns**.

**Timeline:** February 24 – May 2026 (thesis defense)  
**Current State:** Neo4j LPG with ~407K nodes, ~1.16M relationships, 16 pipeline steps  
**Target State:** Semantic KG with ICD-10, composite constraints, causal discovery edges, standalone insertion mechanism

---

## Quick Start for New Claude Code Sessions

```
1. Read this file: CLAUDE_CODE_GUIDE.md
2. Read TASKS.md → find the FIRST unchecked task (look for "- [ ]")
3. Execute that task
4. Check it off in TASKS.md (change "[ ]" to "[x]")
5. Continue until token limit approaches
6. Save progress notes in the SESSION NOTES section of TASKS.md
7. Next session: repeat from step 1
```

### CRITICAL FIRST-SESSION RULE

**Before writing ANY code, run pre-flight checks (T0.1–T0.12).** The actual property names and node labels in the Neo4j database may differ from what the Blueprint documents assume. All subsequent Cypher queries must use the ACTUAL names, not the Blueprint names.

---

## Project Structure

```
ADNIKnowledgeGraph/
├── steps/                                # Pipeline steps (executable)
│   ├── step1_database_setup.py           # ✅ Neo4j + ES setup
│   ├── step2_load_tables.py              # ✅ Load 108 CSV tables
│   ├── step3_create_patients.py          # ✅ Patient node creation
│   ├── step4_extract_family.py           # ✅ Family history
│   ├── step5_improved_process_images.py  # ✅ DICOM→TIFF/PNG/thumbnails (NO JPEG2K)
│   ├── step5_improved_process_images_with_tiff.py # ✅ Alt with TIFF
│   ├── step6_extract_findings_robust.py  # ✅ Clinical findings
│   ├── step7_batch_insert.py             # ✅ Batch insert (NO hash detection)
│   ├── step8_create_relationships.py     # ✅ Relationship creation
│   ├── step9_knowledge_graph_enhancer.py # ✅ Semantic enrichment (ATN, risk factors)
│   ├── step10_execute_queries.py         # ✅ Query execution
│   ├── step11_biomarker_analysis.py      # ✅ Biomarker analysis
│   ├── step12_complete_graph_enhancement.py # ✅ Enhancement
│   ├── step13_graph_eda.py               # ✅ EDA
│   ├── step14_test_queries.py            # ✅ Research queries
│   ├── step15_event_based_model.py       # ✅ Event-based model
│   ├── step16_create_metrics.py          # ✅ Performance metrics
│   ├── step17_apply_constraints.py       # ❌ TO BUILD
│   ├── step18_add_ontology_properties.py # ❌ TO BUILD
│   ├── step19_icd10_integration.py       # ❌ TO BUILD
│   ├── step20_ontology_layer.py          # ❌ TO BUILD
│   ├── step21_extract_causal_features.py # ❌ TO BUILD
│   ├── step22_causal_discovery.py        # ❌ TO BUILD
│   ├── step23_embed_causal_edges.py      # ❌ TO BUILD
│   ├── step24_alzkb_bridge.py            # ❌ TO BUILD
│   ├── step25_validate_causal.py         # ❌ TO BUILD
│   ├── step26_dowhy_inference.py         # ❌ TO BUILD
│   ├── step27_final_stats.py             # ❌ TO BUILD
│   ├── step28_thesis_figures.py          # ❌ TO BUILD
│   ├── step5b_jpeg2k_conversion.py       # ❌ TO BUILD
│   └── step7b_hash_detection.py          # ❌ TO BUILD
├── models/
│   └── entities.py                       # Data models (Patient, Visit, etc.)
├── utils/
│   ├── neo4j_connector.py                # Neo4j connection wrapper
│   ├── batch_processor.py                # Batch processing utilities
│   └── quality_aware_logger.py           # Logging
├── misc/                                 # Miscellaneous utilities
├── ontology/                             # ❌ TO CREATE
│   ├── icd10_mappings.json               # Static ICD-10 hierarchy
│   ├── icd10_api_cache.json              # Cached WHO ICD API responses
│   └── concept_mappings.json             # SNOMED/LOINC/UBERON tables
├── causal/                               # ❌ TO CREATE
│   ├── causal_features.csv               # Extracted baseline features
│   ├── consensus_edges.json              # Edges found by ≥2 algorithms
│   └── *.png                             # Algorithm output visualizations
├── thesis_output/                        # ❌ TO CREATE
│   ├── *.svg                             # Publication figures
│   ├── validation_report.md              # Validation results
│   └── final_stats.json                  # Graph statistics
├── config.yaml                           # Pipeline configuration
├── pipeline.py                           # Main orchestrator (steps 1-15)
├── insertion_main.py                     # ❌ TO BUILD: Standalone insertion entry point
├── headers.json                          # 108 ADNI tables (5,608 columns)
├── requirements.txt                      # Python dependencies
├── docker-compose.yml                    # Neo4j + ES containers
├── kg_streamlit_ui.py                    # Streamlit UI (existing)
├── new_pipeline4_6.py                    # Alt pipeline (existing)
├── IMPLEMENTATION_PLAN.md                # Detailed plan
├── TASKS.md                              # Granular task checklist (STATE TRACKER)
├── CLAUDE_CODE_GUIDE.md                  # THIS FILE
└── PRE_FLIGHT_RESULTS.md                 # ❌ TO CREATE: Actual graph state documentation
```

---

## Prerequisites

### 1. Environment Setup

```bash
# Clone repo (if not already)
git clone https://github.com/theFellandes/ADNIKnowledgeGraph.git
cd ADNIKnowledgeGraph

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install existing dependencies
pip install -r requirements.txt

# Install NEW dependencies for KG enhancement
pip install rdflib SPARQLWrapper requests-oauthlib
pip install causal-learn dowhy
pip install pandas numpy scipy networkx matplotlib graphviz
pip install glymur imagecodecs  # JPEG2000 support
```

### 2. Required Accounts (Free)

| Service | URL | What You Need | Required? |
|---------|-----|---------------|-----------|
| WHO ICD API | https://icd.who.int/icdapi | Client ID + Secret (OAuth2) | Optional (static mapping works) |
| BioPortal REST | https://bioportal.bioontology.org/account | API Key | Optional |
| ADNI Data | https://ida.loni.usc.edu | Already have access | Already done |

### 3. Neo4j Instance

Your existing Neo4j instance must be running. Verify:
```bash
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'YOUR_PASSWORD'))
with driver.session() as s:
    result = s.run('MATCH (n) RETURN count(n) as cnt')
    print(f'Nodes: {result.single()[\"cnt\"]}')
driver.close()
"
```

---

## Standalone Insertion Mechanism (insertion_main.py)

### Why This Exists

`pipeline.py` runs all 16 steps sequentially. For thesis work, you often need to:
- Run only the semantic enhancement steps (17-20) without reprocessing images
- Run only causal discovery (21-23) after the KG is built
- Re-run a single step after fixing a bug
- Resume from a specific step after a crash

`insertion_main.py` is the solution. It provides step-level granularity with the same config.

### Usage

```bash
# List all available steps and their implementation status
python insertion_main.py --list-steps

# Run a single step
python insertion_main.py --config config.yaml --step 17

# Run a range of steps
python insertion_main.py --config config.yaml --step 17-20

# Run specific steps (comma-separated)
python insertion_main.py --config config.yaml --step 17,18,19

# Run from a step to the end
python insertion_main.py --config config.yaml --from-step 17

# Run all steps in a phase
python insertion_main.py --config config.yaml --phase semantic

# Dry run (show what would execute without running)
python insertion_main.py --config config.yaml --phase causal --dry-run
```

### Phases

| Phase | Steps | Description |
|-------|-------|-------------|
| `setup` | 1–2 | Database + table loading |
| `ingest` | 3–8 | Patient creation → relationships |
| `enhance` | 9–16 | Knowledge graph enhancement + analysis |
| `semantic` | 17–20 | Ontology properties, ICD-10, MAPS_TO |
| `causal` | 21–23 | Feature extraction → discovery → embedding |
| `validate` | 24–26 | AlzKB bridge → validation → DoWhy |
| `report` | 27–28 | Statistics + figures |

### Implementation Pattern

Every new step file MUST follow this pattern:

```python
"""
Step N: [Step Name]
[Description]
"""

import logging
from typing import Dict, Any
from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


class StepNExecutor:
    """Main executor class for Step N"""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector

    def execute(self) -> Dict[str, Any]:
        """Execute the step, return results dict"""
        results = {'created': 0, 'updated': 0, 'errors': []}
        try:
            # ... step logic ...
            pass
        except Exception as e:
            logger.error(f"Step N failed: {e}")
            results['errors'].append(str(e))
        return results


def execute_step_n(config: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point called by insertion_main.py and pipeline.py"""
    connector = Neo4jConnector(
        uri=config['neo4j_uri'],
        user=config['neo4j_user'],
        password=config['neo4j_password']
    )
    try:
        executor = StepNExecutor(connector)
        return executor.execute()
    finally:
        connector.close()
```

---

## Data Sources — Verified as of February 2026

### ✅ CONFIRMED AVAILABLE

| Source | Status | Access Method | Notes |
|--------|--------|---------------|-------|
| **WHO ICD API** (ICD-10) | ✅ Active | REST API (OAuth2) | Free. Supports ICD-10 2008/2010/2016 releases |
| **FBK ICD-10 OWL** | ✅ Available | Download OWL file | CC BY-NC-SA. Local rdflib queries |
| **BioPortal REST API** | ✅ Active | REST API (API Key) | SPARQL is DEAD, but REST works |
| **causal-learn** | ✅ v0.1.4.3 on PyPI | `pip install causal-learn` | PC, FCI, GES, LiNGAM, DAG-GNN |
| **DoWhy** | ✅ Active | `pip install dowhy` | Causal inference + refutation |
| **rdflib** | ✅ Active | `pip install rdflib` | Local SPARQL on downloaded OWL files |
| **glymur** | ✅ Active | `pip install glymur` | JPEG2000 via OpenJPEG binding |

### ⚠️ CRITICAL: BioPortal SPARQL is DEAD

**BioPortal's SPARQL endpoint (sparql.bioontology.org) is DEPRECATED and SHUT DOWN.**
Use static JSON mappings (primary) + WHO REST API (secondary) + local rdflib (tertiary).

---

## ADNI Dataset Reference

108 tables with 5,608 columns total in `headers.json`. Key tables by domain:

### Patient Demographics
- `PTDEMOG` (84 cols): gender, DOB, education, ethnicity, race
- `APOERES` (16 cols): APOE genotype (APGEN1, APGEN2)

### Diagnosis
- `DXSUM` (41 cols): DXCURREN, DXCHANGE, DXCONV, DIAGNOSIS

### Cognitive Assessments (14 tables)
- `MMSE` (58 cols) → MMSCORE
- `CDR` (25 cols) → CDGLOBAL
- `ADAS` (16 cols) → TOTSCORE, TOTAL13
- `MOCA` (58 cols), `FAQ` (27 cols), `GDSCALE` (32 cols)
- `NPI` (168 cols), `NPIQ` (41 cols), `NEUROBAT` (83 cols)
- `ECOGPT` (62 cols), `ECOGSP` (59 cols), `STAIAD` (21 cols)

### CSF Biomarkers
- `UPENNBIOMK_ROCHE_ELECSYS` (13 cols): Abeta42, Abeta40, tau, ptau → PRIMARY

### Neuroimaging
- MRI: `Key_MRI`, `Structural_MRI_Images`, `MRI3META`, `MRIMETA` (7 tables)
- PET: `Key_PET`, `PET_Images`, `AV45META`, `TAUMETA` (8 tables)
- Volumetrics: `UCSFFSX7`, `UCBERKELEY_*`, `UCD_WMH`, `DTIROI_*` (7 tables)

### Genetics, Medications, Adverse Events, Family History, Neuropathology
- See `headers.json` for full column lists per table

---

## Ontology Mapping Tables

### Diagnosis → SNOMED-CT / ICD-10 / MONDO

```python
DIAGNOSIS_ONTOLOGY = {
    "AD":   {"snomed_code": "26929004",  "icd10_code": "G30.9", "mondo_code": "MONDO:0004975"},
    "MCI":  {"snomed_code": "386806002", "icd10_code": "F06.7", "mondo_code": "MONDO:0024647"},
    "CN":   {"snomed_code": "17621005",  "icd10_code": "Z03.89"},
    "Dementia": {"snomed_code": "52448006", "icd10_code": "F03.9", "mondo_code": "MONDO:0001627"},
}
```

### CognitiveAssessment → LOINC

```python
ASSESSMENT_LOINC = {
    "MMSE": "72106-8",   "CDR": "72172-0",   "ADAS": "72194-4",
    "MOCA": "72133-2",   "FAQ": "72107-6",   "GDS": "72166-2",
    "NPI": "72169-6",    "NPIQ": "72169-6",  "NEUROBAT": "72196-9",
    "ECOGPT": "72175-3", "ECOGSP": "72175-3", "STAIAD": "72198-5",
}
```

### CSFBiomarker → LOINC

```python
CSF_LOINC = {
    "Abeta42": "72333-6", "Abeta40": "72332-8",
    "tau": "72335-1",     "ptau": "72334-4",
    "ratio_42_40": "72336-9",
}
```

### BrainRegion → UBERON

```python
BRAIN_UBERON = {
    "Hippocampus": "0002421", "Entorhinal": "0002728", "Amygdala": "0001876",
    "Frontal": "0001870",     "Temporal": "0001871",   "Parietal": "0001872",
    "Occipital": "0002021",   "Cingulate": "0003027",  "Insula": "0002022",
    "Caudate": "0001873",     "Putamen": "0001874",    "Thalamus": "0001897",
}
```

### Relationship → Relation Ontology URIs

```python
RELATIONSHIP_URIS = {
    "HAS_VISIT": "ro:RO_0000056",          # participates_in
    "FOLLOWED_BY": "time:intervalBefore",
    "HAS_DIAGNOSIS": "ro:RO_0000091",      # has_disposition
    "PROGRESSED_TO": "ro:RO_0002263",
    "YIELDED_ASSESSMENT": "ro:RO_0002234", # has_output
    "HAS_CSF_BIOMARKER": "ro:RO_0002234",
    "HAS_BLOOD_BIOMARKER": "ro:RO_0002234",
    "HAS_ATN_PROFILE": "adni:derived_from",
    "HAS_MRI_SCAN": "ro:RO_0002234",
    "HAS_PET_SCAN": "ro:RO_0002234",
    "HAS_VOLUMETRIC": "ro:RO_0002234",
    "MEASURES_REGION": "bfo:BFO_0000066",
    "HAS_GENETIC_PROFILE": "ro:RO_0000053",
    "TAKES_MEDICATION": "ro:RO_0000056",
    "MAPS_TO": "skos:exactMatch",
    "IS_A": "rdfs:subClassOf",
    "CLASSIFIED_AS": "skos:exactMatch",
    "CAUSES": "ro:RO_0002411",             # causally_upstream_of
}
```

---

## Common Claude Code Prompts

### For exploring the current graph (ALWAYS DO FIRST)

```
Connect to my Neo4j at bolt://localhost:7687 (user: neo4j, password from
config.yaml). Run these queries and save results to PRE_FLIGHT_RESULTS.md:
1. CALL dbms.components() — what Neo4j version?
2. CALL db.labels() — what node types exist?
3. CALL db.relationshipTypes() — what edge types exist?
4. MATCH (n) RETURN labels(n)[0] as label, count(n) ORDER BY count(n) DESC
5. MATCH ()-[r]->() RETURN type(r), count(r) ORDER BY count(r) DESC
6. For each node type: MATCH (n:TYPE) RETURN keys(n) LIMIT 3
```

### For executing a specific step

```
Read TASKS.md. Find the first unchecked task. Read the relevant existing
step files for patterns (especially step9_knowledge_graph_enhancer.py for
the Neo4jConnector usage). Execute the task. Check it off. Verify results.
```

### For building insertion_main.py

```
Read CLAUDE_CODE_GUIDE.md section "Standalone Insertion Mechanism". Read
pipeline.py to understand the existing orchestration pattern. Create
insertion_main.py following the STEP_REGISTRY pattern. Test with --list-steps.
```

### For building a semantic step (17-20)

```
Read PRE_FLIGHT_RESULTS.md to know actual property names. Read the ontology
mapping tables in CLAUDE_CODE_GUIDE.md. Create the step file following the
pattern shown. Use actual property names from the graph, not Blueprint names.
Register in insertion_main.py. Run and verify with Cypher queries.
```

### For debugging constraint issues

```
My step17 is failing. Check what properties actually exist on the target nodes:
  MATCH (c:CognitiveAssessment) RETURN keys(c) LIMIT 5
Then adapt the constraint to use the actual property names.
```

### For resuming after cooldown

```
Read TASKS.md. Find the first unchecked task. Read the SESSION NOTES at the
bottom for context from the previous session. Continue from where we left off.
```

---

## Config Additions Needed (for config.yaml)

```yaml
# ============================================================================
# ONTOLOGY & SEMANTIC ENRICHMENT (NEW)
# ============================================================================

# WHO ICD API credentials (optional — static mapping works without this)
who_icd:
  client_id: "YOUR_CLIENT_ID"
  client_secret: "YOUR_CLIENT_SECRET"
  token_url: "https://icdaccessmanagement.who.int/connect/token"
  api_url: "https://id.who.int/icd"
  release: "2019"

# BioPortal REST API (optional)
bioportal:
  api_key: "YOUR_API_KEY"
  base_url: "https://data.bioontology.org"

# ============================================================================
# CAUSAL DISCOVERY SETTINGS (NEW)
# ============================================================================

causal:
  alpha: 0.05
  algorithms: ["PC", "FCI", "GES"]
  consensus_threshold: 2          # Edges must be found by N algorithms
  independence_test: "fisherz"
  max_missing_pct: 0.5            # Drop patients with >50% missing

# ============================================================================
# IMAGE FORMAT SETTINGS (NEW)
# ============================================================================

output_formats:
  jpeg2000: true        # Lossless archival via glymur
  htj2k: false          # Optional: faster decode (needs OpenJPEG ≥2.5)
  tiff: true            # Existing
  png: true             # Existing
  thumbnail: true       # Existing JPEG 256x256

# ============================================================================
# NEW PIPELINE STEP FLAGS
# ============================================================================

run_apply_constraints: true         # Step 17
run_ontology_properties: true       # Step 18
run_icd10_integration: true         # Step 19
run_ontology_layer: true            # Step 20
run_causal_feature_extraction: true # Step 21
run_causal_discovery: true          # Step 22
run_embed_causal_edges: true        # Step 23
run_alzkb_bridge: true              # Step 24
run_validate_causal: true           # Step 25
run_dowhy_inference: true           # Step 26
run_final_stats: true               # Step 27
run_thesis_figures: true            # Step 28
run_jpeg2k_conversion: true         # Step 5b
run_hash_detection: true            # Step 7b
```

---

## ICD-10 Static Mapping (for ontology/icd10_mappings.json)

```json
{
  "G30.9": {"label": "Alzheimer disease, unspecified", "parent": "G30"},
  "G30": {"label": "Alzheimer disease", "parent": "G30-G32"},
  "G30.0": {"label": "Alzheimer disease with early onset", "parent": "G30"},
  "G30.1": {"label": "Alzheimer disease with late onset", "parent": "G30"},
  "G30-G32": {"label": "Other degenerative diseases of the nervous system", "parent": "G20-G26"},
  "G20-G26": {"label": "Extrapyramidal and movement disorders", "parent": "G00-G99"},
  "G00-G99": {"label": "Diseases of the nervous system", "parent": null},
  "F06.7": {"label": "Mild cognitive disorder", "parent": "F06"},
  "F06": {"label": "Other mental disorders due to known physiological condition", "parent": "F01-F09"},
  "F01-F09": {"label": "Mental disorders due to known physiological conditions", "parent": "F01-F99"},
  "F03.9": {"label": "Unspecified dementia, unspecified severity", "parent": "F03"},
  "F03": {"label": "Unspecified dementia", "parent": "F01-F09"},
  "Z03.89": {"label": "Encounter for observation for other suspected diseases", "parent": "Z03"},
  "Z03": {"label": "Encounter for medical observation for suspected diseases", "parent": "Z00-Z13"}
}
```

---

## Risk Mitigation

| Risk | Probability | Mitigation |
|------|-------------|------------|
| WHO ICD API down | Low | Static JSON mapping as primary (always works) |
| Neo4j < 5.x | Medium | Check version first. Fallback: node key constraints |
| **Actual property names differ from Blueprint** | **High** | Run T0.4 FIRST, adapt ALL Cypher |
| Causal-learn produces empty graph | Medium | Lower alpha to 0.1, try KCI |
| AlzKB dump not downloadable | Medium | Use paper tables, create 50 concepts manually |
| BioPortal SPARQL down | **Confirmed** | WHO REST + local rdflib |

---

## Thesis Narrative: Construct → Discover → Represent

1. **Construct:** Build a semantic KG from ADNI data (108 tables → 17 node types, 20+ relationship types, ontology grounding)
2. **Discover:** Apply causal discovery algorithms (PC, FCI, GES) to extract causal relationships
3. **Represent:** Embed discovered causal edges back into the KG as native CAUSES relationships, validated against AlzKB and known AD biology

**What's original:** No existing work combines (1) a full-scale ADNI data graph (108 tables, 407K nodes) with (2) semantic ontology grounding AND (3) causal discovery integration where discovered causal edges become native KG relationships.

---

## References

- **Blueprint v1:** `ADNI_KG_Design_Blueprint.pdf`
- **Blueprint v2:** `ADNI_KG_Blueprint_v2.pdf` (incorporates Prof. Turhan's feedback)
- **IEEE Paper:** `IEEE_Big_Data_2025_Oguzhan.pdf`
- **Thesis Draft:** `OğuzhanGüngör_Tez_1.pdf`
- **ADNI Report:** `adni_kg_report.pdf` (current graph state documentation)
- **AlzKB:** Romano et al. 2024, 118,902 entities, 1,309,527 relationships
- **Shen et al. 2020:** FCI on ADNI biomarkers, 71% precision
- **Dobreva et al. 2025:** AD-KG 2.0 framework, validates Construct→Discover→Represent
- **ADNI Data:** https://adni.loni.usc.edu/data-samples/adni-data/
- **ADNI Docs:** https://adni.loni.usc.edu/help-faqs/adni-documentation/

---

## Token Cooldown Recovery Protocol

When Claude Code hits the token limit mid-task:

1. **STOP** current execution gracefully
2. **SAVE** any partially written files
3. **NOTE** in TASKS.md SESSION NOTES section:
   - Which task was in progress
   - What was completed within that task
   - What remains for that task
   - Any variables or state needed to resume
4. **COMMIT** changes to git if possible: `git add -A && git commit -m "WIP: Task TXXX partial"`

When resuming:
1. Read TASKS.md → check SESSION NOTES for context
2. Find the first unchecked task
3. If a task was partially done, read the notes and continue from where it stopped
4. Do NOT restart completed sub-tasks

---

## Success Criteria (Thesis Defense Checklist)

- [ ] ~407K+ data nodes + ~200 OntologyConcept nodes + ICD-10 hierarchy
- [ ] Composite unique constraints on ALL observation nodes
- [ ] MAPS_TO edges: ≥80% of data nodes with ontology codes linked
- [ ] CLASSIFIED_AS edges: All Diagnosis nodes → ICD-10
- [ ] IS_A hierarchy: ICD-10 + SNOMED-CT concepts
- [ ] Causal discovery from ≥3 algorithms (PC, FCI, GES)
- [ ] CAUSES edges with metadata (algorithm, p_value, confidence)
- [ ] AlzKB bridge with SAME_AS edges for overlapping concepts
- [ ] Validation report: precision/recall vs. known AD biology
- [ ] Publication-quality SVG figures for thesis
- [ ] Hash-based change detection + BatchIngestion audit trail
- [ ] JPEG2000 lossless tier in image pipeline
- [ ] Standalone `insertion_main.py` with step-level control
- [ ] All steps registered in `insertion_main.py` STEP_REGISTRY

---

*Last updated: 2026-02-23*
*Next action: Open TASKS.md → Execute T0.1*
