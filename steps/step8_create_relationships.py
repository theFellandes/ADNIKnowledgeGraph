"""
Step 8: Create Comprehensive Relationships
Creates advanced relationships based on AD-DPC ontology and research insights
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from models.relationships import RelationshipType, RelationshipBuilder
from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


class RelationshipCreator:
    """Create comprehensive relationships in the knowledge graph"""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector
        self.relationship_stats = {}

    def execute(self) -> Dict[str, Any]:
        """
        Execute relationship creation

        Returns:
            Dictionary with creation results
        """
        results = {
            'relationships_created': 0,
            'relationship_types': {},
            'errors': [],
            'timing': {}
        }

        start_time = datetime.now()

        # Create different categories of relationships
        logger.info("Creating temporal relationships...")
        temporal_count = self._create_temporal_relationships()
        results['relationship_types']['temporal'] = temporal_count

        logger.info("Creating clinical progression relationships...")
        progression_count = self._create_progression_relationships()
        results['relationship_types']['progression'] = progression_count

        logger.info("Creating biomarker correlation relationships...")
        biomarker_count = self._create_biomarker_relationships()
        results['relationship_types']['biomarker'] = biomarker_count

        logger.info("Creating imaging-clinical relationships...")
        imaging_count = self._create_imaging_clinical_relationships()
        results['relationship_types']['imaging_clinical'] = imaging_count

        logger.info("Creating genetic risk relationships...")
        genetic_count = self._create_genetic_risk_relationships()
        results['relationship_types']['genetic'] = genetic_count

        logger.info("Creating multimodal relationships...")
        multimodal_count = self._create_multimodal_relationships()
        results['relationship_types']['multimodal'] = multimodal_count

        logger.info("Creating AD pathway relationships...")
        pathway_count = self._create_ad_pathway_relationships()
        results['relationship_types']['pathways'] = pathway_count

        logger.info("Creating research cohort relationships...")
        cohort_count = self._create_research_cohort_relationships()
        results['relationship_types']['cohorts'] = cohort_count

        # Calculate totals
        results['relationships_created'] = sum(results['relationship_types'].values())
        results['timing']['total_seconds'] = (datetime.now() - start_time).total_seconds()

        return results

    def _create_temporal_relationships(self) -> int:
        """Create temporal relationships between visits and findings"""
        count = 0

        # Already created in previous steps: Visit PRECEDES Visit
        # Here we add temporal relationships for findings

        # Link consecutive cognitive assessments
        query = """
MATCH (p:Patient)-[:HAS_VISIT]->(v1:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(a1:CognitiveAssessment)
MATCH (p)-[:HAS_VISIT]->(v2:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(a2:CognitiveAssessment)
WHERE v1.months_from_baseline < v2.months_from_baseline
  AND a1.test_name = a2.test_name
  AND NOT (a1)-[:FOLLOWED_BY]->()
WITH a1, a2, v2.months_from_baseline - v1.months_from_baseline AS months_delta
ORDER BY a1.assessment_id, months_delta
WITH a1, COLLECT({assessment: a2, delta: months_delta})[0] AS next
WITH a1, next.assessment AS a2next, next.delta AS delta
MERGE (a1)-[r:FOLLOWED_BY]->(a2next)
SET r.months_delta = delta
RETURN count(r) AS count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        # Link consecutive biomarkers
        query = """
MATCH (p:Patient)-[:HAS_VISIT]->(v1:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(a1:CognitiveAssessment)
MATCH (p)-[:HAS_VISIT]->(v2:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(a2:CognitiveAssessment)
WHERE v1.months_from_baseline < v2.months_from_baseline
  AND a1.test_name = a2.test_name
  AND NOT (a1)-[:FOLLOWED_BY]->()
WITH a1, a2, v2.months_from_baseline - v1.months_from_baseline AS months_delta
ORDER BY a1.assessment_id, months_delta
WITH a1, COLLECT({assessment: a2, delta: months_delta})[0] AS next
WITH a1, next.assessment AS a2next, next.delta AS delta
MERGE (a1)-[r:FOLLOWED_BY]->(a2next)
SET r.months_delta = delta
RETURN count(r) AS count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        return count

    def _create_progression_relationships(self) -> int:
        """Create disease progression relationships"""
        count = 0

        # Create progression relationships between diagnoses
        query = """
        MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d1:Diagnosis)
        MATCH (p)-[:HAS_DIAGNOSIS]->(d2:Diagnosis)
        MATCH (d1)<-[:HAS_DIAGNOSIS]-(v1:Visit)
        MATCH (d2)<-[:HAS_DIAGNOSIS]-(v2:Visit)
        WHERE v1.months_from_baseline < v2.months_from_baseline
          AND d1.diagnosis_code IN ['CN', 'SMC'] 
          AND d2.diagnosis_code IN ['MCI', 'EMCI', 'LMCI']
        MERGE (d1)-[r:PROGRESSED_TO {
            progression_type: 'CN_to_MCI',
            months_delta: v2.months_from_baseline - v1.months_from_baseline
        }]->(d2)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        # MCI to AD progression
        query = """
        MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d1:Diagnosis)
        MATCH (p)-[:HAS_DIAGNOSIS]->(d2:Diagnosis)
        MATCH (d1)<-[:HAS_DIAGNOSIS]-(v1:Visit)
        MATCH (d2)<-[:HAS_DIAGNOSIS]-(v2:Visit)
        WHERE v1.months_from_baseline < v2.months_from_baseline
          AND d1.diagnosis_code IN ['MCI', 'EMCI', 'LMCI']
          AND d2.diagnosis_code = 'AD'
        MERGE (d1)-[r:PROGRESSED_TO {
            progression_type: 'MCI_to_AD',
            months_delta: v2.months_from_baseline - v1.months_from_baseline
        }]->(d2)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        # Create patient progression summary
        query = """
        MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WITH p, d
        ORDER BY d.visit_id
        WITH p, COLLECT(d) as diagnoses
        WHERE size(diagnoses) > 1
        WITH p, diagnoses[0] as first_dx, diagnoses[-1] as last_dx
        WHERE first_dx.diagnosis_code <> last_dx.diagnosis_code
        MERGE (prog:ProgressionPattern {
            pattern_id: p.ptid + '_progression',
            from_diagnosis: first_dx.diagnosis_code,
            to_diagnosis: last_dx.diagnosis_code
        })
        MERGE (p)-[:HAS_PROGRESSION_PATTERN]->(prog)
        RETURN count(prog) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        return count

    def _create_biomarker_relationships(self) -> int:
        """Create biomarker correlation relationships"""
        count = 0

        # Create amyloid-tau relationships
        query = """
        MATCH (v:Visit)-[:HAS_BIOMARKER]->(amyloid:Biomarker {analyte: 'ABETA42'})
        MATCH (v)-[:HAS_BIOMARKER]->(tau:Biomarker)
        WHERE tau.analyte IN ['TAU', 'PTAU', 'PTAU181P']
        MERGE (amyloid)-[r:CORRELATES_WITH {
            correlation_type: 'amyloid_tau',
            same_visit: true
        }]->(tau)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        # Create biomarker-diagnosis relationships
        query = """
        MATCH (v:Visit)-[:HAS_BIOMARKER]->(b:Biomarker)
        MATCH (v)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WHERE b.abnormal_flag = true
        MERGE (b)-[r:ASSOCIATED_WITH_DIAGNOSIS {
            diagnosis_code: d.diagnosis_code,
            same_visit: true
        }]->(d)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        # Create biomarker pattern nodes
        query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_BIOMARKER]->(b:Biomarker)
        WHERE b.abnormal_flag = true
        WITH p, b.analyte as analyte, COUNT(DISTINCT v) as abnormal_visits
        WHERE abnormal_visits >= 2
        MERGE (pattern:BiomarkerPattern {
            pattern_id: p.ptid + '_' + analyte + '_abnormal',
            patient_id: p.ptid,
            analyte: analyte,
            pattern_type: 'persistent_abnormal',
            visit_count: abnormal_visits
        })
        MERGE (p)-[:HAS_BIOMARKER_PATTERN]->(pattern)
        RETURN count(pattern) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        return count

    def _create_imaging_clinical_relationships(self) -> int:
        """Create relationships between imaging and clinical findings"""
        count = 0

        # Link volumetric measures to cognitive scores
        query = """
        MATCH (v:Visit)-[:HAS_VOLUMETRIC_MEASURE]->(vol:VolumetricMeasure)
        MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(cog:CognitiveAssessment)
        WHERE vol.region = 'hippocampus'
          AND cog.test_name IN ['MMSE', 'CDR']
        MERGE (vol)-[r:CORRELATES_WITH_COGNITIVE {
            test_name: cog.test_name,
            same_visit: true
        }]->(cog)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        # Link PET binding to diagnosis
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
        if result:
            count += result[0]['count']

        # Create imaging biomarker nodes
        query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_PET_BINDING]->(pet:PETBinding)
        WHERE pet.abnormal_flag = true
        WITH p, pet.tracer as tracer, AVG(pet.suvr) as avg_suvr, COUNT(v) as scan_count
        WHERE scan_count >= 1
        MERGE (ib:ImagingBiomarker {
            biomarker_id: p.ptid + '_' + tracer + '_biomarker',
            patient_id: p.ptid,
            tracer: tracer,
            average_suvr: avg_suvr,
            scan_count: scan_count,
            status: CASE WHEN avg_suvr > 1.1 THEN 'positive' ELSE 'negative' END
        })
        MERGE (p)-[:HAS_IMAGING_BIOMARKER]->(ib)
        RETURN count(ib) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        return count

    def _create_genetic_risk_relationships(self) -> int:
        """Create genetic risk relationships"""
        count = 0

        # Link APOE status to progression
        query = """
        MATCH (p:Patient)
        WHERE p.apoe_genotype IS NOT NULL
        WITH p, 
             CASE 
                WHEN p.apoe_genotype CONTAINS 'E4/E4' THEN 'homozygous'
                WHEN p.apoe_genotype CONTAINS 'E4' THEN 'heterozygous'
                ELSE 'non_carrier'
             END as apoe_status
        MERGE (risk:GeneticRisk {
            risk_id: p.ptid + '_apoe_risk',
            patient_id: p.ptid,
            gene: 'APOE',
            status: apoe_status,
            risk_level: CASE 
                WHEN apoe_status = 'homozygous' THEN 'very_high'
                WHEN apoe_status = 'heterozygous' THEN 'high'
                ELSE 'normal'
            END
        })
        MERGE (p)-[:HAS_GENETIC_RISK]->(risk)
        RETURN count(risk) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        # Link genetic risk to disease progression
        query = """
        MATCH (p:Patient)-[:HAS_GENETIC_RISK]->(risk:GeneticRisk)
        MATCH (p)-[:HAS_PROGRESSION_PATTERN]->(prog:ProgressionPattern)
        WHERE risk.risk_level IN ['high', 'very_high']
          AND prog.to_diagnosis = 'AD'
        MERGE (risk)-[r:INFLUENCES_PROGRESSION {
            influence_type: 'increases_risk',
            progression_type: prog.from_diagnosis + '_to_' + prog.to_diagnosis
        }]->(prog)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        return count

    def _create_multimodal_relationships(self) -> int:
        """Create relationships across multiple data modalities"""
        count = 0

        # Create multimodal assessment nodes
        query = """
        MATCH (v:Visit)
        OPTIONAL MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(cog:CognitiveAssessment)
        OPTIONAL MATCH (v)-[:HAS_BIOMARKER]->(bio:Biomarker)
        OPTIONAL MATCH (v)-[:HAS_IMAGING]->(img:ImagingStudy)
        WITH v, 
             COUNT(DISTINCT cog) as cog_count,
             COUNT(DISTINCT bio) as bio_count,
             COUNT(DISTINCT img) as img_count
        WHERE cog_count > 0 AND bio_count > 0 AND img_count > 0
        MERGE (ma:MultimodalAssessment {
            assessment_id: v.visit_id + '_multimodal',
            visit_id: v.visit_id,
            cognitive_count: cog_count,
            biomarker_count: bio_count,
            imaging_count: img_count
        })
        MERGE (v)-[:HAS_MULTIMODAL_ASSESSMENT]->(ma)
        RETURN count(ma) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        # Link PET and MRI from same timepoint
        query = """
        MATCH (v:Visit)-[:HAS_IMAGING]->(mri:ImagingStudy {modality: 'MRI'})
        MATCH (v)-[:HAS_IMAGING]->(pet:ImagingStudy {modality: 'PET'})
        MERGE (mri)-[r:COMPLEMENTARY_IMAGING {
            same_visit: true,
            modality_pair: 'MRI_PET'
        }]->(pet)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        return count

    def _create_ad_pathway_relationships(self) -> int:
        """Create AD pathophysiology pathway relationships"""
        count = 0

        # Create pathway nodes
        pathways = [
            {
                'id': 'amyloid_cascade',
                'name': 'Amyloid Cascade',
                'description': 'Amyloid beta accumulation pathway'
            },
            {
                'id': 'tau_pathology',
                'name': 'Tau Pathology',
                'description': 'Tau hyperphosphorylation and tangle formation'
            },
            {
                'id': 'neurodegeneration',
                'name': 'Neurodegeneration',
                'description': 'Neuronal loss and brain atrophy'
            },
            {
                'id': 'neuroinflammation',
                'name': 'Neuroinflammation',
                'description': 'Inflammatory processes in AD'
            },
            {
                'id': 'synaptic_dysfunction',
                'name': 'Synaptic Dysfunction',
                'description': 'Loss of synaptic function and plasticity'
            }
        ]

        query = """
        UNWIND $pathways as pathway
        MERGE (p:Pathway {pathway_id: pathway.id})
        SET p.name = pathway.name,
            p.description = pathway.description
        """

        self.connector.batch_write(query, pathways, param_name="pathways")

        # Create pathway relationships
        pathway_rels = """
        MATCH (a:Pathway {pathway_id: 'amyloid_cascade'})
        MATCH (t:Pathway {pathway_id: 'tau_pathology'})
        MATCH (n:Pathway {pathway_id: 'neurodegeneration'})
        MATCH (i:Pathway {pathway_id: 'neuroinflammation'})
        MATCH (s:Pathway {pathway_id: 'synaptic_dysfunction'})
        MERGE (a)-[:TRIGGERS]->(t)
        MERGE (t)-[:LEADS_TO]->(n)
        MERGE (a)-[:INDUCES]->(i)
        MERGE (i)-[:ACCELERATES]->(n)
        MERGE (a)-[:CAUSES]->(s)
        MERGE (s)-[:CONTRIBUTES_TO]->(n)
        """

        self.connector.execute_write_transaction(pathway_rels)

        # Link biomarkers to pathways
        query = """
        MATCH (b:Biomarker)
        MATCH (p:Pathway)
        WHERE (b.analyte IN ['ABETA42', 'ABETA40'] AND p.pathway_id = 'amyloid_cascade')
           OR (b.analyte IN ['TAU', 'PTAU', 'PTAU181P'] AND p.pathway_id = 'tau_pathology')
           OR (b.analyte IN ['NFL', 'GFAP'] AND p.pathway_id = 'neurodegeneration')
        MERGE (b)-[r:INDICATES_PATHWAY]->(p)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        # Link PET tracers to pathways
        query = """
        MATCH (pet:PETBinding)
        MATCH (p:Pathway)
        WHERE (pet.tracer IN ['AV45', 'PIB'] AND p.pathway_id = 'amyloid_cascade')
           OR (pet.tracer IN ['AV1451', 'MK6240'] AND p.pathway_id = 'tau_pathology')
           OR (pet.tracer = 'FDG' AND p.pathway_id = 'synaptic_dysfunction')
        MERGE (pet)-[r:REVEALS_PATHWAY]->(p)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        return count

    def _create_research_cohort_relationships(self) -> int:
        """Create research cohort relationships for analysis"""
        count = 0

        # Create cohorts based on diagnosis and biomarker status
        query = """
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        OPTIONAL MATCH (p)-[:HAS_GENETIC_RISK]->(gr:GeneticRisk)
        OPTIONAL MATCH (p)-[:HAS_IMAGING_BIOMARKER]->(ib:ImagingBiomarker)
        WITH p, 
             COLLECT(DISTINCT d.diagnosis_code) as diagnoses,
             gr.risk_level as genetic_risk,
             ib.status as imaging_status
        WITH p,
             CASE 
                WHEN 'AD' IN diagnoses THEN 'AD'
                WHEN 'MCI' IN diagnoses OR 'EMCI' IN diagnoses OR 'LMCI' IN diagnoses THEN 'MCI'
                WHEN 'CN' IN diagnoses THEN 'CN'
                ELSE 'Unknown'
             END as clinical_group,
             COALESCE(genetic_risk, 'unknown') as risk_level,
             COALESCE(imaging_status, 'unknown') as amyloid_status
        MERGE (cohort:ResearchCohort {
            cohort_id: clinical_group + '_' + risk_level + '_' + amyloid_status,
            clinical_group: clinical_group,
            genetic_risk: risk_level,
            amyloid_status: amyloid_status
        })
        MERGE (p)-[:BELONGS_TO_COHORT]->(cohort)
        RETURN count(DISTINCT cohort) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        # Create longitudinal cohorts
        query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)
        WITH p, COUNT(DISTINCT v) as visit_count
        WHERE visit_count >= 3
        WITH p,
             CASE 
                WHEN visit_count >= 10 THEN 'long_term'
                WHEN visit_count >= 5 THEN 'medium_term'
                ELSE 'short_term'
             END as follow_up_category
        MERGE (lcohort:LongitudinalCohort {
            cohort_id: follow_up_category + '_follow_up',
            follow_up_type: follow_up_category,
            min_visits: CASE 
                WHEN follow_up_category = 'long_term' THEN 10
                WHEN follow_up_category = 'medium_term' THEN 5
                ELSE 3
            END
        })
        MERGE (p)-[:IN_LONGITUDINAL_COHORT]->(lcohort)
        RETURN count(DISTINCT lcohort) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        # Update cohort statistics
        query = """
        MATCH (c:ResearchCohort)<-[:BELONGS_TO_COHORT]-(p:Patient)
        WITH c, COUNT(p) as patient_count
        SET c.patient_count = patient_count
        RETURN count(c) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0]['count']

        return count

    def create_summary_statistics(self) -> Dict[str, Any]:
        """Create summary statistics for the graph"""
        stats = {}

        # Patient statistics
        query = """
MATCH (p:Patient)
OPTIONAL MATCH (p)-[:HAS_VISIT]->(v:Visit)
WITH p, COUNT(DISTINCT v) AS visit_count

// derive per-patient flags without duplicating rows
OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
OPTIONAL MATCH (p)-[:HAS_GENETIC_RISK]->(gr:GeneticRisk)
WITH p, visit_count,
     MAX(CASE WHEN d.diagnosis_code = 'AD' THEN 1 ELSE 0 END) AS has_ad,
     MAX(CASE WHEN gr.risk_level IN ['high','very_high'] THEN 1 ELSE 0 END) AS is_high_risk

RETURN COUNT(p) AS total_patients,
       SUM(is_high_risk) AS high_risk_patients,
       SUM(has_ad) AS ad_patients,
       AVG(visit_count) AS avg_visits_per_patient
        """

        result = self.connector.run_query(query)
        if result:
            stats['patients'] = result[0]

        # Biomarker statistics
        query = """
        MATCH (b:Biomarker)
        RETURN 
            b.analyte as biomarker,
            COUNT(b) as measurements,
            SUM(CASE WHEN b.abnormal_flag = true THEN 1 ELSE 0 END) as abnormal_count,
            AVG(b.value) as avg_value
        ORDER BY measurements DESC
        """

        result = self.connector.run_query(query)
        if result:
            stats['biomarkers'] = result

        # Progression statistics
        query = """
        MATCH (pp:ProgressionPattern)
        RETURN 
            pp.from_diagnosis + ' -> ' + pp.to_diagnosis as progression,
            COUNT(pp) as count
        ORDER BY count DESC
        """

        result = self.connector.run_query(query)
        if result:
            stats['progressions'] = result

        return stats


def execute_relationship_creation(neo4j_uri: str, neo4j_user: str, neo4j_password: str) -> Dict[str, Any]:
    """
    Main execution function for relationship creation

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Username
        neo4j_password: Password

    Returns:
        Creation results
    """
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        creator = RelationshipCreator(connector)
        results = creator.execute()

        # Get summary statistics
        stats = creator.create_summary_statistics()
        results['summary_stats'] = stats

        logger.info(f"✅ Created {results['relationships_created']:,} relationships")

        # Log breakdown
        logger.info("\nRelationships by type:")
        for rel_type, count in results['relationship_types'].items():
            logger.info(f"  {rel_type:<20}: {count:>10,}")

        return results

    except Exception as e:
        logger.error(f"Relationship creation failed: {e}")
        raise
    finally:
        connector.close()


if __name__ == "__main__":
    # Test execution
    results = execute_relationship_creation(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="your_password"
    )

    print(f"Created {results['relationships_created']} relationships")