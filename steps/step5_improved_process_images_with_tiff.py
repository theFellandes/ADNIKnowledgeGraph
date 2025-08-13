"""
Step 5: Enhanced Image Processing with Integrated ZIP Support
Seamlessly handles both directory and ZIP processing based on config
"""

import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set, Any, Union
import pydicom
import nibabel as nib
import numpy as np
from PIL import Image
import tifffile
import json
import mmap
import os
import zipfile
import io
import re
import yaml
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from multiprocessing import cpu_count
import lmdb
from tqdm import tqdm
import time
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ProcessingMode(Enum):
    """Processing modes for image data"""
    EXTRACTED_DIR = "extracted"
    ZIP_DIRECT = "zip_direct"
    MIXED = "mixed"
    AUTO = "auto"  # Auto-detect based on what's available


@dataclass
class ZipProcessingConfig:
    """Configuration for ZIP processing"""
    mode: ProcessingMode
    zip_directory: Optional[Path] = None
    extracted_directory: Optional[Path] = None
    zip_numbers: Optional[List[int]] = None
    zip_patterns: Optional[List[str]] = None
    max_zips: Optional[int] = None
    extract_for_serving: bool = False
    serving_cache_dir: Optional[Path] = None

    @classmethod
    def from_storage_config(cls, storage_config: Dict[str, Any], base_path: str) -> 'ZipProcessingConfig':
        """Create from storage config section"""
        zip_config = storage_config.get('zip_processing', {})

        # Determine mode
        mode_str = zip_config.get('mode', 'auto')
        mode = ProcessingMode(mode_str)

        # Parse ZIP numbers
        zip_numbers = None
        if 'zip_numbers' in zip_config:
            numbers = zip_config['zip_numbers']
            if isinstance(numbers, list):
                zip_numbers = numbers
            elif isinstance(numbers, str):
                zip_numbers = cls._parse_number_range(numbers)

        return cls(
            mode=mode,
            zip_directory=Path(zip_config.get('zip_directory', base_path)) if zip_config.get('zip_directory') else None,
            extracted_directory=Path(zip_config.get('extracted_directory', base_path)) if zip_config.get('extracted_directory') else None,
            zip_numbers=zip_numbers,
            zip_patterns=zip_config.get('zip_patterns', ['*.zip']),
            max_zips=zip_config.get('max_zips'),
            extract_for_serving=zip_config.get('extract_for_serving', False),
            serving_cache_dir=Path(zip_config.get('serving_cache_dir')) if zip_config.get('serving_cache_dir') else None
        )

    @staticmethod
    def _parse_number_range(range_str: str) -> List[int]:
        """Parse number range string"""
        numbers = []
        parts = range_str.split(',')

        for part in parts:
            if '-' in part:
                start, end = map(int, part.split('-'))
                numbers.extend(range(start, end + 1))
            else:
                numbers.append(int(part.strip()))

        return sorted(set(numbers))


class EnhancedLosslessProcessor:
    """
    Enhanced processor that handles both directories and ZIP files
    Integrates SelectiveZipProcessor functionality
    """

    def __init__(self, base_path: str, storage_path: str,
                 batch_size: int = 1000, max_workers: int = None,
                 storage_config: Dict = None):
        """
        Initialize processor with optional ZIP support

        Args:
            base_path: Base path for data
            storage_path: Output storage path
            batch_size: Batch size for processing
            max_workers: Number of workers
            storage_config: Storage configuration including ZIP settings
        """
        self.base_path = Path(base_path)
        self.storage_path = Path(storage_path)
        self.batch_size = batch_size
        self.max_workers = max_workers or min(cpu_count() - 1, 16)
        self.storage_config = storage_config or {}

        # Parse ZIP configuration if present
        self.zip_config = None
        if storage_config and 'zip_processing' in storage_config:
            self.zip_config = ZipProcessingConfig.from_storage_config(storage_config, str(base_path))

        # Storage directories
        self.metadata_path = self.storage_path / "metadata"
        self.lossless_path = self.storage_path / "lossless"
        self.lossless_png_path = self.lossless_path / "lossless_png"
        self.lossless_tiff_path = self.lossless_path / "lossless_tiff"
        self.thumbnail_path = self.storage_path / "thumbnails"

        # Create directories
        for path in [self.metadata_path, self.lossless_png_path,
                     self.lossless_tiff_path, self.thumbnail_path]:
            path.mkdir(parents=True, exist_ok=True)

        # Setup serving cache if needed
        if self.zip_config and self.zip_config.extract_for_serving and self.zip_config.serving_cache_dir:
            self.zip_config.serving_cache_dir.mkdir(parents=True, exist_ok=True)

        # LMDB for checkpoint tracking
        self.checkpoint_db_path = self.storage_path / "checkpoints"
        self.checkpoint_db_path.mkdir(exist_ok=True)

        self.env = lmdb.open(
            str(self.checkpoint_db_path),
            map_size=10 * 1024 * 1024 * 1024,  # 10GB
            max_dbs=3
        )
        self.processed_db = self.env.open_db(b'processed')
        self.failed_db = self.env.open_db(b'failed')
        self.zip_tracking_db = self.env.open_db(b'zip_tracking')

        # Determine processing mode
        self.processing_mode = self._determine_processing_mode()

        # Build appropriate file index
        if self.processing_mode in [ProcessingMode.ZIP_DIRECT, ProcessingMode.MIXED]:
            self.available_zips = self._discover_zips()
        else:
            self.available_zips = {}

        if self.processing_mode in [ProcessingMode.EXTRACTED_DIR, ProcessingMode.MIXED]:
            self.file_index = self._build_file_index()
        else:
            self.file_index = []

    def _determine_processing_mode(self) -> ProcessingMode:
        """Determine the actual processing mode based on config and available data"""
        if not self.zip_config:
            return ProcessingMode.EXTRACTED_DIR

        mode = self.zip_config.mode

        if mode == ProcessingMode.AUTO:
            # Auto-detect based on what's available
            has_extracted = self.base_path.exists() and any(self.base_path.iterdir())
            has_zips = False

            if self.zip_config.zip_directory and self.zip_config.zip_directory.exists():
                has_zips = any(self.zip_config.zip_directory.glob('*.zip'))

            if has_zips and not has_extracted:
                mode = ProcessingMode.ZIP_DIRECT
            elif has_extracted and not has_zips:
                mode = ProcessingMode.EXTRACTED_DIR
            elif has_zips and has_extracted:
                mode = ProcessingMode.MIXED
            else:
                mode = ProcessingMode.EXTRACTED_DIR

            logger.info(f"Auto-detected processing mode: {mode.value}")

        return mode

    def _discover_zips(self) -> Dict[int, Path]:
        """Discover available ZIP files"""
        available = {}

        if self.zip_config and self.zip_config.zip_directory and self.zip_config.zip_directory.exists():
            for pattern in self.zip_config.zip_patterns or ['*.zip']:
                for zip_path in self.zip_config.zip_directory.glob(pattern):
                    # Extract number from filename
                    match = re.search(r'_(\d+)\.zip', zip_path.name)
                    if match:
                        num = int(match.group(1))
                        available[num] = zip_path
                    else:
                        available[len(available) + 1] = zip_path

        if available:
            logger.info(f"Discovered {len(available)} ZIP files")

        return available

    def _build_file_index(self) -> List[Tuple[str, Path]]:
        """Build index of all image files in directories"""
        logger.info("Building file index for directories...")

        image_files = []
        skip_dirs = {'.git', '__pycache__', 'thumbnails', 'lossless', 'metadata'}

        # Use extracted directory if specified, otherwise base_path
        search_path = self.base_path
        if self.zip_config and self.zip_config.extracted_directory and self.zip_config.extracted_directory.exists():
            search_path = self.zip_config.extracted_directory

        for root, dirs, files in os.walk(search_path):
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
                    if self._is_dicom_mmap(file_path):
                        image_files.append(('dicom', file_path))

                # Check for NIfTI files
                elif file_lower.endswith(('.nii', '.nii.gz')):
                    image_files.append(('nifti', file_path))

        logger.info(f"Found {len(image_files)} image files in directories")
        return image_files

    def _is_dicom_mmap(self, file_path: Path) -> bool:
        """Check if file is DICOM using memory-mapped file access"""
        try:
            with open(file_path, 'rb') as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mmapped_file:
                    if len(mmapped_file) > 132:
                        return mmapped_file[128:132] == b'DICM'
            return False
        except:
            return False

    def process_all_parallel(self) -> Dict[str, int]:
        """
        Process all images based on the determined mode
        Handles both directory and ZIP processing seamlessly
        """
        results = {
            'total_files': 0,
            'already_processed': 0,
            'newly_processed': 0,
            'failed': 0,
            'dicom_count': 0,
            'nifti_count': 0,
            'mode': self.processing_mode.value,
            'zips_processed': 0,
            'dirs_processed': 0
        }

        logger.info(f"Processing mode: {self.processing_mode.value}")

        # Get already processed files
        processed_hashes = self._get_processed_hashes()
        results['already_processed'] = len(processed_hashes)

        # Process based on mode
        if self.processing_mode == ProcessingMode.EXTRACTED_DIR:
            # Traditional directory processing
            results = self._process_directories(results, processed_hashes)

        elif self.processing_mode == ProcessingMode.ZIP_DIRECT:
            # ZIP-only processing
            results = self._process_zips(results, processed_hashes)

        elif self.processing_mode == ProcessingMode.MIXED:
            # Process both directories and ZIPs
            logger.info("Mixed mode: processing directories first, then ZIPs")
            results = self._process_directories(results, processed_hashes)
            results = self._process_zips(results, processed_hashes)

        return results

    def _process_directories(self, results: Dict, processed_hashes: Set[str]) -> Dict:
        """Process files from directories"""
        if not self.file_index:
            logger.info("No files found in directories")
            return results

        logger.info(f"Processing {len(self.file_index)} files from directories...")
        results['dirs_processed'] = 1

        # Filter unprocessed files
        unprocessed_files = []
        for file_type, file_path in self.file_index:
            file_hash = self._quick_hash(file_path)
            if file_hash not in processed_hashes:
                unprocessed_files.append((file_type, file_path, file_hash))

            # Count file types
            if file_type == 'dicom':
                results['dicom_count'] += 1
            else:
                results['nifti_count'] += 1

        results['total_files'] += len(self.file_index)

        if not unprocessed_files:
            logger.info("All directory files already processed")
            return results

        # Process in batches
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []

            for i in range(0, len(unprocessed_files), self.batch_size):
                batch = unprocessed_files[i:i + self.batch_size]
                future = executor.submit(process_batch_worker_enhanced, batch, self.storage_path)
                futures.append(future)

            with tqdm(total=len(unprocessed_files), desc="Processing directories") as pbar:
                for future in as_completed(futures):
                    try:
                        batch_results = future.result(timeout=300)
                        results['newly_processed'] += batch_results['processed']
                        results['failed'] += batch_results['failed']
                        pbar.update(batch_results['total'])
                        self._save_checkpoint(batch_results['metadata'])
                    except Exception as e:
                        logger.error(f"Batch failed: {e}")
                        results['failed'] += self.batch_size

        return results

    def _process_zips(self, results: Dict, processed_hashes: Set[str]) -> Dict:
        """Process files from ZIP archives"""
        if not self.available_zips:
            logger.info("No ZIP files to process")
            return results

        # Get ZIPs to process based on config
        zips_to_process = self._get_zips_to_process()

        if not zips_to_process:
            logger.info("No ZIP files selected for processing")
            return results

        logger.info(f"Processing {len(zips_to_process)} ZIP files...")
        results['zips_processed'] = len(zips_to_process)

        for zip_path in zips_to_process:
            logger.info(f"Processing ZIP: {zip_path.name}")

            # Check if already processed
            if self._is_zip_processed(zip_path):
                logger.info(f"ZIP already processed: {zip_path.name}")
                continue

            # Process this ZIP
            zip_results = self._process_single_zip(zip_path, processed_hashes)

            # Aggregate results
            results['total_files'] += zip_results['total_files']
            results['newly_processed'] += zip_results['processed']
            results['failed'] += zip_results['failed']
            results['dicom_count'] += zip_results['dicom_files']
            results['nifti_count'] += zip_results['nifti_files']

            # Mark ZIP as processed
            self._mark_zip_processed(zip_path)

            # Update processed hashes for next ZIP
            processed_hashes.update(self._get_processed_hashes())

        return results

    def _get_zips_to_process(self) -> List[Path]:
        """Get list of ZIP files to process based on config"""
        if not self.available_zips or not self.zip_config:
            return []

        # Filter by specified numbers
        if self.zip_config.zip_numbers:
            selected = [
                self.available_zips[num]
                for num in self.zip_config.zip_numbers
                if num in self.available_zips
            ]

            missing = [
                num for num in self.zip_config.zip_numbers
                if num not in self.available_zips
            ]
            if missing:
                logger.warning(f"Requested ZIP numbers not found: {missing}")

            return selected

        # Limit by max_zips
        elif self.zip_config.max_zips:
            sorted_nums = sorted(self.available_zips.keys())[:self.zip_config.max_zips]
            return [self.available_zips[num] for num in sorted_nums]

        # Return all
        return list(self.available_zips.values())

    def _process_single_zip(self, zip_path: Path, processed_hashes: Set[str]) -> Dict:
        """Process a single ZIP file"""
        results = {
            'total_files': 0,
            'processed': 0,
            'failed': 0,
            'dicom_files': 0,
            'nifti_files': 0
        }

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Discover medical images
                image_files = self._discover_medical_images_in_zip(zf)
                results['total_files'] = len(image_files)

                logger.info(f"Found {len(image_files)} medical images in {zip_path.name}")

                # Process images with ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = []

                    with tqdm(total=len(image_files), desc=f"Processing {zip_path.name}") as pbar:
                        for file_type, file_path in image_files:
                            if file_type == 'dicom':
                                results['dicom_files'] += 1
                            else:
                                results['nifti_files'] += 1

                            file_hash = self._generate_file_hash_zip(zf, file_path)

                            if file_hash in processed_hashes:
                                pbar.update(1)
                                continue

                            future = executor.submit(
                                self._process_image_from_zip,
                                zf, file_path, file_type, file_hash, zip_path
                            )
                            futures.append((future, file_hash, file_path))

                        for future, file_hash, file_path in futures:
                            try:
                                metadata = future.result(timeout=60)

                                if metadata:
                                    results['processed'] += 1
                                    self._save_metadata(metadata)
                                    self._mark_processed(file_hash)

                                    # Extract for serving if configured
                                    if self.zip_config and self.zip_config.extract_for_serving:
                                        serving_path = self._extract_for_serving(zf, file_path, metadata)
                                        if serving_path:
                                            metadata['serving_path'] = str(serving_path)
                                            self._save_metadata(metadata)
                                else:
                                    results['failed'] += 1

                            except Exception as e:
                                logger.error(f"Failed to process {file_path}: {e}")
                                results['failed'] += 1

                            pbar.update(1)

        except Exception as e:
            logger.error(f"Failed to process ZIP {zip_path}: {e}")

        return results

    def _discover_medical_images_in_zip(self, zf: zipfile.ZipFile) -> List[Tuple[str, str]]:
        """Discover medical image files in ZIP"""
        image_files = []

        for file_path in zf.namelist():
            if file_path.endswith('/') or '__MACOSX' in file_path or '.DS_Store' in file_path:
                continue

            file_lower = file_path.lower()

            if file_lower.endswith(('.dcm', '.ima')):
                image_files.append(('dicom', file_path))
            elif file_lower.endswith(('.nii', '.nii.gz')):
                image_files.append(('nifti', file_path))
            elif '.' not in os.path.basename(file_path):
                try:
                    with zf.open(file_path) as f:
                        header = f.read(132)
                        if len(header) >= 132 and header[128:132] == b'DICM':
                            image_files.append(('dicom', file_path))
                except:
                    pass

        return image_files

    def _process_image_from_zip(self, zf: zipfile.ZipFile, file_path: str,
                                file_type: str, file_hash: str, zip_path: Path) -> Optional[Dict]:
        """Process a single image from ZIP"""
        try:
            with zf.open(file_path) as f:
                file_data = f.read()

            patient_id = extract_patient_id_from_path(file_path)

            if file_type == 'dicom':
                return process_dicom_from_memory(
                    file_data, file_path, file_hash, patient_id,
                    zip_path, self.storage_path
                )
            elif file_type == 'nifti':
                return process_nifti_from_memory(
                    file_data, file_path, file_hash, patient_id,
                    zip_path, self.storage_path
                )
        except Exception as e:
            logger.error(f"Failed to process {file_path}: {e}")
            return None

    def _extract_for_serving(self, zf: zipfile.ZipFile, file_path: str,
                            metadata: Dict) -> Optional[Path]:
        """Extract file for DICOM serving"""
        if not self.zip_config or not self.zip_config.serving_cache_dir:
            return None

        try:
            patient_id = metadata.get('patient_id', 'UNKNOWN')
            patient_dir = self.zip_config.serving_cache_dir / patient_id
            patient_dir.mkdir(parents=True, exist_ok=True)

            file_name = f"{metadata['image_hash'][:8]}_{os.path.basename(file_path)}"
            output_path = patient_dir / file_name

            with zf.open(file_path) as src:
                with open(output_path, 'wb') as dst:
                    dst.write(src.read())

            return output_path
        except Exception as e:
            logger.error(f"Failed to extract for serving: {e}")
            return None

    def _quick_hash(self, file_path: Path) -> str:
        """Quick hash using file attributes"""
        stat = file_path.stat()
        hash_str = f"{file_path}_{stat.st_size}_{stat.st_mtime}"
        return hashlib.md5(hash_str.encode()).hexdigest()[:16]

    def _generate_file_hash_zip(self, zf: zipfile.ZipFile, file_path: str) -> str:
        """Generate hash for file in ZIP"""
        info = zf.getinfo(file_path)
        hash_str = f"{file_path}_{info.file_size}_{info.CRC}"
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
                txn.put(
                    metadata['image_hash'].encode(),
                    b'1',
                    db=self.processed_db
                )
                self._save_metadata(metadata)

    def _save_metadata(self, metadata: Dict):
        """Save metadata to JSON file"""
        metadata_path = self.metadata_path / f"{metadata['image_hash']}.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

    def _mark_processed(self, file_hash: str):
        """Mark file as processed"""
        with self.env.begin(write=True) as txn:
            txn.put(file_hash.encode(), b'1', db=self.processed_db)

    def _is_zip_processed(self, zip_path: Path) -> bool:
        """Check if ZIP has been processed"""
        with self.env.begin(db=self.zip_tracking_db) as txn:
            return txn.get(str(zip_path).encode()) is not None

    def _mark_zip_processed(self, zip_path: Path):
        """Mark ZIP as processed"""
        with self.env.begin(write=True) as txn:
            txn.put(
                str(zip_path).encode(),
                datetime.now().isoformat().encode(),
                db=self.zip_tracking_db
            )

    def insert_to_neo4j(self, connector) -> int:
        """Insert all processed images to Neo4j"""
        logger.info("Inserting images to Neo4j...")

        batch = []
        batch_size = 5000
        total_inserted = 0

        for metadata_file in self.metadata_path.glob("*.json"):
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            neo4j_data = {
                'image_hash': metadata['image_hash'],
                'file_type': metadata['file_type'],
                'original_path': metadata.get('original_path', ''),
                'source_archive': metadata.get('source_archive', ''),
                'patient_id': metadata['patient_id'],
                'modality': metadata.get('modality', 'UNKNOWN'),
                'study_date': metadata.get('study_date', ''),
                'lossless_png_path': metadata.get('lossless_png_path', ''),
                'lossless_tiff_path': metadata.get('lossless_tiff_path', ''),
                'thumbnail_path': metadata.get('thumbnail_path', ''),
                'serving_path': metadata.get('serving_path', ''),
                'created_at': datetime.now().isoformat()
            }

            batch.append(neo4j_data)

            if len(batch) >= batch_size:
                count = self._insert_batch_to_neo4j(connector, batch)
                total_inserted += count
                batch = []

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
        MERGE (p:Patient {ptid: img.patient_id})
        MERGE (p)-[:HAS_IMAGE]->(i)
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
                'original_path': metadata.get('original_path', ''),
                'source_archive': metadata.get('source_archive', ''),
                'lossless_png_path': metadata.get('lossless_png_path', ''),
                'lossless_tiff_path': metadata.get('lossless_tiff_path', ''),
                'thumbnail_path': metadata.get('thumbnail_path', ''),
                'indexed_at': datetime.now().isoformat()
            }

            documents.append(es_doc)

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


# Worker functions for parallel processing
def process_batch_worker_enhanced(batch: List[Tuple[str, Path, str]],
                                  storage_path: Path) -> Dict:
    """Worker function to process a batch of files"""
    batch_results = {
        'total': len(batch),
        'processed': 0,
        'failed': 0,
        'metadata': []
    }

    for file_type, file_path, file_hash in batch:
        try:
            if file_type == 'dicom':
                metadata = process_dicom_lossless_enhanced(file_path, file_hash, storage_path)
            else:
                metadata = process_nifti_lossless_enhanced(file_path, file_hash, storage_path)

            if metadata:
                batch_results['processed'] += 1
                batch_results['metadata'].append(metadata)
            else:
                batch_results['failed'] += 1

        except Exception as e:
            logger.debug(f"Failed to process {file_path}: {e}")
            batch_results['failed'] += 1

    return batch_results


def process_dicom_lossless_enhanced(file_path: Path, file_hash: str,
                                    storage_path: Path) -> Optional[Dict]:
    """Process DICOM file with proper window/level handling"""
    try:
        ds = pydicom.dcmread(str(file_path), stop_before_pixels=True)
        patient_id = extract_patient_id(file_path, ds)

        # Extract window/level values for proper conversion
        window_center = 0
        window_width = 0
        if hasattr(ds, 'WindowCenter'):
            wc = ds.WindowCenter
            window_center = float(wc[0] if isinstance(wc, (list, pydicom.multival.MultiValue)) else wc)
        if hasattr(ds, 'WindowWidth'):
            ww = ds.WindowWidth
            window_width = float(ww[0] if isinstance(ww, (list, pydicom.multival.MultiValue)) else ww)

        metadata = {
            'image_hash': file_hash,
            'file_type': 'DICOM',
            'original_path': str(file_path),
            'patient_id': patient_id,
            'modality': getattr(ds, 'Modality', 'UNKNOWN'),
            'study_date': getattr(ds, 'StudyDate', ''),
            'series_description': getattr(ds, 'SeriesDescription', ''),
            'rows': getattr(ds, 'Rows', 0),
            'columns': getattr(ds, 'Columns', 0),
            'bits_stored': getattr(ds, 'BitsStored', 16),
            'rescale_slope': float(getattr(ds, 'RescaleSlope', 1.0)),
            'rescale_intercept': float(getattr(ds, 'RescaleIntercept', 0.0)),
            'window_center': window_center,
            'window_width': window_width,
            'photometric_interpretation': getattr(ds, 'PhotometricInterpretation', 'MONOCHROME2')
        }

        if hasattr(ds, 'NumberOfFrames') or metadata['rows'] > 0:
            ds = pydicom.dcmread(str(file_path))

            if hasattr(ds, 'pixel_array'):
                pixel_array = ds.pixel_array

                # Handle photometric interpretation
                if metadata['photometric_interpretation'] == 'MONOCHROME1':
                    pixel_array = np.max(pixel_array) - pixel_array

                png_path = create_lossless_png_enhanced(
                    pixel_array, patient_id, file_hash,
                    metadata, storage_path
                )
                metadata['lossless_png_path'] = str(png_path)

                tiff_path = create_lossless_tiff(
                    pixel_array, patient_id, file_hash, metadata, storage_path
                )
                metadata['lossless_tiff_path'] = str(tiff_path)

                thumb_path = create_thumbnail(
                    pixel_array, patient_id, file_hash, metadata, storage_path
                )
                metadata['thumbnail_path'] = str(thumb_path)

        return metadata

    except Exception as e:
        logger.error(f"Error processing DICOM {file_path}: {e}")
        return None


def process_nifti_lossless_enhanced(file_path: Path, file_hash: str,
                                    storage_path: Path) -> Optional[Dict]:
    """Process NIfTI file with lossless quality preservation"""
    try:
        nii = nib.load(str(file_path))
        data_shape = nii.shape
        header = nii.header
        patient_id = extract_patient_id(file_path, None)

        metadata = {
            'image_hash': file_hash,
            'file_type': 'NIfTI',
            'original_path': str(file_path),
            'patient_id': patient_id,
            'modality': determine_modality_from_path(file_path),
            'data_shape': list(data_shape),
            'voxel_size': list(header.get_zooms()),
            'data_type': str(header.get_data_dtype()),
            'window_center': 0,  # Will be auto-calculated
            'window_width': 0,
            'rescale_slope': 1.0,
            'rescale_intercept': 0.0
        }

        data = nii.get_fdata(caching='unchanged')

        if len(data_shape) >= 3:
            slice_idx = data_shape[2] // 2
            if len(data_shape) == 4:
                slice_data = data[:, :, slice_idx, 0]
            else:
                slice_data = data[:, :, slice_idx]

            png_path = create_lossless_png_enhanced(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['lossless_png_path'] = str(png_path)

            tiff_path = create_lossless_tiff(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['lossless_tiff_path'] = str(tiff_path)

            thumb_path = create_thumbnail(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['thumbnail_path'] = str(thumb_path)

            metadata['extracted_slice'] = slice_idx

        return metadata

    except Exception as e:
        logger.error(f"Error processing NIfTI {file_path}: {e}")
        return None


def process_dicom_from_memory(file_data: bytes, file_path: str, file_hash: str,
                              patient_id: str, source_archive: Path,
                              storage_path: Path) -> Optional[Dict]:
    """Process DICOM from memory (ZIP) with proper window/level"""
    try:
        dicom_io = io.BytesIO(file_data)
        ds = pydicom.dcmread(dicom_io)

        # Extract window/level values
        window_center = 0
        window_width = 0
        if hasattr(ds, 'WindowCenter'):
            wc = ds.WindowCenter
            window_center = float(wc[0] if isinstance(wc, (list, pydicom.multival.MultiValue)) else wc)
        if hasattr(ds, 'WindowWidth'):
            ww = ds.WindowWidth
            window_width = float(ww[0] if isinstance(ww, (list, pydicom.multival.MultiValue)) else ww)

        metadata = {
            'image_hash': file_hash,
            'file_type': 'DICOM',
            'original_path': file_path,
            'source_archive': str(source_archive),
            'patient_id': patient_id or getattr(ds, 'PatientID', 'UNKNOWN'),
            'modality': getattr(ds, 'Modality', 'UNKNOWN'),
            'study_date': getattr(ds, 'StudyDate', ''),
            'series_description': getattr(ds, 'SeriesDescription', ''),
            'rows': getattr(ds, 'Rows', 0),
            'columns': getattr(ds, 'Columns', 0),
            'bits_stored': getattr(ds, 'BitsStored', 16),
            'rescale_slope': float(getattr(ds, 'RescaleSlope', 1.0)),
            'rescale_intercept': float(getattr(ds, 'RescaleIntercept', 0.0)),
            'window_center': window_center,
            'window_width': window_width,
            'photometric_interpretation': getattr(ds, 'PhotometricInterpretation', 'MONOCHROME2')
        }

        if hasattr(ds, 'pixel_array'):
            pixel_array = ds.pixel_array

            # Handle photometric interpretation
            if metadata['photometric_interpretation'] == 'MONOCHROME1':
                pixel_array = np.max(pixel_array) - pixel_array

            png_path = create_lossless_png_enhanced(
                pixel_array, metadata['patient_id'], file_hash,
                metadata, storage_path
            )
            metadata['lossless_png_path'] = str(png_path)

            tiff_path = create_lossless_tiff(
                pixel_array, metadata['patient_id'], file_hash,
                metadata, storage_path
            )
            metadata['lossless_tiff_path'] = str(tiff_path)

            thumb_path = create_thumbnail(
                pixel_array, metadata['patient_id'], file_hash,
                metadata, storage_path
            )
            metadata['thumbnail_path'] = str(thumb_path)

        return metadata

    except Exception as e:
        logger.error(f"Failed to process DICOM from memory: {e}")
        return None


def process_nifti_from_memory(file_data: bytes, file_path: str, file_hash: str,
                              patient_id: str, source_archive: Path,
                              storage_path: Path) -> Optional[Dict]:
    """Process NIfTI from memory (ZIP)"""
    try:
        if file_path.endswith('.gz'):
            import gzip
            file_data = gzip.decompress(file_data)

        nifti_io = io.BytesIO(file_data)
        nii = nib.Nifti1Image.from_bytes(nifti_io.read())

        header = nii.header
        data_shape = nii.shape

        metadata = {
            'image_hash': file_hash,
            'file_type': 'NIfTI',
            'original_path': file_path,
            'source_archive': str(source_archive),
            'patient_id': patient_id,
            'modality': determine_modality_from_path(Path(file_path)),
            'data_shape': list(data_shape),
            'voxel_size': list(header.get_zooms()),
            'data_type': str(header.get_data_dtype()),
            'window_center': 0,  # Will be auto-calculated
            'window_width': 0,
            'rescale_slope': 1.0,
            'rescale_intercept': 0.0
        }

        data = nii.get_fdata()

        if len(data_shape) >= 3:
            slice_idx = data_shape[2] // 2
            if len(data_shape) == 4:
                slice_data = data[:, :, slice_idx, 0]
            else:
                slice_data = data[:, :, slice_idx]

            png_path = create_lossless_png_enhanced(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['lossless_png_path'] = str(png_path)

            tiff_path = create_lossless_tiff(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['lossless_tiff_path'] = str(tiff_path)

            thumb_path = create_thumbnail(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['thumbnail_path'] = str(thumb_path)

            metadata['extracted_slice'] = slice_idx

        return metadata

    except Exception as e:
        logger.error(f"Failed to process NIfTI from memory: {e}")
        return None


# Helper functions with proper DICOM window/level handling
def auto_window_level(pixel_array: np.ndarray,
                     percentile_min: float = 0.5,
                     percentile_max: float = 99.5) -> Tuple[float, float]:
    """Auto-calculate window center and width based on histogram"""
    non_zero = pixel_array[pixel_array != 0] if np.any(pixel_array != 0) else pixel_array

    if len(non_zero) > 0:
        min_val = np.percentile(non_zero, percentile_min)
        max_val = np.percentile(non_zero, percentile_max)
    else:
        min_val = pixel_array.min()
        max_val = pixel_array.max()

    window_center = (max_val + min_val) / 2
    window_width = max_val - min_val

    return window_center, window_width


def apply_dicom_windowing(pixel_array: np.ndarray,
                         window_center: float,
                         window_width: float,
                         rescale_slope: float = 1.0,
                         rescale_intercept: float = 0.0) -> np.ndarray:
    """Apply DICOM window/level to pixel array"""
    # Apply rescale slope and intercept
    pixel_array = pixel_array.astype(np.float32) * rescale_slope + rescale_intercept

    if window_center == 0 and window_width == 0:
        return pixel_array

    # Apply window/level
    min_window = window_center - window_width / 2
    max_window = window_center + window_width / 2

    pixel_array = np.clip(pixel_array, min_window, max_window)

    return pixel_array


def create_lossless_png_enhanced(pixel_array: np.ndarray, patient_id: str,
                                 file_hash: str, metadata: Dict,
                                 storage_path: Path) -> Path:
    """Create lossless PNG with proper window/level handling"""
    lossless_png_dir = storage_path / "lossless" / "lossless_png" / patient_id
    lossless_png_dir.mkdir(parents=True, exist_ok=True)

    # Ensure 2D
    if len(pixel_array.shape) > 2:
        pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

    # Get window/level parameters
    window_center = metadata.get('window_center', 0)
    window_width = metadata.get('window_width', 0)
    rescale_slope = metadata.get('rescale_slope', 1.0)
    rescale_intercept = metadata.get('rescale_intercept', 0.0)

    # Apply rescale
    pixel_array_rescaled = pixel_array.astype(np.float32) * rescale_slope + rescale_intercept

    # Auto-calculate window/level if not provided
    if window_center == 0 and window_width == 0:
        window_center, window_width = auto_window_level(pixel_array_rescaled)

    # Apply windowing for display version
    pixel_array_windowed = apply_dicom_windowing(
        pixel_array, window_center, window_width, rescale_slope, rescale_intercept
    )

    # Normalize for PNG
    min_val = pixel_array_windowed.min()
    max_val = pixel_array_windowed.max()

    output_path = lossless_png_dir / f"{file_hash[:12]}.png"

    if output_path.exists():
        return output_path

    if max_val > min_val:
        # Scale to 16-bit range
        pixel_array_normalized = ((pixel_array_windowed - min_val) / (max_val - min_val) * 65535).astype(np.uint16)
        img = Image.fromarray(pixel_array_normalized, mode='I;16')
    else:
        pixel_array_normalized = np.zeros_like(pixel_array_windowed, dtype=np.uint16)
        img = Image.fromarray(pixel_array_normalized, mode='I;16')

    img.save(output_path, 'PNG', compress_level=1)
    return output_path


def create_lossless_tiff(pixel_array: np.ndarray, patient_id: str,
                         file_hash: str, metadata: Dict,
                         storage_path: Path) -> Path:
    """Create TIFF with proper DICOM window/level conversion - FIXED WHITE IMAGE ISSUE"""
    tiff_dir = storage_path / "lossless" / "lossless_tiff" / patient_id
    tiff_dir.mkdir(parents=True, exist_ok=True)

    # Ensure 2D
    if len(pixel_array.shape) > 2:
        pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

    # Get window/level parameters
    window_center = metadata.get('window_center', 0)
    window_width = metadata.get('window_width', 0)
    rescale_slope = metadata.get('rescale_slope', 1.0)
    rescale_intercept = metadata.get('rescale_intercept', 0.0)
    modality = metadata.get('modality', 'UNKNOWN')

    # Apply rescale slope and intercept
    pixel_array_rescaled = pixel_array.astype(np.float32) * rescale_slope + rescale_intercept

    # Auto-calculate window/level if not provided
    if window_center == 0 and window_width == 0:
        # Use robust percentiles for auto window/level
        non_zero = pixel_array_rescaled[pixel_array_rescaled != pixel_array_rescaled.min()]
        if len(non_zero) > 0:
            p1 = np.percentile(non_zero, 1)
            p99 = np.percentile(non_zero, 99)
            p10 = np.percentile(non_zero, 10)
            p90 = np.percentile(non_zero, 90)
            window_center = (p10 + p90) / 2
            window_width = p99 - p1
            if window_width < 1:
                window_width = p90 - p10
        else:
            window_center = (pixel_array_rescaled.min() + pixel_array_rescaled.max()) / 2
            window_width = pixel_array_rescaled.max() - pixel_array_rescaled.min()

    # Save primary display version (viewable)
    display_path = tiff_dir / f"{file_hash[:12]}.tiff"
    if not display_path.exists():
        # Apply windowing for display
        min_window = window_center - window_width / 2
        max_window = window_center + window_width / 2
        pixel_array_windowed = np.clip(pixel_array_rescaled, min_window, max_window)

        # Normalize to 16-bit for display
        min_val = pixel_array_windowed.min()
        max_val = pixel_array_windowed.max()

        if max_val > min_val:
            pixel_array_display = ((pixel_array_windowed - min_val) / (max_val - min_val) * 65535).astype(np.uint16)
        else:
            pixel_array_display = np.full_like(pixel_array_windowed, 32768, dtype=np.uint16)

        tiff_metadata_display = {
            'ImageDescription': json.dumps({
                'version': 'display',
                'patient_id': patient_id,
                'modality': modality,
                'window_center': float(window_center),
                'window_width': float(window_width),
                'original_min': float(pixel_array_rescaled.min()),
                'original_max': float(pixel_array_rescaled.max())
            }),
            'Software': 'ADNI Pipeline - Display Version',
            'DateTime': datetime.now().isoformat()
        }

        tifffile.imwrite(
            display_path,
            pixel_array_display,
            compression='lzw',
            metadata=tiff_metadata_display,
            photometric='minisblack'
        )

    # Save data version (normalized for viewing but preserves relationships)
    data_path = tiff_dir / f"{file_hash[:12]}_data.tiff"
    if not data_path.exists():
        # Normalize data to 16-bit range for viewability
        data_min = pixel_array_rescaled.min()
        data_max = pixel_array_rescaled.max()

        if data_max > data_min:
            pixel_array_data = ((pixel_array_rescaled - data_min) / (data_max - data_min) * 65535).astype(np.uint16)
        else:
            pixel_array_data = np.full_like(pixel_array_rescaled, 32768, dtype=np.uint16)

        tiff_metadata_data = {
            'ImageDescription': json.dumps({
                'version': 'data_normalized',
                'patient_id': patient_id,
                'modality': modality,
                'original_min': float(data_min),
                'original_max': float(data_max),
                'reconstruction': '(pixel/65535)*(max-min)+min'
            }),
            'Software': 'ADNI Pipeline - Data Version',
            'DateTime': datetime.now().isoformat()
        }

        tifffile.imwrite(
            data_path,
            pixel_array_data,
            compression='lzw',
            metadata=tiff_metadata_data,
            photometric='minisblack'
        )

    # Return display version (better for viewing)
    return display_path


def create_thumbnail(pixel_array: np.ndarray, patient_id: str,
                     file_hash: str, metadata: Dict, storage_path: Path) -> Path:
    """Create thumbnail with proper window/level for viewing"""
    thumb_dir = storage_path / "thumbnails" / patient_id
    thumb_dir.mkdir(parents=True, exist_ok=True)

    output_path = thumb_dir / f"{file_hash[:8]}_t.jpg"

    if output_path.exists():
        return output_path

    # Ensure 2D
    if len(pixel_array.shape) > 2:
        pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

    # Apply rescale
    rescale_slope = metadata.get('rescale_slope', 1.0)
    rescale_intercept = metadata.get('rescale_intercept', 0.0)
    pixel_array = pixel_array.astype(np.float32) * rescale_slope + rescale_intercept

    # Auto window/level for thumbnail (wider percentiles for overview)
    window_center, window_width = auto_window_level(pixel_array, 2, 98)

    # Apply windowing
    min_window = window_center - window_width / 2
    max_window = window_center + window_width / 2
    pixel_array = np.clip(pixel_array, min_window, max_window)

    # Normalize to 8-bit
    if max_window > min_window:
        pixel_array = ((pixel_array - min_window) / (max_window - min_window) * 255).astype(np.uint8)
    else:
        pixel_array = np.zeros_like(pixel_array, dtype=np.uint8)

    # Create and save thumbnail
    img = Image.fromarray(pixel_array, mode='L')
    img.thumbnail((256, 256), Image.Resampling.LANCZOS)
    img.save(output_path, 'JPEG', quality=90, optimize=True)

    return output_path


def extract_patient_id(file_path: Path, ds) -> str:
    """Extract patient ID from DICOM or path"""
    if ds:
        patient_id = getattr(ds, 'PatientID', None)
        if patient_id:
            return str(patient_id).strip()

    return extract_patient_id_from_path(str(file_path))


def extract_patient_id_from_path(file_path: str) -> str:
    """Extract patient ID from file path"""
    import re
    path_str = str(file_path)

    match = re.search(r'(\d{3}_S_\d{4})', path_str)
    if match:
        return match.group(1)

    match = re.search(r'(I\d{6})', path_str)
    if match:
        return match.group(1)

    parts = file_path.split('/')
    if len(parts) > 1:
        return parts[-2]

    return 'UNKNOWN'


def determine_modality_from_path(file_path: Path) -> str:
    """Determine modality from file path"""
    path_str = str(file_path).upper()

    if any(x in path_str for x in ['PET', 'FDG', 'AV45']):
        return 'PET'
    elif any(x in path_str for x in ['MRI', 'MR', 'T1', 'T2', 'FLAIR']):
        return 'MRI'
    elif 'CT' in path_str:
        return 'CT'

    return 'UNKNOWN'


def execute_enhanced_image_processing(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                                      base_path: str, storage_path: str,
                                      storage_config: Dict = None,
                                      max_workers: int = 8) -> Dict[str, Any]:
    """
    Main execution function with integrated ZIP support
    This is the ONLY function the pipeline needs to call
    """
    from utils.neo4j_connector import Neo4jConnector

    logger.info("\n" + "="*70)
    logger.info("ENHANCED IMAGE PROCESSING (WITH ZIP SUPPORT)")
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

        # Initialize the enhanced processor with ZIP support
        processor = EnhancedLosslessProcessor(
            base_path=base_path,
            storage_path=storage_path,
            batch_size=batch_size,
            max_workers=max_workers,
            storage_config=storage_config  # Pass full storage config
        )

        # Log processing mode
        logger.info(f"Processing mode: {processor.processing_mode.value}")

        if processor.zip_config:
            if processor.zip_config.zip_numbers:
                logger.info(f"Will process ZIP numbers: {processor.zip_config.zip_numbers}")
            elif processor.zip_config.max_zips:
                logger.info(f"Will process first {processor.zip_config.max_zips} ZIPs")

        # Process all images (directories and/or ZIPs based on config)
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
        logger.info(f"Processing mode: {processing_results['mode']}")
        logger.info(f"Total files found: {processing_results['total_files']:,}")
        logger.info(f"  DICOM files: {processing_results['dicom_count']:,}")
        logger.info(f"  NIfTI files: {processing_results['nifti_count']:,}")
        logger.info(f"Already processed: {processing_results['already_processed']:,}")
        logger.info(f"Newly processed: {processing_results['newly_processed']:,}")
        logger.info(f"Failed: {processing_results['failed']:,}")

        if processing_results.get('dirs_processed', 0) > 0:
            logger.info(f"Directories processed: {processing_results['dirs_processed']}")
        if processing_results.get('zips_processed', 0) > 0:
            logger.info(f"ZIP files processed: {processing_results['zips_processed']}")

        logger.info(f"Inserted to Neo4j: {processing_results['neo4j_inserted']:,}")
        if es_count > 0:
            logger.info(f"Indexed to Elasticsearch: {es_count:,}")
        logger.info(f"Processing time: {elapsed_time:.2f} seconds")
        logger.info(f"Output formats: PNG (16-bit), TIFF (32-bit float), JPEG thumbnails")

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


# The pipeline just needs to call this function with the config
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Enhanced Image Processing with ZIP Support")
    parser.add_argument('--config', help='Path to config YAML')
    parser.add_argument('--neo4j-uri', default='bolt://localhost:7687')
    parser.add_argument('--neo4j-user', default='neo4j')
    parser.add_argument('--neo4j-password', required=True)
    parser.add_argument('--base-path', help='Base path for data')
    parser.add_argument('--storage-path', default='./image_storage')

    args = parser.parse_args()

    # Load config if provided
    storage_config = None
    if args.config:
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
            storage_config = config.get('image_storage', {})

            # Override with command line args if provided
            if not args.base_path:
                args.base_path = config.get('base_path', '.')

    # Execute processing - this is the ONLY function the pipeline needs
    results = execute_enhanced_image_processing(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        base_path=args.base_path,
        storage_path=args.storage_path or storage_config.get('storage_path', './image_storage'),
        storage_config=storage_config,
        max_workers=8
    )

    print(f"\n✅ Processing complete!")
    print(f"   Mode: {results.get('mode', 'unknown')}")
    print(f"   Processed: {results.get('newly_processed', 0):,} images")
    print(f"   Time: {results.get('processing_time_seconds', 0):.2f} seconds")