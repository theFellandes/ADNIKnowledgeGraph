"""
Step 7: Batch Insert All Data
Efficiently inserts all collected data into Neo4j using batch operations
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import tempfile
from pathlib import Path
import base64

from models.entities import (
    Patient, Visit, ImagingStudy, ImageNode,
    CognitiveAssessment, Biomarker, Diagnosis,
    FamilyMember, VolumetricMeasure, PETBinding
)
from utils.neo4j_connector import Neo4jConnector
from utils.batch_processor import BatchProcessor

logger = logging.getLogger(__name__)


class BatchInserter:
    """Handle batch insertion of all ADNI data into Neo4j"""

    # Batch sizes optimized for different entity types
    BATCH_SIZES = {
        'patients': 1000,
        'visits': 2000,
        'family_members': 2000,
        'imaging_studies': 1000,
        'images': 500,  # Smaller due to potential blob data
        'cognitive': 5000,
        'biomarkers': 5000,
        'diagnoses': 3000,
        'volumetric': 5000,
        'pet_bindings': 5000
    }

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector
        self.batch_processor = BatchProcessor()
        self.insertion_stats = {}

    def execute(self, data_objects: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute batch insertion of all data

        Args:
            data_objects: Dictionary containing all extracted data objects
                - image_processor: From step 5
                - findings_extractor: From step 6

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

        # Get data from processors
        image_processor = data_objects.get('image_processor')
        findings_extractor = data_objects.get('findings_extractor')

        if not image_processor or not findings_extractor:
            raise ValueError("Missing required data processors")

        # Insert imaging data
        logger.info("Inserting imaging data...")
        imaging_results = self._insert_imaging_data(image_processor)
        results['insertion_stats'].update(imaging_results)

        # Insert clinical findings
        logger.info("Inserting clinical findings...")
        findings_results = self._insert_findings_data(findings_extractor)
        results['insertion_stats'].update(findings_results)

        # Calculate totals
        results['total_inserted'] = sum(results['insertion_stats'].values())
        results['timing']['total_seconds'] = (datetime.now() - start_time).total_seconds()

        # Log summary
        self._log_insertion_summary(results)

        return results

    def _insert_imaging_data(self, image_processor) -> Dict[str, int]:
        """Insert all imaging-related data"""
        results = {}

        # Insert imaging studies
        if image_processor.imaging_studies:
            logger.info(f"Inserting {len(image_processor.imaging_studies)} imaging studies...")
            count = self._insert_imaging_studies(list(image_processor.imaging_studies.values()))
            results['imaging_studies'] = count

        # Insert image nodes
        if image_processor.image_nodes:
            logger.info(f"Inserting {len(image_processor.image_nodes)} images...")
            count = self._insert_images(image_processor.image_nodes)
            results['images'] = count

        return results

    def _insert_findings_data(self, findings_extractor) -> Dict[str, int]:
        """Insert all clinical findings data"""
        results = {}

        # Insert cognitive assessments
        if findings_extractor.cognitive_assessments:
            logger.info(f"Inserting {len(findings_extractor.cognitive_assessments)} cognitive assessments...")
            count = self._insert_cognitive_assessments(findings_extractor.cognitive_assessments)
            results['cognitive_assessments'] = count

        # Insert biomarkers
        if findings_extractor.biomarkers:
            logger.info(f"Inserting {len(findings_extractor.biomarkers)} biomarkers...")
            count = self._insert_biomarkers(findings_extractor.biomarkers)
            results['biomarkers'] = count

        # Insert diagnoses
        if findings_extractor.diagnoses:
            logger.info(f"Inserting {len(findings_extractor.diagnoses)} diagnoses...")
            count = self._insert_diagnoses(findings_extractor.diagnoses)
            results['diagnoses'] = count

        # Insert volumetric measures
        if findings_extractor.volumetric_measures:
            logger.info(f"Inserting {len(findings_extractor.volumetric_measures)} volumetric measures...")
            count = self._insert_volumetric_measures(findings_extractor.volumetric_measures)
            results['volumetric_measures'] = count

        # Insert PET bindings
        if findings_extractor.pet_bindings:
            logger.info(f"Inserting {len(findings_extractor.pet_bindings)} PET bindings...")
            count = self._insert_pet_bindings(findings_extractor.pet_bindings)
            results['pet_bindings'] = count

        return results

    def _insert_imaging_studies(self, studies: List[ImagingStudy]) -> int:
        """Insert imaging study nodes"""
        query = """
        UNWIND $batch as study
        MERGE (s:ImagingStudy {study_id: study.study_id})
        SET s.patient_id = study.patient_id,
            s.visit_id = study.visit_id,
            s.modality = study.modality,
            s.study_date = study.study_date,
            s.study_description = study.study_description,
            s.created_at = study.created_at
        WITH s, study
        MATCH (p:Patient {ptid: study.patient_id})
        MERGE (p)-[:HAS_IMAGING_STUDY]->(s)
        WITH s, study
        WHERE study.visit_id IS NOT NULL
        MATCH (v:Visit {visit_id: study.visit_id})
        MERGE (v)-[:HAS_IMAGING]->(s)
        """

        # Convert to dictionaries and handle scanner info
        study_data = []
        for study in studies:
            data = study.to_dict()
            # Flatten scanner_info
            if 'scanner_info' in data and data['scanner_info']:
                for key, value in data['scanner_info'].items():
                    data[f'scanner_{key}'] = value
            study_data.append(data)

        return self.connector.batch_write(
            query,
            study_data,
            batch_size=self.BATCH_SIZES['imaging_studies']
        )

    def _insert_images(self, images: List[ImageNode]) -> int:
        """Insert image nodes with optional blob data"""

        # Separate images with and without blobs for different handling
        images_with_blobs = [img for img in images if img.image_blob]
        images_without_blobs = [img for img in images if not img.image_blob]

        total_inserted = 0

        # Insert images without blobs (can use larger batches)
        if images_without_blobs:
            query_no_blob = """
            UNWIND $batch as image
            MERGE (i:ImageNode {image_id: image.image_id})
            SET i.study_id = image.study_id,
                i.patient_id = image.patient_id,
                i.visit_id = image.visit_id,
                i.series_description = image.series_description,
                i.image_type = image.image_type,
                i.anatomical_region = image.anatomical_region,
                i.pet_tracer = image.pet_tracer,
                i.slice_number = image.slice_number,
                i.file_path = image.file_path,
                i.created_at = image.created_at,
                i.has_blob = false
            WITH i, image
            MATCH (s:ImagingStudy {study_id: image.study_id})
            MERGE (s)-[:HAS_IMAGE]->(i)
            WITH i, image
            WHERE image.anatomical_region IS NOT NULL
            MATCH (r:BrainRegion {region_id: image.anatomical_region})
            MERGE (i)-[:DEPICTS_REGION]->(r)
            WITH i, image
            WHERE image.pet_tracer IS NOT NULL
            MATCH (t:PETTracer {tracer_id: image.pet_tracer})
            MERGE (i)-[:USES_TRACER]->(t)
            """

            image_data = []
            for img in images_without_blobs:
                data = img.to_dict()
                # Add acquisition parameters as properties
                if 'acquisition_parameters' in data:
                    for key, value in data['acquisition_parameters'].items():
                        data[f'acq_{key}'] = value
                image_data.append(data)

            count = self.connector.batch_write(
                query_no_blob,
                image_data,
                batch_size=self.BATCH_SIZES['images'] * 2  # Can use larger batch
            )
            total_inserted += count

        # Insert images with blobs (smaller batches due to memory)
        if images_with_blobs:
            query_with_blob = """
            UNWIND $batch as image
            MERGE (i:ImageNode {image_id: image.image_id})
            SET i.study_id = image.study_id,
                i.patient_id = image.patient_id,
                i.visit_id = image.visit_id,
                i.series_description = image.series_description,
                i.image_type = image.image_type,
                i.anatomical_region = image.anatomical_region,
                i.pet_tracer = image.pet_tracer,
                i.slice_number = image.slice_number,
                i.file_path = image.file_path,
                i.created_at = image.created_at,
                i.has_blob = true,
                i.image_blob = image.image_blob,
                i.thumbnail_blob = image.thumbnail_blob
            WITH i, image
            MATCH (s:ImagingStudy {study_id: image.study_id})
            MERGE (s)-[:HAS_IMAGE]->(i)
            """

            # Process in smaller batches
            blob_batch_size = min(100, self.BATCH_SIZES['images'] // 5)

            for i in range(0, len(images_with_blobs), blob_batch_size):
                batch = images_with_blobs[i:i + blob_batch_size]

                image_data = []
                for img in batch:
                    data = img.to_dict()

                    # Convert blob to base64 for Neo4j storage
                    if img.image_blob:
                        data['image_blob'] = base64.b64encode(img.image_blob).decode('utf-8')
                    if img.thumbnail_blob:
                        data['thumbnail_blob'] = base64.b64encode(img.thumbnail_blob).decode('utf-8')

                    image_data.append(data)

                count = self.connector.batch_write(query_with_blob, image_data, batch_size=blob_batch_size)
                total_inserted += count

                # Log progress for blob insertion
                logger.info(f"  Inserted {i + len(batch)}/{len(images_with_blobs)} images with blobs")

        return total_inserted

    def _insert_cognitive_assessments(self, assessments: List[CognitiveAssessment]) -> int:
        """Insert cognitive assessment nodes"""
        query = """
        UNWIND $batch as assessment
        MERGE (a:CognitiveAssessment {assessment_id: assessment.assessment_id})
        SET a.patient_id = assessment.patient_id,
            a.visit_id = assessment.visit_id,
            a.test_name = assessment.test_name,
            a.test_version = assessment.test_version,
            a.total_score = assessment.total_score,
            a.clinical_significance = assessment.clinical_significance,
            a.source_table = assessment.source_table,
            a.created_at = assessment.created_at
        WITH a, assessment
        MATCH (v:Visit {visit_id: assessment.visit_id})
        MERGE (v)-[:HAS_COGNITIVE_ASSESSMENT]->(a)
        WITH a, assessment
        WHERE assessment.test_name IS NOT NULL
        MATCH (t:CognitiveTest {test_id: assessment.test_name})
        MERGE (a)-[:IS_INSTANCE_OF]->(t)
        WITH a, assessment
        WHERE assessment.clinical_significance IS NOT NULL
        MERGE (sig:ClinicalSignificance {significance: assessment.clinical_significance})
        MERGE (a)-[:HAS_SIGNIFICANCE]->(sig)
        """

        # Convert to dictionaries and handle subscores
        assessment_data = []
        for assessment in assessments:
            data = assessment.to_dict()
            # Store subscores as JSON string for Neo4j
            if 'subscores' in data and data['subscores']:
                data['subscores_json'] = json.dumps(data['subscores'])
            assessment_data.append(data)

        return self.connector.batch_write(
            query,
            assessment_data,
            batch_size=self.BATCH_SIZES['cognitive']
        )

    def _insert_biomarkers(self, biomarkers: List[Biomarker]) -> int:
        """Insert biomarker nodes"""
        query = """
        UNWIND $batch as biomarker
        MERGE (b:Biomarker {biomarker_id: biomarker.biomarker_id})
        SET b.patient_id = biomarker.patient_id,
            b.visit_id = biomarker.visit_id,
            b.biomarker_type = biomarker.biomarker_type,
            b.analyte = biomarker.analyte,
            b.value = biomarker.value,
            b.unit = biomarker.unit,
            b.specimen_type = biomarker.specimen_type,
            b.abnormal_flag = biomarker.abnormal_flag,
            b.source_table = biomarker.source_table,
            b.created_at = biomarker.created_at
        WITH b, biomarker
        MATCH (v:Visit {visit_id: biomarker.visit_id})
        MERGE (v)-[:HAS_BIOMARKER]->(b)
        WITH b, biomarker
        WHERE biomarker.biomarker_type = 'CSF'
        MERGE (csf:SpecimenType {type: 'CSF'})
        MERGE (b)-[:FROM_SPECIMEN]->(csf)
        WITH b, biomarker
        WHERE biomarker.biomarker_type = 'PLASMA'
        MERGE (plasma:SpecimenType {type: 'PLASMA'})
        MERGE (b)-[:FROM_SPECIMEN]->(plasma)
        """

        # Convert to dictionaries and handle assay info
        biomarker_data = []
        for biomarker in biomarkers:
            data = biomarker.to_dict()
            # Flatten assay_info
            if 'assay_info' in data and data['assay_info']:
                for key, value in data['assay_info'].items():
                    data[f'assay_{key}'] = value
            biomarker_data.append(data)

        return self.connector.batch_write(
            query,
            biomarker_data,
            batch_size=self.BATCH_SIZES['biomarkers']
        )

    def _insert_diagnoses(self, diagnoses: List[Diagnosis]) -> int:
        """Insert diagnosis nodes"""
        query = """
        UNWIND $batch as diagnosis
        MERGE (d:Diagnosis {diagnosis_id: diagnosis.diagnosis_id})
        SET d.patient_id = diagnosis.patient_id,
            d.visit_id = diagnosis.visit_id,
            d.diagnosis_code = diagnosis.diagnosis_code,
            d.diagnosis_text = diagnosis.diagnosis_text,
            d.confidence = diagnosis.confidence,
            d.criteria_used = diagnosis.criteria_used,
            d.source_table = diagnosis.source_table,
            d.created_at = diagnosis.created_at
        WITH d, diagnosis
        MATCH (v:Visit {visit_id: diagnosis.visit_id})
        MERGE (v)-[:HAS_DIAGNOSIS]->(d)
        WITH d, diagnosis
        MATCH (p:Patient {ptid: diagnosis.patient_id})
        MERGE (p)-[:HAS_DIAGNOSIS]->(d)
        WITH d, diagnosis
        MERGE (dc:DiagnosisCategory {code: diagnosis.diagnosis_code})
        SET dc.text = diagnosis.diagnosis_text
        MERGE (d)-[:IS_TYPE]->(dc)
        """

        diagnosis_data = [d.to_dict() for d in diagnoses]

        return self.connector.batch_write(
            query,
            diagnosis_data,
            batch_size=self.BATCH_SIZES['diagnoses']
        )

    def _insert_volumetric_measures(self, measures: List[VolumetricMeasure]) -> int:
        """Insert volumetric measure nodes"""
        query = """
        UNWIND $batch as measure
        MERGE (m:VolumetricMeasure {measure_id: measure.measure_id})
        SET m.image_id = measure.image_id,
            m.patient_id = measure.patient_id,
            m.visit_id = measure.visit_id,
            m.region = measure.region,
            m.volume = measure.volume,
            m.unit = measure.unit,
            m.hemisphere = measure.hemisphere,
            m.processing_method = measure.processing_method,
            m.created_at = measure.created_at
        WITH m, measure
        WHERE measure.image_id IS NOT NULL
        MATCH (i:ImageNode {image_id: measure.image_id})
        MERGE (i)-[:HAS_VOLUMETRIC_MEASURE]->(m)
        WITH m, measure
        WHERE measure.region IS NOT NULL
        MATCH (r:BrainRegion {region_id: measure.region})
        MERGE (m)-[:MEASURES_REGION]->(r)
        WITH m, measure
        MATCH (v:Visit {visit_id: measure.visit_id})
        MERGE (v)-[:HAS_VOLUMETRIC_MEASURE]->(m)
        """

        measure_data = [m.to_dict() for m in measures]

        return self.connector.batch_write(
            query,
            measure_data,
            batch_size=self.BATCH_SIZES['volumetric']
        )

    def _insert_pet_bindings(self, bindings: List[PETBinding]) -> int:
        """Insert PET binding nodes"""
        query = """
        UNWIND $batch as binding
        MERGE (b:PETBinding {binding_id: binding.binding_id})
        SET b.image_id = binding.image_id,
            b.patient_id = binding.patient_id,
            b.visit_id = binding.visit_id,
            b.tracer = binding.tracer,
            b.region = binding.region,
            b.suvr = binding.suvr,
            b.reference_region = binding.reference_region,
            b.abnormal_flag = binding.abnormal_flag,
            b.created_at = binding.created_at
        WITH b, binding
        WHERE binding.image_id IS NOT NULL
        MATCH (i:ImageNode {image_id: binding.image_id})
        MERGE (i)-[:HAS_PET_BINDING]->(b)
        WITH b, binding
        WHERE binding.tracer IS NOT NULL
        MATCH (t:PETTracer {tracer_id: binding.tracer})
        MERGE (b)-[:USES_TRACER]->(t)
        WITH b, binding
        WHERE binding.region IS NOT NULL
        MERGE (r:BrainRegion {region_id: binding.region})
        MERGE (b)-[:IN_REGION]->(r)
        WITH b, binding
        MATCH (v:Visit {visit_id: binding.visit_id})
        MERGE (v)-[:HAS_PET_BINDING]->(b)
        """

        binding_data = [b.to_dict() for b in bindings]

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

        # Overall stats
        logger.info(f"Total entities inserted: {results['total_inserted']:,}")
        logger.info(f"Total time: {results['timing']['total_seconds']:.2f} seconds")

        # Detailed breakdown
        logger.info("\nEntities inserted by type:")
        for entity_type, count in sorted(results['insertion_stats'].items()):
            logger.info(f"  {entity_type:<25}: {count:>10,}")

        # Calculate rate
        if results['timing']['total_seconds'] > 0:
            rate = results['total_inserted'] / results['timing']['total_seconds']
            logger.info(f"\nInsertion rate: {rate:,.0f} entities/second")

        # Report errors if any
        if results['errors']:
            logger.warning(f"\nErrors encountered: {len(results['errors'])}")
            for error in results['errors'][:5]:  # Show first 5 errors
                logger.warning(f"  - {error}")

        logger.info("=" * 60)


def execute_batch_insertion(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                            data_objects: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main execution function for batch insertion

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Username
        neo4j_password: Password
        data_objects: Dictionary containing data processors from previous steps

    Returns:
        Insertion results
    """
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        inserter = BatchInserter(connector)
        results = inserter.execute(data_objects)

        logger.info(f"✅ Batch insertion completed: {results['total_inserted']:,} entities inserted")
        return results

    except Exception as e:
        logger.error(f"Batch insertion failed: {e}")
        raise
    finally:
        connector.close()


if __name__ == "__main__":
    # Test execution would require actual data objects from previous steps
    logger.info("This step requires data from previous pipeline steps")