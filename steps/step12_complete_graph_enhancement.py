"""
Step 12: Complete Graph Enhancement with Research Paper Implementation
Fixed to work with actual ADNI data structure
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import pandas as pd
import numpy as np
from collections import defaultdict

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


class ResearchBasedGraphEnhancer:
    """Creates complete ADNI knowledge graph based on research paper ontologies"""

    def __init__(self, connector: Neo4jConnector, table_data: Dict[str, pd.DataFrame] = None):
        self.connector = connector
        self.table_data = table_data
        self.stats = {
            'nodes_created': 0,
            'relationships_created': 0,
            'clinical_entities_created': 0,
            'ontology_nodes_created': 0,
            'assessments_linked': 0,
            'biomarkers_linked': 0
        }

    def execute(self) -> Dict[str, Any]:
        """Execute complete graph enhancement based on research papers"""

        logger.info("\n" + "=" * 70)
        logger.info("COMPLETE GRAPH ENHANCEMENT WITH RESEARCH ONTOLOGY")
        logger.info("=" * 70)

        # 1. Create AD-DPC Ontology Structure
        self._create_ad_dpc_ontology()

        # 2. Create Clinical Entities from actual ADNI data
        self._create_clinical_entities_from_adni()

        # 3. Create Cognitive Assessment nodes from ADNI tables
        self._create_cognitive_assessments()

        # 4. Create Diagnosis nodes from DXSUM table
        self._create_diagnosis_nodes()

        # 5. Create Demographic Nodes
        self._create_demographic_entities()

        # 6. Create Genetic Marker Nodes
        self._create_genetic_markers()

        # 7. Link Clinical Assessments
        self._link_clinical_assessments()

        # 8. Create Biomarker Classifications
        self._create_biomarker_classifications()

        # 9. Create Diagnosis Hierarchy
        self._create_diagnosis_hierarchy()

        # 10. Create ATN Framework
        self._create_atn_framework()

        # 11. Create Temporal Network
        self._create_temporal_network()

        # 12. Fix Orphaned Nodes
        self._fix_orphaned_nodes()

        # 13. Create Graph Analytics
        self._create_graph_analytics()

        logger.info(f"\n✅ Graph Enhancement Complete:")
        logger.info(f"   Nodes created: {self.stats['nodes_created']}")
        logger.info(f"   Relationships created: {self.stats['relationships_created']}")
        logger.info(f"   Clinical entities: {self.stats['clinical_entities_created']}")
        logger.info(f"   Ontology nodes: {self.stats['ontology_nodes_created']}")

        return self.stats

    def _create_ad_dpc_ontology(self):
        """Create the AD-DPC ontology structure from the research paper"""
        logger.info("Creating AD-DPC Ontology...")

        try:
            query = """
            MERGE (o:Ontology {ontology_id: 'AD-DPC'})
            SET o.name = 'Alzheimer Disease Data Processing and Cohort',
                o.version = '2.0',
                o.description = 'Comprehensive AD Knowledge Graph Ontology',
                o.created_at = datetime()
            
            MERGE (clinical:Domain {domain_id: 'CLINICAL'})
            SET clinical.name = 'Clinical Domain',
                clinical.description = 'Clinical findings, diagnoses, and assessments'
            
            MERGE (biomarker:Domain {domain_id: 'BIOMARKER'})
            SET biomarker.name = 'Biomarker Domain',
                biomarker.description = 'CSF, blood, and imaging biomarkers'
            
            MERGE (genetic:Domain {domain_id: 'GENETIC'})
            SET genetic.name = 'Genetic Domain',
                genetic.description = 'Genetic markers and risk factors'
            
            MERGE (imaging:Domain {domain_id: 'IMAGING'})
            SET imaging.name = 'Neuroimaging Domain',
                imaging.description = 'MRI, PET, and other imaging modalities'
            
            MERGE (cognitive:Domain {domain_id: 'COGNITIVE'})
            SET cognitive.name = 'Cognitive Domain',
                cognitive.description = 'Cognitive assessments and trajectories'
            
            MERGE (o)-[:HAS_DOMAIN]->(clinical)
            MERGE (o)-[:HAS_DOMAIN]->(biomarker)
            MERGE (o)-[:HAS_DOMAIN]->(genetic)
            MERGE (o)-[:HAS_DOMAIN]->(imaging)
            MERGE (o)-[:HAS_DOMAIN]->(cognitive)
            """

            self.connector.execute_write_transaction(query)
            self.stats['ontology_nodes_created'] += 6
        except Exception as e:
            logger.warning(f"Failed to create AD-DPC ontology: {e}")

    def _create_clinical_entities_from_adni(self):
        """Create clinical entities from actual ADNI data"""
        logger.info("Creating clinical entities from ADNI data...")

        # First, ensure Diagnosis nodes exist
        if self.table_data and 'DXSUM' in self.table_data:
            self._create_diagnosis_nodes()

        # Create ClinicalFinding nodes from existing Diagnosis nodes
        try:
            query = """
            MATCH (d:Diagnosis)
            WHERE d.diagnosis_id IS NOT NULL
            MERGE (cf:ClinicalFinding {
                finding_id: 'cf_' + d.diagnosis_id
            })
            SET cf.finding_type = 'Diagnosis',
                cf.finding_code = d.diagnosis_code,
                cf.finding_text = d.diagnosis_text,
                cf.confidence = COALESCE(d.confidence, 1.0),
                cf.created_at = datetime()
            
            MERGE (d)-[:IS_CLINICAL_FINDING]->(cf)
            
            WITH cf, d
            WHERE d.patient_id IS NOT NULL
            MATCH (p:Patient {ptid: d.patient_id})
            MERGE (p)-[:HAS_CLINICAL_FINDING]->(cf)
            """

            self.connector.execute_write_transaction(query)
            self.stats['clinical_entities_created'] += 1
        except Exception as e:
            logger.warning(f"Failed to create clinical findings: {e}")

    def _create_cognitive_assessments(self):
        """Create CognitiveAssessment nodes from ADNI cognitive test tables"""
        logger.info("Creating cognitive assessments...")

        # Process MMSE data
        if self.table_data and 'MMSE' in self.table_data:
            df = self.table_data['MMSE']
            assessments = []

            for _, row in df.iterrows():
                ptid = str(row['PTID']) if pd.notna(row.get('PTID')) else None
                if not ptid:
                    continue

                viscode = str(row.get('VISCODE2', row.get('VISCODE', 'bl')))
                score = row.get('MMSCORE')

                if pd.notna(score):
                    assessment = {
                        'assessment_id': f"mmse_{ptid}_{viscode}",
                        'patient_id': ptid,
                        'visit_id': f"{ptid}_{viscode}",
                        'test_name': 'MMSE',
                        'total_score': float(score),
                        'clinical_significance': self._get_mmse_significance(score),
                        'source_table': 'MMSE'
                    }
                    assessments.append(assessment)

            if assessments:
                query = """
                UNWIND $batch as ca
                MERGE (n:CognitiveAssessment {assessment_id: ca.assessment_id})
                SET n += ca,
                    n.created_at = datetime()
                """
                self.connector.batch_write(query, assessments, batch_size=500)
                self.stats['clinical_entities_created'] += len(assessments)

        # Process CDR data
        if self.table_data and 'CDR' in self.table_data:
            df = self.table_data['CDR']
            assessments = []

            for _, row in df.iterrows():
                ptid = str(row['PTID']) if pd.notna(row.get('PTID')) else None
                if not ptid:
                    continue

                viscode = str(row.get('VISCODE2', row.get('VISCODE', 'bl')))
                global_score = row.get('CDGLOBAL')
                sob_score = row.get('CDRSB')

                if pd.notna(global_score):
                    assessment = {
                        'assessment_id': f"cdr_{ptid}_{viscode}",
                        'patient_id': ptid,
                        'visit_id': f"{ptid}_{viscode}",
                        'test_name': 'CDR',
                        'total_score': float(global_score),
                        'sob_score': float(sob_score) if pd.notna(sob_score) else None,
                        'clinical_significance': self._get_cdr_significance(global_score),
                        'source_table': 'CDR'
                    }
                    assessments.append(assessment)

            if assessments:
                query = """
                UNWIND $batch as ca
                MERGE (n:CognitiveAssessment {assessment_id: ca.assessment_id})
                SET n += ca,
                    n.created_at = datetime()
                """
                self.connector.batch_write(query, assessments, batch_size=500)
                self.stats['clinical_entities_created'] += len(assessments)

    def _create_diagnosis_nodes(self):
        """Create Diagnosis nodes from DXSUM table"""
        logger.info("Creating diagnosis nodes from DXSUM...")

        if not self.table_data or 'DXSUM' not in self.table_data:
            logger.warning("DXSUM table not found")
            return

        df = self.table_data['DXSUM']
        diagnoses = []

        for _, row in df.iterrows():
            ptid = str(row['PTID']) if pd.notna(row.get('PTID')) else None
            if not ptid:
                continue

            viscode = str(row.get('VISCODE2', row.get('VISCODE', 'bl')))
            diagnosis = row.get('DIAGNOSIS')

            if pd.notna(diagnosis):
                # Map ADNI diagnosis codes
                dx_map = {
                    1: ('CN', 'Cognitively Normal'),
                    2: ('MCI', 'Mild Cognitive Impairment'),
                    3: ('AD', 'Alzheimer Disease'),
                    4: ('MCI', 'MCI'),
                    5: ('AD', 'AD'),
                    6: ('SMC', 'Subjective Memory Concern'),
                    7: ('EMCI', 'Early MCI'),
                    8: ('LMCI', 'Late MCI')
                }

                dx_code, dx_text = dx_map.get(int(diagnosis), ('Unknown', 'Unknown'))

                dx_node = {
                    'diagnosis_id': f"dx_{ptid}_{viscode}",
                    'patient_id': ptid,
                    'visit_id': f"{ptid}_{viscode}",
                    'diagnosis_code': dx_code,
                    'diagnosis_text': dx_text,
                    'confidence': row.get('DXCONFID', 1.0),
                    'source_table': 'DXSUM'
                }
                diagnoses.append(dx_node)

        if diagnoses:
            query = """
            UNWIND $batch as d
            MERGE (n:Diagnosis {diagnosis_id: d.diagnosis_id})
            SET n += d,
                n.created_at = datetime()
            """
            self.connector.batch_write(query, diagnoses, batch_size=500)
            self.stats['clinical_entities_created'] += len(diagnoses)
            logger.info(f"Created {len(diagnoses)} diagnosis nodes")

    def _create_demographic_entities(self):
        """Create demographic nodes and relationships"""
        logger.info("Creating demographic entities...")

        try:
            demo_query = """
            MATCH (p:Patient)
            WHERE p.age_at_baseline IS NOT NULL OR p.gender IS NOT NULL
            MERGE (d:Demographics {
                demo_id: p.ptid + '_demographics'
            })
            SET d.age = p.age_at_baseline,
                d.gender = p.gender,
                d.education_years = p.education_years,
                d.age_group = CASE
                    WHEN p.age_at_baseline < 65 THEN '<65'
                    WHEN p.age_at_baseline < 75 THEN '65-74'
                    WHEN p.age_at_baseline < 85 THEN '75-84'
                    ELSE '85+'
                END
            
            MERGE (p)-[:HAS_DEMOGRAPHICS]->(d)
            """

            self.connector.execute_write_transaction(demo_query)
            self.stats['nodes_created'] += 1
        except Exception as e:
            logger.warning(f"Failed to create demographics: {e}")

    def _create_genetic_markers(self):
        """Create genetic marker nodes"""
        logger.info("Creating genetic markers...")

        try:
            genetic_query = """
            MATCH (p:Patient)
            WHERE p.apoe_genotype IS NOT NULL
            MERGE (gm:GeneticMarker {
                marker_id: p.ptid + '_APOE'
            })
            SET gm.gene = 'APOE',
                gm.genotype = p.apoe_genotype,
                gm.e4_carrier = CASE 
                    WHEN p.apoe_genotype CONTAINS '4' THEN true 
                    ELSE false 
                END,
                gm.risk_level = CASE
                    WHEN p.apoe_genotype CONTAINS '4/4' THEN 'very_high'
                    WHEN p.apoe_genotype CONTAINS '4' THEN 'high'
                    WHEN p.apoe_genotype CONTAINS '2' THEN 'protective'
                    ELSE 'normal'
                END
            
            MERGE (p)-[:HAS_GENETIC_MARKER]->(gm)
            """

            self.connector.execute_write_transaction(genetic_query)
            self.stats['nodes_created'] += 1
        except Exception as e:
            logger.warning(f"Failed to create genetic markers: {e}")

    def _link_clinical_assessments(self):
        """Link clinical assessments with proper null handling"""
        logger.info("Linking clinical assessments...")

        try:
            query = """
            MATCH (ca:CognitiveAssessment)
            WHERE ca.patient_id IS NOT NULL
            MATCH (p:Patient {ptid: ca.patient_id})
            MERGE (p)-[r:UNDERWENT_ASSESSMENT]->(ca)
            SET r.test_name = ca.test_name
            
            WITH ca, p
            WHERE ca.visit_id IS NOT NULL
            MATCH (v:Visit {visit_id: ca.visit_id})
            MERGE (v)-[:INCLUDES_ASSESSMENT]->(ca)
            """

            self.connector.execute_write_transaction(query)
            self.stats['assessments_linked'] += 1
        except Exception as e:
            logger.warning(f"Failed to link some assessments: {e}")

    def _create_biomarker_classifications(self):
        """Create biomarker classification nodes"""
        logger.info("Creating biomarker classifications...")

        try:
            # Create biomarker category nodes
            types_query = """
            MERGE (csf:BiomarkerCategory {category_id: 'CSF'})
            SET csf.name = 'Cerebrospinal Fluid Biomarkers'
            
            MERGE (blood:BiomarkerCategory {category_id: 'BLOOD'})
            SET blood.name = 'Blood-based Biomarkers'
            
            MERGE (genetic:BiomarkerCategory {category_id: 'GENETIC'})
            SET genetic.name = 'Genetic Biomarkers'
            
            MERGE (plasma:BiomarkerCategory {category_id: 'PLASMA'})
            SET plasma.name = 'Plasma Biomarkers'
            """

            self.connector.execute_write_transaction(types_query)

            # Link biomarkers to categories
            link_query = """
            MATCH (b:Biomarker)
            WITH b,
                CASE
                    WHEN b.biomarker_type = 'CSF' THEN 'CSF'
                    WHEN b.biomarker_type IN ['Blood'] THEN 'BLOOD'
                    WHEN b.biomarker_type = 'Plasma' THEN 'PLASMA'
                    WHEN b.biomarker_type = 'Genetic' THEN 'GENETIC'
                    ELSE null
                END as category
            WHERE category IS NOT NULL
            MATCH (c:BiomarkerCategory {category_id: category})
            MERGE (b)-[:BELONGS_TO_CATEGORY]->(c)
            """

            self.connector.execute_write_transaction(link_query)
            self.stats['biomarkers_linked'] += 1
        except Exception as e:
            logger.warning(f"Failed to create biomarker classifications: {e}")

    def _create_diagnosis_hierarchy(self):
        """Create diagnosis hierarchy based on AD progression"""
        logger.info("Creating diagnosis hierarchy...")

        try:
            query = """
            MERGE (cn:DiagnosisStage {stage_id: 'CN'})
            SET cn.name = 'Cognitively Normal',
                cn.order = 1,
                cn.description = 'No cognitive impairment'
            
            MERGE (smc:DiagnosisStage {stage_id: 'SMC'})
            SET smc.name = 'Subjective Memory Concern',
                smc.order = 2,
                smc.description = 'Self-reported memory problems'
            
            MERGE (emci:DiagnosisStage {stage_id: 'EMCI'})
            SET emci.name = 'Early Mild Cognitive Impairment',
                emci.order = 3,
                emci.description = 'Early stage MCI'
            
            MERGE (lmci:DiagnosisStage {stage_id: 'LMCI'})
            SET lmci.name = 'Late Mild Cognitive Impairment',
                lmci.order = 4,
                lmci.description = 'Late stage MCI'
            
            MERGE (ad:DiagnosisStage {stage_id: 'AD'})
            SET ad.name = 'Alzheimer Disease',
                ad.order = 5,
                ad.description = 'Clinical AD diagnosis'
            
            MERGE (cn)-[:CAN_PROGRESS_TO {typical_months: 36}]->(smc)
            MERGE (smc)-[:CAN_PROGRESS_TO {typical_months: 24}]->(emci)
            MERGE (emci)-[:CAN_PROGRESS_TO {typical_months: 18}]->(lmci)
            MERGE (lmci)-[:CAN_PROGRESS_TO {typical_months: 12}]->(ad)
            """

            self.connector.execute_write_transaction(query)
            self.stats['nodes_created'] += 5
        except Exception as e:
            logger.warning(f"Failed to create diagnosis hierarchy: {e}")

    def _create_atn_framework(self):
        """Create ATN (Amyloid-Tau-Neurodegeneration) framework"""
        logger.info("Creating ATN framework...")

        try:
            # Create ATN categories
            categories_query = """
            MERGE (a_pos:ATNCategory {category: 'A+'})
            SET a_pos.name = 'Amyloid Positive',
                a_pos.description = 'Abnormal amyloid biomarkers'
            
            MERGE (a_neg:ATNCategory {category: 'A-'})
            SET a_neg.name = 'Amyloid Negative',
                a_neg.description = 'Normal amyloid biomarkers'
            
            MERGE (t_pos:ATNCategory {category: 'T+'})
            SET t_pos.name = 'Tau Positive',
                t_pos.description = 'Abnormal tau biomarkers'
            
            MERGE (t_neg:ATNCategory {category: 'T-'})
            SET t_neg.name = 'Tau Negative',
                t_neg.description = 'Normal tau biomarkers'
            
            MERGE (n_pos:ATNCategory {category: 'N+'})
            SET n_pos.name = 'Neurodegeneration Positive',
                n_pos.description = 'Evidence of neurodegeneration'
            
            MERGE (n_neg:ATNCategory {category: 'N-'})
            SET n_neg.name = 'Neurodegeneration Negative',
                n_neg.description = 'No neurodegeneration'
            """

            self.connector.execute_write_transaction(categories_query)

            # Create ATN profiles based on biomarkers
            profile_query = """
            MATCH (p:Patient)-[:HAS_BIOMARKER]->(b:Biomarker)
            WHERE b.analyte IN ['ABETA42', 'PTAU181', 'TAU']
            WITH p,
                MAX(CASE WHEN b.analyte = 'ABETA42' AND b.value < 192 THEN 1 ELSE 0 END) as a_pos,
                MAX(CASE WHEN b.analyte = 'PTAU181' AND b.value > 23 THEN 1 ELSE 0 END) as t_pos,
                MAX(CASE WHEN b.analyte = 'TAU' AND b.value > 93 THEN 1 ELSE 0 END) as n_pos
            
            MERGE (atn:ATNProfile {
                profile_id: p.ptid + '_atn'
            })
            SET atn.patient_id = p.ptid,
                atn.a_status = CASE WHEN a_pos = 1 THEN 'A+' ELSE 'A-' END,
                atn.t_status = CASE WHEN t_pos = 1 THEN 'T+' ELSE 'T-' END,
                atn.n_status = CASE WHEN n_pos = 1 THEN 'N+' ELSE 'N-' END
            
            WITH p, atn
            SET atn.profile = atn.a_status + '/' + atn.t_status + '/' + atn.n_status
            MERGE (p)-[:HAS_ATN_PROFILE]->(atn)
            """

            self.connector.execute_write_transaction(profile_query)
            self.stats['nodes_created'] += 6
        except Exception as e:
            logger.warning(f"Failed to create ATN framework: {e}")

    def _create_temporal_network(self):
        """Create temporal event network"""
        logger.info("Creating temporal network...")

        try:
            query = """
            MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)
            WITH p, v ORDER BY v.months_from_baseline
            WITH p, collect(v) as visits
            WHERE size(visits) >= 2
            
            MERGE (tl:Timeline {
                timeline_id: p.ptid + '_timeline'
            })
            SET tl.patient_id = p.ptid,
                tl.start_month = visits[0].months_from_baseline,
                tl.end_month = visits[-1].months_from_baseline,
                tl.visit_count = size(visits)
            
            MERGE (p)-[:HAS_TIMELINE]->(tl)
            """

            self.connector.execute_write_transaction(query)
        except Exception as e:
            logger.warning(f"Failed to create temporal network: {e}")

    def _fix_orphaned_nodes(self):
        """Fix orphaned nodes and create missing relationships"""
        logger.info("Fixing orphaned nodes...")

        queries = [
            # Fix orphaned diagnoses
            """
            MATCH (d:Diagnosis)
            WHERE NOT (d)<-[:HAS_DIAGNOSIS]-(:Patient)
            AND d.patient_id IS NOT NULL
            MATCH (p:Patient {ptid: d.patient_id})
            MERGE (p)-[:HAS_DIAGNOSIS]->(d)
            """,

            # Fix orphaned biomarkers
            """
            MATCH (b:Biomarker)
            WHERE NOT (b)<-[:HAS_BIOMARKER]-(:Patient)
            AND b.patient_id IS NOT NULL
            MATCH (p:Patient {ptid: b.patient_id})
            MERGE (p)-[:HAS_BIOMARKER]->(b)
            """,

            # Fix orphaned assessments
            """
            MATCH (ca:CognitiveAssessment)
            WHERE NOT (ca)<-[:UNDERWENT_ASSESSMENT]-(:Patient)
            AND ca.patient_id IS NOT NULL
            MATCH (p:Patient {ptid: ca.patient_id})
            MERGE (p)-[:UNDERWENT_ASSESSMENT]->(ca)
            """
        ]

        for query in queries:
            try:
                self.connector.execute_write_transaction(query)
            except Exception as e:
                logger.warning(f"Failed to fix some orphaned nodes: {e}")

    def _create_graph_analytics(self):
        """Create graph analytics properties"""
        logger.info("Creating graph analytics...")

        try:
            # Calculate patient centrality
            centrality_query = """
            MATCH (p:Patient)
            OPTIONAL MATCH (p)-[r]-()
            WITH p, count(r) as degree
            SET p.degree_centrality = degree
            """

            self.connector.execute_write_transaction(centrality_query)

            # Count total relationships
            count_query = """
            MATCH ()-[r]->()
            RETURN count(r) as total
            """

            result = self.connector.run_query(count_query)
            if result:
                self.stats['relationships_created'] = result[0]['total']
                logger.info(f"   Total relationships in graph: {result[0]['total']}")
        except Exception as e:
            logger.warning(f"Failed to create graph analytics: {e}")

    def _get_mmse_significance(self, score):
        """Determine clinical significance of MMSE score"""
        if pd.isna(score):
            return None
        score = float(score)
        if score >= 27:
            return 'Normal'
        elif score >= 21:
            return 'Mild impairment'
        elif score >= 10:
            return 'Moderate impairment'
        else:
            return 'Severe impairment'

    def _get_cdr_significance(self, score):
        """Determine clinical significance of CDR score"""
        if pd.isna(score):
            return None
        score = float(score)
        if score == 0:
            return 'Normal'
        elif score == 0.5:
            return 'Questionable'
        elif score == 1:
            return 'Mild'
        elif score == 2:
            return 'Moderate'
        else:
            return 'Severe'


def execute_complete_graph_enhancement(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                                       table_data: Dict[str, pd.DataFrame] = None) -> Dict[str, Any]:
    """Execute complete graph enhancement with research paper implementation"""

    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        enhancer = ResearchBasedGraphEnhancer(connector, table_data)
        results = enhancer.execute()

        return results

    except Exception as e:
        logger.error(f"Graph enhancement failed: {e}")
        raise
    finally:
        connector.close()