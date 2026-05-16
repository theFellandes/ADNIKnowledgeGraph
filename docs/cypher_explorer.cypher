// ============================================================================
// ADNI Knowledge Graph — Cypher Explorer
// ============================================================================
// A guided tour of the ADNI-KG in Neo4j Browser.
// Copy-paste sections into Neo4j Browser (http://localhost:7474) one at a time.
//
// Sections:
//   1. Overview & Schema Discovery
//   2. Patient Demographics
//   3. Diagnosis & Disease Progression
//   4. Cognitive Assessments
//   5. Biomarkers (CSF, PET, ATN)
//   6. Medical Imaging
//   7. Family History & Genetics
//   8. Ontology & Semantic Layer
//   9. Temporal Patterns (Visits)
//  10. Graph Topology & Connectivity
//  11. Cross-Domain Queries (Putting It All Together)
//  12. Data Quality & Completeness
// ============================================================================


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  1. OVERVIEW & SCHEMA DISCOVERY                                     ║
// ║  What's in the graph? How big is it?                                ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 1.1 Total node and relationship counts
//     Quick sanity check: returns the overall size of the knowledge graph.
//     total_nodes: every entity (Patient, Diagnosis, Biomarker, etc.)
//     total_relationships: every directed edge in the graph
MATCH (n) WITH count(n) AS nodes
MATCH ()-[r]->() WITH nodes, count(r) AS rels
RETURN nodes AS total_nodes, rels AS total_relationships;

// 1.2 Count nodes by label (sorted, skip empty labels)
//     Shows the cardinality of each node type in the KG.
//     label: the Neo4j node label (e.g., Patient, Diagnosis, Biomarker)
//     cnt: how many nodes carry that label
CALL db.labels() YIELD label
CALL (label) { MATCH (n) WHERE label IN labels(n) RETURN count(n) AS cnt }
WITH label, cnt WHERE cnt > 0
RETURN label, cnt
ORDER BY cnt DESC;

// 1.3 Count relationships by type (sorted)
//     Enumerates every edge type and its frequency.
//     type: relationship name (e.g., HAS_DIAGNOSIS, MAPS_TO, PRECEDES)
//     cnt: number of edges of that type
CALL db.relationshipTypes() YIELD relationshipType AS type
CALL (type) { MATCH ()-[r]->() WHERE type(r) = type RETURN count(r) AS cnt }
RETURN type, cnt
ORDER BY cnt DESC;

// 1.4 Visual schema — shows how node types connect (best in Neo4j Browser)
CALL db.schema.visualization();

// 1.5 Relationship patterns: which node types connect via which relationships
//     A meta-level view of the KG schema inferred from actual data.
//     source/target: node labels on each end of the edge
//     relationship: edge type name
//     Filtered to patterns with >50 occurrences to suppress noise.
MATCH (a)-[r]->(b)
WITH labels(a)[0] AS source, type(r) AS relationship, labels(b)[0] AS target, count(*) AS cnt
WHERE cnt > 50
RETURN source, relationship, target, cnt
ORDER BY cnt DESC
LIMIT 40;

// 1.6 Unique constraints
//     Lists all uniqueness/existence constraints enforcing data integrity.
SHOW CONSTRAINTS;

// 1.7 Unique indexes
//     Lists all indexes that speed up lookups (property, full-text, etc.).
SHOW INDEXES;


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  2. PATIENT DEMOGRAPHICS                                            ║
// ║  Who are the 2,638 participants?                                    ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 2.1 Gender distribution
//     ADNI recruits roughly balanced male/female cohorts.
//     gender: Male or Female; count: number of patients per group.
MATCH (p:Patient)
RETURN p.gender AS gender, count(p) AS count
ORDER BY count DESC;

// 2.2 Education years distribution
//     Higher education is a known protective factor against cognitive decline.
//     education_years: total years of formal education (typically 6-20).
MATCH (p:Patient) WHERE p.education_years IS NOT NULL
RETURN p.education_years AS education_years, count(p) AS count
ORDER BY education_years;

// 2.3 Age at baseline distribution (bucketed into 5-year ranges)
//     Buckets patients by age at their first ADNI visit into 5-year bins.
//     age_at_baseline is calculated from PTDOBYY (birth year) and VISDATE.
//     toFloat() ensures safe arithmetic even if the value was ingested as a string.
//     Typical ADNI range: 55-90 years.
//     Requires: Pipeline re-run after step3 fix (PTDOBYY-based age calculation).
MATCH (p:Patient)
WHERE p.age_at_baseline IS NOT NULL
WITH toInteger(toFloat(p.age_at_baseline) / 5) * 5 AS bucket
RETURN bucket AS age_range_start, (bucket + 5) AS age_range_end, count(*) AS count
ORDER BY bucket;

// 2.4 APOE genotype distribution (major Alzheimer's genetic risk factor)
//     APOE e4 carriers have significantly higher AD risk.
//     Genotype format: 'E3/E4', 'E4/E4', etc. (parsed from APOERES GENOTYPE column).
//     E4/E4 homozygotes have ~12x higher AD risk than E3/E3.
//     Requires: Pipeline re-run after step3 fix (GENOTYPE column parsing).
MATCH (p:Patient)
WHERE p.apoe_genotype IS NOT NULL
RETURN p.apoe_genotype AS apoe_genotype, count(*) AS count
ORDER BY count DESC;

// 2.5 Sample 10 patients with their key attributes
//     Quick peek at actual patient records. Use a PTID from here
//     in placeholder queries (4.4, 6.5, 9.3, 10.5, 10.6).
MATCH (p:Patient)
RETURN p.ptid AS patient_id, p.gender AS gender,
       p.education_years AS education,
       coalesce(p.age_at_baseline, p.age) AS age,
       coalesce(p.apoe_genotype, p.apoe4) AS apoe
ORDER BY p.ptid
LIMIT 10;

// 2.6 Diagnosis-based cohort distribution
//     These are diagnosis-based cohorts (AD, MCI, SMC, CN), NOT ADNI study
//     phases. BELONGS_TO_COHORT links each patient to a ResearchCohort node
//     that represents their baseline diagnostic group.
//     cohort: the cohort identifier (e.g., AD, MCI, CN, SMC)
//     patients: number of patients assigned to that cohort
MATCH (p:Patient)-[:BELONGS_TO_COHORT]->(c:ResearchCohort)
RETURN c.cohort_id AS cohort, count(p) AS patients
ORDER BY patients DESC;


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  3. DIAGNOSIS & DISEASE PROGRESSION                                 ║
// ║  CN → MCI → AD trajectory                                          ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 3.1 Diagnosis distribution
//     CN  = Cognitively Normal (healthy control)
//     MCI = Mild Cognitive Impairment (prodromal stage)
//     AD  = Alzheimer's Disease (clinical dementia)
MATCH (d:Diagnosis)
RETURN coalesce(d.diagnosis_code, d.dx_label, d.diagnosis) AS diagnosis,
       count(d) AS count
ORDER BY count DESC;

// 3.2 Patients per diagnosis group
//     Groups patients by their first distinct diagnosis label.
//     A patient may have multiple diagnoses over time; this takes the first.
//     diagnosis: CN, MCI, LMCI, EMCI, AD, SMC, etc.
//     patients: unique patient count per group
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
WITH p, collect(DISTINCT coalesce(d.diagnosis_code, d.dx_label))[0] AS dx
RETURN dx AS diagnosis, count(DISTINCT p) AS patients
ORDER BY patients DESC;

// 3.3 Disease stage transitions
//     Shows how diagnoses transition over time using PROGRESSED_TO edges.
//     These edges connect Diagnosis nodes when a patient's diagnostic
//     label changes at a subsequent visit (e.g., CN -> MCI, MCI -> AD).
//     from_dx/to_dx: the diagnosis codes at start and end of the transition.
//     transitions: how many times this specific transition was observed.
MATCH (d1:Diagnosis)-[r:PROGRESSED_TO]->(d2:Diagnosis)
WITH coalesce(d1.diagnosis_code, d1.dx_label) AS from_dx,
     coalesce(d2.diagnosis_code, d2.dx_label) AS to_dx,
     count(r) AS transitions
RETURN from_dx, to_dx, transitions
ORDER BY transitions DESC
LIMIT 20;

// 3.4 Patients who converted from CN to MCI or AD (converters)
//     "Converters" are clinically important — they let researchers study
//     what biomarker/cognitive changes precede diagnostic conversion.
//     converted_to: the new diagnostic label after conversion
//     at_visit: the visit code when conversion was first recorded
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d1:Diagnosis),
      (p)-[:HAS_DIAGNOSIS]->(d2:Diagnosis)
WHERE coalesce(d1.diagnosis_code, d1.dx_label) = 'CN'
  AND coalesce(d2.diagnosis_code, d2.dx_label) IN ['MCI', 'LMCI', 'AD']
RETURN p.ptid AS patient_id,
       coalesce(d2.diagnosis_code, d2.dx_label) AS converted_to,
       d2.visit_id AS at_visit
ORDER BY patient_id
LIMIT 25;

// 3.5 Progression patterns
//     Shows all diagnosis transitions detected by Step 15 (event-based model).
//     pattern_type: 'rapid_progression' (CN→AD <36mo), 'fast_progression' (<24mo),
//     or 'standard_progression' (all other transitions).
//     from_state/to_state: diagnostic labels at start and end of progression.
//     progression_time: duration in months between the two diagnoses.
//     Requires: Step 15 must have been executed.
MATCH (pp:ProgressionPattern)
WHERE pp.pattern_type IS NOT NULL
RETURN pp.pattern_type AS type,
       pp.from_state AS from_stage,
       pp.to_state AS to_stage,
       pp.progression_time AS duration_months,
       pp.patient_id AS patient
ORDER BY pp.progression_time
LIMIT 15;

// 3.5b Event-based progression patterns
//      EventPattern nodes capture common 3-event trajectory sequences
//      (e.g., 'DIAGNOSIS_CHANGE->BIOMARKER_CHANGE->COGNITIVE_DECLINE').
//      Created by Step 15 (event-based model) from FOLLOWED_BY chains.
//      pattern_string: the sequence of event types
//      frequency: how many times this 3-event chain occurred
//      percentage: relative frequency across all detected patterns
//      Requires: Step 15 must have been executed.
MATCH (ep:EventPattern)
RETURN ep.pattern_string AS event_sequence,
       ep.frequency AS occurrences,
       ep.percentage AS pct
ORDER BY ep.frequency DESC
LIMIT 15;

// 3.6 DiseaseStage ontology nodes (reference data)
//     DiseaseStage nodes are ordered reference entries representing the
//     clinical spectrum: CN (1) -> SMC (2) -> EMCI (3) -> LMCI (4) -> AD (5).
//     stage_id: unique identifier for the stage node
//     name: human-readable stage label
//     order: numeric position in the progression continuum
//     snomed_code/snomed_label: optional SNOMED-CT mapping for interoperability
MATCH (ds:DiseaseStage)
RETURN ds.stage_id AS stage_id, ds.name AS stage, ds.order AS stage_order,
       ds.snomed_code AS snomed_code, ds.snomed_label AS snomed_label
ORDER BY ds.order;


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  4. COGNITIVE ASSESSMENTS                                           ║
// ║  MMSE, CDR-SB, ADAS-Cog — the clinical endpoints                   ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 4.1 Assessment types and counts
//     MMSE: Mini-Mental State Exam (0-30, higher=better)
//     CDR-SB: Clinical Dementia Rating Sum of Boxes (0-18, lower=better)
//     ADAS-Cog: Alzheimer's Disease Assessment Scale (0-70, lower=better)
MATCH (ca:CognitiveAssessment)
RETURN ca.test_name AS test, count(ca) AS assessments
ORDER BY assessments DESC;

// 4.2 Average cognitive scores by diagnosis group
//     Validates that the KG reflects known clinical patterns:
//     AD patients should have lower MMSE (worse cognition) and higher
//     ADAS-Cog/CDR-SB (more impairment) than CN controls.
//     mean_score: group average; std_dev: within-group variability; n: sample size.
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis),
      (p)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
WITH coalesce(d.diagnosis_code, d.dx_label) AS dx, ca.test_name AS test,
     ca.total_score AS score
WHERE score IS NOT NULL AND dx IS NOT NULL
RETURN dx AS diagnosis, test,
       round(avg(score), 2) AS mean_score,
       round(stdev(score), 2) AS std_dev,
       count(score) AS n
ORDER BY test, dx;

// 4.3 Cognitive decline over time -- MMSE scores at each visit
//     Tracks mean MMSE across visits to visualize population-level decline.
//     visit: visit code (bl, m06, m12, etc.); mean_mmse: average score at that visit.
MATCH (p:Patient)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
WHERE ca.test_name CONTAINS 'MMSE' AND ca.total_score IS NOT NULL
WITH ca.visit_id AS visit, ca.total_score AS score
RETURN visit,
       round(avg(score), 2) AS mean_mmse,
       count(score) AS n_assessments
ORDER BY visit
LIMIT 20;

// 4.4 A single patient's full cognitive timeline
//     Longitudinal view of all cognitive tests for one participant.
//     Useful for case-study analysis or verifying data completeness.
//     Replace the PTID below with one from query 2.5.
MATCH (p:Patient {ptid: '002_S_0295'})-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
RETURN ca.test_name AS test, ca.visit_id AS visit,
       ca.total_score AS score, ca.visit_date AS date
ORDER BY ca.visit_date;

// 4.5 CognitiveTest reference nodes
//     CognitiveTest nodes are schema-level reference entries describing
//     each assessment instrument available in ADNI.
//     test_id: unique identifier; name: human-readable test name;
//     max_score: the theoretical maximum score for the test.
MATCH (ct:CognitiveTest)
RETURN ct.test_id AS test_id, ct.name AS test_name,
       ct.max_score AS max_score;

// 4.6 Multimodal assessments -- combined cognitive + biomarker evaluations
//     MultimodalAssessment nodes aggregate data across modalities for
//     a single patient-visit. They record how many cognitive tests,
//     biomarkers, and diagnoses were captured at that assessment point.
//     assessment_id: unique key; cognitive_count/biomarker_count/diagnosis_count:
//     number of linked measurements; cognitive_tests: list of test names.
MATCH (ma:MultimodalAssessment)
RETURN ma.assessment_id AS assessment_id,
       ma.cognitive_count AS cognitive_count,
       ma.biomarker_count AS biomarker_count,
       ma.diagnosis_count AS diagnosis_count,
       ma.cognitive_tests AS cognitive_tests
ORDER BY ma.cognitive_count DESC
LIMIT 10;


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  5. BIOMARKERS (CSF, PET, ATN)                                      ║
// ║  Biological evidence of Alzheimer's pathology                       ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 5.1 Biomarker types and counts
//     Key CSF biomarkers:
//       Abeta42: low in AD (amyloid pathology)
//       Tau: high in AD (neurodegeneration)
//       pTau: high in AD (tau tangle pathology)
MATCH (b:Biomarker)
RETURN b.analyte AS biomarker, count(b) AS measurements
ORDER BY measurements DESC
LIMIT 15;

// 5.2 Average biomarker values by diagnosis
//     Cross-references biomarkers with diagnoses to validate known patterns:
//     AD patients typically show low Abeta42, high Tau, and high pTau.
//     marker: the analyte name; mean_value/std_dev: group statistics; n: sample size.
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis),
      (p)-[:HAS_BIOMARKER]->(b:Biomarker)
WHERE b.value IS NOT NULL
WITH coalesce(d.diagnosis_code, d.dx_label) AS dx,
     b.analyte AS marker, b.value AS val
RETURN dx AS diagnosis, marker,
       round(avg(val), 2) AS mean_value,
       round(stdev(val), 2) AS std_dev,
       count(val) AS n
ORDER BY marker, dx;

// 5.3 ATN framework profiles
//     A = Amyloid (Abeta42), T = Tau (pTau), N = Neurodegeneration (tTau/FDG)
//     A+T+N+ = full Alzheimer's pathology; A-T-N- = no pathology
MATCH (atn:ATNProfile)
RETURN atn.profile AS atn_profile, count(atn) AS patients
ORDER BY patients DESC
LIMIT 10;
// ^ atn_profile: string like "A+T+N+"; patients: how many carry that profile

// 5.4 Biomarker categories (by specimen type)
//     Groups biomarkers by biological source: CSF, Blood/Plasma, Genetic.
//     The biomarker_type property captures the specimen or measurement method.
//     category: specimen/method type; analytes: distinct biomarker names;
//     total_measurements: number of Biomarker nodes in that category.
MATCH (b:Biomarker)
RETURN coalesce(b.biomarker_type, 'Unknown') AS category,
       collect(DISTINCT b.analyte) AS analytes,
       count(b) AS total_measurements
ORDER BY total_measurements DESC;

// 5.5 PET tracer types from binding measurements
//     PET tracers target specific pathologies:
//       AV45/FBB/PIB: amyloid tracers (detect beta-amyloid plaques)
//       FDG: glucose metabolism (neurodegeneration marker)
//       AV1451: tau tracer (detect tau tangles)
//     SUVR: Standardized Uptake Value Ratio -- higher = more tracer binding.
//     PETBinding nodes are created by step6 from AMYLOID_PET source data.
//     Note: If this returns no results, the source tables may not contain
//     SUMMARY_SUVR data. Query is structurally correct.
MATCH (pb:PETBinding)
RETURN pb.tracer AS tracer, count(pb) AS measurements,
       round(avg(pb.suvr), 3) AS avg_suvr
ORDER BY measurements DESC;

// 5.6 Patients with abnormal amyloid (A+) -- early AD detection
//     Amyloid-positive patients are on the Alzheimer's continuum even if
//     cognitively normal, making this a key early-detection biomarker.
//     IMPORTANT: The cutoff depends on the assay platform:
//       - Roche Elecsys (this dataset): Aβ42 < 1100 pg/mL indicates A+
//       - Legacy INNOTEST: Aβ42 < 192 pg/mL indicates A+
//     This dataset uses Roche Elecsys (source: UPENNBIOMK_ROCHE_ELECSYS).
//     The analyte property uses Unicode: 'Aβ42' (not 'ABETA42').
MATCH (p:Patient)-[:HAS_BIOMARKER]->(b:Biomarker)
WHERE (b.analyte CONTAINS 'Aβ' OR b.analyte CONTAINS 'ABETA' OR b.analyte CONTAINS 'Abeta')
  AND b.value < 1100
RETURN p.ptid AS patient_id, b.analyte AS marker,
       round(b.value, 1) AS value, b.visit_id AS visit
ORDER BY b.value
LIMIT 20;


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  6. MEDICAL IMAGING                                                 ║
// ║  MRI & PET scans stored as multi-format renderings                  ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 6.1 Total image count
//     ImageNode represents a single MRI or PET scan in the graph.
//     Each image is linked to a Patient via HAS_IMAGE and carries
//     metadata such as modality, description, and format.
//     total_images: the number of ImageNode entities in the KG.
MATCH (img:ImageNode)
RETURN count(img) AS total_images;

// 6.2 Images per patient (distribution)
//     Summary statistics for how many scans each patient has.
//     Patients with many images have longer follow-up or multi-modality data.
MATCH (p:Patient)-[:HAS_IMAGE]->(img:ImageNode)
WITH p.ptid AS patient, count(img) AS image_count
RETURN min(image_count) AS min_images,
       round(avg(image_count), 1) AS avg_images,
       max(image_count) AS max_images,
       count(patient) AS patients_with_images;

// 6.3 Image modality breakdown (MRI vs PET)
//     MRI captures brain structure; PET captures molecular pathology.
//     modality: imaging type; count: number of scans of that type.
MATCH (img:ImageNode)
RETURN coalesce(img.modality, 'Unknown') AS modality, count(img) AS count
ORDER BY count DESC;

// 6.4 Sample image metadata
//     Peek at raw image properties: hash (unique ID), modality, description, format.
MATCH (img:ImageNode)
RETURN img.image_hash AS hash,
       img.modality AS modality,
       img.description AS description,
       img.format AS format
LIMIT 10;

// 6.5 Images linked to a specific patient (visual in Neo4j Browser)
//     Returns separate node/rel columns so Neo4j Browser renders
//     interactive graph bubbles rather than a flat path list.
//     Replace PLACEHOLDER with an actual PTID from query 2.5.
MATCH (p:Patient)-[r:HAS_IMAGE]->(img:ImageNode)
WHERE p.ptid = 'PLACEHOLDER'
RETURN p, r, img
LIMIT 25;
// ^ Replace PLACEHOLDER with an actual PTID


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  7. FAMILY HISTORY & GENETICS                                       ║
// ║  Hereditary risk factors for Alzheimer's disease                    ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 7.1 Family member counts
//     Total number of FamilyMember nodes in the KG.
//     Each represents a first-degree relative (parent, sibling, child)
//     reported by an ADNI participant.
MATCH (fm:FamilyMember)
RETURN count(fm) AS total_family_members;

// 7.2 Family relationship types
//     Shows which edge types connect Patient -> FamilyMember
//     (e.g., HAS_FAMILY_MEMBER, HAS_SIBLING, HAS_PARENT, HAS_CHILD).
MATCH (p:Patient)-[r]->(fm:FamilyMember)
RETURN type(r) AS relationship, count(r) AS count
ORDER BY count DESC;

// 7.3 Family dementia risk summary
//     Counts patients by how many first-degree relatives have dementia.
//     Family history of dementia is a major non-genetic risk factor for AD.
//     affected_relatives: number of relatives with dementia for a given patient.
//     patients_with_n_affected: how many patients have that count.
MATCH (p:Patient)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember)
WHERE fm.has_dementia = true
WITH p.ptid AS patient, count(fm) AS affected_relatives
RETURN affected_relatives, count(patient) AS patients_with_n_affected
ORDER BY affected_relatives;

// 7.4 Patients with first-degree relatives affected by dementia
//     Lists individual patients and their count of affected relatives.
//     Sorted descending to find patients with the strongest family burden.
MATCH (p:Patient)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember)
WHERE fm.has_dementia = true OR fm.dementia_status = 'Yes'
RETURN p.ptid AS patient, count(fm) AS affected_relatives
ORDER BY affected_relatives DESC
LIMIT 20;

// 7.5 Sibling relationships
//     HAS_SIBLING connects Patient -> FamilyMember (siblings of the patient).
//     This was previously broken because it matched FamilyMember->FamilyMember
//     instead of Patient->FamilyMember.
//     sibling_relationships: total HAS_SIBLING edges
//     patients_with_siblings: distinct patients who have at least one sibling recorded
MATCH (p:Patient)-[:HAS_SIBLING]->(fm:FamilyMember)
RETURN count(*) AS sibling_relationships,
       count(DISTINCT p) AS patients_with_siblings;


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  8. ONTOLOGY & SEMANTIC LAYER                                       ║
// ║  SNOMED-CT, LOINC, UBERON, ICD-10 mappings                         ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 8.1 OntologyConcept nodes — the semantic backbone
//     These map ADNI clinical data to international medical standards
MATCH (oc:OntologyConcept)
RETURN oc.source_ontology AS ontology, oc.code AS code,
       oc.label AS label, oc.uri AS uri
ORDER BY oc.source_ontology, oc.code;

// 8.2 MAPS_TO relationships -- how clinical nodes link to ontology
//     MAPS_TO edges connect clinical data nodes (Diagnosis, CognitiveAssessment,
//     BrainRegion, Biomarker) to standardized OntologyConcept nodes.
//     node_type: which label is mapped; ontology: SNOMED/LOINC/UBERON/ICD-10/HPO.
MATCH (n)-[:MAPS_TO]->(oc:OntologyConcept)
WITH labels(n)[0] AS node_type, oc.source_ontology AS ontology, count(*) AS cnt
RETURN node_type, ontology, cnt
ORDER BY cnt DESC;

// 8.3 IS_A hierarchy (ontology taxonomy)
//     IS_A edges form a subsumption hierarchy within the ontology layer
//     (e.g., "Alzheimer's disease" IS_A "Dementia"). 27 IS_A edges total.
MATCH path = (child:OntologyConcept)-[:IS_A]->(parent:OntologyConcept)
RETURN child.label AS child, parent.label AS parent,
       child.source_ontology AS ontology
ORDER BY ontology, parent;

// 8.4 SNOMED coverage -- which diagnoses have SNOMED codes
//     Measures what fraction of Diagnosis nodes carry a snomed_code property.
//     High coverage means better semantic interoperability.
MATCH (d:Diagnosis) WHERE d.snomed_code IS NOT NULL
WITH count(d) AS with_snomed
MATCH (d2:Diagnosis)
WITH with_snomed, count(d2) AS total
RETURN with_snomed, total,
       round(100.0 * with_snomed / total, 1) AS snomed_coverage_pct;

// 8.5 ICD-10 codes on diagnoses
//     Lists distinct ICD-10 codes stored directly on Diagnosis nodes.
//     icd10: the code (e.g., G30.9); label: human-readable description.
MATCH (d:Diagnosis)
WHERE d.icd10_code IS NOT NULL
RETURN DISTINCT d.icd10_code AS icd10, d.icd10_label AS label, count(d) AS count
ORDER BY count DESC;

// 8.6 ICD-10 → OntologyConcept mapping via CLASSIFIED_AS
//     Shows how diagnosis nodes connect to ICD-10 ontology concepts
MATCH (d:Diagnosis)-[:CLASSIFIED_AS]->(oc:OntologyConcept)
WHERE oc.source_ontology = 'ICD-10'
RETURN oc.code AS icd10_code, oc.label AS label, count(d) AS diagnoses_mapped
ORDER BY diagnoses_mapped DESC;

// 8.7 ICD-10 IS_A hierarchy traversal
//     Walk the ICD-10 taxonomy tree (e.g. G30.9 → G30)
MATCH path = (child:OntologyConcept)-[:IS_A*1..3]->(parent:OntologyConcept)
WHERE child.source_ontology = 'ICD-10'
RETURN child.code AS child_code, child.label AS child_label,
       [n IN nodes(path) | n.code] AS hierarchy_path,
       length(path) AS depth
ORDER BY depth DESC;

// 8.8 Diagnoses without ICD-10 mapping (coverage gap analysis)
//     Finds diagnosis codes that lack a CLASSIFIED_AS edge to an ICD-10 OntologyConcept.
//     If this returns no results, it means ALL diagnoses have ICD-10 mappings
//     -- which indicates full semantic coverage (a good outcome).
MATCH (d:Diagnosis)
WHERE NOT (d)-[:CLASSIFIED_AS]->(:OntologyConcept {source_ontology: 'ICD-10'})
RETURN coalesce(d.diagnosis_code, d.diagnosis_text) AS unmapped_diagnosis, count(d) AS count
ORDER BY count DESC;

// 8.9 Full ICD-10 semantic chain: Patient → Diagnosis → CLASSIFIED_AS → OntologyConcept
//     End-to-end traversal from patient to international classification
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)-[:CLASSIFIED_AS]->(oc:OntologyConcept)
WHERE oc.source_ontology = 'ICD-10'
RETURN p.ptid AS patient, coalesce(d.diagnosis_code, d.dx_label) AS dx,
       oc.code AS icd10, oc.label AS icd10_label
ORDER BY p.ptid
LIMIT 25;

// 8.10 LOINC codes on cognitive assessments
//      LOINC (Logical Observation Identifiers) codes standardize lab/clinical
//      test identifiers. Shows which cognitive tests have been LOINC-mapped.
MATCH (ca:CognitiveAssessment) WHERE ca.loinc_code IS NOT NULL
RETURN DISTINCT ca.loinc_code AS loinc, ca.test_name AS test, count(ca) AS count
ORDER BY count DESC;

// 8.11 Brain regions (UBERON-mapped)
//      BrainRegion nodes represent anatomical structures (hippocampus,
//      entorhinal cortex, etc.) mapped to UBERON ontology codes.
MATCH (br:BrainRegion)
RETURN br.name AS region, br.uberon_code AS uberon,
       br.description AS description
ORDER BY br.name;


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  9. TEMPORAL PATTERNS (VISITS)                                      ║
// ║  Longitudinal study visits from baseline through 10+ years          ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 9.1 Visit count by visit code
//     bl = baseline, m06 = 6 months, y1 = year 1, m24 = 24 months, etc.
MATCH (v:Visit)
RETURN v.viscode AS visit_code, count(v) AS visits
ORDER BY visits DESC
LIMIT 30;

// 9.2 Visits per patient (follow-up duration indicator)
//     More visits = longer longitudinal follow-up. ADNI patients
//     may have 1 (baseline only) to 20+ visits over a decade.
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)
WITH p.ptid AS patient, count(v) AS visit_count
RETURN min(visit_count) AS min_visits,
       round(avg(visit_count), 1) AS avg_visits,
       max(visit_count) AS max_visits;

// 9.3 Visit timeline -- sequential visit chain for one patient
//     Shows every visit for a single participant, ordered chronologically.
//     months: months elapsed since baseline; useful for time-series analysis.
MATCH path = (p:Patient)-[:HAS_VISIT]->(v:Visit)
WHERE p.ptid = 'PLACEHOLDER'
RETURN v.viscode AS visit_code,
       v.visit_date AS date,
       v.months_from_baseline AS months
ORDER BY v.months_from_baseline;
// ^ Replace PLACEHOLDER with an actual PTID

// 9.4 Temporal ordering -- PRECEDES chains
//     PRECEDES edges link consecutive Visit nodes, forming a temporal chain.
//     from_visit/to_visit: adjacent visit codes; count: how many patients have that pair.
MATCH (v1:Visit)-[:PRECEDES]->(v2:Visit)
WITH v1.viscode AS from_visit, v2.viscode AS to_visit, count(*) AS count
RETURN from_visit, to_visit, count
ORDER BY count DESC
LIMIT 20;

// 9.5 Patients with the longest follow-up
//     Finds participants with the most months since baseline.
//     Long follow-up is valuable for studying slow progression trajectories.
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)
WHERE v.months_from_baseline IS NOT NULL
WITH p.ptid AS patient, max(v.months_from_baseline) AS max_months
RETURN patient, max_months AS follow_up_months
ORDER BY max_months DESC
LIMIT 15;


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  10. GRAPH TOPOLOGY & CONNECTIVITY                                  ║
// ║  How densely connected is the knowledge graph?                      ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 10.1 Degree distribution (top hub nodes)
//      Hubs are the most connected nodes — usually patients or diagnoses
MATCH (n)
WITH n, labels(n)[0] AS label, size([(n)-[]-() | 1]) AS degree
RETURN label, n.ptid AS id, degree
ORDER BY degree DESC
LIMIT 20;

// 10.2 Average degree by node type
//     Shows how connected each node type is on average.
//     Patient nodes should have high degree (many edges to diagnoses, visits, etc.).
MATCH (n)
WITH labels(n)[0] AS label, size([(n)-[]-() | 1]) AS degree
RETURN label, count(*) AS nodes,
       round(avg(degree), 1) AS avg_degree,
       max(degree) AS max_degree
ORDER BY avg_degree DESC
LIMIT 20;

// 10.3 Isolated nodes (no relationships -- potential data quality issue)
//      Nodes with zero relationships are unreachable by graph traversal.
//      These may indicate orphaned reference data or ingestion failures.
MATCH (n)
WHERE NOT (n)--()
RETURN labels(n)[0] AS label, count(n) AS isolated_count
ORDER BY isolated_count DESC;

// 10.4 Shortest path between two patients
//      Useful for finding shared visits, diagnoses, or biomarker patterns
MATCH (p1:Patient {ptid: 'PTID_1'}), (p2:Patient {ptid: 'PTID_2'})
MATCH path = shortestPath((p1)-[*..6]-(p2))
RETURN path;
// ^ Replace PTID_1 and PTID_2 with actual patient IDs

// 10.5 Subgraph around a single patient (great for visualization)
//      Shows all direct neighbours — visualize in Neo4j Browser
MATCH (p:Patient {ptid: 'PLACEHOLDER'})-[r]->(n)
RETURN p, r, n
LIMIT 50;
// ^ Replace PLACEHOLDER with an actual PTID

// 10.6 Full patient neighborhood — all connected nodes (bidirectional)
//      Returns nodes & relationships separately so Neo4j Browser renders graph bubbles
MATCH (p:Patient {ptid: 'PLACEHOLDER'})-[r]-(n)
RETURN p, r, n
LIMIT 50;
// ^ Replace PLACEHOLDER with an actual PTID

// 10.7 Connected components -- are there disconnected clusters?
//      Compares connected vs disconnected nodes. High connectivity_pct
//      indicates a well-integrated KG with few orphan entities.
MATCH (n)
WHERE NOT (n)--()
WITH count(n) AS disconnected
MATCH (m) WHERE (m)--()
WITH disconnected, count(m) AS connected
RETURN connected, disconnected,
       round(100.0 * connected / (connected + disconnected), 1) AS connectivity_pct;


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  11. CROSS-DOMAIN QUERIES (PUTTING IT ALL TOGETHER)                 ║
// ║  Combine clinical, imaging, biomarker, and genetic data             ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 11.1 Full patient profile: demographics + diagnosis + MMSE + biomarkers
//      The quintessential cross-domain query: joins demographic, clinical,
//      cognitive, and biomarker data into a single row per patient.
//      baseline_mmse: MMSE score at the baseline visit (higher = better cognition).
//      abeta42: CSF Abeta42 concentration (lower = more amyloid pathology).
//      Note: CognitiveAssessment has visit_id (e.g. 'PTID_bl'), not visit_code.
//      We filter for baseline by matching visit_id ending with '_bl'.
//      Analyte uses Unicode: 'Aβ42' (not 'ABETA').
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
OPTIONAL MATCH (p)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
  WHERE ca.test_name = 'MMSE' AND (ca.visit_id ENDS WITH '_bl' OR ca.visit_id ENDS WITH '_sc')
OPTIONAL MATCH (p)-[:HAS_BIOMARKER]->(b:Biomarker)
  WHERE b.analyte CONTAINS 'Aβ' OR b.analyte CONTAINS 'ABETA'
WITH p, d, ca, b
RETURN p.ptid AS patient,
       p.gender AS gender,
       coalesce(d.diagnosis_code, d.diagnosis_text) AS diagnosis,
       ca.total_score AS baseline_mmse,
       round(b.value, 1) AS abeta42
ORDER BY p.ptid
LIMIT 20;

// 11.2 AD patients with low Abeta42 AND low MMSE -- confirmed pathology
//      Finds patients with both biological (A+) and clinical (impaired cognition)
//      evidence of Alzheimer's. MMSE < 24 indicates cognitive impairment.
//      Roche Elecsys Aβ42 < 1100 pg/mL indicates amyloid positivity (A+).
//      These patients have "biomarker-confirmed" AD.
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis),
      (p)-[:HAS_BIOMARKER]->(b:Biomarker),
      (p)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
WHERE d.diagnosis_code = 'AD'
  AND (b.analyte CONTAINS 'Aβ' OR b.analyte CONTAINS 'ABETA') AND b.value < 1100
  AND ca.test_name = 'MMSE' AND ca.total_score < 24
RETURN DISTINCT p.ptid AS patient,
       round(b.value, 1) AS abeta42,
       ca.total_score AS mmse_score
ORDER BY ca.total_score
LIMIT 20;

// 11.3 Patients with imaging AND biomarkers AND family history
//      Multi-modal data completeness check
MATCH (p:Patient)
OPTIONAL MATCH (p)-[:HAS_IMAGE]->(img:ImageNode) WITH p, count(img) AS images
OPTIONAL MATCH (p)-[:HAS_BIOMARKER]->(b:Biomarker) WITH p, images, count(b) AS biomarkers
OPTIONAL MATCH (p)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember) WITH p, images, biomarkers, count(fm) AS family
WHERE images > 0 AND biomarkers > 0 AND family > 0
RETURN p.ptid AS patient, images, biomarkers, family
ORDER BY images DESC
LIMIT 20;

// 11.4 Knowledge graph "depth" -- how many hops from Patient to OntologyConcept
//      Measures the path length from clinical data to ontology layer.
//      The original variable-length path query [*..4] caused memory exhaustion
//      (combinatorial explosion across ~421K nodes). This version uses explicit
//      relationship types to stay within memory limits.
//      2 hops = direct semantic mapping (Patient->Diagnosis->OntologyConcept).
// Via MAPS_TO (SNOMED, LOINC, UBERON, HPO):
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)-[:MAPS_TO]->(oc:OntologyConcept)
RETURN p.ptid AS patient, oc.label AS concept, oc.source_ontology AS ontology, 2 AS hops
LIMIT 15
UNION
// Via CLASSIFIED_AS (ICD-10):
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)-[:CLASSIFIED_AS]->(oc:OntologyConcept)
RETURN p.ptid AS patient, oc.label AS concept, oc.source_ontology AS ontology, 2 AS hops
LIMIT 15;

// 11.5 Diagnosis semantic chain: Patient -> Diagnosis -> MAPS_TO -> OntologyConcept
//      Core value of the KG upgrade -- semantic interoperability.
//      This query shows how patient diagnoses connect to standardized
//      ontology concepts (SNOMED-CT, ICD-10) via MAPS_TO edges.
//      dx: the raw diagnosis label; ontology_concept: the standardized term;
//      ontology: which vocabulary (SNOMED, ICD-10); code: the ontology code.
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)-[:MAPS_TO]->(oc:OntologyConcept)
RETURN p.ptid AS patient,
       coalesce(d.diagnosis_code, d.dx_label) AS dx,
       oc.label AS ontology_concept,
       oc.source_ontology AS ontology,
       oc.code AS code
ORDER BY p.ptid
LIMIT 25;

// 11.6 Biomarker to ontology mapping
//      Shows how biomarkers link to LOINC codes via MAPS_TO.
//      LOINC codes standardize laboratory test identifiers, enabling
//      cross-study comparability and integration with EHR systems.
//      biomarker: the analyte name; ontology_label: LOINC description;
//      loinc_code: the LOINC identifier; measurements: edge count.
MATCH (b:Biomarker)-[:MAPS_TO]->(oc:OntologyConcept)
RETURN DISTINCT b.analyte AS biomarker,
       oc.label AS ontology_label, oc.code AS loinc_code,
       count(*) AS measurements
ORDER BY measurements DESC;


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  12. DATA QUALITY & COMPLETENESS                                    ║
// ║  Identify gaps and ensure pipeline correctness                      ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 12.1 Missing key properties per node type
//      Data completeness audit for Patient nodes.
//      Each *_pct column shows what percentage of patients have that property.
//      age_at_baseline: age when first enrolled; apoe_genotype: APOE allele pair;
//      education_years: total years of formal education.
// Patient completeness
MATCH (p:Patient)
WITH count(p) AS total,
     count(p.gender) AS has_gender,
     count(p.age_at_baseline) AS has_age,
     count(p.apoe_genotype) AS has_apoe,
     count(p.education_years) AS has_education
RETURN total,
       round(100.0 * has_gender / total, 1) AS gender_pct,
       round(100.0 * has_age / total, 1) AS age_pct,
       round(100.0 * has_apoe / total, 1) AS apoe_pct,
       round(100.0 * has_education / total, 1) AS education_pct;

// 12.2 Diagnosis completeness
//      Checks what fraction of Diagnosis nodes carry SNOMED, ICD-10,
//      and a human-readable label. Gaps indicate incomplete ontology mapping.
MATCH (d:Diagnosis)
WITH count(d) AS total,
     count(d.snomed_code) AS has_snomed,
     count(d.icd10_code) AS has_icd10,
     count(coalesce(d.diagnosis_code, d.dx_label)) AS has_label
RETURN total,
       round(100.0 * has_snomed / total, 1) AS snomed_pct,
       round(100.0 * has_icd10 / total, 1) AS icd10_pct,
       round(100.0 * has_label / total, 1) AS label_pct;

// 12.3 Patients without any visit
//      Every patient should have at least a baseline visit. Non-zero = data gap.
MATCH (p:Patient)
WHERE NOT (p)-[:HAS_VISIT]->(:Visit)
RETURN count(p) AS patients_without_visits;

// 12.4 Patients without any diagnosis
//      Every ADNI participant receives a diagnosis at each visit.
//      Non-zero here indicates a pipeline ingestion issue.
MATCH (p:Patient)
WHERE NOT (p)-[:HAS_DIAGNOSIS]->(:Diagnosis)
RETURN count(p) AS patients_without_diagnosis;

// 12.5 Orphan nodes (exist but have no incoming or outgoing relationships)
//      Orphans are disconnected from the graph and cannot be reached by traversal.
//      They may indicate failed MERGE operations or leftover test data.
MATCH (n) WHERE NOT (n)--()
RETURN labels(n)[0] AS label, count(n) AS orphans
ORDER BY orphans DESC;

// 12.6 ADNI data quality check — verify no 381_S_ patients
//      Per ADNI advisory, these 78 participants must be excluded
MATCH (p:Patient) WHERE p.ptid STARTS WITH '381_S_'
RETURN count(p) AS excluded_patients_found;

// 12.7 Diagnosis source analysis -- how many diagnosis nodes per patient per visit
//      ADNI diagnoses are extracted from multiple sources (DXSUM, CDR, MMSE, BLCHANGE).
//      Each source creates a separate Diagnosis node with a unique diagnosis_id suffix.
//      This query shows how many diagnosis nodes each patient has at baseline,
//      grouped by the distinct diagnosis codes. Multiple identical codes (e.g., 6x "CN")
//      indicate multi-source extraction, NOT data errors.
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
WHERE d.visit_id ENDS WITH '_bl'
WITH p.ptid AS patient,
     collect(DISTINCT d.diagnosis_code) AS distinct_diagnoses,
     count(d) AS total_diagnosis_nodes
WHERE total_diagnosis_nodes > 1
RETURN patient, distinct_diagnoses, total_diagnosis_nodes
ORDER BY total_diagnosis_nodes DESC
LIMIT 20;

// 12.7b True diagnostic conflicts -- patients with DIFFERENT diagnoses at baseline
//       This is a real data quality concern: conflicting diagnoses at the same visit.
//       E.g., one source says "CN" and another says "MCI" for the same patient at bl.
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
WHERE d.visit_id ENDS WITH '_bl'
WITH p.ptid AS patient, collect(DISTINCT d.diagnosis_code) AS distinct_dx
WHERE size(distinct_dx) > 1
RETURN patient, distinct_dx
LIMIT 20;

// 12.8 Property key inventory -- all properties used across node types
//      Introspects one sample node per label and lists its property keys.
//      Useful for understanding the schema when documentation is unavailable.
CALL db.labels() YIELD label
CALL (label) {
  MATCH (n) WHERE label IN labels(n)
  WITH n LIMIT 1
  RETURN keys(n) AS props
}
RETURN label, props
ORDER BY label;
