// Synthetic mini-KG fixture for metric / validity tests.
//
// Designed so the validity rubric (default thresholds) PASSES on this graph,
// modulo the deliberately-poisoned variants documented at the bottom of the
// file. Tests load the base block, then optionally apply mutations to flip
// individual assertions to FAIL.
//
// Cardinality summary (base block):
//   :Patient                     4   (one with forbidden 381_S_ prefix in the variant)
//   :Visit                       4
//   :Diagnosis                   4   (snomed_code coverage 4/4 = 1.0)
//   :CognitiveAssessment         4   (loinc_code coverage 4/4 = 1.0)
//   :Biomarker (CSF)             3   (loinc_code coverage 3/3 = 1.0)
//   :BrainRegion                 3   (uberon_code coverage 3/3 = 1.0)
//   :OntologyConcept             7   (SNOMED, LOINC, UBERON, HPO, ICD-10)
//   relationships
//     HAS_VISIT                  4   (uri set)
//     HAS_DIAGNOSIS              4   (uri set)
//     HAS_ASSESSMENT             4   (uri set)
//     HAS_BIOMARKER              3   (uri set)
//     HAS_REGION                 3   (uri set)
//     MAPS_TO                    14  (uri set)
//     IS_A                       2   (uri set, between OntologyConcepts)
//     CLASSIFIED_AS              4   (uri set)

// =====================================================================
// Patients
// =====================================================================
MERGE (p1:Patient {ptid: "002_S_0413"}) SET p1.rdf_type = "ncit:C16960";
MERGE (p2:Patient {ptid: "003_S_1059"}) SET p2.rdf_type = "ncit:C16960";
MERGE (p3:Patient {ptid: "011_S_0023"}) SET p3.rdf_type = "ncit:C16960";
MERGE (p4:Patient {ptid: "067_S_0019"}) SET p4.rdf_type = "ncit:C16960";

// =====================================================================
// Visits
// =====================================================================
MERGE (v1:Visit {visit_id: "002_S_0413_bl",  viscode: "bl"})  SET v1.rdf_type = "ncit:C159705";
MERGE (v2:Visit {visit_id: "003_S_1059_m06", viscode: "m06"}) SET v2.rdf_type = "ncit:C159705";
MERGE (v3:Visit {visit_id: "011_S_0023_m12", viscode: "m12"}) SET v3.rdf_type = "ncit:C159705";
MERGE (v4:Visit {visit_id: "067_S_0019_y3",  viscode: "y3"})  SET v4.rdf_type = "ncit:C159705";

// =====================================================================
// Diagnoses (snomed_code on every node)
// =====================================================================
MERGE (d1:Diagnosis {diagnosis_id: "dx_p1_bl"})
  SET d1.snomed_code = "26929004", d1.snomed_label = "Alzheimer's disease",
      d1.icd10_code = "G30.9", d1.mondo_code = "MONDO:0004975",
      d1.rdf_type  = "snomed:26929004";
MERGE (d2:Diagnosis {diagnosis_id: "dx_p2_m06"})
  SET d2.snomed_code = "230267008", d2.snomed_label = "Mild cognitive impairment",
      d2.icd10_code = "F06.7";
MERGE (d3:Diagnosis {diagnosis_id: "dx_p3_m12"})
  SET d3.snomed_code = "17226007",  d3.snomed_label = "Cognitively normal",
      d3.icd10_code = "Z03.89";
MERGE (d4:Diagnosis {diagnosis_id: "dx_p4_y3"})
  SET d4.snomed_code = "26929004", d4.snomed_label = "Alzheimer's disease",
      d4.icd10_code = "G30.9";

// =====================================================================
// Cognitive assessments (loinc_code on every node)
// =====================================================================
MERGE (c1:CognitiveAssessment {assessment_id: "mmse_p1_bl"})
  SET c1.test_name = "MMSE", c1.score = 24,
      c1.loinc_code = "72172-0", c1.loinc_label = "Mini-Mental State Examination";
MERGE (c2:CognitiveAssessment {assessment_id: "cdr_p2_m06"})
  SET c2.test_name = "CDR",  c2.score = 0.5,
      c2.loinc_code = "72133-2", c2.loinc_label = "Clinical Dementia Rating";
MERGE (c3:CognitiveAssessment {assessment_id: "moca_p3_m12"})
  SET c3.test_name = "MoCA", c3.score = 27,
      c3.loinc_code = "72172-0", c3.loinc_label = "Montreal Cognitive Assessment";
MERGE (c4:CognitiveAssessment {assessment_id: "adas_p4_y3"})
  SET c4.test_name = "ADAS-Cog", c4.score = 32,
      c4.loinc_code = "72133-2", c4.loinc_label = "ADAS-Cog";

// =====================================================================
// Biomarkers — CSF only carry LOINC codes per spec (A2 filter)
// =====================================================================
MERGE (b1:Biomarker {biomarker_id: "abeta42_p1_bl"})
  SET b1.biomarker_type = "CSF_ABETA42", b1.value = 450.0,
      b1.loinc_code = "33203-1", b1.loinc_label = "Amyloid beta 42 [Mass/volume]";
MERGE (b2:Biomarker {biomarker_id: "tau_p2_m06"})
  SET b2.biomarker_type = "CSF_TAU", b2.value = 350.0,
      b2.loinc_code = "33204-9";
MERGE (b3:Biomarker {biomarker_id: "ptau_p3_m12"})
  SET b3.biomarker_type = "CSF_PTAU", b3.value = 30.0,
      b3.loinc_code = "33205-6";

// =====================================================================
// Brain regions
// =====================================================================
MERGE (br1:BrainRegion {region_name: "hippocampus"})
  SET br1.uberon_code = "0002421", br1.uberon_label = "hippocampus formation";
MERGE (br2:BrainRegion {region_name: "entorhinal_cortex"})
  SET br2.uberon_code = "0002728", br2.uberon_label = "entorhinal cortex";
MERGE (br3:BrainRegion {region_name: "amygdala"})
  SET br3.uberon_code = "0001876", br3.uberon_label = "amygdala";

// =====================================================================
// Ontology concept layer (covers all five required sources)
// =====================================================================
MERGE (oc_snomed_ad:OntologyConcept {uri: "snomed:26929004"})
  SET oc_snomed_ad.code = "26929004", oc_snomed_ad.label = "Alzheimer's disease",
      oc_snomed_ad.source_ontology = "SNOMED-CT";
MERGE (oc_snomed_mci:OntologyConcept {uri: "snomed:230267008"})
  SET oc_snomed_mci.code = "230267008", oc_snomed_mci.label = "Mild cognitive impairment",
      oc_snomed_mci.source_ontology = "SNOMED-CT";
MERGE (oc_loinc_mmse:OntologyConcept {uri: "loinc:72172-0"})
  SET oc_loinc_mmse.code = "72172-0", oc_loinc_mmse.label = "MMSE",
      oc_loinc_mmse.source_ontology = "LOINC";
MERGE (oc_loinc_cdr:OntologyConcept {uri: "loinc:72133-2"})
  SET oc_loinc_cdr.code = "72133-2", oc_loinc_cdr.label = "CDR",
      oc_loinc_cdr.source_ontology = "LOINC";
MERGE (oc_uberon_hippo:OntologyConcept {uri: "uberon:0002421"})
  SET oc_uberon_hippo.code = "0002421", oc_uberon_hippo.label = "hippocampus",
      oc_uberon_hippo.source_ontology = "UBERON";
MERGE (oc_hpo_anxiety:OntologyConcept {uri: "hp:0000739"})
  SET oc_hpo_anxiety.code = "HP:0000739", oc_hpo_anxiety.label = "Anxiety",
      oc_hpo_anxiety.source_ontology = "HPO";
MERGE (oc_icd10_g30:OntologyConcept {uri: "icd10:G30"})
  SET oc_icd10_g30.code = "G30", oc_icd10_g30.label = "Alzheimer disease",
      oc_icd10_g30.source_ontology = "ICD-10",
      oc_icd10_g30.is_hierarchy_root = true;

// =====================================================================
// Patient → Visit
// =====================================================================
MATCH (p:Patient {ptid:"002_S_0413"}), (v:Visit {visit_id:"002_S_0413_bl"})
MERGE (p)-[r:HAS_VISIT]->(v)  SET r.uri = "ro:0000056";
MATCH (p:Patient {ptid:"003_S_1059"}), (v:Visit {visit_id:"003_S_1059_m06"})
MERGE (p)-[r:HAS_VISIT]->(v)  SET r.uri = "ro:0000056";
MATCH (p:Patient {ptid:"011_S_0023"}), (v:Visit {visit_id:"011_S_0023_m12"})
MERGE (p)-[r:HAS_VISIT]->(v)  SET r.uri = "ro:0000056";
MATCH (p:Patient {ptid:"067_S_0019"}), (v:Visit {visit_id:"067_S_0019_y3"})
MERGE (p)-[r:HAS_VISIT]->(v)  SET r.uri = "ro:0000056";

// =====================================================================
// Visit → Diagnosis / Assessment / Biomarker
// =====================================================================
MATCH (v:Visit {visit_id:"002_S_0413_bl"}),  (d:Diagnosis {diagnosis_id:"dx_p1_bl"})
MERGE (v)-[r:HAS_DIAGNOSIS]->(d) SET r.uri = "ro:0000059";
MATCH (v:Visit {visit_id:"003_S_1059_m06"}), (d:Diagnosis {diagnosis_id:"dx_p2_m06"})
MERGE (v)-[r:HAS_DIAGNOSIS]->(d) SET r.uri = "ro:0000059";
MATCH (v:Visit {visit_id:"011_S_0023_m12"}), (d:Diagnosis {diagnosis_id:"dx_p3_m12"})
MERGE (v)-[r:HAS_DIAGNOSIS]->(d) SET r.uri = "ro:0000059";
MATCH (v:Visit {visit_id:"067_S_0019_y3"}),  (d:Diagnosis {diagnosis_id:"dx_p4_y3"})
MERGE (v)-[r:HAS_DIAGNOSIS]->(d) SET r.uri = "ro:0000059";

MATCH (v:Visit {visit_id:"002_S_0413_bl"}),  (c:CognitiveAssessment {assessment_id:"mmse_p1_bl"})
MERGE (v)-[r:HAS_ASSESSMENT]->(c) SET r.uri = "ro:0000056";
MATCH (v:Visit {visit_id:"003_S_1059_m06"}), (c:CognitiveAssessment {assessment_id:"cdr_p2_m06"})
MERGE (v)-[r:HAS_ASSESSMENT]->(c) SET r.uri = "ro:0000056";
MATCH (v:Visit {visit_id:"011_S_0023_m12"}), (c:CognitiveAssessment {assessment_id:"moca_p3_m12"})
MERGE (v)-[r:HAS_ASSESSMENT]->(c) SET r.uri = "ro:0000056";
MATCH (v:Visit {visit_id:"067_S_0019_y3"}),  (c:CognitiveAssessment {assessment_id:"adas_p4_y3"})
MERGE (v)-[r:HAS_ASSESSMENT]->(c) SET r.uri = "ro:0000056";

MATCH (v:Visit {visit_id:"002_S_0413_bl"}),  (b:Biomarker {biomarker_id:"abeta42_p1_bl"})
MERGE (v)-[r:HAS_BIOMARKER]->(b) SET r.uri = "ro:0000056";
MATCH (v:Visit {visit_id:"003_S_1059_m06"}), (b:Biomarker {biomarker_id:"tau_p2_m06"})
MERGE (v)-[r:HAS_BIOMARKER]->(b) SET r.uri = "ro:0000056";
MATCH (v:Visit {visit_id:"011_S_0023_m12"}), (b:Biomarker {biomarker_id:"ptau_p3_m12"})
MERGE (v)-[r:HAS_BIOMARKER]->(b) SET r.uri = "ro:0000056";

// =====================================================================
// Brain region attachments (CognitiveAssessment HAS_REGION BrainRegion)
// =====================================================================
MATCH (c:CognitiveAssessment {assessment_id:"mmse_p1_bl"}), (br:BrainRegion {region_name:"hippocampus"})
MERGE (c)-[r:HAS_REGION]->(br) SET r.uri = "ro:0000051";
MATCH (c:CognitiveAssessment {assessment_id:"cdr_p2_m06"}), (br:BrainRegion {region_name:"entorhinal_cortex"})
MERGE (c)-[r:HAS_REGION]->(br) SET r.uri = "ro:0000051";
MATCH (c:CognitiveAssessment {assessment_id:"moca_p3_m12"}), (br:BrainRegion {region_name:"amygdala"})
MERGE (c)-[r:HAS_REGION]->(br) SET r.uri = "ro:0000051";

// =====================================================================
// MAPS_TO edges (data → OntologyConcept) — uri = skos:exactMatch
// =====================================================================
MATCH (d:Diagnosis {diagnosis_id:"dx_p1_bl"}), (oc:OntologyConcept {uri:"snomed:26929004"})
MERGE (d)-[r:MAPS_TO]->(oc) SET r.uri = "skos:exactMatch";
MATCH (d:Diagnosis {diagnosis_id:"dx_p2_m06"}), (oc:OntologyConcept {uri:"snomed:230267008"})
MERGE (d)-[r:MAPS_TO]->(oc) SET r.uri = "skos:exactMatch";
MATCH (d:Diagnosis {diagnosis_id:"dx_p3_m12"}), (oc:OntologyConcept {uri:"snomed:230267008"})
MERGE (d)-[r:MAPS_TO]->(oc) SET r.uri = "skos:closeMatch";
MATCH (d:Diagnosis {diagnosis_id:"dx_p4_y3"}),  (oc:OntologyConcept {uri:"snomed:26929004"})
MERGE (d)-[r:MAPS_TO]->(oc) SET r.uri = "skos:exactMatch";

MATCH (c:CognitiveAssessment {assessment_id:"mmse_p1_bl"}), (oc:OntologyConcept {uri:"loinc:72172-0"})
MERGE (c)-[r:MAPS_TO]->(oc) SET r.uri = "skos:exactMatch";
MATCH (c:CognitiveAssessment {assessment_id:"cdr_p2_m06"}), (oc:OntologyConcept {uri:"loinc:72133-2"})
MERGE (c)-[r:MAPS_TO]->(oc) SET r.uri = "skos:exactMatch";
MATCH (c:CognitiveAssessment {assessment_id:"moca_p3_m12"}), (oc:OntologyConcept {uri:"loinc:72172-0"})
MERGE (c)-[r:MAPS_TO]->(oc) SET r.uri = "skos:exactMatch";
MATCH (c:CognitiveAssessment {assessment_id:"adas_p4_y3"}), (oc:OntologyConcept {uri:"loinc:72133-2"})
MERGE (c)-[r:MAPS_TO]->(oc) SET r.uri = "skos:exactMatch";

MATCH (b:Biomarker {biomarker_id:"abeta42_p1_bl"}), (oc:OntologyConcept {uri:"loinc:72172-0"})
MERGE (b)-[r:MAPS_TO]->(oc) SET r.uri = "skos:exactMatch";
MATCH (b:Biomarker {biomarker_id:"tau_p2_m06"}), (oc:OntologyConcept {uri:"loinc:72133-2"})
MERGE (b)-[r:MAPS_TO]->(oc) SET r.uri = "skos:exactMatch";
MATCH (b:Biomarker {biomarker_id:"ptau_p3_m12"}), (oc:OntologyConcept {uri:"loinc:72133-2"})
MERGE (b)-[r:MAPS_TO]->(oc) SET r.uri = "skos:exactMatch";

MATCH (br:BrainRegion {region_name:"hippocampus"}), (oc:OntologyConcept {uri:"uberon:0002421"})
MERGE (br)-[r:MAPS_TO]->(oc) SET r.uri = "skos:exactMatch";

// HPO concept reachable via a synthetic family-symptom edge (keeps it non-orphan)
MATCH (c:CognitiveAssessment {assessment_id:"mmse_p1_bl"}), (oc:OntologyConcept {uri:"hp:0000739"})
MERGE (c)-[r:MAPS_TO]->(oc) SET r.uri = "skos:closeMatch";

// =====================================================================
// IS_A hierarchy (OntologyConcept → OntologyConcept) — uri = rdfs:subClassOf
// =====================================================================
MATCH (child:OntologyConcept {uri:"snomed:230267008"}), (parent:OntologyConcept {uri:"snomed:26929004"})
MERGE (child)-[r:IS_A]->(parent) SET r.uri = "rdfs:subClassOf";
MATCH (child:OntologyConcept {uri:"loinc:72133-2"}), (parent:OntologyConcept {uri:"loinc:72172-0"})
MERGE (child)-[r:IS_A]->(parent) SET r.uri = "rdfs:subClassOf";

// =====================================================================
// CLASSIFIED_AS — Diagnosis → ICD-10 OntologyConcept
// =====================================================================
MATCH (d:Diagnosis {diagnosis_id:"dx_p1_bl"}),  (oc:OntologyConcept {uri:"icd10:G30"})
MERGE (d)-[r:CLASSIFIED_AS]->(oc) SET r.uri = "skos:closeMatch";
MATCH (d:Diagnosis {diagnosis_id:"dx_p2_m06"}), (oc:OntologyConcept {uri:"icd10:G30"})
MERGE (d)-[r:CLASSIFIED_AS]->(oc) SET r.uri = "skos:closeMatch";
MATCH (d:Diagnosis {diagnosis_id:"dx_p3_m12"}), (oc:OntologyConcept {uri:"icd10:G30"})
MERGE (d)-[r:CLASSIFIED_AS]->(oc) SET r.uri = "skos:closeMatch";
MATCH (d:Diagnosis {diagnosis_id:"dx_p4_y3"}),  (oc:OntologyConcept {uri:"icd10:G30"})
MERGE (d)-[r:CLASSIFIED_AS]->(oc) SET r.uri = "skos:closeMatch";

// =====================================================================
// Mutations (apply individually in tests to flip a single assertion)
// ---------------------------------------------------------------------
// MUTATION-A2-DIAGNOSIS-MISSING-SNOMED:
//   MATCH (d:Diagnosis {diagnosis_id:"dx_p3_m12"}) REMOVE d.snomed_code;
//
// MUTATION-A3-DROP-HPO:
//   MATCH (oc:OntologyConcept {uri:"hp:0000739"}) DETACH DELETE oc;
//
// MUTATION-A4-MAPS_TO-NO-URI:
//   MATCH (d:Diagnosis {diagnosis_id:"dx_p1_bl"})-[r:MAPS_TO]->() REMOVE r.uri;
//
// MUTATION-A6-ORPHAN-CONCEPT:
//   MERGE (orphan:OntologyConcept {uri:"snomed:OOPS"})
//     SET orphan.code = "OOPS", orphan.source_ontology = "SNOMED-CT";
//
// MUTATION-A7-FORBIDDEN-PATIENT:
//   MERGE (p:Patient {ptid:"381_S_0001"});
// =====================================================================
