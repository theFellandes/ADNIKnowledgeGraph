"""
Step 9: Knowledge Graph Enhancement Module (FIXED)
Creates semantic relationships based on ADNI domain knowledge
Fixed null property issues and improved error handling
"""

import logging
from typing import Dict, List, Any, Optional
from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


class KnowledgeGraphEnhancer:
    """Enhance the graph with semantic relationships based on AD research"""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector

    def create_semantic_relationships(self) -> Dict[str, int]:
        """Create all semantic relationships for a proper knowledge graph"""
        results = {}

        try:
            # 1. Create AD Stage Progression Network
            logger.info("Creating AD stage progression network...")
            results['stage_progression'] = self._create_stage_progression()

            # 2. Create Biomarker-Diagnosis Associations
            logger.info("Creating biomarker-diagnosis associations...")
            results['biomarker_diagnosis'] = self._create_biomarker_diagnosis_associations()

            # 3. Create Cognitive Decline Trajectories
            logger.info("Creating cognitive decline trajectories...")
            results['cognitive_trajectories'] = self._create_cognitive_trajectories()

            # 4. Create Risk Factor Network
            logger.info("Creating risk factor network...")
            results['risk_factors'] = self._create_risk_factor_network()

            # 5. Create Temporal Disease Network
            logger.info("Creating temporal disease network...")
            results['temporal_network'] = self._create_temporal_disease_network()

            # 6. Create Amyloid-Tau-Neurodegeneration (ATN) Framework
            logger.info("Creating ATN framework...")
            results['atn_framework'] = self._create_atn_framework()

            # 7. Create Clinical Phenotypes
            logger.info("Creating clinical phenotypes...")
            results['phenotypes'] = self._create_clinical_phenotypes()

            # 8. Create Progression Pathways
            logger.info("Creating progression pathways...")
            results['progression_pathways'] = self._create_progression_pathways()

        except Exception as e:
            logger.error(f"Error creating semantic relationships: {e}")
            # Continue with partial results rather than failing completely
            results['error'] = str(e)

        return results

    def _create_stage_progression(self) -> int:
        """Create disease stage progression relationships - FIXED NULL HANDLING"""

        # Create disease stage nodes
        create_stages_query = """
        MERGE (cn:DiseaseStage {stage_id: 'CN', name: 'Cognitively Normal', order: 1})
        MERGE (smc:DiseaseStage {stage_id: 'SMC', name: 'Subjective Memory Concern', order: 2})
        MERGE (emci:DiseaseStage {stage_id: 'EMCI', name: 'Early MCI', order: 3})
        MERGE (lmci:DiseaseStage {stage_id: 'LMCI', name: 'Late MCI', order: 4})
        MERGE (ad:DiseaseStage {stage_id: 'AD', name: 'Alzheimer Disease', order: 5})
        """

        self.connector.execute_write_transaction(create_stages_query)

        # Create progression relationships
        progressions_query = """
        MATCH (cn:DiseaseStage {stage_id: 'CN'})
        MATCH (smc:DiseaseStage {stage_id: 'SMC'})
        MATCH (emci:DiseaseStage {stage_id: 'EMCI'})
        MATCH (lmci:DiseaseStage {stage_id: 'LMCI'})
        MATCH (ad:DiseaseStage {stage_id: 'AD'})
        
        MERGE (cn)-[:PROGRESSES_TO {typical_duration_months: 36}]->(smc)
        MERGE (smc)-[:PROGRESSES_TO {typical_duration_months: 24}]->(emci)
        MERGE (emci)-[:PROGRESSES_TO {typical_duration_months: 18}]->(lmci)
        MERGE (lmci)-[:PROGRESSES_TO {typical_duration_months: 12}]->(ad)
        
        // Alternative progressions
        MERGE (cn)-[:CAN_PROGRESS_TO {typical_duration_months: 60}]->(emci)
        MERGE (cn)-[:CAN_PROGRESS_TO {typical_duration_months: 84}]->(ad)
        MERGE (emci)-[:CAN_PROGRESS_TO {typical_duration_months: 36}]->(ad)
        """

        self.connector.execute_write_transaction(progressions_query)

        # FIXED: Link patients to disease stages with proper null handling
        patient_stage_query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WITH p, d, v
        ORDER BY v.months_from_baseline DESC
        WITH p, COLLECT({diagnosis: d, visit: v})[0] as latest
        WHERE latest.diagnosis.diagnosis_code IN ['CN', 'SMC', 'EMCI', 'LMCI', 'MCI', 'AD']
        MATCH (ds:DiseaseStage)
        WHERE ds.stage_id = CASE 
            WHEN latest.diagnosis.diagnosis_code = 'MCI' THEN 'LMCI'
            ELSE latest.diagnosis.diagnosis_code
        END
        
        // Only create relationship if we have valid date
        WITH p, ds, latest, 
             COALESCE(latest.visit.visit_date, 'unknown') as visit_date,
             COALESCE(latest.visit.months_from_baseline, 0) as months
        
        MERGE (p)-[r:AT_STAGE]->(ds)
        SET r.since = visit_date,
            r.months_from_baseline = months,
            r.diagnosis_code = latest.diagnosis.diagnosis_code
        
        RETURN count(p) as count
        """

        try:
            result = self.connector.run_query(patient_stage_query)
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.warning(f"Could not link all patients to disease stages: {e}")
            # Try alternative without date properties
            return self._create_stage_progression_simple()

    def _create_stage_progression_simple(self) -> int:
        """Simplified version without date properties"""
        simple_query = """
        MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WHERE d.diagnosis_code IN ['CN', 'SMC', 'EMCI', 'LMCI', 'MCI', 'AD']
        WITH p, d.diagnosis_code as dx_code
        WITH p, COLLECT(DISTINCT dx_code) as diagnoses
        WITH p, 
             CASE 
                WHEN 'AD' IN diagnoses THEN 'AD'
                WHEN 'LMCI' IN diagnoses THEN 'LMCI'
                WHEN 'MCI' IN diagnoses THEN 'LMCI'
                WHEN 'EMCI' IN diagnoses THEN 'EMCI'
                WHEN 'SMC' IN diagnoses THEN 'SMC'
                WHEN 'CN' IN diagnoses THEN 'CN'
                ELSE NULL
             END as current_stage
        WHERE current_stage IS NOT NULL
        MATCH (ds:DiseaseStage {stage_id: current_stage})
        MERGE (p)-[:AT_STAGE {inferred: true}]->(ds)
        RETURN count(p) as count
        """

        try:
            result = self.connector.run_query(simple_query)
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.error(f"Failed to create stage progression: {e}")
            return 0

    def _create_biomarker_diagnosis_associations(self) -> int:
        """Create associations between biomarkers and diagnoses"""

        # Create biomarker patterns
        biomarker_patterns_query = """
        MERGE (abeta_low:BiomarkerPattern {
            pattern_id: 'abeta_low',
            name: 'Low Aβ42',
            threshold: '<600 pg/mL',
            significance: 'Amyloid positivity'
        })
        
        MERGE (tau_high:BiomarkerPattern {
            pattern_id: 'tau_high',
            name: 'High Tau',
            threshold: '>400 pg/mL',
            significance: 'Neurodegeneration'
        })
        
        MERGE (ptau_high:BiomarkerPattern {
            pattern_id: 'ptau_high',
            name: 'High p-Tau',
            threshold: '>80 pg/mL',
            significance: 'Tau pathology'
        })
        
        WITH abeta_low, tau_high, ptau_high
        
        // Link patterns to disease stages
        MATCH (ad:DiseaseStage {stage_id: 'AD'})
        MERGE (abeta_low)-[:INDICATES {strength: 0.9}]->(ad)
        MERGE (tau_high)-[:INDICATES {strength: 0.85}]->(ad)
        MERGE (ptau_high)-[:INDICATES {strength: 0.87}]->(ad)
        
        WITH abeta_low
        
        MATCH (mci:DiseaseStage)
        WHERE mci.stage_id IN ['EMCI', 'LMCI']
        MERGE (abeta_low)-[:INDICATES {strength: 0.7}]->(mci)
        """

        self.connector.execute_write_transaction(biomarker_patterns_query)

        # Link actual biomarkers to patterns
        link_biomarkers_query = """
        // Count Aβ42 biomarkers
        MATCH (b:Biomarker)
        WHERE b.analyte IN ['Aβ42', 'ABETA42', 'AB42', 'Abeta42'] 
        AND b.value IS NOT NULL 
        AND b.value < 600
        MATCH (pattern:BiomarkerPattern {pattern_id: 'abeta_low'})
        MERGE (b)-[:MATCHES_PATTERN]->(pattern)
        WITH count(*) as count_abeta
        
        // Count Tau biomarkers
        MATCH (b:Biomarker)
        WHERE b.analyte IN ['Total Tau', 'TAU', 'TTAU', 'T-TAU', 't-tau'] 
        AND b.value IS NOT NULL 
        AND b.value > 400
        MATCH (pattern:BiomarkerPattern {pattern_id: 'tau_high'})
        MERGE (b)-[:MATCHES_PATTERN]->(pattern)
        WITH count_abeta, count(*) as count_tau
        
        // Count p-Tau biomarkers
        MATCH (b:Biomarker)
        WHERE b.analyte IN ['p-Tau181', 'PTAU', 'P-TAU', 'PTAU181', 'p-tau'] 
        AND b.value IS NOT NULL 
        AND b.value > 80
        MATCH (pattern:BiomarkerPattern {pattern_id: 'ptau_high'})
        MERGE (b)-[:MATCHES_PATTERN]->(pattern)
        WITH count_abeta, count_tau, count(*) as count_ptau
        
        // Return total
        RETURN count_abeta + count_tau + count_ptau as total
        """

        try:
            result = self.connector.run_query(link_biomarkers_query)
            return result[0]['total'] if result else 0
        except Exception as e:
            logger.warning(f"Could not link all biomarkers to patterns: {e}")
            return 0

    def _create_cognitive_trajectories(self) -> int:
        """Create cognitive decline trajectories with better null handling"""

        # First create trajectories
        trajectory_query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        WHERE ca.total_score IS NOT NULL 
        AND v.months_from_baseline IS NOT NULL
        
        WITH p, ca.test_name as test, 
             COLLECT({
                score: ca.total_score, 
                months: v.months_from_baseline,
                visit_id: v.visit_id
             }) as scores
        WHERE SIZE(scores) >= 3
        
        WITH p, test, scores,
             scores[0].score as baseline_score,
             scores[-1].score as final_score,
             scores[-1].months - scores[0].months as duration_months
        WHERE duration_months > 0 
        AND baseline_score IS NOT NULL 
        AND final_score IS NOT NULL
        
        WITH p, test, baseline_score, final_score, duration_months,
             (final_score - baseline_score) / duration_months as change_rate,
             CASE 
                WHEN test = 'MMSE' THEN
                    CASE 
                        WHEN (baseline_score - final_score) >= 3 THEN 'declining'
                        WHEN (baseline_score - final_score) <= -2 THEN 'improving'
                        ELSE 'stable'
                    END
                WHEN test IN ['ADAS-Cog', 'ADAS-Cog13', 'ADAS13'] THEN
                    CASE 
                        WHEN (final_score - baseline_score) >= 4 THEN 'declining'
                        WHEN (final_score - baseline_score) <= -3 THEN 'improving'
                        ELSE 'stable'
                    END
                ELSE 'stable'
             END as trajectory_type
        
        MERGE (traj:CognitiveTrajectory {
            trajectory_id: p.ptid + '_' + test + '_trajectory',
            patient_id: p.ptid,
            test_name: test
        })
        SET traj.baseline_score = baseline_score,
            traj.final_score = final_score,
            traj.duration_months = duration_months,
            traj.change_rate = change_rate,
            traj.trajectory_type = trajectory_type
        
        MERGE (p)-[:HAS_TRAJECTORY]->(traj)
        
        RETURN count(DISTINCT traj) as count
        """

        try:
            result = self.connector.run_query(trajectory_query)
            trajectory_count = result[0]['count'] if result else 0
        except Exception as e:
            logger.warning(f"Could not create all cognitive trajectories: {e}")
            trajectory_count = 0

        # Link trajectories to stages
        if trajectory_count > 0:
            link_query = """
            MATCH (traj:CognitiveTrajectory)
            MATCH (p:Patient {ptid: traj.patient_id})
            OPTIONAL MATCH (p)-[:AT_STAGE]->(stage:DiseaseStage)
            WHERE stage IS NOT NULL
            WITH traj, stage
            WHERE stage IS NOT NULL
            MERGE (traj)-[:ASSOCIATED_WITH_STAGE]->(stage)
            RETURN count(*) as count
            """

            try:
                result = self.connector.run_query(link_query)
                logger.info(f"Linked {result[0]['count'] if result else 0} trajectories to disease stages")
            except Exception as e:
                logger.warning(f"Could not link trajectories to stages: {e}")

        return trajectory_count

    def _create_risk_factor_network(self) -> int:
        """Create risk factor relationships with null safety"""

        # Create risk factor nodes
        create_factors_query = """
        MERGE (apoe4:RiskFactor {
            factor_id: 'APOE4',
            name: 'APOE ε4 Carrier',
            category: 'Genetic',
            odds_ratio: 3.2
        })
        
        MERGE (age:RiskFactor {
            factor_id: 'AGE',
            name: 'Advanced Age',
            category: 'Demographic',
            odds_ratio: 2.0
        })
        
        MERGE (family:RiskFactor {
            factor_id: 'FAMILY_HISTORY',
            name: 'Family History of AD',
            category: 'Genetic',
            odds_ratio: 2.5
        })
        """

        self.connector.execute_write_transaction(create_factors_query)

        total = 0

        # Link APOE4 carriers
        apoe_query = """
        MATCH (p:Patient)
        WHERE p.apoe_genotype IS NOT NULL AND p.apoe_genotype CONTAINS '4'
        MATCH (apoe4:RiskFactor {factor_id: 'APOE4'})
        MERGE (p)-[:HAS_RISK_FACTOR {
            level: CASE 
                WHEN p.apoe_genotype CONTAINS '4/4' THEN 'very_high'
                WHEN p.apoe_genotype CONTAINS '4' THEN 'high'
                ELSE 'moderate'
            END
        }]->(apoe4)
        RETURN count(p) as count
        """

        try:
            result = self.connector.run_query(apoe_query)
            total += result[0]['count'] if result else 0
        except Exception as e:
            logger.warning(f"Could not link APOE4 risk factors: {e}")

        # Link age risk
        age_query = """
        MATCH (p:Patient)
        WHERE p.age_at_baseline IS NOT NULL AND p.age_at_baseline > 75
        MATCH (age:RiskFactor {factor_id: 'AGE'})
        MERGE (p)-[:HAS_RISK_FACTOR {level: 'moderate'}]->(age)
        RETURN count(p) as count
        """

        try:
            result = self.connector.run_query(age_query)
            total += result[0]['count'] if result else 0
        except Exception as e:
            logger.warning(f"Could not link age risk factors: {e}")

        # Link family history
        family_query = """
        MATCH (p:Patient)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember)
        WHERE fm.has_dementia = true
        MATCH (family:RiskFactor {factor_id: 'FAMILY_HISTORY'})
        MERGE (p)-[:HAS_RISK_FACTOR {level: 'moderate'}]->(family)
        RETURN count(DISTINCT p) as count
        """

        try:
            result = self.connector.run_query(family_query)
            total += result[0]['count'] if result else 0
        except Exception as e:
            logger.warning(f"Could not link family history risk factors: {e}")

        return total

    def _create_temporal_disease_network(self) -> int:
        """Create temporal relationships in small batches"""

        total_created = 0
        batch_size = 50

        # Get patients to process
        patient_query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(:Visit)-[:HAS_DIAGNOSIS]->(:Diagnosis)
        RETURN DISTINCT p.ptid as patient_id
        ORDER BY patient_id
        """

        patients = self.connector.run_query(patient_query)
        if not patients:
            return 0

        logger.info(f"Processing temporal network for {len(patients)} patients in batches...")

        for i in range(0, len(patients), batch_size):
            batch_ids = [p['patient_id'] for p in patients[i:i + batch_size]]

            batch_query = """
            UNWIND $patient_ids as pid
            MATCH (p:Patient {ptid: pid})
            MATCH (p)-[:HAS_VISIT]->(v:Visit)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
            WHERE v.months_from_baseline IS NOT NULL
            WITH p, v, d
            ORDER BY p.ptid, v.months_from_baseline

            WITH p, COLLECT({
                months: v.months_from_baseline,
                diagnosis: d.diagnosis_code
            }) as visits
            WHERE SIZE(visits) >= 2

            WITH p, visits[0] as first, visits[-1] as last
            WHERE first.diagnosis <> last.diagnosis

            MERGE (pe:ProgressionEvent {
                event_id: p.ptid + '_' + first.diagnosis + '_to_' + last.diagnosis,
                patient_id: p.ptid,
                from_diagnosis: first.diagnosis,
                to_diagnosis: last.diagnosis,
                duration_months: last.months - first.months
            })

            MERGE (p)-[:EXPERIENCED_PROGRESSION]->(pe)

            RETURN count(DISTINCT pe) as count
            """

            try:
                result = self.connector.run_query(batch_query, {'patient_ids': batch_ids})
                if result:
                    total_created += result[0]['count']

                if i % 200 == 0:
                    logger.info(f"  Processed {i + batch_size}/{len(patients)} patients...")

            except Exception as e:
                logger.warning(f"Batch {i // batch_size} failed: {e}")
                continue

        return total_created

    def _create_atn_framework(self) -> int:
        """Create ATN (Amyloid-Tau-Neurodegeneration) framework with improved handling"""

        # Create ATN categories
        categories_query = """
        MERGE (a_pos:ATNCategory {category: 'A+', name: 'Amyloid Positive'})
        MERGE (a_neg:ATNCategory {category: 'A-', name: 'Amyloid Negative'})
        MERGE (t_pos:ATNCategory {category: 'T+', name: 'Tau Positive'})
        MERGE (t_neg:ATNCategory {category: 'T-', name: 'Tau Negative'})
        MERGE (n_pos:ATNCategory {category: 'N+', name: 'Neurodegeneration Positive'})
        MERGE (n_neg:ATNCategory {category: 'N-', name: 'Neurodegeneration Negative'})
        """

        self.connector.execute_write_transaction(categories_query)

        # Classify patients based on biomarkers
        atn_profile_query = """
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[:HAS_VISIT]->(v:Visit)-[:HAS_BIOMARKER]->(b:Biomarker)
        WHERE b.value IS NOT NULL
        
        WITH p, 
             MAX(CASE 
                WHEN b.analyte IN ['Aβ42', 'ABETA42', 'AB42', 'Abeta42'] 
                AND b.value < 600 THEN 1 
                ELSE 0 
             END) as amyloid_pos,
             MAX(CASE 
                WHEN b.analyte IN ['p-Tau181', 'PTAU', 'P-TAU', 'p-tau'] 
                AND b.value > 80 THEN 1 
                ELSE 0 
             END) as tau_pos,
             MAX(CASE 
                WHEN b.analyte IN ['Total Tau', 'TAU', 'T-TAU', 't-tau'] 
                AND b.value > 400 THEN 1 
                ELSE 0 
             END) as neuro_pos
        
        WHERE amyloid_pos IS NOT NULL OR tau_pos IS NOT NULL OR neuro_pos IS NOT NULL
        
        WITH p,
             CASE WHEN amyloid_pos = 1 THEN 'A+' ELSE 'A-' END as a_status,
             CASE WHEN tau_pos = 1 THEN 'T+' ELSE 'T-' END as t_status,
             CASE WHEN neuro_pos = 1 THEN 'N+' ELSE 'N-' END as n_status
        
        MERGE (profile:ATNProfile {
            profile_id: p.ptid + '_atn',
            patient_id: p.ptid
        })
        SET profile.a_status = a_status,
            profile.t_status = t_status,
            profile.n_status = n_status,
            profile.classification = a_status + '/' + t_status + '/' + n_status
        
        MERGE (p)-[:HAS_ATN_PROFILE]->(profile)
        
        // Link to ATN categories
        WITH profile, a_status, t_status, n_status
        MATCH (a_cat:ATNCategory {category: a_status})
        MATCH (t_cat:ATNCategory {category: t_status})
        MATCH (n_cat:ATNCategory {category: n_status})
        MERGE (profile)-[:HAS_AMYLOID_STATUS]->(a_cat)
        MERGE (profile)-[:HAS_TAU_STATUS]->(t_cat)
        MERGE (profile)-[:HAS_NEURODEGENERATION_STATUS]->(n_cat)
        
        RETURN count(DISTINCT profile) as count
        """

        try:
            result = self.connector.run_query(atn_profile_query)
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.warning(f"Could not create all ATN profiles: {e}")
            return 0

    def _create_clinical_phenotypes(self) -> int:
        """Create clinical phenotype clusters with better null handling"""

        phenotype_query = """
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[:HAS_TRAJECTORY]->(traj:CognitiveTrajectory)
        OPTIONAL MATCH (p)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
        OPTIONAL MATCH (p)-[:AT_STAGE]->(stage:DiseaseStage)
        
        WITH p, 
             traj.trajectory_type as traj_type,
             atn.a_status as a_status,
             stage.stage_id as stage_id
        
        WITH p,
             CASE 
                WHEN stage_id = 'AD' AND a_status = 'A+' THEN 'typical_ad'
                WHEN stage_id = 'AD' AND a_status = 'A-' THEN 'snap'
                WHEN stage_id IN ['EMCI', 'LMCI'] AND traj_type = 'declining' THEN 'progressive_mci'
                WHEN stage_id IN ['EMCI', 'LMCI'] AND traj_type = 'stable' THEN 'stable_mci'
                WHEN stage_id = 'CN' AND a_status = 'A+' THEN 'preclinical_ad'
                WHEN stage_id = 'AD' THEN 'ad_unspecified'
                WHEN stage_id IN ['EMCI', 'LMCI'] THEN 'mci_unspecified'
                WHEN stage_id = 'CN' THEN 'control'
                ELSE 'unclassified'
             END as phenotype_type
        
        WHERE phenotype_type <> 'unclassified'
        
        MERGE (phenotype:ClinicalPhenotype {
            phenotype_id: p.ptid + '_phenotype',
            patient_id: p.ptid
        })
        SET phenotype.phenotype_type = phenotype_type,
            phenotype.has_trajectory = traj_type IS NOT NULL,
            phenotype.has_atn = a_status IS NOT NULL,
            phenotype.has_stage = stage_id IS NOT NULL
        
        MERGE (p)-[:HAS_PHENOTYPE]->(phenotype)
        
        RETURN count(DISTINCT phenotype) as count
        """

        try:
            result = self.connector.run_query(phenotype_query)
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.warning(f"Could not create all clinical phenotypes: {e}")
            return 0

    def _create_progression_pathways(self) -> int:
        """Create AD progression pathways based on longitudinal data"""

        query = """
        // Find patients who progressed between stages
        MATCH (p:Patient)-[:HAS_VISIT]->(v1:Visit)-[:HAS_DIAGNOSIS]->(d1:Diagnosis)
        MATCH (p)-[:HAS_VISIT]->(v2:Visit)-[:HAS_DIAGNOSIS]->(d2:Diagnosis)
        WHERE d1.diagnosis_code IN ['CN', 'SMC', 'EMCI', 'LMCI', 'MCI', 'AD']
        AND d2.diagnosis_code IN ['CN', 'SMC', 'EMCI', 'LMCI', 'MCI', 'AD']
        AND d1.diagnosis_code <> d2.diagnosis_code
        AND v1.visit_id < v2.visit_id
        
        // Map diagnosis codes to progression severity
        WITH p, d1, d2,
             CASE d1.diagnosis_code
                WHEN 'CN' THEN 1
                WHEN 'SMC' THEN 2
                WHEN 'EMCI' THEN 3
                WHEN 'LMCI' THEN 4
                WHEN 'MCI' THEN 4
                WHEN 'AD' THEN 5
                ELSE 0
             END as stage1,
             CASE d2.diagnosis_code
                WHEN 'CN' THEN 1
                WHEN 'SMC' THEN 2
                WHEN 'EMCI' THEN 3
                WHEN 'LMCI' THEN 4
                WHEN 'MCI' THEN 4
                WHEN 'AD' THEN 5
                ELSE 0
             END as stage2
        
        WHERE stage2 > stage1  // Only progression, not regression
        
        MERGE (prog:ProgressionPattern {
            pattern_id: p.ptid + '_' + d1.diagnosis_code + '_to_' + d2.diagnosis_code,
            patient_id: p.ptid,
            from_stage: d1.diagnosis_code,
            to_stage: d2.diagnosis_code
        })
        SET prog.progression_type = CASE
            WHEN stage2 - stage1 = 1 THEN 'gradual'
            WHEN stage2 - stage1 > 1 THEN 'rapid'
            ELSE 'unknown'
        END
        
        MERGE (p)-[:FOLLOWS_PROGRESSION]->(prog)
        MERGE (d1)-[pr:PROGRESSED_TO]->(d2)
        SET pr.patient_id = p.ptid

        RETURN count(DISTINCT prog) as count
        """

        try:
            result = self.connector.run_query(query)
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.warning(f"Could not create all progression pathways: {e}")
            return 0


def enhance_knowledge_graph(neo4j_uri: str, neo4j_user: str, neo4j_password: str) -> Dict[str, Any]:
    """Main function to enhance the knowledge graph"""

    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        enhancer = KnowledgeGraphEnhancer(connector)
        results = enhancer.create_semantic_relationships()

        logger.info("\n" + "="*60)
        logger.info("KNOWLEDGE GRAPH ENHANCEMENT COMPLETE")
        logger.info("="*60)

        for relationship_type, count in results.items():
            if relationship_type != 'error':
                logger.info(f"{relationship_type}: {count} created")
            else:
                logger.warning(f"Some operations had errors: {count}")

        return results

    except Exception as e:
        logger.error(f"Knowledge graph enhancement failed: {e}")
        raise
    finally:
        connector.close()