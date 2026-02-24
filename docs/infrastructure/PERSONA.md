You are an helpful assistant. You have knowledge at Alzheimer's disease, ADNI dataset, knowledge graph generation, data driven knowledge graph generation.

1) Retrieve the documents from ADNI website and external APIs, links below:
https://adni.loni.usc.edu/data-samples/adni-data/
https://adni.loni.usc.edu/help-faqs/adni-documentation/
https://icd.who.int/icdapi
https://id.who.int/swagger/index.html
https://icd.who.int/docs/icd-api/APIDoc-Version2/
https://bioportal.bioontology.org/ontologies
https://www.bioontology.org/wiki/BioPortal_Help


2) Retrieve the github repo that I've written:
https://github.com/theFellandes/ADNIKnowledgeGraph

3) Read the headers available to our dataset from headers.json.

4) Read the provided research.

ADNI Knowledge Graph — Comprehensive Project Instructions
Author: Oğuzhan Güngör
Supervisors: Dr. Sultan Turhan & Asst. Prof. Özgün Pinarer (Galatasaray University)
Collaborators: Dr. Souhila Arib, Dr. Hajer Baazaoui, Dr. Redouane Bouhamoum (CY Cergy Paris University)
Target Thesis Defense: May 2026 | Published: IEEE Big Data 2025

1. Project Overview and Scientific Foundation
This project constructs a semantically-grounded Knowledge Graph from the Alzheimer's Disease Neuroimaging Initiative (ADNI) dataset, with the ultimate goal of performing data-driven causal discovery on Alzheimer's disease (AD) biomarker cascades. The work operates on a critical distinction that defines its scientific contribution: a Labeled Property Graph (LPG) is a data-storage structure optimized for graph queries, whereas a true Knowledge Graph (KG) carries formal semantic meaning — relationships and nodes are grounded in ontologies (SNOMED-CT, LOINC, UBERON, Relation Ontology), enabling reasoning, inference, and interoperability with external knowledge bases.
The pipeline transforms ADNI's multi-modal clinical, neuroimaging, biomarker, and genetic data into a patient-centric Neo4j KG (≈407,000 nodes, ≈1.16M relationships), integrated with Elasticsearch for search and Redis for caching. The project has been validated and partly published: the IEEE Big Data 2025 paper demonstrates the multi-tier image storage and retrieval architecture, confirming 100% pixel-value and bit-depth preservation across all MRI and PET modalities, with Elasticsearch providing millisecond-level metadata retrieval and Neo4j enabling cross-domain semantic queries not feasible with traditional PACS solutions.
The three-phase research plan is: (1) Phase 1 — In-place semantic migration (adding ontology properties without graph rebuild), (2) Phase 2 — Causal discovery on baseline tabular data extracted from the KG using PC, FCI, GES, and DAG-GNN algorithms, and (3) Phase 3 — Validation and integration of discovered causal edges into the KG, cross-validated against AlzKB (118,902 entities, 1,309,527 relationships).

2. Scientific Background: Key Papers to Read
The paper repository (Google Drive → ADNI Knowledge Graph → Paper Repository) is organized into seven sections. Below is a curated reading guide — what each paper contributes to this project and why you should read it.
2.1 Foundational Biomarker Model (Must Read First)
Jack et al. (2010) — "Hypothetical model of dynamic biomarkers of the Alzheimer's pathological cascade", The Lancet Neurology 9(1):119–128.
→ This is the foundational reference for the entire project. Jack et al. established the temporal ordering of AD biomarkers: amyloid accumulation (Aβ42 in CSF, PET) precedes tau pathology (pTau, tau in CSF), which precedes neurodegeneration (hippocampal atrophy, FDG-PET hypometabolism), which precedes cognitive decline (MCI → dementia). Your KG's disease stage progression network in Step 9 (CN → SMC → EMCI → LMCI → AD) directly implements this model. Read this to understand the biological ground truth that your causal discovery should confirm or refine.
2.2 Causal Modeling of the AD Cascade
Bilgel et al. (2022) — "Causal links among amyloid, tau, and neurodegeneration", Brain Communications 4(4):fcac193.
→ Establishes directed causal relationships (Aβ → tau → neurodegeneration) using longitudinal ADNI data and structural causal models. Directly validates what your Phase 2 causal discovery should recover. Read the Methods section for their variable selection strategy — you can replicate it using UPENNBIOMK_ROCHE_ELECSYS (ABETA42, TAU, PTAU) and UCSFFSX7 (hippocampal volumes).
Petrella/Hao et al. (2019) — "Computational Causal Modeling of the Dynamic Biomarker Cascade in AD", Computational and Mathematical Methods in Medicine.
→ Implements the Jack model computationally with ODEs. Useful for Phase 3 validation: the causal edges your algorithms discover should be consistent with the ODE-derived orderings.
Shen et al. (2020) — "Challenges and Opportunities with Causal Discovery Algorithms: Application to Alzheimer's Pathophysiology", Scientific Reports 10:2975.
→ Critical reading before Phase 2. Tests PC, FCI, GES, and other constraint-based algorithms on ADNI biomarker data. Documents common pitfalls: non-Gaussianity of neuroimaging features, missing data patterns in ADNI, and the impact of cohort selection on recovered graphs. This paper will directly inform your algorithm selection and preprocessing choices.
Zheng et al. (2022) — "Data-driven causal model discovery and personalized prediction in AD", npj Digital Medicine 5:137.
→ Shows a complete pipeline from ADNI data to personalized causal models. Particularly valuable for Phase 2 methodology: their variable encoding, handling of categorical diagnosis (DX), and evaluation framework are directly transferable.
Glazman et al. (2024) — "Dynamic causal discovery in Alzheimer's disease through latent pseudotime modelling", arXiv:2511.04619.
→ Most recent (2024) approach. Uses latent pseudotime to handle the irregular sampling in ADNI longitudinal data. Relevant if you extend the project beyond baseline analysis.
2.3 Multicausality and Systems-Level Models
Uleman et al. (2021) — "Mapping the multicausality of Alzheimer's disease through group model building", GeroScience 43:829–843.
→ Uses causal loop diagrams to map the full multi-factorial causal structure of AD, including non-biomarker factors (education, cardiovascular health, social engagement). Contextualizes your KG's risk factor network (Step 9) scientifically.
Iturria-Medina et al. (2017) — "Multifactorial causal model of brain (dis)organization and therapeutic intervention", NeuroImage 152:60–77.
→ The most comprehensive multi-factor causal model available. Covers seven disease factors simultaneously. Reference this when justifying why your KG needs multi-modal data (MRI volumetrics, PET amyloid, CSF biomarkers, cognitive scores all together).
Pölsterl et al. (2023) — "Identification of causal effects of neuroanatomy on cognitive decline requires modeling unobserved confounders", Alzheimer's & Dementia 19:1994–2005.
→ A methodological warning: unobserved confounders (APOE4 genotype, education level) invalidate naive causal inference. Read before interpreting your Phase 2 output. Your KG should include APOE4 status from APOERES table as a key confounder node.
2.4 Knowledge Graphs for Alzheimer's Disease
Romano et al. (2024) — "The Alzheimer's Knowledge Base: A Knowledge Graph for Alzheimer Disease Research", JMIR 26:e46777.
→ Describes AlzKB, the external KG you plan to use for Phase 3 validation. Read the entity and relationship schema before designing your Phase 3 alignment. AlzKB contains 118,902 entities with sources including DisGeNET, DrugBank, GWAS Catalog, Gene Ontology, and the Monarch Initiative.
Spassov et al. (2024) — "Alzheimer's Disease Knowledge Graph Based on Ontology and Neo4j Graph Database", ICDAM 2023 Proceedings pp.71–80.
→ Most directly comparable published work to yours — also builds an AD KG on Neo4j with ontology grounding. Compare their node/relationship taxonomy to your Step 1 schema. Particularly useful for thesis methodology section to position your contribution against prior art.
Yang et al. (2025) — "Alzheimer's disease knowledge graph enhances knowledge discovery and disease prediction", Computers in Biology and Medicine 192:110285.
→ Uses GPT-4 for literature-based KG construction + UK Biobank validation. Shows the state-of-the-art in AD KG enrichment. Your data-driven approach (from ADNI observations) is complementary — cite this to frame what literature-based KGs miss that patient-observation KGs provide.
Lyu et al. (2025) — "Improving knowledge graphs via data-based causal structures", Knowledge and Information Systems 67:6505–6523.
→ Directly relevant to your thesis contribution. This paper formalizes exactly what you are doing in Phase 3: using causal discovery on observational data to add or refine edges in a KG. Use their pipeline as a methodological template and cite it as the primary methodological antecedent for your Phase 3 integration step.
Malec et al. (2023) — "Causal feature selection using a knowledge graph combining structured knowledge from biomedical literature and ontologies", Journal of Biomedical Informatics 142:104368.
→ Uses an existing KG to guide causal feature selection (e.g., which variables to include as potential confounders). This bridges your KG (Phase 1) to your causal discovery (Phase 2): use the KG's existing relationships to inform the Markov blanket of each target variable before running PC/FCI.
2.5 Causal Discovery Algorithms (Technical Reading)
Ramsey (2017) — "Scaling up Greedy Equivalence Search for continuous variables", arXiv:1507.07749.
→ FGES algorithm — the scalable version of GES you should use in Phase 2 for large feature sets. Available in the TETRAD software suite and the causal-learn Python package.
Huang et al. (2020) — "Causal discovery from heterogeneous/nonstationary data", JMLR 21(89):1–53.
→ JCI/CD-NOD algorithm for heterogeneous data (important because ADNI spans ADNI1/2/3/4 with different protocols). Read the section on how to handle multi-cohort data.
Gomez et al. (2025) — "Causal inference for time series datasets with partially overlapping variables", JBI 166:104828.
→ CMC-TS method for datasets where different patients have different measured variables. Directly applicable to ADNI because not all biomarkers are measured at all visits for all cohorts.
Pearl (2009) — Causality: Models, Reasoning, and Inference, Cambridge University Press.
→ The foundational text. At minimum read Chapters 1–3 (structural causal models, do-calculus basics) and Chapter 7 (the front-door and back-door criteria) before writing your Phase 2 methods section.
2.6 Disease Trajectory Modeling
Young et al. (2018) — "Uncovering the heterogeneity and temporal complexity of neurodegenerative diseases with SuStaIn", Nature Communications 9:4761.
→ SuStaIn (Subtype and Stage Inference) models disease heterogeneity: not all patients follow the same biomarker cascade ordering. Read this to understand why your static causal graph may need to account for patient subtypes.
Bossa & Sahli (2023) — "A multidimensional ODE-based model of Alzheimer's disease progression", Scientific Reports 13:3162.
→ Mathematical formalization of biomarker progression as a system of coupled ODEs. Provides a quantitative benchmark: if your Phase 2 causal graph disagrees with the ODE-derived ordering, you need to explain why.
2.7 Neuroimaging and Multimodal Analysis
Raj et al. (2015) — "Network Diffusion Model of Progression Predicts Longitudinal Patterns of Atrophy and Metabolism in Alzheimer's Disease", Cell Reports 10:359–369.
→ Graph-based diffusion model of atrophy spreading. Provides a network science perspective on how neurodegeneration propagates — relevant to your MRI volumetric data and the UCSFFSX7 FreeSurfer regional volumes in headers.json.
Venugopalan et al. (2021) — "Multimodal deep learning models for early detection of Alzheimer's disease stage", Scientific Reports 11:3254.
→ Shows classification performance when combining MRI, PET, cognitive scores, and genetic data — exactly the multi-modal combination in your KG. Read to benchmark which feature combinations provide the strongest signal.

3. ADNI Dataset: Table Reference Guide
The headers.json file documents 180+ ADNI tables across 5,800+ columns. Below is a curated reference of the most important tables for the KG construction and causal analysis phases.
3.1 Core Identity and Diagnostic Tables
TableKey ColumnsPurpose in KGPTDEMOGPTID, RID, PTGENDER, PTDOBYY, PTEDUC, PTMARRY, PTRACCATPatient hub node — demographics, APOE4DXSUM_PDXCONVPTID, VISCODE, DXCHANGE, DXCURRENDiagnosis node — maps to DiseaseStageROSTERRID, PTID, PHASE, SITEIDCohort assignment — ADNI1/2/GO/3/4
3.2 Cognitive Assessment Tables
TableKey ColumnsPurpose in KGADASPTID, VISCODE, TOTSCORE, TOTAL13ADAS-Cog score — primary AD cognitive markerMOCAPTID, VISCODE, MOCA (score)MoCA — screening cognitive measureMMSEPTID, VISCODE, MMSCOREMMSE — widely used dementia screenCDRPTID, VISCODE, CDGLOBAL, CDRSBClinical Dementia Rating — stagingNEUROBATPTID, VISCODE, multipleNeuropsychological battery scoresAMNARTPTID, VISCODE, AMNART1–50American NART — premorbid IQ estimateAMASPTID, VISCODE, AMAS1–42Anxiety/mood scale itemsWATCPTID, VISCODE, WATC1–40, RAWSCOREWatch test of cognitive function
For causal discovery: use ADAS.TOTSCORE, MOCA total, MMSE.MMSCORE, and CDR.CDRSB as outcome/cognitive decline variables. These are your Phase 2 dependent variables in the Jack cascade model.
3.3 Biomarker Tables (Core of Causal Analysis)
TableKey ColumnsOntology MappingUPENNBIOMK_ROCHE_ELECSYSPTID, VISCODE2, ABETA40, ABETA42, TAU, PTAULOINC: 57973-5, 48543-0, etc.URMC_LABDATARID, VISCODE, TestName, ResultValueStandard lab valuesVITALSPTID, VISCODE, VSWEIGHT, VSHEIGHT, VSBPSYS, VSBPDIA, VSPULSEVital signs — vascular risk factors
The UPENNBIOMK_ROCHE_ELECSYS table is the most important for Phase 2 causal discovery — ABETA42, TAU, and PTAU are the three pillars of the Jack biomarker cascade. The ABETA42/ABETA40 ratio is a more sensitive amyloid marker than ABETA42 alone. Compute this ratio as a derived feature before running causal algorithms.
3.4 Neuroimaging Metadata Tables
TableKey ColumnsPurposeAll_Imagesimage_id, subject_id, modality, image_type, image_visit, image_descriptionImage inventory — links to file storageAMYMETARID, VISCODE, RADTRACER, SCANDATE, TRACERTYPEAmyloid PET metadataUCBERKELEY_AMY_6MMRID, VISCODE, SUMMARYSUVR_WHOLECEREBNORMAmyloid PET SUVR — quantitative amyloid loadUCSFFSX7RID, VISCODE, ST*SV/CV/SA/TA/TSFreeSurfer 7 volumes — 130+ regional brain measures
The UCSFFSX7 table contains 130+ FreeSurfer-derived regional brain measures. Key ones for the Jack cascade: hippocampal volume (ST29SV or ST30SV depending on hemisphere), entorhinal cortex thickness (ST8SV), and ventricle volume (ST42SV) as a neurodegeneration marker. The column naming follows ST{region_id}{measure} where measure is SV=SubVolume, CV=Cortical Volume, SA=Surface Area, TA=Thickness Average, TS=Thickness Std.
3.5 Genetic Tables
TableKey ColumnsPurposeAPOERESPTID, APGEN1, APGEN2APOE genotype — major genetic risk factorGWAS_resultsSNP identifiers, effect sizesGWAS associations
APOE4 is a critical confounder in causal analysis (per Pölsterl et al., 2023). The APOERES table provides APGEN1 and APGEN2 alleles — derive APOE4 carrier status (1 if either allele = 4, 2 if both = 4) as a categorical variable. Always include in the conditioning set.
3.6 Safety and Symptom Tables
TableKey ColumnsPurposeADVERSEPTID, AEHONSDT, AEOUTCOME, AEHSEVR, AERELADAdverse events — comorbidity trackingADSXLISTPTID, VISCODE, AX* columnsAdverse symptom checklist (30 symptoms)MEDHISTPTID, VISCODE, variousMedical history — comorbidities
3.7 Visit and Event Structure
Every ADNI table uses three primary visit identifiers: VISCODE (original, e.g., "bl", "m06", "m12") and VISCODE2 (standardized across phases). For Phase 1 KG semantics, map VISCODE values to Visit nodes with visit_month properties. For Phase 2 (baseline causal analysis), always filter to VISCODE = 'bl' or VISCODE2 = 'bl' to obtain cross-sectional baseline data that avoids longitudinal dependencies.

4. Repository Architecture
The GitHub repository (theFellandes/ADNIKnowledgeGraph) is organized as:
ADNIKnowledgeGraph/
├── steps/              # The 15-step ETL + KG pipeline
├── models/             # Data models and schema definitions  
├── utils/              # Neo4j connector, ES indexer, helpers
├── misc/               # Utilities, exploratory notebooks
├── new_pipeline4_6.py  # Main pipeline orchestrator
├── kg_streamlit_ui.py  # Streamlit visualization UI
├── config.yaml         # All configuration (connections, paths, flags)
├── docker-compose.yml  # Container setup for Neo4j + Elasticsearch + Redis
└── requirements.txt    # Python dependencies
4.1 Pipeline Step Summary
StepFileFunctionStatus1step1_database_setup.pyInitialize Neo4j + Elasticsearch, create constraints and indexesComplete2step2_load_tables.pyLoad all ADNI CSV tables into memory with dtype optimizationComplete3step3_create_patients.pyCreate Patient hub nodes from PTDEMOGComplete4step4_extract_family.pyExtract family relationship dataComplete5step5_improved_process_images.pyProcess DICOM/NIfTI images, create TIFF + thumbnailsComplete5bstep5_improved_process_images_with_tiff.pyTIFF variant with HTJ2K/JPEG2000 supportComplete6step6_extract_findings_robust.pyExtract clinical findings from assessment tablesComplete7step7_batch_insert.pyBatch-insert remaining node typesComplete8step8_create_relationships.pyCreate all graph relationshipsComplete9step9_knowledge_graph_enhancer.pyAdd semantic relationships (ATN framework, stage progression, etc.)Complete10step10_execute_queries.pyExecute analytical Cypher queries, generate reportsComplete11step11_biomarker_analysis.pyDedicated biomarker analysisComplete12step12_complete_graph_enhancement.pyExternal knowledge integration (AlzKB alignment)Complete13step13_graph_eda.pyExport to CSV/JSON/GraphML for EDAComplete14step14_test_queries.pyResearch query executionComplete15step15_event_based_model.pyEvent-based temporal modelComplete
4.2 Current Graph Schema (17 Node Types)
The Neo4j graph currently contains the following node labels, each corresponding to an ADNI domain concept:

Patient — Core hub node (PTID, RID, demographics from PTDEMOG)
Visit — Clinical visit (viscode, phase, date)
Diagnosis — Clinical diagnosis at visit (diagnosis_code, diagnosis_name)
DiseaseStage — Semantic stage node (CN, SMC, EMCI, LMCI, AD)
Biomarker — Biomarker measurement (type, value, unit)
BiomarkerProfile — Aggregated CSF/blood biomarker panel per visit
CognitiveAssessment — ADAS, MMSE, CDR, MoCA scores per visit
MedicalImage — Image metadata (modality, format, path, hash)
ImageSeries — DICOM series grouping
BrainRegion — FreeSurfer anatomical region (UBERON-mapped)
GeneticProfile — APOE genotype and GWAS markers
RiskFactor — Modifiable/non-modifiable risk factor node
ClinicalFinding — Extracted findings from assessment tables
FamilyMember — Family history data
AdverseEvent — Adverse events from ADVERSE table
Site — Clinical site (SITEID)
ResearchProtocol — ADNI phase protocol reference

4.3 Key Relationship Types (20+)
RelationshipFrom → ToSemantic MeaningHAS_VISITPatient → VisitPatient attended visitHAS_DIAGNOSISVisit → DiagnosisDiagnosis at visitIN_STAGEDiagnosis → DiseaseStageStage classificationPROGRESSES_TODiseaseStage → DiseaseStageTemporal orderingHAS_BIOMARKERVisit → BiomarkerProfileBiomarker panel at visitMEASURESBiomarkerProfile → BiomarkerSpecific measurementHAS_COGNITIVE_ASSESSMENTVisit → CognitiveAssessmentCognitive test at visitHAS_IMAGINGVisit → ImageSeriesImaging session at visitCONTAINS_IMAGEImageSeries → MedicalImageImage in seriesHAS_BRAIN_REGIONMedicalImage → BrainRegionFreeSurfer region volumesHAS_GENETIC_PROFILEPatient → GeneticProfileGenetic dataASSOCIATED_WITH_RISKPatient → RiskFactorRisk factor linkageINDICATESBiomarker → DiseaseStageBiomarker-stage associationCORRELATES_WITHBiomarker → BiomarkerCorrelation edges (Step 9)FAMILY_HISTORY_OFPatient → FamilyMemberFamily AD historyTREATED_ATPatient → SiteClinical site

5. Configuration Guide (config.yaml)
5.1 Critical Settings
yaml# Database Connections — must configure before any run
neo4j_uri: "bolt://localhost:7687"        # Change for remote servers
neo4j_user: "neo4j"
neo4j_password: "YOUR_PASSWORD"           # MUST CHANGE

elasticsearch:
  host: "localhost"
  port: 9200

# Data Paths — use absolute paths
base_path: "path/to/ADNI/data"           # Root of CSV downloads from IDA
output_dir: "path/to/outputs"

# Pipeline Mode (choose one)
clear_database: false                     # DESTRUCTIVE — deletes all data
incremental: true                         # SAFE — adds new, skips existing
5.2 Recommended Settings for Thesis Phase
For Phase 1 (semantic migration) and Phase 2 (causal discovery data extraction):
yamlincremental: true                         # Never rebuild from scratch
run_complete_graph_enhancement: true      # Step 15 — ensures semantic enrichment

# Performance
max_workers: 16                           # Adjust to CPU count
performance:
  neo4j:
    batch_size: 1000
    use_unwind: true

# Quality
quality_checks:
  enable: true
  validate_data: true
  detect_outliers: true
5.3 Image Processing Notes
The image_storage.zip_processing.mode: 'auto' setting handles both extracted DICOM directories and ZIP archives. For the IEEE paper submission validation, the following were confirmed:

MRI: 62/62 passed (100%)
PET: 38/38 passed (100%)
All formats produced TIFF with Pixel Value Preservation: 100% and Bit Depth Preservation: 100%

The output_formats.tiff: true and output_formats.png: true settings produce the lossless derivatives that the paper validates. Set output_formats.pyramid_tiff: false always (confirmed incompatibility with the pipeline).

6. ADNI Data Access Reference
ADNI data is accessed through the LONI Image and Data Archive (IDA) at ida.loni.usc.edu. The following is the official documentation structure:
Data Categories Available:

Subject Characteristics — Demographics, vital signs, family history
Clinical Assessments & Questionnaires — ADAS, CDR, MMSE, MoCA, neuropsychological battery
MRI — Raw DICOM + processed (FreeSurfer, TBM-SyN, DTI, fMRI, ASL)
PET — FDG-PET, Amyloid-PET (florbetapir/florbetaben/NAV), Tau-PET
Biofluid Biomarkers — CSF (Aβ, tau, pTau via Roche Elecsys), plasma, urine
Genetics & Omics — APOE genotyping, GWAS, WGS (via NIAGADS/NACC)
Neuropathology — Brain donation data (ADNI-NPC)

Protocol Documentation Available:

MRI: ADNI1/2/GO/3 technical manuals (see adni.loni.usc.edu/help-faqs/adni-documentation/)
PET: Centiloid conversion documentation
CSF: Biomarker test instructions (Roche Elecsys platform)
Clinical: Phase-specific protocol PDFs (ADNI1/2/3/4)

Important for thesis methodology: ADNI participants are assigned a Schedule of Events (SOE) based on diagnosis (CN, MCI, AD). Not all tables are collected at all visits for all participants — this creates the partially-overlapping variable problem addressed by Gomez et al. (2025) in the CMC-TS paper.

7. Three-Phase Research Plan
Phase 1: In-Place Semantic Migration (Current)
Goal: Transform the existing LPG into a true Knowledge Graph by adding semantic ontology properties to all node types, without rebuilding the database.
Actions:

Add ontology_uri properties to all node labels (e.g., Patient → SNOMED-CT 116154003, Visit → SNOMED-CT 308335008)
Add loinc_code to all Biomarker nodes (e.g., ABETA42 → LOINC 57973-5, PTAU → LOINC 53817-7)
Add uberon_id to all BrainRegion nodes (e.g., hippocampus → UBERON:0001954)
Map all relationship types to Relation Ontology terms (e.g., INDICATES → RO:0000059 "correlated with condition")
Add source_table and source_column provenance properties to all nodes
Create OntologyTerm nodes for SNOMED-CT, LOINC, UBERON entries and link with MAPPED_TO relationships

Quality criterion: After Phase 1, a query MATCH (b:Biomarker) WHERE b.loinc_code IS NULL RETURN count(b) should return 0 for all biomarker nodes with known LOINC mappings.
Phase 2: Causal Discovery on Baseline Data
Goal: Apply PC, FCI, GES/FGES, and DAG-GNN algorithms to baseline cross-sectional ADNI data to discover the causal structure of the AD biomarker cascade.
Variable Set (from headers.json):

Amyloid: UPENNBIOMK_ROCHE_ELECSYS.ABETA42, computed ABETA42/ABETA40 ratio, UCBERKELEY_AMY_6MM.SUMMARYSUVR_WHOLECEREBNORM
Tau: UPENNBIOMK_ROCHE_ELECSYS.TAU, UPENNBIOMK_ROCHE_ELECSYS.PTAU
Neurodegeneration: UCSFFSX7.ST29SV (left hippocampus), UCSFFSX7.ST30SV (right hippocampus), UCSFFSX7.ST42SV (ventricles)
Cognition: ADAS.TOTSCORE, CDR.CDRSB, MMSE.MMSCORE
Confounders: PTDEMOG.PTAGE, APOERES (APOE4 status), PTDEMOG.PTEDUC, PTDEMOG.PTGENDER
Cohort indicator: ROSTER.PHASE (for multi-cohort heterogeneity)

Filter: VISCODE2 = 'bl' (baseline only for static causal analysis)
Expected graph topology (based on Jack 2010 + Bilgel 2022): Aβ42↓ → pTau↑ → hippocampal atrophy↓ → ADAS-Cog↑ (cognitive decline). Any algorithm that recovers a significantly different topology requires justification against the biological literature.
Software: Use causal-learn Python library (implements PC, FCI, GES, LiNGAM) and DoWhy for causal inference. For DAG-GNN, use the original PyTorch implementation.
Phase 3: Validation and KG Integration
Goal: Cross-validate discovered causal edges against AlzKB, then integrate confirmed causal edges as first-class CAUSALLY_PRECEDES relationships in the Neo4j KG.
AlzKB Alignment: Query AlzKB for entity pairs matching your discovered edges. Use the AlzKB SPARQL endpoint or download the RDF dump. Map your node URIs (LOINC, SNOMED, UBERON) to AlzKB entity identifiers.
New Relationship Type: Add CAUSALLY_PRECEDES {algorithm: "PC", p_value: ..., confidence: ..., validated_by: "AlzKB/Bilgel2022"} as a typed, provenance-annotated relationship.

8. Ontology Mapping Quick Reference
Entity TypeOntologyExample CodePatientSNOMED-CT116154003 (person)Alzheimer DiseaseSNOMED-CT26929004CSF Aβ42LOINC57973-5CSF pTauLOINC53817-7CSF Total TauLOINC48543-0Plasma Aβ40LOINC99521-7HippocampusUBERON0001954Entorhinal cortexUBERON0002728MRI scanDICOMmodality=MRPET scanDICOMmodality=PTAPOE4 genotypeSO (Sequence Ontology)0001023 (allele)HAS_PARTRelation OntologyRO:0000051PART_OFRelation OntologyRO:0000050CAUSALLY_UPSTREAM_OFRelation OntologyRO:0002404CORRELATED_WITHRelation OntologyRO:0000059

9. Thesis Positioning
Your thesis makes three scientifically distinct contributions:

Engineering contribution (published — IEEE Big Data 2025): Multi-tier medical imaging storage architecture combining DICOM preservation, Elasticsearch metadata indexing, and Neo4j ontology-driven graph integration. Validated on ADNI with 100% quality preservation.
Knowledge engineering contribution (Phase 1): Systematic transformation methodology for converting a real-world ADNI LPG to a semantically-grounded KG. This methodology can be generalized to other clinical datasets. Reference Spassov et al. (2024) and Dobreva et al. (2025) as the prior art being extended.
Data science contribution (Phases 2–3): Data-driven causal structure discovery from ADNI multi-modal data, with results integrated back into the KG as provenance-annotated causal edges. Reference Lyu et al. (2025) as the methodological framework being instantiated on the AD domain.


10. External Resources
ResourceURL / LocationUseADNI Data Portal (IDA)ida.loni.usc.eduDownload CSVs, imagesADNI Documentationadni.loni.usc.edu/help-faqs/adni-documentation/Protocol PDFsADNI Data Dictionaryadni.loni.usc.edu/data-samples/data-dictionary-search/Column descriptionsAlzKB Downloadgithub.com/EpistasisLab/alzheimers-knowledge-basePhase 3 validationcausal-learncausal-learn.readthedocs.ioPC, FCI, GES PythonDoWhypy-why.github.io/dowhy/Causal inference + refutationsTETRADbd2kccd.github.io/docs/tetrad/Causal discovery suiteBiolink Modelbiolink.github.io/biolink-model/Biomedical KG standard schemaOBO Foundryobofoundry.orgUBERON, RO, SO ontologiesLOINC Browserloinc.org/search/LOINC code lookupSNOMED Browserbrowser.ihtsdotools.orgSNOMED-CT lookupGitHub Repogithub.com/theFellandes/ADNIKnowledgeGraphSource codeGoogle Drivedrive.google.com/drive/folders/1Ab-TgveIWRNCqKiPlc_zzF8aj7wTC0HOPaper repository, reports

Last updated: February 2026 | This document integrates ADNI official documentation, GitHub repository architecture, headers.json dataset schema, IEEE Big Data 2025 paper findings, and the full paper repository bibliography from Google Drive.