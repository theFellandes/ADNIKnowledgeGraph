"""
Step 5: Process Medical Images with External Storage, Redis, and Elasticsearch
Fixed version that properly integrates caching and search capabilities
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import concurrent.futures
from datetime import datetime
import hashlib
import re
import json

from models.entities import ImagingStudy, ImageNode
from utils.batch_processor import BatchProcessor
from utils.neo4j_connector import Neo4jConnector

# Import cache and search managers
try:
    from utils.redis_cacher import CacheManager
except ImportError:
    CacheManager = None
    logging.warning("Redis cache manager not available")

try:
    from utils.elasticsearch_indexer import SearchIndexer
except ImportError:
    SearchIndexer = None
    logging.warning("Elasticsearch indexer not available")

# Try to import the medical image storage manager
try:
    from utils.medical_image_storage import MedicalImageStorageManager
except ImportError:
    MedicalImageStorageManager = None
    logging.warning("Medical image storage manager not available. Using simplified storage.")

logger = logging.getLogger(__name__)


def execute_image_processing_external(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    base_path: str,
    storage_path: str = None,
    storage_config: Dict[str, Any] = None,
    max_workers: int = 8,
    cache_manager: Optional[Any] = None,
    search_indexer: Optional[Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Main execution function for image processing with external storage, Redis, and Elasticsearch

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Username
        neo4j_password: Password
        base_path: Base path containing image directories
        storage_path: Path for hierarchical image storage
        storage_config: Storage configuration dictionary
        max_workers: Maximum number of parallel workers
        cache_manager: Optional Redis cache manager instance
        search_indexer: Optional Elasticsearch indexer instance
        **kwargs: Additional arguments

    Returns:
        Processing results dictionary
    """

    logger.info("Starting image processing with external storage, caching, and search")

    # Set default storage path if not provided
    if storage_path is None:
        storage_path = Path(base_path).parent / "outputs" / "image_store"
    else:
        storage_path = Path(storage_path)

    # Create storage directory
    storage_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Using storage path: {storage_path}")

    # Initialize Redis cache if not provided
    if cache_manager is None and CacheManager is not None:
        try:
            cache_manager = CacheManager(host='localhost', port=6379)
            logger.info("✅ Redis cache initialized")
        except Exception as e:
            logger.warning(f"Could not initialize Redis cache: {e}")
            cache_manager = None

    # Initialize Elasticsearch if not provided
    if search_indexer is None and SearchIndexer is not None:
        try:
            search_indexer = SearchIndexer(host='localhost', port=9200)
            logger.info("✅ Elasticsearch indexer initialized")
        except Exception as e:
            logger.warning(f"Could not initialize Elasticsearch: {e}")
            search_indexer = None

    # Initialize Neo4j connection
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        # Initialize processor
        processor = EnhancedImageProcessor(
            connector=connector,
            base_path=base_path,
            storage_path=storage_path,
            storage_config=storage_config or {},
            max_workers=max_workers,
            cache_manager=cache_manager,
            search_indexer=search_indexer
        )

        # Execute processing
        results = processor.execute()

        # Add processor to results for subsequent steps
        results['processor'] = processor

        return results

    except Exception as e:
        logger.error(f"Image processing failed: {e}")
        raise
    finally:
        connector.close()
        if cache_manager:
            cache_manager.close()
        if search_indexer:
            search_indexer.close()


class EnhancedImageProcessor:
    """
    Enhanced image processor with Redis caching and Elasticsearch indexing
    """

    def __init__(self, connector: Neo4jConnector,
                 base_path: str,
                 storage_path: Path,
                 storage_config: Dict[str, Any],
                 max_workers: int = 8,
                 cache_manager: Optional[Any] = None,
                 search_indexer: Optional[Any] = None):
        """Initialize enhanced image processor"""

        self.connector = connector
        self.base_path = Path(base_path)
        self.storage_path = storage_path
        self.storage_config = storage_config
        self.max_workers = max_workers
        self.cache_manager = cache_manager
        self.search_indexer = search_indexer

        # Image paths - check what exists
        self.mri_dicom_path = self.base_path / "Images"
        self.pet_dicom_path = self.base_path / "PET"
        self.mri_converted_path = self.base_path / "Updated"
        self.pet_converted_path = self.base_path / "Updated_PET"

        # Log which directories exist
        logger.info("Checking for image directories:")
        for name, path in [
            ("MRI DICOM", self.mri_dicom_path),
            ("PET DICOM", self.pet_dicom_path),
            ("MRI Converted", self.mri_converted_path),
            ("PET Converted", self.pet_converted_path)
        ]:
            if path.exists():
                logger.info(f"  ✓ {name}: {path}")
            else:
                logger.info(f"  ✗ {name}: Not found")

        # Storage for pipeline compatibility
        self.imaging_studies = {}
        self.image_nodes = []

        # Batch processor
        self.batch_processor = BatchProcessor(max_workers=max_workers)

        # Create storage subdirectories
        for subdir in ["metadata", "diagnostic", "preview", "thumbnail"]:
            (self.storage_path / subdir).mkdir(parents=True, exist_ok=True)

        # Initialize medical image storage manager if available
        if MedicalImageStorageManager:
            self.storage_manager = MedicalImageStorageManager(
                str(self.storage_path),
                neo4j_connector=connector
            )
        else:
            self.storage_manager = None

    def execute(self) -> Dict[str, Any]:
        """Execute enhanced image processing pipeline"""

        results = {
            'mri_processed': 0,
            'pet_processed': 0,
            'studies_created': 0,
            'images_created': 0,
            'images_stored': 0,
            'images_cached': 0,
            'images_indexed': 0,
            'storage_size_mb': 0,
            'errors': []
        }

        # Process converted images (JPG/PNG) - these are most likely to exist
        if self.mri_converted_path.exists():
            logger.info("Processing converted MRI images...")
            mri_results = self._process_converted_directory(self.mri_converted_path, 'MRI')
            results['mri_processed'] += mri_results['processed']
            results['images_cached'] += mri_results.get('cached', 0)
            results['images_indexed'] += mri_results.get('indexed', 0)
            results['errors'].extend(mri_results['errors'])

        if self.pet_converted_path.exists():
            logger.info("Processing converted PET images...")
            pet_results = self._process_converted_directory(self.pet_converted_path, 'PET')
            results['pet_processed'] += pet_results['processed']
            results['images_cached'] += pet_results.get('cached', 0)
            results['images_indexed'] += pet_results.get('indexed', 0)
            results['errors'].extend(pet_results['errors'])

        # Process DICOM if available and storage manager exists
        if self.storage_manager:
            if self.mri_dicom_path.exists():
                logger.info("Processing MRI DICOM with full storage...")
                mri_dicom_results = self._process_dicom_directory(self.mri_dicom_path, 'MRI')
                results['mri_processed'] += mri_dicom_results['processed']
                results['images_cached'] += mri_dicom_results.get('cached', 0)
                results['images_indexed'] += mri_dicom_results.get('indexed', 0)
                results['errors'].extend(mri_dicom_results['errors'])

            if self.pet_dicom_path.exists():
                logger.info("Processing PET DICOM with full storage...")
                pet_dicom_results = self._process_dicom_directory(self.pet_dicom_path, 'PET')
                results['pet_processed'] += pet_dicom_results['processed']
                results['images_cached'] += pet_dicom_results.get('cached', 0)
                results['images_indexed'] += pet_dicom_results.get('indexed', 0)
                results['errors'].extend(pet_dicom_results['errors'])

        # Update counts
        results['studies_created'] = len(self.imaging_studies)
        results['images_created'] = len(self.image_nodes)
        results['images_stored'] = len(self.image_nodes)  # All are "stored" as references

        # Calculate approximate storage size
        results['storage_size_mb'] = self._calculate_storage_size()

        logger.info(f"✅ Processed {results['images_created']} images")
        logger.info(f"   MRI: {results['mri_processed']}, PET: {results['pet_processed']}")
        logger.info(f"   Cached: {results['images_cached']}, Indexed: {results['images_indexed']}")

        return results

    def _process_converted_directory(self, directory: Path, modality: str) -> Dict[str, Any]:
        """Process pre-converted images (JPG/PNG) with caching and indexing"""

        results = {'processed': 0, 'cached': 0, 'indexed': 0, 'errors': []}

        # Find all image files
        image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png']:
            image_files.extend(directory.rglob(ext))

        logger.info(f"Found {len(image_files)} converted {modality} images")

        # Process in batches for better performance
        batch_size = 100
        for i in range(0, len(image_files), batch_size):
            batch = image_files[i:i+batch_size]

            # Prepare documents for bulk indexing
            es_documents = []

            for img_file in batch:
                try:
                    # Extract patient ID
                    patient_id = self._extract_patient_id(img_file)
                    if not patient_id:
                        continue

                    # Generate IDs
                    study_id = self._generate_study_id(patient_id, modality, img_file)
                    image_id = self._generate_image_id(patient_id, img_file)

                    # Find or create visit ID
                    visit_id = self._find_visit_id(patient_id, "")

                    # Extract series info from path
                    series_desc = img_file.parent.name if img_file.parent != directory else modality

                    # Create image node (without unsupported parameters)
                    image_node = ImageNode(
                        image_id=image_id,
                        study_id=study_id,
                        patient_id=patient_id,
                        visit_id=visit_id,
                        series_description=series_desc,
                        image_type='CONVERTED',
                        file_path=str(img_file),
                        # Store paths in existing fields
                        diagnostic_path=str(img_file),
                        preview_path=str(img_file),
                        thumbnail_path=str(img_file),
                        has_diagnostic=True,
                        has_preview=True,
                        has_thumbnail=True
                    )

                    self.image_nodes.append(image_node)
                    self._update_imaging_study(image_node)
                    results['processed'] += 1

                    # Cache metadata in Redis
                    if self.cache_manager:
                        cache_data = {
                            'image_id': image_id,
                            'patient_id': patient_id,
                            'study_id': study_id,
                            'visit_id': visit_id,
                            'modality': modality,
                            'series_description': series_desc,
                            'file_path': str(img_file),
                            'diagnostic_path': str(img_file),
                            'preview_path': str(img_file),
                            'thumbnail_path': str(img_file),
                            'timestamp': datetime.now().isoformat()
                        }

                        # Cache image metadata
                        if self.cache_manager.cache_image_metadata(image_id, cache_data):
                            results['cached'] += 1

                        # Cache image paths for quick retrieval
                        self.cache_manager.cache_image_path(image_id, 'diagnostic', str(img_file))
                        self.cache_manager.cache_image_path(image_id, 'preview', str(img_file))
                        self.cache_manager.cache_image_path(image_id, 'thumbnail', str(img_file))

                    # Prepare for Elasticsearch indexing
                    if self.search_indexer:
                        es_doc = {
                            'image_id': image_id,
                            'patient_id': patient_id,
                            'study_id': study_id,
                            'visit_id': visit_id,
                            'modality': modality,
                            'series_description': series_desc,
                            'anatomical_region': self._infer_anatomical_region(series_desc),
                            'pet_tracer': self._infer_pet_tracer(series_desc) if modality == 'PET' else None,
                            'storage_path': str(img_file),
                            'preview_path': str(img_file),
                            'thumbnail_path': str(img_file),
                            'timestamp': datetime.now().isoformat(),
                            'processing_status': 'completed',
                            'quality_verified': False
                        }
                        es_documents.append(es_doc)

                    # Save metadata to file
                    self._save_image_metadata(image_node)

                except Exception as e:
                    logger.error(f"Error processing {img_file}: {e}")
                    results['errors'].append(str(e))

            # Bulk index to Elasticsearch
            if self.search_indexer and es_documents:
                success_count, failed = self.search_indexer.bulk_index(
                    'medical_images',
                    es_documents,
                    id_field='image_id'
                )
                results['indexed'] += success_count
                if failed:
                    logger.warning(f"Failed to index {len(failed)} documents")

            if (i + batch_size) % 1000 == 0:
                logger.info(f"  Processed {min(i + batch_size, len(image_files))}/{len(image_files)} images")

        return results

    def _process_dicom_directory(self, directory: Path, modality: str) -> Dict[str, Any]:
        """Process DICOM files with full storage, caching, and indexing"""

        results = {'processed': 0, 'cached': 0, 'indexed': 0, 'errors': []}

        if not self.storage_manager:
            logger.warning("Storage manager not available for DICOM processing")
            return results

        # Check if pydicom is available
        try:
            import pydicom
        except ImportError:
            logger.warning("pydicom not installed. Skipping DICOM processing.")
            return results

        # Find all DICOM files
        dicom_files = list(directory.rglob("*.dcm"))
        logger.info(f"Found {len(dicom_files)} DICOM files")

        # Process a limited number for performance
        max_dicoms = min(len(dicom_files), 100)  # Process up to 100 DICOM files

        for dicom_file in dicom_files[:max_dicoms]:
            try:
                # Extract patient ID from path first
                patient_id = self._extract_patient_id(dicom_file)
                if not patient_id:
                    continue

                # Generate IDs
                study_id = self._generate_study_id(patient_id, modality, dicom_file)
                series_id = self._extract_series_id(dicom_file)

                # Process with storage manager
                storage_metadata = self.storage_manager.process_dicom_for_storage(
                    str(dicom_file),
                    patient_id,
                    study_id,
                    series_id
                )

                # Find visit
                visit_id = self._find_visit_id(patient_id, "")

                # Create image node
                image_node = ImageNode(
                    image_id=storage_metadata.storage_id,
                    study_id=study_id,
                    patient_id=patient_id,
                    visit_id=visit_id,
                    series_description=series_id,
                    image_type='DICOM',
                    file_path=str(dicom_file),
                    diagnostic_path=storage_metadata.file_paths.get('diagnostic'),
                    preview_path=storage_metadata.file_paths.get('preview'),
                    thumbnail_path=storage_metadata.file_paths.get('thumbnail'),
                    has_diagnostic=True,
                    has_preview=True,
                    has_thumbnail=True,
                    # Store quality metrics
                    snr=storage_metadata.quality_metrics.get('snr'),
                    entropy=storage_metadata.quality_metrics.get('entropy')
                )

                self.image_nodes.append(image_node)
                self._update_imaging_study(image_node)
                results['processed'] += 1

                # Cache in Redis
                if self.cache_manager:
                    cache_data = {
                        'image_id': storage_metadata.storage_id,
                        'patient_id': patient_id,
                        'study_id': study_id,
                        'visit_id': visit_id,
                        'modality': modality,
                        'storage_metadata': asdict(storage_metadata),
                        'timestamp': datetime.now().isoformat()
                    }

                    if self.cache_manager.cache_image_metadata(storage_metadata.storage_id, cache_data):
                        results['cached'] += 1

                    # Cache paths
                    for resolution, path in storage_metadata.file_paths.items():
                        self.cache_manager.cache_image_path(storage_metadata.storage_id, resolution, path)

                # Index in Elasticsearch
                if self.search_indexer:
                    es_doc = {
                        'image_id': storage_metadata.storage_id,
                        'patient_id': patient_id,
                        'study_id': study_id,
                        'visit_id': visit_id,
                        'modality': modality,
                        'series_description': series_id,
                        'storage_path': storage_metadata.file_paths.get('diagnostic'),
                        'preview_path': storage_metadata.file_paths.get('preview'),
                        'thumbnail_path': storage_metadata.file_paths.get('thumbnail'),
                        'quality_metrics': storage_metadata.quality_metrics,
                        'dimensions': list(storage_metadata.dimensions),
                        'voxel_spacing': list(storage_metadata.voxel_spacing) if storage_metadata.voxel_spacing else None,
                        'checksum': storage_metadata.checksums.get('diagnostic'),
                        'timestamp': storage_metadata.storage_timestamp,
                        'processing_status': 'completed',
                        'quality_verified': True
                    }

                    if self.search_indexer.index_document('medical_images', es_doc, doc_id=storage_metadata.storage_id):
                        results['indexed'] += 1

            except Exception as e:
                logger.debug(f"Error processing DICOM {dicom_file}: {e}")
                results['errors'].append(str(e))

        if max_dicoms < len(dicom_files):
            logger.info(f"  Processed {max_dicoms} of {len(dicom_files)} DICOM files (limited for performance)")

        return results

    def _save_image_metadata(self, image_node: ImageNode) -> None:
        """Save image metadata to JSON file"""

        metadata_file = self.storage_path / "metadata" / f"{image_node.image_id}.json"

        # Convert image node to dictionary
        metadata = {
            'image_id': image_node.image_id,
            'patient_id': image_node.patient_id,
            'study_id': image_node.study_id,
            'visit_id': image_node.visit_id,
            'series_description': image_node.series_description,
            'image_type': image_node.image_type,
            'file_path': image_node.file_path,
            'diagnostic_path': image_node.diagnostic_path,
            'preview_path': image_node.preview_path,
            'thumbnail_path': image_node.thumbnail_path,
            'created_at': datetime.now().isoformat()
        }

        # Save to JSON
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

    def _update_imaging_study(self, image_node: ImageNode) -> None:
        """Create or update imaging study"""

        study_id = image_node.study_id

        if study_id not in self.imaging_studies:
            study = ImagingStudy(
                study_id=study_id,
                patient_id=image_node.patient_id,
                visit_id=image_node.visit_id,
                modality='PET' if 'PET' in study_id else 'MRI',
                study_date=datetime.now().strftime("%Y-%m-%d"),
                study_description=image_node.series_description
            )
            self.imaging_studies[study_id] = study

    def _calculate_storage_size(self) -> float:
        """Calculate approximate storage size"""

        total_size = 0

        # Calculate size of storage directory
        if self.storage_path.exists():
            for file_path in self.storage_path.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size

        # Also include referenced files
        for image_node in self.image_nodes:
            if image_node.file_path and Path(image_node.file_path).exists():
                try:
                    total_size += Path(image_node.file_path).stat().st_size
                except:
                    pass

        return total_size / (1024 * 1024)  # Convert to MB

    # Helper methods

    def _extract_patient_id(self, path: Path) -> Optional[str]:
        """Extract patient ID from path"""

        # Check filename and parent directories
        path_str = str(path)
        match = re.search(r'(\d{3}_S_\d{4})', path_str)
        if match:
            return match.group(1)

        # Check each parent directory
        for parent in path.parents:
            if re.match(r'^\d{3}_S_\d{4}$', parent.name):
                return parent.name

        return None

    def _generate_study_id(self, patient_id: str, modality: str, file_path: Path) -> str:
        """Generate study ID"""

        # Try to extract date from path
        date_match = re.search(r'(\d{8})', str(file_path))
        if date_match:
            date_str = date_match.group(1)
        else:
            date_str = datetime.now().strftime("%Y%m%d")

        return f"study_{patient_id}_{modality}_{date_str}"

    def _generate_image_id(self, patient_id: str, image_path: Path) -> str:
        """Generate unique image ID"""

        content = f"{patient_id}_{image_path.name}_{image_path.stat().st_size}"
        hash_obj = hashlib.sha256(content.encode())
        return f"img_{hash_obj.hexdigest()[:16]}"

    def _extract_series_id(self, file_path: Path) -> str:
        """Extract series ID from file path"""

        # Try to get from parent directory name
        if file_path.parent.name not in ['.', '']:
            return file_path.parent.name
        return "default_series"

    def _find_visit_id(self, patient_id: str, study_date: str) -> str:
        """Find or create visit ID"""

        # Format study date if needed
        if study_date and len(study_date) == 8:
            study_date = f"{study_date[:4]}-{study_date[4:6]}-{study_date[6:8]}"

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


# Import function for asdict if not available
try:
    from dataclasses import asdict
except ImportError:
    def asdict(obj):
        """Simple conversion to dict for dataclass-like objects"""
        return {k: getattr(obj, k) for k in dir(obj) if not k.startswith('_')}