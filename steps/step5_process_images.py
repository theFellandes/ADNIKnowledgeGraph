"""
Step 5: Process Medical Images
Processes MRI and PET images from both converted and DICOM formats
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import concurrent.futures
from datetime import datetime
import hashlib
import re

from models.entities import ImagingStudy, ImageNode, Visit
from utils.image_processor import ImageProcessor
from utils.batch_processor import BatchProcessor
from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


class ImageProcessingPipeline:
    """Process medical images for ADNI knowledge graph"""

    def __init__(self, connector: Neo4jConnector, base_path: str,
                 store_blobs: bool = True, max_workers: int = 8):
        self.connector = connector
        self.base_path = Path(base_path)
        self.store_blobs = store_blobs
        self.max_workers = max_workers

        # Image paths
        self.mri_updated_path = self.base_path / "Updated"
        self.pet_updated_path = self.base_path / "Updated_PET"
        self.mri_dicom_path = self.base_path / "Images"
        self.pet_dicom_path = self.base_path / "PET"

        # Processors
        self.image_processor = ImageProcessor()
        self.batch_processor = BatchProcessor(max_workers=max_workers)

        # Storage
        self.imaging_studies = {}
        self.image_nodes = []

    def execute(self) -> Dict[str, Any]:
        """
        Execute image processing pipeline

        Returns:
            Dictionary with processing results
        """
        results = {
            'mri_processed': 0,
            'pet_processed': 0,
            'studies_created': 0,
            'images_created': 0,
            'blobs_stored': 0,
            'errors': []
        }

        # Process MRI images
        logger.info("Processing MRI images...")
        mri_results = self._process_modality('MRI')
        results['mri_processed'] = mri_results['processed']
        results['errors'].extend(mri_results['errors'])

        # Process PET images
        logger.info("Processing PET images...")
        pet_results = self._process_modality('PET')
        results['pet_processed'] = pet_results['processed']
        results['errors'].extend(pet_results['errors'])

        # Create imaging studies
        logger.info("Creating imaging studies...")
        results['studies_created'] = len(self.imaging_studies)
        results['images_created'] = len(self.image_nodes)

        if self.store_blobs:
            results['blobs_stored'] = sum(1 for img in self.image_nodes if img.image_blob)

        return results

    def _process_modality(self, modality: str) -> Dict[str, Any]:
        """Process images for a specific modality"""
        results = {'processed': 0, 'errors': []}

        if modality == 'MRI':
            updated_path = self.mri_updated_path
            dicom_path = self.mri_dicom_path
        else:
            updated_path = self.pet_updated_path
            dicom_path = self.pet_dicom_path

        # Process converted images first (PNG/JPG)
        if updated_path.exists():
            logger.info(f"Processing converted {modality} images from {updated_path}")
            converted_results = self._process_converted_images(updated_path, modality)
            results['processed'] += converted_results['processed']
            results['errors'].extend(converted_results['errors'])

        # Process DICOM images if needed
        if dicom_path.exists() and self.store_blobs:
            logger.info(f"Processing DICOM {modality} images from {dicom_path}")
            dicom_results = self._process_dicom_images(dicom_path, modality)
            results['processed'] += dicom_results['processed']
            results['errors'].extend(dicom_results['errors'])

        return results

    def _process_converted_images(self, base_path: Path, modality: str) -> Dict[str, Any]:
        """Process converted (PNG/JPG) images"""
        results = {'processed': 0, 'errors': []}

        # Get all patient directories
        patient_dirs = [d for d in base_path.iterdir() if d.is_dir()]

        for patient_dir in patient_dirs:
            patient_id = patient_dir.name

            # Validate patient ID
            if not self._validate_patient_id(patient_id):
                logger.warning(f"Invalid patient ID: {patient_id}")
                continue

            # Process patient images
            patient_results = self._process_patient_images(patient_dir, patient_id, modality)
            results['processed'] += patient_results['processed']
            results['errors'].extend(patient_results['errors'])

        return results

    def _process_patient_images(self, patient_dir: Path, patient_id: str,
                                modality: str) -> Dict[str, Any]:
        """Process all images for a patient"""
        results = {'processed': 0, 'errors': []}

        # Collect all image files
        image_files = []

        # Check for series directories
        series_dirs = [d for d in patient_dir.iterdir() if d.is_dir()]

        if series_dirs:
            # Images organized by series
            for series_dir in series_dirs:
                series_name = series_dir.name

                # Check for timestamp directories
                timestamp_dirs = [d for d in series_dir.iterdir() if d.is_dir()]

                if timestamp_dirs:
                    for timestamp_dir in timestamp_dirs:
                        for img_file in timestamp_dir.iterdir():
                            if self._is_image_file(img_file):
                                image_files.append({
                                    'path': img_file,
                                    'series': series_name,
                                    'timestamp': timestamp_dir.name
                                })
                else:
                    # Images directly in series directory
                    for img_file in series_dir.iterdir():
                        if self._is_image_file(img_file):
                            image_files.append({
                                'path': img_file,
                                'series': series_name,
                                'timestamp': None
                            })
        else:
            # Images directly in patient directory
            for img_file in patient_dir.iterdir():
                if self._is_image_file(img_file):
                    image_files.append({
                        'path': img_file,
                        'series': None,
                        'timestamp': None
                    })

        # Process images in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = []

            for img_info in image_files:
                future = executor.submit(
                    self._process_single_image,
                    img_info['path'],
                    patient_id,
                    modality,
                    img_info['series'],
                    img_info['timestamp']
                )
                futures.append(future)

            for future in concurrent.futures.as_completed(futures):
                try:
                    image_node = future.result()
                    if image_node:
                        self.image_nodes.append(image_node)
                        results['processed'] += 1

                        # Create or update imaging study
                        self._update_imaging_study(image_node)

                except Exception as e:
                    logger.error(f"Error processing image: {e}")
                    results['errors'].append(str(e))

        return results

    def _process_single_image(self, image_path: Path, patient_id: str,
                              modality: str, series_name: Optional[str] = None,
                              timestamp: Optional[str] = None) -> Optional[ImageNode]:
        """Process a single image file"""
        try:
            # Generate unique image ID
            image_id = self._generate_image_id(patient_id, image_path)

            # Extract metadata from filename and path
            metadata = self._extract_metadata(image_path, series_name, timestamp)

            # Determine anatomical region
            anatomical_region = self.image_processor.determine_anatomical_region(
                series_name or image_path.stem, modality
            )

            # Extract PET tracer if applicable
            pet_tracer = None
            if modality == 'PET':
                pet_tracer = self.image_processor.extract_pet_tracer(
                    metadata,
                    image_path.stem
                )

            # Process image to get blobs if requested
            image_blob = None
            thumbnail_blob = None

            if self.store_blobs:
                img_result = self.image_processor.process_image(str(image_path))
                if img_result['success']:
                    image_blob = img_result['image_blob']
                    thumbnail_blob = img_result['thumbnail_blob']

            # Find associated visit
            visit_id = self._find_visit_id(patient_id, metadata.get('study_date', ''))

            # Create image node
            image_node = ImageNode(
                image_id=image_id,
                study_id=f"study_{patient_id}_{modality}_{metadata.get('study_date', 'unknown')}",
                patient_id=patient_id,
                visit_id=visit_id,
                series_description=series_name or metadata.get('series_description', ''),
                image_type='CONVERTED',
                anatomical_region=anatomical_region,
                pet_tracer=pet_tracer,
                acquisition_parameters=metadata,
                image_blob=image_blob,
                thumbnail_blob=thumbnail_blob,
                file_path=str(image_path)
            )

            return image_node

        except Exception as e:
            logger.error(f"Failed to process image {image_path}: {e}")
            return None

    def _process_dicom_images(self, base_path: Path, modality: str) -> Dict[str, Any]:
        """Process DICOM images"""
        results = {'processed': 0, 'errors': []}

        # Get all DICOM files
        dicom_files = list(base_path.rglob("*.dcm"))
        logger.info(f"Found {len(dicom_files)} DICOM files")

        # Process in batches to avoid memory issues
        batch_size = 100

        for i in range(0, len(dicom_files), batch_size):
            batch = dicom_files[i:i + batch_size]

            for dicom_path in batch:
                try:
                    # Extract patient ID from path
                    patient_id = self._extract_patient_id_from_path(dicom_path)
                    if not patient_id:
                        continue

                    # Process DICOM
                    dicom_result = self.image_processor.process_dicom(str(dicom_path))

                    if dicom_result['success']:
                        # Create image node
                        image_id = self._generate_image_id(patient_id, dicom_path)
                        metadata = dicom_result['metadata']

                        # Extract study date
                        study_date = metadata.get('StudyDate', '')
                        if study_date and len(study_date) == 8:
                            study_date = f"{study_date[:4]}-{study_date[4:6]}-{study_date[6:8]}"

                        # Find visit
                        visit_id = self._find_visit_id(patient_id, study_date)

                        # Determine anatomical region
                        series_desc = metadata.get('SeriesDescription', '')
                        anatomical_region = self.image_processor.determine_anatomical_region(
                            series_desc, modality
                        )

                        # Extract PET tracer
                        pet_tracer = None
                        if modality == 'PET':
                            pet_tracer = self.image_processor.extract_pet_tracer(
                                metadata,
                                dicom_path.name
                            )

                        # Create image node
                        image_node = ImageNode(
                            image_id=image_id,
                            study_id=f"study_{patient_id}_{modality}_{study_date or 'unknown'}",
                            patient_id=patient_id,
                            visit_id=visit_id,
                            series_description=series_desc,
                            image_type='DICOM',
                            anatomical_region=anatomical_region,
                            pet_tracer=pet_tracer,
                            slice_number=metadata.get('InstanceNumber'),
                            acquisition_parameters=metadata,
                            dicom_metadata=metadata,
                            image_blob=dicom_result.get('image_blob') if self.store_blobs else None,
                            thumbnail_blob=dicom_result.get('thumbnail_blob') if self.store_blobs else None,
                            file_path=str(dicom_path)
                        )

                        self.image_nodes.append(image_node)
                        self._update_imaging_study(image_node)
                        results['processed'] += 1

                except Exception as e:
                    logger.error(f"Error processing DICOM {dicom_path}: {e}")
                    results['errors'].append(str(e))

        return results

    def _update_imaging_study(self, image_node: ImageNode) -> None:
        """Create or update imaging study for an image"""
        study_id = image_node.study_id

        if study_id not in self.imaging_studies:
            # Extract modality from study_id
            parts = study_id.split('_')
            modality = parts[2] if len(parts) > 2 else 'UNKNOWN'

            # Create new study
            study = ImagingStudy(
                study_id=study_id,
                patient_id=image_node.patient_id,
                visit_id=image_node.visit_id,
                modality=modality,
                study_date=image_node.acquisition_parameters.get('study_date', ''),
                study_description=image_node.series_description
            )

            self.imaging_studies[study_id] = study

    def _generate_image_id(self, patient_id: str, image_path: Path) -> str:
        """Generate unique image ID"""
        # Create hash from patient ID and file path
        content = f"{patient_id}_{image_path}"
        hash_obj = hashlib.sha256(content.encode())
        return f"img_{hash_obj.hexdigest()[:16]}"

    def _extract_metadata(self, image_path: Path, series_name: Optional[str],
                          timestamp: Optional[str]) -> Dict[str, Any]:
        """Extract metadata from file path and name"""
        metadata = {}

        # Extract from filename
        filename = image_path.stem

        # Common ADNI patterns
        # Example: ADNI_002_S_0295_MR_MT1__GradWarp__N3m_Br_20070217114937668_S18402_I40731
        parts = filename.split('_')

        for i, part in enumerate(parts):
            # Patient ID pattern
            if re.match(r'\d{3}_S_\d{4}', '_'.join(parts[i:i + 3])):
                metadata['patient_id'] = '_'.join(parts[i:i + 3])

            # Date pattern (YYYYMMDD)
            elif re.match(r'\d{8}', part):
                metadata['study_date'] = f"{part[:4]}-{part[4:6]}-{part[6:8]}"

            # Image ID pattern (I followed by numbers)
            elif re.match(r'I\d+', part):
                metadata['image_number'] = part

        # Add series and timestamp
        if series_name:
            metadata['series_description'] = series_name
        if timestamp:
            metadata['acquisition_timestamp'] = timestamp
            # Try to parse date from timestamp
            if len(timestamp) >= 8 and timestamp[:8].isdigit():
                metadata['study_date'] = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"

        return metadata

    def _extract_patient_id_from_path(self, path: Path) -> Optional[str]:
        """Extract patient ID from file path"""
        # Check parent directories for patient ID pattern
        for parent in path.parents:
            if self._validate_patient_id(parent.name):
                return parent.name

        # Check filename
        filename = path.stem
        match = re.search(r'(\d{3}_S_\d{4})', filename)
        if match:
            return match.group(1)

        return None

    def _validate_patient_id(self, patient_id: str) -> bool:
        """Validate ADNI patient ID format"""
        pattern = r'^\d{3}_S_\d{4}$'
        return bool(re.match(pattern, patient_id))

    def _is_image_file(self, path: Path) -> bool:
        """Check if file is an image"""
        image_extensions = {'.png', '.jpg', '.jpeg', '.dcm', '.nii', '.nii.gz'}
        return path.is_file() and path.suffix.lower() in image_extensions

    def _find_visit_id(self, patient_id: str, study_date: str) -> str:
        """Find or create visit ID for the image"""
        # Query Neo4j for matching visit
        query = """
        MATCH (p:Patient {ptid: $patient_id})-[:HAS_VISIT]->(v:Visit)
        WHERE v.visit_date = $study_date OR 
              (v.visit_date IS NULL AND $study_date = '')
        RETURN v.visit_id as visit_id
        ORDER BY v.months_from_baseline
        LIMIT 1
        """

        result = self.connector.run_query(
            query,
            {'patient_id': patient_id, 'study_date': study_date}
        )

        if result and result[0]['visit_id']:
            return result[0]['visit_id']

        # Default to baseline visit
        return f"{patient_id}_bl"

    def get_processing_summary(self) -> Dict[str, Any]:
        """Get summary of processed images"""
        summary = {
            'total_images': len(self.image_nodes),
            'total_studies': len(self.imaging_studies),
            'by_modality': {},
            'by_type': {},
            'with_blobs': 0,
            'pet_tracers': {}
        }

        # Count by modality and type
        for img in self.image_nodes:
            # Modality
            modality = 'PET' if 'PET' in img.study_id else 'MRI'
            summary['by_modality'][modality] = summary['by_modality'].get(modality, 0) + 1

            # Type
            img_type = img.image_type
            summary['by_type'][img_type] = summary['by_type'].get(img_type, 0) + 1

            # Blobs
            if img.image_blob:
                summary['with_blobs'] += 1

            # PET tracers
            if img.pet_tracer:
                tracer = img.pet_tracer
                summary['pet_tracers'][tracer] = summary['pet_tracers'].get(tracer, 0) + 1

        return summary


def execute_image_processing(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                             base_path: str, store_blobs: bool = True,
                             max_workers: int = 8) -> Dict[str, Any]:
    """
    Main execution function for image processing

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Username
        neo4j_password: Password
        base_path: Base path containing image directories
        store_blobs: Whether to store image blobs in database
        max_workers: Maximum number of parallel workers

    Returns:
        Processing results
    """
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        processor = ImageProcessingPipeline(
            connector,
            base_path,
            store_blobs=store_blobs,
            max_workers=max_workers
        )

        results = processor.execute()

        # Get summary
        summary = processor.get_processing_summary()
        results['summary'] = summary

        # Store the processor for next steps
        results['processor'] = processor

        logger.info(f"✅ Processed {results['mri_processed']} MRI and {results['pet_processed']} PET images")
        logger.info(f"   Created {results['studies_created']} studies and {results['images_created']} image nodes")

        if store_blobs:
            logger.info(f"   Stored {results['blobs_stored']} image blobs")

        return results

    except Exception as e:
        logger.error(f"Image processing failed: {e}")
        raise
    finally:
        connector.close()


if __name__ == "__main__":
    # Test execution
    results = execute_image_processing(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="your_password",
        base_path="inputs",
        store_blobs=True,
        max_workers=4
    )

    print(f"Results: {results['summary']}")