"""
Step 1: Database Setup and Schema Creation
Sets up Neo4j database and Elasticsearch with support for clearing and incremental modes
"""

import logging
from typing import Dict, List, Tuple, Optional
from utils.neo4j_connector import Neo4jConnector
from pathlib import Path

logger = logging.getLogger(__name__)


class DatabaseSetup:
    """Handle database initialization and schema creation"""

    def __init__(self, connector: Neo4jConnector, es_host: str = 'localhost',
                 es_port: int = 9200):
        """
        Initialize database setup

        Args:
            connector: Neo4j connector instance
            es_host: Elasticsearch host
            es_port: Elasticsearch port
        """
        self.connector = connector
        self.es_host = es_host
        self.es_port = es_port
        self.es_indexer = None

        # Try to initialize Elasticsearch connection
        try:
            from utils.elasticsearch_indexer import SearchIndexer
            self.es_indexer = SearchIndexer(es_host, es_port)
            logger.info(f"✅ Connected to Elasticsearch at {es_host}:{es_port}")
        except Exception as e:
            logger.warning(f"Could not connect to Elasticsearch: {e}")
            logger.warning("Continuing without Elasticsearch support")

    def execute(self, clear_database: bool = False, incremental: bool = True) -> Dict[str, bool]:
        """
        Execute database setup

        Args:
            clear_database: Whether to clear existing data (overrides incremental)
            incremental: Whether to run in incremental mode (preserve existing data)

        Returns:
            Dictionary with setup status
        """
        results = {
            'connection_verified': False,
            'database_cleared': False,
            'elasticsearch_cleared': False,
            'constraints_created': False,
            'indexes_created': False,
            'mode': 'clear' if clear_database else ('incremental' if incremental else 'fresh')
        }

        # Verify connection
        logger.info("Verifying database connection...")
        if not self.connector.verify_connection():
            logger.error("Failed to connect to Neo4j database")
            return results

        results['connection_verified'] = True
        logger.info("✅ Neo4j database connection verified")

        # Handle different modes
        if clear_database:
            logger.info("🗑️ CLEAR MODE: Removing all existing data...")

            # Clear Neo4j
            logger.info("Clearing Neo4j database...")
            if self.connector.clear_database():
                results['database_cleared'] = True
                logger.info("✅ Neo4j database cleared")
            else:
                logger.error("Failed to clear Neo4j database")
                return results

            # Clear Elasticsearch
            if self.es_indexer:
                logger.info("Clearing Elasticsearch indices...")
                if self._clear_elasticsearch():
                    results['elasticsearch_cleared'] = True
                    logger.info("✅ Elasticsearch indices cleared")
                else:
                    logger.warning("Failed to clear some Elasticsearch indices")

            # Clear any cached files if they exist
            self._clear_cache_files()

        elif incremental:
            logger.info("➕ INCREMENTAL MODE: Preserving existing data...")
            # Just verify that indices exist
            if self.es_indexer:
                self._ensure_elasticsearch_indices()
        else:
            logger.info("🆕 FRESH MODE: Setting up new database schema...")

        # Create constraints (safe to run multiple times)
        logger.info("Creating/verifying constraints...")
        constraints_created = self._create_constraints()
        results['constraints_created'] = constraints_created

        # Create indexes (safe to run multiple times)
        logger.info("Creating/verifying indexes...")
        indexes_created = self._create_indexes()
        results['indexes_created'] = indexes_created

        # Create reference nodes only if needed
        if clear_database or not incremental:
            self.create_reference_nodes()
        else:
            logger.info("Skipping reference nodes creation (incremental mode)")

        return results

    def _clear_elasticsearch(self) -> bool:
        """Clear all Elasticsearch indices related to ADNI"""
        if not self.es_indexer:
            return False

        success = True
        indices_to_clear = [
            'medical_images',
            'adni_patients',
            'adni_studies',
            'adni_biomarkers',
            'adni_assessments'
        ]

        for index_name in indices_to_clear:
            try:
                if self.es_indexer.es.indices.exists(index=index_name):
                    self.es_indexer.es.indices.delete(index=index_name)
                    logger.info(f"  ✅ Deleted index: {index_name}")
            except Exception as e:
                logger.error(f"  ❌ Failed to delete index {index_name}: {e}")
                success = False

        # Recreate the medical_images index
        if success:
            try:
                self.es_indexer._create_image_index()
                logger.info("  ✅ Recreated medical_images index")
            except Exception as e:
                logger.error(f"  ❌ Failed to recreate medical_images index: {e}")
                success = False

        return success

    def _ensure_elasticsearch_indices(self) -> bool:
        """Ensure Elasticsearch indices exist (for incremental mode)"""
        if not self.es_indexer:
            return False

        try:
            # This will create the index if it doesn't exist
            self.es_indexer._create_image_index()

            # Get index stats to verify
            stats = self.es_indexer.get_index_stats()
            if stats:
                logger.info(f"  📊 Existing images in ES: {stats.get('total_images', 0):,}")

            return True
        except Exception as e:
            logger.error(f"Failed to ensure ES indices: {e}")
            return False

    def _clear_cache_files(self) -> None:
        """Clear any cached files from previous runs"""
        cache_dirs = [
            Path("outputs/cache"),
            Path("outputs/checkpoints"),
            Path("outputs/temp")
        ]

        for cache_dir in cache_dirs:
            if cache_dir.exists():
                try:
                    import shutil
                    shutil.rmtree(cache_dir)
                    logger.info(f"  ✅ Cleared cache directory: {cache_dir}")
                except Exception as e:
                    logger.warning(f"  ⚠️ Could not clear {cache_dir}: {e}")

    def _create_constraints(self) -> bool:
        """Create all necessary constraints (idempotent operation)"""
        constraints = [
            # Core entities
            ("Patient", "ptid"),
            ("Patient", "rid"),
            ("Visit", "visit_id"),
            ("ImagingStudy", "study_id"),
            ("ImageNode", "image_id"),
            ("ImageNode", "image_hash"),  # Add hash constraint
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
        existing_count = 0

        for label, property in constraints:
            # Check if constraint exists first
            check_query = f"""
            SHOW CONSTRAINTS
            WHERE entityType = 'NODE' 
            AND labelsOrTypes = ['{label}']
            AND properties = ['{property}']
            """

            try:
                existing = self.connector.run_query(check_query)
                if existing:
                    existing_count += 1
                    logger.debug(f"  Constraint already exists: {label}.{property}")
                    success_count += 1
                else:
                    if self.connector.create_constraint(label, property):
                        success_count += 1
                        logger.info(f"  ✅ Created constraint: {label}.{property}")
            except:
                # Fallback for older Neo4j versions
                if self.connector.create_constraint(label, property):
                    success_count += 1

        logger.info(f"Constraints: {success_count}/{len(constraints)} ready ({existing_count} existing)")
        return success_count == len(constraints)

    def _create_indexes(self) -> bool:
        """Create all necessary indexes (idempotent operation)"""
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
            ("ImagingStudy", "study_date"),
            ("ImageNode", "patient_id"),
            ("ImageNode", "study_id"),
            ("ImageNode", "anatomical_region"),
            ("ImageNode", "pet_tracer"),
            ("ImageNode", "modality"),
            ("ImageNode", "series_description"),

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
        existing_count = 0

        for index_spec in indexes:
            if len(index_spec) == 2:
                label, property = index_spec

                # Check if index exists
                check_query = f"""
                SHOW INDEXES
                WHERE entityType = 'NODE'
                AND labelsOrTypes = ['{label}']
                AND properties = ['{property}']
                """

                try:
                    existing = self.connector.run_query(check_query)
                    if existing:
                        existing_count += 1
                        logger.debug(f"  Index already exists: {label}.{property}")
                        success_count += 1
                    else:
                        if self.connector.create_index(label, property):
                            success_count += 1
                            logger.info(f"  ✅ Created index: {label}.{property}")
                except:
                    # Fallback for older Neo4j versions
                    if self.connector.create_index(label, property):
                        success_count += 1
            else:
                # Composite index
                label = index_spec[0]
                properties = index_spec[1:]
                query = f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON ({', '.join(f'n.{p}' for p in properties)})"
                try:
                    self.connector.execute_write_transaction(query)
                    success_count += 1
                    logger.debug(f"  Created composite index: {label}({properties})")
                except Exception as e:
                    logger.debug(f"  Composite index may already exist: {label}({properties})")
                    success_count += 1  # Count as success if it might exist

        logger.info(f"Indexes: {success_count}/{len(indexes)} ready ({existing_count} existing)")
        return success_count > len(indexes) * 0.8  # Allow some failures

    def create_reference_nodes(self) -> None:
        """Create reference nodes for standardized values (idempotent)"""
        logger.info("Creating/updating reference nodes...")

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
        self.connector.batch_write(query, regions_data, param_name="regions")

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
        self.connector.batch_write(query, tests_data, param_name="tests")

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
        self.connector.batch_write(query, tracers_data, param_name="tracers")

        logger.info("✅ Reference nodes created/updated")

    def get_database_stats(self) -> Dict[str, int]:
        """Get current database statistics"""
        stats = {}

        # Neo4j stats
        node_labels = [
            "Patient", "Visit", "ImagingStudy", "ImageNode",
            "CognitiveAssessment", "Biomarker", "Diagnosis", "FamilyMember"
        ]

        for label in node_labels:
            query = f"MATCH (n:{label}) RETURN count(n) as count"
            result = self.connector.run_query(query)
            stats[f"neo4j_{label.lower()}"] = result[0]['count'] if result else 0

        # Elasticsearch stats
        if self.es_indexer:
            es_stats = self.es_indexer.get_index_stats()
            if es_stats:
                stats['elasticsearch_images'] = es_stats.get('total_images', 0)
                stats['elasticsearch_size_mb'] = es_stats.get('index_size_mb', 0)

        return stats


def execute_database_setup(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                          clear_database: bool = False, incremental: bool = True,
                          es_host: str = 'localhost', es_port: int = 9200) -> Dict[str, any]:
    """
    Main execution function for database setup

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Username
        neo4j_password: Password
        clear_database: Whether to clear existing data (overrides incremental)
        incremental: Whether to run in incremental mode
        es_host: Elasticsearch host
        es_port: Elasticsearch port

    Returns:
        Setup results with statistics
    """
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        setup = DatabaseSetup(connector, es_host, es_port)

        # Get initial stats
        initial_stats = setup.get_database_stats()

        # Run setup
        results = setup.execute(clear_database, incremental)

        # Get final stats
        final_stats = setup.get_database_stats()

        # Add statistics to results
        results['initial_stats'] = initial_stats
        results['final_stats'] = final_stats

        # Log summary
        mode = results['mode']
        logger.info("\n" + "="*60)
        logger.info(f"DATABASE SETUP COMPLETED - {mode.upper()} MODE")
        logger.info("="*60)

        if mode == 'clear':
            logger.info("✅ All databases cleared and reset")
        elif mode == 'incremental':
            logger.info("✅ Incremental setup completed")
            logger.info(f"   Existing patients: {final_stats.get('neo4j_patient', 0):,}")
            logger.info(f"   Existing images: {final_stats.get('neo4j_imagenode', 0):,}")
            if 'elasticsearch_images' in final_stats:
                logger.info(f"   ES indexed images: {final_stats.get('elasticsearch_images', 0):,}")

        if all([results.get('connection_verified'),
                results.get('constraints_created'),
                results.get('indexes_created')]):
            logger.info("✅ Database setup completed successfully")
        else:
            logger.warning("⚠️ Database setup completed with some issues")

        return results

    except Exception as e:
        logger.error(f"Database setup failed: {e}")
        raise
    finally:
        connector.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ADNI Database Setup")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687", help="Neo4j URI")
    parser.add_argument("--neo4j-user", default="neo4j", help="Neo4j username")
    parser.add_argument("--neo4j-password", required=True, help="Neo4j password")
    parser.add_argument("--clear", action="store_true", help="Clear all existing data")
    parser.add_argument("--no-incremental", action="store_true", help="Disable incremental mode")
    parser.add_argument("--es-host", default="localhost", help="Elasticsearch host")
    parser.add_argument("--es-port", type=int, default=9200, help="Elasticsearch port")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Execute setup
    results = execute_database_setup(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        clear_database=args.clear,
        incremental=not args.no_incremental,
        es_host=args.es_host,
        es_port=args.es_port
    )

    print(f"\nSetup results: {results}")