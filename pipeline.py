"""
ADNI Knowledge Graph Pipeline
Main orchestrator for building a comprehensive Alzheimer's Disease knowledge graph
"""

import logging
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import json
import yaml

# Import all pipeline steps
from steps.step1_database_setup import execute_database_setup
from steps.step2_load_tables import execute_table_loading
from steps.step3_create_patients import execute_patient_creation
from steps.step4_extract_family import execute_family_extraction
from steps.step5_process_images import execute_image_processing
from steps.step6_extract_findings import execute_findings_extraction
from steps.step7_batch_insert import execute_batch_insertion
from steps.step8_create_relationships import execute_relationship_creation
from utils.quality_aware_logger import QualityAwarePipeline

LOG_FMT = (
    "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
)

# Configure logging
def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    """Set up logging configuration"""
    log_format = "% (asctime)s - %(name)s - %(levelname)s - %(message)s"

    handlers = [logging.StreamHandler(sys.stdout)]

    if log_file:
        file_handler = logging.FileHandler(log_file)
        handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=LOG_FMT,
        handlers=handlers
    )


class ADNIPipeline:
    """Main pipeline orchestrator for ADNI knowledge graph"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize pipeline with configuration

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.results = {}
        self.start_time = None
        self.logger = logging.getLogger(__name__)

        # Validate configuration
        self._validate_config()

        # Create output directory
        self.output_dir = Path(config.get('output_dir', 'outputs'))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _validate_config(self):
        """Validate required configuration parameters"""
        required = ['neo4j_uri', 'neo4j_user', 'neo4j_password', 'base_path']

        for param in required:
            if param not in self.config:
                raise ValueError(f"Missing required configuration parameter: {param}")

        # Validate paths exist
        base_path = Path(self.config['base_path'])
        if not base_path.exists():
            raise ValueError(f"Base path does not exist: {base_path}")

        tables_path = base_path / "Tables"
        if not tables_path.exists():
            raise ValueError(f"Tables directory not found: {tables_path}")

    def run(self) -> Dict[str, Any]:
        """
        Execute the complete pipeline

        Returns:
            Dictionary with pipeline results
        """
        self.start_time = datetime.now()
        self.logger.info("=" * 70)
        self.logger.info("ADNI KNOWLEDGE GRAPH PIPELINE")
        self.logger.info("=" * 70)
        self.logger.info(f"Start time: {self.start_time}")
        self.logger.info(f"Configuration: {self._safe_config()}")

        try:
            # Step 1: Database Setup
            if self.config.get('run_database_setup', True):
                self._run_step(1, "Database Setup", self._execute_database_setup)

            # Step 2: Load Tables
            if self.config.get('run_table_loading', True):
                self._run_step(2, "Load Tables", self._execute_table_loading)

            # Step 3: Create Patients
            if self.config.get('run_patient_creation', True):
                self._run_step(3, "Create Patients", self._execute_patient_creation)

            # Step 4: Extract Family
            if self.config.get('run_family_extraction', True):
                self._run_step(4, "Extract Family", self._execute_family_extraction)

            # Step 5: Process Images
            if self.config.get('run_image_processing', True):
                self._run_step(5, "Process Images", self._execute_image_processing)

            # Step 6: Extract Findings
            if self.config.get('run_findings_extraction', True):
                self._run_step(6, "Extract Findings", self._execute_findings_extraction)

            # Step 7: Batch Insert
            if self.config.get('run_batch_insertion', True):
                self._run_step(7, "Batch Insert", self._execute_batch_insertion)

            # Step 8: Create Relationships
            if self.config.get('run_relationship_creation', True):
                self._run_step(8, "Create Relationships", self._execute_relationship_creation)

            # Generate final report
            self._generate_final_report()

            # Save results
            self._save_results()

            end_time = datetime.now()
            duration = end_time - self.start_time

            self.logger.info("=" * 70)
            self.logger.info("PIPELINE COMPLETED SUCCESSFULLY")
            self.logger.info(f"End time: {end_time}")
            self.logger.info(f"Total duration: {duration}")
            self.logger.info("=" * 70)

            return self.results

        except Exception as e:
            self.logger.error(f"Pipeline failed: {e}", exc_info=True)
            self.results['error'] = str(e)
            self.results['status'] = 'failed'
            raise

    def _run_step(self, step_num: int, step_name: str, step_function):
        """Run a single pipeline step"""
        self.logger.info(f"\n{'=' * 60}")
        self.logger.info(f"STEP {step_num}: {step_name.upper()}")
        self.logger.info(f"{'=' * 60}")

        start = datetime.now()

        try:
            result = step_function()
            duration = (datetime.now() - start).total_seconds()

            self.results[f'step{step_num}_{step_name.lower().replace(" ", "_") }'] = {
                'status': 'success',
                'duration_seconds': duration,
                'result': result
            }

            self.logger.info(f"✅ {step_name} completed in {duration:.2f} seconds")

        except Exception as e:
            self.logger.error(f"❌ {step_name} failed: {e}")
            self.results[f'step{step_num}_{step_name.lower().replace(" ", "_") }'] = {
                'status': 'failed',
                'error': str(e)
            }
            raise

    def _execute_database_setup(self) -> Dict[str, Any]:
        """Execute database setup step"""
        return execute_database_setup(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
            clear_database=self.config.get('clear_database', False)
        )

    def _execute_table_loading(self) -> Dict[str, Any]:
        """Execute table loading step"""
        tables_path = Path(self.config['base_path']) / "Tables"
        result = execute_table_loading(str(tables_path))

        # Store table data for subsequent steps
        self.table_data = result['table_data']
        self.patient_ids = result['patient_ids']

        return result

    def _execute_patient_creation(self) -> Dict[str, Any]:
        """Execute patient creation step"""
        if not hasattr(self, 'table_data'):
            raise ValueError("Table data not loaded. Run table loading step first.")

        return execute_patient_creation(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
            table_data=self.table_data
        )

    def _execute_family_extraction(self) -> Dict[str, Any]:
        """Execute family extraction step"""
        if not hasattr(self, 'table_data'):
            raise ValueError("Table data not loaded. Run table loading step first.")

        return execute_family_extraction(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
            table_data=self.table_data
        )

    def _execute_image_processing(self) -> Dict[str, Any]:
        """Execute image processing step"""
        # Check if we should use external storage (new default)
        use_external_storage = self.config.get('use_external_storage', True)

        if use_external_storage:
            self.logger.info("📁 Using external storage for images")

            # Try to import and use the external storage version
            try:
                # Import from correct path
                from steps.step5_process_images_external import execute_image_processing_external

                # Get storage configuration
                storage_config = self.config.get('image_storage', {})
                storage_path = storage_config.get('storage_path')

                if not storage_path:
                    # Default storage path
                    storage_path = str(Path(self.config['base_path']) / '../outputs/image_store')

                # Execute with external storage
                result = execute_image_processing_external(
                    neo4j_uri=self.config['neo4j_uri'],
                    neo4j_user=self.config['neo4j_user'],
                    neo4j_password=self.config['neo4j_password'],
                    base_path=self.config['base_path'],
                    storage_path=storage_path,
                    storage_config=storage_config,
                    max_workers=self.config.get('max_workers', 8)
                )

                # Log storage statistics
                if 'storage_size_mb' in result:
                    self.logger.info(f"📊 Image storage size: {result['storage_size_mb']:.2f} MB")
                if 'quality_metrics' in result:
                    metrics = result['quality_metrics']
                    if metrics.get('avg_snr'):
                        self.logger.info(f"📈 Average image SNR: {metrics['avg_snr']:.2f}")

                # Store processor for batch insertion
                self.image_processor = result.get('processor')
                return result

            except ImportError as e:
                self.logger.warning(f"External storage module not found: {e}")
                self.logger.warning("Falling back to original image processing (blob storage)")

                # Fall back to original image processing
                try:
                    from steps.step5_process_images import execute_image_processing

                    result = execute_image_processing(
                        neo4j_uri=self.config['neo4j_uri'],
                        neo4j_user=self.config['neo4j_user'],
                        neo4j_password=self.config['neo4j_password'],
                        base_path=self.config['base_path'],
                        store_blobs=self.config.get('store_image_blobs', False),
                        max_workers=self.config.get('max_workers', 8)
                    )

                    # Store processor for batch insertion
                    self.image_processor = result.get('processor')
                    return result

                except ImportError as e2:
                    self.logger.error(f"Could not import any image processing module: {e2}")
                    # Return minimal result to allow pipeline to continue
                    return {
                        'mri_processed': 0,
                        'pet_processed': 0,
                        'studies_created': 0,
                        'images_created': 0,
                        'images_stored': 0,
                        'storage_size_mb': 0,
                        'errors': [str(e), str(e2)]
                    }
        else:
            # Use original blob storage (not recommended)
            self.logger.warning("⚠️  Using blob storage (not recommended for production)")
            self.logger.warning("Consider setting 'use_external_storage: true' in config.yaml")

            try:
                from steps.step5_process_images import execute_image_processing

                result = execute_image_processing(
                    neo4j_uri=self.config['neo4j_uri'],
                    neo4j_user=self.config['neo4j_user'],
                    neo4j_password=self.config['neo4j_password'],
                    base_path=self.config['base_path'],
                    store_blobs=self.config.get('store_image_blobs', True),
                    max_workers=self.config.get('max_workers', 8)
                )

                # Store processor for batch insertion
                self.image_processor = result.get('processor')
                return result

            except ImportError as e:
                self.logger.error(f"Could not import image processing module: {e}")
                # Return minimal result to allow pipeline to continue
                return {
                    'mri_processed': 0,
                    'pet_processed': 0,
                    'studies_created': 0,
                    'images_created': 0,
                    'images_stored': 0,
                    'storage_size_mb': 0,
                    'errors': [str(e)]
                }

    def _execute_findings_extraction(self) -> Dict[str, Any]:
        """Execute findings extraction step"""
        if not hasattr(self, 'table_data'):
            raise ValueError("Table data not loaded. Run table loading step first.")

        result = execute_findings_extraction(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
            table_data=self.table_data
        )

        # Store extractor for batch insertion
        self.findings_extractor = result.get('extractor')

        return result

    def _execute_batch_insertion(self) -> Dict[str, Any]:
        """Execute batch insertion step"""
        # Prepare data objects
        data_objects = {}

        if hasattr(self, 'image_processor'):
            data_objects['image_processor'] = self.image_processor

        if hasattr(self, 'findings_extractor'):
            data_objects['findings_extractor'] = self.findings_extractor

        if not data_objects:
            raise ValueError("No data to insert. Run processing steps first.")

        return execute_batch_insertion(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
            data_objects=data_objects
        )

    def _execute_relationship_creation(self) -> Dict[str, Any]:
        """Execute relationship creation step"""
        return execute_relationship_creation(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password']
        )

    def _generate_final_report(self):
        """Generate comprehensive final report"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("FINAL PIPELINE REPORT")
        self.logger.info("=" * 70)

        # Overall statistics
        total_nodes = 0
        total_relationships = 0

        # Collect statistics from each step
        stats = {
            'patients': 0,
            'visits': 0,
            'family_members': 0,
            'images': 0,
            'images_stored': 0,
            'storage_size_mb': 0,
            'cognitive_assessments': 0,
            'biomarkers': 0,
            'diagnoses': 0,
            'relationships': 0
        }

        # Extract counts from results
        if 'step3_create_patients' in self.results:
            step3 = self.results['step3_create_patients']['result']
            stats['patients'] = step3.get('patients_created', 0)
            stats['visits'] = step3.get('visits_created', 0)

        if 'step4_extract_family' in self.results:
            step4 = self.results['step4_extract_family']['result']
            stats['family_members'] = step4.get('family_members_created', 0)

        if 'step5_process_images' in self.results:
            step5 = self.results['step5_process_images']['result']
            stats['images'] = step5.get('images_created', 0)
            stats['images_stored'] = step5.get('images_stored', 0)
            stats['storage_size_mb'] = step5.get('storage_size_mb', 0)

        if 'step6_extract_findings' in self.results:
            step6 = self.results['step6_extract_findings']['result']
            stats['cognitive_assessments'] = step6.get('cognitive_assessments', 0)
            stats['biomarkers'] = step6.get('biomarkers', 0)
            stats['diagnoses'] = step6.get('diagnoses', 0)

        if 'step8_create_relationships' in self.results:
            step8 = self.results['step8_create_relationships']['result']
            stats['relationships'] = step8.get('relationships_created', 0)

        # Calculate totals
        total_nodes = sum([stats[k] for k in stats.keys() if k not in ['relationships', 'storage_size_mb']])
        total_relationships = stats['relationships']

        # Log report
        self.logger.info("\n📊 OVERALL STATISTICS:")
        self.logger.info(f"Total Nodes Created: {total_nodes:,}")
        self.logger.info(f"Total Relationships Created: {total_relationships:,}")

        self.logger.info("\n📋 DETAILED BREAKDOWN:")
        self.logger.info(f"  Patients:              {stats['patients']:>10,}")
        self.logger.info(f"  Visits:                {stats['visits']:>10,}")
        self.logger.info(f"  Family Members:        {stats['family_members']:>10,}")
        self.logger.info(f"  Images:                {stats['images']:>10,}")

        # Only show storage stats if using external storage
        if stats['images_stored'] > 0:
            self.logger.info(f"  Images Stored:         {stats['images_stored']:>10,}")
            self.logger.info(f"  Storage Size:          {stats['storage_size_mb']:>10.2f} MB")

        self.logger.info(f"  Cognitive Assessments: {stats['cognitive_assessments']:>10,}")
        self.logger.info(f"  Biomarkers:            {stats['biomarkers']:>10,}")
        self.logger.info(f"  Diagnoses:             {stats['diagnoses']:>10,}")

        # Step timings
        self.logger.info("\n⏱️  STEP TIMINGS:")
        total_time = 0
        for step_key, step_data in self.results.items():
            if step_key.startswith('step') and 'duration_seconds' in step_data:
                step_name = step_key.replace('_', ' ').title()
                duration = step_data['duration_seconds']
                total_time += duration
                self.logger.info(f"  {step_name:<30}: {duration:>10.2f} seconds")

        self.logger.info(f"  {'Total Pipeline Time':<30}: {total_time:>10.2f} seconds")

        # Add summary to results
        self.results['summary'] = {
            'total_nodes': total_nodes,
            'total_relationships': total_relationships,
            'statistics': stats,
            'total_duration_seconds': total_time
        }

    def _save_results(self):
        """Save pipeline results to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = self.output_dir / f"pipeline_results_{timestamp}.json"

        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)

        self.logger.info(f"\n💾 Results saved to: {results_file}")

    def _safe_config(self) -> Dict[str, Any]:
        """Return config with sensitive data masked"""
        safe_config = self.config.copy()
        if 'neo4j_password' in safe_config:
            safe_config['neo4j_password'] = '***masked***'
        return safe_config


def load_config(config_file: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from file or use defaults"""
    default_config = {
        'neo4j_uri': 'bolt://localhost:7687',
        'neo4j_user': 'neo4j',
        'neo4j_password': 'your_password',
        'base_path': 'inputs',
        'output_dir': 'outputs',
        'clear_database': False,
        'store_image_blobs': False,
        'use_external_storage': True,  # NEW: Default to external storage
        'max_workers': 8,
        'log_level': 'INFO',
        'run_database_setup': True,
        'run_table_loading': True,
        'run_patient_creation': True,
        'run_family_extraction': True,
        'run_image_processing': True,
        'run_findings_extraction': True,
        'run_batch_insertion': True,
        'run_relationship_creation': True
    }

    if config_file and Path(config_file).exists():
        with open(config_file, 'r') as f:
            if config_file.endswith('.yaml') or config_file.endswith('.yml'):
                file_config = yaml.safe_load(f)
            else:
                file_config = json.load(f)

        # Merge with defaults
        default_config.update(file_config)

    return default_config


def main():
    """Main entry point for the pipeline"""
    parser = argparse.ArgumentParser(
        description="ADNI Knowledge Graph Pipeline - Build a comprehensive AD knowledge graph"
    )

    # Configuration arguments
    parser.add_argument('--config', type=str, help='Configuration file (JSON or YAML)')
    parser.add_argument('--neo4j-uri', type=str, help='Neo4j connection URI')
    parser.add_argument('--neo4j-user', type=str, help='Neo4j username')
    parser.add_argument('--neo4j-password', type=str, help='Neo4j password')
    parser.add_argument('--base-path', type=str, help='Base path for ADNI data')
    parser.add_argument('--output-dir', type=str, help='Output directory for results')

    # Pipeline control arguments
    parser.add_argument('--clear-database', action='store_true', help='Clear database before loading')
    parser.add_argument('--store-blobs', action='store_true', help='Store image blobs in database (not recommended)')
    parser.add_argument('--use-external-storage', action='store_true', help='Use external storage for images (recommended)')
    parser.add_argument('--max-workers', type=int, help='Maximum parallel workers')
    parser.add_argument('--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level')
    parser.add_argument('--log-file', type=str, help='Log file path')

    # Step control arguments
    parser.add_argument('--skip-database-setup', action='store_true', help='Skip database setup')
    parser.add_argument('--skip-table-loading', action='store_true', help='Skip table loading')
    parser.add_argument('--skip-patient-creation', action='store_true', help='Skip patient creation')
    parser.add_argument('--skip-family-extraction', action='store_true', help='Skip family extraction')
    parser.add_argument('--skip-image-processing', action='store_true', help='Skip image processing')
    parser.add_argument('--skip-findings-extraction', action='store_true', help='Skip findings extraction')
    parser.add_argument('--skip-batch-insertion', action='store_true', help='Skip batch insertion')
    parser.add_argument('--skip-relationship-creation', action='store_true', help='Skip relationship creation')

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Override with command line arguments
    if args.neo4j_uri:
        config['neo4j_uri'] = args.neo4j_uri
    if args.neo4j_user:
        config['neo4j_user'] = args.neo4j_user
    if args.neo4j_password:
        config['neo4j_password'] = args.neo4j_password
    if args.base_path:
        config['base_path'] = args.base_path
    if args.output_dir:
        config['output_dir'] = args.output_dir
    if args.clear_database:
        config['clear_database'] = True
    if args.store_blobs:
        config['store_image_blobs'] = True
        config['use_external_storage'] = False  # Disable external storage if using blobs
    if args.use_external_storage:
        config['use_external_storage'] = True
        config['store_image_blobs'] = False  # Disable blobs if using external storage
    if args.max_workers:
        config['max_workers'] = args.max_workers
    if args.log_level:
        config['log_level'] = args.log_level

    # Handle skip arguments
    if args.skip_database_setup:
        config['run_database_setup'] = False
    if args.skip_table_loading:
        config['run_table_loading'] = False
    if args.skip_patient_creation:
        config['run_patient_creation'] = False
    if args.skip_family_extraction:
        config['run_family_extraction'] = False
    if args.skip_image_processing:
        config['run_image_processing'] = False
    if args.skip_findings_extraction:
        config['run_findings_extraction'] = False
    if args.skip_batch_insertion:
        config['run_batch_insertion'] = False
    if args.skip_relationship_creation:
        config['run_relationship_creation'] = False

    # Setup logging
    setup_logging(config['log_level'], args.log_file)

    # Print banner
    print("=" * 70)
    print("     ADNI KNOWLEDGE GRAPH PIPELINE     ")
    print("  Alzheimer's Disease Neuroimaging Initiative  ")
    print("=" * 70)
    print()

    quality_pipeline = QualityAwarePipeline(config)

    # Run pipeline
    try:
        pipeline = ADNIPipeline(config)
        results = quality_pipeline.run_with_quality_checks(pipeline)

        print("\n✅ Pipeline completed successfully!")
        print(f"   Total nodes: {results['summary']['total_nodes']:,}")
        print(f"   Total relationships: {results['summary']['total_relationships']:,}")

        return 0

    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())