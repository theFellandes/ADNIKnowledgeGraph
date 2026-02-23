"""
Enhanced Step 5: Image Processing with Smooth Rendering and Multi-Resolution Support
Includes interpolation instructions, pyramid TIFF, and web viewer formats
"""

import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set, Any, Union
import pydicom
import nibabel as nib
import numpy as np
from PIL import Image
try:
    from PIL.PngImagePlugin import PngInfo
except ImportError:
    PngInfo = None
import tifffile
import json
import mmap
import os
import zipfile
import io
import re
import yaml
import base64
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from multiprocessing import cpu_count
import lmdb
from tqdm import tqdm
import time
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from scipy import ndimage

# Try to import optional scikit-image components
try:
    from skimage import img_as_float, img_as_ubyte
    from skimage.transform import resize as sk_resize
    SKIMAGE_AVAILABLE = True
except ImportError:
    SKIMAGE_AVAILABLE = False
    sk_resize = None  # Define as None for clarity
    # Define fallback functions if needed
    def img_as_float(image):
        """Simple fallback for img_as_float"""
        return image.astype(np.float32) / np.max(image)

    def img_as_ubyte(image):
        """Simple fallback for img_as_ubyte"""
        return (image * 255).astype(np.uint8)

logger = logging.getLogger(__name__)


class ProcessingMode(Enum):
    """Processing modes for image data"""
    EXTRACTED_DIR = "extracted"
    ZIP_DIRECT = "zip_direct"
    MIXED = "mixed"
    AUTO = "auto"


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
        mode_str = zip_config.get('mode', 'auto')
        mode = ProcessingMode(mode_str)

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
    """Enhanced processor with smooth rendering and multi-resolution support"""

    def __init__(self, base_path: str, storage_path: str,
                 batch_size: int = 1000, max_workers: int = None,
                 storage_config: Dict = None):
        """Initialize processor with enhanced features"""
        self.base_path = Path(base_path)
        self.storage_path = Path(storage_path)
        self.batch_size = batch_size
        self.max_workers = max_workers or min(cpu_count() - 1, 16)
        self.storage_config = storage_config or {}

        # Parse ZIP configuration if present
        self.zip_config = None
        if storage_config and 'zip_processing' in storage_config:
            self.zip_config = ZipProcessingConfig.from_storage_config(storage_config, str(base_path))

        # Storage directories - Enhanced with new formats
        self.metadata_path = self.storage_path / "metadata"
        self.lossless_path = self.storage_path / "lossless"
        self.lossless_png_path = self.lossless_path / "lossless_png"
        self.lossless_tiff_path = self.lossless_path / "lossless_tiff"
        self.smooth_tiff_path = self.lossless_path / "smooth_tiff"  # NEW
        self.pyramid_tiff_path = self.lossless_path / "pyramid_tiff"  # NEW
        self.viewer_data_path = self.storage_path / "viewer_ready"  # NEW
        self.thumbnail_path = self.storage_path / "thumbnails"

        # Create all directories
        for path in [self.metadata_path, self.lossless_png_path,
                     self.lossless_tiff_path, self.smooth_tiff_path,
                     self.pyramid_tiff_path, self.viewer_data_path,
                     self.thumbnail_path]:
            path.mkdir(parents=True, exist_ok=True)

        # Setup serving cache if needed
        if self.zip_config and self.zip_config.extract_for_serving and self.zip_config.serving_cache_dir:
            self.zip_config.serving_cache_dir.mkdir(parents=True, exist_ok=True)

        # LMDB for checkpoint tracking
        self.checkpoint_db_path = self.storage_path / "checkpoints"
        self.checkpoint_db_path.mkdir(exist_ok=True)

        self.env = lmdb.open(
            str(self.checkpoint_db_path),
            map_size=10 * 1024 * 1024 * 1024,
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
        skip_dirs = {'.git', '__pycache__', 'thumbnails', 'lossless', 'metadata', 'viewer_ready'}

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

                if file_lower.endswith(('.dcm', '.ima')):
                    image_files.append(('dicom', file_path))
                elif '.' not in file and file_path.stat().st_size > 100000:
                    if self._is_dicom_mmap(file_path):
                        image_files.append(('dicom', file_path))
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
        """Process all images with enhanced features"""
        results = {
            'total_files': 0,
            'already_processed': 0,
            'newly_processed': 0,
            'failed': 0,
            'dicom_count': 0,
            'nifti_count': 0,
            'mode': self.processing_mode.value,
            'zips_processed': 0,
            'dirs_processed': 0,
            'smooth_tiffs_created': 0,
            'pyramid_tiffs_created': 0,
            'viewer_files_created': 0
        }

        logger.info(f"Processing mode: {self.processing_mode.value}")

        processed_hashes = self._get_processed_hashes()
        results['already_processed'] = len(processed_hashes)

        if self.processing_mode == ProcessingMode.EXTRACTED_DIR:
            results = self._process_directories(results, processed_hashes)
        elif self.processing_mode == ProcessingMode.ZIP_DIRECT:
            results = self._process_zips(results, processed_hashes)
        elif self.processing_mode == ProcessingMode.MIXED:
            logger.info("Mixed mode: processing directories first, then ZIPs")
            results = self._process_directories(results, processed_hashes)
            results = self._process_zips(results, processed_hashes)

        return results

    def _process_directories(self, results: Dict, processed_hashes: Set[str]) -> Dict:
        """Process files from directories with enhanced features"""
        if not self.file_index:
            logger.info("No files found in directories")
            return results

        logger.info(f"Processing {len(self.file_index)} files from directories...")
        results['dirs_processed'] = 1

        unprocessed_files = []
        for file_type, file_path in self.file_index:
            file_hash = self._quick_hash(file_path)
            if file_hash not in processed_hashes:
                unprocessed_files.append((file_type, file_path, file_hash))

            if file_type == 'dicom':
                results['dicom_count'] += 1
            else:
                results['nifti_count'] += 1

        results['total_files'] += len(self.file_index)

        if not unprocessed_files:
            logger.info("All directory files already processed")
            return results

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
                        results['smooth_tiffs_created'] += batch_results.get('smooth_tiffs', 0)
                        results['pyramid_tiffs_created'] += batch_results.get('pyramid_tiffs', 0)
                        results['viewer_files_created'] += batch_results.get('viewer_files', 0)
                        pbar.update(batch_results['total'])
                        self._save_checkpoint(batch_results['metadata'])
                    except Exception as e:
                        logger.error(f"Batch failed: {e}")
                        results['failed'] += self.batch_size

        return results

    def _process_zips(self, results: Dict, processed_hashes: Set[str]) -> Dict:
        """Process files from ZIP archives with enhanced features"""
        if not self.available_zips:
            logger.info("No ZIP files to process")
            return results

        zips_to_process = self._get_zips_to_process()

        if not zips_to_process:
            logger.info("No ZIP files selected for processing")
            return results

        logger.info(f"Processing {len(zips_to_process)} ZIP files...")
        results['zips_processed'] = len(zips_to_process)

        for zip_path in zips_to_process:
            logger.info(f"Processing ZIP: {zip_path.name}")

            if self._is_zip_processed(zip_path):
                logger.info(f"ZIP already processed: {zip_path.name}")
                continue

            zip_results = self._process_single_zip(zip_path, processed_hashes)

            results['total_files'] += zip_results['total_files']
            results['newly_processed'] += zip_results['processed']
            results['failed'] += zip_results['failed']
            results['dicom_count'] += zip_results['dicom_files']
            results['nifti_count'] += zip_results['nifti_files']
            results['smooth_tiffs_created'] += zip_results.get('smooth_tiffs', 0)
            results['pyramid_tiffs_created'] += zip_results.get('pyramid_tiffs', 0)
            results['viewer_files_created'] += zip_results.get('viewer_files', 0)

            self._mark_zip_processed(zip_path)
            processed_hashes.update(self._get_processed_hashes())

        return results

    def _get_zips_to_process(self) -> List[Path]:
        """Get list of ZIP files to process based on config"""
        if not self.available_zips or not self.zip_config:
            return []

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
        elif self.zip_config.max_zips:
            sorted_nums = sorted(self.available_zips.keys())[:self.zip_config.max_zips]
            return [self.available_zips[num] for num in sorted_nums]

        return list(self.available_zips.values())

    def _process_single_zip(self, zip_path: Path, processed_hashes: Set[str]) -> Dict:
        """Process a single ZIP file with enhanced features"""
        results = {
            'total_files': 0,
            'processed': 0,
            'failed': 0,
            'dicom_files': 0,
            'nifti_files': 0,
            'smooth_tiffs': 0,
            'pyramid_tiffs': 0,
            'viewer_files': 0
        }

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                image_files = self._discover_medical_images_in_zip(zf)
                results['total_files'] = len(image_files)

                logger.info(f"Found {len(image_files)} medical images in {zip_path.name}")

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
                                    if 'smooth_tiff_path' in metadata:
                                        results['smooth_tiffs'] += 1
                                    if 'pyramid_tiff_path' in metadata:
                                        results['pyramid_tiffs'] += 1
                                    if 'viewer_data_path' in metadata:
                                        results['viewer_files'] += 1

                                    self._save_metadata(metadata)
                                    self._mark_processed(file_hash)

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
        """Process a single image from ZIP with enhanced features"""
        try:
            with zf.open(file_path) as f:
                file_data = f.read()

            patient_id = extract_patient_id_from_path(file_path)

            if file_type == 'dicom':
                return process_dicom_from_memory_enhanced(
                    file_data, file_path, file_hash, patient_id,
                    zip_path, self.storage_path
                )
            elif file_type == 'nifti':
                return process_nifti_from_memory_enhanced(
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
        """Insert all processed images to Neo4j with enhanced paths"""
        logger.info("Inserting enhanced images to Neo4j...")

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
                'smooth_tiff_path': metadata.get('smooth_tiff_path', ''),  # NEW
                'pyramid_tiff_path': metadata.get('pyramid_tiff_path', ''),  # NEW
                'viewer_data_path': metadata.get('viewer_data_path', ''),  # NEW
                'viewer_html_path': metadata.get('viewer_html_path', ''),  # NEW
                'thumbnail_path': metadata.get('thumbnail_path', ''),
                'serving_path': metadata.get('serving_path', ''),
                'created_at': datetime.now().isoformat(),
                # Additional rendering metadata
                'has_smooth_rendering': bool(metadata.get('smooth_tiff_path')),
                'has_pyramid': bool(metadata.get('pyramid_tiff_path')),
                'has_web_viewer': bool(metadata.get('viewer_data_path')),
                'original_resolution': metadata.get('original_resolution', ''),
                'pyramid_levels': metadata.get('pyramid_levels', 0)
            }

            batch.append(neo4j_data)

            if len(batch) >= batch_size:
                count = self._insert_batch_to_neo4j(connector, batch)
                total_inserted += count
                batch = []

        if batch:
            count = self._insert_batch_to_neo4j(connector, batch)
            total_inserted += count

        logger.info(f"Inserted {total_inserted} enhanced images to Neo4j")
        return total_inserted

    def _insert_batch_to_neo4j(self, connector, batch: List[Dict]) -> int:
        """Insert batch to Neo4j with enhanced properties"""
        query = """
        UNWIND $batch as img
        MERGE (i:ImageNode {image_hash: img.image_hash})
        SET i += img,
            i.enhanced_formats = true,
            i.last_updated = datetime()
        WITH i, img
        WHERE img.patient_id IS NOT NULL
        MERGE (p:Patient {ptid: img.patient_id})
        MERGE (p)-[:HAS_IMAGE]->(i)
        
        // Create additional relationships for enhanced formats
        WITH i, img
        WHERE img.has_smooth_rendering = true
        SET i:SmoothRendering
        
        WITH i, img
        WHERE img.has_pyramid = true
        SET i:PyramidFormat
        
        WITH i, img
        WHERE img.has_web_viewer = true
        SET i:WebViewerReady
        
        RETURN count(i) as count
        """

        try:
            result = connector.run_query(query, {'batch': batch})
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.error(f"Neo4j insert failed: {e}")
            return 0

    def insert_to_elasticsearch(self, es_indexer) -> int:
        """Insert to Elasticsearch with enhanced fields"""
        if not es_indexer:
            return 0

        logger.info("Indexing enhanced images to Elasticsearch...")

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
                'smooth_tiff_path': metadata.get('smooth_tiff_path', ''),
                'pyramid_tiff_path': metadata.get('pyramid_tiff_path', ''),
                'viewer_data_path': metadata.get('viewer_data_path', ''),
                'viewer_html_path': metadata.get('viewer_html_path', ''),
                'thumbnail_path': metadata.get('thumbnail_path', ''),
                'has_smooth_rendering': bool(metadata.get('smooth_tiff_path')),
                'has_pyramid': bool(metadata.get('pyramid_tiff_path')),
                'has_web_viewer': bool(metadata.get('viewer_data_path')),
                'original_resolution': metadata.get('original_resolution', ''),
                'pyramid_levels': metadata.get('pyramid_levels', 0),
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

        logger.info(f"Indexed {success_count} enhanced images to Elasticsearch")
        return success_count


# Enhanced worker functions with new features
def process_batch_worker_enhanced(batch: List[Tuple[str, Path, str]],
                                  storage_path: Path) -> Dict:
    """Worker function to process a batch of files with enhanced features"""
    batch_results = {
        'total': len(batch),
        'processed': 0,
        'failed': 0,
        'smooth_tiffs': 0,
        'pyramid_tiffs': 0,
        'viewer_files': 0,
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
                if 'smooth_tiff_path' in metadata:
                    batch_results['smooth_tiffs'] += 1
                if 'pyramid_tiff_path' in metadata:
                    batch_results['pyramid_tiffs'] += 1
                if 'viewer_data_path' in metadata:
                    batch_results['viewer_files'] += 1
                batch_results['metadata'].append(metadata)
            else:
                batch_results['failed'] += 1

        except Exception as e:
            logger.debug(f"Failed to process {file_path}: {e}")
            batch_results['failed'] += 1

    return batch_results


def process_dicom_lossless_enhanced(file_path: Path, file_hash: str,
                                    storage_path: Path) -> Optional[Dict]:
    """Process DICOM file with enhanced rendering features"""
    try:
        ds = pydicom.dcmread(str(file_path), stop_before_pixels=True)
        patient_id = extract_patient_id(file_path, ds)

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
            'photometric_interpretation': getattr(ds, 'PhotometricInterpretation', 'MONOCHROME2'),
            'original_resolution': f"{getattr(ds, 'Columns', 0)}x{getattr(ds, 'Rows', 0)}"
        }

        if hasattr(ds, 'NumberOfFrames') or metadata['rows'] > 0:
            ds = pydicom.dcmread(str(file_path))

            if hasattr(ds, 'pixel_array'):
                pixel_array = ds.pixel_array

                # Handle photometric interpretation
                if metadata['photometric_interpretation'] == 'MONOCHROME1':
                    pixel_array = np.max(pixel_array) - pixel_array

                # Create standard lossless formats
                png_path = create_lossless_png_enhanced(
                    pixel_array, patient_id, file_hash, metadata, storage_path
                )
                metadata['lossless_png_path'] = str(png_path)

                tiff_path = create_lossless_tiff(
                    pixel_array, patient_id, file_hash, metadata, storage_path
                )
                metadata['lossless_tiff_path'] = str(tiff_path)

                # NEW: Create smooth TIFF with interpolation instructions
                smooth_tiff_path = create_smooth_tiff(
                    pixel_array, patient_id, file_hash, metadata, storage_path
                )
                if smooth_tiff_path:
                    metadata['smooth_tiff_path'] = str(smooth_tiff_path)
                else:
                    logger.warning(f"Failed to create smooth TIFF for {file_hash}")

                # NEW: Create pyramid TIFF
                pyramid_path, levels = create_pyramid_tiff(
                    pixel_array, patient_id, file_hash, metadata, storage_path
                )
                if pyramid_path:
                    metadata['pyramid_tiff_path'] = str(pyramid_path)
                    metadata['pyramid_levels'] = levels
                else:
                    logger.warning(f"Failed to create pyramid TIFF for {file_hash}")

                # NEW: Create web viewer data
                viewer_paths = create_web_viewer_data(
                    pixel_array, patient_id, file_hash, metadata, storage_path
                )
                if viewer_paths:
                    metadata['viewer_data_path'] = viewer_paths['data_path']
                    metadata['viewer_html_path'] = viewer_paths['html_path']
                else:
                    logger.warning(f"Failed to create web viewer for {file_hash}")

                # Create thumbnail
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
    """Process NIfTI file with enhanced rendering features"""
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
            'window_center': 0,
            'window_width': 0,
            'rescale_slope': 1.0,
            'rescale_intercept': 0.0,
            'original_resolution': f"{data_shape[0]}x{data_shape[1]}" if len(data_shape) >= 2 else ""
        }

        data = nii.get_fdata(caching='unchanged')

        if len(data_shape) >= 3:
            slice_idx = data_shape[2] // 2
            if len(data_shape) == 4:
                slice_data = data[:, :, slice_idx, 0]
            else:
                slice_data = data[:, :, slice_idx]

            # Create all enhanced formats
            png_path = create_lossless_png_enhanced(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['lossless_png_path'] = str(png_path)

            tiff_path = create_lossless_tiff(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['lossless_tiff_path'] = str(tiff_path)

            smooth_tiff_path = create_smooth_tiff(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['smooth_tiff_path'] = str(smooth_tiff_path)

            pyramid_path, levels = create_pyramid_tiff(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['pyramid_tiff_path'] = str(pyramid_path)
            metadata['pyramid_levels'] = levels

            viewer_paths = create_web_viewer_data(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['viewer_data_path'] = viewer_paths['data_path']
            metadata['viewer_html_path'] = viewer_paths['html_path']

            thumb_path = create_thumbnail(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['thumbnail_path'] = str(thumb_path)

            metadata['extracted_slice'] = slice_idx

        return metadata

    except Exception as e:
        logger.error(f"Error processing NIfTI {file_path}: {e}")
        return None


def process_dicom_from_memory_enhanced(file_data: bytes, file_path: str, file_hash: str,
                                       patient_id: str, source_archive: Path,
                                       storage_path: Path) -> Optional[Dict]:
    """Process DICOM from memory with enhanced features"""
    try:
        dicom_io = io.BytesIO(file_data)
        ds = pydicom.dcmread(dicom_io)

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
            'photometric_interpretation': getattr(ds, 'PhotometricInterpretation', 'MONOCHROME2'),
            'original_resolution': f"{getattr(ds, 'Columns', 0)}x{getattr(ds, 'Rows', 0)}"
        }

        if hasattr(ds, 'pixel_array'):
            pixel_array = ds.pixel_array

            if metadata['photometric_interpretation'] == 'MONOCHROME1':
                pixel_array = np.max(pixel_array) - pixel_array

            # Create all enhanced formats
            png_path = create_lossless_png_enhanced(
                pixel_array, metadata['patient_id'], file_hash, metadata, storage_path
            )
            metadata['lossless_png_path'] = str(png_path)

            tiff_path = create_lossless_tiff(
                pixel_array, metadata['patient_id'], file_hash, metadata, storage_path
            )
            metadata['lossless_tiff_path'] = str(tiff_path)

            smooth_tiff_path = create_smooth_tiff(
                pixel_array, metadata['patient_id'], file_hash, metadata, storage_path
            )
            metadata['smooth_tiff_path'] = str(smooth_tiff_path)

            pyramid_path, levels = create_pyramid_tiff(
                pixel_array, metadata['patient_id'], file_hash, metadata, storage_path
            )
            metadata['pyramid_tiff_path'] = str(pyramid_path)
            metadata['pyramid_levels'] = levels

            viewer_paths = create_web_viewer_data(
                pixel_array, metadata['patient_id'], file_hash, metadata, storage_path
            )
            metadata['viewer_data_path'] = viewer_paths['data_path']
            metadata['viewer_html_path'] = viewer_paths['html_path']

            thumb_path = create_thumbnail(
                pixel_array, metadata['patient_id'], file_hash, metadata, storage_path
            )
            metadata['thumbnail_path'] = str(thumb_path)

        return metadata

    except Exception as e:
        logger.error(f"Failed to process DICOM from memory: {e}")
        return None


def process_nifti_from_memory_enhanced(file_data: bytes, file_path: str, file_hash: str,
                                       patient_id: str, source_archive: Path,
                                       storage_path: Path) -> Optional[Dict]:
    """Process NIfTI from memory with enhanced features"""
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
            'window_center': 0,
            'window_width': 0,
            'rescale_slope': 1.0,
            'rescale_intercept': 0.0,
            'original_resolution': f"{data_shape[0]}x{data_shape[1]}" if len(data_shape) >= 2 else ""
        }

        data = nii.get_fdata()

        if len(data_shape) >= 3:
            slice_idx = data_shape[2] // 2
            if len(data_shape) == 4:
                slice_data = data[:, :, slice_idx, 0]
            else:
                slice_data = data[:, :, slice_idx]

            # Create all enhanced formats
            png_path = create_lossless_png_enhanced(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['lossless_png_path'] = str(png_path)

            tiff_path = create_lossless_tiff(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['lossless_tiff_path'] = str(tiff_path)

            smooth_tiff_path = create_smooth_tiff(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['smooth_tiff_path'] = str(smooth_tiff_path)

            pyramid_path, levels = create_pyramid_tiff(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['pyramid_tiff_path'] = str(pyramid_path)
            metadata['pyramid_levels'] = levels

            viewer_paths = create_web_viewer_data(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['viewer_data_path'] = viewer_paths['data_path']
            metadata['viewer_html_path'] = viewer_paths['html_path']

            thumb_path = create_thumbnail(
                slice_data, patient_id, file_hash, metadata, storage_path
            )
            metadata['thumbnail_path'] = str(thumb_path)

            metadata['extracted_slice'] = slice_idx

        return metadata

    except Exception as e:
        logger.error(f"Failed to process NIfTI from memory: {e}")
        return None


# NEW ENHANCED FORMAT FUNCTIONS

def _create_smooth_tiff(pixel_array: np.ndarray, patient_id: str,
                       file_hash: str, metadata: Dict,
                       storage_path: Path) -> Optional[Path]:
    """Create TIFF with embedded interpolation instructions for smooth rendering"""
    try:
        smooth_dir = storage_path / "lossless" / "smooth_tiff" / patient_id
        smooth_dir.mkdir(parents=True, exist_ok=True)

        output_path = smooth_dir / f"{file_hash[:12]}_smooth.tiff"

        if output_path.exists():
            logger.debug(f"Smooth TIFF already exists: {output_path}")
            return output_path

        # Ensure 2D
        if len(pixel_array.shape) > 2:
            pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

        # Get parameters
        window_center = metadata.get('window_center', 0)
        window_width = metadata.get('window_width', 0)
        rescale_slope = metadata.get('rescale_slope', 1.0)
        rescale_intercept = metadata.get('rescale_intercept', 0.0)

        # Apply rescale
        pixel_array_rescaled = pixel_array.astype(np.float32) * rescale_slope + rescale_intercept

        # Auto-calculate window/level if needed
        if window_center == 0 and window_width == 0:
            window_center, window_width = auto_window_level(pixel_array_rescaled)

        # Apply windowing
        min_window = window_center - window_width / 2
        max_window = window_center + window_width / 2
        pixel_array_windowed = np.clip(pixel_array_rescaled, min_window, max_window)

        # Normalize to 16-bit
        min_val = pixel_array_windowed.min()
        max_val = pixel_array_windowed.max()

        if max_val > min_val:
            pixel_array_normalized = ((pixel_array_windowed - min_val) / (max_val - min_val) * 65535).astype(np.uint16)
        else:
            pixel_array_normalized = np.full_like(pixel_array_windowed, 32768, dtype=np.uint16)

        # Create metadata with interpolation instructions
        tiff_metadata = {
            'ImageDescription': json.dumps({
                'interpolation': 'bicubic',
                'rendering_mode': 'smooth',
                'original_resolution': list(pixel_array.shape),
                'display_instructions': {
                    'interpolation_method': 'bicubic',
                    'smoothing_enabled': True,
                    'quality': 'high',
                    'anti_aliasing': True
                },
                'window_center': float(window_center),
                'window_width': float(window_width),
                'patient_id': patient_id,
                'modality': metadata.get('modality', 'UNKNOWN')
            }),
            'Software': 'Medical Imaging Pipeline - Smooth Rendering Version',
            'DateTime': datetime.now().isoformat(),
            'ResolutionUnit': 2,  # Inches
            'XResolution': 300.0,
            'YResolution': 300.0,
        }

        # Save with high quality settings
        tifffile.imwrite(
            output_path,
            pixel_array_normalized,
            compression='lzw',
            metadata=tiff_metadata,
            photometric='minisblack',
            resolution=(300.0, 300.0),
            resolutionunit=2
        )

        logger.info(f"Created smooth TIFF: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to create smooth TIFF: {e}")
        return None


def create_smooth_tiff(pixel_array: np.ndarray, patient_id: str,
                         file_hash: str, metadata: Dict,
                         storage_path: Path, scale_factor: int = 4) -> Optional[Path]:
    """Create high-resolution upscaled TIFF for smooth viewing"""
    try:
        highres_dir = storage_path / "lossless" / "highres_tiff" / patient_id
        highres_dir.mkdir(parents=True, exist_ok=True)

        output_path = highres_dir / f"{file_hash[:12]}_highres.tiff"

        if output_path.exists():
            return output_path

        # Ensure 2D
        if len(pixel_array.shape) > 2:
            pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

        # Apply windowing first
        rescale_slope = metadata.get('rescale_slope', 1.0)
        rescale_intercept = metadata.get('rescale_intercept', 0.0)
        pixel_array_rescaled = pixel_array.astype(np.float32) * rescale_slope + rescale_intercept

        # Upscale using cubic interpolation
        from scipy.ndimage import zoom
        upscaled = zoom(pixel_array_rescaled, scale_factor, order=3)  # Cubic interpolation

        # Normalize to 16-bit
        min_val = upscaled.min()
        max_val = upscaled.max()

        if max_val > min_val:
            normalized = ((upscaled - min_val) / (max_val - min_val) * 65535).astype(np.uint16)
        else:
            normalized = np.full_like(upscaled, 32768, dtype=np.uint16)

        # Save as single TIFF (Windows compatible)
        tifffile.imwrite(
            output_path,
            normalized,
            compression='lzw',
            photometric='minisblack'
        )

        return output_path
    except Exception as e:
        logger.error(f"Failed to create high-res TIFF: {e}")
        return None

def create_pyramid_tiff(pixel_array: np.ndarray, patient_id: str,
                        file_hash: str, metadata: Dict,
                        storage_path: Path) -> Tuple[Optional[Path], int]:
    """Create multi-resolution pyramid TIFF for smooth zooming"""
    try:
        pyramid_dir = storage_path / "lossless" / "pyramid_tiff" / patient_id
        pyramid_dir.mkdir(parents=True, exist_ok=True)

        output_path = pyramid_dir / f"{file_hash[:12]}_pyramid.tiff"

        if output_path.exists():
            # If already exists, calculate levels from file
            try:
                with tifffile.TiffFile(output_path) as tif:
                    levels = len(tif.pages)
                    logger.debug(f"Pyramid TIFF already exists with {levels} levels: {output_path}")
                    return output_path, levels
            except:
                logger.warning(f"Failed to read existing pyramid TIFF: {output_path}")

        # Ensure 2D
        if len(pixel_array.shape) > 2:
            pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

        # Apply rescale and windowing
        rescale_slope = metadata.get('rescale_slope', 1.0)
        rescale_intercept = metadata.get('rescale_intercept', 0.0)
        pixel_array_rescaled = pixel_array.astype(np.float32) * rescale_slope + rescale_intercept

        window_center = metadata.get('window_center', 0)
        window_width = metadata.get('window_width', 0)

        if window_center == 0 and window_width == 0:
            window_center, window_width = auto_window_level(pixel_array_rescaled)

        min_window = window_center - window_width / 2
        max_window = window_center + window_width / 2
        pixel_array_windowed = np.clip(pixel_array_rescaled, min_window, max_window)

        # Normalize for initial level
        min_val = pixel_array_windowed.min()
        max_val = pixel_array_windowed.max()

        if max_val > min_val:
            base_image = ((pixel_array_windowed - min_val) / (max_val - min_val) * 65535).astype(np.uint16)
        else:
            base_image = np.full_like(pixel_array_windowed, 32768, dtype=np.uint16)

        # Generate pyramid levels
        pyramid_levels = []
        current_image = base_image
        min_size = 64  # Minimum dimension for smallest level

        while min(current_image.shape) >= min_size:
            pyramid_levels.append(current_image)
            if min(current_image.shape) <= min_size * 2:
                break

            # Downsample by 2
            if SKIMAGE_AVAILABLE:
                # Use high-quality scikit-image resize
                new_shape = (max(min_size, current_image.shape[0] // 2),
                           max(min_size, current_image.shape[1] // 2))
                # Convert to float for skimage
                current_float = current_image.astype(np.float32) / 65535.0
                current_float = sk_resize(current_float, new_shape,
                                        order=3,  # Bicubic interpolation
                                        mode='reflect',
                                        anti_aliasing=True,
                                        preserve_range=True)
                current_image = (current_float * 65535).astype(np.uint16)
            else:
                # Simple numpy downsampling by averaging 2x2 blocks
                h, w = current_image.shape
                new_h, new_w = max(min_size, h // 2), max(min_size, w // 2)

                # Use slicing and mean for simple downsampling
                downsampled = np.zeros((new_h, new_w), dtype=np.float32)
                for i in range(new_h):
                    for j in range(new_w):
                        i_start = min(i * 2, h - 2)
                        j_start = min(j * 2, w - 2)
                        i_end = min(i_start + 2, h)
                        j_end = min(j_start + 2, w)
                        downsampled[i, j] = np.mean(current_image[i_start:i_end, j_start:j_end])

                current_image = downsampled.astype(np.uint16)

        # Save as multi-page TIFF
        with tifffile.TiffWriter(output_path, bigtiff=True) as tiff:
            for level, image in enumerate(pyramid_levels):
                # Ensure uint16
                if image.dtype != np.uint16:
                    img_uint16 = image.astype(np.uint16)
                else:
                    img_uint16 = image

                page_metadata = {
                    'ImageDescription': json.dumps({
                        'pyramid_level': level,
                        'total_levels': len(pyramid_levels),
                        'resolution': list(image.shape),
                        'scale_factor': 2 ** level,
                        'interpolation': 'bicubic' if SKIMAGE_AVAILABLE else 'average'
                    })
                }

                tiff.write(
                    img_uint16,
                    compression='lzw',
                    photometric='minisblack',
                    metadata=page_metadata,
                    subfiletype=1 if level > 0 else 0  # Mark reduced resolution images
                )

        logger.info(f"Created pyramid TIFF with {len(pyramid_levels)} levels: {output_path}")
        return output_path, len(pyramid_levels)

    except Exception as e:
        logger.error(f"Failed to create pyramid TIFF: {e}", exc_info=True)
        return None, 0


def create_web_viewer_data(pixel_array: np.ndarray, patient_id: str,
                           file_hash: str, metadata: Dict,
                           storage_path: Path) -> Optional[Dict[str, str]]:
    """Create web-ready data and viewer HTML for smooth browser rendering"""
    try:
        viewer_dir = storage_path / "viewer_ready" / patient_id
        viewer_dir.mkdir(parents=True, exist_ok=True)

        data_path = viewer_dir / f"{file_hash[:12]}_data.json"
        html_path = viewer_dir / f"{file_hash[:12]}_viewer.html"

        if data_path.exists() and html_path.exists():
            logger.debug(f"Web viewer files already exist for {file_hash}")
            return {
                'data_path': str(data_path),
                'html_path': str(html_path)
            }

        # Ensure 2D
        if len(pixel_array.shape) > 2:
            pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

        # Apply rescale and windowing
        rescale_slope = metadata.get('rescale_slope', 1.0)
        rescale_intercept = metadata.get('rescale_intercept', 0.0)
        pixel_array_rescaled = pixel_array.astype(np.float32) * rescale_slope + rescale_intercept

        window_center = metadata.get('window_center', 0)
        window_width = metadata.get('window_width', 0)

        if window_center == 0 and window_width == 0:
            window_center, window_width = auto_window_level(pixel_array_rescaled)

        # Apply windowing
        min_window = window_center - window_width / 2
        max_window = window_center + window_width / 2
        pixel_array_windowed = np.clip(pixel_array_rescaled, min_window, max_window)

        # Normalize to 0-255 for web display
        min_val = pixel_array_windowed.min()
        max_val = pixel_array_windowed.max()

        if max_val > min_val:
            normalized = ((pixel_array_windowed - min_val) / (max_val - min_val) * 255).astype(np.uint8)
        else:
            normalized = np.full_like(pixel_array_windowed, 128, dtype=np.uint8)

        # Create multiple resolutions for smooth zooming
        resolutions = {}

        for scale in [1, 2, 4]:
            if scale == 1:
                scaled_img = normalized
            else:
                new_size = (pixel_array.shape[0] * scale, pixel_array.shape[1] * scale)

                if SKIMAGE_AVAILABLE:
                    scaled_img = sk_resize(normalized, new_size,
                                        order=3,  # Bicubic
                                        mode='reflect',
                                        anti_aliasing=True,
                                        preserve_range=True).astype(np.uint8)
                else:
                    # Simple numpy repeat for upscaling
                    scaled_img = np.repeat(np.repeat(normalized, scale, axis=0), scale, axis=1)

            # Convert to base64
            resolutions[f'x{scale}'] = {
                'width': scaled_img.shape[1],
                'height': scaled_img.shape[0],
                'data': base64.b64encode(scaled_img.tobytes()).decode('utf-8')
            }

        # Save viewer data
        viewer_data = {
            'image_hash': file_hash,
            'patient_id': patient_id,
            'modality': metadata.get('modality', 'UNKNOWN'),
            'original_width': pixel_array.shape[1],
            'original_height': pixel_array.shape[0],
            'window_center': float(window_center),
            'window_width': float(window_width),
            'resolutions': resolutions,
            'metadata': {
                'study_date': metadata.get('study_date', ''),
                'series_description': metadata.get('series_description', ''),
                'original_min': float(pixel_array_rescaled.min()),
                'original_max': float(pixel_array_rescaled.max())
            }
        }

        with open(data_path, 'w') as f:
            json.dump(viewer_data, f)

        # Create HTML viewer (simplified version for brevity)
        viewer_html = create_viewer_html_content(file_hash, patient_id, pixel_array.shape, metadata)

        with open(html_path, 'w') as f:
            f.write(viewer_html)

        logger.info(f"Created web viewer files: {data_path} and {html_path}")

        return {
            'data_path': str(data_path),
            'html_path': str(html_path)
        }

    except Exception as e:
        logger.error(f"Failed to create web viewer data: {e}", exc_info=True)
        return None


def create_viewer_html_content(file_hash: str, patient_id: str, shape: tuple, metadata: Dict) -> str:
    """Create the HTML content for the viewer (separated for clarity)"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Medical Image Viewer - {patient_id}</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: #1a1a1a;
            color: #fff;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            overflow: hidden;
        }}
        
        #viewer-container {{
            width: 100vw;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            position: relative;
        }}
        
        #canvas {{
            border: 1px solid #333;
            cursor: crosshair;
            image-rendering: smooth;
            image-rendering: high-quality;
            -ms-interpolation-mode: bicubic;
            will-change: transform;
        }}
        
        #controls {{
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(0, 0, 0, 0.7);
            padding: 15px;
            border-radius: 8px;
            backdrop-filter: blur(10px);
        }}
        
        #info {{
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.7);
            padding: 15px;
            border-radius: 8px;
            backdrop-filter: blur(10px);
            font-size: 12px;
            font-family: monospace;
        }}
        
        .control-group {{
            margin-bottom: 10px;
        }}
        
        label {{
            display: inline-block;
            width: 100px;
            font-size: 12px;
        }}
        
        input[type="range"] {{
            width: 150px;
        }}
        
        button {{
            margin: 2px;
            padding: 5px 10px;
            background: #333;
            color: #fff;
            border: 1px solid #666;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }}
        
        button:hover {{
            background: #444;
        }}
        
        #zoom-display {{
            display: inline-block;
            width: 50px;
            text-align: right;
        }}
    </style>
</head>
<body>
    <div id="viewer-container">
        <canvas id="canvas"></canvas>
        
        <div id="controls">
            <h3 style="margin-top: 0;">Controls</h3>
            <div class="control-group">
                <label>Zoom:</label>
                <button onclick="zoom(0.8)">-</button>
                <span id="zoom-display">100%</span>
                <button onclick="zoom(1.25)">+</button>
            </div>
            <div class="control-group">
                <button onclick="resetView()">Reset View</button>
                <button onclick="fitToWindow()">Fit to Window</button>
            </div>
            <div class="control-group">
                <label>Interpolation:</label>
                <select id="interpolation">
                    <option value="high">High Quality</option>
                    <option value="medium">Medium</option>
                    <option value="pixelated">Pixelated</option>
                </select>
            </div>
        </div>
        
        <div id="info">
            <h3 style="margin-top: 0;">Image Info</h3>
            <div>Patient: {patient_id}</div>
            <div>Modality: {metadata.get('modality', 'UNKNOWN')}</div>
            <div>Resolution: {shape[1]}x{shape[0]}</div>
            <div>Study Date: {metadata.get('study_date', 'N/A')}</div>
            <div id="pixel-info"></div>
        </div>
    </div>
    
    <script>
        let imageData = null;
        let currentZoom = 1.0;
        let panX = 0;
        let panY = 0;
        let isDragging = false;
        let dragStartX = 0;
        let dragStartY = 0;
        
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        
        // Enable smooth rendering
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        
        // Load image data
        fetch('{file_hash[:12]}_data.json')
            .then(response => response.json())
            .then(data => {{
                imageData = data;
                initViewer();
            }})
            .catch(error => console.error('Error loading image data:', error));
        
        function initViewer() {{
            if (!imageData) return;
            
            // Set canvas size
            canvas.width = imageData.original_width;
            canvas.height = imageData.original_height;
            
            // Draw initial image
            drawImage();
            
            // Fit to window initially
            fitToWindow();
            
            // Setup controls
            setupControls();
        }}
        
        function drawImage() {{
            if (!imageData) return;
            
            // Clear canvas
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            // Select appropriate resolution based on zoom
            let resKey = 'x1';
            if (currentZoom > 2) resKey = 'x4';
            else if (currentZoom > 1) resKey = 'x2';
            
            const res = imageData.resolutions[resKey];
            
            // Decode base64 image data
            const binaryString = atob(res.data);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {{
                bytes[i] = binaryString.charCodeAt(i);
            }}
            
            // Create image data
            const imgData = ctx.createImageData(res.width, res.height);
            for (let i = 0; i < bytes.length; i++) {{
                imgData.data[i * 4] = bytes[i];     // R
                imgData.data[i * 4 + 1] = bytes[i]; // G
                imgData.data[i * 4 + 2] = bytes[i]; // B
                imgData.data[i * 4 + 3] = 255;      // A
            }}
            
            // Create temporary canvas for smooth scaling
            const tempCanvas = document.createElement('canvas');
            tempCanvas.width = res.width;
            tempCanvas.height = res.height;
            const tempCtx = tempCanvas.getContext('2d');
            tempCtx.putImageData(imgData, 0, 0);
            
            // Apply transformations
            ctx.save();
            ctx.translate(panX, panY);
            ctx.scale(currentZoom, currentZoom);
            
            // Draw with smooth interpolation
            const interpolation = document.getElementById('interpolation').value;
            ctx.imageSmoothingEnabled = interpolation !== 'pixelated';
            ctx.imageSmoothingQuality = interpolation === 'high' ? 'high' : 'medium';
            
            ctx.drawImage(tempCanvas, 0, 0, canvas.width, canvas.height);
            ctx.restore();
            
            // Update zoom display
            document.getElementById('zoom-display').textContent = Math.round(currentZoom * 100) + '%';
        }}
        
        function zoom(factor) {{
            currentZoom *= factor;
            currentZoom = Math.max(0.1, Math.min(10, currentZoom));
            drawImage();
        }}
        
        function resetView() {{
            currentZoom = 1.0;
            panX = 0;
            panY = 0;
            drawImage();
        }}
        
        function fitToWindow() {{
            const container = document.getElementById('viewer-container');
            const scaleX = (container.clientWidth - 100) / canvas.width;
            const scaleY = (container.clientHeight - 100) / canvas.height;
            currentZoom = Math.min(scaleX, scaleY);
            panX = (container.clientWidth - canvas.width * currentZoom) / 2;
            panY = (container.clientHeight - canvas.height * currentZoom) / 2;
            drawImage();
        }}
        
        function setupControls() {{
            // Mouse wheel zoom
            canvas.addEventListener('wheel', (e) => {{
                e.preventDefault();
                const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
                zoom(zoomFactor);
            }});
            
            // Mouse drag pan
            canvas.addEventListener('mousedown', (e) => {{
                isDragging = true;
                dragStartX = e.clientX - panX;
                dragStartY = e.clientY - panY;
                canvas.style.cursor = 'grabbing';
            }});
            
            canvas.addEventListener('mousemove', (e) => {{
                if (isDragging) {{
                    panX = e.clientX - dragStartX;
                    panY = e.clientY - dragStartY;
                    drawImage();
                }}
                
                // Show pixel info
                const rect = canvas.getBoundingClientRect();
                const x = Math.floor((e.clientX - rect.left - panX) / currentZoom);
                const y = Math.floor((e.clientY - rect.top - panY) / currentZoom);
                
                if (x >= 0 && x < canvas.width && y >= 0 && y < canvas.height) {{
                    document.getElementById('pixel-info').textContent = `Pixel: (${{x}}, ${{y}})`;
                }}
            }});
            
            canvas.addEventListener('mouseup', () => {{
                isDragging = false;
                canvas.style.cursor = 'crosshair';
            }});
            
            canvas.addEventListener('mouseleave', () => {{
                isDragging = false;
                canvas.style.cursor = 'crosshair';
            }});
            
            // Interpolation control
            document.getElementById('interpolation').addEventListener('change', drawImage);
            
            // Keyboard shortcuts
            document.addEventListener('keydown', (e) => {{
                switch(e.key) {{
                    case '+':
                    case '=':
                        zoom(1.25);
                        break;
                    case '-':
                    case '_':
                        zoom(0.8);
                        break;
                    case 'r':
                        resetView();
                        break;
                    case 'f':
                        fitToWindow();
                        break;
                }}
            }});
        }}
        
        // Handle window resize
        window.addEventListener('resize', () => {{
            if (imageData) {{
                fitToWindow();
            }}
        }});
    </script>
</body>
</html>"""


# Keep existing helper functions
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
    pixel_array = pixel_array.astype(np.float32) * rescale_slope + rescale_intercept

    if window_center == 0 and window_width == 0:
        return pixel_array

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

    if len(pixel_array.shape) > 2:
        pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

    window_center = metadata.get('window_center', 0)
    window_width = metadata.get('window_width', 0)
    rescale_slope = metadata.get('rescale_slope', 1.0)
    rescale_intercept = metadata.get('rescale_intercept', 0.0)

    pixel_array_rescaled = pixel_array.astype(np.float32) * rescale_slope + rescale_intercept

    if window_center == 0 and window_width == 0:
        window_center, window_width = auto_window_level(pixel_array_rescaled)

    pixel_array_windowed = apply_dicom_windowing(
        pixel_array, window_center, window_width, rescale_slope, rescale_intercept
    )

    min_val = pixel_array_windowed.min()
    max_val = pixel_array_windowed.max()

    output_path = lossless_png_dir / f"{file_hash[:12]}.png"

    if output_path.exists():
        return output_path

    if max_val > min_val:
        pixel_array_normalized = ((pixel_array_windowed - min_val) / (max_val - min_val) * 65535).astype(np.uint16)
        img = Image.fromarray(pixel_array_normalized, mode='I;16')
    else:
        pixel_array_normalized = np.zeros_like(pixel_array_windowed, dtype=np.uint16)
        img = Image.fromarray(pixel_array_normalized, mode='I;16')

    # Save with metadata hints for smooth rendering (if PngInfo is available)
    if PngInfo is not None:
        pnginfo = PngInfo()
        pnginfo.add_text("Interpolation", "bicubic")
        pnginfo.add_text("Software", "Medical Imaging Pipeline")
        pnginfo.add_text("RenderingIntent", "Perceptual")
        img.save(output_path, 'PNG', compress_level=1, pnginfo=pnginfo)
    else:
        # Fall back to saving without metadata if PngInfo not available
        img.save(output_path, 'PNG', compress_level=1)

    return output_path


def create_lossless_tiff(pixel_array: np.ndarray, patient_id: str,
                         file_hash: str, metadata: Dict,
                         storage_path: Path) -> Path:
    """Create TIFF with proper DICOM window/level conversion"""
    tiff_dir = storage_path / "lossless" / "lossless_tiff" / patient_id
    tiff_dir.mkdir(parents=True, exist_ok=True)

    if len(pixel_array.shape) > 2:
        pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

    window_center = metadata.get('window_center', 0)
    window_width = metadata.get('window_width', 0)
    rescale_slope = metadata.get('rescale_slope', 1.0)
    rescale_intercept = metadata.get('rescale_intercept', 0.0)
    modality = metadata.get('modality', 'UNKNOWN')

    pixel_array_rescaled = pixel_array.astype(np.float32) * rescale_slope + rescale_intercept

    if window_center == 0 and window_width == 0:
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

    display_path = tiff_dir / f"{file_hash[:12]}.tiff"
    if not display_path.exists():
        min_window = window_center - window_width / 2
        max_window = window_center + window_width / 2
        pixel_array_windowed = np.clip(pixel_array_rescaled, min_window, max_window)

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

    return display_path


def create_thumbnail(pixel_array: np.ndarray, patient_id: str,
                     file_hash: str, metadata: Dict, storage_path: Path) -> Path:
    """Create thumbnail with proper window/level for viewing"""
    thumb_dir = storage_path / "thumbnails" / patient_id
    thumb_dir.mkdir(parents=True, exist_ok=True)

    output_path = thumb_dir / f"{file_hash[:8]}_t.jpg"

    if output_path.exists():
        return output_path

    if len(pixel_array.shape) > 2:
        pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

    rescale_slope = metadata.get('rescale_slope', 1.0)
    rescale_intercept = metadata.get('rescale_intercept', 0.0)
    pixel_array = pixel_array.astype(np.float32) * rescale_slope + rescale_intercept

    window_center, window_width = auto_window_level(pixel_array, 2, 98)

    min_window = window_center - window_width / 2
    max_window = window_center + window_width / 2
    pixel_array = np.clip(pixel_array, min_window, max_window)

    if max_window > min_window:
        pixel_array = ((pixel_array - min_window) / (max_window - min_window) * 255).astype(np.uint8)
    else:
        pixel_array = np.zeros_like(pixel_array, dtype=np.uint8)

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
    Main execution function with enhanced rendering features

    Note: For full functionality, install optional dependencies:
        pip install scikit-image

    The code will work without scikit-image but with reduced quality for pyramid TIFFs.
    """
    from utils.neo4j_connector import Neo4jConnector

    logger.info("\n" + "="*70)
    logger.info("ENHANCED IMAGE PROCESSING WITH SMOOTH RENDERING")
    logger.info("="*70)

    # Check for optional dependencies
    if SKIMAGE_AVAILABLE:
        logger.info("✓ scikit-image available - full quality rendering enabled")
    else:
        logger.warning("⚠ scikit-image not available - using basic rendering (install with: pip install scikit-image)")

    start_time = time.time()

    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

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
        batch_size = storage_config.get('batch_size', 1000) if storage_config else 1000

        processor = EnhancedLosslessProcessor(
            base_path=base_path,
            storage_path=storage_path,
            batch_size=batch_size,
            max_workers=max_workers,
            storage_config=storage_config
        )

        logger.info(f"Processing mode: {processor.processing_mode.value}")
        logger.info("Enhanced features enabled:")
        logger.info("  ✓ Smooth TIFF with interpolation instructions")
        logger.info("  ✓ Multi-resolution pyramid TIFF")
        logger.info("  ✓ Web viewer with canvas rendering")

        if processor.zip_config:
            if processor.zip_config.zip_numbers:
                logger.info(f"Will process ZIP numbers: {processor.zip_config.zip_numbers}")
            elif processor.zip_config.max_zips:
                logger.info(f"Will process first {processor.zip_config.max_zips} ZIPs")

        processing_results = processor.process_all_parallel()

        neo4j_count = processor.insert_to_neo4j(connector)
        processing_results['neo4j_inserted'] = neo4j_count

        es_count = 0
        if es_indexer:
            es_count = processor.insert_to_elasticsearch(es_indexer)
            processing_results['es_indexed'] = es_count

        elapsed_time = time.time() - start_time
        processing_results['processing_time_seconds'] = elapsed_time

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

        logger.info("\nEnhanced formats created:")
        logger.info(f"  Smooth TIFFs: {processing_results.get('smooth_tiffs_created', 0):,}")
        logger.info(f"  Pyramid TIFFs: {processing_results.get('pyramid_tiffs_created', 0):,}")
        logger.info(f"  Web viewer files: {processing_results.get('viewer_files_created', 0):,}")

        if processing_results.get('dirs_processed', 0) > 0:
            logger.info(f"Directories processed: {processing_results['dirs_processed']}")
        if processing_results.get('zips_processed', 0) > 0:
            logger.info(f"ZIP files processed: {processing_results['zips_processed']}")

        logger.info(f"Inserted to Neo4j: {processing_results['neo4j_inserted']:,}")
        if es_count > 0:
            logger.info(f"Indexed to Elasticsearch: {es_count:,}")
        logger.info(f"Processing time: {elapsed_time:.2f} seconds")

        if processing_results['newly_processed'] > 0:
            rate = processing_results['newly_processed'] / elapsed_time
            logger.info(f"Processing rate: {rate:.1f} images/second")

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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Enhanced Image Processing with Smooth Rendering")
    parser.add_argument('--config', help='Path to config YAML')
    parser.add_argument('--neo4j-uri', default='bolt://localhost:7687')
    parser.add_argument('--neo4j-user', default='neo4j')
    parser.add_argument('--neo4j-password', required=True)
    parser.add_argument('--base-path', help='Base path for data')
    parser.add_argument('--storage-path', default='./image_storage')

    args = parser.parse_args()

    storage_config = None
    if args.config:
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
            storage_config = config.get('image_storage', {})

            if not args.base_path:
                args.base_path = config.get('base_path', '.')

    results = execute_enhanced_image_processing(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        base_path=args.base_path,
        storage_path=args.storage_path or storage_config.get('storage_path', './image_storage'),
        storage_config=storage_config,
        max_workers=8
    )

    print(f"\n✅ Enhanced processing complete!")
    print(f"   Mode: {results.get('mode', 'unknown')}")
    print(f"   Processed: {results.get('newly_processed', 0):,} images")
    print(f"   Smooth TIFFs: {results.get('smooth_tiffs_created', 0):,}")
    print(f"   Pyramid TIFFs: {results.get('pyramid_tiffs_created', 0):,}")
    print(f"   Web viewers: {results.get('viewer_files_created', 0):,}")
    print(f"   Time: {results.get('processing_time_seconds', 0):.2f} seconds")