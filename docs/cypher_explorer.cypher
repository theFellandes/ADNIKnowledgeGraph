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
MATCH (n) WITH count(n) AS nodes
MATCH ()-[r]->() WITH nodes, count(r) AS rels
RETURN nodes AS total_nodes, rels AS total_relationships;

// 1.2 Count nodes by label (sorted, skip empty labels)
CALL db.labels() YIELD label
CALL (label) { MATCH (n) WHERE label IN labels(n) RETURN count(n) AS cnt }
WITH label, cnt WHERE cnt > 0
RETURN label, cnt
ORDER BY cnt DESC;

// 1.3 Count relationships by type (sorted)
CALL db.relationshipTypes() YIELD relationshipType AS type
CALL (type) { MATCH ()-[r]->() WHERE type(r) = type RETURN count(r) AS cnt }
RETURN type, cnt
ORDER BY cnt DESC;

// 1.4 Visual schema — shows how node types connect (best in Neo4j Browser)
CALL db.schema.visualization();

// 1.5 Relationship patterns: which node types connect via which relationships
MATCH (a)-[r]->(b)
WITH labels(a)[0] AS source, type(r) AS relationship, labels(b)[0] AS target, count(*) AS cnt
WHERE cnt > 50
RETURN source, relationship, target, cnt
ORDER BY cnt DESC
LIMIT 40;

// 1.6 Unique constraints and indexes
SHOW CONSTRAINTS;
SHOW INDEXES;


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  2. PATIENT DEMOGRAPHICS                                            ║
// ║  Who are the 2,638 participants?                                    ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 2.1 Gender distribution
MATCH (p:Patient)
RETURN p.gender AS gender, count(p) AS count
ORDER BY count DESC;

// 2.2 Education years distribution
MATCH (p:Patient) WHERE p.education_years IS NOT NULL
RETURN p.education_years AS education_years, count(p) AS count
ORDER BY education_years;

// 2.3 Age at baseline distribution (bucketed into 5-year ranges)
MATCH (p:Patient)
WITH coalesce(p.age_at_baseline, p.age, p.AGE) AS age
WHERE age IS NOT NULL
WITH toInteger(age / 5) * 5 AS bucket
RETURN bucket AS age_range_start, (bucket + 5) AS age_range_end, count(*) AS count
ORDER BY bucket;

// 2.4 APOE genotype distribution (major Alzheimer's genetic risk factor)
//     APOE e4 carriers have significantly higher AD risk
MATCH (p:Patient)
WITH coalesce(p.apoe_genotype, p.apoe4, p.APOE4) AS apoe
WHERE apoe IS NOT NULL
RETURN apoe AS apoe_genotype, count(*) AS count
ORDER BY count DESC;

// 2.5 Sample 10 patients with their key attributes
MATCH (p:Patient)
RETURN p.ptid AS patient_id, p.gender AS gender,
       p.education_years AS education,
       coalesce(p.age_at_baseline, p.age) AS age,
       coalesce(p.apoe_genotype, p.apoe4) AS apoe
ORDER BY p.ptid
LIMIT 10;

// 2.6 Research cohort distribution (ADNI-1, ADNI-GO, ADNI-2, ADNI-3, ADNI-4)
MATCH (p:Patient)-[:BELONGS_TO]->(c:ResearchCohort)
RETURN c.name AS cohort, count(p) AS patients
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
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
WITH p, collect(DISTINCT coalesce(d.diagnosis_code, d.dx_label))[0] AS dx
RETURN dx AS diagnosis, count(DISTINCT p) AS patients
ORDER BY patients DESC;

// 3.3 Disease stage progression events
//     Shows how patients move between diagnostic stages over time
MATCH (pe:ProgressionEvent)-[:PROGRESSED_TO]->(pe2:ProgressionEvent)
WITH pe.stage AS from_stage, pe2.stage AS to_stage, count(*) AS transitions
RETURN from_stage, to_stage, transitions
ORDER BY transitions DESC
LIMIT 20;

// 3.4 Patients who converted from CN to MCI or AD (converters)
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d1:Diagnosis),
      (p)-[:HAS_DIAGNOSIS]->(d2:Diagnosis)
WHERE coalesce(d1.diagnosis_code, d1.dx_label) = 'CN'
  AND coalesce(d2.diagnosis_code, d2.dx_label) IN ['MCI', 'LMCI', 'AD']
RETURN p.ptid AS patient_id,
       coalesce(d2.diagnosis_code, d2.dx_label) AS converted_to,
       d2.visit_code AS at_visit
ORDER BY patient_id
LIMIT 25;

// 3.5 Progression patterns — how many patients follow each trajectory
MATCH (pp:ProgressionPattern)
RETURN pp.pattern AS trajectory, pp.patient_count AS patients
ORDER BY patients DESC
LIMIT 15;

// 3.6 DiseaseStage ontology nodes (reference data)
MATCH (ds:DiseaseStage)
RETURN ds.name AS stage, ds.description AS description,
       ds.snomed_code AS snomed
ORDER BY ds.name;


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

// 4.3 Cognitive decline over time — MMSE scores at each visit
MATCH (p:Patient)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
WHERE ca.test_name CONTAINS 'MMSE' AND ca.total_score IS NOT NULL
WITH ca.visit_code AS visit, ca.total_score AS score
RETURN visit,
       round(avg(score), 2) AS mean_mmse,
       count(score) AS n_assessments
ORDER BY visit
LIMIT 20;

// 4.4 A single patient's full cognitive timeline
MATCH (p:Patient {ptid: 'PLACEHOLDER'})-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
RETURN ca.test_name AS test, ca.visit_code AS visit,
       ca.total_score AS score, ca.visit_date AS date
ORDER BY ca.visit_date;
// ^ Replace PLACEHOLDER with an actual PTID from query 2.5

// 4.5 CognitiveTest reference nodes (ontology-like)
MATCH (ct:CognitiveTest)
RETURN ct.name AS test_name, ct.loinc_code AS loinc,
       ct.description AS description;

// 4.6 Multimodal assessments — combined cognitive + biomarker evaluations
MATCH (ma:MultimodalAssessment)
RETURN ma.assessment_type AS type, count(ma) AS count
ORDER BY count DESC
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
RETURN b.biomarker_name AS biomarker, count(b) AS measurements
ORDER BY measurements DESC
LIMIT 15;

// 5.2 Average biomarker values by diagnosis
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis),
      (p)-[:HAS_BIOMARKER]->(b:Biomarker)
WHERE b.value IS NOT NULL
WITH coalesce(d.diagnosis_code, d.dx_label) AS dx,
     b.biomarker_name AS marker, b.value AS val
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

// 5.4 Biomarker categories
MATCH (bc:BiomarkerCategory)<-[:BELONGS_TO_CATEGORY]-(b:Biomarker)
RETURN bc.name AS category, count(b) AS biomarker_count
ORDER BY biomarker_count DESC;

// 5.5 PET tracer types (Florbetapir, FDG, AV-1451, etc.)
MATCH (pt:PETTracer)
RETURN pt.name AS tracer, pt.target AS target_pathology
ORDER BY tracer;

// 5.6 Patients with abnormal amyloid (A+) — early AD detection
MATCH (p:Patient)-[:HAS_BIOMARKER]->(b:Biomarker)
WHERE b.biomarker_name CONTAINS 'ABETA' AND b.value < 192
RETURN p.ptid AS patient_id, b.biomarker_name AS marker,
       round(b.value, 1) AS value, b.visit_code AS visit
ORDER BY b.value
LIMIT 20;


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  6. MEDICAL IMAGING                                                 ║
// ║  MRI & PET scans stored as multi-format renderings                  ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 6.1 Total images and rendering types
MATCH (img:ImageNode)
WITH count(img) AS images
OPTIONAL MATCH (sr:SmoothRendering)
WITH images, count(sr) AS smooth
OPTIONAL MATCH (pf:PyramidFormat)
WITH images, smooth, count(pf) AS pyramid
OPTIONAL MATCH (wv:WebViewerReady)
RETURN images, smooth AS smooth_renderings,
       pyramid AS pyramid_formats, count(wv) AS web_ready;

// 6.2 Images per patient (distribution)
MATCH (p:Patient)-[:HAS_IMAGE]->(img:ImageNode)
WITH p.ptid AS patient, count(img) AS image_count
RETURN min(image_count) AS min_images,
       round(avg(image_count), 1) AS avg_images,
       max(image_count) AS max_images,
       count(patient) AS patients_with_images;

// 6.3 Image modality breakdown (MRI vs PET)
MATCH (img:ImageNode)
RETURN coalesce(img.modality, 'Unknown') AS modality, count(img) AS count
ORDER BY count DESC;

// 6.4 Sample image metadata
MATCH (img:ImageNode)
RETURN img.image_hash AS hash,
       img.modality AS modality,
       img.description AS description,
       img.format AS format
LIMIT 10;

// 6.5 Images linked to a specific patient (visual in Neo4j Browser)
MATCH path = (p:Patient)-[:HAS_IMAGE]->(img:ImageNode)
WHERE p.ptid = 'PLACEHOLDER'
RETURN path
LIMIT 25;
// ^ Replace PLACEHOLDER with an actual PTID


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  7. FAMILY HISTORY & GENETICS                                       ║
// ║  Hereditary risk factors for Alzheimer's disease                    ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 7.1 Family member counts
MATCH (fm:FamilyMember)
RETURN count(fm) AS total_family_members;

// 7.2 Family relationship types
MATCH (p:Patient)-[r]->(fm:FamilyMember)
RETURN type(r) AS relationship, count(r) AS count
ORDER BY count DESC;

// 7.3 Family risk assessments
MATCH (fr:FamilyRisk)
RETURN fr.risk_level AS risk_level, count(fr) AS patients
ORDER BY patients DESC;

// 7.4 Patients with first-degree relatives affected by dementia
MATCH (p:Patient)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember)
WHERE fm.has_dementia = true OR fm.dementia_status = 'Yes'
RETURN p.ptid AS patient, count(fm) AS affected_relatives
ORDER BY affected_relatives DESC
LIMIT 20;

// 7.5 Sibling relationships
MATCH (fm1:FamilyMember)-[:HAS_SIBLING]->(fm2:FamilyMember)
RETURN count(*) AS sibling_pairs;


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

// 8.2 MAPS_TO relationships — how clinical nodes link to ontology
MATCH (n)-[:MAPS_TO]->(oc:OntologyConcept)
WITH labels(n)[0] AS node_type, oc.source_ontology AS ontology, count(*) AS cnt
RETURN node_type, ontology, cnt
ORDER BY cnt DESC;

// 8.3 IS_A hierarchy (ontology taxonomy)
MATCH path = (child:OntologyConcept)-[:IS_A]->(parent:OntologyConcept)
RETURN child.label AS child, parent.label AS parent,
       child.source_ontology AS ontology
ORDER BY ontology, parent;

// 8.4 SNOMED coverage — which diagnoses have SNOMED codes
MATCH (d:Diagnosis) WHERE d.snomed_code IS NOT NULL
WITH count(d) AS with_snomed
MATCH (d2:Diagnosis)
WITH with_snomed, count(d2) AS total
RETURN with_snomed, total,
       round(100.0 * with_snomed / total, 1) AS snomed_coverage_pct;

// 8.5 ICD-10 codes on diagnoses
MATCH (d:Diagnosis)
WHERE d.icd10_code IS NOT NULL
RETURN DISTINCT d.icd10_code AS icd10, d.icd10_label AS label, count(d) AS count
ORDER BY count DESC;

// 8.6 LOINC codes on cognitive assessments
MATCH (ca:CognitiveAssessment) WHERE ca.loinc_code IS NOT NULL
RETURN DISTINCT ca.loinc_code AS loinc, ca.test_name AS test, count(ca) AS count
ORDER BY count DESC;

// 8.7 Brain regions (UBERON-mapped)
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
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)
WITH p.ptid AS patient, count(v) AS visit_count
RETURN min(visit_count) AS min_visits,
       round(avg(visit_count), 1) AS avg_visits,
       max(visit_count) AS max_visits;

// 9.3 Visit timeline — sequential visit chain for one patient
MATCH path = (p:Patient)-[:HAS_VISIT]->(v:Visit)
WHERE p.ptid = 'PLACEHOLDER'
RETURN v.viscode AS visit_code,
       v.visit_date AS date,
       v.months_from_baseline AS months
ORDER BY v.months_from_baseline;
// ^ Replace PLACEHOLDER with an actual PTID

// 9.4 Temporal ordering — PRECEDES chains
MATCH (v1:Visit)-[:PRECEDES]->(v2:Visit)
WITH v1.viscode AS from_visit, v2.viscode AS to_visit, count(*) AS count
RETURN from_visit, to_visit, count
ORDER BY count DESC
LIMIT 20;

// 9.5 Patients with the longest follow-up
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
MATCH (n)
WITH labels(n)[0] AS label, size([(n)-[]-() | 1]) AS degree
RETURN label, count(*) AS nodes,
       round(avg(degree), 1) AS avg_degree,
       max(degree) AS max_degree
ORDER BY avg_degree DESC
LIMIT 20;

// 10.3 Isolated nodes (no relationships — potential data quality issue)
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

// 10.7 Connected components — are there disconnected clusters?
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
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
OPTIONAL MATCH (p)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
  WHERE ca.test_name CONTAINS 'MMSE' AND ca.visit_code = 'bl'
OPTIONAL MATCH (p)-[:HAS_BIOMARKER]->(b:Biomarker)
  WHERE b.biomarker_name CONTAINS 'ABETA'
WITH p, d, ca, b
RETURN p.ptid AS patient,
       p.gender AS gender,
       coalesce(d.diagnosis_code, d.dx_label) AS diagnosis,
       ca.total_score AS baseline_mmse,
       round(b.value, 1) AS abeta42
ORDER BY p.ptid
LIMIT 20;

// 11.2 AD patients with low Abeta42 AND low MMSE — confirmed pathology
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis),
      (p)-[:HAS_BIOMARKER]->(b:Biomarker),
      (p)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
WHERE coalesce(d.diagnosis_code, d.dx_label) = 'AD'
  AND b.biomarker_name CONTAINS 'ABETA' AND b.value < 192
  AND ca.test_name CONTAINS 'MMSE' AND ca.total_score < 24
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

// 11.4 Knowledge graph "depth" — how many hops from Patient to OntologyConcept
MATCH path = (p:Patient)-[*..4]->(oc:OntologyConcept)
WITH p.ptid AS patient, oc.label AS concept,
     length(path) AS hops, oc.source_ontology AS ontology
RETURN patient, concept, ontology, hops
ORDER BY hops, patient
LIMIT 30;

// 11.5 Diagnosis support chain: Patient → Diagnosis → ClinicalFinding → OntologyConcept
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
              -[:IS_CLINICAL_FINDING]->(cf:ClinicalFinding)
OPTIONAL MATCH (d)-[:MAPS_TO]->(oc:OntologyConcept)
RETURN p.ptid AS patient,
       coalesce(d.diagnosis_code, d.dx_label) AS dx,
       cf.finding_type AS finding,
       oc.label AS ontology_concept,
       oc.source_ontology AS ontology
LIMIT 25;

// 11.6 Biomarker pathway associations
MATCH (b:Biomarker)-[:INDICATES_PATHWAY]->(bp:BiologicalPathway)
RETURN DISTINCT b.biomarker_name AS biomarker,
       bp.name AS pathway, count(*) AS associations
ORDER BY associations DESC;


// ╔══════════════════════════════════════════════════════════════════════╗
// ║  12. DATA QUALITY & COMPLETENESS                                    ║
// ║  Identify gaps and ensure pipeline correctness                      ║
// ╚══════════════════════════════════════════════════════════════════════╝

// 12.1 Missing key properties per node type
// Patient completeness
MATCH (p:Patient)
WITH count(p) AS total,
     count(p.gender) AS has_gender,
     count(coalesce(p.age_at_baseline, p.age)) AS has_age,
     count(coalesce(p.apoe_genotype, p.apoe4)) AS has_apoe,
     count(p.education_years) AS has_education
RETURN total,
       round(100.0 * has_gender / total, 1) AS gender_pct,
       round(100.0 * has_age / total, 1) AS age_pct,
       round(100.0 * has_apoe / total, 1) AS apoe_pct,
       round(100.0 * has_education / total, 1) AS education_pct;

// 12.2 Diagnosis completeness
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
MATCH (p:Patient)
WHERE NOT (p)-[:HAS_VISIT]->(:Visit)
RETURN count(p) AS patients_without_visits;

// 12.4 Patients without any diagnosis
MATCH (p:Patient)
WHERE NOT (p)-[:HAS_DIAGNOSIS]->(:Diagnosis)
RETURN count(p) AS patients_without_diagnosis;

// 12.5 Orphan nodes (exist but have no incoming or outgoing relationships)
MATCH (n) WHERE NOT (n)--()
RETURN labels(n)[0] AS label, count(n) AS orphans
ORDER BY orphans DESC;

// 12.6 ADNI data quality check — verify no 381_S_ patients
//      Per ADNI advisory, these 78 participants must be excluded
MATCH (p:Patient) WHERE p.ptid STARTS WITH '381_S_'
RETURN count(p) AS excluded_patients_found;

// 12.7 Duplicate detection — patients with multiple baseline diagnoses
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
WHERE d.visit_code = 'bl'
WITH p.ptid AS patient, collect(coalesce(d.diagnosis_code, d.dx_label)) AS diagnoses
WHERE size(diagnoses) > 1
RETURN patient, diagnoses
LIMIT 20;

// 12.8 Property key inventory — all properties used across node types
CALL db.labels() YIELD label
CALL (label) {
  MATCH (n) WHERE label IN labels(n)
  WITH n LIMIT 1
  RETURN keys(n) AS props
}
RETURN label, props
ORDER BY label;
