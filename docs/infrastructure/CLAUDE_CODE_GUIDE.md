# ADNI Knowledge Graph — Claude Code Execution Guide (Extended)

## Overview

This guide is your step-by-step playbook for transforming the existing ADNI Labeled Property Graph into a true Knowledge Graph with causal discovery capabilities. It is designed for **Claude Code** (Anthropic's CLI agent) so you can execute each step directly from your terminal — and **resume after token cooldowns**.

**Timeline:** February 24 – May 2026 (thesis defense)
**Current State:** Neo4j LPG with ~407K nodes, ~1.16M relationships, 16 pipeline steps
**Target State:** Semantic KG with ICD-10 via SPARQL, composite constraints, causal discovery edges

---

## Quick Start for New Claude Code Sessions

```
1. Read this file: CLAUDE_CODE_GUIDE.md
2. Read TASKS.md → find the FIRST unchecked task
3. Execute that task
4. Check it off in TASKS.md
5. Continue until token limit approaches
6. Save progress notes at the bottom of TASKS.md
```

---

## Project Structure

```
ADNIKnowledgeGraph/
├── steps/                              # Pipeline steps (executable)
│   ├── step1_database_setup.py         # ✅ Neo4j + ES setup
│   ├── step2_load_tables.py            # ✅ Load 108 CSV tables
│   ├── step3_create_patients.py        # ✅ Patient node creation
│   ├── step4_extract_family.py         # ✅ Family history
│   ├── step5_improved_process_images.py # ✅ DICOM/NIfTI processing (NO JPEG2K)
│   ├── step5_improved_process_images_with_tiff.py # ✅ Alt version with TIFF
│   ├── step6_extract_findings_robust.py # ✅ Clinical findings
│   ├── step7_batch_insert.py           # ✅ Batch insert (NO hash detection)
│   ├── step8_create_relationships.py   # ✅ Relationship creation
│   ├── step9_knowledge_graph_enhancer.py # ✅ Graph enrichment
│   ├── step10_execute_queries.py       # ✅ Query execution
│   ├── step11_biomarker_analysis.py    # ✅ Biomarker analysis
│   ├── step12_complete_graph_enhancement.py # ✅ Enhancement
│   ├── step13_graph_eda.py             # ✅ EDA
│   ├── step14_test_queries.py          # ✅ Research queries
│   ├── step15_event_based_model.py     # ✅ Event-based model
│   ├── step16_create_metrics.py        # ✅ Performance metrics
│   ├── step17_apply_constraints.py     # ❌ TO BUILD: Composite unique constraints
│   ├── step18_add_ontology_properties.py # ❌ TO BUILD: SNOMED/LOINC/UBERON codes
│   ├── step19_icd10_integration.py     # ❌ TO BUILD: WHO ICD API + rdflib
│   ├── step20_ontology_layer.py        # ❌ TO BUILD: OntologyConcept + MAPS_TO
│   ├── step21_extract_causal_features.py # ❌ TO BUILD: Feature matrix
│   ├── step22_causal_discovery.py      # ❌ TO BUILD: PC/FCI/GES
│   ├── step23_embed_causal_edges.py    # ❌ TO BUILD: CAUSES edges
│   ├── step24_alzkb_bridge.py          # ❌ TO BUILD: AlzKB integration
│   ├── step25_validate_causal.py       # ❌ TO BUILD: Validation
│   ├── step26_dowhy_inference.py       # ❌ TO BUILD: DoWhy
│   ├── step27_final_stats.py           # ❌ TO BUILD: Statistics
│   └── step28_thesis_figures.py        # ❌ TO BUILD: Figures
├── models/
│   └── entities.py                     # Data models (Patient, Visit, etc.)
├── utils/
│   ├── neo4j_connector.py              # Neo4j connection wrapper
│   ├── batch_processor.py              # Batch processing utilities
│   └── quality_aware_logger.py         # Logging
├── misc/                               # Miscellaneous utilities
├── ontology/                           # ❌ TO CREATE
│   ├── icd10_cache.json                # Cached WHO ICD API responses
│   ├── icd10_mappings.json             # Static ICD-10 hierarchy
│   └── concept_mappings.json           # SNOMED/LOINC/UBERON tables
├── causal/                             # ❌ TO CREATE
│   ├── causal_features.csv             # Extracted baseline features
│   ├── consensus_edges.json            # Edges found by ≥2 algorithms
│   └── *.png                           # Algorithm output graphs
├── thesis_output/                      # ❌ TO CREATE
│   ├── *.svg                           # Publication figures
│   ├── validation_report.md            # Validation results
│   └── final_stats.json                # Graph statistics
├── config.yaml                         # Pipeline configuration
├── pipeline.py                         # Main orchestrator
├── headers.json                        # 108 ADNI tables with column names
├── requirements.txt                    # Python dependencies
├── docker-compose.yml                  # Neo4j + ES containers
├── kg_streamlit_ui.py                  # UI (existing)
├── new_pipeline4_6.py                  # Alt pipeline (existing)
├── IMPLEMENTATION_PLAN.md              # Detailed plan (this project)
├── TASKS.md                            # Granular task checklist
└── CLAUDE_CODE_GUIDE.md                # THIS FILE
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
pip install rdflib SPARQLWrapper requests-oauthlib causal-learn dowhy
pip install pandas numpy scipy networkx matplotlib graphviz
pip install glymur  # JPEG2000 support
```

### 2. Required Accounts (Free)

| Service | URL | What You Need | Time to Get |
|---------|-----|---------------|-------------|
| WHO ICD API | https://icd.who.int/icdapi | Client ID + Secret (OAuth2) | ~5 minutes |
| BioPortal REST API | https://bioportal.bioontology.org/account | API Key | ~2 minutes |
| ADNI Data | https://ida.loni.usc.edu | Already have access | — |

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

## Data Sources — Verified as of February 2026

### ✅ CONFIRMED AVAILABLE

| Source | Status | Access Method | Notes |
|--------|--------|---------------|-------|
| **WHO ICD API** (ICD-10) | ✅ Active | REST API (OAuth2) | Supports ICD-10 2008/2010/2016 releases. Free. |
| **FBK ICD-10 OWL** | ✅ Available | Download OWL file | CC BY-NC-SA license. Local rdflib queries. |
| **ICDO GitHub** | ✅ Available | `git clone github.com/icdo/ICDO` | OWL representation of ICD-10 + ICD-9. |
| **BioPortal REST API** | ✅ Active | REST API (API Key) | SPARQL endpoint is SHUT DOWN, but REST works. |
| **causal-learn** | ✅ v0.1.4.3 on PyPI | `pip install causal-learn` | PC, FCI, GES, LiNGAM, DAG-GNN. MIT license. |
| **DoWhy** | ✅ Active | `pip install dowhy` | Causal inference + refutation. |
| **rdflib** | ✅ Active | `pip install rdflib` | Local SPARQL on downloaded OWL files. |
| **SNOMED-CT** | ✅ Available | UMLS download or BioPortal REST | Need UMLS license (free for research). |
| **LOINC** | ✅ Available | https://loinc.org/downloads | Free registration required. |

### ⚠️ CRITICAL: BioPortal SPARQL is DEAD

**BioPortal's SPARQL endpoint (sparql.bioontology.org) is DEPRECATED and SHUT DOWN.**

The v2 blueprint showed SPARQL queries to BioPortal. This will NOT work. Instead, use:
1. **Primary:** WHO ICD REST API → resolve ICD-10 codes and hierarchy
2. **Secondary:** Download FBK ICD-10 OWL → query locally with rdflib SPARQL
3. **Fallback:** BioPortal REST API → get ontology terms via REST (not SPARQL)

---

## ADNI Dataset Reference

The ADNI dataset contains **108 tables** with **~5,800 columns** total. Key tables by domain:

### Patient Demographics
- `PTDEMOG` (84 cols): gender, DOB, education, ethnicity, race
- `APOERES` (16 cols): APOE genotype (APGEN1, APGEN2)
- `Study_Entry` (5 cols): enrollment info
- `ARM` (14 cols): study arm assignment

### Diagnosis
- `DXSUM` (41 cols): DXCURREN, DXCHANGE, DXCONV, DIAGNOSIS
- `BLCHANGE` (29 cols): baseline change tracking

### Cognitive Assessments (14 tables)
- `MMSE` (58 cols): Mini-Mental State Exam → MMSCORE
- `CDR` (25 cols): Clinical Dementia Rating → CDGLOBAL
- `ADAS` (16 cols): ADAS-Cog → TOTSCORE, TOTAL13
- `MOCA` (58 cols): Montreal Cognitive Assessment
- `FAQ` (27 cols): Functional Activities Questionnaire
- `GDSCALE` (32 cols): Geriatric Depression Scale
- `NPI` (168 cols) / `NPIQ` (41 cols): Neuropsychiatric Inventory
- `NEUROBAT` (83 cols): Neuropsychological Battery
- `ECOGPT` (62 cols) / `ECOGSP` (59 cols): ECog scales
- `STAIAD` (21 cols): State-Trait Anxiety

### CSF Biomarkers
- `UPENNBIOMK_ROCHE_ELECSYS` (13 cols): Abeta42, Abeta40, tau, ptau → PRIMARY
- `BIOMARK` (65 cols): legacy biomarker data
- `FOXLABBSI` (28 cols): Fox Lab BSI data

### Blood Biomarkers
- `LABDATA` (132 cols): comprehensive lab data
- `URMC_LABDATA` (28 cols): Rochester lab data
- `FNIHBC_BLOOD_BIOMARKER_TRAJECTORIES` (20 cols): FNIH trajectories
- `JANSSEN_PLASMA_P217_TAU` (9 cols): plasma p-tau217

### Neuroimaging — MRI
- `Key_MRI` (23 cols): MRI metadata keys
- `Structural_MRI_Images` (23 cols): structural MRI records
- `MRI3META` (42 cols) / `MRIMETA` (35 cols): MRI metadata
- `MRI_Images_with_AI` (8 cols): AI-processed images

### Neuroimaging — PET
- `Key_PET` (8 cols): PET metadata keys
- `PET_Images` (24 cols): PET scan records
- `AV45META` (51 cols): Florbetapir (amyloid) metadata
- `AMYMETA` (38 cols): Amyloid metadata
- `TAUMETA` (39 cols): Tau PET metadata

### Volumetrics
- `UCSFFSX7` (347 cols): FreeSurfer cross-sectional (ST* columns)
- `UCBERKELEY_AMY_6MM` (344 cols): Berkeley amyloid regional
- `UCBERKELEY_TAU_6MM` (339 cols): Berkeley tau regional
- `UCBERKELEY_TAUPVC_6MM` (335 cols): Berkeley tau PVC
- `UCD_WMH` (27 cols): white matter hyperintensities
- `DTIROI_MEAN` (309 cols) / `DTIROI_ROBUSTMEAN` (309 cols): DTI

### Genetics
- `APOERES` (16 cols): APOE results
- `GENETIC` (57 cols): comprehensive genetic data

### Medications & Adverse Events
- `BACKMEDS` (15 cols): background medications
- `RECCMEDS` (30 cols): concomitant medications
- `ANTIAMYTX` (20 cols): anti-amyloid treatment
- `ADVERSE` (88 cols) / `ADSXLIST` (39 cols) / `RECADV` (38 cols): adverse events

### Family History
- `FAMHXPAR` (24 cols): parental history
- `FAMHXSIB` (22 cols): sibling history
- `FHQ` (18 cols) / `RECFHQ` (15 cols): family history questionnaire

### Neuropathology
- `NEUROPATH` (164 cols): Braak stage, CERAD, Thal phase, Lewy body

---

## KG Schema Reference (Target State)

### 17 Node Types

| Node | Key Properties | Ontology | From Tables |
|------|---------------|----------|-------------|
| Patient | ptid (PK), rid, sex, birth_year, education | ncit:C16960 | PTDEMOG, APOERES |
| Visit | visit_id (PK: ptid+viscode), viscode, visit_date | ncit:C159705 | All tables |
| Diagnosis | dx_label (CN/MCI/AD), snomed_code, icd10_code | SNOMED + ICD-10 | DXSUM |
| CognitiveAssessment | test_name, total_score, loinc_code | LOINC | 14 assessment tables |
| CSFBiomarker | abeta42, tau, ptau, assay, loinc_code | LOINC | UPENNBIOMK, BIOMARK |
| BloodBiomarker | analyte, value, assay, loinc_code | LOINC | LABDATA, FNIHBC |
| ATNProfile | a_status, t_status, n_status, atn_class | NIA-AA | Derived |
| MRIScan | image_id (PK), sequence, field_strength | DICOM | Key_MRI, MRI3META |
| PETScan | image_id (PK), tracer, centiloids, suvr | SNOMED | Key_PET, AV45META |
| VolumetricMeasure | region_name, volume_mm3, cortical_thickness | UBERON | UCSFFSX7, UCBERKELEY |
| BrainRegion | name, hemisphere, uberon_code | UBERON | Reference data |
| GeneticProfile | apoe_genotype, risk_snps | Gene Ontology | APOERES, GENETIC |
| GeneticRiskFactor | gene_symbol, variant, risk_level | — | GENETIC |
| Medication | compound_name, drug_class, rxnorm_code | RxNorm | BACKMEDS, RECCMEDS |
| AdverseEvent | description, severity, meddra_code | MedDRA | ADVERSE |
| FamilyMember | relationship, has_dementia, age_at_onset | HPO | FAMHXPAR, FAMHXSIB |
| NeuropathFinding | braak_stage, cerad_score, thal_phase | SNOMED | NEUROPATH |
| OntologyConcept | uri (PK), code, label, source_ontology | Self-referencing | Imported |
| ConversionEvent | from_dx, to_dx, conversion_month | Custom | Derived from DXSUM |
| BatchIngestion | batch_id, rows_processed, nodes_created | — | Audit trail |

### 20+ Relationship Types

| Relationship | Source → Target | URI |
|-------------|----------------|-----|
| HAS_VISIT | Patient → Visit | ro:RO_0000056 |
| FOLLOWED_BY | Visit → Visit | time:intervalBefore |
| HAS_DIAGNOSIS | Visit → Diagnosis | ro:RO_0000091 |
| PROGRESSED_TO | Diagnosis → Diagnosis | ro:RO_0002263 |
| YIELDED_ASSESSMENT | Visit → CognitiveAssessment | ro:RO_0002234 |
| HAS_CSF_BIOMARKER | Visit → CSFBiomarker | ro:RO_0002234 |
| HAS_BLOOD_BIOMARKER | Visit → BloodBiomarker | ro:RO_0002234 |
| HAS_ATN_PROFILE | Visit → ATNProfile | adni:derived_from |
| HAS_MRI_SCAN | Visit → MRIScan | ro:RO_0002234 |
| HAS_PET_SCAN | Visit → PETScan | ro:RO_0002234 |
| HAS_VOLUMETRIC | MRIScan → VolumetricMeasure | ro:RO_0002234 |
| MEASURES_REGION | VolumetricMeasure → BrainRegion | bfo:BFO_0000066 |
| HAS_GENETIC_PROFILE | Patient → GeneticProfile | ro:RO_0000053 |
| TAKES_MEDICATION | Patient → Medication | ro:RO_0000056 |
| MAPS_TO | Any → OntologyConcept | skos:exactMatch |
| IS_A | OntologyConcept → OntologyConcept | rdfs:subClassOf |
| CLASSIFIED_AS | Diagnosis → ICD-10 Concept | skos:exactMatch |
| SAME_AS | OntologyConcept → AlzKB entity | owl:sameAs |
| CAUSES | Any → Any (Phase 2) | ro:RO_0002411 |

---

## Implementation Phases

### Phase 1: Schema Migration (LPG → KG) — ~2 weeks

**Goal:** Transform existing LPG into semantically grounded KG without rebuilding.

| Step | File | Description | Depends On |
|------|------|-------------|------------|
| 17 | step17_apply_constraints.py | Composite unique constraints + indexes | Neo4j 5.x |
| 18 | step18_add_ontology_properties.py | Add SNOMED/LOINC/UBERON codes to nodes | Step 17 |
| 19 | step19_icd10_integration.py | WHO ICD API + rdflib → ICD-10 hierarchy | Step 18 |
| 20 | step20_ontology_layer.py | OntologyConcept nodes + MAPS_TO edges | Steps 18, 19 |

### Phase 1.5: Image & Insertion Enhancements — ~1 week

| Step | File | Description | Depends On |
|------|------|-------------|------------|
| 5b | step5 modifications | JPEG2000/HTJ2K lossless conversion | glymur/openjpeg |
| 7b | step7 modifications | Hash-based change detection + audit trail | Step 17 |

### Phase 2: Causal Discovery — ~2 weeks

| Step | File | Description | Depends On |
|------|------|-------------|------------|
| 21 | step21_extract_causal_features.py | Extract flat feature matrix from KG | Phase 1 |
| 22 | step22_causal_discovery.py | PC, FCI, GES algorithms | Step 21 |
| 23 | step23_embed_causal_edges.py | CAUSES edges in KG | Step 22 |

### Phase 3: Validation & Integration — ~2 weeks

| Step | File | Description | Depends On |
|------|------|-------------|------------|
| 24 | step24_alzkb_bridge.py | AlzKB SAME_AS edges | Step 20 |
| 25 | step25_validate_causal.py | Precision/recall vs. known AD biology | Steps 23, 24 |
| 26 | step26_dowhy_inference.py | Causal effect estimation + refutation | Step 22 |

### Phase 4: Documentation — ~1 week

| Step | File | Description | Depends On |
|------|------|-------------|------------|
| 27 | step27_final_stats.py | Graph statistics + report | All above |
| 28 | step28_thesis_figures.py | SVG/PNG figures for thesis | All above |

---

## Connector Pattern Reference

All new steps should follow the existing connector pattern. Here's the template:

```python
"""
Step N: [Description]
"""

import logging
from typing import Dict, Any
from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


def execute_step_n(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                   **kwargs) -> Dict[str, Any]:
    """
    Execute step N.

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Neo4j username
        neo4j_password: Neo4j password

    Returns:
        Dictionary with execution results
    """
    results = {'status': 'started', 'errors': [], 'stats': {}}

    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        with connector.driver.session() as session:
            # Your logic here
            pass

        results['status'] = 'completed'
    except Exception as e:
        logger.error(f"Step N failed: {e}")
        results['status'] = 'failed'
        results['errors'].append(str(e))
    finally:
        connector.close()

    return results
```

### Registration in pipeline.py

```python
# In pipeline.py imports section:
from steps.step17_apply_constraints import execute_constraints

# In ADNIPipeline.run():
if self.config.get('run_apply_constraints', True):
    self._run_step(17, "Apply Constraints", self._execute_constraints)

# Add method:
def _execute_constraints(self) -> Dict[str, Any]:
    return execute_constraints(
        neo4j_uri=self.config['neo4j_uri'],
        neo4j_user=self.config['neo4j_user'],
        neo4j_password=self.config['neo4j_password'],
    )
```

---

## Ontology Mapping Tables

### Diagnosis → SNOMED + ICD-10 + MONDO

```python
DIAGNOSIS_ONTOLOGY = {
    "AD": {
        "snomed_code": "26929004",
        "icd10_code": "G30.9",
        "mondo_code": "MONDO:0004975",
        "rdf_type": "snomed:26929004",
    },
    "MCI": {
        "snomed_code": "386806002",
        "icd10_code": "F06.7",
        "mondo_code": "MONDO:0024647",
        "rdf_type": "snomed:386806002",
    },
    "CN": {
        "snomed_code": "17621005",
        "icd10_code": "Z03.89",
        "rdf_type": "snomed:17621005",
    },
    "Dementia": {
        "snomed_code": "52448006",
        "icd10_code": "F03.9",
        "mondo_code": "MONDO:0001627",
    },
}
```

### CognitiveAssessment → LOINC

```python
ASSESSMENT_LOINC = {
    "MMSE": "72106-8",
    "CDR": "72172-0",
    "ADAS": "72194-4",
    "MOCA": "72133-2",
    "FAQ": "72107-6",
    "GDS": "72166-2",
    "NPI": "72169-6",
    "NPIQ": "72169-6",
    "NEUROBAT": "72196-9",
    "ECOGPT": "72175-3",
    "ECOGSP": "72175-3",
    "STAIAD": "72198-5",
}
```

### CSFBiomarker → LOINC

```python
CSF_LOINC = {
    "Abeta42": "72333-6",
    "Abeta40": "72332-8",
    "tau": "72335-1",
    "ptau": "72334-4",
    "ratio_42_40": "72336-9",
}
```

### BrainRegion → UBERON

```python
BRAIN_UBERON = {
    "Hippocampus": "0002421",
    "Entorhinal": "0002728",
    "Amygdala": "0001876",
    "Frontal": "0001870",
    "Temporal": "0001871",
    "Parietal": "0001872",
    "Occipital": "0002021",
    "Cingulate": "0003027",
    "Insula": "0002022",
    "Caudate": "0001873",
    "Putamen": "0001874",
    "Thalamus": "0001897",
}
```

---

## Common Claude Code Prompts

### For exploring the current graph

```
Connect to my Neo4j at bolt://localhost:7687 (user: neo4j, password from
config.yaml). Run these exploration queries and summarize what you find:
1. CALL db.labels() — what node types exist?
2. CALL db.relationshipTypes() — what edge types exist?
3. MATCH (n) RETURN labels(n)[0] as label, count(n) ORDER BY count(n) DESC
4. MATCH ()-[r]->() RETURN type(r), count(r) ORDER BY count(r) DESC
5. MATCH (p:Patient) RETURN count(p) — how many patients?
```

### For executing a specific step

```
Read TASKS.md and find the first unchecked task. Execute it following the
patterns in the existing pipeline code. After completing, check it off and
verify the result.
```

### For debugging constraint issues

```
My step17 is failing with "Property does not exist" errors. Check what
properties actually exist on the target nodes:
  MATCH (c:CognitiveAssessment) RETURN keys(c) LIMIT 5
Then adapt the constraint to use the actual property names.
```

### For validating ICD-10 integration

```
Check if ICD-10 integration worked:
1. MATCH (o:OntologyConcept {source_ontology: 'ICD-10'}) RETURN o.code, o.label
2. MATCH (d:Diagnosis)-[:CLASSIFIED_AS]->(o) RETURN d.dx_label, o.code, o.label
3. MATCH path = (:OntologyConcept {code: 'G30.9'})-[:IS_A*]->(parent)
   RETURN [n in nodes(path) | n.code + ': ' + n.label]
```

### For causal discovery

```
Read step21 output (causal/causal_features.csv). Verify it has the expected
columns and sample size. Then run step22 with PC, FCI, GES. Save results
to causal/ directory. Report which edges were found by which algorithms.
```

### For resuming after cooldown

```
Read TASKS.md. Find the first unchecked task. Read the relevant step files
for context. Continue execution from where we left off. Check off completed
tasks.
```

---

## Risk Mitigation

| Risk | Probability | Mitigation |
|------|-------------|------------|
| WHO ICD API down | Low | FBK ICD-10 OWL fallback + rdflib local SPARQL |
| Neo4j composite constraints not supported | Medium | Check version first (`CALL dbms.components()`). Need 5.x. |
| Causal-learn produces empty graph | Medium | Lower alpha to 0.1, use KCI for mixed data |
| Not enough patients with complete baseline data | Low | ADNI has ~2,400 patients. Even 30% completeness → 700+ rows. |
| AlzKB dump not downloadable | Medium | Use paper tables manually; create 50 key concepts by hand |
| BioPortal SPARQL down | **Confirmed** | Already mitigated: WHO REST API + local rdflib |

---

## Success Criteria

By thesis defense, the KG must have:

- [ ] ~407K+ nodes (original) + ~200 OntologyConcept nodes + ICD-10 hierarchy
- [ ] All observation nodes with composite unique constraints
- [ ] MAPS_TO edges connecting data nodes to OntologyConcept
- [ ] CLASSIFIED_AS edges from Diagnosis to ICD-10 (via WHO API)
- [ ] IS_A hierarchy for ICD-10, SNOMED-CT concepts
- [ ] Causal discovery results from at least PC + FCI + GES
- [ ] CAUSES edges with metadata (algorithm, p_value, confidence)
- [ ] AlzKB bridge with SAME_AS edges for overlapping concepts
- [ ] Validation report: precision/recall vs. known AD biology
- [ ] Publication-quality SVG figures for thesis
- [ ] Hash-based change detection + BatchIngestion audit trail
- [ ] JPEG2000 lossless tier in image pipeline

---

## Config Additions Needed

Add these sections to `config.yaml`:

```yaml
# WHO ICD API credentials
who_icd:
  client_id: "YOUR_CLIENT_ID"
  client_secret: "YOUR_CLIENT_SECRET"
  token_url: "https://icdaccessmanagement.who.int/connect/token"
  api_url: "https://id.who.int/icd"
  release: "2019"

# BioPortal REST API
bioportal:
  api_key: "YOUR_API_KEY"
  base_url: "https://data.bioontology.org"

# Causal discovery settings
causal:
  alpha: 0.05
  algorithms: ["PC", "FCI", "GES"]
  consensus_threshold: 2
  independence_test: "fisherz"
  max_missing_pct: 0.5

# New pipeline steps
run_apply_constraints: true
run_ontology_properties: true
run_icd10_integration: true
run_ontology_layer: true
run_causal_feature_extraction: true
run_causal_discovery: true
run_embed_causal_edges: true
run_alzkb_bridge: true
run_validate_causal: true
run_dowhy_inference: true
run_final_stats: true
run_thesis_figures: true
```

---

## Thesis Narrative: Construct → Discover → Represent

The thesis follows a three-act structure:

1. **Construct:** Build a semantic KG from ADNI data (108 tables → 17 node types, 20+ relationship types, ontology grounding)
2. **Discover:** Apply causal discovery algorithms (PC, FCI, GES) to extract causal relationships from the KG
3. **Represent:** Embed discovered causal edges back into the KG as native CAUSES relationships, validated against AlzKB and known AD biology

This is what's original: no existing work combines (1) a full-scale ADNI data graph (108 tables, 407K nodes) with (2) semantic ontology grounding AND (3) causal discovery integration where discovered causal edges become native KG relationships.

---

## References

- **Blueprint v1:** `ADNI_KG_Design_Blueprint.pdf` (in project files)
- **Blueprint v2:** `ADNI_KG_Blueprint_v2.pdf` (in project files, incorporates Prof. Turhan's feedback)
- **IEEE Paper:** `IEEE_Big_Data_2025_Oguzhan.pdf`
- **Thesis Draft:** `OğuzhanGüngör_Tez_1.pdf`
- **AlzKB:** Romano et al. 2024, 118,902 entities, 1,309,527 relationships
- **Shen et al. 2020:** FCI on ADNI biomarkers, 71% precision
- **Dobreva et al. 2025:** AD-KG 2.0 framework, validates Construct→Discover→Represent

---

*Last updated: 2026-02-23*
*Next action: Open TASKS.md → Execute T0.1*
