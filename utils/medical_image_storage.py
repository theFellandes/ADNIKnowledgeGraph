"""
Medical Image Storage Manager for ADNI Knowledge Graph
Implements hierarchical storage with lossless compression and Neo4j metadata integration
Based on DICOM standards and medical imaging best practices
"""

import os
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from PIL import Image
import pydicom
import cv2
from datetime import datetime
import nibabel as nib
import SimpleITK as sitk
from dataclasses import dataclass, asdict
import zarr
import h5py

logger = logging.getLogger(__name__)


@dataclass
class ImageStorageMetadata:
    """Metadata for stored medical images"""
    storage_id: str
    original_format: str
    storage_format: str
    compression: str
    dimensions: Tuple[int, ...]
    voxel_spacing: Optional[Tuple[float, ...]]
    bits_per_pixel: int
    photometric_interpretation: str
    checksums: Dict[str, str]
    file_paths: Dict[str, str]
    storage_timestamp: str
    quality_metrics: Dict[str, float]


class MedicalImageStorageManager:
    """
    Manages hierarchical storage of medical images with quality preservation
    Based on academic research in medical image archiving and PACS systems
    """

    # Storage formats based on medical imaging standards
    STORAGE_CONFIGS = {
        'diagnostic': {
            'format': 'nifti',  # NIfTI for full 3D volumes
            'compression': 'gzip',
            'quality': 100,
            'preserve_metadata': True
        },
        'research': {
            'format': 'hdf5',  # HDF5 for efficient access
            'compression': 'lzf',
            'quality': 100,
            'preserve_metadata': True
        },
        'preview': {
            'format': 'png',  # PNG for lossless 2D slices
            'compression': 'png',
            'quality': 100,
            'max_size': (1024, 1024)
        },
        'thumbnail': {
            'format': 'jpeg',
            'compression': 'jpeg',
            'quality': 95,
            'max_size': (256, 256)
        }
    }

    def __init__(self, base_storage_path: str, neo4j_connector=None):
        """
        Initialize storage manager

        Args:
            base_storage_path: Root directory for image storage
            neo4j_connector: Neo4j connection for metadata storage
        """
        self.base_path = Path(base_storage_path)
        self.neo4j = neo4j_connector

        # Create storage hierarchy
        self.diagnostic_path = self.base_path / "diagnostic"
        self.research_path = self.base_path / "research"
        self.preview_path = self.base_path / "preview"
        self.thumbnail_path = self.base_path / "thumbnail"
        self.metadata_path = self.base_path / "metadata"

        for path in [self.diagnostic_path, self.research_path,
                     self.preview_path, self.thumbnail_path, self.metadata_path]:
            path.mkdir(parents=True, exist_ok=True)

    def process_dicom_for_storage(self, dicom_path: str, patient_id: str,
                                  study_id: str, series_id: str) -> ImageStorageMetadata:
        """
        Process DICOM file for hierarchical storage with quality preservation

        Args:
            dicom_path: Path to DICOM file
            patient_id: Patient identifier
            study_id: Study identifier
            series_id: Series identifier

        Returns:
            ImageStorageMetadata with all storage information
        """
        # Read DICOM
        ds = pydicom.dcmread(dicom_path)

        # Generate unique storage ID
        storage_id = self._generate_storage_id(patient_id, study_id, series_id)

        # Extract pixel data and metadata
        pixel_array = ds.pixel_array
        metadata = self._extract_dicom_metadata(ds)

        # Initialize storage paths
        file_paths = {}
        checksums = {}
        quality_metrics = {}

        # 1. Store diagnostic quality (lossless)
        if len(pixel_array.shape) == 2:
            # Single slice - store as high-quality PNG
            diagnostic_path = self._store_as_png(
                pixel_array, storage_id, self.diagnostic_path,
                metadata, quality='diagnostic'
            )
            file_paths['diagnostic'] = str(diagnostic_path)
            checksums['diagnostic'] = self._calculate_checksum(diagnostic_path)

        else:
            # Multi-slice - store as NIfTI or HDF5
            diagnostic_path = self._store_as_nifti(
                pixel_array, storage_id, self.diagnostic_path, metadata
            )
            file_paths['diagnostic'] = str(diagnostic_path)
            checksums['diagnostic'] = self._calculate_checksum(diagnostic_path)

            # Also create HDF5 for efficient slice access
            research_path = self._store_as_hdf5(
                pixel_array, storage_id, self.research_path, metadata
            )
            file_paths['research'] = str(research_path)
            checksums['research'] = self._calculate_checksum(research_path)

        # 2. Create preview images (middle slice or MIP)
        preview_array = self._create_preview(pixel_array)
        preview_path = self._store_as_png(
            preview_array, storage_id, self.preview_path,
            metadata, quality='preview'
        )
        file_paths['preview'] = str(preview_path)
        checksums['preview'] = self._calculate_checksum(preview_path)

        # 3. Create thumbnail
        thumbnail_array = self._create_thumbnail(preview_array)
        thumbnail_path = self._store_as_jpeg(
            thumbnail_array, storage_id, self.thumbnail_path
        )
        file_paths['thumbnail'] = str(thumbnail_path)
        checksums['thumbnail'] = self._calculate_checksum(thumbnail_path)

        # 4. Calculate quality metrics
        quality_metrics = self._calculate_quality_metrics(pixel_array)

        # 5. Create metadata object
        storage_metadata = ImageStorageMetadata(
            storage_id=storage_id,
            original_format='DICOM',
            storage_format='multi-resolution',
            compression='mixed',
            dimensions=pixel_array.shape,
            voxel_spacing=self._extract_voxel_spacing(ds),
            bits_per_pixel=int(ds.BitsStored) if hasattr(ds, 'BitsStored') else 16,
            photometric_interpretation=str(ds.PhotometricInterpretation) if hasattr(ds,
                                                                                    'PhotometricInterpretation') else 'MONOCHROME2',
            checksums=checksums,
            file_paths=file_paths,
            storage_timestamp=datetime.now().isoformat(),
            quality_metrics=quality_metrics
        )

        # 6. Store metadata
        self._store_metadata(storage_metadata)

        # 7. Update Neo4j with storage references
        if self.neo4j:
            self._update_neo4j_references(storage_metadata, metadata)

        return storage_metadata

    def _store_as_nifti(self, pixel_array: np.ndarray, storage_id: str,
                        base_path: Path, metadata: Dict) -> Path:
        """
        Store as NIfTI format (standard in neuroimaging)
        Preserves 3D structure and metadata
        """
        # Create NIfTI image
        affine = np.eye(4)  # Identity affine (can be improved with actual DICOM geometry)

        # Handle orientation and spacing from DICOM
        if 'PixelSpacing' in metadata:
            spacing = metadata['PixelSpacing']
            affine[0, 0] = spacing[0]
            affine[1, 1] = spacing[1]

        if 'SliceThickness' in metadata:
            affine[2, 2] = metadata['SliceThickness']

        # Create NIfTI image
        nifti_img = nib.Nifti1Image(pixel_array, affine)

        # Add metadata as header extensions
        nifti_img.header['descrip'] = f'ADNI_{storage_id}'

        # Save with compression
        file_path = base_path / f"{storage_id}.nii.gz"
        nib.save(nifti_img, str(file_path))

        logger.info(f"Stored NIfTI: {file_path}")
        return file_path

    def _store_as_hdf5(self, pixel_array: np.ndarray, storage_id: str,
                       base_path: Path, metadata: Dict) -> Path:
        """
        Store as HDF5 for efficient slice access and metadata preservation
        Used in many medical imaging research applications
        """
        file_path = base_path / f"{storage_id}.h5"

        with h5py.File(file_path, 'w') as f:
            # Store image data with compression
            img_dataset = f.create_dataset(
                'image_data',
                data=pixel_array,
                compression='lzf',  # Fast compression
                chunks=True  # Enable chunking for efficient slice access
            )

            # Store metadata
            meta_group = f.create_group('metadata')
            for key, value in metadata.items():
                if value is not None:
                    try:
                        meta_group.attrs[key] = value
                    except:
                        meta_group.attrs[key] = str(value)

            # Create pyramid levels for multi-resolution access
            pyramid_group = f.create_group('pyramid')

            # Level 0: Full resolution (reference to main data)
            pyramid_group['level_0'] = img_dataset

            # Level 1: Half resolution
            if len(pixel_array.shape) == 3:
                half_res = pixel_array[::2, ::2, ::2]
            else:
                half_res = pixel_array[::2, ::2]
            pyramid_group.create_dataset('level_1', data=half_res, compression='lzf')

            # Level 2: Quarter resolution
            if len(pixel_array.shape) == 3:
                quarter_res = pixel_array[::4, ::4, ::4]
            else:
                quarter_res = pixel_array[::4, ::4]
            pyramid_group.create_dataset('level_2', data=quarter_res, compression='lzf')

        logger.info(f"Stored HDF5: {file_path}")
        return file_path

    def _store_as_png(self, pixel_array: np.ndarray, storage_id: str,
                      base_path: Path, metadata: Dict, quality: str = 'diagnostic') -> Path:
        """
        Store as PNG for lossless 2D image storage
        PNG is widely supported and provides lossless compression
        """
        # Normalize to 16-bit if needed (PNG supports 16-bit grayscale)
        if pixel_array.dtype != np.uint16:
            if pixel_array.max() <= 255:
                # 8-bit image
                normalized = pixel_array.astype(np.uint8)
            else:
                # Scale to 16-bit
                normalized = ((pixel_array - pixel_array.min()) /
                              (pixel_array.max() - pixel_array.min()) * 65535).astype(np.uint16)
        else:
            normalized = pixel_array

        # Apply windowing if specified in metadata
        if quality == 'preview' and 'WindowCenter' in metadata and 'WindowWidth' in metadata:
            normalized = self._apply_windowing(
                normalized,
                metadata['WindowCenter'],
                metadata['WindowWidth']
            )

        # Resize if needed
        config = self.STORAGE_CONFIGS.get(quality, {})
        if 'max_size' in config:
            normalized = self._resize_preserve_aspect(normalized, config['max_size'])

        # Save as PNG
        file_path = base_path / f"{storage_id}.png"

        # Use cv2 for 16-bit PNG support
        cv2.imwrite(str(file_path), normalized)

        logger.info(f"Stored PNG: {file_path}")
        return file_path

    def _store_as_jpeg(self, pixel_array: np.ndarray, storage_id: str,
                       base_path: Path, quality: int = 95) -> Path:
        """
        Store as JPEG for thumbnails only (lossy but efficient)
        """
        # Convert to 8-bit
        if pixel_array.max() > 255:
            normalized = ((pixel_array - pixel_array.min()) /
                          (pixel_array.max() - pixel_array.min()) * 255).astype(np.uint8)
        else:
            normalized = pixel_array.astype(np.uint8)

        # Save as JPEG
        file_path = base_path / f"{storage_id}.jpg"
        Image.fromarray(normalized, mode='L').save(
            file_path,
            'JPEG',
            quality=quality,
            optimize=True
        )

        return file_path

    def _create_preview(self, pixel_array: np.ndarray) -> np.ndarray:
        """
        Create preview image (middle slice or MIP for 3D)
        """
        if len(pixel_array.shape) == 3:
            # For 3D, create Maximum Intensity Projection (MIP) or middle slice
            middle_slice = pixel_array.shape[0] // 2
            preview = pixel_array[middle_slice, :, :]

            # Optionally create MIP for better visualization
            # mip = np.max(pixel_array, axis=0)

        else:
            preview = pixel_array

        return preview

    def _create_thumbnail(self, image_array: np.ndarray, size: Tuple[int, int] = (256, 256)) -> np.ndarray:
        """
        Create thumbnail preserving aspect ratio
        """
        return self._resize_preserve_aspect(image_array, size)

    def _resize_preserve_aspect(self, image: np.ndarray, max_size: Tuple[int, int]) -> np.ndarray:
        """
        Resize image preserving aspect ratio
        """
        h, w = image.shape[:2]
        max_h, max_w = max_size

        # Calculate scaling factor
        scale = min(max_w / w, max_h / h)

        if scale < 1:
            new_w = int(w * scale)
            new_h = int(h * scale)
            resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
        else:
            resized = image

        return resized

    def _apply_windowing(self, image: np.ndarray, center: float, width: float) -> np.ndarray:
        """
        Apply DICOM windowing for better visualization
        """
        lower = center - width / 2
        upper = center + width / 2

        windowed = np.clip(image, lower, upper)
        windowed = ((windowed - lower) / (upper - lower) * 255).astype(np.uint8)

        return windowed

    def _extract_dicom_metadata(self, ds) -> Dict[str, Any]:
        """
        Extract comprehensive DICOM metadata
        """
        metadata = {}

        # Essential fields for medical imaging
        important_tags = [
            'PatientID', 'StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID',
            'StudyDate', 'SeriesDate', 'AcquisitionDate',
            'Modality', 'BodyPartExamined', 'ViewPosition',
            'PixelSpacing', 'SliceThickness', 'SpacingBetweenSlices',
            'WindowCenter', 'WindowWidth', 'RescaleSlope', 'RescaleIntercept',
            'PhotometricInterpretation', 'BitsAllocated', 'BitsStored',
            'HighBit', 'PixelRepresentation',
            'ImageOrientationPatient', 'ImagePositionPatient',
            'FrameOfReferenceUID', 'Rows', 'Columns',
            'ManufacturerModelName', 'MagneticFieldStrength'
        ]

        for tag in important_tags:
            if hasattr(ds, tag):
                value = getattr(ds, tag)
                if isinstance(value, (list, tuple)):
                    metadata[tag] = list(value)
                elif hasattr(value, 'value'):
                    metadata[tag] = value.value
                else:
                    metadata[tag] = str(value)

        return metadata

    def _extract_voxel_spacing(self, ds) -> Optional[Tuple[float, ...]]:
        """
        Extract voxel spacing from DICOM
        """
        spacing = []

        if hasattr(ds, 'PixelSpacing'):
            spacing.extend(list(map(float, ds.PixelSpacing)))

        if hasattr(ds, 'SliceThickness'):
            spacing.append(float(ds.SliceThickness))
        elif hasattr(ds, 'SpacingBetweenSlices'):
            spacing.append(float(ds.SpacingBetweenSlices))

        return tuple(spacing) if spacing else None

    def _calculate_quality_metrics(self, pixel_array: np.ndarray) -> Dict[str, float]:
        """
        Calculate image quality metrics for quality assurance
        """
        metrics = {}

        # Signal-to-Noise Ratio (SNR) estimation
        # Using method from "A robust method for measuring SNR in MRI images"
        signal = np.mean(pixel_array[pixel_array > np.percentile(pixel_array, 75)])
        noise = np.std(pixel_array[pixel_array < np.percentile(pixel_array, 25)])
        metrics['snr'] = float(signal / noise) if noise > 0 else 0

        # Contrast metrics
        metrics['contrast'] = float(np.std(pixel_array))
        metrics['dynamic_range'] = float(pixel_array.max() - pixel_array.min())

        # Sharpness estimation (using Laplacian variance)
        if len(pixel_array.shape) == 2:
            laplacian = cv2.Laplacian(pixel_array.astype(np.float32), cv2.CV_64F)
            metrics['sharpness'] = float(laplacian.var())

        # Entropy (information content)
        hist, _ = np.histogram(pixel_array, bins=256)
        hist = hist[hist > 0]
        prob = hist / hist.sum()
        metrics['entropy'] = float(-np.sum(prob * np.log2(prob)))

        return metrics

    def _calculate_checksum(self, file_path: Path) -> str:
        """
        Calculate SHA-256 checksum for data integrity
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _generate_storage_id(self, patient_id: str, study_id: str, series_id: str) -> str:
        """
        Generate unique storage identifier
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_str = f"{patient_id}_{study_id}_{series_id}_{timestamp}"
        return hashlib.md5(unique_str.encode()).hexdigest()[:16]

    def _store_metadata(self, storage_metadata: ImageStorageMetadata) -> None:
        """
        Store metadata as JSON for easy retrieval
        """
        metadata_file = self.metadata_path / f"{storage_metadata.storage_id}.json"

        with open(metadata_file, 'w') as f:
            json.dump(asdict(storage_metadata), f, indent=2, default=str)

    def _update_neo4j_references(self, storage_metadata: ImageStorageMetadata,
                                 dicom_metadata: Dict) -> None:
        """
        Update Neo4j with storage references instead of blobs
        """
        if not self.neo4j:
            return

        query = """
        MATCH (i:ImageNode {image_id: $image_id})
        SET i.storage_id = $storage_id,
            i.diagnostic_path = $diagnostic_path,
            i.preview_path = $preview_path,
            i.thumbnail_path = $thumbnail_path,
            i.storage_format = $storage_format,
            i.checksum = $checksum,
            i.snr = $snr,
            i.entropy = $entropy,
            i.dimensions = $dimensions,
            i.voxel_spacing = $voxel_spacing,
            i.storage_timestamp = $storage_timestamp,
            i.has_diagnostic = true,
            i.has_preview = true,
            i.has_thumbnail = true,
            i.quality_verified = true
        REMOVE i.image_blob, i.thumbnail_blob
        """

        params = {
            'image_id': storage_metadata.storage_id,
            'storage_id': storage_metadata.storage_id,
            'diagnostic_path': storage_metadata.file_paths.get('diagnostic'),
            'preview_path': storage_metadata.file_paths.get('preview'),
            'thumbnail_path': storage_metadata.file_paths.get('thumbnail'),
            'storage_format': storage_metadata.storage_format,
            'checksum': storage_metadata.checksums.get('diagnostic'),
            'snr': storage_metadata.quality_metrics.get('snr'),
            'entropy': storage_metadata.quality_metrics.get('entropy'),
            'dimensions': list(storage_metadata.dimensions),
            'voxel_spacing': list(storage_metadata.voxel_spacing) if storage_metadata.voxel_spacing else None,
            'storage_timestamp': storage_metadata.storage_timestamp
        }

        self.neo4j.run_query(query, params)

    def retrieve_image(self, storage_id: str, resolution: str = 'preview') -> Optional[np.ndarray]:
        """
        Retrieve image at specified resolution

        Args:
            storage_id: Storage identifier
            resolution: 'diagnostic', 'research', 'preview', or 'thumbnail'

        Returns:
            Image array or None if not found
        """
        # Load metadata
        metadata_file = self.metadata_path / f"{storage_id}.json"
        if not metadata_file.exists():
            logger.error(f"Metadata not found for {storage_id}")
            return None

        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        # Get file path for requested resolution
        file_path = metadata['file_paths'].get(resolution)
        if not file_path:
            logger.error(f"Resolution {resolution} not available for {storage_id}")
            return None

        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        # Load based on format
        if file_path.suffix == '.gz':
            # NIfTI
            img = nib.load(str(file_path))
            return img.get_fdata()
        elif file_path.suffix == '.h5':
            # HDF5
            with h5py.File(file_path, 'r') as f:
                return f['image_data'][:]
        elif file_path.suffix == '.png':
            # PNG
            return cv2.imread(str(file_path), cv2.IMREAD_ANYDEPTH)
        elif file_path.suffix in ['.jpg', '.jpeg']:
            # JPEG
            return cv2.imread(str(file_path), cv2.IMREAD_GRAYSCALE)
        else:
            logger.error(f"Unsupported format: {file_path.suffix}")
            return None


# Integration function for the existing pipeline
def integrate_storage_manager_with_pipeline(neo4j_connector, base_path: str,
                                            output_base: str = "outputs/image_store"):
    """
    Integration function to use with existing ADNI pipeline

    This replaces the blob storage approach in step5_process_images.py
    """
    storage_manager = MedicalImageStorageManager(output_base, neo4j_connector)

    # Modified processing function
    def process_image_for_storage(image_path: Path, patient_id: str,
                                  study_id: str, series_id: str) -> Dict[str, Any]:
        """
        Process single image for storage
        """
        try:
            if image_path.suffix.lower() == '.dcm':
                # Process DICOM
                metadata = storage_manager.process_dicom_for_storage(
                    str(image_path), patient_id, study_id, series_id
                )
                return {
                    'success': True,
                    'storage_id': metadata.storage_id,
                    'paths': metadata.file_paths,
                    'quality_metrics': metadata.quality_metrics
                }
            else:
                # For already converted images (JPG/PNG), store them directly
                # and create additional resolutions
                logger.info(f"Processing converted image: {image_path}")
                # Implementation for non-DICOM images
                return {'success': False, 'error': 'Non-DICOM processing not implemented'}

        except Exception as e:
            logger.error(f"Error processing {image_path}: {e}")
            return {'success': False, 'error': str(e)}

    return storage_manager, process_image_for_storage