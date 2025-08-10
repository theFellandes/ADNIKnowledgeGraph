"""
Research Paper Based Queries for ADNI Knowledge Graph
Implements queries from AD-DPC and AlzKB papers
Fixed version with corrected Cypher queries
"""

import logging
from typing import Dict, List, Any
from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


class ResearchBasedQueries:
    """Execute research paper queries on ADNI knowledge graph"""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector
        self.results = {}

    def execute_all_queries(self) -> Dict[str, Any]:
        """Execute all research-based queries"""

        logger.info("\n" + "=" * 70)
        logger.info("EXECUTING RESEARCH PAPER QUERIES")
        logger.info("=" * 70)

        # 1. Patient Laboratory Findings Query (from paper)
        self._query_patient_lab_findings()

        # 2. ATN Profile Analysis
        self._query_atn_profiles()

        # 3. Disease Progression Patterns
        self._query_progression_patterns()

        # 4. Biomarker Correlations
        self._query_biomarker_correlations()

        # 5. Multi-Modal Data Integration
        self._query_multimodal_assessments()

        # 6. Genetic Risk Analysis
        self._query_genetic_risk()

        # 7. Treatment Response Analysis
        self._query_treatment_responses()

        # 8. Family History Impact
        self._query_family_history_impact()

        # 9. Cognitive Trajectory Analysis
        self._query_cognitive_trajectories()

        # 10. Drug-Gene Interactions (from AlzKB paper)
        self._query_drug_gene_interactions()

        return self.results

    def _query_patient_lab_findings(self):
        """Query from the research paper - return all laboratory findings for a patient"""

        query = """
        // Get a sample patient with biomarkers
        MATCH (p:Patient)-[:HAS_BIOMARKER]->(b:Biomarker)
        WITH p LIMIT 1
        
        // Get all laboratory findings for this patient
        MATCH (p)-[:HAS_BIOMARKER]->(bio:Biomarker)
        WITH p, bio
        ORDER BY bio.viscode
        
        // Also get clinical findings
        OPTIONAL MATCH (p)-[:HAS_CLINICAL_FINDING]->(cf:ClinicalFinding)
        
        // Get demographics
        OPTIONAL MATCH (p)-[:HAS_DEMOGRAPHICS]->(d:Demographics)
        
        // Get ATN profile
        OPTIONAL MATCH (p)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
        
        RETURN p.ptid as patient_id,
               d.age as age,
               d.gender as gender,
               d.education_years as education,
               p.apoe_genotype as apoe,
               atn.profile as atn_status,
               collect(DISTINCT {
                   analyte: bio.analyte,
                   value: bio.value,
                   unit: bio.unit,
                   abnormal: bio.abnormal_flag,
                   viscode: bio.viscode,
                   type: bio.biomarker_type
               }) as biomarkers,
               collect(DISTINCT {
                   finding: cf.finding_text,
                   confidence: cf.confidence
               }) as clinical_findings
        """

        try:
            result = self.connector.run_query(query)
            self.results['patient_lab_findings'] = result

            if result:
                logger.info(f"✅ Patient Lab Findings: Found {len(result[0]['biomarkers'])} biomarkers")
        except Exception as e:
            logger.warning(f"Failed to query patient lab findings: {e}")
            self.results['patient_lab_findings'] = []

    def _query_atn_profiles(self):
        """Analyze ATN profiles and their association with diagnosis"""

        query = """
        MATCH (p:Patient)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
        OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        
        WITH atn.profile as atn_profile,
             collect(DISTINCT d.diagnosis_code) as diagnoses,
             count(DISTINCT p) as patient_count
        
        RETURN atn_profile,
               patient_count,
               diagnoses,
               CASE atn_profile
                   WHEN 'A+/T+/N+' THEN 'High AD likelihood'
                   WHEN 'A+/T+/N-' THEN 'AD pathologic change'  
                   WHEN 'A+/T-/N+' THEN 'AD with neurodegeneration'
                   WHEN 'A+/T-/N-' THEN 'Preclinical AD'
                   WHEN 'A-/T+/N+' THEN 'Non-AD pathology'
                   WHEN 'A-/T-/N+' THEN 'Non-AD neurodegeneration'
                   WHEN 'A-/T+/N-' THEN 'Primary tauopathy'
                   ELSE 'Normal'
               END as interpretation
        ORDER BY patient_count DESC
        """

        try:
            result = self.connector.run_query(query)
            self.results['atn_profiles'] = result

            if result:
                logger.info(f"✅ ATN Profiles: Found {len(result)} distinct profiles")
        except Exception as e:
            logger.warning(f"Failed to query ATN profiles: {e}")
            self.results['atn_profiles'] = []

    def _query_progression_patterns(self):
        """Analyze disease progression patterns - FIXED version"""

        # First check if we have progression relationships
        check_query = """
        MATCH ()-[r:CAN_PROGRESS_TO]->()
        RETURN count(r) as count
        """

        try:
            check_result = self.connector.run_query(check_query)

            if check_result and check_result[0]['count'] > 0:
                # Use DiagnosisStage nodes if they exist
                query = """
                MATCH path = (d1:DiagnosisStage)-[:CAN_PROGRESS_TO*1..3]->(d2:DiagnosisStage)
                WHERE d1.stage_id = 'CN'
                
                WITH [n in nodes(path) | n.stage_id] as progression_path,
                     count(*) as frequency
                
                RETURN progression_path,
                       frequency,
                       size(progression_path) as stages
                ORDER BY frequency DESC
                LIMIT 10
                """
            else:
                # Alternative: analyze actual patient diagnosis changes
                query = """
                MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d1:Diagnosis)
                MATCH (p)-[:HAS_DIAGNOSIS]->(d2:Diagnosis)
                WHERE d1.visit_id < d2.visit_id
                
                WITH p,
                     d1.diagnosis_code as start_dx,
                     d2.diagnosis_code as end_dx,
                     d1.visit_id as start_visit,
                     d2.visit_id as end_visit
                WHERE start_dx <> end_dx
                
                WITH [start_dx, end_dx] as progression_path,
                     count(DISTINCT p) as patient_count
                
                RETURN progression_path,
                       patient_count as frequency,
                       size(progression_path) as stages
                ORDER BY patient_count DESC
                LIMIT 10
                """

            result = self.connector.run_query(query)
            self.results['progression_patterns'] = result

            if result:
                logger.info(f"✅ Progression Patterns: Found {len(result)} patterns")
        except Exception as e:
            logger.warning(f"Failed to query progression patterns: {e}")
            self.results['progression_patterns'] = []

    def _query_biomarker_correlations(self):
        """Analyze correlations between different biomarkers"""

        query = """
        MATCH (p:Patient)-[:HAS_BIOMARKER]->(b1:Biomarker {biomarker_type: 'CSF'})
        MATCH (p)-[:HAS_BIOMARKER]->(b2:Biomarker {biomarker_type: 'CSF'})
        WHERE b1.analyte < b2.analyte  // Avoid duplicates
        AND b1.viscode = b2.viscode    // Same visit
        
        WITH b1.analyte as biomarker1,
             b2.analyte as biomarker2,
             count(*) as pair_count,
             avg(b1.value) as avg_value1,
             avg(b2.value) as avg_value2
        WHERE pair_count >= 10
        
        RETURN biomarker1,
               biomarker2,
               pair_count,
               round(avg_value1, 2) as avg_value1,
               round(avg_value2, 2) as avg_value2
        ORDER BY pair_count DESC
        LIMIT 15
        """

        try:
            result = self.connector.run_query(query)
            self.results['biomarker_correlations'] = result

            if result:
                logger.info(f"✅ Biomarker Correlations: Found {len(result)} correlations")
        except Exception as e:
            logger.warning(f"Failed to query biomarker correlations: {e}")
            self.results['biomarker_correlations'] = []

    def _query_multimodal_assessments(self):
        """Analyze multi-modal assessment completeness"""

        # First check if MultiModalAssessment nodes exist
        check_query = """
        MATCH (mm:MultiModalAssessment)
        RETURN count(mm) as count
        """

        try:
            check_result = self.connector.run_query(check_query)

            if check_result and check_result[0]['count'] > 0:
                query = """
                MATCH (mm:MultiModalAssessment)
                MATCH (v:Visit {visit_id: mm.visit_id})
                MATCH (p:Patient)-[:HAS_VISIT]->(v)
                
                WITH p.ptid as patient_id,
                     avg(mm.completeness_score) as avg_completeness,
                     count(mm) as assessment_count,
                     avg(mm.modality_count) as avg_modalities
                
                RETURN patient_id,
                       round(avg_completeness, 2) as completeness,
                       assessment_count,
                       round(avg_modalities, 1) as avg_modalities
                ORDER BY completeness DESC
                LIMIT 20
                """
            else:
                # Alternative: count different assessment types per patient
                query = """
                MATCH (p:Patient)
                OPTIONAL MATCH (p)-[:UNDERWENT_ASSESSMENT]->(ca:CognitiveAssessment)
                OPTIONAL MATCH (p)-[:HAS_BIOMARKER]->(b:Biomarker)
                OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
                
                WITH p.ptid as patient_id,
                     count(DISTINCT ca) as cognitive_count,
                     count(DISTINCT b) as biomarker_count,
                     count(DISTINCT d) as diagnosis_count
                WHERE (cognitive_count + biomarker_count + diagnosis_count) > 0
                
                WITH patient_id,
                     cognitive_count,
                     biomarker_count,
                     diagnosis_count,
                     CASE 
                         WHEN cognitive_count > 0 THEN 1 ELSE 0 
                     END + CASE 
                         WHEN biomarker_count > 0 THEN 1 ELSE 0 
                     END + CASE 
                         WHEN diagnosis_count > 0 THEN 1 ELSE 0 
                     END as modality_count
                
                RETURN patient_id,
                       modality_count as modalities,
                       cognitive_count,
                       biomarker_count,
                       diagnosis_count
                ORDER BY modality_count DESC
                LIMIT 20
                """

            result = self.connector.run_query(query)
            self.results['multimodal_assessments'] = result

            if result:
                logger.info(f"✅ Multi-Modal Assessments: Analyzed {len(result)} patients")
        except Exception as e:
            logger.warning(f"Failed to query multimodal assessments: {e}")
            self.results['multimodal_assessments'] = []

    def _query_genetic_risk(self):
        """Analyze genetic risk factors and their impact"""

        query = """
        MATCH (p:Patient)-[:HAS_GENETIC_MARKER]->(gm:GeneticMarker)
        OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        OPTIONAL MATCH (p)-[:HAS_BIOMARKER_PROFILE]->(bp:BiomarkerProfile)
        
        WITH gm.risk_level as genetic_risk,
             count(DISTINCT p) as patient_count,
             collect(DISTINCT d.diagnosis_code) as diagnoses,
             avg(bp.risk_score) as avg_biomarker_risk
        
        RETURN genetic_risk,
               patient_count,
               diagnoses,
               round(avg_biomarker_risk, 2) as avg_risk_score
        ORDER BY 
            CASE genetic_risk
                WHEN 'very_high' THEN 1
                WHEN 'high' THEN 2
                WHEN 'normal' THEN 3
                WHEN 'protective' THEN 4
                ELSE 5
            END
        """

        try:
            result = self.connector.run_query(query)
            self.results['genetic_risk'] = result

            if result:
                total_patients = sum(r['patient_count'] for r in result)
                logger.info(f"✅ Genetic Risk: Analyzed {total_patients} patients")
        except Exception as e:
            logger.warning(f"Failed to query genetic risk: {e}")
            self.results['genetic_risk'] = []

    def _query_treatment_responses(self):
        """Analyze treatment responses by drug class"""

        # Check if Drug nodes exist
        check_query = """
        MATCH (d:Drug)
        RETURN count(d) as count
        """

        try:
            check_result = self.connector.run_query(check_query)

            if check_result and check_result[0]['count'] > 0:
                query = """
                MATCH (d:Drug)-[:BELONGS_TO_CLASS]->(dc:DrugClass)
                
                RETURN dc.name as drug_class,
                       collect(d.name) as drugs,
                       count(d) as drug_count
                ORDER BY drug_count DESC
                """
            else:
                # Alternative: return predefined drug classes
                query = """
                MATCH (dc:DrugClass)
                RETURN dc.name as drug_class,
                       dc.description as description,
                       1 as drug_count
                ORDER BY dc.name
                """

            result = self.connector.run_query(query)
            self.results['treatment_responses'] = result

            if result:
                logger.info(f"✅ Treatment Analysis: Found {len(result)} drug classes")
        except Exception as e:
            logger.warning(f"Failed to query treatment responses: {e}")
            self.results['treatment_responses'] = []

    def _query_family_history_impact(self):
        """Analyze impact of family history on disease progression"""

        query = """
        MATCH (p:Patient)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember)
        WHERE fm.has_dementia = true OR fm.ad_status_has_ad = true
        
        WITH p, count(fm) as affected_relatives
        
        OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        OPTIONAL MATCH (p)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
        
        WITH affected_relatives,
             count(DISTINCT p) as patient_count,
             collect(DISTINCT d.diagnosis_code) as diagnoses,
             collect(DISTINCT atn.profile) as atn_profiles
        
        RETURN affected_relatives,
               patient_count,
               diagnoses,
               atn_profiles
        ORDER BY affected_relatives DESC
        """

        try:
            result = self.connector.run_query(query)
            self.results['family_history_impact'] = result

            if result:
                total_patients = sum(r['patient_count'] for r in result)
                logger.info(f"✅ Family History: Analyzed impact on {total_patients} patients")
        except Exception as e:
            logger.warning(f"Failed to query family history impact: {e}")
            self.results['family_history_impact'] = []

    def _query_cognitive_trajectories(self):
        """Analyze cognitive decline trajectories"""

        query = """
        MATCH (p:Patient)-[:UNDERWENT_ASSESSMENT]->(ca:CognitiveAssessment)
        WHERE ca.test_name = 'MMSE' AND ca.total_score IS NOT NULL
        
        WITH p, ca.visit_id as visit_id, ca.total_score as score
        ORDER BY p.ptid, visit_id
        
        WITH p.ptid as patient_id,
             collect({visit: visit_id, score: score}) as trajectory
        WHERE size(trajectory) >= 3
        
        WITH patient_id,
             trajectory,
             trajectory[0].score as baseline_score,
             trajectory[-1].score as final_score,
             size(trajectory) as num_assessments
        WHERE baseline_score IS NOT NULL AND final_score IS NOT NULL
        
        RETURN patient_id,
               baseline_score,
               final_score,
               num_assessments,
               round(baseline_score - final_score, 2) as total_decline,
               CASE
                   WHEN baseline_score - final_score > 10 THEN 'severe'
                   WHEN baseline_score - final_score > 5 THEN 'moderate'
                   WHEN baseline_score - final_score > 0 THEN 'mild'
                   ELSE 'stable'
               END as decline_category
        ORDER BY total_decline DESC
        LIMIT 20
        """

        try:
            result = self.connector.run_query(query)
            self.results['cognitive_trajectories'] = result

            if result:
                logger.info(f"✅ Cognitive Trajectories: Analyzed {len(result)} patients")
        except Exception as e:
            logger.warning(f"Failed to query cognitive trajectories: {e}")
            self.results['cognitive_trajectories'] = []

    def _query_drug_gene_interactions(self):
        """Query drug-gene interactions from AlzKB approach"""

        query = """
        // Find relationships between drugs and genetic markers
        MATCH (gm:GeneticMarker)<-[:HAS_GENETIC_MARKER]-(p:Patient)
        OPTIONAL MATCH (dc:DrugClass)
        
        WITH gm.gene as gene,
             dc.name as drug_class,
             count(DISTINCT p) as patient_count
        WHERE gene IS NOT NULL
        
        RETURN gene,
               drug_class,
               patient_count,
               CASE
                   WHEN gene = 'APOE' AND drug_class = 'Monoclonal Antibodies' 
                   THEN 'Higher risk of ARIA'
                   WHEN gene = 'APOE' AND drug_class = 'Cholinesterase Inhibitors'
                   THEN 'Variable response'
                   ELSE 'Standard response'
               END as interaction_note
        ORDER BY patient_count DESC
        LIMIT 10
        """

        try:
            result = self.connector.run_query(query)
            self.results['drug_gene_interactions'] = result

            if result:
                logger.info(f"✅ Drug-Gene Interactions: Found {len(result)} interactions")
        except Exception as e:
            logger.warning(f"Failed to query drug-gene interactions: {e}")
            self.results['drug_gene_interactions'] = []

    def get_summary_statistics(self) -> Dict[str, Any]:
        """Get summary statistics from all queries"""

        stats_query = """
        MATCH (n)
        WITH labels(n)[0] as label, count(n) as count
        WHERE label IN ['Patient', 'Biomarker', 'Diagnosis', 'CognitiveAssessment', 
                       'ClinicalFinding', 'GeneticMarker', 'ATNProfile', 
                       'Drug', 'BiologicalPathway', 'Demographics', 'Visit',
                       'BiomarkerProfile', 'DiagnosisStage']
        RETURN label, count
        ORDER BY count DESC
        """

        try:
            node_stats = self.connector.run_query(stats_query)
        except Exception as e:
            logger.warning(f"Failed to get node statistics: {e}")
            node_stats = []

        relationship_query = """
        MATCH ()-[r]->()
        RETURN type(r) as relationship, count(r) as count
        ORDER BY count DESC
        LIMIT 15
        """

        try:
            rel_stats = self.connector.run_query(relationship_query)
        except Exception as e:
            logger.warning(f"Failed to get relationship statistics: {e}")
            rel_stats = []

        return {
            'node_statistics': node_stats,
            'relationship_statistics': rel_stats
        }


def execute_research_queries(neo4j_uri: str, neo4j_user: str, neo4j_password: str) -> Dict[str, Any]:
    """Execute all research-based queries"""

    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        query_executor = ResearchBasedQueries(connector)
        results = query_executor.execute_all_queries()

        # Add summary statistics
        results['summary'] = query_executor.get_summary_statistics()

        logger.info("\n" + "=" * 70)
        logger.info("RESEARCH QUERIES COMPLETE")
        logger.info("=" * 70)

        successful_queries = 0
        for query_name, query_results in results.items():
            if query_name != 'summary' and query_results:
                successful_queries += 1
                if isinstance(query_results, list):
                    logger.info(f"  {query_name}: {len(query_results)} results")
                else:
                    logger.info(f"  {query_name}: completed")

        logger.info(f"\n✅ Successfully executed {successful_queries} queries")

        return results

    except Exception as e:
        logger.error(f"Research queries failed: {e}")
        raise
    finally:
        connector.close()