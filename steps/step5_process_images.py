"""
Step 5: Process Medical Images (MODIFIED FOR EXTERNAL STORAGE)
Processes MRI and PET images with hierarchical external storage instead of Neo4j blobs
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
from utils.batch_processor import BatchProcessor
from utils.neo4j_connector import Neo4jConnector
from utils.medical_image_storage import MedicalImageStorageManager

logger = logging.getLogger(__name__)


class ImageProcessingPipeline:
    """Process medical images for ADNI knowledge graph with external storage"""

    def __init__(self, connector: Neo4jConnector, base_path: str,
                 storage_path: str = None, store_blobs: bool = False, max_workers: int = 8):
        """
        Initialize image processing pipeline with external storage

        Args:
            connector: Neo4j connector
            base_path: Base path for ADNI data
            storage_path: Path for hierarchical image storage
            max_workers: Maximum parallel workers
        """
        self.connector = connector
        self.base_path = Path(base_path)
        self.max_workers = max_workers
        self.store_blobs = store_blobs

        # Set up storage path
        if storage_path is None:
            storage_path = self.base_path / "image_store"
        self.storage_path = Path(storage_path)

        # Image paths
        self.mri_updated_path = self.base_path / "Updated"
        self.pet_updated_path = self.base_path / "Updated_PET"
        self.mri_dicom_path = self.base_path / "Images"
        self.pet_dicom_path = self.base_path / "PET"

        # Initialize storage manager
        self.storage_manager = MedicalImageStorageManager(
            str(self.storage_path),
            neo4j_connector=connector
        )

        # Processors
        self.batch_processor = BatchProcessor(max_workers=max_workers)

        # Storage
        self.imaging_studies = {}
        self.image_nodes = []
        self.storage_results = []

    def execute(self) -> Dict[str, Any]:
        """
        Execute image processing pipeline with external storage

        Returns:
            Dictionary with processing results
        """
        results = {
            'mri_processed': 0,
            'pet_processed': 0,
            'studies_created': 0,
            'images_created': 0,
            'images_stored': 0,
            'storage_size_mb': 0,
            'quality_metrics': {},
            'errors': []
        }

        # Process DICOM images first (preferred for medical imaging)
        if self.mri_dicom_path.exists():
            logger.info("Processing MRI DICOM images...")
            mri_dicom_results = self._process_dicom_modality('MRI', self.mri_dicom_path)
            results['mri_processed'] += mri_dicom_results['processed']
            results['errors'].extend(mri_dicom_results['errors'])

        if self.pet_dicom_path.exists():
            logger.info("Processing PET DICOM images...")
            pet_dicom_results = self._process_dicom_modality('PET', self.pet_dicom_path)
            results['pet_processed'] += pet_dicom_results['processed']
            results['errors'].extend(pet_dicom_results['errors'])

        # Process converted images as fallback
        if self.mri_updated_path.exists() and results['mri_processed'] == 0:
            logger.info("Processing converted MRI images...")
            mri_results = self._process_converted_modality('MRI', self.mri_updated_path)
            results['mri_processed'] += mri_results['processed']
            results['errors'].extend(mri_results['errors'])

        if self.pet_updated_path.exists() and results['pet_processed'] == 0:
            logger.info("Processing converted PET images...")
            pet_results = self._process_converted_modality('PET', self.pet_updated_path)
            results['pet_processed'] += pet_results['processed']
            results['errors'].extend(pet_results['errors'])

        # Create imaging studies
        logger.info("Creating imaging studies...")
        results['studies_created'] = len(self.imaging_studies)
        results['images_created'] = len(self.image_nodes)
        results['images_stored'] = len(self.storage_results)

        # Calculate storage size
        results['storage_size_mb'] = self._calculate_storage_size()

        # Aggregate quality metrics
        results['quality_metrics'] = self._aggregate_quality_metrics()

        return results

    def _process_dicom_modality(self, modality: str, dicom_path: Path) -> Dict[str, Any]:
        """Process DICOM images for a specific modality"""
        results = {'processed': 0, 'errors': []}

        # Get all DICOM files
        dicom_files = list(dicom_path.rglob("*.dcm"))
        logger.info(f"Found {len(dicom_files)} DICOM files for {modality}")

        # Process in batches
        batch_size = 50  # Smaller batches for DICOM processing

        for i in range(0, len(dicom_files), batch_size):
            batch = dicom_files[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(dicom_files) + batch_size - 1)//batch_size}")

            # Process batch in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, self.max_workers)) as executor:
                futures = []

                for dicom_file in batch:
                    # Extract identifiers from path
                    patient_id = self._extract_patient_id_from_path(dicom_file)
                    if not patient_id:
                        logger.warning(f"Could not extract patient ID from {dicom_file}")
                        continue

                    study_id = self._generate_study_id(patient_id, modality, dicom_file)
                    series_id = self._extract_series_id(dicom_file)

                    future = executor.submit(
                        self._process_single_dicom,
                        dicom_file,
                        patient_id,
                        study_id,
                        series_id,
                        modality
                    )
                    futures.append(future)

                # Collect results
                for future in concurrent.futures.as_completed(futures):
                    try:
                        result = future.result(timeout=60)  # 60 second timeout per file
                        if result and result['success']:
                            results['processed'] += 1
                            self.storage_results.append(result)

                            # Create image node
                            image_node = self._create_image_node_from_storage(result, modality)
                            if image_node:
                                self.image_nodes.append(image_node)
                                self._update_imaging_study(image_node)
                    except Exception as e:
                        logger.error(f"Error processing DICOM: {e}")
                        results['errors'].append(str(e))

        return results

    def _process_single_dicom(self, dicom_path: Path, patient_id: str,
                             study_id: str, series_id: str, modality: str) -> Dict[str, Any]:
        """Process a single DICOM file"""
        try:
            # Use storage manager to process and store
            storage_metadata = self.storage_manager.process_dicom_for_storage(
                str(dicom_path),
                patient_id,
                study_id,
                series_id
            )

            return {
                'success': True,
                'storage_metadata': storage_metadata,
                'patient_id': patient_id,
                'study_id': study_id,
                'series_id': series_id,
                'modality': modality,
                'original_path': str(dicom_path)
            }

        except Exception as e:
            logger.error(f"Failed to process DICOM {dicom_path}: {e}")
            return {
                'success': False,
                'error': str(e),
                'original_path': str(dicom_path)
            }

    def _process_converted_modality(self, modality: str, base_path: Path) -> Dict[str, Any]:
        """Process pre-converted images (JPG/PNG) as fallback"""
        results = {'processed': 0, 'errors': []}

        # Get all patient directories
        patient_dirs = [d for d in base_path.iterdir() if d.is_dir()]

        for patient_dir in patient_dirs:
            patient_id = patient_dir.name

            if not self._validate_patient_id(patient_id):
                logger.warning(f"Invalid patient ID: {patient_id}")
                continue

            # Process patient's converted images
            patient_results = self._process_patient_converted_images(
                patient_dir, patient_id, modality
            )
            results['processed'] += patient_results['processed']
            results['errors'].extend(patient_results['errors'])

        return results

    def _process_patient_converted_images(self, patient_dir: Path, patient_id: str,
                                         modality: str) -> Dict[str, Any]:
        """Process converted images for a patient"""
        results = {'processed': 0, 'errors': []}

        # Collect all image files
        image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png']:
            image_files.extend(patient_dir.rglob(ext))

        for img_file in image_files:
            try:
                # Generate IDs
                study_id = self._generate_study_id(patient_id, modality, img_file)
                series_id = img_file.parent.name if img_file.parent != patient_dir else "default"
                image_id = self._generate_image_id(patient_id, img_file)

                # Create storage reference (without actual storage for converted images)
                # In production, you might want to copy these to the storage hierarchy
                storage_ref = {
                    'storage_id': image_id,
                    'patient_id': patient_id,
                    'study_id': study_id,
                    'series_id': series_id,
                    'original_path': str(img_file),
                    'format': 'converted',
                    'modality': modality
                }

                # Create image node with reference to original file
                visit_id = self._find_visit_id(patient_id, "")

                image_node = ImageNode(
                    image_id=image_id,
                    study_id=study_id,
                    patient_id=patient_id,
                    visit_id=visit_id,
                    series_description=series_id,
                    image_type='CONVERTED',
                    anatomical_region=self._infer_anatomical_region(img_file.name),
                    pet_tracer=self._infer_pet_tracer(img_file.name) if modality == 'PET' else None,
                    file_path=str(img_file),
                    storage_format='external_file',
                    has_diagnostic=False,  # Converted images may not be diagnostic quality
                    has_preview=True,
                    has_thumbnail=True
                )

                self.image_nodes.append(image_node)
                self._update_imaging_study(image_node)
                results['processed'] += 1

            except Exception as e:
                logger.error(f"Error processing converted image {img_file}: {e}")
                results['errors'].append(str(e))

        return results

    def _create_image_node_from_storage(self, storage_result: Dict, modality: str) -> Optional[ImageNode]:
        """Create image node from storage result"""
        try:
            storage_metadata = storage_result['storage_metadata']

            # Find associated visit
            visit_id = self._find_visit_id(
                storage_result['patient_id'],
                storage_metadata.storage_timestamp[:10]  # Use date part
            )

            # Create image node with storage references
            image_node = ImageNode(
                image_id=storage_metadata.storage_id,
                study_id=storage_result['study_id'],
                patient_id=storage_result['patient_id'],
                visit_id=visit_id,
                series_description=storage_result.get('series_id', ''),
                image_type='DICOM',
                anatomical_region=self._infer_anatomical_region(storage_result.get('series_id', '')),
                pet_tracer=self._infer_pet_tracer(storage_result.get('series_id', '')) if modality == 'PET' else None,

                # Storage references instead of blobs
                storage_id=storage_metadata.storage_id,
                diagnostic_path=storage_metadata.file_paths.get('diagnostic'),
                preview_path=storage_metadata.file_paths.get('preview'),
                thumbnail_path=storage_metadata.file_paths.get('thumbnail'),

                # Quality metrics
                snr=storage_metadata.quality_metrics.get('snr'),
                entropy=storage_metadata.quality_metrics.get('entropy'),
                contrast=storage_metadata.quality_metrics.get('contrast'),

                # Metadata
                dimensions=list(storage_metadata.dimensions),
                voxel_spacing=list(storage_metadata.voxel_spacing) if storage_metadata.voxel_spacing else None,
                bits_per_pixel=storage_metadata.bits_per_pixel,
                checksum=storage_metadata.checksums.get('diagnostic'),

                # Flags
                has_diagnostic=True,
                has_preview=True,
                has_thumbnail=True,
                quality_verified=True,
                storage_format='hierarchical',

                file_path=storage_result['original_path']
            )

            return image_node

        except Exception as e:
            logger.error(f"Failed to create image node: {e}")
            return None

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
                study_date=datetime.now().strftime("%Y-%m-%d"),
                study_description=image_node.series_description
            )

            self.imaging_studies[study_id] = study

    def _calculate_storage_size(self) -> float:
        """Calculate total storage size in MB"""
        total_size = 0

        # Calculate size of all files in storage directory
        if self.storage_path.exists():
            for file_path in self.storage_path.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size

        return total_size / (1024 * 1024)  # Convert to MB

    def _aggregate_quality_metrics(self) -> Dict[str, Any]:
        """Aggregate quality metrics from all processed images"""
        metrics = {
            'avg_snr': 0,
            'avg_entropy': 0,
            'avg_contrast': 0,
            'total_images': 0
        }

        snr_values = []
        entropy_values = []
        contrast_values = []

        for result in self.storage_results:
            if result['success'] and 'storage_metadata' in result:
                quality = result['storage_metadata'].quality_metrics
                if 'snr' in quality:
                    snr_values.append(quality['snr'])
                if 'entropy' in quality:
                    entropy_values.append(quality['entropy'])
                if 'contrast' in quality:
                    contrast_values.append(quality['contrast'])

        if snr_values:
            metrics['avg_snr'] = sum(snr_values) / len(snr_values)
        if entropy_values:
            metrics['avg_entropy'] = sum(entropy_values) / len(entropy_values)
        if contrast_values:
            metrics['avg_contrast'] = sum(contrast_values) / len(contrast_values)

        metrics['total_images'] = len(self.storage_results)

        return metrics

    # Helper methods (same as original but adapted for storage)
    def _generate_image_id(self, patient_id: str, image_path: Path) -> str:
        """Generate unique image ID"""
        content = f"{patient_id}_{image_path}"
        hash_obj = hashlib.sha256(content.encode())
        return f"img_{hash_obj.hexdigest()[:16]}"

    def _generate_study_id(self, patient_id: str, modality: str, file_path: Path) -> str:
        """Generate study ID"""
        date_str = datetime.now().strftime("%Y%m%d")
        return f"study_{patient_id}_{modality}_{date_str}"

    def _extract_series_id(self, file_path: Path) -> str:
        """Extract series ID from file path"""
        # Try to get from parent directory name
        if file_path.parent.name not in ['.', '']:
            return file_path.parent.name
        return "default_series"

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

    def _infer_anatomical_region(self, description: str) -> str:
        """Infer anatomical region from description"""
        desc_lower = description.lower()

        if 'hippo' in desc_lower:
            return 'hippocampus'
        elif 'frontal' in desc_lower:
            return 'frontal_lobe'
        elif 'temporal' in desc_lower:
            return 'temporal_lobe'
        elif 'parietal' in desc_lower:
            return 'parietal_lobe'
        else:
            return 'whole_brain'

    def _infer_pet_tracer(self, description: str) -> Optional[str]:
        """Infer PET tracer from description"""
        desc_upper = description.upper()

        if 'FDG' in desc_upper:
            return 'FDG'
        elif 'AV45' in desc_upper or 'FLORBETAPIR' in desc_upper:
            return 'AV45'
        elif 'AV1451' in desc_upper or 'TAU' in desc_upper:
            return 'AV1451'
        elif 'PIB' in desc_upper:
            return 'PIB'

        return None

    def get_processing_summary(self) -> Dict[str, Any]:
        """Get summary of processed images"""
        summary = {
            'total_images': len(self.image_nodes),
            'total_studies': len(self.imaging_studies),
            'total_stored': len(self.storage_results),
            'by_modality': {},
            'by_type': {},
            'storage_stats': {
                'diagnostic_count': 0,
                'preview_count': 0,
                'thumbnail_count': 0
            },
            'quality_stats': {}
        }

        # Count by modality and type
        for img in self.image_nodes:
            # Modality
            modality = 'PET' if 'PET' in img.study_id else 'MRI'
            summary['by_modality'][modality] = summary['by_modality'].get(modality, 0) + 1

            # Type
            img_type = img.image_type
            summary['by_type'][img_type] = summary['by_type'].get(img_type, 0) + 1

            # Storage stats
            if hasattr(img, 'has_diagnostic') and img.has_diagnostic:
                summary['storage_stats']['diagnostic_count'] += 1
            if hasattr(img, 'has_preview') and img.has_preview:
                summary['storage_stats']['preview_count'] += 1
            if hasattr(img, 'has_thumbnail') and img.has_thumbnail:
                summary['storage_stats']['thumbnail_count'] += 1

        # Quality stats
        summary['quality_stats'] = self._aggregate_quality_metrics()

        return summary


def execute_image_processing(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                             base_path: str, storage_path: str | None = None,
                             store_blobs: bool = False,
                             max_workers: int = 8) -> Dict[str, Any]:
    """
    Main execution function for image processing with external storage

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Username
        neo4j_password: Password
        base_path: Base path containing image directories
        storage_path: Path for hierarchical image storage (optional)
        store_blobs: Whether to store images as blobs in Neo4j
        max_workers: Maximum number of parallel workers

    Returns:
        Processing results
    """
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        processor = ImageProcessingPipeline(
            connector,
            base_path,
            storage_path=storage_path,
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
        logger.info(f"   Stored {results['images_stored']} images in hierarchical storage")
        logger.info(f"   Total storage size: {results['storage_size_mb']:.2f} MB")

        if results['quality_metrics']:
            logger.info(f"   Average SNR: {results['quality_metrics'].get('avg_snr', 0):.2f}")
            logger.info(f"   Average entropy: {results['quality_metrics'].get('avg_entropy', 0):.2f}")

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
        storage_path="outputs/image_store",
        store_blobs=True,
        max_workers=4
    )

    print(f"Results: {results['summary']}")