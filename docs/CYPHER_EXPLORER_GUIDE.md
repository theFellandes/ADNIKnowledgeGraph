# ADNI Knowledge Graph -- Cypher Explorer Guide

**Companion document for `cypher_explorer.cypher`**
**Thesis: Knowledge Graph Construction and Analysis for Alzheimer's Disease Research Using ADNI Data**
**Author: Oguzhan Gungor -- Galatasaray University, 2026**

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [ADNI Glossary](#2-adni-glossary)
3. [Knowledge Graph Schema](#3-knowledge-graph-schema)
4. [Section-by-Section Guide](#4-section-by-section-guide)
5. [Neo4j Browser Tips](#5-neo4j-browser-tips)
6. [Graph Statistics](#6-graph-statistics)

---

## 1. Introduction

### Purpose

The `cypher_explorer.cypher` file provides a **guided Cypher query tour** of the ADNI Knowledge Graph (ADNI-KG). It contains 70+ ready-to-run queries organized into 12 thematic sections, each targeting a different clinical or structural aspect of the graph. The queries are designed to demonstrate the full breadth of the knowledge graph during thesis defense presentations and to serve as a reference for researchers who wish to explore the graph independently.

### How to Use

1. Start Neo4j 5.24.2 Community Edition.
2. Open **Neo4j Browser** at [http://localhost:7474](http://localhost:7474).
3. Connect using the Bolt protocol at `bolt://localhost:7687`.
4. Open `cypher_explorer.cypher` in any text editor.
5. **Copy-paste one query at a time** into the Neo4j Browser query box and press `Ctrl+Enter` (or click the play button) to execute.
6. Queries that return `p, r, n` patterns will render as interactive graph visualizations. Queries that return scalar values or tables will appear in the Table tab.

> **Important:** Do not paste the entire file at once. Neo4j Browser executes only one statement per submission. Copy individual queries (from one semicolon to the next).

### Prerequisites

| Requirement | Version / Detail |
|---|---|
| Neo4j | 5.24.2 Community Edition |
| Protocol | `bolt://localhost:7687` |
| Browser | [http://localhost:7474](http://localhost:7474) |
| Database | ADNI-KG (loaded via the project pipeline) |
| APOC plugin | Not required (all queries use standard Cypher) |

---

## 2. ADNI Glossary

The Alzheimer's Disease Neuroimaging Initiative (ADNI) uses domain-specific terminology throughout its datasets. The following table defines the key terms encountered in the Cypher queries and in the knowledge graph node properties.

### Participant Identifiers

| Term | Full Name | Description |
|------|-----------|-------------|
| PTID | Patient ID | Format: `###_S_####` (e.g., `011_S_0002`). The first three digits identify the recruitment site, `S` is a separator, and the last four digits identify the subject within that site. |
| RID | Roster ID | Numeric participant identifier used internally by ADNI. Integer value, unique across all cohorts. |
| viscode | Visit Code | Encodes the time point of a study visit. `bl` = baseline, `m06` = 6 months, `m12` = 12 months, `m24` = 24 months, `m36` = 36 months, etc. Some cohorts also use `y1`, `y2` notation. |

### Diagnostic Categories

| Term | Full Name | Description |
|------|-----------|-------------|
| CN | Cognitively Normal | Healthy control participant with no objective cognitive impairment. Serves as the reference group. |
| SMC | Subjective Memory Concern | Self-reported memory issues without measurable objective impairment on standardized tests. |
| EMCI | Early MCI | Early mild cognitive impairment. Subtle but measurable cognitive decline, particularly in memory. Defined by specific Wechsler Memory Scale thresholds. |
| LMCI | Late MCI | Late mild cognitive impairment. More pronounced cognitive decline than EMCI but not yet meeting criteria for dementia. |
| MCI | Mild Cognitive Impairment | General prodromal stage between CN and AD. In earlier ADNI cohorts (ADNI-1), MCI was not subdivided into Early/Late. |
| AD | Alzheimer's Disease | Clinical dementia diagnosis meeting NINCDS-ADRDA criteria. MMSE typically 20--26 at enrollment. |

### Cognitive Assessment Instruments

| Term | Full Name | Description |
|------|-----------|-------------|
| MMSE | Mini-Mental State Exam | Score range 0--30, higher is better. Screens orientation, memory, attention, language, and visuospatial skills. A score below 24 generally indicates cognitive impairment. |
| CDR-SB | Clinical Dementia Rating -- Sum of Boxes | Score range 0--18, lower is better. Evaluates six domains: memory, orientation, judgment, community affairs, home/hobbies, and personal care. A score of 0 indicates no dementia. |
| ADAS-Cog | Alzheimer's Disease Assessment Scale -- Cognitive | Score range 0--70, lower is better. The primary cognitive endpoint in most AD clinical trials. Assesses memory, language, praxis, and orientation. |
| MoCA | Montreal Cognitive Assessment | Score range 0--30, higher is better. More sensitive than MMSE for detecting MCI. |
| RAVLT | Rey Auditory Verbal Learning Test | Measures verbal memory through word-list learning and recall across five trials plus delayed recall. |
| FAQ | Functional Activities Questionnaire | Score range 0--30, higher indicates greater impairment. Measures instrumental activities of daily living. |

### Biomarker Framework

| Term | Full Name | Description |
|------|-----------|-------------|
| ATN | Amyloid / Tau / Neurodegeneration | The NIA-AA 2018 research framework for classifying Alzheimer's biomarkers into three binary categories (positive/negative). |
| A+ | Amyloid positive | Indicates amyloid-beta pathology. Defined by CSF ABETA42 < 192 pg/mL or a positive amyloid PET scan (e.g., florbetapir SUVR > 1.11). |
| T+ | Tau positive | Indicates tau tangle pathology. Defined by elevated CSF phosphorylated tau (pTau181) above age-adjusted thresholds. |
| N+ | Neurodegeneration positive | Indicates neuronal injury or neurodegeneration. Defined by elevated CSF total tau, hippocampal atrophy on MRI, or temporoparietal hypometabolism on FDG-PET. |
| SUVR | Standardized Uptake Value Ratio | PET imaging metric. The ratio of tracer uptake in a target region to a reference region (typically the cerebellum). Higher SUVR indicates more tracer binding (more pathology for amyloid/tau tracers). |
| CSF | Cerebrospinal Fluid | Collected via lumbar puncture. The three core AD CSF biomarkers are ABETA42 (amyloid), pTau181 (tau tangles), and tTau (neurodegeneration). |

### Genetics

| Term | Full Name | Description |
|------|-----------|-------------|
| APOE | Apolipoprotein E | The strongest genetic risk factor for late-onset AD. Three alleles exist: E2 (protective), E3 (neutral), E4 (risk). Carrying one E4 allele increases AD risk 3--4x; two copies increase risk 8--12x. Encoded as allele pairs (e.g., 3/4, 4/4). |

---

## 3. Knowledge Graph Schema

### Schema Diagram

```
Patient ──HAS_VISIT──> Visit
  |                      └──PRECEDES──> Visit (temporal ordering)
  |
  ├──HAS_DIAGNOSIS──> Diagnosis
  |                     ├──MAPS_TO──> OntologyConcept (SNOMED-CT)
  |                     ├──CLASSIFIED_AS──> OntologyConcept (ICD-10)
  |                     ├──PROGRESSED_TO──> Diagnosis
  |                     └──IS_CLINICAL_FINDING──> ClinicalFinding
  |
  ├──HAS_COGNITIVE_ASSESSMENT──> CognitiveAssessment
  |                                └──MAPS_TO──> OntologyConcept (LOINC)
  |
  ├──HAS_BIOMARKER──> Biomarker
  |                     ├──MAPS_TO──> OntologyConcept (LOINC)
  |                     ├──BELONGS_TO_CATEGORY──> BiomarkerCategory
  |                     └──INDICATES_PATHWAY──> BiologicalPathway
  |
  ├──HAS_IMAGE──> ImageNode
  |                 ├──SmoothRendering
  |                 ├──PyramidFormat
  |                 └──WebViewerReady
  |
  ├──HAS_FAMILY_MEMBER──> FamilyMember
  |                         └──HAS_SIBLING──> FamilyMember
  |
  ├──HAS_ATN_PROFILE──> ATNProfile
  |
  ├──BELONGS_TO──> ResearchCohort
  |
  ├──EXPERIENCED_EVENT──> Event
  |   ├──ClinicalEvent
  |   ├──BiomarkerEvent
  |   ├──CognitiveEvent
  |   └──ImagingEvent
  |       └──FOLLOWED_BY──> Event (temporal chain)
  |           └──PART_OF_CHAIN──> EventChain
  |
  ├──HAS_TIMELINE──> PatientTimeline
  |
  └──EXPERIENCED_PROGRESSION──> ProgressionEvent
                                  └──PROGRESSED_TO──> ProgressionEvent

OntologyConcept ──IS_A──> OntologyConcept (taxonomy hierarchy)

DiseaseStage          (reference nodes: CN, SMC, EMCI, LMCI, AD)
CognitiveTest         (reference nodes: MMSE, CDR, ADAS-Cog, MoCA, RAVLT, FAQ)
ProgressionPattern    (summary nodes: trajectory counts)
PETTracer             (reference nodes: Florbetapir, FDG, AV-1451)
FamilyRisk            (risk stratification nodes)
MultimodalAssessment  (combined assessment nodes)
```

### Node Type Reference

| Node Type | Description | Key Properties |
|-----------|-------------|----------------|
| **Patient** | An ADNI study participant. Central hub node from which all clinical data radiates. | `ptid`, `gender`, `age_at_baseline`, `education_years`, `apoe_genotype` |
| **Visit** | A single study visit at a specific time point. | `viscode`, `visit_date`, `months_from_baseline` |
| **Diagnosis** | A clinical diagnosis assigned at a given visit. | `diagnosis_code` / `dx_label`, `visit_code`, `snomed_code`, `icd10_code` |
| **CognitiveAssessment** | A cognitive test result recorded at a visit. | `test_name`, `total_score`, `visit_code`, `visit_date`, `loinc_code` |
| **Biomarker** | A biological measurement (CSF analyte, PET SUVR, etc.). | `biomarker_name`, `value`, `visit_code` |
| **ImageNode** | Metadata for a brain scan (MRI or PET). | `image_hash`, `modality`, `description`, `format` |
| **FamilyMember** | A family member of a patient, recording hereditary risk. | `has_dementia`, `dementia_status` |
| **ATNProfile** | A patient's ATN biomarker classification. | `profile` (e.g., `A+T+N+`) |
| **OntologyConcept** | A term from an international medical ontology. | `code`, `label`, `source_ontology`, `uri` |
| **DiseaseStage** | Reference node for a diagnostic category. | `name`, `description`, `snomed_code` |
| **CognitiveTest** | Reference node for a cognitive assessment instrument. | `name`, `loinc_code`, `description` |
| **ResearchCohort** | An ADNI study phase (ADNI-1, ADNI-GO, ADNI-2, ADNI-3, ADNI-4). | `name` |
| **ProgressionEvent** | A disease stage transition event for a patient. | `stage` |
| **ProgressionPattern** | Aggregate summary of a trajectory (e.g., CN->MCI->AD). | `pattern`, `patient_count` |
| **BiomarkerCategory** | Classification group for biomarkers (CSF, PET, etc.). | `name` |
| **BiologicalPathway** | A biological process associated with a biomarker. | `name` |
| **PETTracer** | Reference node for a PET radiotracer. | `name`, `target` |
| **FamilyRisk** | Hereditary risk stratification. | `risk_level` |
| **ClinicalFinding** | A clinical finding supporting a diagnosis. | `finding_type` |
| **MultimodalAssessment** | Combined multi-domain assessment. | `assessment_type` |
| **SmoothRendering** | Image processing artifact: smooth-rendered version. | -- |
| **PyramidFormat** | Image processing artifact: pyramid/tiled format. | -- |
| **WebViewerReady** | Image processing artifact: web-optimized version. | -- |
| **EventChain** | A temporal chain linking sequential clinical events. | -- |
| **PatientTimeline** | Aggregate timeline representation for a patient. | -- |

### Relationship Type Reference

| Relationship | Source | Target | Description |
|---|---|---|---|
| `HAS_VISIT` | Patient | Visit | Patient attended a study visit |
| `PRECEDES` | Visit | Visit | Temporal ordering between visits |
| `HAS_DIAGNOSIS` | Patient | Diagnosis | Diagnosis assigned to patient |
| `PROGRESSED_TO` | Diagnosis / ProgressionEvent | Diagnosis / ProgressionEvent | Disease stage transition |
| `HAS_COGNITIVE_ASSESSMENT` | Patient | CognitiveAssessment | Cognitive test administered |
| `HAS_BIOMARKER` | Patient | Biomarker | Biomarker measurement recorded |
| `HAS_IMAGE` | Patient | ImageNode | Brain scan associated with patient |
| `HAS_FAMILY_MEMBER` | Patient | FamilyMember | Family relationship |
| `HAS_SIBLING` | FamilyMember | FamilyMember | Sibling relationship between family members |
| `HAS_ATN_PROFILE` | Patient | ATNProfile | ATN biomarker classification |
| `BELONGS_TO` | Patient | ResearchCohort | Patient enrolled in ADNI phase |
| `BELONGS_TO_CATEGORY` | Biomarker | BiomarkerCategory | Biomarker classification |
| `MAPS_TO` | Diagnosis / CognitiveAssessment / Biomarker | OntologyConcept | Mapping to ontology standard |
| `CLASSIFIED_AS` | Diagnosis | OntologyConcept | ICD-10 classification |
| `IS_A` | OntologyConcept | OntologyConcept | Ontology taxonomy hierarchy |
| `IS_CLINICAL_FINDING` | Diagnosis | ClinicalFinding | Supporting clinical evidence |
| `INDICATES_PATHWAY` | Biomarker | BiologicalPathway | Biological pathway association |
| `EXPERIENCED_EVENT` | Patient | Event | Clinical/biomarker/imaging event |
| `FOLLOWED_BY` | Event | Event | Temporal ordering of events |
| `PART_OF_CHAIN` | Event | EventChain | Event belongs to a chain |
| `HAS_TIMELINE` | Patient | PatientTimeline | Timeline aggregate |
| `EXPERIENCED_PROGRESSION` | Patient | ProgressionEvent | Disease progression event |

---

## 4. Section-by-Section Guide

### Section 1: Overview and Schema Discovery

**Purpose:** Answer the fundamental question -- *What is in this graph and how big is it?*

**Key queries to try first:**
- **Query 1.1** -- Total node and relationship counts. The single most important "vital sign" of the graph. Returns two numbers that confirm the graph is loaded and healthy.
- **Query 1.4** -- `CALL db.schema.visualization()`. Renders the full schema as an interactive graph in Neo4j Browser. This is the best single query for thesis defense demonstrations.

**How to interpret results:**
- Total nodes should be approximately 421K; total relationships approximately 1.4M. If numbers are significantly lower, the pipeline may not have completed all steps.
- Query 1.2 breaks down nodes by label. `Patient` should show ~2,638; `Visit` ~30,267; `Diagnosis` ~25,946. These are the core clinical entities.
- Query 1.5 shows which node types connect to which, filtering out rare patterns (< 50 occurrences).

**Clinical significance:**
This section validates that the ETL pipeline successfully transformed tabular ADNI CSV data into a connected knowledge graph. The schema visualization demonstrates the graph's structure -- a patient-centric star schema enriched with semantic ontology mappings.

---

### Section 2: Patient Demographics

**Purpose:** Answer -- *Who are the 2,638 participants in this study?*

**Key queries to try first:**
- **Query 2.1** -- Gender distribution. Quick validation that the cohort is balanced.
- **Query 2.4** -- APOE genotype distribution. Reveals the proportion of E4 carriers, the strongest genetic risk factor for AD.

**How to interpret results:**
- Gender should show a roughly balanced cohort (ADNI aims for representative enrollment).
- Age distribution (Query 2.3) typically peaks in the 70--80 range, reflecting the target population for AD research.
- APOE genotype: approximately 25% of the general population carries at least one E4 allele. In ADNI, this proportion is enriched because MCI and AD groups have higher E4 prevalence.
- Education years (Query 2.2) tend to skew high (median ~16 years) because ADNI recruits from academic medical centers.

**Clinical significance:**
Demographics establish the external validity of the cohort. High education levels may introduce cognitive reserve effects (participants with more education can tolerate more pathology before showing symptoms). APOE E4 status is the single most important genetic covariate in any AD analysis.

---

### Section 3: Diagnosis and Disease Progression

**Purpose:** Answer -- *How do patients move along the CN -> MCI -> AD trajectory?*

**Key queries to try first:**
- **Query 3.1** -- Diagnosis distribution. Shows the overall balance of diagnostic groups.
- **Query 3.4** -- Converters from CN to MCI/AD. These patients are the most scientifically valuable because they allow studying the transition from health to disease.

**How to interpret results:**
- Diagnosis counts should show CN as the largest group (healthy controls), followed by MCI categories, then AD.
- Query 3.3 (progression events) reveals the most common transitions. CN -> EMCI and EMCI -> LMCI should dominate. Reversions (e.g., MCI -> CN) do occur and are clinically meaningful.
- Query 3.5 (progression patterns) shows aggregate trajectories. The most common pattern is "stable CN" (participants who never converted).

**Clinical significance:**
Disease progression is the central research question in ADNI. Identifying which patients convert, when they convert, and what biomarker/cognitive changes precede conversion is the foundation of early detection research. The knowledge graph uniquely enables traversal of these progression chains as graph paths rather than requiring complex SQL joins across time-stamped tables.

---

### Section 4: Cognitive Assessments

**Purpose:** Answer -- *How do cognitive scores change across diagnostic groups and over time?*

**Key queries to try first:**
- **Query 4.2** -- Average cognitive scores by diagnosis group. The definitive query showing that MMSE, CDR-SB, and ADAS-Cog separate diagnostic groups.
- **Query 4.4** -- A single patient's full cognitive timeline. Replace the PTID with a real patient ID from Query 2.5 to see longitudinal decline.

**How to interpret results:**
- **MMSE by diagnosis:** CN ~29, EMCI ~28, LMCI ~27, AD ~21--23. The separation between LMCI and AD is the most clinically significant.
- **CDR-SB by diagnosis:** CN ~0, EMCI ~1.0--1.5, LMCI ~1.5--2.5, AD ~4.5--6.0. Higher values indicate more functional impairment.
- **ADAS-Cog by diagnosis:** CN ~5--9, EMCI ~9--12, LMCI ~13--17, AD ~25--35. This is the primary endpoint in AD clinical trials.
- Standard deviations indicate within-group variability. Large SDs suggest heterogeneous populations.

**Clinical significance:**
These cognitive measures are the primary clinical endpoints in AD research and drug trials. The knowledge graph stores them as first-class nodes (not buried in CSV columns), enabling queries like "find all patients whose MMSE dropped by more than 4 points between baseline and month 24." CognitiveTest reference nodes link each instrument to its LOINC code, connecting clinical measurement to international standards.

---

### Section 5: Biomarkers (CSF, PET, ATN)

**Purpose:** Answer -- *What biological evidence of AD pathology exists in these patients?*

**Key queries to try first:**
- **Query 5.3** -- ATN framework profiles. Shows the distribution of patients across the NIA-AA biological classification of AD.
- **Query 5.6** -- Patients with abnormal amyloid (A+). Lists patients with CSF ABETA42 < 192 pg/mL, the established threshold for amyloid positivity.

**How to interpret results:**
- **ATN profiles:** `A-T-N-` = biologically normal; `A+T-N-` = preclinical AD (amyloid pathology only); `A+T+N-` = pathologic change; `A+T+N+` = full AD pathology. The distribution of these profiles across diagnostic groups is a key research finding.
- **CSF ABETA42:** Values below 192 pg/mL indicate amyloid plaque deposition in the brain. Lower values mean more pathology. CN patients with low ABETA42 are at high risk of future cognitive decline.
- **CSF pTau/tTau:** Elevated values indicate tau pathology and neurodegeneration, respectively.
- **PET SUVR:** For amyloid tracers (Florbetapir), SUVR > 1.11 is typically considered positive.

**Clinical significance:**
Biomarkers provide objective, biological evidence of AD pathology that precedes clinical symptoms by 15--20 years. The ATN framework represents the current scientific consensus for defining AD biologically rather than clinically. The knowledge graph links biomarker measurements to patients, diagnoses, ontology concepts, and biological pathways, enabling multi-modal queries that are extremely difficult in relational databases.

---

### Section 6: Medical Imaging

**Purpose:** Answer -- *What brain scans are available and how are they structured?*

**Key queries to try first:**
- **Query 6.1** -- Total images and rendering types. Overview of the imaging data volume.
- **Query 6.3** -- Image modality breakdown (MRI vs PET). Shows the distribution of scan types.

**How to interpret results:**
- Image counts reflect the processed output of the pipeline's image handling steps (steps 5 and 5b). Multiple rendering formats (SmoothRendering, PyramidFormat, WebViewerReady) are generated per source image for different visualization use cases.
- The `modality` property distinguishes MRI (structural brain imaging) from PET (functional/molecular imaging targeting amyloid, tau, or glucose metabolism).
- Query 6.2 shows the distribution of images per patient. Patients with longer follow-up will have more scans.

**Clinical significance:**
Neuroimaging is essential for measuring brain atrophy (MRI), amyloid deposition (amyloid PET), tau accumulation (tau PET), and metabolic decline (FDG-PET). Storing image metadata in the graph enables queries like "find all patients with both an MRI and an amyloid PET scan at baseline who later converted to AD." The image nodes do not store pixel data but rather metadata and file references.

---

### Section 7: Family History and Genetics

**Purpose:** Answer -- *What hereditary risk factors are present in the cohort?*

**Key queries to try first:**
- **Query 7.4** -- Patients with first-degree relatives affected by dementia. Having an affected parent or sibling roughly doubles AD risk.
- **Query 7.3** -- Family risk assessments. Shows the distribution of hereditary risk levels.

**How to interpret results:**
- Query 7.1 returns the total number of FamilyMember nodes. Each node represents a specific family member (mother, father, sibling) of a patient.
- Query 7.4 filters for family members with documented dementia. The `affected_relatives` count indicates genetic load.
- Query 7.5 (sibling relationships) may return 0. This is a known data modeling limitation noted in the cypher file.

**Clinical significance:**
Family history is one of the strongest non-genetic risk factors for AD. Combined with APOE genotype (from Section 2), family history data enables genetic risk stratification. The graph structure naturally represents family relationships as edges, making hereditary pattern analysis intuitive compared to tabular representations.

---

### Section 8: Ontology and Semantic Layer

**Purpose:** Answer -- *How does the graph connect ADNI data to international medical standards?*

**Key queries to try first:**
- **Query 8.1** -- All OntologyConcept nodes. Displays the 52 concepts from SNOMED-CT, LOINC, UBERON, HPO, and ICD-10 that form the semantic backbone.
- **Query 8.9** -- Full ICD-10 semantic chain (Patient -> Diagnosis -> CLASSIFIED_AS -> OntologyConcept). Demonstrates the end-to-end traversal from clinical data to international classification.

**How to interpret results:**
- Query 8.1 returns 52 ontology concepts organized by source ontology. Each has a URI linking to the authoritative ontology source.
- Query 8.2 shows MAPS_TO relationship counts by node type and ontology. Diagnoses map to SNOMED-CT; cognitive assessments map to LOINC; brain regions map to UBERON.
- Query 8.3 displays the IS_A hierarchy. For example, ICD-10 code G30.9 (Alzheimer's disease, unspecified) IS_A G30 (Alzheimer's disease).
- Query 8.4 and 8.8 measure ontology coverage and gaps. High SNOMED coverage means the graph is well-mapped to clinical terminology standards.

**Clinical significance:**
The ontology layer transforms the ADNI-KG from a labeled property graph into a true knowledge graph. Mapping clinical observations to SNOMED-CT, LOINC, and ICD-10 enables:
- **Interoperability** with other clinical datasets using the same ontologies.
- **Semantic reasoning** such as "find all diagnoses classified under ICD-10 chapter G (Diseases of the Nervous System)."
- **Standardized reporting** using internationally recognized terminology codes.
- This semantic enrichment is the primary contribution of the thesis -- elevating raw study data to a standards-compliant knowledge representation.

---

### Section 9: Temporal Patterns (Visits)

**Purpose:** Answer -- *How is the longitudinal study structured over time?*

**Key queries to try first:**
- **Query 9.1** -- Visit count by visit code. Shows how many participants attended each time point.
- **Query 9.5** -- Patients with the longest follow-up. Identifies participants with 10+ years of longitudinal data.

**How to interpret results:**
- Visit counts decrease over time (attrition). Baseline (`bl`) has the most visits; later time points (e.g., `m120` = 10 years) have fewer due to participant dropout, death, or study completion.
- Query 9.2 shows the distribution of visits per patient. Average visits per patient indicates study engagement depth.
- Query 9.4 (PRECEDES chains) reveals the temporal backbone of the graph. Each visit links to the next via PRECEDES edges, enabling temporal traversal without relying on date sorting.

**Clinical significance:**
ADNI is fundamentally a longitudinal study. The temporal structure encoded in PRECEDES relationships enables graph-native longitudinal queries: "Follow this patient's visit chain and show how their MMSE score changes at each step." This is more natural than the relational approach of self-joining a visits table on patient ID and ordering by date.

---

### Section 10: Graph Topology and Connectivity

**Purpose:** Answer -- *How densely connected is the knowledge graph? Are there structural issues?*

**Key queries to try first:**
- **Query 10.5** -- Subgraph around a single patient. Replace `PLACEHOLDER` with a real PTID. This produces the most visually compelling graph visualization in Neo4j Browser, showing a patient surrounded by their diagnoses, visits, biomarkers, images, and assessments.
- **Query 10.2** -- Average degree by node type. Reveals which node types are the most connected.

**How to interpret results:**
- **Hub nodes** (Query 10.1): OntologyConcept nodes that many diagnoses map to will have the highest degree. Patient nodes with long follow-up and extensive testing will also be hubs.
- **Average degree** (Query 10.2): Patient nodes should have the highest average degree because they connect to visits, diagnoses, assessments, biomarkers, images, and family members.
- **Isolated nodes** (Query 10.3): Nodes with zero relationships may indicate data quality issues or reference nodes that are not yet linked.
- **Connectivity percentage** (Query 10.7): Should be above 95%. A small number of isolated reference nodes is expected.

**Clinical significance:**
Graph topology metrics quantify the richness of the knowledge graph. High connectivity means that multi-modal queries (combining clinical, imaging, and biomarker data) will return meaningful results. Identifying isolated nodes helps prioritize data quality improvements. The shortest path query (10.4) can reveal unexpected connections between patients through shared diagnoses, biomarker patterns, or ontology concepts.

---

### Section 11: Cross-Domain Queries (Putting It All Together)

**Purpose:** Answer -- *What insights emerge when we combine clinical, imaging, biomarker, and genetic data?*

**Key queries to try first:**
- **Query 11.1** -- Full patient profile (demographics + diagnosis + MMSE + biomarkers). The quintessential "why a knowledge graph?" query -- it traverses four different data domains in a single query.
- **Query 11.2** -- AD patients with low ABETA42 AND low MMSE. Identifies patients with confirmed biological and clinical AD, demonstrating concordance between biomarker and cognitive evidence.

**How to interpret results:**
- Query 11.1 returns a table combining data from Patient, Diagnosis, CognitiveAssessment, and Biomarker nodes. In a relational database, this would require joining 4+ tables with complex WHERE clauses. In the graph, it is a natural traversal from the Patient hub.
- Query 11.2 applies dual thresholds: ABETA42 < 192 (amyloid positive) AND MMSE < 24 (cognitively impaired). Patients meeting both criteria have the strongest evidence for AD.
- Query 11.3 checks multi-modal data completeness. Patients with imaging AND biomarkers AND family history are the most valuable for comprehensive analyses.
- Query 11.4 measures the "depth" of the knowledge graph -- how many relationship hops separate a patient from an ontology concept. Shorter paths indicate more direct mappings.

**Clinical significance:**
Cross-domain queries are the primary justification for building a knowledge graph rather than using tabular data. These queries demonstrate that the graph enables:
- Multi-modal patient profiling in a single query.
- Biomarker-clinical concordance analysis.
- Data completeness assessment across modalities.
- Semantic traversal from raw clinical data to international ontology standards.
These capabilities directly support the thesis argument that knowledge graphs are superior to relational databases for integrative AD research.

---

### Section 12: Data Quality and Completeness

**Purpose:** Answer -- *Is the data complete and correct? Are there gaps or anomalies?*

**Key queries to try first:**
- **Query 12.1** -- Patient property completeness. Shows what percentage of patients have gender, age, APOE, and education data.
- **Query 12.6** -- Verify 381\_S\_ patient exclusion. Per ADNI advisory, 78 participants from site 381 must be excluded due to data quality concerns.

**How to interpret results:**
- Query 12.1 returns coverage percentages. Gender should be near 100%. APOE may be lower because not all participants consented to genetic testing. Education is typically well-populated.
- Query 12.2 checks diagnosis completeness for SNOMED and ICD-10 codes. High coverage validates the ontology mapping pipeline.
- Query 12.3 and 12.4 check for patients without visits or diagnoses. A small number may be expected (screen failures), but large numbers indicate pipeline issues.
- Query 12.5 (orphan nodes) identifies nodes with no relationships. These should be minimal in a well-constructed graph.
- Query 12.6 should return 0 for `excluded_patients_found`, confirming that the 381\_S\_ exclusion was properly applied.
- Query 12.7 checks for patients with multiple baseline diagnoses, which would indicate a data integrity issue.

**Clinical significance:**
Data quality directly impacts the validity of any analysis performed on the knowledge graph. The 381\_S\_ exclusion is a real-world example of a data quality issue discovered during the ADNI study. Systematic quality checks embedded in the Cypher explorer ensure reproducibility and help identify issues before they propagate into downstream analyses (causal inference, event-based modeling, etc.).

---

## 5. Neo4j Browser Tips

### Visualization

- **Graph vs. Table view:** After running a query, click the **Graph** tab (node-and-edge icon) to see an interactive visualization. Queries that return node and relationship variables (e.g., `RETURN p, r, n`) render as graph bubbles. Queries returning only scalar values or aggregations appear only in the **Table** tab.
- **RETURN format matters:** `RETURN p, r, n` renders as a graph. `RETURN path` may not render correctly in all cases. For best results, destructure paths into their component nodes and relationships.
- **Use LIMIT generously:** Queries without LIMIT can return thousands of nodes and freeze the browser. Start with `LIMIT 25` and increase gradually. For large pattern matches, `LIMIT 50` is a practical ceiling for visualization.

### Interaction

- **Double-click a node** to expand its connections (shows all neighbors not yet visible).
- **Drag nodes** to rearrange the layout. Pin important nodes by clicking and holding to keep them in place.
- **Hover over nodes and relationships** to see their properties in the info panel at the bottom.
- **Click a node** to see its full property list in the right sidebar.

### Customization

- Use the `:style` command to customize node colors by label. For example, make Patient nodes blue, Diagnosis nodes red, and OntologyConcept nodes green for clearer visualizations.
- Use `:config` to adjust browser settings such as the maximum number of nodes to display.
- **Fullscreen mode:** Click the expand icon on a result panel to get a larger visualization area. This is especially useful during presentations.

### Query Execution

- **Ctrl+Enter** runs the query.
- **Multi-statement mode** is not enabled by default. Run one query at a time.
- Use the query history (up arrow) to recall previous queries.
- Prefix a query with `:param` to set parameters: `:param ptid => '002_S_0295'` and then use `$ptid` in subsequent queries.

### Presentation Mode

- For thesis defense: maximize the browser window, use fullscreen on result panels, and pre-run key queries to have them in history.
- Use the `:style` command to assign distinct colors to each node label for visually clear schema demonstrations.
- The schema visualization query (`CALL db.schema.visualization()`) produces an excellent overview slide.

---

## 6. Graph Statistics

### Overall Counts

| Metric | Value |
|---|---|
| Total nodes | ~421,000 |
| Total relationships | ~1,400,000 |
| Node labels (types) | 41 |
| Relationship types | 25+ |

### Core Clinical Entities

| Entity | Count | Description |
|---|---|---|
| Patient | 2,638 | Study participants across 5 ADNI cohorts |
| Visit | 30,267 | Longitudinal study visits (baseline through 10+ years) |
| Diagnosis | 25,946 | Clinical diagnoses (CN, SMC, EMCI, LMCI, MCI, AD) |
| CognitiveAssessment | -- | MMSE, CDR-SB, ADAS-Cog, MoCA, RAVLT, FAQ scores |
| Biomarker | -- | CSF analytes, PET SUVRs, other biological measurements |
| ImageNode | -- | MRI and PET scan metadata |
| FamilyMember | -- | Family member records for hereditary risk |

### Semantic Layer

| Metric | Value |
|---|---|
| OntologyConcept nodes | 52 |
| SNOMED-CT concepts | 18 |
| LOINC concepts | 10 |
| UBERON concepts | 14 |
| HPO concepts | 5 |
| ICD-10 concepts | 5 |
| MAPS_TO relationships | 100,770 |
| CLASSIFIED_AS relationships | 25,946 |
| IS_A relationships | 27 |
| Total semantic edges | ~126,743 |

### Research Cohorts

| Cohort | Description | Years |
|---|---|---|
| ADNI-1 | Original cohort | 2004--2010 |
| ADNI-GO | Grand Opportunities extension | 2009--2011 |
| ADNI-2 | Second phase with EMCI/LMCI | 2011--2016 |
| ADNI-3 | Third phase with tau PET | 2016--2022 |
| ADNI-4 | Current phase | 2022--present |

### Relationship Counts (Top 10)

| Relationship Type | Approximate Count | Connects |
|---|---|---|
| MAPS_TO | ~100,770 | Clinical nodes -> OntologyConcept |
| HAS_VISIT | ~30,267 | Patient -> Visit |
| HAS_COGNITIVE_ASSESSMENT | -- | Patient -> CognitiveAssessment |
| HAS_DIAGNOSIS | ~25,946 | Patient -> Diagnosis |
| CLASSIFIED_AS | ~25,946 | Diagnosis -> OntologyConcept (ICD-10) |
| HAS_BIOMARKER | -- | Patient -> Biomarker |
| HAS_IMAGE | -- | Patient -> ImageNode |
| PRECEDES | -- | Visit -> Visit |
| FOLLOWED_BY | -- | Event -> Event |
| IS_A | ~27 | OntologyConcept -> OntologyConcept |

> **Note:** Counts marked with `--` depend on the specific pipeline steps executed. Run Query 1.2 and 1.3 from the Cypher explorer to obtain exact live counts from your Neo4j instance.

---

*This document accompanies `docs/cypher_explorer.cypher` in the ADNI Knowledge Graph repository.*
*Generated for thesis defense preparation -- Galatasaray University, 2026.*
