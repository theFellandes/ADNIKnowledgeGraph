"""
Step 5: Batch-Based Image Processing for Large Datasets
Processes images in manageable batches without loading all paths into memory
"""

import logging
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Generator, Tuple
from datetime import datetime
import concurrent.futures
import pydicom
import nibabel as nib
import numpy as np
from PIL import Image
import os
import time
import gc

from models.entities import ImagingStudy, ImageNode
from utils.neo4j_connector import Neo4jConnector
from utils.batch_processor import BatchProcessor
from utils.elasticsearch_indexer import SearchIndexer

logger = logging.getLogger(__name__)


class OptimizedImageProcessor:
    """Optimized image processing with proper batching"""

    def __init__(self, connector: Neo4jConnector, base_path: str,
                 storage_path: str, es_host: str = 'localhost',
                 es_port: int = 9200, batch_size: int = 100,
                 max_workers: int = 4):
        self.connector = connector
        self.base_path = Path(base_path).resolve()
        self.storage_path = Path(storage_path).resolve()
        self.batch_size = batch_size  # Files per batch
        self.max_workers = max_workers

        # Base directories
        self.metadata_base = self.storage_path / "metadata"
        self.png_base = self.storage_path / "png"
        self.thumbnail_base = self.storage_path / "thumbnails"

        # Create base directories
        for dir_path in [self.metadata_base, self.png_base, self.thumbnail_base]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.batch_processor = BatchProcessor(max_workers=max_workers)
        self.es_indexer = SearchIndexer(es_host, es_port) if es_host else None

        # Track processed files
        self.checkpoint_file = self.storage_path / "processing_checkpoint.json"
        self.processed_files = self._load_checkpoint()

        # Create indexes
        self._create_optimized_indexes()

        self.processing_stats = {
            'total_files_scanned': 0,
            'total_batches': 0,
            'images_processed': 0,
            'neo4j_inserted': 0,
            'es_indexed': 0,
            'errors': 0,
            'skipped': 0
        }

    def _create_optimized_indexes(self):
        """Create optimized indexes for fast insertion"""
        logger.info("Creating optimized indexes...")

        queries = [
            "CREATE INDEX IF NOT EXISTS FOR (i:ImageNode) ON (i.patient_id, i.study_id)",
            "CREATE INDEX IF NOT EXISTS FOR (i:ImageNode) ON (i.image_hash)",
            "CREATE INDEX IF NOT EXISTS FOR (s:ImagingStudy) ON (s.patient_id, s.study_date)",
            "CREATE INDEX IF NOT EXISTS FOR (p:Patient) ON (p.ptid)"
        ]

        for query in queries:
            try:
                self.connector.execute_write_transaction(query)
            except:
                pass

    def _load_checkpoint(self) -> set:
        """Load checkpoint of processed files"""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, 'r') as f:
                    data = json.load(f)
                    return set(data.get('processed_files', []))
            except:
                return set()
        return set()

    def _save_checkpoint(self):
        """Save checkpoint of processed files"""
        try:
            with open(self.checkpoint_file, 'w') as f:
                json.dump({
                    'processed_files': list(self.processed_files),
                    'stats': self.processing_stats,
                    'last_update': datetime.now().isoformat()
                }, f)
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    def execute(self) -> Dict[str, Any]:
        """Execute batch-based image processing"""
        start_time = datetime.now()

        logger.info("=" * 60)
        logger.info("Starting Batch-Based Image Processing")
        logger.info(f"Batch size: {self.batch_size} files")
        logger.info(f"Previously processed: {len(self.processed_files)} files")
        logger.info("=" * 60)

        # Get existing images from database
        existing_hashes = self._get_existing_image_hashes()
        logger.info(f"Found {len(existing_hashes)} existing images in database")

        # Process each directory separately
        image_dirs = [
            self.base_path / "New_MRI",
            self.base_path / "New_PET",
            self.base_path / "Updated",
            self.base_path / "Updated_PET"
        ]

        for img_dir in image_dirs:
            if not img_dir.exists():
                logger.warning(f"Directory not found: {img_dir}")
                continue

            logger.info(f"\n📁 Processing directory: {img_dir}")
            self._process_directory_in_batches(img_dir, existing_hashes)

        # Final statistics
        self.processing_stats['time_taken'] = (datetime.now() - start_time).total_seconds()

        logger.info("\n" + "=" * 60)
        logger.info("Batch Processing Complete")
        logger.info(f"Total files scanned: {self.processing_stats['total_files_scanned']:,}")
        logger.info(f"Total batches processed: {self.processing_stats['total_batches']:,}")
        logger.info(f"Images processed: {self.processing_stats['images_processed']:,}")
        logger.info(f"Images inserted to Neo4j: {self.processing_stats['neo4j_inserted']:,}")
        logger.info(f"Images indexed to ES: {self.processing_stats['es_indexed']:,}")
        logger.info(f"Errors: {self.processing_stats['errors']:,}")
        logger.info(f"Skipped (already processed): {self.processing_stats['skipped']:,}")
        logger.info(f"Time taken: {self.processing_stats['time_taken']:.2f} seconds")
        logger.info("=" * 60)

        return self.processing_stats

    def _process_directory_in_batches(self, directory: Path, existing_hashes: set):
        """Process a directory in batches"""
        batch_num = 0

        # Use generator to scan files without loading all into memory
        for batch in self._scan_directory_in_batches(directory):
            batch_num += 1
            batch_start = datetime.now()

            logger.info(f"  Batch {batch_num}: Processing {len(batch)} files...")

            # Filter out already processed files
            new_files = []
            for file_path in batch:
                file_str = str(file_path)
                if file_str in self.processed_files:
                    self.processing_stats['skipped'] += 1
                else:
                    new_files.append(file_path)

            if not new_files:
                logger.info(f"    All files in batch already processed, skipping...")
                continue

            # Process the batch
            metadata_list = self._process_batch(new_files, existing_hashes)

            if metadata_list:
                # Insert to Neo4j
                neo4j_count = self._insert_batch_to_neo4j(metadata_list)
                self.processing_stats['neo4j_inserted'] += neo4j_count

                # Index to Elasticsearch
                if self.es_indexer:
                    es_count = self._index_batch_to_elasticsearch(metadata_list)
                    self.processing_stats['es_indexed'] += es_count

                # Update processed files
                for file_path in new_files:
                    self.processed_files.add(str(file_path))

                # Save checkpoint after each batch
                self._save_checkpoint()

            batch_time = (datetime.now() - batch_start).total_seconds()
            logger.info(f"    Batch {batch_num} complete: "
                       f"{len(metadata_list)} processed in {batch_time:.2f}s")

            # Force garbage collection between batches
            gc.collect()

            self.processing_stats['total_batches'] += 1

    def _scan_directory_in_batches(self, directory: Path) -> Generator[List[Path], None, None]:
        """Generator that yields batches of file paths"""
        batch = []

        logger.info(f"  Scanning {directory} for image files...")

        for root, dirs, files in os.walk(directory):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            # Limit depth to avoid very deep recursion
            depth = len(Path(root).relative_to(directory).parts)
            if depth > 5:
                dirs.clear()
                continue

            for file in files:
                # Skip hidden and temp files
                if file.startswith('.') or file.startswith('~'):
                    continue

                file_path = Path(root) / file
                file_lower = file.lower()

                # Check if it's an image file
                is_image = False

                if file_lower.endswith(('.dcm', '.nii', '.nii.gz')):
                    is_image = True
                elif '.' not in file:
                    # Could be DICOM without extension
                    if self._quick_dicom_check(file_path):
                        is_image = True

                if is_image:
                    batch.append(file_path)
                    self.processing_stats['total_files_scanned'] += 1

                    # Yield batch when it reaches the size limit
                    if len(batch) >= self.batch_size:
                        yield batch
                        batch = []

                    # Log progress
                    if self.processing_stats['total_files_scanned'] % 1000 == 0:
                        logger.info(f"    Scanned {self.processing_stats['total_files_scanned']:,} files so far...")

        # Yield remaining files
        if batch:
            yield batch

    def _quick_dicom_check(self, file_path: Path) -> bool:
        """Quick check if file is DICOM"""
        try:
            # Check file size first
            if file_path.stat().st_size < 10000:
                return False

            # Check for DICOM magic number
            with open(file_path, 'rb') as f:
                f.seek(128)
                return f.read(4) == b'DICM'
        except:
            return False

    def _process_batch(self, file_paths: List[Path], existing_hashes: set) -> List[Dict]:
        """Process a batch of files"""
        metadata_list = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._process_single_image, fp, existing_hashes): fp
                for fp in file_paths
            }

            for future in concurrent.futures.as_completed(futures):
                try:
                    metadata = future.result(timeout=30)  # 30 second timeout per file
                    if metadata:
                        metadata_list.append(metadata)
                        self.processing_stats['images_processed'] += 1
                except concurrent.futures.TimeoutError:
                    file_path = futures[future]
                    logger.warning(f"Timeout processing {file_path}")
                    self.processing_stats['errors'] += 1
                except Exception as e:
                    file_path = futures[future]
                    logger.error(f"Error processing {file_path}: {e}")
                    self.processing_stats['errors'] += 1

        return metadata_list

    def _process_single_image(self, img_file: Path, existing_hashes: set) -> Optional[Dict]:
        """Process a single image file"""
        try:
            # Extract patient ID
            patient_id = self._extract_patient_id(img_file)
            if not patient_id:
                return None

            # Generate hash
            relative_path = str(img_file.relative_to(self.base_path))
            hash_str = f"{patient_id}_{relative_path}"
            image_hash = hashlib.sha256(hash_str.encode()).hexdigest()[:32]

            # Skip if already in database
            if image_hash in existing_hashes:
                return None

            # Determine modality
            modality = self._determine_modality(img_file)

            # Create patient-specific directories
            patient_metadata_dir = self.metadata_base / patient_id / modality
            patient_png_dir = self.png_base / patient_id / modality
            patient_thumbnail_dir = self.thumbnail_base / patient_id / modality

            for dir_path in [patient_metadata_dir, patient_png_dir, patient_thumbnail_dir]:
                dir_path.mkdir(parents=True, exist_ok=True)

            # Process based on file type
            if img_file.suffix.lower() in ['.dcm', ''] and self._quick_dicom_check(img_file):
                metadata = self._process_dicom(img_file, patient_id, image_hash,
                                              patient_png_dir, patient_thumbnail_dir)
            elif img_file.suffix.lower() in ['.nii', '.gz']:
                metadata = self._process_nifti(img_file, patient_id, image_hash,
                                              patient_png_dir, patient_thumbnail_dir)
            else:
                return None

            if metadata:
                metadata['modality_category'] = modality

                # Save metadata
                metadata_file = patient_metadata_dir / f"{image_hash}.json"
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)

                metadata['metadata_path'] = str(metadata_file)

            return metadata

        except Exception as e:
            logger.error(f"Error processing {img_file}: {e}")
            return None

    def _extract_patient_id(self, file_path: Path) -> Optional[str]:
        """Extract patient ID from file path"""
        import re
        path_str = str(file_path)

        patterns = [
            r'(\d{3}_S_\d{4})',
            r'(I\d{6})',
            r'ADNI_(\d{3}_S_\d{4})',
        ]

        for pattern in patterns:
            match = re.search(pattern, path_str)
            if match:
                return match.group(1)

        # Check parent directories
        for parent in file_path.parents:
            for pattern in patterns:
                match = re.search(pattern, parent.name)
                if match:
                    return match.group(1)

        return None

    def _determine_modality(self, file_path: Path) -> str:
        """Determine modality from file path"""
        path_str = str(file_path).upper()

        if any(x in path_str for x in ['PET', 'FDG', 'AV45', 'AV1451']):
            return 'PET'
        elif any(x in path_str for x in ['MRI', 'T1', 'T2', 'FLAIR']):
            return 'MRI'
        elif 'CT' in path_str:
            return 'CT'
        else:
            return 'MRI'  # Default

    def _process_dicom(self, dcm_file: Path, patient_id: str, image_hash: str,
                      png_dir: Path, thumbnail_dir: Path) -> Optional[Dict]:
        """Process DICOM file"""
        try:
            ds = pydicom.dcmread(str(dcm_file))

            metadata = {
                'image_hash': image_hash,
                'patient_id': patient_id,
                'file_type': 'DICOM',
                'original_path': str(dcm_file),
                'modality': getattr(ds, 'Modality', 'UNKNOWN'),
                'study_date': getattr(ds, 'StudyDate', ''),
                'study_id': getattr(ds, 'StudyInstanceUID', image_hash[:16]),
                'series_id': getattr(ds, 'SeriesInstanceUID', ''),
                'series_description': getattr(ds, 'SeriesDescription', ''),
                'processed_date': datetime.now().isoformat()
            }

            # Convert to PNG if pixel data available
            if hasattr(ds, 'pixel_array'):
                try:
                    pixel_array = ds.pixel_array

                    # Normalize to 8-bit
                    if pixel_array.dtype != np.uint8:
                        pixel_array = ((pixel_array - pixel_array.min()) /
                                     (pixel_array.max() - pixel_array.min() + 1e-8) * 255).astype(np.uint8)

                    # Save PNG
                    png_path = png_dir / f"{image_hash}.png"
                    img = Image.fromarray(pixel_array)
                    img.save(png_path)

                    # Save thumbnail
                    thumbnail_path = thumbnail_dir / f"{image_hash}_thumb.png"
                    img.thumbnail((256, 256))
                    img.save(thumbnail_path)

                    metadata['png_path'] = str(png_path)
                    metadata['thumbnail_path'] = str(thumbnail_path)
                    metadata['original_resolution'] = [ds.Columns, ds.Rows]
                except Exception as e:
                    logger.warning(f"Could not extract pixel data from {dcm_file}: {e}")

            return metadata

        except Exception as e:
            logger.error(f"Failed to process DICOM {dcm_file}: {e}")
            return None

    def _process_nifti(self, nii_file: Path, patient_id: str, image_hash: str,
                      png_dir: Path, thumbnail_dir: Path) -> Optional[Dict]:
        """Process NIfTI file"""
        try:
            nii = nib.load(str(nii_file))
            data = nii.get_fdata()

            metadata = {
                'image_hash': image_hash,
                'patient_id': patient_id,
                'file_type': 'NIfTI',
                'original_path': str(nii_file),
                'modality': self._determine_modality(nii_file),
                'study_date': datetime.fromtimestamp(nii_file.stat().st_mtime).strftime('%Y%m%d'),
                'study_id': image_hash[:16],
                'data_shape': list(data.shape),
                'voxel_size': list(nii.header.get_zooms()),
                'processed_date': datetime.now().isoformat()
            }

            # Extract middle slice
            if len(data.shape) >= 3:
                try:
                    middle_slice = data[:, :, data.shape[2] // 2]

                    # Normalize to 8-bit
                    middle_slice = ((middle_slice - middle_slice.min()) /
                                  (middle_slice.max() - middle_slice.min() + 1e-8) * 255).astype(np.uint8)

                    # Save PNG
                    png_path = png_dir / f"{image_hash}.png"
                    img = Image.fromarray(middle_slice)
                    img.save(png_path)

                    # Save thumbnail
                    thumbnail_path = thumbnail_dir / f"{image_hash}_thumb.png"
                    img.thumbnail((256, 256))
                    img.save(thumbnail_path)

                    metadata['png_path'] = str(png_path)
                    metadata['thumbnail_path'] = str(thumbnail_path)
                    metadata['original_resolution'] = list(middle_slice.shape)
                except Exception as e:
                    logger.warning(f"Could not create PNG from {nii_file}: {e}")

            return metadata

        except Exception as e:
            logger.error(f"Failed to process NIfTI {nii_file}: {e}")
            return None

    def _get_existing_image_hashes(self) -> set:
        """Get existing image hashes from database"""
        query = """
        MATCH (i:ImageNode)
        WHERE i.image_hash IS NOT NULL
        RETURN collect(i.image_hash) as hashes
        """

        try:
            results = self.connector.run_query(query)
            if results and results[0].get('hashes'):
                return set(results[0]['hashes'])
        except:
            pass

        return set()

    def _insert_batch_to_neo4j(self, metadata_list: List[Dict]) -> int:
        """Insert batch to Neo4j"""
        if not metadata_list:
            return 0

        # Create studies first
        studies = {}
        for metadata in metadata_list:
            study_id = metadata.get('study_id', '')
            if study_id and study_id not in studies:
                studies[study_id] = {
                    'study_id': study_id,
                    'patient_id': metadata.get('patient_id', ''),
                    'modality': metadata.get('modality', 'UNKNOWN'),
                    'study_date': metadata.get('study_date', ''),
                    'created_at': datetime.now().isoformat()
                }

        # Insert studies
        if studies:
            study_query = """
            UNWIND $studies as study
            MERGE (s:ImagingStudy {study_id: study.study_id})
            SET s += study
            WITH s, study
            MATCH (p:Patient {ptid: study.patient_id})
            MERGE (p)-[:HAS_IMAGING_STUDY]->(s)
            """

            try:
                self.connector.run_query(study_query, {'studies': list(studies.values())})
            except Exception as e:
                logger.error(f"Failed to create studies: {e}")

        # Insert images
        images = []
        for metadata in metadata_list:
            image_data = {
                'image_hash': metadata['image_hash'],
                'image_id': metadata['image_hash'][:16],
                'study_id': metadata.get('study_id', ''),
                'patient_id': metadata.get('patient_id', ''),
                'modality': metadata.get('modality', 'UNKNOWN'),
                'file_type': metadata.get('file_type', ''),
                'original_path': metadata.get('original_path', ''),
                'png_path': metadata.get('png_path', ''),
                'thumbnail_path': metadata.get('thumbnail_path', ''),
                'study_date': metadata.get('study_date', ''),
                'created_at': datetime.now().isoformat()
            }
            images.append(image_data)

        image_query = """
        UNWIND $images as img
        CREATE (i:ImageNode)
        SET i = img
        WITH i, img
        MATCH (s:ImagingStudy {study_id: img.study_id})
        CREATE (s)-[:HAS_IMAGE]->(i)
        WITH i, img
        MATCH (p:Patient {ptid: img.patient_id})
        CREATE (p)-[:HAS_IMAGE]->(i)
        RETURN count(i) as count
        """

        try:
            result = self.connector.run_query(image_query, {'images': images})
            if result:
                return result[0].get('count', 0)
        except Exception as e:
            logger.error(f"Failed to insert images: {e}")

        return 0

    def _index_batch_to_elasticsearch(self, metadata_list: List[Dict]) -> int:
        """Index batch to Elasticsearch"""
        if not self.es_indexer:
            return 0

        es_documents = []
        for metadata in metadata_list:
            es_doc = {
                'image_hash': metadata.get('image_hash'),
                'patient_id': metadata.get('patient_id'),
                'study_id': metadata.get('study_id'),
                'modality': metadata.get('modality'),
                'study_date': metadata.get('study_date'),
                'file_type': metadata.get('file_type'),
                'png_path': metadata.get('png_path', ''),
                'thumbnail_path': metadata.get('thumbnail_path', ''),
                'indexed_date': datetime.now().isoformat()
            }
            es_documents.append(es_doc)

        try:
            success_count, _ = self.es_indexer.bulk_index_images(es_documents)
            return success_count
        except Exception as e:
            logger.error(f"Failed to index to Elasticsearch: {e}")
            return 0


def execute_image_processing_optimized(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                                       base_path: str, storage_path: str,
                                       storage_config: Dict[str, Any] = None,
                                       max_workers: int = 8) -> Dict[str, Any]:
    """Execute batch-based image processing"""
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        config = storage_config or {}

        # Use smaller batch size for large datasets
        batch_size = config.get('batch_size', 100)  # Smaller batches
        es_host = config.get('es_host', 'localhost')
        es_port = config.get('es_port', 9200)

        # Reduce workers for stability
        max_workers = min(max_workers, 4)

        logger.info(f"Starting batch processing with batch_size={batch_size}, workers={max_workers}")

        processor = OptimizedImageProcessor(
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

        return results

    except Exception as e:
        logger.error(f"Image processing failed: {e}", exc_info=True)
        return {'error': str(e), 'images_processed': 0}
    finally:
        connector.close()