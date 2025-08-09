"""
Step 7: Batch Insert All Data (FIXED)
Handles batch insertion with proper error handling and null checks
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

from models.entities import (
    Patient, Visit, ImagingStudy, ImageNode,
    CognitiveAssessment, Biomarker, Diagnosis,
    FamilyMember, VolumetricMeasure, PETBinding
)
from utils.neo4j_connector import Neo4jConnector
from utils.batch_processor import BatchProcessor

logger = logging.getLogger(__name__)


class BatchInserter:
    """Fixed batch insertion with improved error handling"""

    # Optimized batch sizes
    BATCH_SIZES = {
        'patients': 1000,
        'visits': 2000,
        'family_members': 2000,
        'imaging_studies': 500,
        'images': 200,  # Smaller for images due to metadata
        'cognitive': 3000,
        'biomarkers': 3000,
        'diagnoses': 2000,
        'volumetric': 3000,
        'pet_bindings': 3000
    }

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector
        self.batch_processor = BatchProcessor()
        self.insertion_stats = {}

    def execute(self, data_objects: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute batch insertion with proper null handling

        Args:
            data_objects: Dictionary containing data processors

        Returns:
            Dictionary with insertion results
        """
        results = {
            'total_inserted': 0,
            'insertion_stats': {},
            'errors': [],
            'timing': {}
        }

        start_time = datetime.now()

        # Handle case where processors might be missing
        image_processor = data_objects.get('image_processor')
        findings_extractor = data_objects.get('findings_extractor')

        # Check what data is available
        if not image_processor and not findings_extractor:
            logger.warning("No data processors provided, checking existing data...")
            # Try to insert any data that might already exist in Neo4j
            existing_count = self._check_existing_data()
            results['existing_data'] = existing_count

            if existing_count == 0:
                logger.error("No data to insert and no existing data found")
                results['error'] = "No data available for insertion"
                return results

        # Insert imaging data if available
        if image_processor:
            logger.info("Inserting imaging data...")
            try:
                imaging_results = self._insert_imaging_data_safe(image_processor)
                results['insertion_stats'].update(imaging_results)
            except Exception as e:
                logger.error(f"Failed to insert imaging data: {e}")
                results['errors'].append(f"Imaging: {str(e)}")

        # Insert clinical findings if available
        if findings_extractor:
            logger.info("Inserting clinical findings...")
            try:
                findings_results = self._insert_findings_data_safe(findings_extractor)
                results['insertion_stats'].update(findings_results)
            except Exception as e:
                logger.error(f"Failed to insert findings data: {e}")
                results['errors'].append(f"Findings: {str(e)}")

        # Calculate totals
        results['total_inserted'] = sum(results['insertion_stats'].values())
        results['timing']['total_seconds'] = (datetime.now() - start_time).total_seconds()

        # Log summary
        self._log_insertion_summary(results)

        return results

    def _check_existing_data(self) -> int:
        """Check for existing data in Neo4j"""
        query = """
        MATCH (n)
        WHERE n:Patient OR n:Visit OR n:ImagingStudy OR n:ImageNode 
           OR n:CognitiveAssessment OR n:Biomarker OR n:Diagnosis
        RETURN count(n) as count
        """

        result = self.connector.run_query(query)
        count = result[0]['count'] if result else 0

        logger.info(f"Found {count} existing nodes in database")
        return count

    def _insert_imaging_data_safe(self, image_processor) -> Dict[str, int]:
        """Insert imaging data with null checks"""
        results = {}

        # Check if processor has the expected attributes
        if hasattr(image_processor, 'imaging_studies') and image_processor.imaging_studies:
            logger.info(f"Inserting {len(image_processor.imaging_studies)} imaging studies...")
            count = self._insert_imaging_studies_batch(list(image_processor.imaging_studies.values()))
            results['imaging_studies'] = count
        else:
            logger.warning("No imaging studies found in processor")

        if hasattr(image_processor, 'image_nodes') and image_processor.image_nodes:
            logger.info(f"Inserting {len(image_processor.image_nodes)} images...")
            count = self._insert_images_batch(image_processor.image_nodes)
            results['images'] = count
        else:
            logger.warning("No image nodes found in processor")

        return results

    def _insert_findings_data_safe(self, findings_extractor) -> Dict[str, int]:
        """Insert findings data with null checks"""
        results = {}

        # Insert each type of finding if available
        if hasattr(findings_extractor, 'cognitive_assessments') and findings_extractor.cognitive_assessments:
            logger.info(f"Inserting {len(findings_extractor.cognitive_assessments)} cognitive assessments...")
            count = self._insert_cognitive_batch(findings_extractor.cognitive_assessments)
            results['cognitive_assessments'] = count

        if hasattr(findings_extractor, 'biomarkers') and findings_extractor.biomarkers:
            logger.info(f"Inserting {len(findings_extractor.biomarkers)} biomarkers...")
            count = self._insert_biomarkers_batch(findings_extractor.biomarkers)
            results['biomarkers'] = count

        if hasattr(findings_extractor, 'diagnoses') and findings_extractor.diagnoses:
            logger.info(f"Inserting {len(findings_extractor.diagnoses)} diagnoses...")
            count = self._insert_diagnoses_batch(findings_extractor.diagnoses)
            results['diagnoses'] = count

        if hasattr(findings_extractor, 'volumetric_measures') and findings_extractor.volumetric_measures:
            logger.info(f"Inserting {len(findings_extractor.volumetric_measures)} volumetric measures...")
            count = self._insert_volumetric_batch(findings_extractor.volumetric_measures)
            results['volumetric_measures'] = count

        if hasattr(findings_extractor, 'pet_bindings') and findings_extractor.pet_bindings:
            logger.info(f"Inserting {len(findings_extractor.pet_bindings)} PET bindings...")
            count = self._insert_pet_batch(findings_extractor.pet_bindings)
            results['pet_bindings'] = count

        return results

    def _insert_imaging_studies_batch(self, studies: List[ImagingStudy]) -> int:
        """Insert imaging studies with improved error handling"""
        query = """
        UNWIND $batch as study
        MERGE (s:ImagingStudy {study_id: study.study_id})
        SET s += study
        """

        # Convert to dictionaries and clean data
        study_data = []
        for study in studies:
            try:
                data = study.to_dict() if hasattr(study, 'to_dict') else study.__dict__
                # Remove None values
                data = {k: v for k, v in data.items() if v is not None}
                study_data.append(data)
            except Exception as e:
                logger.warning(f"Skipping invalid study: {e}")
                continue

        if not study_data:
            return 0

        return self.connector.batch_write(
            query,
            study_data,
            batch_size=self.BATCH_SIZES['imaging_studies']
        )

    def _insert_images_batch(self, images: List[ImageNode]) -> int:
        """Insert images with improved batching"""
        query = """
        UNWIND $batch as image
        MERGE (i:ImageNode {image_id: image.image_id})
        SET i += image
        WITH i, image
        WHERE image.study_id IS NOT NULL
        MATCH (s:ImagingStudy {study_id: image.study_id})
        MERGE (s)-[:HAS_IMAGE]->(i)
        """

        # Process in smaller batches for images
        total_inserted = 0
        batch_size = self.BATCH_SIZES['images']

        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]

            image_data = []
            for img in batch:
                try:
                    data = img.to_dict() if hasattr(img, 'to_dict') else img.__dict__
                    # Remove None values and complex objects
                    data = {k: v for k, v in data.items()
                           if v is not None and not isinstance(v, (list, dict))}
                    image_data.append(data)
                except Exception as e:
                    logger.warning(f"Skipping invalid image: {e}")
                    continue

            if image_data:
                count = self.connector.batch_write(query, image_data, batch_size=batch_size)
                total_inserted += count
                logger.debug(f"Inserted batch {i//batch_size + 1}: {count} images")

        return total_inserted

    def _insert_cognitive_batch(self, assessments: List[CognitiveAssessment]) -> int:
        """Insert cognitive assessments"""
        query = """
        UNWIND $batch as assessment
        MERGE (a:CognitiveAssessment {assessment_id: assessment.assessment_id})
        SET a += assessment
        WITH a, assessment
        WHERE assessment.visit_id IS NOT NULL
        MATCH (v:Visit {visit_id: assessment.visit_id})
        MERGE (v)-[:HAS_COGNITIVE_ASSESSMENT]->(a)
        """

        assessment_data = []
        for assessment in assessments:
            try:
                data = assessment.to_dict() if hasattr(assessment, 'to_dict') else assessment.__dict__
                # Handle subscores as JSON
                if 'subscores' in data and isinstance(data['subscores'], dict):
                    data['subscores_json'] = json.dumps(data['subscores'])
                    del data['subscores']
                # Remove None values
                data = {k: v for k, v in data.items() if v is not None}
                assessment_data.append(data)
            except Exception as e:
                logger.warning(f"Skipping invalid assessment: {e}")
                continue

        if not assessment_data:
            return 0

        return self.connector.batch_write(
            query,
            assessment_data,
            batch_size=self.BATCH_SIZES['cognitive']
        )

    def _insert_biomarkers_batch(self, biomarkers: List[Biomarker]) -> int:
        """Insert biomarkers"""
        query = """
        UNWIND $batch as biomarker
        MERGE (b:Biomarker {biomarker_id: biomarker.biomarker_id})
        SET b += biomarker
        WITH b, biomarker
        WHERE biomarker.visit_id IS NOT NULL
        MATCH (v:Visit {visit_id: biomarker.visit_id})
        MERGE (v)-[:HAS_BIOMARKER]->(b)
        """

        biomarker_data = []
        for biomarker in biomarkers:
            try:
                data = biomarker.to_dict() if hasattr(biomarker, 'to_dict') else biomarker.__dict__
                data = {k: v for k, v in data.items() if v is not None}
                biomarker_data.append(data)
            except Exception as e:
                logger.warning(f"Skipping invalid biomarker: {e}")
                continue

        if not biomarker_data:
            return 0

        return self.connector.batch_write(
            query,
            biomarker_data,
            batch_size=self.BATCH_SIZES['biomarkers']
        )

    def _insert_diagnoses_batch(self, diagnoses: List[Diagnosis]) -> int:
        """Insert diagnoses"""
        query = """
        UNWIND $batch as diagnosis
        MERGE (d:Diagnosis {diagnosis_id: diagnosis.diagnosis_id})
        SET d += diagnosis
        WITH d, diagnosis
        WHERE diagnosis.visit_id IS NOT NULL
        MATCH (v:Visit {visit_id: diagnosis.visit_id})
        MERGE (v)-[:HAS_DIAGNOSIS]->(d)
        WITH d, diagnosis
        WHERE diagnosis.patient_id IS NOT NULL
        MATCH (p:Patient {ptid: diagnosis.patient_id})
        MERGE (p)-[:HAS_DIAGNOSIS]->(d)
        """

        diagnosis_data = []
        for diagnosis in diagnoses:
            try:
                data = diagnosis.to_dict() if hasattr(diagnosis, 'to_dict') else diagnosis.__dict__
                data = {k: v for k, v in data.items() if v is not None}
                diagnosis_data.append(data)
            except Exception as e:
                logger.warning(f"Skipping invalid diagnosis: {e}")
                continue

        if not diagnosis_data:
            return 0

        return self.connector.batch_write(
            query,
            diagnosis_data,
            batch_size=self.BATCH_SIZES['diagnoses']
        )

    def _insert_volumetric_batch(self, measures: List[VolumetricMeasure]) -> int:
        """Insert volumetric measures"""
        query = """
        UNWIND $batch as measure
        MERGE (m:VolumetricMeasure {measure_id: measure.measure_id})
        SET m += measure
        WITH m, measure
        WHERE measure.visit_id IS NOT NULL
        MATCH (v:Visit {visit_id: measure.visit_id})
        MERGE (v)-[:HAS_VOLUMETRIC_MEASURE]->(m)
        """

        measure_data = []
        for measure in measures:
            try:
                data = measure.to_dict() if hasattr(measure, 'to_dict') else measure.__dict__
                data = {k: v for k, v in data.items() if v is not None}
                measure_data.append(data)
            except Exception as e:
                logger.warning(f"Skipping invalid measure: {e}")
                continue

        if not measure_data:
            return 0

        return self.connector.batch_write(
            query,
            measure_data,
            batch_size=self.BATCH_SIZES['volumetric']
        )

    def _insert_pet_batch(self, bindings: List[PETBinding]) -> int:
        """Insert PET bindings"""
        query = """
        UNWIND $batch as binding
        MERGE (b:PETBinding {binding_id: binding.binding_id})
        SET b += binding
        WITH b, binding
        WHERE binding.visit_id IS NOT NULL
        MATCH (v:Visit {visit_id: binding.visit_id})
        MERGE (v)-[:HAS_PET_BINDING]->(b)
        """

        binding_data = []
        for binding in bindings:
            try:
                data = binding.to_dict() if hasattr(binding, 'to_dict') else binding.__dict__
                data = {k: v for k, v in data.items() if v is not None}
                binding_data.append(data)
            except Exception as e:
                logger.warning(f"Skipping invalid binding: {e}")
                continue

        if not binding_data:
            return 0

        return self.connector.batch_write(
            query,
            binding_data,
            batch_size=self.BATCH_SIZES['pet_bindings']
        )

    def _log_insertion_summary(self, results: Dict[str, Any]) -> None:
        """Log detailed insertion summary"""
        logger.info("\n" + "=" * 60)
        logger.info("BATCH INSERTION SUMMARY")
        logger.info("=" * 60)

        logger.info(f"Total entities inserted: {results['total_inserted']:,}")

        if results['timing'].get('total_seconds'):
            logger.info(f"Total time: {results['timing']['total_seconds']:.2f} seconds")

        if results['insertion_stats']:
            logger.info("\nEntities inserted by type:")
            for entity_type, count in sorted(results['insertion_stats'].items()):
                logger.info(f"  {entity_type:<25}: {count:>10,}")

        if results.get('existing_data'):
            logger.info(f"\nExisting data found: {results['existing_data']:,}")

        if results['errors']:
            logger.warning(f"\nErrors encountered: {len(results['errors'])}")
            for error in results['errors'][:5]:
                logger.warning(f"  - {error}")

        logger.info("=" * 60)


def execute_batch_insertion_fixed(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                                 data_objects: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fixed execution function for batch insertion

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Username
        neo4j_password: Password
        data_objects: Dictionary containing data processors

    Returns:
        Insertion results
    """
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        inserter = BatchInserter(connector)
        results = inserter.execute(data_objects)

        if results['total_inserted'] > 0:
            logger.info(f"✅ Batch insertion completed: {results['total_inserted']:,} entities inserted")
        else:
            logger.warning("⚠️ No entities were inserted - check data processors")

        return results

    except Exception as e:
        logger.error(f"Batch insertion failed: {e}")
        return {
            'total_inserted': 0,
            'insertion_stats': {},
            'errors': [str(e)],
            'error': str(e)
        }
    finally:
        connector.close()