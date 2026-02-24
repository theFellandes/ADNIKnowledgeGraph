# ADNI Knowledge Graph — Claude Code Execution Guide

## Overview

This guide is your step-by-step playbook for transforming the existing ADNI Labeled Property Graph into a true Knowledge Graph with causal discovery capabilities. It's designed for use with **Claude Code** (Anthropic's CLI agent) so you can execute each step directly from your terminal.

**Timeline:** February 24 – March 30, 2026 (5 weeks)  
**Current State:** Neo4j LPG with ~407K nodes, ~1.16M relationships, 16 pipeline steps  
**Target State:** Semantic KG with ICD-10 via SPARQL, composite constraints, causal discovery edges  

---

## Prerequisites

### 1. Environment Setup

```bash
# Clone your repo (if not already)
git clone https://github.com/theFellandes/ADNIKnowledgeGraph.git
cd ADNIKnowledgeGraph

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install existing dependencies
pip install -r requirements.txt

# Install NEW dependencies for KG enhancement
pip install rdflib SPARQLWrapper requests-oauthlib causal-learn dowhy
pip install pandas numpy scipy networkx matplotlib
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
# Test connection
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

## Data Source Verification

Before starting, confirm every data source is accessible. This has been verified as of February 2026:

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

### ⚠️ IMPORTANT CHANGE FROM v2 BLUEPRINT

**BioPortal's SPARQL endpoint (sparql.bioontology.org) is DEPRECATED and SHUT DOWN.**

The v2 blueprint showed SPARQL queries to BioPortal. This will NOT work. Instead, use:

1. **Primary:** WHO ICD REST API → resolve ICD-10 codes and hierarchy  
2. **Secondary:** Download FBK ICD-10 OWL → query locally with rdflib SPARQL  
3. **Fallback:** BioPortal REST API → get ontology terms via REST (not SPARQL)  

This actually makes the implementation cleaner — no dependency on an external SPARQL endpoint that can go down.

---

## Week-by-Week Execution Plan

### WEEK 1 (Feb 24–Mar 2): Constraints + Ontology Properties

**Goal:** Apply composite unique constraints, add ontology codes to existing nodes.

#### Day 1-2: Apply Constraints

Create a new pipeline step: `step17_apply_constraints.py`

```python
"""
Step 17: Apply Composite Unique Constraints
Must run BEFORE any new data ingestion.
"""

CONSTRAINTS = [
    # Core entities
    "CREATE CONSTRAINT patient_ptid IF NOT EXISTS FOR (p:Patient) REQUIRE p.ptid IS UNIQUE",
    "CREATE CONSTRAINT visit_id IF NOT EXISTS FOR (v:Visit) REQUIRE v.visit_id IS UNIQUE",
    "CREATE CONSTRAINT mri_image_id IF NOT EXISTS FOR (m:MRIScan) REQUIRE m.image_id IS UNIQUE",
    "CREATE CONSTRAINT pet_image_id IF NOT EXISTS FOR (p:PETScan) REQUIRE p.image_id IS UNIQUE",
    "CREATE CONSTRAINT brain_region IF NOT EXISTS FOR (b:BrainRegion) REQUIRE (b.name, b.hemisphere) IS UNIQUE",
    "CREATE CONSTRAINT ontology_uri IF NOT EXISTS FOR (o:OntologyConcept) REQUIRE o.uri IS UNIQUE",
    
    # Observation nodes (PREVENTS DUPLICATES — Prof. Turhan's feedback)
    "CREATE CONSTRAINT assess_unique IF NOT EXISTS FOR (c:CognitiveAssessment) REQUIRE (c.visit_id, c.test_name) IS UNIQUE",
    "CREATE CONSTRAINT csf_unique IF NOT EXISTS FOR (c:CSFBiomarker) REQUIRE (c.visit_id, c.assay) IS UNIQUE",
    "CREATE CONSTRAINT blood_unique IF NOT EXISTS FOR (b:BloodBiomarker) REQUIRE (b.visit_id, b.analyte, b.assay) IS UNIQUE",
    "CREATE CONSTRAINT vol_unique IF NOT EXISTS FOR (v:VolumetricMeasure) REQUIRE (v.visit_id, v.region_name, v.hemisphere) IS UNIQUE",
    "CREATE CONSTRAINT atn_unique IF NOT EXISTS FOR (a:ATNProfile) REQUIRE (a.visit_id) IS UNIQUE",
    "CREATE CONSTRAINT dx_unique IF NOT EXISTS FOR (d:Diagnosis) REQUIRE (d.visit_id, d.dx_label) IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX patient_rid IF NOT EXISTS FOR (p:Patient) ON (p.rid)",
    "CREATE INDEX visit_ptid IF NOT EXISTS FOR (v:Visit) ON (v.ptid)",
    "CREATE INDEX visit_viscode IF NOT EXISTS FOR (v:Visit) ON (v.viscode)",
    "CREATE INDEX dx_label IF NOT EXISTS FOR (d:Diagnosis) ON (d.dx_label)",
    "CREATE INDEX dx_icd10 IF NOT EXISTS FOR (d:Diagnosis) ON (d.icd10_code)",
    "CREATE INDEX dx_snomed IF NOT EXISTS FOR (d:Diagnosis) ON (d.snomed_code)",
    "CREATE INDEX assess_test IF NOT EXISTS FOR (c:CognitiveAssessment) ON (c.test_name)",
    "CREATE INDEX assess_loinc IF NOT EXISTS FOR (c:CognitiveAssessment) ON (c.loinc_code)",
    "CREATE INDEX atn_class IF NOT EXISTS FOR (a:ATNProfile) ON (a.atn_class)",
    "CREATE INDEX pet_tracer IF NOT EXISTS FOR (p:PETScan) ON (p.tracer)",
    "CREATE INDEX vol_region IF NOT EXISTS FOR (v:VolumetricMeasure) ON (v.region_name)",
    "CREATE INDEX med_name IF NOT EXISTS FOR (m:Medication) ON (m.compound_name)",
    "CREATE INDEX ontology_code IF NOT EXISTS FOR (o:OntologyConcept) ON (o.code)",
    "CREATE INDEX ontology_src IF NOT EXISTS FOR (o:OntologyConcept) ON (o.source_ontology)",
]

def execute_constraints(connector):
    """Apply all constraints and indexes."""
    with connector.driver.session() as session:
        for c in CONSTRAINTS:
            try:
                session.run(c)
                print(f"  ✓ {c[:60]}...")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"  ○ Already exists: {c[:50]}...")
                else:
                    print(f"  ✗ Failed: {e}")
        
        for idx in INDEXES:
            try:
                session.run(idx)
                print(f"  ✓ {idx[:60]}...")
            except Exception as e:
                print(f"  ○ {idx[:50]}... ({e})")
```

**Claude Code prompt:**
```
Read step9_knowledge_graph_enhancer.py and the config.yaml to understand the 
connector pattern. Then create step17_apply_constraints.py following the same 
pattern. Apply all composite unique constraints and indexes from the blueprint. 
Handle "already exists" errors gracefully. Register it in pipeline.py.
```

#### Day 3-4: Add Ontology Properties to Existing Nodes

Create `step18_add_ontology_properties.py`

This step adds SNOMED codes, LOINC codes, UBERON codes, ICD-10 codes to existing nodes. It does NOT create new nodes — it enriches existing ones.

```python
"""
Step 18: Add Ontology Properties to Existing Nodes (In-Place Upgrade)
"""

# Diagnosis mappings
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
        "rdf_type": "snomed:52448006",
    },
}

# Cognitive assessment LOINC mappings
ASSESSMENT_LOINC = {
    "MMSE": "72106-8",
    "MoCA": "72172-0",
    "CDR": "CDR-SB",       # No single LOINC — use CDR-SB convention
    "ADAS": "89249-2",     # ADAS-Cog
    "FAQ": "89252-6",
    "GDS": "44261-6",
    "NPI": "NPI-Q",
}

# Brain region UBERON mappings  
BRAIN_REGION_UBERON = {
    "Hippocampus": "UBERON:0002421",
    "Entorhinal": "UBERON:0002728",
    "Fusiform": "UBERON:0002766",
    "MidTemporal": "UBERON:0002771",
    "InferiorTemporal": "UBERON:0002751",
    "Precuneus": "UBERON:0006083",
    "PosteriorCingulate": "UBERON:0002600",
}

def add_diagnosis_ontology(session):
    """Add ICD-10, SNOMED, MONDO codes to Diagnosis nodes."""
    for dx_label, codes in DIAGNOSIS_ONTOLOGY.items():
        set_clauses = ", ".join(f"d.{k} = '{v}'" for k, v in codes.items())
        query = f"""
            MATCH (d:Diagnosis) 
            WHERE d.dx_label CONTAINS '{dx_label}' OR d.diagnosis CONTAINS '{dx_label}'
            SET {set_clauses}, d.ontology_updated = datetime()
            RETURN count(d) as updated
        """
        result = session.run(query)
        count = result.single()["updated"]
        print(f"  ✓ {dx_label}: {count} nodes updated with {list(codes.keys())}")

def add_assessment_loinc(session):
    """Add LOINC codes to CognitiveAssessment nodes."""
    for test_name, loinc in ASSESSMENT_LOINC.items():
        query = f"""
            MATCH (c:CognitiveAssessment)
            WHERE c.test_name = '{test_name}'
            SET c.loinc_code = '{loinc}', c.ontology_updated = datetime()
            RETURN count(c) as updated
        """
        result = session.run(query)
        count = result.single()["updated"]
        print(f"  ✓ {test_name} → LOINC {loinc}: {count} nodes")

def add_brain_region_uberon(session):
    """Add UBERON codes to BrainRegion or VolumetricMeasure nodes."""
    for region, uberon in BRAIN_REGION_UBERON.items():
        query = f"""
            MATCH (v:VolumetricMeasure)
            WHERE v.region_name CONTAINS '{region}'
            SET v.uberon_code = '{uberon}', v.ontology_updated = datetime()
            RETURN count(v) as updated
        """
        result = session.run(query)
        count = result.single()["updated"]
        print(f"  ✓ {region} → {uberon}: {count} nodes")
```

**Claude Code prompt:**
```
Create step18_add_ontology_properties.py that adds SNOMED, ICD-10, LOINC, 
and UBERON codes to existing Diagnosis, CognitiveAssessment, CSFBiomarker, 
and VolumetricMeasure nodes. Use the mapping tables from the blueprint. 
Follow the connector pattern from step9. Add it to pipeline.py.
Check what node labels and property names currently exist in the graph first 
by running: CALL db.labels() and CALL db.propertyKeys()
```

#### Day 5: Add Audit Properties

```python
# Add data_hash and batch tracking to all existing nodes
"""
MATCH (n) WHERE NOT exists(n.created_at)
SET n.created_at = datetime(), n.source_pipeline = 'v1_original'
"""
```

---

### WEEK 2 (Mar 3–9): ICD-10 via WHO API + OntologyConcept Layer

**Goal:** Resolve ICD-10 hierarchies, create OntologyConcept nodes, build MAPS_TO edges.

#### Day 1-2: WHO ICD API Integration

Create `step19_icd10_integration.py`

```python
"""
Step 19: ICD-10 Integration via WHO ICD API
Resolves disease hierarchy and caches in Neo4j as OntologyConcept nodes.
"""

import requests
import json
import time

# WHO ICD API Configuration
TOKEN_ENDPOINT = "https://icdaccessmanagement.who.int/connect/token"
ICD10_BASE = "https://id.who.int/icd/release/10/2016"

class WHOICDClient:
    """Client for WHO ICD-10 REST API."""
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
    
    def authenticate(self):
        """Get OAuth2 access token."""
        resp = requests.post(TOKEN_ENDPOINT, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "icdapi_access",
            "grant_type": "client_credentials",
        })
        resp.raise_for_status()
        self.token = resp.json()["access_token"]
        return self.token
    
    def get_code(self, code: str) -> dict:
        """Get ICD-10 code details including parent hierarchy."""
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Accept-Language": "en",
            "API-Version": "v2",
        }
        # ICD-10 codes use format like G30.9 -> G30/9
        url_code = code.replace(".", "/")
        url = f"{ICD10_BASE}/{url_code}"
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()
    
    def get_hierarchy(self, code: str, max_depth=5) -> list:
        """Walk up the ICD-10 hierarchy from a code to the root."""
        chain = []
        current = code
        for _ in range(max_depth):
            try:
                data = self.get_code(current)
                chain.append({
                    "code": current,
                    "title": data.get("title", {}).get("@value", ""),
                    "parent": data.get("parent", [""])[0] if data.get("parent") else "",
                })
                # Extract parent code from URI
                parent_uri = data.get("parent", [""])[0] if data.get("parent") else ""
                if not parent_uri or parent_uri == ICD10_BASE:
                    break
                current = parent_uri.split("/")[-1].replace("/", ".")
                time.sleep(0.2)  # Rate limiting
            except Exception as e:
                print(f"  ⚠ Could not resolve {current}: {e}")
                break
        return chain

# Codes relevant to ADNI
ADNI_ICD10_CODES = ["G30.9", "G30.0", "G30.1", "F06.7", "F03.9", "Z03.89"]

def resolve_and_store(client, session):
    """Resolve ICD-10 hierarchies and store as OntologyConcept nodes."""
    for code in ADNI_ICD10_CODES:
        hierarchy = client.get_hierarchy(code)
        for item in hierarchy:
            # Create OntologyConcept node
            session.run("""
                MERGE (c:OntologyConcept {uri: $uri})
                ON CREATE SET
                    c.code = $code,
                    c.label = $label,
                    c.source_ontology = 'ICD-10',
                    c.created_at = datetime()
                ON MATCH SET
                    c.label = $label,
                    c.updated_at = datetime()
            """, uri=f"icd10:{item['code']}", code=item["code"], label=item["title"])
        
        # Create IS_A hierarchy
        for i in range(len(hierarchy) - 1):
            session.run("""
                MATCH (child:OntologyConcept {uri: $child_uri})
                MATCH (parent:OntologyConcept {uri: $parent_uri})
                MERGE (child)-[:IS_A]->(parent)
            """, child_uri=f"icd10:{hierarchy[i]['code']}",
                 parent_uri=f"icd10:{hierarchy[i+1]['code']}")
        
        print(f"  ✓ {code}: {len(hierarchy)} levels resolved")
```

**Claude Code prompt:**
```
Create step19_icd10_integration.py. First register at https://icd.who.int/icdapi
to get client_id and client_secret. Store them in config.yaml under a new 
'who_icd' section. The step should:
1. Authenticate with WHO ICD API via OAuth2
2. Resolve ICD-10 hierarchy for each ADNI diagnosis code
3. Create OntologyConcept nodes in Neo4j for each ICD-10 code
4. Create IS_A relationships between parent-child codes
5. Create CLASSIFIED_AS edges from Diagnosis nodes to ICD-10 OntologyConcept nodes
Also implement a fallback: download the FBK ICD-10 OWL from 
https://dkm.fbk.eu/technologies/ontologies/icd-10-ontology/ and query it 
locally with rdflib if WHO API is down.
```

#### Day 3-4: Create OntologyConcept Layer for Non-Disease Ontologies

Create `step20_ontology_layer.py`

This step creates OntologyConcept nodes for SNOMED-CT, LOINC, UBERON concepts and builds MAPS_TO edges from data nodes to these concepts.

**Claude Code prompt:**
```
Create step20_ontology_layer.py that:
1. Creates ~200 OntologyConcept nodes for SNOMED-CT clinical terms
   (AD: 26929004, MCI: 386806002, CN: 17621005, Dementia: 52448006, etc.)
2. Creates OntologyConcept nodes for LOINC codes used in our assessments
   (MMSE: 72106-8, MoCA: 72172-0, Abeta42: 72333-6, Tau: 72332-8)
3. Creates OntologyConcept nodes for UBERON brain regions
   (Hippocampus: 0002421, Entorhinal: 0002728, etc.)
4. Builds IS_A hierarchies within each ontology
5. Creates MAPS_TO relationships from data nodes to their OntologyConcept
Use BioPortal REST API (key from config.yaml) to resolve terms if needed.
Note: BioPortal's SPARQL endpoint is DEAD. Use only their REST API:
  GET https://data.bioontology.org/ontologies/SNOMEDCT/classes/{code}
  Headers: Authorization: apikey token={YOUR_API_KEY}
```

#### Day 5: Verification Queries

Run these to confirm the ontology layer is working:

```cypher
-- How many OntologyConcept nodes?
MATCH (o:OntologyConcept) RETURN o.source_ontology, count(o) ORDER BY count(o) DESC

-- Does IS_A hierarchy work?
MATCH path = (child:OntologyConcept {code: 'G30.9'})-[:IS_A*]->(ancestor)
RETURN [n in nodes(path) | n.label] AS hierarchy

-- Are MAPS_TO edges connecting data to ontology?
MATCH (d:Diagnosis)-[:MAPS_TO|CLASSIFIED_AS]->(o:OntologyConcept)
RETURN d.dx_label, o.code, o.source_ontology LIMIT 20

-- Semantic query: find all patients with any form of dementia
MATCH (o:OntologyConcept {code: '52448006'})<-[:IS_A*0..]-(child)
MATCH (d:Diagnosis)-[:MAPS_TO]->(child)
MATCH (v:Visit)-[:HAS_DIAGNOSIS]->(d)
MATCH (p:Patient)-[:HAS_VISIT]->(v)
RETURN DISTINCT p.ptid, d.dx_label, child.code
```

---

### WEEK 3 (Mar 10–16): Causal Discovery

**Goal:** Extract feature matrix from KG, run PC/FCI/GES, compare results.

#### Day 1-2: Extract Baseline Feature Matrix

Create `step21_extract_causal_features.py`

```python
"""
Step 21: Extract Baseline Feature Matrix for Causal Discovery
"""

BASELINE_QUERY = """
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)
WHERE v.viscode IN ['bl', 'sc', 'scmri']

OPTIONAL MATCH (v)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
OPTIONAL MATCH (v)-[:YIELDED_ASSESSMENT]->(mmse:CognitiveAssessment {test_name: 'MMSE'})
OPTIONAL MATCH (v)-[:YIELDED_ASSESSMENT]->(cdr:CognitiveAssessment {test_name: 'CDR'})
OPTIONAL MATCH (v)-[:YIELDED_ASSESSMENT]->(adas:CognitiveAssessment {test_name: 'ADAS'})
OPTIONAL MATCH (v)-[:HAS_CSF_BIOMARKER]->(csf:CSFBiomarker)
OPTIONAL MATCH (v)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
OPTIONAL MATCH (p)-[:HAS_GENETIC_PROFILE]->(gp:GeneticProfile)

RETURN 
    p.ptid AS patient_id,
    p.sex AS sex,
    p.education_years AS education,
    p.birth_year AS birth_year,
    d.dx_label AS diagnosis,
    mmse.total_score AS mmse_score,
    cdr.total_score AS cdr_score,
    adas.total_score AS adas_score,
    csf.abeta42 AS abeta42,
    csf.tau AS tau,
    csf.ptau AS ptau,
    atn.atn_class AS atn_class,
    atn.a_status AS amyloid_status,
    atn.t_status AS tau_status,
    atn.n_status AS neurodegeneration_status,
    gp.apoe_genotype AS apoe_genotype
"""

import pandas as pd
import numpy as np

def extract_features(connector) -> pd.DataFrame:
    """Pull baseline features from KG into a DataFrame."""
    with connector.driver.session() as session:
        result = session.run(BASELINE_QUERY)
        records = [dict(r) for r in result]
    
    df = pd.DataFrame(records)
    print(f"  Extracted {len(df)} patients with {len(df.columns)} features")
    
    # Encode categoricals
    if 'diagnosis' in df.columns:
        df['dx_numeric'] = df['diagnosis'].map({'CN': 0, 'MCI': 1, 'AD': 2})
    if 'sex' in df.columns:
        df['sex_numeric'] = df['sex'].map({'Male': 0, 'Female': 1})
    if 'amyloid_status' in df.columns:
        df['amyloid_pos'] = (df['amyloid_status'] == '+').astype(float)
    if 'tau_status' in df.columns:
        df['tau_pos'] = (df['tau_status'] == '+').astype(float)
    
    # Select numeric columns for causal discovery
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    df_numeric = df[numeric_cols].dropna(axis=1, thresh=int(len(df)*0.3))
    
    print(f"  After filtering: {df_numeric.shape[0]} rows x {df_numeric.shape[1]} columns")
    df_numeric.to_csv("causal_features.csv", index=False)
    return df_numeric
```

**Claude Code prompt:**
```
Create step21_extract_causal_features.py. First check what node labels, 
relationship types, and property names exist in the current graph:
  CALL db.labels()
  CALL db.relationshipTypes()
  CALL db.propertyKeys()
Adapt the Cypher query to match ACTUAL property names in the graph (they 
might differ from the blueprint names). Extract baseline features into a 
DataFrame and save as CSV. Handle missing values appropriately.
```

#### Day 3-4: Run Causal Discovery Algorithms

Create `step22_causal_discovery.py`

```python
"""
Step 22: Run Causal Discovery Algorithms
Uses causal-learn library (CMU)
"""

import numpy as np
import pandas as pd
from causallearn.search.ConstraintBased.FCI import fci
from causallearn.search.ConstraintBased.PC import pc
from causallearn.search.ScoreBased.GES import ges
from causallearn.utils.GraphUtils import GraphUtils

def run_all_algorithms(df: pd.DataFrame, alpha=0.05):
    """Run PC, FCI, GES on the feature matrix."""
    data = df.values.astype(float)
    labels = list(df.columns)
    results = {}
    
    # 1. PC Algorithm (assumes no latent confounders)
    print("  Running PC algorithm...")
    pc_result = pc(data, alpha=alpha, indep_test='fisherz')
    results['PC'] = pc_result
    pyd = GraphUtils.to_pydot(pc_result.G, labels=labels)
    pyd.write_png('causal_graph_PC.png')
    print(f"  ✓ PC: {pc_result.G.get_num_edges()} edges found")
    
    # 2. FCI Algorithm (handles latent confounders — PRIORITY per Shen et al.)
    print("  Running FCI algorithm...")
    fci_result, fci_edges = fci(data, independence_test_method='fisherz', alpha=alpha)
    results['FCI'] = fci_result
    pyd = GraphUtils.to_pydot(fci_result, labels=labels)
    pyd.write_png('causal_graph_FCI.png')
    print(f"  ✓ FCI: {fci_result.get_num_edges()} edges found")
    
    # 3. GES Algorithm (score-based)
    print("  Running GES algorithm...")
    ges_result = ges(data, score_func='local_score_BIC')
    results['GES'] = ges_result
    pyd = GraphUtils.to_pydot(ges_result['G'], labels=labels)
    pyd.write_png('causal_graph_GES.png')
    print(f"  ✓ GES: {ges_result['G'].get_num_edges()} edges found")
    
    return results

def compare_algorithms(results: dict, labels: list):
    """Compare edges found by different algorithms."""
    consensus = {}
    for algo_name, result in results.items():
        graph = result.G if hasattr(result, 'G') else result.get('G', result)
        adj = graph.graph  # adjacency matrix
        for i in range(len(labels)):
            for j in range(len(labels)):
                if adj[i][j] != 0:
                    edge = (labels[i], labels[j])
                    if edge not in consensus:
                        consensus[edge] = []
                    consensus[edge].append(algo_name)
    
    # Edges found by 2+ algorithms are "consensus" edges
    strong = {k: v for k, v in consensus.items() if len(v) >= 2}
    print(f"\n  Consensus edges (found by 2+ algorithms): {len(strong)}")
    for edge, algos in sorted(strong.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"    {edge[0]} → {edge[1]} [{', '.join(algos)}]")
    
    return consensus, strong
```

**Claude Code prompt:**
```
Create step22_causal_discovery.py. Load causal_features.csv, run PC, FCI, 
and GES from causal-learn. Compare results across algorithms. Save 
consensus edges (found by 2+ algorithms) as JSON. Generate PNG visualizations 
of each causal graph. Handle the case where data has too many missing values 
by using listwise deletion or mean imputation. Set alpha=0.05 for PC and FCI.
```

#### Day 5: Embed Causal Edges in KG

Create `step23_embed_causal_edges.py`

**Claude Code prompt:**
```
Create step23_embed_causal_edges.py that reads the consensus edges JSON from 
step22 and creates CAUSES relationships in Neo4j. Each CAUSES edge should 
have properties: algorithm (which algorithms found it), p_value, confidence 
(high if 3/3, medium if 2/3), and ro_uri='ro:RO_0002411'. Connect the 
edges between OntologyConcept nodes rather than raw data nodes so the 
causal structure is at the semantic level.
```

---

### WEEK 4 (Mar 17–23): AlzKB Bridge + Validation

**Goal:** Import AlzKB subset, validate causal edges against literature.

#### Day 1-2: AlzKB Integration

Create `step24_alzkb_bridge.py`

**Claude Code prompt:**
```
Create step24_alzkb_bridge.py. AlzKB data is available at 
https://github.com/EpistasisLab/AlzKB (check if the Neo4j dump or CSV 
exports are downloadable). Import only the ~200 concepts that overlap with 
our ADNI data: genes (APOE, APP, PSEN1, PSEN2, MAPT), biomarker analytes 
(Abeta42, tau, ptau, NfL), brain regions, and drugs from BACKMEDS. Create 
SAME_AS relationships between our OntologyConcept nodes and AlzKB entities.
```

#### Day 3-4: Validate Causal Edges Against Literature

Create `step25_validate_causal.py`

**Claude Code prompt:**
```
Create step25_validate_causal.py that:
1. Loads the consensus causal edges from step22/23
2. Checks each edge against AlzKB relationships
3. Checks against the canonical A→T→N cascade from Jack et al. 2013
4. Marks each CAUSES edge with validated_by_literature=true/false
5. Computes precision/recall vs. known AD biology:
   - Known: amyloid → tau (A→T)
   - Known: tau → neurodegeneration (T→N)  
   - Known: APOE → amyloid
   - Known: age → all biomarkers
6. Generate a validation report
```

#### Day 5: DoWhy Causal Inference

**Claude Code prompt:**
```
Create step26_dowhy_inference.py using DoWhy. Take the causal DAG from step22 
(FCI output) as the structural model. Estimate the causal effect of 
amyloid_positivity on MMSE decline using the backdoor criterion. Run 
refutation tests (placebo, data subset, random common cause). Report 
estimated effect size and p-value.
```

---

### WEEK 5 (Mar 24–30): Documentation + Defense Preparation

**Goal:** Generate thesis methodology figures, verify graph stats, polish documentation.

#### Day 1-2: Graph Statistics & EDA

**Claude Code prompt:**
```
Create step27_final_stats.py that generates a comprehensive report:
1. Total nodes by label, total relationships by type
2. OntologyConcept coverage (% of data nodes with MAPS_TO)
3. ICD-10 hierarchy depth
4. Causal edges summary (how many, which algorithms, validation rate)
5. Graph density, average degree, connected components
6. Export as both JSON and a formatted markdown report
```

#### Day 3-4: Thesis Figures

**Claude Code prompt:**
```
Create step28_thesis_figures.py that generates publication-quality figures:
1. KG schema diagram (use graphviz, save as SVG + PNG)
2. Causal graph overlay on the KG schema
3. Before/after comparison: LPG query vs KG semantic query results
4. ATN biomarker cascade with causal edges annotated
5. ICD-10 hierarchy tree for AD-related codes
Save all as SVG (for thesis) and PNG (for presentations).
```

#### Day 5: Final Pipeline Integration

```bash
# Register all new steps in pipeline.py
# Run full pipeline end-to-end to verify
python pipeline.py --steps 17,18,19,20,21,22,23,24,25,26,27,28

# Verify the graph
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'PASSWORD'))
with driver.session() as s:
    # Node counts
    for label in ['Patient', 'Visit', 'Diagnosis', 'OntologyConcept', 
                   'CognitiveAssessment', 'CSFBiomarker']:
        r = s.run(f'MATCH (n:{label}) RETURN count(n) as c')
        print(f'{label}: {r.single()[\"c\"]}')
    
    # Relationship counts
    for rel in ['HAS_VISIT', 'MAPS_TO', 'IS_A', 'CLASSIFIED_AS', 'CAUSES']:
        r = s.run(f'MATCH ()-[r:{rel}]->() RETURN count(r) as c')
        print(f'{rel}: {r.single()[\"c\"]}')
driver.close()
"
```

---

## File Structure After Completion

```
ADNIKnowledgeGraph/
├── steps/
│   ├── step1_database_setup.py      # Existing
│   ├── ...                          # Steps 2-16 (existing)
│   ├── step17_apply_constraints.py  # Week 1: Constraints
│   ├── step18_add_ontology_properties.py  # Week 1: Ontology codes
│   ├── step19_icd10_integration.py  # Week 2: WHO ICD API + rdflib
│   ├── step20_ontology_layer.py     # Week 2: OntologyConcept + MAPS_TO
│   ├── step21_extract_causal_features.py  # Week 3: Feature extraction
│   ├── step22_causal_discovery.py   # Week 3: PC/FCI/GES
│   ├── step23_embed_causal_edges.py # Week 3: CAUSES edges
│   ├── step24_alzkb_bridge.py       # Week 4: AlzKB integration
│   ├── step25_validate_causal.py    # Week 4: Validation
│   ├── step26_dowhy_inference.py    # Week 4: Causal inference
│   ├── step27_final_stats.py        # Week 5: Stats & report
│   └── step28_thesis_figures.py     # Week 5: Figures
├── ontology/
│   ├── icd10_cache.json             # Cached WHO ICD API responses
│   ├── icd10_fbk.owl               # Fallback: FBK ICD-10 OWL file
│   └── concept_mappings.json        # SNOMED/LOINC/UBERON mapping tables
├── causal/
│   ├── causal_features.csv          # Extracted baseline features
│   ├── consensus_edges.json         # Edges found by 2+ algorithms
│   ├── causal_graph_PC.png
│   ├── causal_graph_FCI.png
│   └── causal_graph_GES.png
├── config.yaml                      # Add who_icd, bioportal sections
├── pipeline.py                      # Updated with steps 17-28
└── thesis_output/
    ├── kg_schema.svg
    ├── causal_overlay.svg
    ├── validation_report.md
    └── final_stats.json
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

---

## Risk Mitigation

| Risk | Probability | Mitigation |
|------|-------------|------------|
| WHO ICD API down | Low | FBK ICD-10 OWL fallback + rdflib local SPARQL |
| Neo4j composite constraints not supported in your version | Medium | Check Neo4j version (`CALL dbms.components()`). Need 5.x for composite constraints. If 4.x, use node key constraints instead. |
| Causal-learn produces empty graph | Medium | Lower alpha to 0.1, use KCI instead of Fisher's Z for mixed data |
| Not enough patients with complete baseline data | Low | ADNI has ~2,400 patients. Even 30% completeness gives 700+ rows. |
| AlzKB dump not downloadable | Medium | Use AlzKB's published paper tables manually; create 50 key concepts by hand |

---

## Success Criteria

By March 30, the thesis KG should have:

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
