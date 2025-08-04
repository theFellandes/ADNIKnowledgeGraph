"""
Step 1: Database Setup and Schema Creation
Sets up Neo4j database with constraints and indexes
"""

import logging
from typing import Dict, List, Tuple
from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


class DatabaseSetup:
    """Handle database initialization and schema creation"""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector

    def execute(self, clear_database: bool = True) -> Dict[str, bool]:
        """
        Execute database setup

        Args:
            clear_database: Whether to clear existing data

        Returns:
            Dictionary with setup status
        """
        results = {
            'connection_verified': False,
            'database_cleared': False,
            'constraints_created': False,
            'indexes_created': False
        }

        # Verify connection
        logger.info("Verifying database connection...")
        if not self.connector.verify_connection():
            logger.error("Failed to connect to database")
            return results

        results['connection_verified'] = True
        logger.info("✅ Database connection verified")

        # Clear database if requested
        if clear_database:
            logger.info("Clearing existing database...")
            if self.connector.clear_database():
                results['database_cleared'] = True
                logger.info("✅ Database cleared")
            else:
                logger.error("Failed to clear database")
                return results

        # Create constraints
        logger.info("Creating constraints...")
        constraints_created = self._create_constraints()
        results['constraints_created'] = constraints_created

        # Create indexes
        logger.info("Creating indexes...")
        indexes_created = self._create_indexes()
        results['indexes_created'] = indexes_created

        return results

    def _create_constraints(self) -> bool:
        """Create all necessary constraints"""
        constraints = [
            # Core entities
            ("Patient", "ptid"),
            ("Patient", "rid"),
            ("Visit", "visit_id"),
            ("ImagingStudy", "study_id"),
            ("ImageNode", "image_id"),
            ("CognitiveAssessment", "assessment_id"),
            ("Biomarker", "biomarker_id"),
            ("Diagnosis", "diagnosis_id"),
            ("FamilyMember", "member_id"),

            # Volumetric and PET measures
            ("VolumetricMeasure", "measure_id"),
            ("PETBinding", "binding_id"),

            # Reference entities
            ("BrainRegion", "region_id"),
            ("CognitiveTest", "test_id"),
            ("BiomarkerType", "type_id"),
            ("PETTracer", "tracer_id"),

            # Provenance
            ("ProcessingActivity", "activity_id"),
            ("DataSource", "source_id")
        ]

        success_count = 0
        for label, property in constraints:
            if self.connector.create_constraint(label, property):
                success_count += 1

        logger.info(f"Created {success_count}/{len(constraints)} constraints")
        return success_count == len(constraints)

    def _create_indexes(self) -> bool:
        """Create all necessary indexes"""
        indexes = [
            # Patient indexes
            ("Patient", "gender"),
            ("Patient", "age_at_baseline"),
            ("Patient", "education_years"),
            ("Patient", "apoe_genotype"),

            # Visit indexes
            ("Visit", "patient_id"),
            ("Visit", "viscode"),
            ("Visit", "months_from_baseline"),
            ("Visit", "visit_date"),

            # Image indexes
            ("ImagingStudy", "patient_id"),
            ("ImagingStudy", "modality"),
            ("ImageNode", "patient_id"),
            ("ImageNode", "study_id"),
            ("ImageNode", "anatomical_region"),
            ("ImageNode", "pet_tracer"),

            # Assessment indexes
            ("CognitiveAssessment", "patient_id"),
            ("CognitiveAssessment", "visit_id"),
            ("CognitiveAssessment", "test_name"),
            ("CognitiveAssessment", "clinical_significance"),

            # Biomarker indexes
            ("Biomarker", "patient_id"),
            ("Biomarker", "visit_id"),
            ("Biomarker", "biomarker_type"),
            ("Biomarker", "analyte"),
            ("Biomarker", "abnormal_flag"),

            # Diagnosis indexes
            ("Diagnosis", "patient_id"),
            ("Diagnosis", "visit_id"),
            ("Diagnosis", "diagnosis_code"),

            # Family indexes
            ("FamilyMember", "patient_id"),
            ("FamilyMember", "relationship_type"),
            ("FamilyMember", "has_dementia"),

            # Composite indexes
            ("Visit", "patient_id", "months_from_baseline"),
            ("ImageNode", "patient_id", "study_date"),
            ("CognitiveAssessment", "patient_id", "test_name")
        ]

        success_count = 0
        for index_spec in indexes:
            if len(index_spec) == 2:
                label, property = index_spec
                if self.connector.create_index(label, property):
                    success_count += 1
            else:
                # Composite index - create using raw query
                label = index_spec[0]
                properties = index_spec[1:]
                query = f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON ({', '.join(f'n.{p}' for p in properties)})"
                try:
                    self.connector.execute_write_transaction(query)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to create composite index on {label}({properties}): {e}")

        logger.info(f"Created {success_count}/{len(indexes)} indexes")
        return success_count > len(indexes) * 0.8  # Allow some failures

    def create_reference_nodes(self) -> None:
        """Create reference nodes for standardized values"""
        logger.info("Creating reference nodes...")

        # Brain regions
        brain_regions = [
            ("hippocampus", "Hippocampus", "Medial temporal lobe structure"),
            ("cortex", "Cerebral Cortex", "Outer layer of cerebrum"),
            ("ventricles", "Ventricles", "CSF-filled spaces"),
            ("cerebellum", "Cerebellum", "Hindbrain structure"),
            ("frontal_lobe", "Frontal Lobe", "Anterior cerebral lobe"),
            ("temporal_lobe", "Temporal Lobe", "Lateral cerebral lobe"),
            ("parietal_lobe", "Parietal Lobe", "Superior cerebral lobe"),
            ("occipital_lobe", "Occipital Lobe", "Posterior cerebral lobe"),
            ("brainstem", "Brainstem", "Midbrain, pons, medulla"),
            ("thalamus", "Thalamus", "Relay center"),
            ("basal_ganglia", "Basal Ganglia", "Subcortical nuclei"),
            ("whole_brain", "Whole Brain", "Entire brain")
        ]

        query = """
        UNWIND $regions as region
        MERGE (r:BrainRegion {region_id: region.id})
        SET r.name = region.name,
            r.description = region.description
        """

        regions_data = [
            {"id": id, "name": name, "description": desc}
            for id, name, desc in brain_regions
        ]
        self.connector.batch_write(query, regions_data)

        # Cognitive tests
        cognitive_tests = [
            ("MMSE", "Mini-Mental State Examination", 30),
            ("CDR", "Clinical Dementia Rating", None),
            ("ADAS-Cog", "Alzheimer's Disease Assessment Scale - Cognitive", None),
            ("MoCA", "Montreal Cognitive Assessment", 30),
            ("RAVLT", "Rey Auditory Verbal Learning Test", None),
            ("FAQ", "Functional Activities Questionnaire", None)
        ]

        query = """
        UNWIND $tests as test
        MERGE (t:CognitiveTest {test_id: test.id})
        SET t.name = test.name,
            t.max_score = test.max_score
        """

        tests_data = [
            {"id": id, "name": name, "max_score": max_score}
            for id, name, max_score in cognitive_tests
        ]
        self.connector.batch_write(query, tests_data)

        # PET tracers
        pet_tracers = [
            ("FDG", "Fluorodeoxyglucose", "Glucose metabolism"),
            ("AV45", "Florbetapir", "Amyloid imaging"),
            ("FBB", "Florbetaben", "Amyloid imaging"),
            ("PIB", "Pittsburgh Compound B", "Amyloid imaging"),
            ("AV1451", "Flortaucipir", "Tau imaging")
        ]

        query = """
        UNWIND $tracers as tracer
        MERGE (t:PETTracer {tracer_id: tracer.id})
        SET t.name = tracer.name,
            t.target = tracer.target
        """

        tracers_data = [
            {"id": id, "name": name, "target": target}
            for id, name, target in pet_tracers
        ]
        self.connector.batch_write(query, tracers_data)

        logger.info("✅ Reference nodes created")


def execute_database_setup(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                           clear_database: bool = True) -> Dict[str, bool]:
    """
    Main execution function for database setup

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Username
        neo4j_password: Password
        clear_database: Whether to clear existing data

    Returns:
        Setup results
    """
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        setup = DatabaseSetup(connector)
        results = setup.execute(clear_database)

        if all(results.values()) or (not clear_database and results['connection_verified']):
            setup.create_reference_nodes()
            logger.info("✅ Database setup completed successfully")
        else:
            logger.error("Database setup failed")

        return results

    finally:
        connector.close()


if __name__ == "__main__":
    # Test execution
    results = execute_database_setup(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="your_password",
        clear_database=True
    )
    print(f"Setup results: {results}")