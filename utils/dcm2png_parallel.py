"""
DICOM to PNG Converter with Incremental Processing and Quality Preservation
Maintains folder structure and generates metadata for Elasticsearch
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
import logging
import shutil
import concurrent.futures
from tqdm import tqdm
import warnings

# For DICOM conversion
try:
    import pydicom
    from PIL import Image
    import numpy as np
    DICOM_AVAILABLE = True

    # Suppress DICOM warnings about invalid VR values
    import pydicom.config
    pydicom.config.settings.reading_validation_mode = pydicom.config.IGNORE

    # Also suppress specific warnings
    warnings.filterwarnings('ignore', message='Invalid value for VR')

except ImportError:
    DICOM_AVAILABLE = False
    print("Warning: pydicom or PIL not available. Install with: pip install pydicom pillow")

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class DICOMtoFSConverter:
    """Convert DICOM images to PNG with incremental processing and quality preservation"""

    def __init__(self, input_dir: str, output_dir: str, modality: str = 'UNKNOWN',
                 skip_if_exists: bool = True, max_workers: int = 4):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.modality = modality  # MRI or PET
        self.skip_if_exists = skip_if_exists
        self.max_workers = max_workers

        # Output directories
        self.png_dir = self.output_dir / "png_images" / modality
        self.thumbnail_dir = self.output_dir / "thumbnails" / modality
        self.metadata_dir = self.output_dir / "metadata" / modality

        # Create output directories
        self.png_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        self.stats = {
            'total_files': 0,
            'converted': 0,
            'skipped': 0,
            'errors': 0
        }

    def convert_all(self) -> Dict[str, int]:
        """Convert all DICOM files maintaining directory structure"""
        logger.info(f"Starting incremental conversion from: {self.input_dir}")
        logger.info(f"Output directory: {self.output_dir}")
        logger.info(f"Modality: {self.modality}")
        logger.info(f"Skip existing: {self.skip_if_exists}")

        if not DICOM_AVAILABLE:
            logger.error("DICOM libraries not available. Cannot proceed.")
            return self.stats

        # Find all DICOM files
        dicom_files = self._find_dicom_files()
        self.stats['total_files'] = len(dicom_files)

        if not dicom_files:
            logger.warning(f"No DICOM files found in {self.input_dir}")
            return self.stats

        logger.info(f"Found {len(dicom_files)} DICOM files to process")

        # Process files in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._process_single_file, dcm_file): dcm_file
                for dcm_file in dicom_files
            }

            # Process with progress bar
            for future in tqdm(concurrent.futures.as_completed(futures),
                              total=len(dicom_files),
                              desc=f"Converting {self.modality} DICOMs"):
                dcm_file = futures[future]
                try:
                    result = future.result(timeout=30)
                    if result == 'converted':
                        self.stats['converted'] += 1
                    elif result == 'skipped':
                        self.stats['skipped'] += 1
                    else:
                        self.stats['errors'] += 1
                except Exception as e:
                    logger.error(f"Error processing {dcm_file}: {e}")
                    self.stats['errors'] += 1

        self._log_summary()
        return self.stats

    def _find_dicom_files(self) -> List[Path]:
        """Find all DICOM files in input directory"""
        dicom_files = []

        # Common DICOM extensions
        extensions = ['.dcm', '.DCM', '.dicom', '.DICOM']

        # Find files with DICOM extensions
        for ext in extensions:
            dicom_files.extend(list(self.input_dir.rglob(f'*{ext}')))

        # Also find files without extension that might be DICOM
        for file in self.input_dir.rglob('*'):
            if file.is_file() and not file.suffix and self._is_dicom_file(file):
                dicom_files.append(file)

        return dicom_files

    def _is_dicom_file(self, file_path: Path) -> bool:
        """Check if a file is a DICOM file by checking header"""
        try:
            with open(file_path, 'rb') as f:
                # Check for DICOM preamble and prefix
                f.seek(128)
                return f.read(4) == b'DICM'
        except:
            return False

    def _process_single_file(self, dicom_path: Path) -> str:
        """Process a single DICOM file"""
        try:
            # Generate output paths preserving folder structure
            relative_path = dicom_path.relative_to(self.input_dir)
            path_parts = relative_path.parts

            # Extract patient ID from path
            patient_id = self._extract_patient_id(path_parts)
            if not patient_id:
                patient_id = "UNKNOWN"

            # Generate unique identifier for this image
            image_hash = self._generate_image_hash(dicom_path, patient_id)

            # Check if already processed (incremental mode)
            metadata_file = self.metadata_dir / patient_id / f"{image_hash}_metadata.json"

            if self.skip_if_exists and metadata_file.exists():
                # Verify output files also exist
                metadata = json.loads(metadata_file.read_text())
                png_path = Path(metadata.get('png_path', ''))
                thumb_path = Path(metadata.get('thumbnail_path', ''))

                if png_path.exists() and thumb_path.exists():
                    return 'skipped'

            # Read DICOM file
            try:
                ds = pydicom.dcmread(str(dicom_path), force=True)
            except Exception as e:
                logger.warning(f"Could not read DICOM file {dicom_path}: {e}")
                return 'error'

            # Extract metadata
            metadata = self._extract_dicom_metadata(ds, dicom_path, patient_id)

            # Convert pixel data to PNG (lossless)
            try:
                png_path = self._convert_to_png(ds, patient_id, image_hash)
            except Exception as e:
                logger.error(f"Failed to convert {dicom_path} to PNG: {e}")
                return 'error'

            # Create thumbnail
            try:
                thumb_path = self._create_thumbnail(png_path, patient_id, image_hash)
            except Exception as e:
                logger.error(f"Failed to create thumbnail for {png_path}: {e}")
                # Continue even if thumbnail fails
                thumb_path = Path('')

            # Update metadata with file paths
            metadata['image_hash'] = image_hash
            metadata['dcm_path'] = str(dicom_path)
            metadata['png_path'] = str(png_path)
            metadata['thumbnail_path'] = str(thumb_path)
            metadata['conversion_date'] = datetime.now().isoformat()

            # Save metadata
            self._save_metadata(metadata, patient_id, image_hash)

            return 'converted'

        except Exception as e:
            logger.error(f"Error processing {dicom_path}: {e}")
            return 'error'

    def _extract_patient_id(self, path_parts: tuple) -> Optional[str]:
        """Extract patient ID from path structure"""
        # Look for common patterns in path
        for part in path_parts:
            # ADNI pattern: contains patient ID like "002_S_0413"
            if '_S_' in part:
                return part
            # Generic pattern: first directory after root
            if part and not part.startswith('.'):
                return part.replace(' ', '_').replace('/', '_')

        return path_parts[0] if path_parts else None

    def _generate_image_hash(self, dicom_path: Path, patient_id: str) -> str:
        """Generate unique hash for image based on path and patient"""
        hash_input = f"{patient_id}_{dicom_path.stem}_{dicom_path.stat().st_size}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _extract_dicom_metadata(self, ds: pydicom.Dataset, dicom_path: Path,
                                patient_id: str) -> Dict[str, Any]:
        """Extract comprehensive metadata from DICOM"""
        metadata = {
            'patient_id': patient_id,
            'modality': self.modality,
            'file_name': dicom_path.name,
            'file_size': dicom_path.stat().st_size
        }

        # Essential DICOM fields
        dicom_fields = {
            'StudyDate': 'study_date',
            'StudyTime': 'study_time',
            'SeriesDescription': 'series_description',
            'SeriesNumber': 'series_number',
            'InstanceNumber': 'instance_number',
            'StudyInstanceUID': 'study_id',
            'SeriesInstanceUID': 'series_id',
            'SOPInstanceUID': 'sop_instance_uid',
            'PatientAge': 'patient_age',
            'PatientSex': 'patient_sex',
            'Manufacturer': 'manufacturer',
            'ManufacturerModelName': 'model_name',
            'SliceThickness': 'slice_thickness',
            'PixelSpacing': 'pixel_spacing',
            'Rows': 'rows',
            'Columns': 'columns'
        }

        # Extract available fields
        dicom_metadata = {}
        for dicom_field, metadata_field in dicom_fields.items():
            if hasattr(ds, dicom_field):
                value = getattr(ds, dicom_field)
                if value is not None:
                    # Convert to serializable format
                    if hasattr(value, 'value'):
                        value = value.value
                    if isinstance(value, (list, tuple)):
                        value = list(value)
                    elif not isinstance(value, (str, int, float, bool)):
                        value = str(value)
                    dicom_metadata[metadata_field] = value

        metadata['dicom_metadata'] = dicom_metadata

        # Get image dimensions
        if hasattr(ds, 'pixel_array'):
            try:
                shape = ds.pixel_array.shape
                metadata['original_resolution'] = [int(shape[1]), int(shape[0])] if len(shape) >= 2 else [0, 0]
            except Exception as e:
                logger.warning(f"Could not get pixel array shape: {e}")
                metadata['original_resolution'] = [
                    int(dicom_metadata.get('columns', 0)),
                    int(dicom_metadata.get('rows', 0))
                ]
        else:
            metadata['original_resolution'] = [
                int(dicom_metadata.get('columns', 0)),
                int(dicom_metadata.get('rows', 0))
            ]

        # Generate naming convention
        study_date = dicom_metadata.get('study_date', 'unknown')
        series_num = dicom_metadata.get('series_number', '0')
        instance_num = dicom_metadata.get('instance_number', '0')
        metadata['naming_convention'] = f"{patient_id}_{study_date}_{series_num}_{instance_num}"

        return metadata

    def _convert_to_png(self, ds: pydicom.Dataset, patient_id: str, image_hash: str) -> Path:
        """Convert DICOM to PNG with lossless quality"""
        # Create output directory for patient
        patient_png_dir = self.png_dir / patient_id
        patient_png_dir.mkdir(parents=True, exist_ok=True)

        # Output file path
        png_filename = f"{image_hash}.png"
        png_path = patient_png_dir / png_filename

        # Get pixel array
        try:
            pixel_array = ds.pixel_array
        except Exception as e:
            logger.error(f"Could not extract pixel array: {e}")
            raise

        # Handle different bit depths properly to preserve quality
        if pixel_array.dtype != np.uint8:
            # Preserve full dynamic range for 16-bit images
            if 'WindowCenter' in ds and 'WindowWidth' in ds:
                # Apply DICOM windowing if available
                try:
                    window_center = float(ds.WindowCenter if not hasattr(ds.WindowCenter, '__iter__') else ds.WindowCenter[0])
                    window_width = float(ds.WindowWidth if not hasattr(ds.WindowWidth, '__iter__') else ds.WindowWidth[0])

                    img_min = window_center - window_width / 2
                    img_max = window_center + window_width / 2

                    pixel_array = np.clip(pixel_array, img_min, img_max)
                    pixel_array = ((pixel_array - img_min) / (img_max - img_min) * 65535).astype(np.uint16)

                    # Save as 16-bit PNG for full quality preservation
                    img = Image.fromarray(pixel_array, mode='I;16')
                except Exception as e:
                    logger.warning(f"Could not apply windowing: {e}, using auto-scaling")
                    # Fallback to auto-scaling
                    pixel_min = pixel_array.min()
                    pixel_max = pixel_array.max()

                    if pixel_max > pixel_min:
                        pixel_array = ((pixel_array - pixel_min) / (pixel_max - pixel_min) * 65535).astype(np.uint16)
                    else:
                        pixel_array = pixel_array.astype(np.uint16)

                    img = Image.fromarray(pixel_array, mode='I;16')
            else:
                # Normalize to full 16-bit range without windowing
                pixel_min = pixel_array.min()
                pixel_max = pixel_array.max()

                if pixel_max > pixel_min:
                    pixel_array = ((pixel_array - pixel_min) / (pixel_max - pixel_min) * 65535).astype(np.uint16)
                else:
                    pixel_array = pixel_array.astype(np.uint16)

                img = Image.fromarray(pixel_array, mode='I;16')
        else:
            # 8-bit image
            img = Image.fromarray(pixel_array, mode='L')

        # Save as PNG (lossless compression)
        img.save(str(png_path), 'PNG', compress_level=1)  # Low compression for speed

        return png_path

    def _create_thumbnail(self, png_path: Path, patient_id: str, image_hash: str) -> Path:
        """Create thumbnail from PNG image"""
        # Create output directory for patient thumbnails
        patient_thumb_dir = self.thumbnail_dir / patient_id
        patient_thumb_dir.mkdir(parents=True, exist_ok=True)

        # Output file path
        thumb_filename = f"{image_hash}_thumb.png"
        thumb_path = patient_thumb_dir / thumb_filename

        # Open the full resolution PNG
        with Image.open(png_path) as img:
            # Convert to 8-bit for thumbnail
            if img.mode == 'I;16':
                # Convert 16-bit to 8-bit for thumbnail
                img_array = np.array(img)
                img_array = (img_array / 256).astype(np.uint8)
                img = Image.fromarray(img_array, mode='L')

            # Create thumbnail (reduced resolution)
            img.thumbnail((128, 128), Image.Resampling.LANCZOS)

            # Save thumbnail
            img.save(str(thumb_path), 'PNG')

        return thumb_path

    def _save_metadata(self, metadata: Dict[str, Any], patient_id: str, image_hash: str):
        """Save metadata to JSON file"""
        # Create patient metadata directory
        patient_metadata_dir = self.metadata_dir / patient_id
        patient_metadata_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata
        metadata_file = patient_metadata_dir / f"{image_hash}_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)

        # Also get PNG resolution
        if 'png_path' in metadata and Path(metadata['png_path']).exists():
            with Image.open(metadata['png_path']) as img:
                metadata['png_resolution'] = list(img.size)

        # Get thumbnail resolution
        if 'thumbnail_path' in metadata and Path(metadata['thumbnail_path']).exists():
            with Image.open(metadata['thumbnail_path']) as img:
                metadata['thumbnail_resolution'] = list(img.size)

        # Save updated metadata
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)

    def _log_summary(self):
        """Log conversion summary"""
        logger.info("\n" + "="*60)
        logger.info("DICOM TO PNG CONVERSION SUMMARY")
        logger.info("="*60)
        logger.info(f"Modality: {self.modality}")
        logger.info(f"Total DICOM files found: {self.stats['total_files']}")
        logger.info(f"Successfully converted: {self.stats['converted']}")
        logger.info(f"Skipped (already exist): {self.stats['skipped']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"Output directory: {self.output_dir}")
        logger.info("="*60)


def drain_new_dicoms(new_mri_path: Path, new_pet_path: Path,
                    mri_dcm_path: Path, pet_dcm_path: Path) -> Dict[str, int]:
    """
    Move new DICOM files from New_MRI/New_PET to MRI_DCM/PET_DCM
    preserving folder structure
    """
    moved = {"MRI": 0, "PET": 0}

    for src_root, dst_root, key in [
        (new_mri_path, mri_dcm_path, "MRI"),
        (new_pet_path, pet_dcm_path, "PET")
    ]:
        if not src_root.exists():
            logger.warning(f"Source directory {src_root} does not exist")
            continue

        # Move files preserving structure
        for file in src_root.rglob("*"):
            if not file.is_file():
                continue

            # Calculate relative path
            rel_path = file.relative_to(src_root)
            target = dst_root / rel_path

            # Create target directory if needed
            target.parent.mkdir(parents=True, exist_ok=True)

            # Move file if it doesn't exist in target
            if not target.exists():
                shutil.move(str(file), str(target))
                moved[key] += 1
                logger.debug(f"Moved: {rel_path}")
            else:
                # Remove from source if already exists in target
                file.unlink()
                logger.debug(f"File already exists, removed from source: {rel_path}")

        # Clean up empty directories
        for dirpath in sorted(src_root.rglob("*"), reverse=True):
            if dirpath.is_dir() and dirpath != src_root:
                try:
                    dirpath.rmdir()  # Only removes if empty
                except OSError:
                    pass

    logger.info(f"Moved {moved['MRI']} MRI and {moved['PET']} PET files")
    return moved


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Incremental DICOM to PNG converter")
    parser.add_argument("--input", required=True, help="Input directory with DICOM files")
    parser.add_argument("--output", required=True, help="Output directory for PNG files")
    parser.add_argument("--modality", default="UNKNOWN", choices=["MRI", "PET", "CT", "UNKNOWN"],
                       help="Imaging modality")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    parser.add_argument("--force", action="store_true", help="Force reconversion of existing files")

    args = parser.parse_args()

    converter = DICOMtoFSConverter(
        input_dir=args.input,
        output_dir=args.output,
        modality=args.modality,
        skip_if_exists=not args.force,
        max_workers=args.workers
    )

    converter.convert_all()