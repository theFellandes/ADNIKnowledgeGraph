"""
Image processing utilities for DICOM and standard image formats
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
from PIL import Image
import pydicom
from io import BytesIO

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Process medical images for storage in Neo4j"""

    def __init__(self, max_image_size: Tuple[int, int] = (512, 512),
                 thumbnail_size: Tuple[int, int] = (128, 128),
                 jpeg_quality: int = 85):
        """
        Initialize image processor

        Args:
            max_image_size: Maximum size for full images
            thumbnail_size: Size for thumbnails
            jpeg_quality: JPEG compression quality (0-100)
        """
        self.max_image_size = max_image_size
        self.thumbnail_size = thumbnail_size
        self.jpeg_quality = jpeg_quality

    def process_dicom(self, dicom_path: str) -> Dict[str, Any]:
        """
        Process DICOM file and extract metadata and image

        Args:
            dicom_path: Path to DICOM file

        Returns:
            Dictionary with metadata, image blob, and thumbnail
        """
        try:
            # Read DICOM
            ds = pydicom.dcmread(dicom_path)

            # Extract metadata
            metadata = self._extract_dicom_metadata(ds)

            # Extract pixel data
            if hasattr(ds, 'pixel_array'):
                pixel_array = ds.pixel_array

                # Normalize to 8-bit
                pixel_array = self._normalize_pixel_array(pixel_array)

                # Convert to PIL Image
                image = Image.fromarray(pixel_array)

                # Create blobs
                image_blob = self._create_image_blob(image, self.max_image_size)
                thumbnail_blob = self._create_image_blob(image, self.thumbnail_size)

                return {
                    'metadata': metadata,
                    'image_blob': image_blob,
                    'thumbnail_blob': thumbnail_blob,
                    'original_size': pixel_array.shape,
                    'success': True
                }
            else:
                logger.warning(f"No pixel data in DICOM: {dicom_path}")
                return {
                    'metadata': metadata,
                    'image_blob': None,
                    'thumbnail_blob': None,
                    'success': False,
                    'error': 'No pixel data'
                }

        except Exception as e:
            logger.error(f"Error processing DICOM {dicom_path}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def process_image(self, image_path: str) -> Dict[str, Any]:
        """
        Process standard image file (PNG, JPG)

        Args:
            image_path: Path to image file

        Returns:
            Dictionary with image blobs
        """
        try:
            # Open image
            with Image.open(image_path) as image:
                # Convert to RGB if necessary
                if image.mode not in ('RGB', 'L'):
                    image = image.convert('RGB')

                # Create blobs
                image_blob = self._create_image_blob(image, self.max_image_size)
                thumbnail_blob = self._create_image_blob(image, self.thumbnail_size)

                return {
                    'image_blob': image_blob,
                    'thumbnail_blob': thumbnail_blob,
                    'original_size': image.size,
                    'original_mode': image.mode,
                    'success': True
                }

        except Exception as e:
            logger.error(f"Error processing image {image_path}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _extract_dicom_metadata(self, ds) -> Dict[str, Any]:
        """Extract relevant metadata from DICOM dataset"""
        metadata = {}

        # Essential fields
        fields = [
            'StudyDate', 'StudyTime', 'SeriesDate', 'SeriesTime',
            'Modality', 'SeriesDescription', 'StudyDescription',
            'PatientID', 'PatientAge', 'PatientSex',
            'SliceThickness', 'PixelSpacing', 'ImageOrientationPatient',
            'ImagePositionPatient', 'SliceLocation',
            'MagneticFieldStrength', 'ImagingFrequency',
            'EchoTime', 'RepetitionTime', 'InversionTime',
            'FlipAngle', 'SequenceName', 'ScanningSequence',
            'Manufacturer', 'ManufacturerModelName',
            'SoftwareVersions', 'ProtocolName'
        ]

        # PET specific fields
        pet_fields = [
            'RadiopharmaceuticalInformationSequence',
            'Radiopharmaceutical', 'RadionuclideTotalDose',
            'RadiopharmaceuticalStartTime', 'RadionuclideHalfLife',
            'Units', 'DecayCorrection', 'AttenuationCorrectionMethod',
            'ReconstructionMethod', 'ScatterCorrectionMethod'
        ]

        for field in fields + pet_fields:
            if hasattr(ds, field):
                value = getattr(ds, field)
                if isinstance(value, (list, tuple)):
                    metadata[field] = list(value)
                elif isinstance(value, pydicom.valuerep.DSfloat):
                    metadata[field] = float(value)
                elif isinstance(value, pydicom.valuerep.IS):
                    metadata[field] = int(value)
                else:
                    metadata[field] = str(value)

        # Handle PET radiopharmaceutical information
        if hasattr(ds, 'RadiopharmaceuticalInformationSequence'):
            try:
                radio_seq = ds.RadiopharmaceuticalInformationSequence[0]
                if hasattr(radio_seq, 'Radiopharmaceutical'):
                    metadata['Radiopharmaceutical'] = str(radio_seq.Radiopharmaceutical)
                if hasattr(radio_seq, 'RadionuclideTotalDose'):
                    metadata['RadionuclideTotalDose'] = float(radio_seq.RadionuclideTotalDose)
            except:
                pass

        return metadata

    def _normalize_pixel_array(self, pixel_array: np.ndarray) -> np.ndarray:
        """Normalize pixel array to 8-bit grayscale"""
        # Handle different bit depths
        if pixel_array.dtype != np.uint8:
            # Normalize to 0-255
            pmin = pixel_array.min()
            pmax = pixel_array.max()
            if pmax > pmin:
                pixel_array = ((pixel_array - pmin) / (pmax - pmin) * 255).astype(np.uint8)
            else:
                pixel_array = np.zeros_like(pixel_array, dtype=np.uint8)

        return pixel_array

    def _create_image_blob(self, image: Image.Image, target_size: Tuple[int, int]) -> bytes:
        """Create image blob with specified size"""
        # Resize image
        image_resized = image.copy()
        image_resized.thumbnail(target_size, Image.Resampling.LANCZOS)

        # Convert to bytes
        buffer = BytesIO()
        if image_resized.mode == 'L':
            image_resized.save(buffer, format='PNG')
        else:
            image_resized.save(buffer, format='JPEG', quality=self.jpeg_quality)

        return buffer.getvalue()

    def extract_pet_tracer(self, metadata: Dict[str, Any], filename: str = "") -> Optional[str]:
        """Extract PET tracer information from metadata or filename"""
        # Check metadata first
        if 'Radiopharmaceutical' in metadata:
            tracer = metadata['Radiopharmaceutical'].upper()
            if 'FDG' in tracer or 'FLUORODEOXYGLUCOSE' in tracer:
                return 'FDG'
            elif 'FLORBETAPIR' in tracer or 'AV45' in tracer:
                return 'AV45'
            elif 'FLORBETABEN' in tracer or 'FBB' in tracer:
                return 'FBB'
            elif 'FLORTAUCIPIR' in tracer or 'AV1451' in tracer:
                return 'AV1451'
            elif 'PIB' in tracer:
                return 'PIB'

        # Check filename patterns
        filename_upper = filename.upper()
        tracer_patterns = {
            'FDG': ['FDG', 'FLUORODEOXYGLUCOSE'],
            'AV45': ['AV45', 'FLORBETAPIR', 'AMYVID'],
            'FBB': ['FBB', 'FLORBETABEN'],
            'PIB': ['PIB', 'PITTSBURGH'],
            'AV1451': ['AV1451', 'FLORTAUCIPIR', 'TAU']
        }

        for tracer, patterns in tracer_patterns.items():
            if any(pattern in filename_upper for pattern in patterns):
                return tracer

        return None

    def determine_anatomical_region(self, series_description: str, modality: str) -> str:
        """Determine anatomical region from series description"""
        desc_lower = series_description.lower()

        regions = {
            'hippocampus': ['hippocampus', 'hippo', 'hipp'],
            'cortex': ['cortex', 'cortical', 'ctx'],
            'ventricles': ['ventricle', 'ventricular', 'vent'],
            'cerebellum': ['cerebellum', 'cerebellar'],
            'frontal_lobe': ['frontal'],
            'temporal_lobe': ['temporal'],
            'parietal_lobe': ['parietal'],
            'occipital_lobe': ['occipital'],
            'brainstem': ['brainstem', 'brain stem'],
            'thalamus': ['thalamus', 'thalamic'],
            'basal_ganglia': ['basal', 'ganglia', 'caudate', 'putamen'],
            'white_matter': ['white matter', 'wm'],
            'gray_matter': ['gray matter', 'grey matter', 'gm']
        }

        for region, keywords in regions.items():
            if any(keyword in desc_lower for keyword in keywords):
                return region

        # Default based on modality
        if modality == 'PET':
            return 'whole_brain'
        else:
            return 'brain'