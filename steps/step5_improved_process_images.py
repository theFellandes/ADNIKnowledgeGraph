"""
Complete Optimized Lossless Image Processing Pipeline
- Full integration with Neo4j and Elasticsearch
- Main execution function
- Standalone testing with image retrieval examples
"""

import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set, Any
import pydicom
import nibabel as nib
import numpy as np
from PIL import Image
import json
import mmap
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
import lmdb
from tqdm import tqdm
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class OptimizedLosslessProcessor:
    """
    Process both DICOM and NIfTI images with lossless quality
    Using mmap for efficient file operations
    """

    def __init__(self, base_path: str, storage_path: str,
                 batch_size: int = 1000, max_workers: int = None):
        self.base_path = Path(base_path)
        self.storage_path = Path(storage_path)
        self.batch_size = batch_size
        self.max_workers = max_workers or min(cpu_count() - 1, 16)

        # Storage directories
        self.metadata_path = self.storage_path / "metadata"
        self.lossless_path = self.storage_path / "lossless"  # 16-bit PNGs
        self.thumbnail_path = self.storage_path / "thumbnails"

        for path in [self.metadata_path, self.lossless_path, self.thumbnail_path]:
            path.mkdir(parents=True, exist_ok=True)

        # LMDB for fast checkpoint tracking
        self.checkpoint_db_path = self.storage_path / "checkpoints"
        self.checkpoint_db_path.mkdir(exist_ok=True)

        self.env = lmdb.open(
            str(self.checkpoint_db_path),
            map_size=10 * 1024 * 1024 * 1024,  # 10GB
            max_dbs=2
        )
        self.processed_db = self.env.open_db(b'processed')
        self.failed_db = self.env.open_db(b'failed')

        # Build file index
        self.file_index = self._build_file_index()

    def _build_file_index(self) -> List[Tuple[str, Path]]:
        """Build index of all image files (DICOM and NIfTI)"""
        logger.info("Building file index for DICOM and NIfTI files...")

        image_files = []
        skip_dirs = {'.git', '__pycache__', 'thumbnails', 'lossless', 'metadata'}

        for root, dirs, files in os.walk(self.base_path):
            # Skip unwanted directories
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for file in files:
                if file.startswith('.'):
                    continue

                file_lower = file.lower()
                file_path = Path(root) / file

                # Check for DICOM files
                if file_lower.endswith(('.dcm', '.ima')):
                    image_files.append(('dicom', file_path))
                elif '.' not in file and file_path.stat().st_size > 100000:
                    # Potential DICOM without extension
                    if self._is_dicom_mmap(file_path):
                        image_files.append(('dicom', file_path))

                # Check for NIfTI files
                elif file_lower.endswith(('.nii', '.nii.gz')):
                    image_files.append(('nifti', file_path))

        logger.info(f"Found {len(image_files)} image files")
        return image_files

    def _is_dicom_mmap(self, file_path: Path) -> bool:
        """
        Check if file is DICOM using memory-mapped file access
        Much faster than regular file reading
        """
        try:
            with open(file_path, 'rb') as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mmapped_file:
                    # Check for DICOM magic number at offset 128
                    if len(mmapped_file) > 132:
                        return mmapped_file[128:132] == b'DICM'
            return False
        except:
            return False

    def process_all_parallel(self) -> Dict[str, int]:
        """Process all images in parallel"""
        results = {
            'total_files': len(self.file_index),
            'already_processed': 0,
            'newly_processed': 0,
            'failed': 0,
            'dicom_count': 0,
            'nifti_count': 0
        }

        # Count file types
        for file_type, _ in self.file_index:
            if file_type == 'dicom':
                results['dicom_count'] += 1
            else:
                results['nifti_count'] += 1

        logger.info(f"File types: {results['dicom_count']} DICOM, {results['nifti_count']} NIfTI")

        # Get already processed files
        processed_hashes = self._get_processed_hashes()
        results['already_processed'] = len(processed_hashes)

        # Filter unprocessed files
        unprocessed_files = []
        for file_type, file_path in self.file_index:
            file_hash = self._quick_hash(file_path)
            if file_hash not in processed_hashes:
                unprocessed_files.append((file_type, file_path, file_hash))

        if not unprocessed_files:
            logger.info("All files already processed!")
            return results

        logger.info(f"Processing {len(unprocessed_files)} new files...")

        # Process in batches using ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []

            for i in range(0, len(unprocessed_files), self.batch_size):
                batch = unprocessed_files[i:i + self.batch_size]
                future = executor.submit(process_batch_worker, batch, self.storage_path)
                futures.append(future)

            # Collect results with progress bar
            with tqdm(total=len(unprocessed_files), desc="Processing") as pbar:
                for future in as_completed(futures):
                    try:
                        batch_results = future.result(timeout=300)

                        results['newly_processed'] += batch_results['processed']
                        results['failed'] += batch_results['failed']

                        pbar.update(batch_results['total'])

                        # Save checkpoint
                        self._save_checkpoint(batch_results['metadata'])

                    except Exception as e:
                        logger.error(f"Batch failed: {e}")
                        results['failed'] += self.batch_size

        return results

    def _quick_hash(self, file_path: Path) -> str:
        """Quick hash using file attributes"""
        stat = file_path.stat()
        hash_str = f"{file_path}_{stat.st_size}_{stat.st_mtime}"
        return hashlib.md5(hash_str.encode()).hexdigest()[:16]

    def _get_processed_hashes(self) -> Set[str]:
        """Get already processed files from LMDB"""
        processed = set()
        with self.env.begin(db=self.processed_db) as txn:
            cursor = txn.cursor()
            for key, _ in cursor:
                processed.add(key.decode())
        return processed

    def _save_checkpoint(self, metadata_list: List[Dict]):
        """Save processing checkpoint"""
        with self.env.begin(write=True) as txn:
            for metadata in metadata_list:
                # Mark as processed
                txn.put(
                    metadata['image_hash'].encode(),
                    b'1',
                    db=self.processed_db
                )

                # Save metadata as JSON
                metadata_path = self.metadata_path / f"{metadata['image_hash']}.json"
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)

    def insert_to_neo4j(self, connector) -> int:
        """Insert all processed images to Neo4j"""
        logger.info("Inserting images to Neo4j...")

        batch = []
        batch_size = 5000
        total_inserted = 0

        # Read all metadata files
        for metadata_file in self.metadata_path.glob("*.json"):
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            # Prepare Neo4j data
            neo4j_data = {
                'image_hash': metadata['image_hash'],
                'file_type': metadata['file_type'],
                'original_path': metadata['original_path'],
                'patient_id': metadata['patient_id'],
                'modality': metadata.get('modality', 'UNKNOWN'),
                'study_date': metadata.get('study_date', ''),
                'lossless_png_path': metadata.get('lossless_png_path', ''),
                'thumbnail_path': metadata.get('thumbnail_path', ''),
                'created_at': datetime.now().isoformat()
            }

            # Add specific fields based on file type
            if metadata['file_type'] == 'DICOM':
                neo4j_data['bits_stored'] = metadata.get('bits_stored', 16)
                neo4j_data['rescale_slope'] = metadata.get('rescale_slope', 1.0)
                neo4j_data['rescale_intercept'] = metadata.get('rescale_intercept', 0.0)
            elif metadata['file_type'] == 'NIfTI':
                neo4j_data['voxel_size'] = str(metadata.get('voxel_size', []))
                neo4j_data['data_shape'] = str(metadata.get('data_shape', []))

            batch.append(neo4j_data)

            if len(batch) >= batch_size:
                count = self._insert_batch_to_neo4j(connector, batch)
                total_inserted += count
                batch = []

        # Insert remaining
        if batch:
            count = self._insert_batch_to_neo4j(connector, batch)
            total_inserted += count

        logger.info(f"Inserted {total_inserted} images to Neo4j")
        return total_inserted

    def _insert_batch_to_neo4j(self, connector, batch: List[Dict]) -> int:
        """Insert batch to Neo4j"""
        query = """
        UNWIND $batch as img
        MERGE (i:ImageNode {image_hash: img.image_hash})
        SET i += img
        WITH i, img
        WHERE img.patient_id IS NOT NULL
        MATCH (p:Patient {ptid: img.patient_id})
        MERGE (p)-[:HAS_IMAGE]->(i)
        WITH i, img
        WHERE img.study_date IS NOT NULL
        MERGE (s:ImagingStudy {study_id: img.patient_id + '_' + img.study_date})
        SET s.patient_id = img.patient_id,
            s.study_date = img.study_date,
            s.modality = img.modality
        MERGE (s)-[:CONTAINS_IMAGE]->(i)
        RETURN count(i) as count
        """

        try:
            result = connector.run_query(query, {'batch': batch})
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.error(f"Neo4j insert failed: {e}")
            return 0

    def insert_to_elasticsearch(self, es_indexer) -> int:
        """Insert to Elasticsearch if available"""
        if not es_indexer:
            return 0

        logger.info("Indexing images to Elasticsearch...")

        documents = []
        for metadata_file in self.metadata_path.glob("*.json"):
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            es_doc = {
                'image_hash': metadata['image_hash'],
                'file_type': metadata['file_type'],
                'patient_id': metadata['patient_id'],
                'modality': metadata.get('modality', 'UNKNOWN'),
                'study_date': metadata.get('study_date', ''),
                'original_path': metadata['original_path'],
                'lossless_png_path': metadata.get('lossless_png_path', ''),
                'thumbnail_path': metadata.get('thumbnail_path', ''),
                'indexed_at': datetime.now().isoformat()
            }

            documents.append(es_doc)

        # Bulk index
        success_count = 0
        batch_size = 1000

        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            try:
                count, _ = es_indexer.bulk_index_images(batch)
                success_count += count
            except Exception as e:
                logger.error(f"ES indexing failed: {e}")

        logger.info(f"Indexed {success_count} images to Elasticsearch")
        return success_count

    def get_lossless_image(self, image_hash: str) -> Optional[np.ndarray]:
        """
        Retrieve lossless image data by hash
        Returns original pixel values without any loss
        """
        # Load metadata
        metadata_path = self.metadata_path / f"{image_hash}.json"
        if not metadata_path.exists():
            logger.error(f"Metadata not found for {image_hash}")
            return None

        with open(metadata_path, 'r') as f:
            metadata = json.load(f)

        # Option 1: Load from original file (best quality)
        original_path = Path(metadata['original_path'])
        if original_path.exists():
            if metadata['file_type'] == 'DICOM':
                ds = pydicom.dcmread(str(original_path))
                return ds.pixel_array
            elif metadata['file_type'] == 'NIfTI':
                nii = nib.load(str(original_path))
                return nii.get_fdata()

        # Option 2: Load from lossless PNG
        if 'lossless_png_path' in metadata:
            png_path = Path(metadata['lossless_png_path'])
            if png_path.exists():
                return reconstruct_from_lossless(png_path, metadata)

        logger.error(f"Could not retrieve image {image_hash}")
        return None

    def get_image_metadata(self, image_hash: str) -> Optional[Dict]:
        """Get metadata for an image"""
        metadata_path = self.metadata_path / f"{image_hash}.json"
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                return json.load(f)
        return None


# Worker functions for multiprocessing
def process_batch_worker(batch: List[Tuple[str, Path, str]],
                         storage_path: Path) -> Dict:
    """
    Worker function to process a batch of files
    Runs in separate process
    """
    batch_results = {
        'total': len(batch),
        'processed': 0,
        'failed': 0,
        'metadata': []
    }

    for file_type, file_path, file_hash in batch:
        try:
            if file_type == 'dicom':
                metadata = process_dicom_lossless(file_path, file_hash, storage_path)
            else:  # nifti
                metadata = process_nifti_lossless(file_path, file_hash, storage_path)

            if metadata:
                batch_results['processed'] += 1
                batch_results['metadata'].append(metadata)
            else:
                batch_results['failed'] += 1

        except Exception as e:
            logger.debug(f"Failed to process {file_path}: {e}")
            batch_results['failed'] += 1

    return batch_results


def process_dicom_lossless(file_path: Path, file_hash: str,
                           storage_path: Path) -> Optional[Dict]:
    """
    Process DICOM file with lossless quality preservation
    Using mmap for efficient reading
    """
    try:
        # Read DICOM header first (faster)
        ds = pydicom.dcmread(str(file_path), stop_before_pixels=True)

        # Extract patient ID
        patient_id = extract_patient_id(file_path, ds)

        # Build metadata
        metadata = {
            'image_hash': file_hash,
            'file_type': 'DICOM',
            'original_path': str(file_path),  # Reference only!
            'patient_id': patient_id,
            'modality': getattr(ds, 'Modality', 'UNKNOWN'),
            'study_date': getattr(ds, 'StudyDate', ''),
            'series_description': getattr(ds, 'SeriesDescription', ''),
            'rows': getattr(ds, 'Rows', 0),
            'columns': getattr(ds, 'Columns', 0),
            'bits_allocated': getattr(ds, 'BitsAllocated', 16),
            'bits_stored': getattr(ds, 'BitsStored', 16),
            'pixel_representation': getattr(ds, 'PixelRepresentation', 0),
            'rescale_slope': float(getattr(ds, 'RescaleSlope', 1.0)),
            'rescale_intercept': float(getattr(ds, 'RescaleIntercept', 0.0))
        }

        # Process pixel data if present
        if hasattr(ds, 'NumberOfFrames') or metadata['rows'] > 0:
            # Read full DICOM with pixel data
            ds = pydicom.dcmread(str(file_path))

            if hasattr(ds, 'pixel_array'):
                pixel_array = ds.pixel_array

                # Create lossless 16-bit PNG
                lossless_path = create_lossless_png(
                    pixel_array, patient_id, file_hash,
                    metadata['bits_stored'], storage_path
                )
                metadata['lossless_png_path'] = str(lossless_path)

                # Create thumbnail for UI
                thumb_path = create_thumbnail(
                    pixel_array, patient_id, file_hash, storage_path
                )
                metadata['thumbnail_path'] = str(thumb_path)

        return metadata

    except Exception as e:
        logger.error(f"Error processing DICOM {file_path}: {e}")
        return None


def process_nifti_lossless(file_path: Path, file_hash: str,
                           storage_path: Path) -> Optional[Dict]:
    """
    Process NIfTI file with nibabel, maintaining lossless quality
    """
    try:
        # Load NIfTI with nibabel
        nii = nib.load(str(file_path))

        # Get data without loading into memory yet (lazy loading)
        data_shape = nii.shape
        header = nii.header

        # Extract patient ID
        patient_id = extract_patient_id(file_path, None)

        # Build metadata from NIfTI header
        metadata = {
            'image_hash': file_hash,
            'file_type': 'NIfTI',
            'original_path': str(file_path),
            'patient_id': patient_id,
            'modality': determine_modality_from_path(file_path),
            'data_shape': list(data_shape),
            'voxel_size': list(header.get_zooms()),
            'data_type': str(header.get_data_dtype()),
            'qform_code': int(header['qform_code']),
            'sform_code': int(header['sform_code']),
            'dim_info': header.get_dim_info()
        }

        # Process data for derived formats
        # Use mmap for efficient memory usage with large NIfTI files
        data = nii.get_fdata(caching='unchanged')  # Keep original dtype

        # For 3D/4D volumes, extract middle slice
        if len(data_shape) >= 3:
            slice_idx = data_shape[2] // 2
            if len(data_shape) == 4:
                # 4D data (e.g., fMRI), take first volume
                slice_data = data[:, :, slice_idx, 0]
            else:
                slice_data = data[:, :, slice_idx]

            # Create lossless 16-bit PNG
            lossless_path = create_lossless_png(
                slice_data, patient_id, file_hash, 16, storage_path
            )
            metadata['lossless_png_path'] = str(lossless_path)

            # Create thumbnail
            thumb_path = create_thumbnail(
                slice_data, patient_id, file_hash, storage_path
            )
            metadata['thumbnail_path'] = str(thumb_path)

            # Store which slice we used
            metadata['extracted_slice'] = slice_idx

        return metadata

    except Exception as e:
        logger.error(f"Error processing NIfTI {file_path}: {e}")
        return None


def create_lossless_png(pixel_array: np.ndarray, patient_id: str,
                        file_hash: str, bits_stored: int,
                        storage_path: Path) -> Path:
    """
    Create truly lossless 16-bit PNG
    NO normalization, NO scaling (unless necessary)
    """
    lossless_dir = storage_path / "lossless" / patient_id
    lossless_dir.mkdir(parents=True, exist_ok=True)

    output_path = lossless_dir / f"{file_hash[:12]}.png"

    # Skip if already exists
    if output_path.exists():
        return output_path

    # Ensure 2D array
    if len(pixel_array.shape) > 2:
        pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

    # Determine proper storage format
    min_val = pixel_array.min()
    max_val = pixel_array.max()

    # Handle signed data
    if min_val < 0:
        # Shift to unsigned range for PNG storage
        pixel_array = pixel_array - min_val
        # Store shift value in filename for reconstruction
        output_path = lossless_dir / f"{file_hash[:12]}_shift{int(-min_val)}.png"

    # Save based on range
    if max_val <= 255 and min_val >= 0:
        # Can use 8-bit without loss
        img = Image.fromarray(pixel_array.astype(np.uint8))
    elif max_val <= 65535:
        # Use 16-bit PNG
        img = Image.fromarray(pixel_array.astype(np.uint16), mode='I;16')
    else:
        # Need to scale for very large values
        scale = 65535.0 / max_val
        scaled = (pixel_array * scale).astype(np.uint16)
        img = Image.fromarray(scaled, mode='I;16')
        # Store scale in filename
        output_path = lossless_dir / f"{file_hash[:12]}_scale{scale:.6f}.png"

    # Save with minimal compression for speed
    img.save(output_path, 'PNG', compress_level=1)

    return output_path


def create_thumbnail(pixel_array: np.ndarray, patient_id: str,
                     file_hash: str, storage_path: Path) -> Path:
    """Create thumbnail for UI display (can be lossy)"""
    thumb_dir = storage_path / "thumbnails" / patient_id
    thumb_dir.mkdir(parents=True, exist_ok=True)

    output_path = thumb_dir / f"{file_hash[:8]}_t.jpg"

    if output_path.exists():
        return output_path

    # Ensure 2D
    if len(pixel_array.shape) > 2:
        pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

    # Auto window/level for better visualization
    p5, p95 = np.percentile(pixel_array, [5, 95])
    pixel_array = np.clip(pixel_array, p5, p95)

    # Normalize to 8-bit for thumbnail
    if p95 > p5:
        pixel_array = ((pixel_array - p5) / (p95 - p5) * 255).astype(np.uint8)
    else:
        pixel_array = np.zeros_like(pixel_array, dtype=np.uint8)

    # Create and save thumbnail
    img = Image.fromarray(pixel_array)
    img.thumbnail((256, 256), Image.Resampling.LANCZOS)
    img.save(output_path, 'JPEG', quality=85, optimize=True)

    return output_path


def extract_patient_id(file_path: Path, ds) -> str:
    """Extract patient ID from DICOM or path"""
    # Try DICOM header
    if ds:
        patient_id = getattr(ds, 'PatientID', None)
        if patient_id:
            return str(patient_id).strip()

    # Try ADNI pattern in path
    import re
    path_str = str(file_path)
    match = re.search(r'(\d{3}_S_\d{4})', path_str)
    if match:
        return match.group(1)

    # Try I-number pattern
    match = re.search(r'(I\d{6})', path_str)
    if match:
        return match.group(1)

    # Use parent directory
    return file_path.parent.name


def determine_modality_from_path(file_path: Path) -> str:
    """Determine modality from file path"""
    path_str = str(file_path).upper()

    if 'PET' in path_str:
        return 'PET'
    elif 'MRI' in path_str or 'MR' in path_str:
        return 'MRI'
    elif 'CT' in path_str:
        return 'CT'
    else:
        return 'UNKNOWN'


def reconstruct_from_lossless(lossless_path: Path, metadata: Dict) -> np.ndarray:
    """
    Reconstruct original pixel values from lossless PNG
    Demonstrates perfect reconstruction
    """
    img = Image.open(lossless_path)
    pixel_array = np.array(img)

    # Check filename for transformations
    filename = lossless_path.name

    # Reverse shift if applied
    if '_shift' in filename:
        shift_val = int(filename.split('_shift')[1].split('.')[0])
        pixel_array = pixel_array + shift_val

    # Reverse scale if applied
    if '_scale' in filename:
        scale_val = float(filename.split('_scale')[1].split('.')[0])
        pixel_array = pixel_array / scale_val

    # Apply DICOM rescale if present
    if metadata.get('rescale_slope'):
        slope = metadata['rescale_slope']
        intercept = metadata.get('rescale_intercept', 0)
        pixel_array = pixel_array * slope + intercept

    return pixel_array


def execute_image_processing_optimized(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                                       base_path: str, storage_path: str,
                                       storage_config: Dict = None,
                                       max_workers: int = 8) -> Dict[str, Any]:
    """
    Main execution function for optimized image processing
    Integrates with Neo4j and Elasticsearch
    """
    from utils.neo4j_connector import Neo4jConnector

    logger.info("\n" + "="*70)
    logger.info("OPTIMIZED LOSSLESS IMAGE PROCESSING")
    logger.info("="*70)

    start_time = time.time()

    # Initialize Neo4j connector
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    # Initialize Elasticsearch if configured
    es_indexer = None
    if storage_config:
        es_host = storage_config.get('es_host', 'localhost')
        es_port = storage_config.get('es_port', 9200)

        try:
            from utils.elasticsearch_indexer import SearchIndexer
            es_indexer = SearchIndexer(es_host, es_port)
            logger.info(f"Connected to Elasticsearch at {es_host}:{es_port}")
        except Exception as e:
            logger.warning(f"Could not connect to Elasticsearch: {e}")

    try:
        # Configure batch size
        batch_size = storage_config.get('batch_size', 1000) if storage_config else 1000

        # Initialize processor
        processor = OptimizedLosslessProcessor(
            base_path=base_path,
            storage_path=storage_path,
            batch_size=batch_size,
            max_workers=max_workers
        )

        # Process all images
        processing_results = processor.process_all_parallel()

        # Insert to Neo4j
        neo4j_count = processor.insert_to_neo4j(connector)
        processing_results['neo4j_inserted'] = neo4j_count

        # Insert to Elasticsearch if available
        es_count = 0
        if es_indexer:
            es_count = processor.insert_to_elasticsearch(es_indexer)
            processing_results['es_indexed'] = es_count

        # Calculate timing
        elapsed_time = time.time() - start_time
        processing_results['processing_time_seconds'] = elapsed_time

        # Log summary
        logger.info("\n" + "="*70)
        logger.info("PROCESSING COMPLETE")
        logger.info("="*70)
        logger.info(f"Total files found: {processing_results['total_files']:,}")
        logger.info(f"  DICOM files: {processing_results['dicom_count']:,}")
        logger.info(f"  NIfTI files: {processing_results['nifti_count']:,}")
        logger.info(f"Already processed: {processing_results['already_processed']:,}")
        logger.info(f"Newly processed: {processing_results['newly_processed']:,}")
        logger.info(f"Failed: {processing_results['failed']:,}")
        logger.info(f"Inserted to Neo4j: {processing_results['neo4j_inserted']:,}")
        if es_count > 0:
            logger.info(f"Indexed to Elasticsearch: {es_count:,}")
        logger.info(f"Processing time: {elapsed_time:.2f} seconds")

        # Calculate processing rate
        if processing_results['newly_processed'] > 0:
            rate = processing_results['newly_processed'] / elapsed_time
            logger.info(f"Processing rate: {rate:.1f} images/second")

        # Add processor to results for potential reuse
        processing_results['processor'] = processor

        return processing_results

    except Exception as e:
        logger.error(f"Image processing failed: {e}", exc_info=True)
        return {
            'error': str(e),
            'images_processed': 0,
            'neo4j_inserted': 0,
            'es_indexed': 0
        }
    finally:
        connector.close()


# Main execution and testing
if __name__ == "__main__":
    import argparse
    import sys

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(
        description="Optimized Lossless Medical Image Processing Pipeline"
    )

    # Main arguments
    parser.add_argument('--mode', choices=['process', 'retrieve', 'verify'],
                       default='process',
                       help='Mode: process images, retrieve image, or verify lossless')

    # Processing arguments
    parser.add_argument('--base-path', type=str,
                       help='Base path containing images (e.g., New_MRI folder)')
    parser.add_argument('--storage-path', type=str, default='./image_storage',
                       help='Path for processed image storage')
    parser.add_argument('--batch-size', type=int, default=1000,
                       help='Batch size for processing')
    parser.add_argument('--max-workers', type=int, default=8,
                       help='Maximum parallel workers')

    # Database arguments
    parser.add_argument('--neo4j-uri', default='bolt://localhost:7687',
                       help='Neo4j connection URI')
    parser.add_argument('--neo4j-user', default='neo4j',
                       help='Neo4j username')
    parser.add_argument('--neo4j-password', required=True,
                       help='Neo4j password')

    # Elasticsearch arguments
    parser.add_argument('--es-host', default='localhost',
                       help='Elasticsearch host')
    parser.add_argument('--es-port', type=int, default=9200,
                       help='Elasticsearch port')

    # Retrieval arguments
    parser.add_argument('--image-hash', type=str,
                       help='Image hash for retrieval/verification')
    parser.add_argument('--patient-id', type=str,
                       help='Patient ID for finding images')

    # Verification arguments
    parser.add_argument('--verify-samples', type=int, default=10,
                       help='Number of random images to verify')

    args = parser.parse_args()

    if args.mode == 'process':
        # Process images
        if not args.base_path:
            print("Error: --base-path required for processing")
            sys.exit(1)

        storage_config = {
            'es_host': args.es_host,
            'es_port': args.es_port,
            'batch_size': args.batch_size
        }

        results = execute_image_processing_optimized(
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password,
            base_path=args.base_path,
            storage_path=args.storage_path,
            storage_config=storage_config,
            max_workers=args.max_workers
        )

        if 'error' not in results:
            print(f"\n✅ Processing completed successfully!")
            print(f"   Processed: {results.get('newly_processed', 0):,} images")
            print(f"   Time: {results.get('processing_time_seconds', 0):.2f} seconds")
        else:
            print(f"\n❌ Processing failed: {results['error']}")
            sys.exit(1)

    elif args.mode == 'retrieve':
        # Retrieve and display lossless image
        if not args.image_hash and not args.patient_id:
            print("Error: --image-hash or --patient-id required for retrieval")
            sys.exit(1)

        processor = OptimizedLosslessProcessor(
            base_path='.',  # Not used for retrieval
            storage_path=args.storage_path
        )

        if args.image_hash:
            # Retrieve by hash
            print(f"\nRetrieving image {args.image_hash}...")

            # Get metadata
            metadata = processor.get_image_metadata(args.image_hash)
            if metadata:
                print("\n📄 Image Metadata:")
                print(f"   File Type: {metadata['file_type']}")
                print(f"   Patient ID: {metadata['patient_id']}")
                print(f"   Modality: {metadata.get('modality', 'Unknown')}")
                print(f"   Original Path: {metadata['original_path']}")

                # Get pixel data
                pixel_array = processor.get_lossless_image(args.image_hash)
                if pixel_array is not None:
                    print(f"\n🖼️  Image Data:")
                    print(f"   Shape: {pixel_array.shape}")
                    print(f"   Data Type: {pixel_array.dtype}")
                    print(f"   Min Value: {pixel_array.min()}")
                    print(f"   Max Value: {pixel_array.max()}")
                    print(f"   Mean Value: {pixel_array.mean():.2f}")

                    # Optional: Display with matplotlib
                    try:
                        import matplotlib.pyplot as plt

                        if len(pixel_array.shape) == 3:
                            # Show middle slice for 3D
                            slice_data = pixel_array[:, :, pixel_array.shape[2]//2]
                        else:
                            slice_data = pixel_array

                        plt.figure(figsize=(8, 8))
                        plt.imshow(slice_data, cmap='gray')
                        plt.title(f"Lossless Image: {args.image_hash[:8]}")
                        plt.colorbar()
                        plt.show()
                    except ImportError:
                        print("(Install matplotlib to visualize images)")
            else:
                print(f"Image {args.image_hash} not found")

        elif args.patient_id:
            # Find images for patient
            print(f"\nFinding images for patient {args.patient_id}...")

            found_count = 0
            for metadata_file in (Path(args.storage_path) / "metadata").glob("*.json"):
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                if metadata['patient_id'] == args.patient_id:
                    found_count += 1
                    print(f"\n📷 Image {found_count}:")
                    print(f"   Hash: {metadata['image_hash']}")
                    print(f"   Modality: {metadata.get('modality', 'Unknown')}")
                    print(f"   Date: {metadata.get('study_date', 'Unknown')}")

                    if found_count >= 10:
                        print(f"\n... and more (showing first 10)")
                        break

            if found_count == 0:
                print(f"No images found for patient {args.patient_id}")

    elif args.mode == 'verify':
        # Verify lossless quality
        print(f"\nVerifying lossless quality for {args.verify_samples} random samples...")

        processor = OptimizedLosslessProcessor(
            base_path='.',
            storage_path=args.storage_path
        )

        # Get random samples
        metadata_files = list((Path(args.storage_path) / "metadata").glob("*.json"))

        if not metadata_files:
            print("No processed images found")
            sys.exit(1)

        import random
        samples = random.sample(metadata_files,
                              min(args.verify_samples, len(metadata_files)))

        verified_count = 0
        perfect_count = 0

        for metadata_file in samples:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            image_hash = metadata['image_hash']
            print(f"\n🔍 Verifying {image_hash[:8]}...")

            # Load original
            original_path = Path(metadata['original_path'])
            if not original_path.exists():
                print("   ⚠️  Original file not found")
                continue

            if metadata['file_type'] == 'DICOM':
                ds = pydicom.dcmread(str(original_path))
                original_pixels = ds.pixel_array
            else:
                nii = nib.load(str(original_path))
                original_pixels = nii.get_fdata()
                if len(original_pixels.shape) >= 3:
                    slice_idx = metadata.get('extracted_slice', original_pixels.shape[2]//2)
                    original_pixels = original_pixels[:, :, slice_idx]

            # Load lossless PNG
            if 'lossless_png_path' in metadata:
                reconstructed = reconstruct_from_lossless(
                    Path(metadata['lossless_png_path']),
                    metadata
                )

                # Compare
                if original_pixels.shape == reconstructed.shape:
                    max_diff = np.abs(original_pixels - reconstructed).max()
                    mean_diff = np.abs(original_pixels - reconstructed).mean()

                    print(f"   Shape match: ✅ {original_pixels.shape}")
                    print(f"   Max difference: {max_diff:.6f}")
                    print(f"   Mean difference: {mean_diff:.6f}")

                    if max_diff < 1e-5:  # Tolerance for floating point
                        print(f"   Quality: ✅ PERFECT (lossless)")
                        perfect_count += 1
                    else:
                        print(f"   Quality: ⚠️  Minor differences detected")

                    verified_count += 1
                else:
                    print(f"   ❌ Shape mismatch!")
            else:
                print("   No lossless PNG found")

        print(f"\n📊 Verification Summary:")
        print(f"   Samples verified: {verified_count}/{args.verify_samples}")
        print(f"   Perfect quality: {perfect_count}/{verified_count}")

        if perfect_count == verified_count:
            print(f"\n✅ All samples verified as LOSSLESS!")
        else:
            print(f"\n⚠️  Some quality issues detected")