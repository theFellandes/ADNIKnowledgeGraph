# ADNI Knowledge Graph Query Documentation

Generated: 2025-08-24 14:05:07

## Query Summary

| ID | Query Name | Complexity | Expected DB Hits | Index Usage |
|---|---|---|---|---|
| Q1 | Q1_patient_lookup | simple | 2 | NodeUniqueIndexSeek on Patient.ptid |
| Q2 | Q2_count_diagnoses | simple | 25,946 | NodeByLabelScan on Diagnosis |
| Q3 | Q3_count_patients | simple | 2,638 | NodeByLabelScan on Patient |
| Q4 | Q4_patient_visits | moderate | 16 | NodeUniqueIndexSeek + Expand |
| Q5 | Q5_cognitive_scores | moderate | 9,280 | NodeByLabelScan + Filter |
| Q6 | Q6_biomarkers_by_type | moderate | 5,000 | NodeByLabelScan + Filter |
| Q7 | Q7_diagnosis_progression | complex | 4,400 | Multiple NodeByLabelScan + Join |
| Q8 | Q8_cognitive_trajectories | complex | 15,000 | NodeByLabelScan + Aggregation |
| Q9 | Q9_atn_profile_analysis | research | 28,000 | NodeByLabelScan + Optional Match |
| Q10 | Q10_multimodal_integration | research | 35,000 | Multiple Optional Matches |
| Q11 | Q11_biomarker_correlations | analytical | 50,000 | Self-join with aggregations |
| Q12 | Q12_temporal_network | analytical | 75,000 | Variable-length path traversal |

## Detailed Query Definitions


### SIMPLE QUERIES

#### Q1_patient_lookup

**Description:** Single patient lookup by ID using index

**Expected DB Hits:** 2

**Index Usage:** `NodeUniqueIndexSeek on Patient.ptid`

**Query:**
```cypher
MATCH (p:Patient {ptid: $patient_id}) 
            RETURN p.ptid, p.age, p.gender, p.education_years
```

---

#### Q2_count_diagnoses

**Description:** Count all diagnosis nodes

**Expected DB Hits:** 25,946

**Index Usage:** `NodeByLabelScan on Diagnosis`

**Query:**
```cypher
MATCH (d:Diagnosis) 
            RETURN count(d) as diagnosis_count
```

---

#### Q3_count_patients

**Description:** Count all patient nodes

**Expected DB Hits:** 2,638

**Index Usage:** `NodeByLabelScan on Patient`

**Query:**
```cypher
MATCH (p:Patient) 
            RETURN count(p) as patient_count
```

---


### MODERATE QUERIES

#### Q4_patient_visits

**Description:** Get all visits for a specific patient

**Expected DB Hits:** 16

**Index Usage:** `NodeUniqueIndexSeek + Expand`

**Query:**
```cypher
MATCH (p:Patient {ptid: $patient_id})-[:HAS_VISIT]->(v:Visit)
            RETURN p.ptid, v.viscode, v.months_from_baseline, v.visit_date
            ORDER BY v.months_from_baseline
```

---

#### Q5_cognitive_scores

**Description:** Find cognitive assessments by test type

**Expected DB Hits:** 9,280

**Index Usage:** `NodeByLabelScan + Filter`

**Query:**
```cypher
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
            WHERE ca.test_name = $test_name
            RETURN p.ptid, v.months_from_baseline, ca.total_score, ca.test_date
            LIMIT 100
```

---

#### Q6_biomarkers_by_type

**Description:** Find biomarkers by type

**Expected DB Hits:** 5,000

**Index Usage:** `NodeByLabelScan + Filter`

**Query:**
```cypher
MATCH (p:Patient)-[:HAS_BIOMARKER]->(b:Biomarker)
            WHERE b.biomarker_type = $biomarker_type
            RETURN p.ptid, b.analyte, b.value, b.units
            LIMIT 100
```

---


### COMPLEX QUERIES

#### Q7_diagnosis_progression

**Description:** Analyze diagnosis changes over time

**Expected DB Hits:** 4,400

**Index Usage:** `Multiple NodeByLabelScan + Join`

**Query:**
```cypher
MATCH (p:Patient)-[:HAS_VISIT]->(v1:Visit)-[:RESULTED_IN]->(d1:Diagnosis)
            MATCH (p)-[:HAS_VISIT]->(v2:Visit)-[:RESULTED_IN]->(d2:Diagnosis)
            WHERE v1.months_from_baseline < v2.months_from_baseline
              AND d1.diagnosis_code <> d2.diagnosis_code
            WITH p, d1, d2, v1, v2
            ORDER BY p.ptid, v1.months_from_baseline
            RETURN p.ptid as patient_id,
                   d1.diagnosis_code as initial_diagnosis,
                   d2.diagnosis_code as final_diagnosis,
                   v1.months_from_baseline as initial_month,
                   v2.months_from_baseline as final_month,
                   v2.months_from_baseline - v1.months_from_baseline as progression_months
            LIMIT 50
```

---

#### Q8_cognitive_trajectories

**Description:** Track MMSE scores over time for patients

**Expected DB Hits:** 15,000

**Index Usage:** `NodeByLabelScan + Aggregation`

**Query:**
```cypher
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
            WHERE ca.test_name = 'MMSE'
            WITH p.ptid as patient,
                 v.months_from_baseline as months,
                 ca.total_score as score
            ORDER BY patient, months
            WITH patient, collect({months: months, score: score}) as trajectory
            WHERE size(trajectory) >= 3
            RETURN patient, trajectory, size(trajectory) as assessment_count
            LIMIT 10
```

---


### RESEARCH QUERIES

#### Q9_atn_profile_analysis

**Description:** Analyze ATN biomarker profiles with diagnosis correlation

**Expected DB Hits:** 28,000

**Index Usage:** `NodeByLabelScan + Optional Match`

**Query:**
```cypher
MATCH (p:Patient)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
            OPTIONAL MATCH (p)-[:HAS_VISIT]->(v:Visit)-[:RESULTED_IN]->(d:Diagnosis)
            WITH atn.profile as atn_profile,
                 collect(DISTINCT d.diagnosis_code) as diagnoses,
                 count(DISTINCT p) as patient_count
            RETURN atn_profile, 
                   patient_count, 
                   diagnoses,
                   size(diagnoses) as diagnosis_variety
            ORDER BY patient_count DESC
```

---

#### Q10_multimodal_integration

**Description:** Integrate cognitive, biomarker, and diagnosis data

**Expected DB Hits:** 35,000

**Index Usage:** `Multiple Optional Matches`

**Query:**
```cypher
MATCH (p:Patient)
            OPTIONAL MATCH (p)-[:UNDERWENT_ASSESSMENT]->(ca:CognitiveAssessment)
            OPTIONAL MATCH (p)-[:HAS_BIOMARKER]->(b:Biomarker)
            OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
            WITH p.ptid as patient_id,
                 count(DISTINCT ca) as cognitive_count,
                 count(DISTINCT b) as biomarker_count,
                 count(DISTINCT d) as diagnosis_count,
                 collect(DISTINCT ca.test_name) as cognitive_tests,
                 collect(DISTINCT b.analyte) as biomarkers,
                 collect(DISTINCT d.diagnosis_code) as diagnoses
            WHERE (cognitive_count + biomarker_count + diagnosis_count) > 0
            RETURN patient_id, 
                   cognitive_count, 
                   biomarker_count, 
                   diagnosis_count,
                   cognitive_tests,
                   biomarkers,
                   diagnoses
            ORDER BY (cognitive_count + biomarker_count + diagnosis_count) DESC
            LIMIT 20
```

---


### ANALYTICAL QUERIES

#### Q11_biomarker_correlations

**Description:** Complex biomarker correlation analysis

**Expected DB Hits:** 50,000

**Index Usage:** `Self-join with aggregations`

**Query:**
```cypher
MATCH (p:Patient)-[:HAS_BIOMARKER]->(b1:Biomarker {biomarker_type: 'CSF'})
            MATCH (p)-[:HAS_BIOMARKER]->(b2:Biomarker {biomarker_type: 'CSF'})
            WHERE b1.analyte < b2.analyte 
              AND b1.visit_code = b2.visit_code
            WITH b1.analyte as biomarker1,
                 b2.analyte as biomarker2,
                 count(*) as pair_count,
                 avg(b1.value) as avg_value1,
                 avg(b2.value) as avg_value2,
                 stdev(b1.value) as std_value1,
                 stdev(b2.value) as std_value2,
                 min(b1.value) as min_value1,
                 max(b1.value) as max_value1
            WHERE pair_count >= 10
            RETURN biomarker1, biomarker2, pair_count,
                   round(avg_value1, 2) as avg1,
                   round(avg_value2, 2) as avg2,
                   round(std_value1, 2) as std1,
                   round(std_value2, 2) as std2
            ORDER BY pair_count DESC
```

---

#### Q12_temporal_network

**Description:** Analyze visit paths and temporal patterns

**Expected DB Hits:** 75,000

**Index Usage:** `Variable-length path traversal`

**Query:**
```cypher
MATCH path = (p:Patient)-[:HAS_VISIT]->(v1:Visit)-[:FOLLOWED_BY*1..3]->(v2:Visit)
            WHERE v1.months_from_baseline = 0
            WITH p, 
                 length(path) as path_length, 
                 v2.months_from_baseline as final_month,
                 nodes(path) as visit_sequence
            RETURN avg(path_length) as avg_path_length,
                   max(path_length) as max_path_length,
                   min(path_length) as min_path_length,
                   avg(final_month) as avg_duration,
                   stdev(final_month) as std_duration,
                   count(DISTINCT p) as patient_count
```

---

