"""
Step 8: Fixed Comprehensive Relationship Creation
Fixes all syntax errors and missing relationships
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


class ComprehensiveRelationshipCreator:
    """Create all relationships with proper syntax and error handling"""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector
        self.relationship_stats = {}
        self.diagnostics = {}

    def execute(self) -> Dict[str, Any]:
        """Execute comprehensive relationship creation"""
        results = {
            'relationships_created': 0,
            'relationship_types': {},
            'errors': [],
            'diagnostics': {}
        }

        start_time = datetime.now()

        # Run diagnostics first
        logger.info("Running diagnostics...")
        self._run_diagnostics()

        # Ensure basic entity relationships exist
        self._ensure_basic_relationships()

        # Create relationships in order
        relationship_functions = [
            ("diagnosis_patient", self._create_diagnosis_patient_relationships),
            ("diagnosis_visit", self._create_diagnosis_visit_relationships),
            ("biomarker_patient", self._create_biomarker_patient_relationships),
            ("biomarker_visit", self._create_biomarker_visit_relationships),
            ("assessment_patient", self._create_assessment_patient_relationships),
            ("assessment_visit", self._create_assessment_visit_relationships),
            ("temporal", self._create_temporal_relationships_fixed),
            ("clinical_progression", self._create_clinical_progression),
            ("biomarker_correlations", self._create_biomarker_correlations),
            ("imaging_clinical", self._create_imaging_clinical_relationships),
            ("genetic_risk", self._create_genetic_risk_relationships),
            ("multimodal", self._create_multimodal_assessments),
            ("research_cohorts", self._create_research_cohorts),
            ("cognitive_trajectories", self._create_cognitive_trajectories),
            ("family_risk", self._create_family_risk_relationships),
            ("disease_networks", self._create_disease_network_relationships)
        ]

        for rel_type, func in relationship_functions:
            try:
                logger.info(f"Creating {rel_type} relationships...")
                count = func()
                results['relationship_types'][rel_type] = count

                if count == 0:
                    logger.warning(f"⚠️ No {rel_type} relationships created")
                    self._diagnose_missing_relationships(rel_type)
                else:
                    logger.info(f"✅ Created {count} {rel_type} relationships")

            except Exception as e:
                logger.error(f"Failed to create {rel_type}: {e}")
                results['errors'].append(f"{rel_type}: {str(e)}")

        results['relationships_created'] = sum(results['relationship_types'].values())
        results['timing'] = (datetime.now() - start_time).total_seconds()
        results['diagnostics'] = self.diagnostics

        return results

    def _run_diagnostics(self):
        """Run diagnostics to understand what data is available"""

        # Check for diagnoses
        query = "MATCH (d:Diagnosis) RETURN count(d) as count, collect(DISTINCT d.diagnosis_code)[..5] as samples"
        result = self.connector.run_query(query)
        diagnosis_count = result[0]['count'] if result else 0
        self.diagnostics['diagnoses'] = diagnosis_count
        logger.info(f"Found {diagnosis_count} Diagnosis nodes")

        # Check for biomarkers
        query = "MATCH (b:Biomarker) RETURN count(b) as count, collect(DISTINCT b.analyte)[..5] as samples"
        result = self.connector.run_query(query)
        biomarker_count = result[0]['count'] if result else 0
        self.diagnostics['biomarkers'] = biomarker_count
        logger.info(f"Found {biomarker_count} Biomarker nodes")

        # Check for visits
        query = "MATCH (v:Visit) RETURN count(v) as count"
        result = self.connector.run_query(query)
        visit_count = result[0]['count'] if result else 0
        self.diagnostics['visits'] = visit_count
        logger.info(f"Found {visit_count} Visit nodes")

        # Check for patients with APOE
        query = "MATCH (p:Patient) WHERE p.apoe_genotype IS NOT NULL RETURN count(p) as count"
        result = self.connector.run_query(query)
        apoe_count = result[0]['count'] if result else 0
        self.diagnostics['patients_with_apoe'] = apoe_count
        logger.info(f"Found {apoe_count} patients with APOE genotype")

    def _diagnose_missing_relationships(self, rel_type: str):
        """Diagnose why a relationship type wasn't created"""

        if rel_type == "diagnosis_patient":
            query = """
            MATCH (d:Diagnosis) 
            RETURN count(d) as total_diagnoses,
                   count(d.patient_id) as with_patient_id,
                   collect(DISTINCT d.patient_id)[..3] as sample_ids
            """
            result = self.connector.run_query(query)
            if result:
                logger.info(f"  Diagnosis diagnostic: {result[0]}")

        elif rel_type == "biomarker_patient":
            query = """
            MATCH (b:Biomarker)
            RETURN count(b) as total_biomarkers,
                   count(b.patient_id) as with_patient_id,
                   collect(DISTINCT b.analyte)[..3] as sample_analytes
            """
            result = self.connector.run_query(query)
            if result:
                logger.info(f"  Biomarker diagnostic: {result[0]}")

    def _ensure_basic_relationships(self):
        """Ensure basic entity relationships exist"""
        logger.info("Ensuring basic relationships...")

        # Update diagnoses with patient_id from visit_id if missing
        query = """
        MATCH (d:Diagnosis)
        WHERE d.patient_id IS NULL AND d.visit_id IS NOT NULL
        WITH d, split(d.visit_id, '_')[0] as extracted_ptid
        SET d.patient_id = extracted_ptid
        """
        self.connector.execute_write_transaction(query)

        # Update biomarkers with patient_id from visit_id if missing
        query = """
        MATCH (b:Biomarker)
        WHERE b.patient_id IS NULL AND b.visit_id IS NOT NULL
        WITH b, split(b.visit_id, '_')[0] as extracted_ptid
        SET b.patient_id = extracted_ptid
        """
        self.connector.execute_write_transaction(query)

        # Ensure visits exist for all visit_ids referenced
        query = """
        MATCH (d:Diagnosis)
        WHERE d.visit_id IS NOT NULL
        WITH DISTINCT d.visit_id as visit_id, split(d.visit_id, '_')[0] as ptid, split(d.visit_id, '_')[1] as viscode
        MERGE (v:Visit {visit_id: visit_id})
        SET v.patient_id = ptid, v.viscode = viscode
        WITH v, ptid
        MATCH (p:Patient {ptid: ptid})
        MERGE (p)-[:HAS_VISIT]->(v)
        """
        self.connector.execute_write_transaction(query)

    def _create_diagnosis_patient_relationships(self) -> int:
        """Create relationships between diagnoses and patients"""
        query = """
        MATCH (d:Diagnosis)
        WHERE d.patient_id IS NOT NULL
        MATCH (p:Patient {ptid: d.patient_id})
        MERGE (p)-[:HAS_DIAGNOSIS {
            diagnosis_code: d.diagnosis_code,
            confidence: COALESCE(d.confidence, 1.0)
        }]->(d)
        RETURN count(*) as count
        """
        result = self.connector.run_query(query)
        return result[0]['count'] if result else 0

    def _create_diagnosis_visit_relationships(self) -> int:
        """Create relationships between diagnoses and visits"""
        query = """
        MATCH (d:Diagnosis)
        WHERE d.visit_id IS NOT NULL
        MATCH (v:Visit {visit_id: d.visit_id})
        MERGE (v)-[:HAS_DIAGNOSIS {
            diagnosis_code: d.diagnosis_code
        }]->(d)
        RETURN count(*) as count
        """
        result = self.connector.run_query(query)
        return result[0]['count'] if result else 0

    def _create_biomarker_patient_relationships(self) -> int:
        """Create relationships between biomarkers and patients"""
        query = """
        MATCH (b:Biomarker)
        WHERE b.patient_id IS NOT NULL
        MATCH (p:Patient {ptid: b.patient_id})
        MERGE (p)-[:HAS_BIOMARKER {
            analyte: b.analyte,
            abnormal: COALESCE(b.abnormal_flag, false)
        }]->(b)
        RETURN count(*) as count
        """
        result = self.connector.run_query(query)
        return result[0]['count'] if result else 0

    def _create_biomarker_visit_relationships(self) -> int:
        """Create relationships between biomarkers and visits"""
        query = """
        MATCH (b:Biomarker)
        WHERE b.visit_id IS NOT NULL
        MATCH (v:Visit {visit_id: b.visit_id})
        MERGE (v)-[:HAS_BIOMARKER {
            analyte: b.analyte
        }]->(b)
        RETURN count(*) as count
        """
        result = self.connector.run_query(query)
        return result[0]['count'] if result else 0

    def _create_assessment_patient_relationships(self) -> int:
        """Create relationships between cognitive assessments and patients"""
        query = """
        MATCH (ca:CognitiveAssessment)
        WHERE ca.patient_id IS NOT NULL
        MATCH (p:Patient {ptid: ca.patient_id})
        MERGE (p)-[:HAS_COGNITIVE_ASSESSMENT {
            test_name: ca.test_name
        }]->(ca)
        RETURN count(*) as count
        """
        result = self.connector.run_query(query)
        return result[0]['count'] if result else 0

    def _create_assessment_visit_relationships(self) -> int:
        """Create relationships between cognitive assessments and visits"""
        query = """
        MATCH (ca:CognitiveAssessment)
        WHERE ca.visit_id IS NOT NULL
        MATCH (v:Visit {visit_id: ca.visit_id})
        MERGE (v)-[:HAS_COGNITIVE_ASSESSMENT {
            test_name: ca.test_name
        }]->(ca)
        RETURN count(*) as count
        """
        result = self.connector.run_query(query)
        return result[0]['count'] if result else 0

    def _create_temporal_relationships_fixed(self) -> int:
        """FIXED: Create temporal relationships between visits"""
        query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v1:Visit)
        MATCH (p)-[:HAS_VISIT]->(v2:Visit)
        WHERE v1.months_from_baseline < v2.months_from_baseline
        WITH v1, v2, v2.months_from_baseline - v1.months_from_baseline as delta
        ORDER BY v1.visit_id, delta
        WITH v1, COLLECT({visit: v2, delta: delta})[0] as next_visit
        WHERE next_visit IS NOT NULL
        WITH v1, next_visit.visit as v2, next_visit.delta as delta
        MERGE (v1)-[r:FOLLOWED_BY {months_delta: delta}]->(v2)
        RETURN count(r) as count
        """
        result = self.connector.run_query(query)
        return result[0]['count'] if result else 0

    def _create_clinical_progression(self) -> int:
        """Create clinical progression relationships"""
        count = 0

        progressions = [
            ('CN', 'MCI', 'CN_to_MCI'),
            ('CN', 'AD', 'CN_to_AD'),
            ('MCI', 'AD', 'MCI_to_AD'),
            ('EMCI', 'LMCI', 'EMCI_to_LMCI'),
            ('LMCI', 'AD', 'LMCI_to_AD'),
            ('CN', 'EMCI', 'CN_to_EMCI'),
            ('CN', 'LMCI', 'CN_to_LMCI'),
            ('SMC', 'EMCI', 'SMC_to_EMCI'),
            ('SMC', 'LMCI', 'SMC_to_LMCI'),
            ('SMC', 'AD', 'SMC_to_AD')
        ]

        for from_dx, to_dx, prog_type in progressions:
            query = """
            MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d1:Diagnosis)
            WHERE d1.diagnosis_code = $from_dx
            MATCH (p)-[:HAS_DIAGNOSIS]->(d2:Diagnosis)
            WHERE d2.diagnosis_code = $to_dx
            WITH p, d1, d2
            MERGE (d1)-[r:PROGRESSED_TO {
                progression_type: $prog_type,
                patient_id: p.ptid
            }]->(d2)
            RETURN count(r) as count
            """

            result = self.connector.run_query(query, {
                'from_dx': from_dx,
                'to_dx': to_dx,
                'prog_type': prog_type
            })

            if result:
                count += result[0]['count']

        return count

    def _create_biomarker_correlations(self) -> int:
        """Create correlations between biomarkers at same visit"""
        query = """
        MATCH (v:Visit)-[:HAS_BIOMARKER]->(b1:Biomarker)
        MATCH (v)-[:HAS_BIOMARKER]->(b2:Biomarker)
        WHERE id(b1) < id(b2)
        AND b1.analyte <> b2.analyte
        WITH b1, b2, v
        MERGE (b1)-[r:CORRELATES_WITH {
            same_visit: true,
            visit_id: v.visit_id
        }]->(b2)
        RETURN count(r) as count
        """
        result = self.connector.run_query(query)
        return result[0]['count'] if result else 0

    def _create_imaging_clinical_relationships(self) -> int:
        """Create relationships between imaging and clinical data"""
        count = 0

        # Link volumetric measures to diagnoses at same visit
        query = """
        MATCH (v:Visit)-[:HAS_VOLUMETRIC_MEASURE]->(vol:VolumetricMeasure)
        MATCH (v)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        MERGE (vol)-[r:ASSOCIATED_WITH_DIAGNOSIS {
            diagnosis_code: d.diagnosis_code,
            same_visit: true
        }]->(d)
        RETURN count(r) as count
        """
        result = self.connector.run_query(query)
        count += result[0]['count'] if result else 0

        # Link PET to diagnoses
        query = """
        MATCH (v:Visit)-[:HAS_PET_BINDING]->(pet:PETBinding)
        MATCH (v)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WHERE pet.abnormal_flag = true
        MERGE (pet)-[r:SUPPORTS_DIAGNOSIS {
            diagnosis_code: d.diagnosis_code,
            tracer: pet.tracer
        }]->(d)
        RETURN count(r) as count
        """
        result = self.connector.run_query(query)
        count += result[0]['count'] if result else 0

        return count

    def _create_genetic_risk_relationships(self) -> int:
        """Create genetic risk relationships for APOE carriers"""
        query = """
        MATCH (p:Patient)
        WHERE p.apoe_genotype IS NOT NULL AND p.apoe_genotype <> ''
        WITH p, p.apoe_genotype as genotype,
             CASE 
                WHEN p.apoe_genotype CONTAINS '4/4' OR p.apoe_genotype CONTAINS 'E4/E4' THEN 'homozygous_e4'
                WHEN p.apoe_genotype CONTAINS '3/4' OR p.apoe_genotype CONTAINS 'E3/E4' THEN 'heterozygous_e4'
                WHEN p.apoe_genotype CONTAINS '2/4' OR p.apoe_genotype CONTAINS 'E2/E4' THEN 'heterozygous_e4'
                WHEN p.apoe_genotype CONTAINS '2' OR p.apoe_genotype CONTAINS 'E2' THEN 'protective_e2'
                ELSE 'non_carrier'
             END as apoe_status,
             CASE 
                WHEN p.apoe_genotype CONTAINS '4/4' OR p.apoe_genotype CONTAINS 'E4/E4' THEN 12.0
                WHEN p.apoe_genotype CONTAINS '3/4' OR p.apoe_genotype CONTAINS 'E3/E4' THEN 3.0
                WHEN p.apoe_genotype CONTAINS '2/4' OR p.apoe_genotype CONTAINS 'E2/E4' THEN 2.5
                WHEN p.apoe_genotype CONTAINS '2' OR p.apoe_genotype CONTAINS 'E2' THEN 0.6
                ELSE 1.0
             END as risk_factor
        MERGE (gr:GeneticRiskProfile {
            profile_id: p.ptid + '_genetic',
            patient_id: p.ptid
        })
        SET gr.apoe_status = apoe_status,
            gr.apoe_genotype = genotype,
            gr.risk_factor = risk_factor
        MERGE (p)-[:HAS_GENETIC_RISK {
            risk_level: CASE 
                WHEN risk_factor >= 10 THEN 'very_high'
                WHEN risk_factor >= 3 THEN 'high'
                WHEN risk_factor < 1 THEN 'protective'
                ELSE 'normal'
            END
        }]->(gr)
        RETURN count(gr) as count
        """
        result = self.connector.run_query(query)
        return result[0]['count'] if result else 0

    def _create_multimodal_assessments(self) -> int:
        """Create multimodal assessment nodes for visits with multiple data types"""
        query = """
        MATCH (v:Visit)
        OPTIONAL MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        OPTIONAL MATCH (v)-[:HAS_BIOMARKER]->(b:Biomarker)
        OPTIONAL MATCH (v)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WITH v, 
             count(DISTINCT ca) as cog_count,
             count(DISTINCT b) as bio_count,
             count(DISTINCT d) as dx_count,
             collect(DISTINCT ca.test_name) as tests,
             collect(DISTINCT b.analyte) as biomarkers
        WHERE (cog_count + bio_count + dx_count) >= 2
        MERGE (ma:MultimodalAssessment {
            assessment_id: v.visit_id + '_multimodal',
            visit_id: v.visit_id
        })
        SET ma.cognitive_count = cog_count,
            ma.biomarker_count = bio_count,
            ma.diagnosis_count = dx_count,
            ma.cognitive_tests = tests,
            ma.biomarkers_collected = biomarkers
        MERGE (v)-[:HAS_MULTIMODAL_ASSESSMENT]->(ma)
        RETURN count(ma) as count
        """
        result = self.connector.run_query(query)
        return result[0]['count'] if result else 0

    def _create_research_cohorts(self) -> int:
        """Create research cohort groupings"""
        query = """
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WITH p, COLLECT(DISTINCT d.diagnosis_code) as diagnoses
        WITH p, 
             CASE 
                WHEN 'AD' IN diagnoses THEN 'AD'
                WHEN 'LMCI' IN diagnoses OR 'EMCI' IN diagnoses OR 'MCI' IN diagnoses THEN 'MCI'
                WHEN 'SMC' IN diagnoses THEN 'SMC'
                WHEN 'CN' IN diagnoses THEN 'CN'
                ELSE 'Unknown'
             END as cohort_type
        WHERE cohort_type <> 'Unknown'
        MERGE (c:ResearchCohort {cohort_id: cohort_type})
        SET c.cohort_type = cohort_type
        MERGE (p)-[:BELONGS_TO_COHORT]->(c)
        RETURN count(DISTINCT c) as count
        """
        result = self.connector.run_query(query)
        return result[0]['count'] if result else 0

    def _create_cognitive_trajectories(self) -> int:
        """Create cognitive trajectory relationships"""
        query = """
        MATCH (p:Patient)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        OPTIONAL MATCH (ca)<-[:HAS_COGNITIVE_ASSESSMENT]-(v:Visit)
        WITH p, ca.test_name as test, 
             COLLECT({
                score: ca.total_score, 
                months: COALESCE(v.months_from_baseline, 0)
             }) as scores
        WHERE SIZE(scores) >= 2
        WITH p, test, scores,
             scores[0].score as baseline_score,
             scores[-1].score as final_score,
             scores[-1].months - scores[0].months as duration
        WHERE duration >= 0
        MERGE (traj:CognitiveTrajectory {
            trajectory_id: p.ptid + '_' + test,
            patient_id: p.ptid,
            test_name: test
        })
        SET traj.baseline_score = baseline_score,
            traj.final_score = final_score,
            traj.duration_months = duration,
            traj.change_rate = CASE 
                WHEN duration > 0 THEN (final_score - baseline_score) / duration 
                ELSE 0 
            END
        MERGE (p)-[:HAS_COGNITIVE_TRAJECTORY]->(traj)
        RETURN count(traj) as count
        """
        result = self.connector.run_query(query)
        return result[0]['count'] if result else 0

    def _create_family_risk_relationships(self) -> int:
        """Create family risk relationships"""
        query = """
        MATCH (p:Patient)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember)
        WHERE fm.has_dementia = true
        WITH p, COUNT(fm) as affected_count
        MERGE (fr:FamilyRisk {
            risk_id: p.ptid + '_family_risk',
            patient_id: p.ptid
        })
        SET fr.affected_family_members = affected_count,
            fr.risk_score = affected_count * 1.5,
            fr.risk_category = CASE
                WHEN affected_count >= 3 THEN 'very_high'
                WHEN affected_count >= 2 THEN 'high'
                WHEN affected_count >= 1 THEN 'moderate'
                ELSE 'low'
            END
        MERGE (p)-[:HAS_FAMILY_RISK]->(fr)
        RETURN count(fr) as count
        """
        result = self.connector.run_query(query)
        return result[0]['count'] if result else 0

    def _create_disease_network_relationships(self) -> int:
        """Create disease network relationships based on biological pathways"""
        count = 0

        # Create biological pathways
        pathways = [
            ('amyloid_cascade', 'Amyloid Cascade', 'Beta-amyloid accumulation pathway'),
            ('tau_pathology', 'Tau Pathology', 'Tau protein aggregation'),
            ('neurodegeneration', 'Neurodegeneration', 'Neural cell death'),
            ('neuroinflammation', 'Neuroinflammation', 'Brain inflammation')
        ]

        for pathway_id, name, description in pathways:
            query = """
            MERGE (p:BiologicalPathway {pathway_id: $pathway_id})
            SET p.name = $name, p.description = $description
            """
            self.connector.execute_write_transaction(
                query,
                {'pathway_id': pathway_id, 'name': name, 'description': description}
            )
            count += 1

        # Link biomarkers to pathways
        biomarker_pathway_map = [
            (['Aβ42', 'ABETA42', 'AB42', 'Aβ40', 'ABETA40', 'AB40'], 'amyloid_cascade'),
            (['Total Tau', 'TAU', 'T-TAU', 'TTAU'], 'tau_pathology'),
            (['p-Tau181', 'PTAU', 'P-TAU', 'PTAU181'], 'tau_pathology'),
            (['Total Tau', 'TAU', 'T-TAU'], 'neurodegeneration')
        ]

        for analytes, pathway_id in biomarker_pathway_map:
            query = """
            MATCH (b:Biomarker)
            WHERE b.analyte IN $analytes
            MATCH (p:BiologicalPathway {pathway_id: $pathway_id})
            MERGE (b)-[r:INDICATES_PATHWAY {
                indication_strength: CASE 
                    WHEN b.abnormal_flag = true THEN 0.9
                    ELSE 0.3
                END
            }]->(p)
            RETURN count(r) as count
            """
            result = self.connector.run_query(query, {
                'analytes': analytes,
                'pathway_id': pathway_id
            })
            if result:
                count += result[0]['count']

        return count


def execute_comprehensive_relationship_creation(neo4j_uri: str, neo4j_user: str,
                                               neo4j_password: str) -> Dict[str, Any]:
    """Execute comprehensive relationship creation with fixes"""
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        creator = ComprehensiveRelationshipCreator(connector)
        results = creator.execute()

        logger.info("\n" + "="*60)
        logger.info("RELATIONSHIP CREATION SUMMARY")
        logger.info("="*60)
        logger.info(f"Total relationships created: {results['relationships_created']:,}")

        for rel_type, count in results['relationship_types'].items():
            status = "✅" if count > 0 else "❌"
            logger.info(f"{status} {rel_type:<30}: {count:>10,}")

        return results

    except Exception as e:
        logger.error(f"Relationship creation failed: {e}")
        raise
    finally:
        connector.close()