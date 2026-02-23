# ADNI Knowledge Graph Pipeline

## 🧠 Overview

The ADNI Knowledge Graph Pipeline transforms Alzheimer's Disease Neuroimaging Initiative (ADNI) data into a comprehensive knowledge graph using Neo4j and Elasticsearch. This system creates a queryable, interconnected representation of patient data, imaging studies, biomarkers, cognitive assessments, and disease progression patterns.

## 📊 Architecture

### Data Flow
```
ADNI Raw Data (CSV/DICOM)
    ↓
Data Extraction & Validation
    ↓
Entity Creation (Patients, Visits, Images)
    ↓
Clinical Data Integration
    ↓
Relationship Mapping
    ↓
Knowledge Graph Enhancement
    ↓
Neo4j Graph Database + Elasticsearch Index
```

### Technology Stack
- **Graph Database**: Neo4j 5.x
- **Search Engine**: Elasticsearch 9.x
- **Cache Layer**: Redis 7.x
- **Processing**: Python 3.9+
- **Image Processing**: PyDICOM, Pillow
- **Orchestration**: Docker Compose

## 🚀 Installation

### Prerequisites
```bash
# System requirements
- Python 3.9+
- Docker & Docker Compose
- 16GB+ RAM
- 100GB+ free disk space
```

### Setup Steps

1. **Clone Repository**
```bash
git clone https://github.com/theFellandes/ADNIKnowledgeGraph
cd ADNIKnowledgeGraph
```

2. **Install Dependencies**
```bash
pip install -r requirements.txt
```

3. **Start Infrastructure**
```bash
docker-compose up -d
```

4. **Configure Environment**
```bash
cp .env.example .env
# Edit .env with your credentials
```

5. **Prepare ADNI Data**
```bash
# Place ADNI data in inputs/
mkdir -p inputs/Tables
mkdir -p inputs/MRI
mkdir -p inputs/PET
# Copy your ADNI CSV files to inputs/Tables/
```

## 📁 Data Structure

### Input Data Organization
```
inputs/
├── Tables/                 # ADNI CSV tables
│   ├── DXSUM.csv          # Diagnoses
│   ├── PTDEMOG.csv        # Demographics
│   ├── MMSE.csv           # Cognitive scores
│   ├── UPENNBIOMK*.csv    # Biomarkers
│   └── ...
├── MRI/                   # MRI DICOM files
│   └── patient_folders/
└── PET/                   # PET DICOM files
    └── patient_folders/
```

### Critical ADNI Tables

#### Essential Tables (Must Have)
- **DXSUM**: Clinical diagnoses (CN/MCI/AD)
- **PTDEMOG**: Patient demographics
- **REGISTRY**: Study enrollment data
- **VISITS**: Visit scheduling and tracking

#### Cognitive Assessment Tables
- **MMSE**: Mini-Mental State Examination
- **CDR**: Clinical Dementia Rating
- **ADAS**: Alzheimer's Disease Assessment Scale
- **MOCA**: Montreal Cognitive Assessment
- **FAQ**: Functional Activities Questionnaire

#### Biomarker Tables
- **UPENNBIOMK_MASTER**: CSF biomarker master file
- **UPENNBIOMK_ROCHE_ELECSYS**: Aβ42, Tau, p-Tau measurements
- **APOERES**: APOE genotype data

#### Imaging Tables
- **MRILIST**: MRI scan inventory
- **PETLIST**: PET scan inventory
- **UCBERKELEYAV45**: Amyloid PET data
- **UCBERKELEYAV1451**: Tau PET data
- **UCSFFSX**: FreeSurfer volumes

#### Family History Tables
- **FAMXHPAR**: Parental dementia history
- **FAMXHSIB**: Sibling dementia history
- **FHQ**: Family history questionnaire

## 🔧 Pipeline Configuration

### Configuration File (updated_config.yaml)
```yaml
# Operation Modes
clear_database: false      # Clear all data before loading
incremental: true          # Add to existing data

# Data Sources
neo4j_uri: "bolt://localhost:7687"
neo4j_user: "neo4j"
neo4j_password: "your_password"

# Processing Options
max_workers: 8
batch_size: 1000

# Feature Flags
run_database_setup: true
run_table_loading: true
run_patient_creation: true
run_family_extraction: true
run_image_processing: true
run_findings_extraction: true
run_batch_insertion: true
run_relationship_creation: true
run_knowledge_enhancement: true
run_query_execution: true
```

## 🏃 Running the Pipeline

### Full Pipeline Execution
```bash
python pipeline.py --config updated_config.yaml --neo4j-password your_password
```

### Incremental Updates
```bash
python pipeline.py --config updated_config.yaml --incremental --neo4j-password your_password
```

### Clear and Rebuild
```bash
python pipeline.py --config updated_config.yaml --clear-database --neo4j-password your_password
```

### Individual Steps
```bash
# Run specific steps
python steps/step1_database_setup.py --neo4j-password your_password
python steps/step2_load_tables.py
python steps/step3_create_patients.py --neo4j-password your_password
# ... etc
```

## 📊 Graph Schema

### Core Nodes

#### Patient Node
```cypher
(:Patient {
  ptid: String,           // Patient ID
  rid: String,            // Registry ID
  gender: String,         // M/F
  age_at_baseline: Float,
  education_years: Integer,
  apoe_genotype: String,  // E2/E3/E4 combinations
  race: String,
  ethnicity: String
})
```

#### Visit Node
```cypher
(:Visit {
  visit_id: String,
  patient_id: String,
  viscode: String,        // Visit code (bl, m06, m12, etc.)
  months_from_baseline: Integer,
  visit_date: String,
  visit_type: String      // baseline/follow-up
})
```

#### Diagnosis Node
```cypher
(:Diagnosis {
  diagnosis_id: String,
  patient_id: String,
  visit_id: String,
  diagnosis_code: String,  // CN/SMC/EMCI/LMCI/AD
  diagnosis_text: String,
  confidence: Float,
  criteria_used: String
})
```

#### Biomarker Node
```cypher
(:Biomarker {
  biomarker_id: String,
  patient_id: String,
  visit_id: String,
  analyte: String,        // Aβ42, Tau, p-Tau181
  value: Float,
  unit: String,
  abnormal_flag: Boolean,
  specimen_type: String   // CSF/Blood
})
```

#### CognitiveAssessment Node
```cypher
(:CognitiveAssessment {
  assessment_id: String,
  patient_id: String,
  visit_id: String,
  test_name: String,      // MMSE/CDR/ADAS
  total_score: Float,
  subscores: Map,
  clinical_significance: String
})
```

### Key Relationships

#### Clinical Relationships
- `(Patient)-[:HAS_VISIT]->(Visit)`
- `(Visit)-[:HAS_DIAGNOSIS]->(Diagnosis)`
- `(Visit)-[:HAS_BIOMARKER]->(Biomarker)`
- `(Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(CognitiveAssessment)`
- `(Patient)-[:HAS_DIAGNOSIS]->(Diagnosis)`

#### Progression Relationships
- `(Diagnosis)-[:PROGRESSED_TO]->(Diagnosis)`
- `(Visit)-[:FOLLOWED_BY]->(Visit)`
- `(Patient)-[:AT_STAGE]->(DiseaseStage)`

#### Risk Relationships
- `(Patient)-[:HAS_GENETIC_RISK]->(GeneticRiskProfile)`
- `(Patient)-[:HAS_FAMILY_MEMBER]->(FamilyMember)`
- `(FamilyMember)-[:HAS_DEMENTIA]->(DementiaStatus)`

#### Correlation Relationships
- `(Biomarker)-[:CORRELATES_WITH]->(Biomarker)`
- `(Biomarker)-[:INDICATES_PATHWAY]->(BiologicalPathway)`
- `(CognitiveAssessment)-[:ASSOCIATED_WITH_STAGE]->(DiseaseStage)`

## 🔍 Common Queries

### Find Disease Progressors
```cypher
MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d1:Diagnosis {diagnosis_code: 'CN'})
MATCH (p)-[:HAS_DIAGNOSIS]->(d2:Diagnosis {diagnosis_code: 'AD'})
WHERE d1.visit_id < d2.visit_id
RETURN p.ptid, d1.visit_id, d2.visit_id
```

### Biomarker Trajectories
```cypher
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_BIOMARKER]->(b:Biomarker)
WHERE b.analyte = 'Aβ42'
RETURN p.ptid, v.months_from_baseline, b.value
ORDER BY p.ptid, v.months_from_baseline
```

### High-Risk Patients
```cypher
MATCH (p:Patient)
WHERE p.apoe_genotype CONTAINS 'E4'
MATCH (p)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember)
WHERE fm.has_dementia = true
RETURN p.ptid, p.apoe_genotype, COUNT(fm) as affected_family
```

## 🎯 Troubleshooting

### Missing Diagnoses
**Problem**: No diagnosis relationships created

**Solution**:
1. Verify DXSUM.csv exists in inputs/Tables/
2. Check table headers match expected format
3. Run diagnosis extraction separately:
```bash
python steps/step6_extract_findings_robust.py --debug
```

### Memory Issues
**Problem**: Out of memory during processing

**Solution**:
1. Reduce batch_size in config
2. Process tables sequentially
3. Increase Docker memory limits

### Slow Performance
**Problem**: Pipeline takes too long

**Solution**:
1. Enable incremental mode
2. Increase max_workers
3. Add Redis caching
4. Create proper indexes

## 📈 Data Quality Checks

### Validation Scripts
```bash
# Check data completeness
python utils/validate_data.py

# Verify relationships
python utils/check_relationships.py

# Generate quality report
python utils/quality_report.py
```

### Expected Metrics
- Patients with diagnoses: >80%
- Patients with biomarkers: >60%
- Patients with imaging: >70%
- Visit temporal consistency: 100%

## 🔄 Maintenance

### Daily Tasks
- Monitor pipeline logs
- Check Redis cache hit rates
- Verify Elasticsearch indexing

### Weekly Tasks
- Run data quality checks
- Optimize slow queries
- Clean up orphaned nodes

### Monthly Tasks
- Full data validation
- Performance tuning
- Backup graph database

## 📚 Additional Resources

- [ADNI Documentation](https://adni.loni.usc.edu/data-samples/data-faq/)
- [Neo4j Graph Data Science](https://neo4j.com/docs/graph-data-science/)
- [Elasticsearch Guide](https://www.elastic.co/guide/)

## 🤝 Contributing

Please read CONTRIBUTING.md for details on our code of conduct and the process for submitting pull requests.

## 📝 License

This project is licensed under the MIT License - see LICENSE.md for details.

## 🙏 Acknowledgments

- ADNI Data Collection and Sharing
- Neo4j Community
- Python Scientific Computing Community

## 📧 Contact

For questions or support, please contact: [oguzhan@divabt.com]