"""
Step 8: Create Comprehensive Relationships (COMPLETE & ENHANCED)
Creates advanced relationships based on AD-DPC ontology and AlzKB research insights
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
        Execute relationship creation with diagnostics

        Returns:
            Dictionary with creation results
        """
        results = {
            'relationships_created': 0,
            'relationship_types': {},
            'errors': [],
            'timing': {},
            'diagnostics': {}
        }

        start_time = datetime.now()

        # Run diagnostics first
        logger.info("Running diagnostics to check available data...")
        self._run_diagnostics(results['diagnostics'])

        # Ensure required reference nodes exist
        self._create_reference_nodes()

        # Create different categories of relationships
        relationship_functions = [
            ("temporal", self._create_temporal_relationships),
            ("clinical_progression", self._create_progression_relationships),
            ("biomarker_correlations", self._create_biomarker_relationships),
            ("imaging_clinical", self._create_imaging_clinical_relationships),
            ("genetic_risk", self._create_genetic_risk_relationships),
            ("multimodal", self._create_multimodal_relationships),
            ("ad_pathways", self._create_ad_pathway_relationships),
            ("research_cohorts", self._create_research_cohort_relationships),
            ("cognitive_trajectories", self._create_cognitive_trajectory_relationships),
            ("family_risk", self._create_family_risk_relationships),
            ("biomarker_pathways", self._create_biomarker_pathway_relationships),
            ("treatment_response", self._create_treatment_response_relationships),
            ("molecular_networks", self._create_molecular_network_relationships),
            ("omics_integration", self._create_omics_integration_relationships),
            ("network_modules", self._create_network_module_relationships),
            ("disease_subtypes", self._create_disease_subtype_relationships),
            ("systems_biology", self._create_systems_biology_relationships),
            ("temporal_biomarker_networks", self._create_temporal_biomarker_networks),
            ("imaging_genomics", self._create_imaging_genomics_relationships),
            ("predictive_models", self._create_predictive_model_relationships)
        ]

        for rel_type, func in relationship_functions:
            try:
                logger.info(f"Creating {rel_type} relationships...")
                count = func()
                results['relationship_types'][rel_type] = count

                if count == 0:
                    logger.warning(f"⚠️  No {rel_type} relationships created - checking why...")
                    self._diagnose_missing_relationships(rel_type)
                else:
                    logger.info(f"✅ Created {count} {rel_type} relationships")

            except Exception as e:
                logger.error(f"Failed to create {rel_type} relationships: {e}")
                results['errors'].append(f"{rel_type}: {str(e)}")

        # Calculate totals
        results['relationships_created'] = sum(results['relationship_types'].values())
        results['timing']['total_seconds'] = (datetime.now() - start_time).total_seconds()

        return results

    def _run_diagnostics(self, diagnostics: Dict[str, Any]) -> None:
        """Run diagnostics to check what data is available"""

        # Check node counts
        node_types = [
            'Patient', 'Visit', 'CognitiveAssessment', 'Biomarker',
            'Diagnosis', 'FamilyMember', 'ImagingStudy', 'ImageNode',
            'VolumetricMeasure', 'PETBinding'
        ]

        diagnostics['node_counts'] = {}
        for node_type in node_types:
            count = self.connector.get_node_count(node_type)
            diagnostics['node_counts'][node_type] = count
            logger.info(f"  {node_type}: {count}")

        # Check for APOE genotype data
        query = "MATCH (p:Patient) WHERE p.apoe_genotype IS NOT NULL RETURN count(p) as count"
        result = self.connector.run_query(query)
        apoe_count = result[0]['count'] if result else 0
        diagnostics['patients_with_apoe'] = apoe_count
        logger.info(f"  Patients with APOE genotype: {apoe_count}")

        # Check for diagnoses
        query = "MATCH (d:Diagnosis) RETURN DISTINCT d.diagnosis_code as code, count(d) as count"
        result = self.connector.run_query(query)
        diagnostics['diagnosis_distribution'] = result if result else []
        if result:
            logger.info(f"  Diagnosis codes found: {[r['code'] for r in result]}")

        # Check for biomarkers
        query = "MATCH (b:Biomarker) RETURN DISTINCT b.analyte as analyte, count(b) as count LIMIT 10"
        result = self.connector.run_query(query)
        diagnostics['biomarker_types'] = result if result else []
        if result:
            logger.info(f"  Biomarker types found: {[r['analyte'] for r in result]}")

    def _diagnose_missing_relationships(self, rel_type: str) -> None:
        """Diagnose why a relationship type returned 0"""

        if rel_type == "clinical_progression":
            # Check if we have diagnoses at different timepoints
            query = """
            MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
            RETURN count(DISTINCT p) as patients_with_dx,
                   count(DISTINCT d.diagnosis_code) as dx_codes
            """
            result = self.connector.run_query(query)
            if result:
                logger.info(f"    → Found {result[0]['patients_with_dx']} patients with diagnoses")
                logger.info(f"    → Found {result[0]['dx_codes']} unique diagnosis codes")
            else:
                logger.info("    → No diagnoses found - need to check Step 6 extraction")

        elif rel_type == "biomarker_correlations":
            # Check if we have biomarkers
            query = "MATCH (b:Biomarker) RETURN count(b) as count"
            result = self.connector.run_query(query)
            count = result[0]['count'] if result else 0
            logger.info(f"    → Found {count} biomarkers total")
            if count == 0:
                logger.info("    → No biomarkers extracted - check Step 6 and table names")

        elif rel_type == "genetic_risk":
            # Check APOE data
            query = "MATCH (p:Patient) WHERE p.apoe_genotype IS NOT NULL RETURN count(p) as count"
            result = self.connector.run_query(query)
            count = result[0]['count'] if result else 0
            logger.info(f"    → Found {count} patients with APOE genotype")
            if count == 0:
                logger.info("    → No APOE data found - check APOERES table in Step 3")

        elif rel_type == "family_risk":
            # Check family members
            query = "MATCH (fm:FamilyMember) RETURN count(fm) as count"
            result = self.connector.run_query(query)
            count = result[0]['count'] if result else 0
            logger.info(f"    → Found {count} family members")
            if count == 0:
                logger.info("    → No family data extracted - check Step 4 and FAMHX tables")

    def _create_reference_nodes(self) -> None:
        """Create necessary reference nodes that may be missing"""
        logger.info("Creating reference nodes...")

        # Create Pathway nodes if they don't exist
        pathways = [
            {
                'pathway_id': 'amyloid_cascade',
                'name': 'Amyloid Cascade',
                'category': 'amyloid',
                'description': 'Amyloid beta accumulation pathway'
            },
            {
                'pathway_id': 'tau_pathology',
                'name': 'Tau Pathology',
                'category': 'tau',
                'description': 'Tau hyperphosphorylation and tangle formation'
            },
            {
                'pathway_id': 'neurodegeneration',
                'name': 'Neurodegeneration',
                'category': 'neurodegeneration',
                'description': 'Neuronal loss and brain atrophy'
            },
            {
                'pathway_id': 'neuroinflammation',
                'name': 'Neuroinflammation',
                'category': 'inflammation',
                'description': 'Inflammatory processes in AD'
            },
            {
                'pathway_id': 'synaptic_dysfunction',
                'name': 'Synaptic Dysfunction',
                'category': 'synaptic',
                'description': 'Loss of synaptic function and plasticity'
            },
            {
                'pathway_id': 'metabolic_dysfunction',
                'name': 'Metabolic Dysfunction',
                'category': 'metabolic',
                'description': 'Brain metabolic changes and insulin resistance'
            }
        ]

        query = """
        UNWIND $pathways as pathway
        MERGE (p:BiologicalPathway {pathway_id: pathway.pathway_id})
        SET p.name = pathway.name,
            p.category = pathway.category,
            p.description = pathway.description
        """

        self.connector.batch_write(query, pathways, param_name="pathways")

        # Create BiomarkerType nodes
        biomarker_types = [
            {
                'type_id': 'csf_abeta42',
                'name': 'CSF Aβ42',
                'category': 'amyloid',
                'specimen_type': 'CSF',
                'measurement_unit': 'pg/mL',
                'normal_range_min': 600
            },
            {
                'type_id': 'csf_tau',
                'name': 'CSF Total Tau',
                'category': 'tau',
                'specimen_type': 'CSF',
                'measurement_unit': 'pg/mL',
                'normal_range_max': 400
            },
            {
                'type_id': 'csf_ptau',
                'name': 'CSF p-Tau',
                'category': 'tau',
                'specimen_type': 'CSF',
                'measurement_unit': 'pg/mL',
                'normal_range_max': 80
            },
            {
                'type_id': 'plasma_nfl',
                'name': 'Plasma NFL',
                'category': 'neurodegeneration',
                'specimen_type': 'blood',
                'measurement_unit': 'pg/mL',
                'normal_range_max': 50
            }
        ]

        query = """
        UNWIND $types as type
        MERGE (bt:BiomarkerType {type_id: type.type_id})
        SET bt.name = type.name,
            bt.category = type.category,
            bt.specimen_type = type.specimen_type,
            bt.measurement_unit = type.measurement_unit,
            bt.normal_range_min = type.normal_range_min,
            bt.normal_range_max = type.normal_range_max
        """

        self.connector.batch_write(query, biomarker_types, param_name="types")

    def _create_temporal_relationships(self) -> int:
        """Create temporal relationships between visits and findings"""
        count = 0

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
        WHERE next IS NOT NULL
        WITH a1, next.assessment AS a2, next.delta AS delta
        MERGE (a1)-[r:FOLLOWED_BY {months_delta: delta}]->(a2)
        RETURN count(r) AS count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        # Link consecutive biomarkers
        query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v1:Visit)-[:HAS_BIOMARKER]->(b1:Biomarker)
        MATCH (p)-[:HAS_VISIT]->(v2:Visit)-[:HAS_BIOMARKER]->(b2:Biomarker)
        WHERE v1.months_from_baseline < v2.months_from_baseline
          AND b1.analyte = b2.analyte
          AND NOT (b1)-[:FOLLOWED_BY]->()
        WITH b1, b2, v2.months_from_baseline - v1.months_from_baseline AS months_delta
        ORDER BY b1.biomarker_id, months_delta
        WITH b1, COLLECT({biomarker: b2, delta: months_delta})[0] AS next
        WHERE next IS NOT NULL
        WITH b1, next.biomarker AS b2, next.delta AS delta
        MERGE (b1)-[r:FOLLOWED_BY {months_delta: delta}]->(b2)
        RETURN count(r) AS count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_progression_relationships(self) -> int:
        """Create disease progression relationships"""
        count = 0

        # Create progression relationships between diagnoses
        progressions = [
            ('CN', ['MCI', 'EMCI', 'LMCI'], 'CN_to_MCI'),
            ('MCI', ['AD'], 'MCI_to_AD'),
            ('EMCI', ['LMCI'], 'EMCI_to_LMCI'),
            ('LMCI', ['AD'], 'LMCI_to_AD')
        ]

        for from_dx, to_dx_list, prog_type in progressions:
            query = f"""
            MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d1:Diagnosis {{diagnosis_code: '{from_dx}'}})
            MATCH (p)-[:HAS_DIAGNOSIS]->(d2:Diagnosis)
            WHERE d2.diagnosis_code IN {to_dx_list}
            MATCH (d1)<-[:HAS_DIAGNOSIS]-(v1:Visit)
            MATCH (d2)<-[:HAS_DIAGNOSIS]-(v2:Visit)
            WHERE v1.months_from_baseline < v2.months_from_baseline
            MERGE (d1)-[r:PROGRESSED_TO {{
                progression_type: '{prog_type}',
                months_delta: v2.months_from_baseline - v1.months_from_baseline
            }}]->(d2)
            RETURN count(r) as count
            """

            result = self.connector.run_query(query)
            if result:
                count += result[0].get('count', 0)

        # Create patient progression summary
        query = """
        MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)<-[:HAS_DIAGNOSIS]-(v:Visit)
        WITH p, d, v
        ORDER BY v.months_from_baseline
        WITH p, COLLECT({diagnosis: d, visit: v}) as diagnoses_timeline
        WHERE size(diagnoses_timeline) > 1
        WITH p, 
             diagnoses_timeline[0].diagnosis as first_dx,
             diagnoses_timeline[-1].diagnosis as last_dx,
             diagnoses_timeline[-1].visit.months_from_baseline - diagnoses_timeline[0].visit.months_from_baseline as total_months
        WHERE first_dx.diagnosis_code <> last_dx.diagnosis_code
        MERGE (prog:ProgressionPattern {
            pattern_id: p.ptid + '_progression',
            from_diagnosis: first_dx.diagnosis_code,
            to_diagnosis: last_dx.diagnosis_code,
            duration_months: total_months
        })
        MERGE (p)-[:HAS_PROGRESSION_PATTERN]->(prog)
        RETURN count(prog) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_biomarker_relationships(self) -> int:
        """Create biomarker correlation relationships"""
        count = 0

        # Create amyloid-tau relationships
        query = """
        MATCH (v:Visit)-[:HAS_BIOMARKER]->(amyloid:Biomarker)
        WHERE amyloid.analyte IN ['ABETA42', 'ABETA40']
        MATCH (v)-[:HAS_BIOMARKER]->(tau:Biomarker)
        WHERE tau.analyte IN ['TAU', 'PTAU', 'PTAU181P']
        MERGE (amyloid)-[r:CORRELATES_WITH {
            correlation_type: 'amyloid_tau',
            same_visit: true,
            visit_id: v.visit_id
        }]->(tau)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

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
            count += result[0].get('count', 0)

        # Create biomarker pattern nodes
        query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_BIOMARKER]->(b:Biomarker)
        WHERE b.abnormal_flag = true
        WITH p, b.analyte as analyte, COUNT(DISTINCT v) as abnormal_visits, 
             AVG(b.value) as avg_value, STDEV(b.value) as std_value
        WHERE abnormal_visits >= 2
        MERGE (pattern:BiomarkerPattern {
            pattern_id: p.ptid + '_' + analyte + '_abnormal',
            patient_id: p.ptid,
            analyte: analyte,
            pattern_type: 'persistent_abnormal',
            visit_count: abnormal_visits,
            average_value: avg_value,
            std_deviation: std_value
        })
        MERGE (p)-[:HAS_BIOMARKER_PATTERN]->(pattern)
        RETURN count(pattern) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_imaging_clinical_relationships(self) -> int:
        """Create relationships between imaging and clinical findings"""
        count = 0

        # Link volumetric measures to cognitive scores
        query = """
        MATCH (v:Visit)-[:HAS_VOLUMETRIC_MEASURE]->(vol:VolumetricMeasure)
        WHERE vol.region IN ['hippocampus', 'entorhinal', 'temporal_lobe']
        MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(cog:CognitiveAssessment)
        WHERE cog.test_name IN ['MMSE', 'CDR', 'ADAS', 'MoCA']
        MERGE (vol)-[r:CORRELATES_WITH_COGNITIVE {
            test_name: cog.test_name,
            same_visit: true,
            region: vol.region
        }]->(cog)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        # Link PET binding to diagnosis
        query = """
        MATCH (v:Visit)-[:HAS_PET_BINDING]->(pet:PETBinding)
        MATCH (v)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WHERE pet.abnormal_flag = true
        MERGE (pet)-[r:SUPPORTS_DIAGNOSIS {
            diagnosis_code: d.diagnosis_code,
            tracer: pet.tracer,
            region: pet.region
        }]->(d)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        # Create imaging biomarker nodes
        query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_PET_BINDING]->(pet:PETBinding)
        WITH p, pet.tracer as tracer, 
             AVG(CASE WHEN pet.abnormal_flag THEN pet.suvr ELSE NULL END) as avg_abnormal_suvr,
             COUNT(CASE WHEN pet.abnormal_flag THEN 1 ELSE NULL END) as abnormal_count,
             COUNT(v) as scan_count
        WHERE abnormal_count > 0
        MERGE (ib:ImagingBiomarker {
            biomarker_id: p.ptid + '_' + tracer + '_biomarker',
            patient_id: p.ptid,
            tracer: tracer,
            average_abnormal_suvr: avg_abnormal_suvr,
            abnormal_scan_count: abnormal_count,
            total_scan_count: scan_count,
            positivity_rate: toFloat(abnormal_count) / scan_count,
            status: CASE WHEN toFloat(abnormal_count) / scan_count > 0.5 THEN 'positive' ELSE 'negative' END
        })
        MERGE (p)-[:HAS_IMAGING_BIOMARKER]->(ib)
        RETURN count(ib) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_genetic_risk_relationships(self) -> int:
        """Create genetic risk relationships"""
        count = 0

        # Create genetic risk profiles
        query = """
        MATCH (p:Patient)
        WHERE p.apoe_genotype IS NOT NULL
        WITH p, 
             p.apoe_genotype as genotype,
             CASE 
                WHEN p.apoe_genotype CONTAINS 'E4/E4' THEN 'homozygous_e4'
                WHEN p.apoe_genotype CONTAINS 'E4' THEN 'heterozygous_e4'
                WHEN p.apoe_genotype CONTAINS 'E2' THEN 'protective_e2'
                ELSE 'non_carrier'
             END as apoe_status,
             CASE 
                WHEN p.apoe_genotype CONTAINS 'E4/E4' THEN 'very_high'
                WHEN p.apoe_genotype CONTAINS 'E4' THEN 'high'
                WHEN p.apoe_genotype CONTAINS 'E2' THEN 'low'
                ELSE 'normal'
             END as risk_level
        MERGE (profile:GeneticRiskProfile {
            profile_id: p.ptid + '_genetic_risk',
            patient_id: p.ptid,
            apoe_status: apoe_status,
            apoe_genotype: genotype,
            apoe_risk_category: risk_level
        })
        MERGE (p)-[:HAS_GENETIC_RISK_PROFILE]->(profile)
        RETURN count(profile) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        # Link genetic risk to disease progression
        query = """
        MATCH (p:Patient)-[:HAS_GENETIC_RISK_PROFILE]->(risk:GeneticRiskProfile)
        WHERE risk.apoe_risk_category IN ['high', 'very_high']
        MATCH (p)-[:HAS_PROGRESSION_PATTERN]->(prog:ProgressionPattern)
        WHERE prog.to_diagnosis = 'AD'
        MERGE (risk)-[r:INFLUENCES_PROGRESSION {
            influence_type: 'increases_risk',
            risk_category: risk.apoe_risk_category,
            progression_type: prog.from_diagnosis + '_to_' + prog.to_diagnosis
        }]->(prog)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

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
             COUNT(DISTINCT img) as img_count,
             COLLECT(DISTINCT cog.test_name) as cognitive_tests,
             COLLECT(DISTINCT bio.analyte) as biomarkers,
             COLLECT(DISTINCT img.modality) as imaging_modalities
        WHERE cog_count > 0 AND bio_count > 0 AND img_count > 0
        MERGE (ma:MultimodalAssessment {
            assessment_id: v.visit_id + '_multimodal',
            visit_id: v.visit_id,
            cognitive_count: cog_count,
            biomarker_count: bio_count,
            imaging_count: img_count,
            cognitive_tests: cognitive_tests,
            biomarkers_collected: biomarkers,
            imaging_performed: imaging_modalities,
            completeness_score: toFloat(cog_count + bio_count + img_count) / 10.0
        })
        MERGE (v)-[:HAS_MULTIMODAL_ASSESSMENT]->(ma)
        RETURN count(ma) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_ad_pathway_relationships(self) -> int:
        """Create AD pathophysiology pathway relationships"""
        count = 0

        # Create pathway relationships
        pathway_rels = """
        MATCH (a:BiologicalPathway {pathway_id: 'amyloid_cascade'})
        MATCH (t:BiologicalPathway {pathway_id: 'tau_pathology'})
        MATCH (n:BiologicalPathway {pathway_id: 'neurodegeneration'})
        MATCH (i:BiologicalPathway {pathway_id: 'neuroinflammation'})
        MATCH (s:BiologicalPathway {pathway_id: 'synaptic_dysfunction'})
        MATCH (m:BiologicalPathway {pathway_id: 'metabolic_dysfunction'})
        MERGE (a)-[:TRIGGERS {strength: 0.8}]->(t)
        MERGE (t)-[:LEADS_TO {strength: 0.9}]->(n)
        MERGE (a)-[:INDUCES {strength: 0.7}]->(i)
        MERGE (i)-[:ACCELERATES {strength: 0.7}]->(n)
        MERGE (a)-[:CAUSES {strength: 0.6}]->(s)
        MERGE (s)-[:CONTRIBUTES_TO {strength: 0.8}]->(n)
        MERGE (m)-[:EXACERBATES {strength: 0.5}]->(a)
        MERGE (m)-[:IMPAIRS {strength: 0.6}]->(s)
        """

        self.connector.execute_write_transaction(pathway_rels)

        # Link biomarkers to pathways
        biomarker_pathway_mappings = [
            (['ABETA42', 'ABETA40'], 'amyloid_cascade'),
            (['TAU', 'PTAU', 'PTAU181P'], 'tau_pathology'),
            (['NFL', 'GFAP'], 'neurodegeneration')
        ]

        for analytes, pathway_id in biomarker_pathway_mappings:
            query = f"""
            MATCH (b:Biomarker)
            WHERE b.analyte IN {analytes}
            MATCH (p:BiologicalPathway {{pathway_id: '{pathway_id}'}})
            MERGE (b)-[r:INDICATES_PATHWAY {{
                indication_strength: CASE 
                    WHEN b.abnormal_flag = true THEN 0.9 
                    ELSE 0.3 
                END
            }}]->(p)
            RETURN count(r) as count
            """

            result = self.connector.run_query(query)
            if result:
                count += result[0].get('count', 0)

        return count

    def _create_research_cohort_relationships(self) -> int:
        """Create research cohort relationships for analysis"""
        count = 0

        # Create cohorts based on diagnosis and biomarker status
        query = """
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)<-[:HAS_DIAGNOSIS]-(v:Visit)
        WITH p, d ORDER BY v.months_from_baseline DESC
        WITH p, COLLECT(d)[0] as latest_diagnosis
        OPTIONAL MATCH (p)-[:HAS_GENETIC_RISK_PROFILE]->(gr:GeneticRiskProfile)
        OPTIONAL MATCH (p)-[:HAS_IMAGING_BIOMARKER]->(ib:ImagingBiomarker)
        WITH p, 
             COALESCE(latest_diagnosis.diagnosis_code, 'Unknown') as clinical_group,
             COALESCE(gr.apoe_risk_category, 'unknown') as genetic_risk,
             COALESCE(ib.status, 'unknown') as amyloid_status
        MERGE (cohort:ResearchCohort {
            cohort_id: clinical_group + '_' + genetic_risk + '_' + amyloid_status,
            clinical_group: clinical_group,
            genetic_risk: genetic_risk,
            amyloid_status: amyloid_status
        })
        MERGE (p)-[:BELONGS_TO_COHORT]->(cohort)
        RETURN count(DISTINCT cohort) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_cognitive_trajectory_relationships(self) -> int:
        """Create cognitive trajectory patterns"""
        count = 0

        # Create cognitive trajectory nodes
        query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        WHERE ca.test_name = 'MMSE'
        WITH p, ca.test_name as test, COLLECT({score: ca.total_score, months: v.months_from_baseline}) as scores
        WHERE size(scores) >= 3
        WITH p, test, scores,
             scores[0].score as baseline_score,
             scores[-1].score as final_score,
             scores[-1].months as duration_months,
             (scores[0].score - scores[-1].score) as total_decline
        WITH p, test, baseline_score, final_score, duration_months, total_decline,
             CASE 
                WHEN total_decline <= 0 THEN 'stable'
                WHEN total_decline / toFloat(duration_months) * 12 < 2 THEN 'slow_decline'
                WHEN total_decline / toFloat(duration_months) * 12 < 4 THEN 'moderate_decline'
                ELSE 'rapid_decline'
             END as trajectory_type
        MERGE (traj:CognitiveTrajectory {
            trajectory_id: p.ptid + '_' + test + '_trajectory',
            patient_id: p.ptid,
            test_name: test,
            trajectory_type: trajectory_type,
            baseline_score: baseline_score,
            final_score: final_score,
            total_decline: total_decline,
            duration_months: duration_months,
            annual_decline_rate: CASE 
                WHEN duration_months > 0 THEN total_decline * 12.0 / duration_months 
                ELSE 0 
            END
        })
        MERGE (p)-[:HAS_COGNITIVE_TRAJECTORY]->(traj)
        RETURN count(traj) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_family_risk_relationships(self) -> int:
        """Create family risk relationships"""
        count = 0

        # Link family history to patient risk
        query = """
        MATCH (p:Patient)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember)
        WHERE fm.has_dementia = true
        WITH p, COUNT(fm) as affected_family_members,
             SUM(CASE WHEN fm.relationship_type = 'parent' THEN 1 ELSE 0 END) as affected_parents,
             SUM(CASE WHEN fm.relationship_type = 'sibling' THEN 1 ELSE 0 END) as affected_siblings
        MERGE (fr:FamilyRisk {
            risk_id: p.ptid + '_family_risk',
            patient_id: p.ptid,
            affected_family_members: affected_family_members,
            affected_parents: affected_parents,
            affected_siblings: affected_siblings,
            risk_score: affected_parents * 2.0 + affected_siblings * 1.5,
            risk_category: CASE
                WHEN affected_parents >= 2 THEN 'very_high'
                WHEN affected_parents >= 1 THEN 'high'
                WHEN affected_siblings >= 2 THEN 'moderate'
                WHEN affected_family_members >= 1 THEN 'low'
                ELSE 'none'
            END
        })
        MERGE (p)-[:HAS_FAMILY_RISK]->(fr)
        RETURN count(fr) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_biomarker_pathway_relationships(self) -> int:
        """Create relationships between biomarkers and biological pathways"""
        count = 0

        # Link abnormal biomarker patterns to pathways
        query = """
        MATCH (bp:BiomarkerPattern)
        WHERE bp.pattern_type = 'persistent_abnormal'
        MATCH (pathway:BiologicalPathway)
        WHERE (bp.analyte IN ['ABETA42', 'ABETA40'] AND pathway.pathway_id = 'amyloid_cascade')
           OR (bp.analyte IN ['TAU', 'PTAU'] AND pathway.pathway_id = 'tau_pathology')
           OR (bp.analyte IN ['NFL', 'GFAP'] AND pathway.pathway_id = 'neurodegeneration')
        MERGE (bp)-[r:REFLECTS_PATHWAY {
            pattern_strength: bp.visit_count / 10.0,
            consistency: 1.0 - (bp.std_deviation / bp.average_value)
        }]->(pathway)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_treatment_response_relationships(self) -> int:
        """Create treatment response relationships (placeholder for future drug data)"""
        count = 0

        # This would be implemented when drug treatment data is available
        # For now, create relationships based on diagnosis changes
        query = """
        MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d1:Diagnosis)<-[:HAS_DIAGNOSIS]-(v1:Visit)
        MATCH (p)-[:HAS_DIAGNOSIS]->(d2:Diagnosis)<-[:HAS_DIAGNOSIS]-(v2:Visit)
        WHERE v1.months_from_baseline < v2.months_from_baseline
          AND d1.diagnosis_code = d2.diagnosis_code
          AND v2.months_from_baseline - v1.months_from_baseline >= 12
        WITH p, d1.diagnosis_code as dx, COUNT(*) as stable_visits
        WHERE stable_visits >= 2
        MERGE (resp:TreatmentResponse {
            response_id: p.ptid + '_stable_' + dx,
            patient_id: p.ptid,
            response_type: 'stable_' + LOWER(dx),
            duration_months: stable_visits * 12
        })
        MERGE (p)-[:HAS_TREATMENT_RESPONSE]->(resp)
        RETURN count(resp) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_molecular_network_relationships(self) -> int:
        """Create molecular interaction network relationships based on AlzKB insights"""
        count = 0

        # Create protein-protein interaction network for AD-related proteins
        protein_interactions = [
            ('APP', 'BACE1', 'enzymatic_cleavage', 0.95),
            ('APP', 'PSEN1', 'complex_formation', 0.9),
            ('APP', 'PSEN2', 'complex_formation', 0.85),
            ('MAPT', 'GSK3B', 'phosphorylation', 0.9),
            ('MAPT', 'CDK5', 'phosphorylation', 0.88),
            ('APOE', 'ABETA', 'binding', 0.85),
            ('TREM2', 'APOE', 'regulation', 0.7),
            ('CLU', 'ABETA', 'clearance', 0.75)
        ]

        for protein1, protein2, interaction_type, confidence in protein_interactions:
            query = f"""
            MERGE (p1:Protein {{name: '{protein1}'}})
            MERGE (p2:Protein {{name: '{protein2}'}})
            MERGE (p1)-[r:INTERACTS_WITH {{
                type: '{interaction_type}',
                confidence: {confidence},
                source: 'AlzKB_curated'
            }}]->(p2)
            """
            self.connector.execute_write_transaction(query)
            count += 1

        return count

    def _create_omics_integration_relationships(self) -> int:
        """Create multi-omics integration relationships"""
        count = 0

        # Link genetic variants to expression changes
        query = """
        MATCH (p:Patient)-[:HAS_GENETIC_RISK_PROFILE]->(gr:GeneticRiskProfile)
        WHERE gr.apoe_status CONTAINS 'e4'
        MATCH (p)-[:HAS_VISIT]->(v:Visit)-[:HAS_BIOMARKER]->(b:Biomarker)
        WHERE b.analyte IN ['ABETA42', 'TAU', 'PTAU']
        MERGE (gr)-[r:INFLUENCES_EXPRESSION {
            influence_type: 'genetic_modulation',
            target_molecule: b.analyte
        }]->(b)
        RETURN count(r) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_network_module_relationships(self) -> int:
        """Create disease network module relationships"""
        count = 0

        # Create co-expression modules
        query = """
        MATCH (b1:Biomarker)<-[:HAS_BIOMARKER]-(v:Visit)-[:HAS_BIOMARKER]->(b2:Biomarker)
        WHERE b1.analyte < b2.analyte  // Avoid duplicates
          AND b1.abnormal_flag = true AND b2.abnormal_flag = true
        WITH b1.analyte as marker1, b2.analyte as marker2, COUNT(v) as co_occurrence
        WHERE co_occurrence >= 5
        MERGE (m:NetworkModule {
            module_id: marker1 + '_' + marker2 + '_module',
            type: 'biomarker_co_expression',
            markers: [marker1, marker2],
            co_occurrence_count: co_occurrence
        })
        RETURN count(m) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_disease_subtype_relationships(self) -> int:
        """Create disease subtype relationships based on multi-modal clustering"""
        count = 0

        # Create subtypes based on progression patterns and biomarker profiles
        query = """
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[:HAS_PROGRESSION_PATTERN]->(prog:ProgressionPattern)
        OPTIONAL MATCH (p)-[:HAS_BIOMARKER_PATTERN]->(bio_pattern:BiomarkerPattern)
        OPTIONAL MATCH (p)-[:HAS_COGNITIVE_TRAJECTORY]->(traj:CognitiveTrajectory)
        WITH p,
             COALESCE(prog.to_diagnosis, 'stable') as progression_endpoint,
             COALESCE(bio_pattern.pattern_type, 'normal') as biomarker_profile,
             COALESCE(traj.trajectory_type, 'unknown') as cognitive_trajectory
        WITH progression_endpoint + '_' + biomarker_profile + '_' + cognitive_trajectory as subtype_signature,
             COLLECT(p) as patients
        WHERE SIZE(patients) >= 5
        MERGE (subtype:DiseaseSubtype {
            subtype_id: subtype_signature,
            patient_count: SIZE(patients)
        })
        WITH subtype, patients
        UNWIND patients as patient
        MERGE (patient)-[:BELONGS_TO_SUBTYPE]->(subtype)
        RETURN count(DISTINCT subtype) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_systems_biology_relationships(self) -> int:
        """Create systems biology relationships for network medicine approaches"""
        count = 0

        # Create biological process nodes and relationships
        biological_processes = [
            ('synaptic_transmission', 'Synaptic Transmission', 'cellular'),
            ('protein_aggregation', 'Protein Aggregation', 'molecular'),
            ('microglial_activation', 'Microglial Activation', 'cellular'),
            ('oxidative_stress', 'Oxidative Stress', 'molecular'),
            ('mitochondrial_dysfunction', 'Mitochondrial Dysfunction', 'cellular'),
            ('calcium_homeostasis', 'Calcium Homeostasis', 'molecular')
        ]

        for process_id, name, level in biological_processes:
            query = f"""
            MERGE (bp:BiologicalProcess {{
                process_id: '{process_id}',
                name: '{name}',
                level: '{level}'
            }})
            """
            self.connector.execute_write_transaction(query)

        # Link processes to pathways
        process_pathway_links = [
            ('synaptic_transmission', 'synaptic_dysfunction'),
            ('protein_aggregation', 'amyloid_cascade'),
            ('protein_aggregation', 'tau_pathology'),
            ('microglial_activation', 'neuroinflammation'),
            ('oxidative_stress', 'neurodegeneration'),
            ('mitochondrial_dysfunction', 'metabolic_dysfunction')
        ]

        for process_id, pathway_id in process_pathway_links:
            query = f"""
            MATCH (bp:BiologicalProcess {{process_id: '{process_id}'}})
            MATCH (path:BiologicalPathway {{pathway_id: '{pathway_id}'}})
            MERGE (bp)-[r:CONTRIBUTES_TO]->(path)
            """
            self.connector.execute_write_transaction(query)
            count += 1

        return count

    def _create_temporal_biomarker_networks(self) -> int:
        """Create temporal biomarker networks showing evolution over time"""
        count = 0

        # Create biomarker evolution patterns
        query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v1:Visit)-[:HAS_BIOMARKER]->(b1:Biomarker)
        MATCH (p)-[:HAS_VISIT]->(v2:Visit)-[:HAS_BIOMARKER]->(b2:Biomarker)
        WHERE v1.months_from_baseline < v2.months_from_baseline
          AND b1.analyte = b2.analyte
          AND abs(b2.value - b1.value) / b1.value > 0.2  // 20% change
        WITH p, b1.analyte as biomarker,
             COLLECT({
                 from_month: v1.months_from_baseline,
                 to_month: v2.months_from_baseline,
                 change_rate: (b2.value - b1.value) / (v2.months_from_baseline - v1.months_from_baseline)
             }) as changes
        WHERE SIZE(changes) >= 2
        MERGE (evolution:BiomarkerEvolution {
            evolution_id: p.ptid + '_' + biomarker + '_evolution',
            patient_id: p.ptid,
            biomarker: biomarker,
            change_count: SIZE(changes)
        })
        MERGE (p)-[:HAS_BIOMARKER_EVOLUTION]->(evolution)
        RETURN count(evolution) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_imaging_genomics_relationships(self) -> int:
        """Create imaging-genomics relationships"""
        count = 0

        # Link genetic risk to imaging patterns
        query = """
        MATCH (p:Patient)-[:HAS_GENETIC_RISK_PROFILE]->(gr:GeneticRiskProfile)
        MATCH (p)-[:HAS_VISIT]->(v:Visit)-[:HAS_VOLUMETRIC_MEASURE]->(vol:VolumetricMeasure)
        WHERE gr.apoe_risk_category IN ['high', 'very_high']
          AND vol.region IN ['hippocampus', 'entorhinal']
        WITH gr, vol.region as region, AVG(vol.volume) as avg_volume, COUNT(vol) as measure_count
        WHERE measure_count >= 3
        MERGE (ig:ImagingGenomicsPattern {
            pattern_id: gr.apoe_status + '_' + region,
            genetic_factor: gr.apoe_status,
            brain_region: region,
            average_volume: avg_volume,
            sample_size: measure_count
        })
        MERGE (gr)-[:ASSOCIATED_WITH_IMAGING]->(ig)
        RETURN count(ig) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def _create_predictive_model_relationships(self) -> int:
        """Create relationships for predictive modeling"""
        count = 0

        # Create risk score nodes based on multiple factors
        query = """
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[:HAS_GENETIC_RISK_PROFILE]->(gr:GeneticRiskProfile)
        OPTIONAL MATCH (p)-[:HAS_FAMILY_RISK]->(fr:FamilyRisk)
        OPTIONAL MATCH (p)-[:HAS_BIOMARKER_PATTERN]->(bp:BiomarkerPattern)
        WHERE bp.pattern_type = 'persistent_abnormal'
        WITH p,
             CASE 
                WHEN gr.apoe_risk_category = 'very_high' THEN 3
                WHEN gr.apoe_risk_category = 'high' THEN 2
                WHEN gr.apoe_risk_category = 'normal' THEN 1
                ELSE 0
             END as genetic_score,
             COALESCE(fr.risk_score, 0) as family_score,
             CASE WHEN bp IS NOT NULL THEN 2 ELSE 0 END as biomarker_score
        WITH p, genetic_score + family_score + biomarker_score as total_risk_score
        WHERE total_risk_score > 0
        MERGE (risk:RiskProfile {
            profile_id: p.ptid + '_risk',
            patient_id: p.ptid,
            total_score: total_risk_score,
            risk_category: CASE
                WHEN total_risk_score >= 6 THEN 'very_high'
                WHEN total_risk_score >= 4 THEN 'high'
                WHEN total_risk_score >= 2 THEN 'moderate'
                ELSE 'low'
            END
        })
        MERGE (p)-[:HAS_RISK_PROFILE]->(risk)
        RETURN count(risk) as count
        """

        result = self.connector.run_query(query)
        if result:
            count += result[0].get('count', 0)

        return count

    def create_summary_statistics(self) -> Dict[str, Any]:
        """Create comprehensive summary statistics for the graph"""
        stats = {}

        # Enhanced patient statistics
        query = """
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[:HAS_VISIT]->(v:Visit)
        OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        OPTIONAL MATCH (p)-[:HAS_GENETIC_RISK_PROFILE]->(gr:GeneticRiskProfile)
        WITH p, 
             COUNT(DISTINCT v) AS visit_count,
             COLLECT(DISTINCT d.diagnosis_code) as all_diagnoses,
             gr.apoe_risk_category as genetic_risk
        RETURN 
            COUNT(DISTINCT p) AS total_patients,
            AVG(visit_count) AS avg_visits_per_patient,
            SUM(CASE WHEN 'AD' IN all_diagnoses THEN 1 ELSE 0 END) AS ad_patients,
            SUM(CASE WHEN 'MCI' IN all_diagnoses OR 'EMCI' IN all_diagnoses OR 'LMCI' IN all_diagnoses THEN 1 ELSE 0 END) AS mci_patients,
            SUM(CASE WHEN genetic_risk IN ['high', 'very_high'] THEN 1 ELSE 0 END) AS high_risk_patients,
            AVG(p.age_at_baseline) AS avg_baseline_age
        """

        result = self.connector.run_query(query)
        if result and result[0]:
            stats['patients'] = result[0]

        # Biomarker statistics
        query = """
        MATCH (b:Biomarker)
        RETURN 
            b.analyte as biomarker,
            COUNT(b) as measurements,
            SUM(CASE WHEN b.abnormal_flag = true THEN 1 ELSE 0 END) as abnormal_count,
            AVG(b.value) as avg_value,
            MIN(b.value) as min_value,
            MAX(b.value) as max_value
        ORDER BY measurements DESC
        """

        result = self.connector.run_query(query)
        if result:
            stats['biomarkers'] = result

        # Progression statistics
        query = """
        MATCH (pp:ProgressionPattern)
        RETURN 
            pp.from_diagnosis + ' → ' + pp.to_diagnosis as progression,
            COUNT(pp) as count,
            AVG(pp.duration_months) as avg_duration_months
        ORDER BY count DESC
        """

        result = self.connector.run_query(query)
        if result:
            stats['progressions'] = result

        # Network statistics
        query = """
        MATCH (n)
        WITH labels(n) as node_labels, COUNT(n) as count
        RETURN node_labels[0] as node_type, count
        ORDER BY count DESC
        """

        result = self.connector.run_query(query)
        if result:
            stats['node_distribution'] = result

        # Relationship statistics
        query = """
        MATCH ()-[r]->()
        RETURN type(r) as relationship_type, COUNT(r) as count
        ORDER BY count DESC
        LIMIT 20
        """

        result = self.connector.run_query(query)
        if result:
            stats['relationship_distribution'] = result

        # Graph complexity metrics
        query = """
        MATCH (n)
        WITH COUNT(n) as node_count
        MATCH ()-[r]->()
        WITH node_count, COUNT(r) as edge_count
        RETURN node_count, edge_count, 
               toFloat(edge_count) / node_count as avg_degree,
               toFloat(edge_count) / (node_count * (node_count - 1)) as density
        """

        result = self.connector.run_query(query)
        if result and result[0]:
            stats['graph_metrics'] = result[0]

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
            logger.info(f"  {rel_type:<25}: {count:>10,}")

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