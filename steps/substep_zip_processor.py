"""
Enhanced ZIP Medical Image Processor with Selective Processing
- Supports processing specific numbered ZIP files
- Two modes: extracted directories or direct ZIP processing
- Config-driven operation
- Integration with main pipeline
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
import zipfile
import yaml
import io
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import cpu_count
import lmdb
from tqdm import tqdm
import time
from datetime import datetime
import tempfile
import shutil
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ProcessingMode(Enum):
    """Processing modes for image data"""
    EXTRACTED_DIR = "extracted"  # Process from extracted directories
    ZIP_DIRECT = "zip_direct"  # Process directly from ZIP files
    MIXED = "mixed"  # Support both modes


@dataclass
class ZipProcessingConfig:
    """Configuration for ZIP processing"""
    mode: ProcessingMode
    zip_directory: Optional[Path] = None
    extracted_directory: Optional[Path] = None
    zip_numbers: Optional[List[int]] = None  # e.g., [1, 2, 3] for first 3 zips
    zip_patterns: Optional[List[str]] = None  # e.g., ["mri_*.zip", "pet_*.zip"]
    max_zips: Optional[int] = None  # Maximum number of ZIPs to process
    storage_path: Path = Path("./image_storage")
    extract_for_serving: bool = False  # Extract files for DICOM serving
    serving_cache_dir: Optional[Path] = None  # Directory for extracted serving files
    batch_size: int = 100
    max_workers: int = 8

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> 'ZipProcessingConfig':
        """Create from pipeline config"""
        image_config = config.get('image_storage', {})
        zip_config = image_config.get('zip_processing', {})

        # Determine mode
        mode_str = zip_config.get('mode', 'extracted')
        mode = ProcessingMode(mode_str)

        # Parse ZIP numbers (can be list or range string)
        zip_numbers = None
        if 'zip_numbers' in zip_config:
            numbers = zip_config['zip_numbers']
            if isinstance(numbers, list):
                zip_numbers = numbers
            elif isinstance(numbers, str):
                # Parse range like "1-3" or "1,2,5"
                zip_numbers = cls._parse_number_range(numbers)

        return cls(
            mode=mode,
            zip_directory=Path(zip_config.get('zip_directory', config.get('base_path', '.'))),
            extracted_directory=Path(zip_config.get('extracted_directory', config.get('base_path', '.'))),
            zip_numbers=zip_numbers,
            zip_patterns=zip_config.get('zip_patterns', ['*.zip']),
            max_zips=zip_config.get('max_zips'),
            storage_path=Path(image_config.get('storage_path', './image_storage')),
            extract_for_serving=zip_config.get('extract_for_serving', False),
            serving_cache_dir=Path(zip_config.get('serving_cache_dir', './serving_cache')) if zip_config.get(
                'serving_cache_dir') else None,
            batch_size=image_config.get('batch_size', 100),
            max_workers=config.get('max_workers', 8)
        )

    @staticmethod
    def _parse_number_range(range_str: str) -> List[int]:
        """Parse number range string like '1-3' or '1,2,5'"""
        numbers = []
        parts = range_str.split(',')

        for part in parts:
            if '-' in part:
                start, end = map(int, part.split('-'))
                numbers.extend(range(start, end + 1))
            else:
                numbers.append(int(part.strip()))

        return sorted(set(numbers))


class SelectiveZipProcessor:
    """
    Process medical images with selective ZIP handling
    Supports both extracted directories and direct ZIP processing
    """

    def __init__(self, config: Union[Dict, ZipProcessingConfig]):
        """
        Initialize with config

        Args:
            config: Dictionary config or ZipProcessingConfig object
        """
        if isinstance(config, dict):
            self.config = ZipProcessingConfig.from_config(config)
        else:
            self.config = config

        # Setup storage directories
        self.storage_path = self.config.storage_path
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
        if self.config.extract_for_serving and self.config.serving_cache_dir:
            self.config.serving_cache_dir.mkdir(parents=True, exist_ok=True)

        # Setup checkpoint tracking
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

        # Track available ZIPs
        self.available_zips = self._discover_zips()

    def _discover_zips(self) -> Dict[int, Path]:
        """
        Discover available ZIP files based on patterns

        Returns:
            Dictionary mapping ZIP number to path
        """
        available = {}

        if self.config.mode in [ProcessingMode.ZIP_DIRECT, ProcessingMode.MIXED]:
            if self.config.zip_directory and self.config.zip_directory.exists():
                # Look for ZIPs matching patterns
                for pattern in self.config.zip_patterns or ['*.zip']:
                    for zip_path in self.config.zip_directory.glob(pattern):
                        # Extract number from filename (e.g., mri_1.zip -> 1)
                        match = re.search(r'_(\d+)\.zip', zip_path.name)
                        if match:
                            num = int(match.group(1))
                            available[num] = zip_path
                        else:
                            # If no number pattern, use sequential numbering
                            available[len(available) + 1] = zip_path

        if available:
            logger.info(f"Discovered {len(available)} ZIP files")
            logger.info(f"Available ZIP numbers: {sorted(available.keys())}")

        return available

    def get_zips_to_process(self) -> List[Path]:
        """
        Get list of ZIP files to process based on config

        Returns:
            List of ZIP file paths to process
        """
        if not self.available_zips:
            return []

        # Filter by specified numbers
        if self.config.zip_numbers:
            selected = [
                self.available_zips[num]
                for num in self.config.zip_numbers
                if num in self.available_zips
            ]

            missing = [
                num for num in self.config.zip_numbers
                if num not in self.available_zips
            ]
            if missing:
                logger.warning(f"Requested ZIP numbers not found: {missing}")

            return selected

        # Limit by max_zips
        elif self.config.max_zips:
            sorted_nums = sorted(self.available_zips.keys())[:self.config.max_zips]
            return [self.available_zips[num] for num in sorted_nums]

        # Return all
        return list(self.available_zips.values())

    def process(self) -> Dict[str, Any]:
        """
        Main processing method based on configured mode

        Returns:
            Processing results
        """
        logger.info(f"Processing mode: {self.config.mode.value}")

        if self.config.mode == ProcessingMode.EXTRACTED_DIR:
            return self._process_extracted_directories()

        elif self.config.mode == ProcessingMode.ZIP_DIRECT:
            return self._process_zip_files()

        elif self.config.mode == ProcessingMode.MIXED:
            # Process both extracted and ZIPs
            results = {
                'extracted_results': {},
                'zip_results': {},
                'combined': {
                    'total_processed': 0,
                    'total_failed': 0
                }
            }

            if self.config.extracted_directory and self.config.extracted_directory.exists():
                results['extracted_results'] = self._process_extracted_directories()
                results['combined']['total_processed'] += results['extracted_results'].get('processed', 0)
                results['combined']['total_failed'] += results['extracted_results'].get('failed', 0)

            if self.available_zips:
                results['zip_results'] = self._process_zip_files()
                results['combined']['total_processed'] += results['zip_results'].get('processed', 0)
                results['combined']['total_failed'] += results['zip_results'].get('failed', 0)

            return results

        else:
            raise ValueError(f"Unknown processing mode: {self.config.mode}")

    def _process_extracted_directories(self) -> Dict[str, Any]:
        """Process from extracted directories (traditional mode)"""
        logger.info("Processing from extracted directories...")

        if not self.config.extracted_directory or not self.config.extracted_directory.exists():
            logger.error(f"Extracted directory not found: {self.config.extracted_directory}")
            return {'error': 'Extracted directory not found'}

        # Use the enhanced processor for directory processing
        from step5_improved_process_images import EnhancedLosslessProcessor

        processor = EnhancedLosslessProcessor(
            base_path=str(self.config.extracted_directory),
            storage_path=str(self.storage_path),
            batch_size=self.config.batch_size,
            max_workers=self.config.max_workers
        )

        return processor.process_all_parallel()

    def _process_zip_files(self) -> Dict[str, Any]:
        """Process directly from ZIP files"""
        logger.info("Processing directly from ZIP files...")

        zips_to_process = self.get_zips_to_process()

        if not zips_to_process:
            logger.warning("No ZIP files to process")
            return {'error': 'No ZIP files found'}

        logger.info(f"Will process {len(zips_to_process)} ZIP files:")
        for zip_path in zips_to_process:
            logger.info(f"  - {zip_path.name}")

        results = {
            'total_zips': len(zips_to_process),
            'processed_zips': 0,
            'total_files': 0,
            'processed': 0,
            'failed': 0,
            'skipped': 0,
            'zip_details': {}
        }

        # Process each selected ZIP
        for zip_path in zips_to_process:
            logger.info(f"\nProcessing ZIP: {zip_path.name}")

            # Check if already processed
            if self._is_zip_processed(zip_path):
                logger.info(f"ZIP already processed: {zip_path.name}")
                results['skipped'] += 1
                continue

            # Process this ZIP
            zip_results = self._process_single_zip(zip_path)

            # Aggregate results
            results['processed_zips'] += 1
            results['total_files'] += zip_results.get('total_files', 0)
            results['processed'] += zip_results.get('processed', 0)
            results['failed'] += zip_results.get('failed', 0)
            results['zip_details'][zip_path.name] = zip_results

            # Mark ZIP as processed
            self._mark_zip_processed(zip_path)

        return results

    def _process_single_zip(self, zip_path: Path) -> Dict[str, Any]:
        """Process a single ZIP file"""
        results = {
            'zip_name': zip_path.name,
            'zip_size_gb': zip_path.stat().st_size / (1024 ** 3),
            'total_files': 0,
            'processed': 0,
            'failed': 0,
            'dicom_files': 0,
            'nifti_files': 0,
            'serving_extracted': []
        }

        # Get already processed hashes
        processed_hashes = self._get_processed_hashes()

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Discover medical image files
                image_files = self._discover_medical_images_in_zip(zf)
                results['total_files'] = len(image_files)

                logger.info(f"Found {len(image_files)} medical images in {zip_path.name}")

                # Process images
                with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
                    futures = []

                    with tqdm(total=len(image_files),
                              desc=f"Processing {zip_path.name}") as pbar:

                        for file_type, file_path in image_files:
                            # Track file type
                            if file_type == 'dicom':
                                results['dicom_files'] += 1
                            elif file_type == 'nifti':
                                results['nifti_files'] += 1

                            # Generate hash
                            file_hash = self._generate_file_hash(zf, file_path)

                            if file_hash in processed_hashes:
                                pbar.update(1)
                                continue

                            # Submit processing task
                            future = executor.submit(
                                self._process_image_from_zip,
                                zf, file_path, file_type, file_hash, zip_path
                            )
                            futures.append((future, file_hash, file_path))

                        # Collect results
                        for future, file_hash, file_path in futures:
                            try:
                                metadata = future.result(timeout=60)

                                if metadata:
                                    results['processed'] += 1

                                    # Save metadata
                                    self._save_metadata(metadata)
                                    self._mark_processed(file_hash)

                                    # Extract for serving if configured
                                    if self.config.extract_for_serving:
                                        serving_path = self._extract_for_serving(
                                            zf, file_path, metadata
                                        )
                                        if serving_path:
                                            results['serving_extracted'].append(str(serving_path))
                                            metadata['serving_path'] = str(serving_path)
                                            # Update metadata with serving path
                                            self._save_metadata(metadata)
                                else:
                                    results['failed'] += 1

                            except Exception as e:
                                logger.error(f"Processing failed for {file_path}: {e}")
                                results['failed'] += 1

                            pbar.update(1)

        except Exception as e:
            logger.error(f"Failed to process ZIP {zip_path}: {e}")
            results['error'] = str(e)

        return results

    def _discover_medical_images_in_zip(self, zf: zipfile.ZipFile) -> List[Tuple[str, str]]:
        """Discover medical image files in ZIP"""
        image_files = []

        for file_path in zf.namelist():
            # Skip directories and system files
            if file_path.endswith('/') or '__MACOSX' in file_path or '.DS_Store' in file_path:
                continue

            file_lower = file_path.lower()

            # Check for DICOM
            if file_lower.endswith(('.dcm', '.ima')):
                image_files.append(('dicom', file_path))

            # Check for NIfTI
            elif file_lower.endswith(('.nii', '.nii.gz')):
                image_files.append(('nifti', file_path))

            # Check for DICOM without extension
            elif '.' not in os.path.basename(file_path):
                try:
                    with zf.open(file_path) as f:
                        header = f.read(132)
                        if len(header) >= 132 and header[128:132] == b'DICM':
                            image_files.append(('dicom', file_path))
                except:
                    pass

        return image_files

    def _process_image_from_zip(self, zf: zipfile.ZipFile,
                                file_path: str,
                                file_type: str,
                                file_hash: str,
                                zip_path: Path) -> Optional[Dict]:
        """Process a single image from ZIP"""
        try:
            # Read file data
            with zf.open(file_path) as f:
                file_data = f.read()

            # Extract patient ID
            patient_id = self._extract_patient_id(file_path)

            if file_type == 'dicom':
                # Process DICOM
                dicom_io = io.BytesIO(file_data)
                ds = pydicom.dcmread(dicom_io)

                metadata = self._create_dicom_metadata(
                    ds, file_hash, file_path, zip_path, patient_id
                )

                if hasattr(ds, 'pixel_array'):
                    pixel_array = ds.pixel_array
                    self._create_lossless_outputs(pixel_array, metadata)

                return metadata

            elif file_type == 'nifti':
                # Process NIfTI
                if file_path.endswith('.gz'):
                    import gzip
                    file_data = gzip.decompress(file_data)

                nifti_io = io.BytesIO(file_data)
                nii = nib.Nifti1Image.from_bytes(nifti_io.read())

                metadata = self._create_nifti_metadata(
                    nii, file_hash, file_path, zip_path, patient_id
                )

                # Process middle slice
                data = nii.get_fdata()
                if len(data.shape) >= 3:
                    slice_idx = data.shape[2] // 2
                    slice_data = data[:, :, slice_idx]
                    metadata['extracted_slice'] = slice_idx
                    self._create_lossless_outputs(slice_data, metadata)

                return metadata

        except Exception as e:
            logger.error(f"Failed to process {file_path}: {e}")
            return None

    def _extract_for_serving(self, zf: zipfile.ZipFile,
                             file_path: str,
                             metadata: Dict) -> Optional[Path]:
        """
        Extract file for DICOM serving

        Args:
            zf: ZIP file object
            file_path: Path within ZIP
            metadata: Image metadata

        Returns:
            Path to extracted file or None
        """
        if not self.config.serving_cache_dir:
            return None

        try:
            # Create patient directory
            patient_id = metadata.get('patient_id', 'UNKNOWN')
            patient_dir = self.config.serving_cache_dir / patient_id
            patient_dir.mkdir(parents=True, exist_ok=True)

            # Extract with unique name
            file_name = f"{metadata['image_hash'][:8]}_{os.path.basename(file_path)}"
            output_path = patient_dir / file_name

            # Extract file
            with zf.open(file_path) as src:
                with open(output_path, 'wb') as dst:
                    dst.write(src.read())

            logger.debug(f"Extracted for serving: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Failed to extract for serving: {e}")
            return None

    def _create_dicom_metadata(self, ds, file_hash: str, file_path: str,
                               zip_path: Path, patient_id: str) -> Dict:
        """Create metadata for DICOM file"""
        return {
            'image_hash': file_hash,
            'file_type': 'DICOM',
            'original_path': file_path,
            'source_archive': str(zip_path),
            'patient_id': patient_id or getattr(ds, 'PatientID', 'UNKNOWN'),
            'modality': getattr(ds, 'Modality', 'UNKNOWN'),
            'study_date': getattr(ds, 'StudyDate', ''),
            'series_description': getattr(ds, 'SeriesDescription', ''),
            'rows': getattr(ds, 'Rows', 0),
            'columns': getattr(ds, 'Columns', 0),
            'bits_stored': getattr(ds, 'BitsStored', 16),
            'rescale_slope': float(getattr(ds, 'RescaleSlope', 1.0)),
            'rescale_intercept': float(getattr(ds, 'RescaleIntercept', 0.0)),
            'processed_timestamp': datetime.now().isoformat()
        }

    def _create_nifti_metadata(self, nii, file_hash: str, file_path: str,
                               zip_path: Path, patient_id: str) -> Dict:
        """Create metadata for NIfTI file"""
        header = nii.header
        return {
            'image_hash': file_hash,
            'file_type': 'NIfTI',
            'original_path': file_path,
            'source_archive': str(zip_path),
            'patient_id': patient_id,
            'modality': self._determine_modality(file_path),
            'data_shape': list(nii.shape),
            'voxel_size': list(header.get_zooms()),
            'data_type': str(header.get_data_dtype()),
            'processed_timestamp': datetime.now().isoformat()
        }

    def _create_lossless_outputs(self, pixel_array: np.ndarray, metadata: Dict):
        """Create lossless PNG, TIFF, and thumbnail"""
        patient_id = metadata['patient_id']
        file_hash = metadata['image_hash']

        # Create PNG
        png_path = self._create_lossless_png(
            pixel_array, patient_id, file_hash,
            metadata.get('bits_stored', 16)
        )
        metadata['lossless_png_path'] = str(png_path)

        # Create TIFF
        tiff_path = self._create_lossless_tiff(
            pixel_array, patient_id, file_hash, metadata
        )
        metadata['lossless_tiff_path'] = str(tiff_path)

        # Create thumbnail
        thumb_path = self._create_thumbnail(
            pixel_array, patient_id, file_hash
        )
        metadata['thumbnail_path'] = str(thumb_path)

    def _create_lossless_png(self, pixel_array: np.ndarray,
                             patient_id: str, file_hash: str,
                             bits_stored: int) -> Path:
        """Create lossless PNG"""
        png_dir = self.lossless_png_path / patient_id
        png_dir.mkdir(parents=True, exist_ok=True)

        output_path = png_dir / f"{file_hash[:12]}.png"

        if output_path.exists():
            return output_path

        # Ensure 2D
        if len(pixel_array.shape) > 2:
            pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

        # Handle range
        min_val = pixel_array.min()
        max_val = pixel_array.max()

        if min_val < 0:
            pixel_array = pixel_array - min_val
            output_path = png_dir / f"{file_hash[:12]}_shift{int(-min_val)}.png"

        if max_val <= 255 and min_val >= 0:
            img = Image.fromarray(pixel_array.astype(np.uint8))
        elif max_val <= 65535:
            img = Image.fromarray(pixel_array.astype(np.uint16), mode='I;16')
        else:
            scale = 65535.0 / max_val
            scaled = (pixel_array * scale).astype(np.uint16)
            img = Image.fromarray(scaled, mode='I;16')
            output_path = png_dir / f"{file_hash[:12]}_scale{scale:.6f}.png"

        img.save(output_path, 'PNG', compress_level=1)
        return output_path

    def _create_lossless_tiff(self, pixel_array: np.ndarray,
                              patient_id: str, file_hash: str,
                              metadata: Dict) -> Path:
        """Create lossless TIFF"""
        tiff_dir = self.lossless_tiff_path / patient_id
        tiff_dir.mkdir(parents=True, exist_ok=True)

        output_path = tiff_dir / f"{file_hash[:12]}.tiff"

        if output_path.exists():
            return output_path

        if len(pixel_array.shape) > 2:
            pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

        tiff_metadata = {
            'ImageDescription': json.dumps({
                'patient_id': patient_id,
                'modality': metadata.get('modality', 'UNKNOWN'),
                'source_archive': metadata.get('source_archive', '')
            }),
            'Software': 'ADNI Selective ZIP Pipeline',
            'DateTime': datetime.now().isoformat()
        }

        tifffile.imwrite(
            output_path,
            pixel_array.astype(np.float32),
            compression='lzw',
            metadata=tiff_metadata,
            photometric='minisblack'
        )

        return output_path

    def _create_thumbnail(self, pixel_array: np.ndarray,
                          patient_id: str, file_hash: str) -> Path:
        """Create thumbnail"""
        thumb_dir = self.thumbnail_path / patient_id
        thumb_dir.mkdir(parents=True, exist_ok=True)

        output_path = thumb_dir / f"{file_hash[:8]}_t.jpg"

        if output_path.exists():
            return output_path

        if len(pixel_array.shape) > 2:
            pixel_array = pixel_array[:, :, pixel_array.shape[2] // 2]

        # Auto contrast
        p5, p95 = np.percentile(pixel_array, [5, 95])
        pixel_array = np.clip(pixel_array, p5, p95)

        if p95 > p5:
            pixel_array = ((pixel_array - p5) / (p95 - p5) * 255).astype(np.uint8)
        else:
            pixel_array = np.zeros_like(pixel_array, dtype=np.uint8)

        img = Image.fromarray(pixel_array)
        img.thumbnail((256, 256), Image.Resampling.LANCZOS)
        img.save(output_path, 'JPEG', quality=85, optimize=True)

        return output_path

    # Helper methods

    def _generate_file_hash(self, zf: zipfile.ZipFile, file_path: str) -> str:
        """Generate hash for file in ZIP"""
        info = zf.getinfo(file_path)
        hash_str = f"{file_path}_{info.file_size}_{info.CRC}"
        return hashlib.md5(hash_str.encode()).hexdigest()[:16]

    def _extract_patient_id(self, file_path: str) -> str:
        """Extract patient ID from path"""
        # ADNI pattern
        match = re.search(r'(\d{3}_S_\d{4})', file_path)
        if match:
            return match.group(1)

        # I-number pattern
        match = re.search(r'(I\d{6})', file_path)
        if match:
            return match.group(1)

        # Use parent directory
        parts = file_path.split('/')
        if len(parts) > 1:
            return parts[-2]

        return 'UNKNOWN'

    def _determine_modality(self, file_path: str) -> str:
        """Determine modality from path"""
        path_upper = file_path.upper()

        if any(x in path_upper for x in ['PET', 'FDG', 'AV45']):
            return 'PET'
        elif any(x in path_upper for x in ['MRI', 'T1', 'T2', 'FLAIR']):
            return 'MRI'
        elif 'CT' in path_upper:
            return 'CT'

        return 'UNKNOWN'

    def _get_processed_hashes(self) -> Set[str]:
        """Get already processed file hashes"""
        processed = set()
        with self.env.begin(db=self.processed_db) as txn:
            cursor = txn.cursor()
            for key, _ in cursor:
                processed.add(key.decode())
        return processed

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

    def _save_metadata(self, metadata: Dict):
        """Save metadata to JSON"""
        metadata_file = self.metadata_path / f"{metadata['image_hash']}.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

    def get_serving_info(self) -> Dict[str, Any]:
        """
        Get information about files available for serving

        Returns:
            Dictionary with serving information
        """
        info = {
            'serving_enabled': self.config.extract_for_serving,
            'serving_directory': str(self.config.serving_cache_dir) if self.config.serving_cache_dir else None,
            'served_files': 0,
            'served_patients': [],
            'total_size_gb': 0
        }

        if self.config.serving_cache_dir and self.config.serving_cache_dir.exists():
            # Count served files
            for patient_dir in self.config.serving_cache_dir.iterdir():
                if patient_dir.is_dir():
                    info['served_patients'].append(patient_dir.name)
                    for file_path in patient_dir.glob('*'):
                        info['served_files'] += 1
                        info['total_size_gb'] += file_path.stat().st_size / (1024 ** 3)

        return info


def execute_step5_with_zip_support(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute Step 5 with ZIP support based on config

    Args:
        config: Pipeline configuration dictionary

    Returns:
        Processing results
    """
    logger.info("\n" + "=" * 70)
    logger.info("STEP 5: IMAGE PROCESSING WITH ZIP SUPPORT")
    logger.info("=" * 70)

    start_time = time.time()

    # Initialize processor with config
    processor = SelectiveZipProcessor(config)

    # Log configuration
    logger.info(f"Processing mode: {processor.config.mode.value}")
    if processor.config.zip_numbers:
        logger.info(f"Processing ZIPs: {processor.config.zip_numbers}")
    elif processor.config.max_zips:
        logger.info(f"Processing first {processor.config.max_zips} ZIPs")

    # Process based on mode
    results = processor.process()

    # Add timing
    results['processing_time'] = time.time() - start_time

    # Log summary
    logger.info("\n" + "=" * 70)
    logger.info("PROCESSING SUMMARY")
    logger.info("=" * 70)

    if processor.config.mode == ProcessingMode.MIXED:
        logger.info(f"Extracted processing: {results.get('extracted_results', {}).get('processed', 0)} files")
        logger.info(f"ZIP processing: {results.get('zip_results', {}).get('processed', 0)} files")
        logger.info(f"Total processed: {results['combined']['total_processed']}")
        logger.info(f"Total failed: {results['combined']['total_failed']}")
    else:
        logger.info(f"Files processed: {results.get('processed', 0)}")
        logger.info(f"Files failed: {results.get('failed', 0)}")

    logger.info(f"Processing time: {results['processing_time']:.2f} seconds")

    # Check serving status
    if processor.config.extract_for_serving:
        serving_info = processor.get_serving_info()
        logger.info(f"\nServing cache:")
        logger.info(f"  Files extracted: {serving_info['served_files']}")
        logger.info(f"  Patients: {len(serving_info['served_patients'])}")
        logger.info(f"  Cache size: {serving_info['total_size_gb']:.2f} GB")

    return results


# Example configuration additions for updated_config.yaml
EXAMPLE_ZIP_CONFIG = """
# Add this section to your updated_config.yaml under image_storage:

image_storage:
  storage_path: "D:/Programming/Python/ADNIKnowledgeGraph/outputs/image_store"

  # ZIP Processing Configuration
  zip_processing:
    # Processing mode: 'extracted', 'zip_direct', or 'mixed'
    mode: 'zip_direct'

    # Directory containing ZIP files
    zip_directory: "D:/Programming/Python/ADNIKnowledgeGraph/inputs/zips"

    # Directory with extracted files (for 'extracted' mode)
    extracted_directory: "D:/Programming/Python/ADNIKnowledgeGraph/inputs/extracted"

    # Specific ZIP numbers to process (e.g., [1, 2, 3] for first 3)
    # Can be list: [1, 2, 3] or range string: "1-3" or "1,3,5-7"
    zip_numbers: [1, 2, 3]  # Process only first 3 ZIPs

    # OR use max_zips to process first N ZIPs
    # max_zips: 3

    # ZIP file patterns to match
    zip_patterns:
      - "mri_*.zip"
      - "pet_*.zip"

    # Extract files for DICOM serving (needed for viewers)
    extract_for_serving: true
    serving_cache_dir: "D:/Programming/Python/ADNIKnowledgeGraph/outputs/serving_cache"
"""

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Process medical images with ZIP support")
    parser.add_argument('--config', required=True, help='Path to config YAML file')
    parser.add_argument('--mode', choices=['extracted', 'zip_direct', 'mixed'],
                        help='Override config mode')
    parser.add_argument('--zip-numbers', nargs='+', type=int,
                        help='Override ZIP numbers to process')
    parser.add_argument('--info-only', action='store_true',
                        help='Show configuration info without processing')

    args = parser.parse_args()

    # Load config
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)

    # Override settings if specified
    if args.mode:
        if 'image_storage' not in config:
            config['image_storage'] = {}
        if 'zip_processing' not in config['image_storage']:
            config['image_storage']['zip_processing'] = {}
        config['image_storage']['zip_processing']['mode'] = args.mode

    if args.zip_numbers:
        config['image_storage']['zip_processing']['zip_numbers'] = args.zip_numbers

    if args.info_only:
        # Show configuration
        processor = SelectiveZipProcessor(config)

        print("\n📋 Configuration:")
        print(f"   Mode: {processor.config.mode.value}")
        print(f"   Storage path: {processor.config.storage_path}")

        if processor.available_zips:
            print(f"\n📦 Available ZIPs:")
            for num, path in sorted(processor.available_zips.items()):
                size_gb = path.stat().st_size / (1024 ** 3)
                print(f"   {num}: {path.name} ({size_gb:.2f} GB)")

        zips_to_process = processor.get_zips_to_process()
        if zips_to_process:
            print(f"\n✅ Will process {len(zips_to_process)} ZIPs:")
            for zip_path in zips_to_process:
                print(f"   - {zip_path.name}")
    else:
        # Execute processing
        results = execute_step5_with_zip_support(config)

        print(f"\n✅ Processing complete!")
        print(f"   Time: {results.get('processing_time', 0):.2f} seconds")