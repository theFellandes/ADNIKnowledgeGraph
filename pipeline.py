"""
ADNI Knowledge Graph Pipeline
Main orchestrator with support for incremental data loading
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
from steps.step4_extract_family import execute_family_extraction_fixed
#from steps.step5_process_images_optimized import execute_image_processing_optimized
from steps.step5_improved_process_images import execute_enhanced_image_processing
#from steps.step5_improved_process_images_with_tiff import execute_enhanced_image_processing
from steps.step6_extract_findings_robust import execute_findings_extraction_fixed
from steps.step7_batch_insert import execute_batch_insertion_fixed
from steps.step8_create_relationships import execute_comprehensive_relationship_creation
from steps.step9_knowledge_graph_enhancer import enhance_knowledge_graph
from steps.step10_execute_queries import execute_adni_queries
from steps.step11_biomarker_analysis import execute_biomarker_analysis_fixed
from steps.step12_complete_graph_enhancement import execute_complete_graph_enhancement
from steps.step13_graph_eda import execute_graph_eda
from steps.step14_test_queries import execute_research_queries
from steps.step15_event_based_model import execute_event_based_model
from steps.step16_create_metrics import run_comprehensive_metrics_analysis
from steps.step17_apply_constraints import execute_constraints
from steps.step18_add_ontology_properties import execute_ontology_properties
from steps.step19_icd10_integration import execute_icd10_integration
from steps.step20_ontology_layer import execute_ontology_layer
from steps.step21_extract_causal_features import execute_causal_features
from steps.step22_causal_discovery import execute_causal_discovery
from steps.step23_embed_causal_edges import execute_causal_edges
from steps.step24_alzkb_bridge import execute_alzkb_bridge
from steps.step25_validate_causal import execute_validate_causal
from steps.step26_dowhy_inference import execute_dowhy_inference
from steps.step27_final_stats import execute_final_stats
from steps.step28_thesis_figures import execute_thesis_figures
from steps.step29_kg_eda import execute_kg_eda
from steps.step30_hpo_expansion import execute_hpo_expansion
from steps.step33_biolink_categories import execute_biolink_categories
from steps.step34_mondo_doid_wiring import execute_mondo_doid_wiring
from steps.step35_gene_ontology_integration import execute_gene_ontology_integration
from utils.quality_aware_logger import QualityAwarePipeline

LOG_FMT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    """Set up logging configuration"""
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
    """Main pipeline orchestrator for ADNI knowledge graph with incremental support"""

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

        # Determine pipeline mode
        self.incremental_mode = config.get('incremental', False)
        self.clear_mode = config.get('clear_database', False)

        # Validate configuration
        self._validate_config()

        # Create output directory
        self.output_dir = Path(config.get('output_dir', 'outputs'))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Log mode
        if self.clear_mode:
            self.logger.info("🗑️ Pipeline running in CLEAR MODE - all data will be deleted first")
        elif self.incremental_mode:
            self.logger.info("➕ Pipeline running in INCREMENTAL MODE - existing data will be preserved")
        else:
            self.logger.info("🆕 Pipeline running in FRESH MODE")

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

        # Warn about conflicting modes
        if self.clear_mode and self.incremental_mode:
            self.logger.warning("Both clear_database and incremental are set. Clear takes precedence.")
            self.incremental_mode = False

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
            # Step 1: Database Setup (with ES clearing if needed)
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

            # Step 5: Process Images (already has incremental support)
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

            # Step 9: Enhance Knowledge Graph
            if self.config.get('run_knowledge_enhancement', True):
                self._run_step(9, "Enhance Knowledge Graph", self._execute_knowledge_enhancement)

            # Step 10: Execute Queries
            if self.config.get('run_query_execution', True):
                self._run_step(10, "Execute Queries", self._execute_queries)

            # Step 11: Comprehensive Biomarker Analysis
            if self.config.get('run_biomarker_analysis', True):
                self._run_step(11, "Biomarker Analysis", self._execute_biomarker_analysis)

            # Step 12: Complete Graph Enhancement
            if self.config.get('run_graph_enhancement', True):
                self._run_step(12, "Complete Graph Enhancement", self._execute_graph_enhancement)

            # Step 13: Graph Exploratory Data Analysis
            if self.config.get('run_graph_eda', True):
                self._run_step(13, "Graph EDA", self._execute_graph_eda)

            # Step 14: Research Queries (optional, can be skipped)
            if self.config.get('run_research_queries', True):
                self._run_step(14, "Research Queries", self._execute_research_queries)

            # Step 15: Event based graph
            if self.config.get('run_complete_graph_enhancement', True):
                self._run_step(15, "Event Based Model", self._execute_event_based_model)

            # Step 16: Create Metrics
            if self.config.get('run_create_metrics', True):
                self._run_step(16, "Create Metrics", self._execute_create_metrics)

            # ── Phase 1: Schema Migration (Steps 17-20) ──────────────
            if self.config.get('run_apply_constraints', False):
                self._run_step(17, "Apply Constraints", self._execute_constraints)

            if self.config.get('run_ontology_properties', False):
                self._run_step(18, "Add Ontology Properties", self._execute_ontology_properties)

            if self.config.get('run_icd10_integration', False):
                self._run_step(19, "ICD-10 Integration", self._execute_icd10_integration)

            if self.config.get('run_ontology_layer', False):
                self._run_step(20, "Ontology Layer", self._execute_ontology_layer)

            # ── Phase 2: Causal Discovery (Steps 21-23) ─────────────
            if self.config.get('run_causal_feature_extraction', False):
                self._run_step(21, "Extract Causal Features", self._execute_causal_features)

            if self.config.get('run_causal_discovery', False):
                self._run_step(22, "Causal Discovery", self._execute_causal_discovery)

            if self.config.get('run_embed_causal_edges', False):
                self._run_step(23, "Embed CAUSES Edges", self._execute_causal_edges)

            # ── Phase 3: Validation & Integration (Steps 24-26) ────
            if self.config.get('run_alzkb_bridge', False):
                self._run_step(24, "AlzKB Bridge", self._execute_alzkb_bridge)

            if self.config.get('run_evaluate_causality', False):
                self._run_step(25, "Validate Causal Edges", self._execute_validate_causal)

            if self.config.get('run_dowhy_inference', False):
                self._run_step(26, "DoWhy Causal Inference", self._execute_dowhy_inference)

            # ── Phase 4: Documentation & Defense Prep (Steps 27-28) ──
            if self.config.get('run_final_stats', False):
                self._run_step(27, "Final Statistics", self._execute_final_stats)

            if self.config.get('run_thesis_figures', False):
                self._run_step(28, "Thesis Figures", self._execute_thesis_figures)

            # ── Step 29: Knowledge Graph EDA ──────────────────────────
            if self.config.get('run_kg_eda', False):
                self._run_step(29, "KG Exploratory Data Analysis", self._execute_kg_eda)

            # ── Phase 1.5: Post-defence enrichment (Steps 30, 33, 34) ──
            # Added 2026-05-16: closes the contribution-table B-17 / B-20 / B-21
            # items. Idempotent — re-running on an already-enriched graph is
            # a no-op. Default-off in config so existing pipeline runs are
            # unaffected; flip the run_* toggles to include in `python pipeline.py`.
            if self.config.get('run_hpo_expansion', False):
                self._run_step(30, "HPO Concept Expansion + FamilyMember Mapping",
                               self._execute_hpo_expansion)

            if self.config.get('run_biolink_categories', False):
                self._run_step(33, "Biolink Model Annotation",
                               self._execute_biolink_categories)

            if self.config.get('run_mondo_doid_wiring', False):
                self._run_step(34, "MONDO + DOID OntologyConcept Wiring",
                               self._execute_mondo_doid_wiring)

            if self.config.get('run_gene_ontology_integration', False):
                self._run_step(35, "Gene Ontology Integration (Contribution 4)",
                               self._execute_gene_ontology_integration)

            # ── Step 18 finalization ─────────────────────────────────
            # Step 18 also runs at its original position (after 17) for
            # ontology property enrichment of nodes. Re-running it HERE,
            # after every edge-creating step has finished, ensures any
            # newly-created relationships of known types receive their
            # `r.uri` annotation. Step 18 is fully idempotent — it only
            # SETs `r.uri` where IS NULL, never overwrites or deletes.
            # See BACKLOGS.md B-04 for the rationale.
            if self.config.get('run_ontology_properties', False):
                self._run_step(
                    18,
                    "Add Ontology Properties (finalization)",
                    self._execute_ontology_properties,
                )

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

        if self.incremental_mode and step_num > 1:
            self.logger.info(f"  Mode: INCREMENTAL")
        elif self.clear_mode and step_num == 1:
            self.logger.info(f"  Mode: CLEAR ALL DATA")

        self.logger.info(f"{'=' * 60}")

        start = datetime.now()

        try:
            result = step_function()
            duration = (datetime.now() - start).total_seconds()

            self.results[f'step{step_num}_{step_name.lower().replace(" ", "_")}'] = {
                'status': 'success',
                'duration_seconds': duration,
                'result': result
            }

            self.logger.info(f"✅ {step_name} completed in {duration:.2f} seconds")

        except Exception as e:
            self.logger.error(f"❌ {step_name} failed: {e}")
            self.results[f'step{step_num}_{step_name.lower().replace(" ", "_")}'] = {
                'status': 'failed',
                'error': str(e)
            }
            if self.config.get('error_handling', {}).get('continue_on_error', False):
                self.logger.warning(f"  Continuing despite error (continue_on_error=true)")
            else:
                raise

    def _execute_database_setup(self) -> Dict[str, Any]:
        """Execute database setup step with ES clearing support"""

        # Get Elasticsearch config
        es_config = self.config.get('elasticsearch', {})
        es_host = es_config.get('host', 'localhost')
        es_port = es_config.get('port', 9200)

        # If using image storage config, use those ES settings
        if 'image_storage' in self.config:
            storage_config = self.config['image_storage']
            es_host = storage_config.get('es_host', es_host)
            es_port = storage_config.get('es_port', es_port)

        return execute_database_setup(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
            clear_database=self.clear_mode,
            incremental=self.incremental_mode,
            es_host=es_host,
            es_port=es_port
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
        """Execute patient creation step with incremental support"""
        if not hasattr(self, 'table_data'):
            raise ValueError("Table data not loaded. Run table loading step first.")

        # TODO: Modify execute_patient_creation to support incremental mode
        # For now, it will use MERGE operations which are naturally incremental
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

        return execute_family_extraction_fixed(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
            table_data=self.table_data
        )

    def _execute_image_processing(self) -> Dict[str, Any]:
        """Execute optimized image processing"""
        use_external_storage = self.config.get('use_external_storage', True)

        if use_external_storage:
            self.logger.info("📁 Using optimized external storage for images")

            storage_config = self.config.get('image_storage', {})
            storage_path = storage_config.get('storage_path')

            if not storage_path:
                storage_path = str(Path(self.config['base_path']) / '../outputs/image_store')

            Path(storage_path).mkdir(parents=True, exist_ok=True)


            # Use optimized processing
            result = execute_enhanced_image_processing(
                neo4j_uri=self.config['neo4j_uri'],
                neo4j_user=self.config['neo4j_user'],
                neo4j_password=self.config['neo4j_password'],
                base_path=self.config['base_path'],
                storage_path=storage_path,
                storage_config=storage_config,
                max_workers=self.config.get('max_workers', 8)
            )

            self.image_processor = result.get('processor')
            return result
        else:
            self.logger.warning("External storage disabled - no image processing")
            return {
                "images_created": 0,
                "images_stored": 0,
                "images_indexed": 0
            }

    def _execute_findings_extraction(self) -> Dict[str, Any]:
        """Execute fixed findings extraction"""
        if not hasattr(self, 'table_data'):
            raise ValueError("Table data not loaded. Run table loading step first.")

        result = execute_findings_extraction_fixed(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
            table_data=self.table_data
        )

        self.findings_extractor = result.get('extractor')
        return result

    def _execute_batch_insertion(self) -> Dict[str, Any]:
        """Execute batch insertion step"""
        data_objects = {}

        if hasattr(self, 'image_processor') and self.image_processor:
            data_objects['image_processor'] = self.image_processor
            self.logger.info("Image processor available for batch insertion")
        else:
            self.logger.warning("Image processor not available for batch insertion")

        if hasattr(self, 'findings_extractor') and self.findings_extractor:
            data_objects['findings_extractor'] = self.findings_extractor
            self.logger.info("Findings extractor available for batch insertion")
        else:
            self.logger.warning("Findings extractor not available for batch insertion")

        try:
            return execute_batch_insertion_fixed(
                neo4j_uri=self.config['neo4j_uri'],
                neo4j_user=self.config['neo4j_user'],
                neo4j_password=self.config['neo4j_password'],
                data_objects=data_objects
            )
        except Exception as e:
            self.logger.error(f"Batch insertion failed: {e}")
            return {'error': str(e), 'total_inserted': 0}

    def _execute_relationship_creation(self) -> Dict[str, Any]:
        """Execute relationship creation step"""
        return execute_comprehensive_relationship_creation(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password']
        )

    def _execute_knowledge_enhancement(self) -> Dict[str, Any]:
        """Execute knowledge graph enhancement"""
        return enhance_knowledge_graph(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password']
        )

    def _execute_queries(self) -> Dict[str, Any]:
        """Execute analysis queries"""
        return execute_adni_queries(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password']
        )

    def _execute_biomarker_analysis(self) -> Dict[str, Any]:
        """Execute comprehensive biomarker analysis"""
        if not hasattr(self, 'table_data'):
            raise ValueError("Table data not loaded. Run table loading step first.")

        return execute_biomarker_analysis_fixed(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
            table_data=self.table_data
        )

    def _execute_graph_enhancement(self) -> Dict[str, Any]:
        """Execute complete graph enhancement"""
        return execute_complete_graph_enhancement(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
            table_data=self.table_data if hasattr(self, 'table_data') else None
        )

    def _execute_graph_eda(self) -> Dict[str, Any]:
        """Execute graph exploratory data analysis"""
        return execute_graph_eda(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password']
        )

    def _execute_research_queries(self) -> Dict[str, Any]:
        """Execute research queries"""
        return execute_research_queries(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password']
        )

    def _execute_event_based_model(self) -> Dict[str, Any]:
        """Execute event based model"""
        return execute_event_based_model(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password']
        )

    def _execute_create_metrics(self) -> Dict[str, Any]:
        """Execute Step 16: Create performance metrics"""
        return run_comprehensive_metrics_analysis(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
        )

    # ── Phase 1: Schema Migration ─────────────────────────────────

    def _execute_constraints(self) -> Dict[str, Any]:
        """Execute Step 17: Apply composite constraints and indexes"""
        return execute_constraints(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
        )

    def _execute_ontology_properties(self) -> Dict[str, Any]:
        """Execute Step 18: Add ontology properties to existing nodes"""
        return execute_ontology_properties(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
        )

    def _execute_icd10_integration(self) -> Dict[str, Any]:
        """Execute Step 19: ICD-10 integration"""
        return execute_icd10_integration(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
            config=self.config,
        )

    def _execute_ontology_layer(self) -> Dict[str, Any]:
        """Execute Step 20: Build ontology layer + MAPS_TO"""
        return execute_ontology_layer(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
        )

    # ── Phase 2: Causal Discovery ──────────────────────────────────

    def _execute_causal_features(self) -> Dict[str, Any]:
        """Execute Step 21: Extract causal feature matrix from KG"""
        return execute_causal_features(
            config=self.config,
            connector=self.connector,
        )

    def _execute_causal_discovery(self) -> Dict[str, Any]:
        """Execute Step 22: Run PC/FCI/GES causal discovery algorithms"""
        return execute_causal_discovery(
            config=self.config,
        )

    def _execute_causal_edges(self) -> Dict[str, Any]:
        """Execute Step 23: Embed CAUSES edges into Neo4j"""
        return execute_causal_edges(
            config=self.config,
            connector=self.connector,
        )

    # ── Phase 3: Validation & Integration ─────────────────────────

    def _execute_alzkb_bridge(self) -> Dict[str, Any]:
        """Execute Step 24: AlzKB Bridge — create SAME_AS links"""
        return execute_alzkb_bridge(
            config=self.config,
            connector=self.connector,
        )

    def _execute_validate_causal(self) -> Dict[str, Any]:
        """Execute Step 25: Validate CAUSES edges against ground truth"""
        return execute_validate_causal(
            config=self.config,
            connector=self.connector,
        )

    def _execute_dowhy_inference(self) -> Dict[str, Any]:
        """Execute Step 26: DoWhy causal effect estimation"""
        return execute_dowhy_inference(
            config=self.config,
        )

    # ── Phase 4: Documentation & Defense Prep ─────────────────

    def _execute_final_stats(self) -> Dict[str, Any]:
        """Execute Step 27: Collect and report final graph statistics"""
        return execute_final_stats(
            config=self.config,
            connector=self.connector,
        )

    def _execute_thesis_figures(self) -> Dict[str, Any]:
        """Execute Step 28: Generate publication-quality thesis figures"""
        return execute_thesis_figures(
            config=self.config,
        )

    def _execute_kg_eda(self) -> Dict[str, Any]:
        """Execute Step 29: Knowledge Graph Exploratory Data Analysis"""
        return execute_kg_eda(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
            output_dir=str(Path(self.config.get('output_dir', 'outputs')) / 'eda_figures'),
        )

    def _execute_hpo_expansion(self) -> Dict[str, Any]:
        """Execute Step 30: HPO concept-layer expansion + FamilyMember dementia mapping."""
        return execute_hpo_expansion(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
        )

    def _execute_biolink_categories(self) -> Dict[str, Any]:
        """Execute Step 33: Biolink Model categorisation pass over nodes + edges."""
        return execute_biolink_categories(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
        )

    def _execute_mondo_doid_wiring(self) -> Dict[str, Any]:
        """Execute Step 34: MONDO + DOID OntologyConcept wiring."""
        return execute_mondo_doid_wiring(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
        )

    def _execute_gene_ontology_integration(self) -> Dict[str, Any]:
        """Execute Step 35: Gene + GO OntologyConcept layer + ENCODES/PARTICIPATES_IN."""
        return execute_gene_ontology_integration(
            neo4j_uri=self.config['neo4j_uri'],
            neo4j_user=self.config['neo4j_user'],
            neo4j_password=self.config['neo4j_password'],
        )

    def _generate_final_report(self):
        """Generate comprehensive final report"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("FINAL PIPELINE REPORT")
        self.logger.info("=" * 70)

        # Mode information
        if self.clear_mode:
            self.logger.info("📋 Mode: CLEAR (All data was deleted and recreated)")
        elif self.incremental_mode:
            self.logger.info("📋 Mode: INCREMENTAL (New data added to existing)")
        else:
            self.logger.info("📋 Mode: FRESH")

        # Get database stats if available
        if 'step1_database_setup' in self.results:
            setup_result = self.results['step1_database_setup'].get('result', {})
            if 'final_stats' in setup_result:
                stats = setup_result['final_stats']
                self.logger.info("\n📊 DATABASE STATISTICS:")
                self.logger.info(f"  Neo4j Patients:        {stats.get('neo4j_patient', 0):>10,}")
                self.logger.info(f"  Neo4j Visits:          {stats.get('neo4j_visit', 0):>10,}")
                self.logger.info(f"  Neo4j Images:          {stats.get('neo4j_imagenode', 0):>10,}")
                self.logger.info(f"  ES Indexed Images:     {stats.get('elasticsearch_images', 0):>10,}")

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
            step3 = self.results['step3_create_patients'].get('result', {})
            stats['patients'] = step3.get('patients_created', 0)
            stats['visits'] = step3.get('visits_created', 0)

        if 'step4_extract_family' in self.results:
            step4 = self.results['step4_extract_family'].get('result', {})
            stats['family_members'] = step4.get('family_members_created', 0)

        if 'step5_process_images' in self.results:
            step5 = self.results['step5_process_images'].get('result', {})
            stats['images'] = step5.get('images_indexed_neo4j', 0)
            stats['images_stored'] = step5.get('images_indexed_es', 0)

        if 'step6_extract_findings' in self.results:
            step6 = self.results['step6_extract_findings'].get('result', {})
            stats['cognitive_assessments'] = step6.get('cognitive_assessments', 0)
            stats['biomarkers'] = step6.get('biomarkers', 0)
            stats['diagnoses'] = step6.get('diagnoses', 0)

        if 'step8_create_relationships' in self.results:
            step8 = self.results['step8_create_relationships'].get('result', {})
            stats['relationships'] = step8.get('relationships_created', 0)

        # Log new items added (for incremental mode)
        if self.incremental_mode:
            self.logger.info("\n➕ NEW ITEMS ADDED:")
        else:
            self.logger.info("\n📋 ITEMS CREATED:")

        self.logger.info(f"  Patients:              {stats['patients']:>10,}")
        self.logger.info(f"  Visits:                {stats['visits']:>10,}")
        self.logger.info(f"  Family Members:        {stats['family_members']:>10,}")
        self.logger.info(f"  Images:                {stats['images']:>10,}")
        self.logger.info(f"  Cognitive Assessments: {stats['cognitive_assessments']:>10,}")
        self.logger.info(f"  Biomarkers:            {stats['biomarkers']:>10,}")
        self.logger.info(f"  Diagnoses:             {stats['diagnoses']:>10,}")
        self.logger.info(f"  Relationships:         {stats['relationships']:>10,}")

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
            'mode': 'clear' if self.clear_mode else ('incremental' if self.incremental_mode else 'fresh'),
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
        'incremental': False,  # New: incremental mode
        'store_image_blobs': False,
        'use_external_storage': True,
        'max_workers': 8,
        'log_level': 'INFO',
        'run_database_setup': True,
        'run_table_loading': True,
        'run_patient_creation': True,
        'run_family_extraction': True,
        'run_image_processing': True,
        'run_findings_extraction': True,
        'run_batch_insertion': True,
        'run_relationship_creation': True,
        'elasticsearch': {
            'host': 'localhost',
            'port': 9200
        }
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

    # Pipeline mode arguments (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--clear-database', action='store_true',
                          help='Clear all databases before loading (DESTRUCTIVE)')
    mode_group.add_argument('--incremental', action='store_true',
                          help='Run in incremental mode (preserve existing data)')

    # Other pipeline control arguments
    parser.add_argument('--store-blobs', action='store_true',
                       help='Store image blobs in database (not recommended)')
    parser.add_argument('--use-external-storage', action='store_true',
                       help='Use external storage for images (recommended)')
    parser.add_argument('--max-workers', type=int, help='Maximum parallel workers')
    parser.add_argument('--log-level', type=str,
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
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
    parser.add_argument('--skip-biomarker-analysis', action='store_true',
                        help='Skip comprehensive biomarker analysis')

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

    # Handle mode arguments
    if args.clear_database:
        config['clear_database'] = True
        config['incremental'] = False
    elif args.incremental:
        config['incremental'] = True
        config['clear_database'] = False

    if args.store_blobs:
        config['store_image_blobs'] = True
        config['use_external_storage'] = False
    if args.use_external_storage:
        config['use_external_storage'] = True
        config['store_image_blobs'] = False
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
    if args.skip_biomarker_analysis:
        config['run_biomarker_analysis'] = False

    # Setup logging
    setup_logging(config['log_level'], args.log_file)

    # Print banner
    print("=" * 70)
    print("     ADNI KNOWLEDGE GRAPH PIPELINE     ")
    print("  Alzheimer's Disease Neuroimaging Initiative  ")
    print("=" * 70)

    # Display mode
    if config.get('clear_database'):
        print("⚠️  MODE: CLEAR - All data will be deleted first!")
        print("    Press Ctrl+C within 5 seconds to cancel...")
        import time
        time.sleep(5)
    elif config.get('incremental'):
        print("➕ MODE: INCREMENTAL - Adding to existing data")
    else:
        print("🆕 MODE: FRESH - Standard execution")
    print()

    # Check if quality pipeline is available
    try:
        quality_pipeline = QualityAwarePipeline(config)
        use_quality = True
    except:
        quality_pipeline = None
        use_quality = False

    # Run pipeline
    try:
        pipeline = ADNIPipeline(config)

        if use_quality:
            results = quality_pipeline.run_with_quality_checks(pipeline)
        else:
            results = pipeline.run()

        print("\n✅ Pipeline completed successfully!")

        # Show final stats
        if 'summary' in results:
            summary = results['summary']
            print(f"   Mode: {summary.get('mode', 'unknown').upper()}")

            if 'statistics' in summary:
                stats = summary['statistics']
                if config.get('incremental'):
                    print(f"   New items added: {sum(stats.values()):,}")
                else:
                    print(f"   Total items created: {sum(stats.values()):,}")

        return 0

    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())