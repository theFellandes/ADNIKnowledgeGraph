"""
Step 5: Process Medical Images with Proper Path Handling
Ensures absolute paths are stored in both Neo4j and Elasticsearch
"""

import logging
import json
import hashlib
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import concurrent.futures
from dataclasses import dataclass, asdict

from models.entities import ImagingStudy, ImageNode
from utils.dcm2png_parallel import drain_new_dicoms, DICOMtoFSConverter
from utils.neo4j_connector import Neo4jConnector
from utils.batch_processor import BatchProcessor
from utils.elasticsearch_indexer import SearchIndexer

logger = logging.getLogger(__name__)


@dataclass
class ImageMetadataExtended:
    """Extended metadata for images with all absolute paths"""
    image_hash: str
    patient_id: str
    study_id: str
    series_id: str
    modality: str
    dcm_path: str  # Absolute path to original DICOM
    png_path: str  # Absolute path to full resolution PNG
    thumbnail_path: str  # Absolute path to thumbnail PNG
    original_resolution: Tuple[int, int]
    png_resolution: Tuple[int, int]
    thumbnail_resolution: Tuple[int, int]
    conversion_date: str
    study_date: str
    series_description: str
    dicom_metadata: Dict[str, Any]
    naming_convention: str
    processing_status: str = "completed"
    quality_verified: bool = True


class IncrementalImageProcessingPipeline:
    """Incremental image processing pipeline with proper absolute path handling"""

    def __init__(self, connector: Neo4jConnector, base_path: str,
                 storage_path: str, es_host: str = 'localhost',
                 es_port: int = 9200, batch_size: int = 100,
                 max_workers: int = 8):
        """Initialize pipeline with incremental processing support"""
        self.connector = connector
        self.base_path = Path(base_path).resolve()  # Ensure absolute path
        self.storage_path = Path(storage_path).resolve()  # Ensure absolute path
        self.batch_size = batch_size
        self.max_workers = max_workers

        # Set up paths for incremental processing
        self.new_mri_path = self.base_path / "New_MRI"
        self.new_pet_path = self.base_path / "New_PET"
        self.mri_dcm_path = self.base_path / "MRI_DCM"
        self.pet_dcm_path = self.base_path / "PET_DCM"

        # Output paths (absolute)
        self.png_output_path = self.storage_path / "png_images"
        self.thumbnail_output_path = self.storage_path / "thumbnails"
        self.metadata_path = self.storage_path / "metadata"

        # Create directories
        for p in [self.new_mri_path, self.new_pet_path, self.mri_dcm_path,
                  self.pet_dcm_path, self.png_output_path, self.thumbnail_output_path,
                  self.metadata_path]:
            p.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.batch_processor = BatchProcessor(max_workers=max_workers)
        self.es_indexer = SearchIndexer(es_host, es_port)

        # Storage for processing
        self.processed_hashes = set()
        self.image_metadata = []
        self.processing_stats = {
            'total_found': 0,
            'new_images': 0,
            'moved': 0,
            'converted': 0,
            'already_processed': 0,
            'indexed_es': 0,
            'indexed_neo4j': 0,
            'failed': 0
        }

    def _ensure_absolute_path(self, path_str: str) -> str:
        """Ensure a path is absolute"""
        if not path_str:
            return ""
        path = Path(path_str)
        if not path.is_absolute():
            # Try to resolve relative to storage path or base path
            if (self.storage_path / path).exists():
                return str((self.storage_path / path).resolve())
            elif (self.base_path / path).exists():
                return str((self.base_path / path).resolve())
            else:
                return str(path.resolve())
        return str(path.resolve())

    def execute(self) -> Dict[str, Any]:
        """Execute the incremental processing pipeline"""
        start_time = datetime.now()

        results = {
            'images_processed': 0,
            'images_converted': 0,
            'images_indexed_es': 0,
            'images_indexed_neo4j': 0,
            'processing_time': 0,
            'errors': []
        }

        try:
            # Step 1: Load existing images from Elasticsearch to avoid duplicates
            logger.info("Loading existing images from Elasticsearch for deduplication...")
            self._load_existing_images()

            # Step 2: Move new DICOM files to processing folders
            logger.info("Moving new DICOM files to processing folders...")
            move_results = self._move_new_dicoms()
            self.processing_stats['moved'] = move_results['total_moved']

            # Step 3: Run incremental DICOM conversion
            logger.info("Running incremental DICOM to PNG conversion...")
            conversion_results = self._run_incremental_conversion()
            results['images_converted'] = conversion_results['converted']
            self.processing_stats['converted'] = conversion_results['converted']

            # Step 4: Process metadata for newly converted images
            logger.info("Processing metadata for newly converted images...")
            metadata_results = self._process_new_metadata()
            results['images_processed'] = metadata_results['processed']

            # Step 5: Index to Elasticsearch (incremental)
            logger.info("Indexing new images to Elasticsearch...")
            es_results = self._index_to_elasticsearch_incremental()
            results['images_indexed_es'] = es_results['indexed']

            # Step 6: Create Neo4j nodes (with duplicate checking)
            logger.info("Creating Neo4j nodes for new images...")
            neo4j_results = self._create_neo4j_nodes_incremental()
            results['images_indexed_neo4j'] = neo4j_results['created']

            # Calculate total time
            total_time = (datetime.now() - start_time).total_seconds()
            results['processing_time'] = total_time
            results['statistics'] = self.processing_stats

            self._log_summary(results)

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            results['errors'].append(str(e))
            raise

        return results

    def _load_existing_images(self) -> None:
        """Load existing image hashes from Elasticsearch to prevent duplicates"""
        try:
            existing_images = self.es_indexer.get_all_image_hashes()
            self.processed_hashes = set(existing_images)
            logger.info(f"Loaded {len(self.processed_hashes)} existing image hashes from Elasticsearch")
        except Exception as e:
            logger.warning(f"Could not load existing images from Elasticsearch: {e}")
            self.processed_hashes = set()

    def _move_new_dicoms(self) -> Dict[str, int]:
        """Move DICOM files from New_* folders to *_DCM folders preserving structure"""
        moved_stats = {'MRI': 0, 'PET': 0, 'total_moved': 0}

        # Move MRI DICOMs
        if self.new_mri_path.exists():
            moved_stats['MRI'] = self._move_files_preserving_structure(
                self.new_mri_path, self.mri_dcm_path
            )

        # Move PET DICOMs
        if self.new_pet_path.exists():
            moved_stats['PET'] = self._move_files_preserving_structure(
                self.new_pet_path, self.pet_dcm_path
            )

        moved_stats['total_moved'] = moved_stats['MRI'] + moved_stats['PET']
        logger.info(f"Moved {moved_stats['MRI']} MRI and {moved_stats['PET']} PET DICOM files")

        return moved_stats

    def _move_files_preserving_structure(self, source_dir: Path, dest_dir: Path) -> int:
        """Move files from source to destination preserving folder structure"""
        moved_count = 0

        for file_path in source_dir.rglob('*'):
            if file_path.is_file():
                relative_path = file_path.relative_to(source_dir)
                dest_path = dest_dir / relative_path

                dest_path.parent.mkdir(parents=True, exist_ok=True)

                if not dest_path.exists():
                    shutil.move(str(file_path), str(dest_path))
                    moved_count += 1
                    logger.debug(f"Moved: {relative_path}")
                else:
                    file_path.unlink()
                    logger.debug(f"File already exists, removed from source: {relative_path}")

        self._cleanup_empty_dirs(source_dir)

        return moved_count

    def _cleanup_empty_dirs(self, root_dir: Path) -> None:
        """Remove empty directories while preserving root"""
        for dirpath in sorted(root_dir.rglob('*'), reverse=True):
            if dirpath.is_dir() and dirpath != root_dir:
                try:
                    dirpath.rmdir()
                except OSError:
                    pass

    def _run_incremental_conversion(self) -> Dict[str, Any]:
        """Run incremental DICOM to PNG conversion"""
        converter_mri = DICOMtoFSConverter(
            input_dir=str(self.mri_dcm_path),
            output_dir=str(self.storage_path),
            modality='MRI',
            skip_if_exists=True
        )

        converter_pet = DICOMtoFSConverter(
            input_dir=str(self.pet_dcm_path),
            output_dir=str(self.storage_path),
            modality='PET',
            skip_if_exists=True
        )

        mri_stats = converter_mri.convert_all()
        pet_stats = converter_pet.convert_all()

        return {
            'converted': mri_stats['converted'] + pet_stats['converted'],
            'skipped': mri_stats['skipped'] + pet_stats['skipped'],
            'failed': mri_stats['errors'] + pet_stats['errors'],
            'mri_stats': mri_stats,
            'pet_stats': pet_stats
        }

    def _process_new_metadata(self) -> Dict[str, Any]:
        """Process metadata only for newly converted images with absolute paths"""
        processed_count = 0

        metadata_files = []
        for metadata_dir in [self.metadata_path / 'MRI', self.metadata_path / 'PET']:
            if metadata_dir.exists():
                for json_file in metadata_dir.rglob('*.json'):
                    file_hash = self._calculate_file_hash(json_file)

                    if file_hash not in self.processed_hashes:
                        metadata_files.append(json_file)

        logger.info(f"Found {len(metadata_files)} new metadata files to process")

        for i in range(0, len(metadata_files), self.batch_size):
            batch = metadata_files[i:i + self.batch_size]
            batch_results = self._process_metadata_batch(batch)
            processed_count += batch_results['processed']

        return {'processed': processed_count}

    def _process_metadata_batch(self, metadata_files: List[Path]) -> Dict[str, Any]:
        """Process a batch of metadata files with absolute path conversion"""
        processed = 0

        for metadata_file in metadata_files:
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                image_hash = self._calculate_image_hash(metadata)

                if image_hash in self.processed_hashes:
                    self.processing_stats['already_processed'] += 1
                    continue

                # Ensure all paths are absolute
                dcm_path = self._ensure_absolute_path(metadata.get('dcm_path', metadata.get('original_path', '')))
                png_path = self._ensure_absolute_path(metadata.get('png_path', ''))
                thumbnail_path = self._ensure_absolute_path(metadata.get('thumbnail_path', ''))

                # Create extended metadata object with absolute paths
                extended_metadata = ImageMetadataExtended(
                    image_hash=image_hash,
                    patient_id=metadata.get('patient_id', ''),
                    study_id=metadata.get('study_id', ''),
                    series_id=metadata.get('series_id', ''),
                    modality=metadata.get('modality', ''),
                    dcm_path=dcm_path,  # Now absolute
                    png_path=png_path,  # Now absolute
                    thumbnail_path=thumbnail_path,  # Now absolute
                    original_resolution=tuple(metadata.get('original_resolution', [0, 0])),
                    png_resolution=tuple(metadata.get('png_resolution', [0, 0])),
                    thumbnail_resolution=tuple(metadata.get('thumbnail_resolution', [128, 128])),
                    conversion_date=metadata.get('conversion_date', datetime.now().isoformat()),
                    study_date=metadata.get('study_date', ''),
                    series_description=metadata.get('series_description', ''),
                    dicom_metadata=metadata.get('dicom_metadata', {}),
                    naming_convention=metadata.get('naming_convention', '')
                )

                self.image_metadata.append(extended_metadata)
                self.processed_hashes.add(image_hash)
                processed += 1

            except Exception as e:
                logger.error(f"Error processing metadata file {metadata_file}: {e}")
                self.processing_stats['failed'] += 1

        return {'processed': processed}

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate hash for a file path"""
        return hashlib.md5(str(file_path).encode()).hexdigest()

    def _calculate_image_hash(self, metadata: Dict[str, Any]) -> str:
        """Calculate unique hash for an image based on its metadata"""
        hash_string = f"{metadata.get('patient_id', '')}_{metadata.get('study_date', '')}_{metadata.get('series_id', '')}_{metadata.get('original_path', metadata.get('dcm_path', ''))}"
        return hashlib.sha256(hash_string.encode()).hexdigest()[:32]

    def _index_to_elasticsearch_incremental(self) -> Dict[str, int]:
        """Index only new images to Elasticsearch with absolute paths"""
        if not self.image_metadata:
            return {'indexed': 0}

        indexed_count = 0
        failed_ids = []

        for i in range(0, len(self.image_metadata), self.batch_size):
            batch = self.image_metadata[i:i + self.batch_size]

            es_documents = []
            for metadata in batch:
                # Ensure paths are absolute in ES document
                es_doc = {
                    'image_hash': metadata.image_hash,
                    'patient_id': metadata.patient_id,
                    'study_id': metadata.study_id,
                    'series_id': metadata.series_id,
                    'modality': metadata.modality,
                    'dcm_path': metadata.dcm_path,  # Already absolute
                    'png_path': metadata.png_path,  # Already absolute
                    'thumbnail_path': metadata.thumbnail_path,  # Already absolute
                    'original_resolution': {
                        'width': metadata.original_resolution[0],
                        'height': metadata.original_resolution[1]
                    },
                    'png_resolution': {
                        'width': metadata.png_resolution[0],
                        'height': metadata.png_resolution[1]
                    },
                    'thumbnail_resolution': {
                        'width': metadata.thumbnail_resolution[0],
                        'height': metadata.thumbnail_resolution[1]
                    },
                    'conversion_date': metadata.conversion_date,
                    'study_date': metadata.study_date,
                    'series_description': metadata.series_description,
                    'naming_convention': metadata.naming_convention,
                    'indexed_date': datetime.now().isoformat()
                }
                es_documents.append(es_doc)

            success, failed = self.es_indexer.bulk_index_images(es_documents)
            indexed_count += success
            failed_ids.extend(failed)

        self.processing_stats['indexed_es'] = indexed_count

        if failed_ids:
            logger.warning(f"Failed to index {len(failed_ids)} images to Elasticsearch")

        return {'indexed': indexed_count, 'failed': failed_ids}

    def _create_neo4j_nodes_incremental(self) -> Dict[str, int]:
        """Create Neo4j nodes only for new images with absolute paths"""
        if not self.image_metadata:
            return {'created': 0}

        created_count = 0

        existing_neo4j = self._get_existing_neo4j_images()

        new_images = [
            img for img in self.image_metadata
            if img.image_hash not in existing_neo4j
        ]

        if not new_images:
            logger.info("No new images to add to Neo4j")
            return {'created': 0}

        studies_created = self._create_imaging_studies(new_images)
        images_created = self._create_image_nodes(new_images)

        created_count = studies_created + images_created
        self.processing_stats['indexed_neo4j'] = created_count

        return {'created': created_count}

    def _get_existing_neo4j_images(self) -> set:
        """Get existing image hashes from Neo4j"""
        query = """
        MATCH (img:ImageNode)
        WHERE img.image_hash IS NOT NULL
        RETURN img.image_hash as hash
        """

        results = self.connector.run_query(query)
        return {r['hash'] for r in results if r.get('hash')}

    def _create_imaging_studies(self, images: List[ImageMetadataExtended]) -> int:
        """Create imaging study nodes in Neo4j"""
        studies = {}
        for img in images:
            if img.study_id not in studies:
                studies[img.study_id] = {
                    'study_id': img.study_id,
                    'patient_id': img.patient_id,
                    'modality': img.modality,
                    'study_date': img.study_date,
                    'created_at': datetime.now().isoformat()
                }

        if not studies:
            return 0

        query = """
        UNWIND $batch as study
        MERGE (s:ImagingStudy {study_id: study.study_id})
        SET s.patient_id = study.patient_id,
            s.modality = study.modality,
            s.study_date = study.study_date,
            s.created_at = study.created_at
        WITH s, study
        MATCH (p:Patient {ptid: study.patient_id})
        MERGE (p)-[:HAS_IMAGING_STUDY]->(s)
        """

        return self.connector.batch_write(query, list(studies.values()), batch_size=100)

    def _create_image_nodes(self, images: List[ImageMetadataExtended]) -> int:
        """Create image nodes in Neo4j with all metadata and absolute paths"""
        image_data = []

        for img in images:
            data = {
                'image_hash': img.image_hash,
                'image_id': img.image_hash[:16],
                'study_id': img.study_id,
                'patient_id': img.patient_id,
                'series_id': img.series_id,
                'series_description': img.series_description,
                'modality': img.modality,
                'dcm_path': img.dcm_path,  # Absolute path
                'png_path': img.png_path,  # Absolute path
                'thumbnail_path': img.thumbnail_path,  # Absolute path
                'study_date': img.study_date,
                'conversion_date': img.conversion_date,
                'naming_convention': img.naming_convention,
                'processing_status': img.processing_status,
                'quality_verified': img.quality_verified,
                'created_at': datetime.now().isoformat(),
                'original_width': img.original_resolution[0],
                'original_height': img.original_resolution[1],
                'png_width': img.png_resolution[0],
                'png_height': img.png_resolution[1]
            }

            if img.dicom_metadata:
                data['dicom_metadata'] = json.dumps(img.dicom_metadata)

            image_data.append(data)

        query = """
        UNWIND $batch as image
        MERGE (i:ImageNode {image_hash: image.image_hash})
        SET i += image
        WITH i, image
        MATCH (s:ImagingStudy {study_id: image.study_id})
        MERGE (s)-[:HAS_IMAGE]->(i)
        WITH i, image
        MATCH (p:Patient {ptid: image.patient_id})
        MERGE (p)-[:HAS_IMAGE]->(i)
        """

        return self.connector.batch_write(query, image_data, batch_size=50)

    def _log_summary(self, results: Dict[str, Any]) -> None:
        """Log processing summary"""
        logger.info("\n" + "="*60)
        logger.info("INCREMENTAL IMAGE PROCESSING SUMMARY")
        logger.info("="*60)
        logger.info(f"Files moved to DCM folders: {self.processing_stats['moved']}")
        logger.info(f"Images converted to PNG: {self.processing_stats['converted']}")
        logger.info(f"Images already processed: {self.processing_stats['already_processed']}")
        logger.info(f"New images indexed to Elasticsearch: {self.processing_stats['indexed_es']}")
        logger.info(f"New images added to Neo4j: {self.processing_stats['indexed_neo4j']}")
        logger.info(f"Failed: {self.processing_stats['failed']}")
        logger.info(f"Total processing time: {results['processing_time']:.2f} seconds")
        logger.info("="*60)


def execute_image_processing_external(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                                     base_path: str, storage_path: str,
                                     storage_config: Dict[str, Any] = None,
                                     max_workers: int = 8) -> Dict[str, Any]:
    """Main execution function for incremental image processing"""
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        config = storage_config or {}
        batch_size = config.get('batch_size', 100)
        es_host = config.get('es_host', 'localhost')
        es_port = config.get('es_port', 9200)

        logger.info(f"Starting incremental image processing pipeline")
        logger.info(f"  Base path: {base_path}")
        logger.info(f"  Storage path: {storage_path}")
        logger.info(f"  Elasticsearch: {es_host}:{es_port}")

        processor = IncrementalImageProcessingPipeline(
            connector=connector,
            base_path=base_path,
            storage_path=storage_path,
            es_host=es_host,
            es_port=es_port,
            batch_size=batch_size,
            max_workers=max_workers
        )

        results = processor.execute()
        results['processor'] = processor

        logger.info(f"✅ Incremental image processing completed")
        return results

    except Exception as e:
        logger.error(f"Image processing failed: {e}")
        raise
    finally:
        connector.close()