"""
Medical Image Retriever Utility
Comprehensive class for retrieving lossless medical images in all formats
Based on the hybrid graph-index architecture described in research papers
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
import numpy as np
import pydicom
import nibabel as nib
from PIL import Image
import tifffile
import json
import hashlib
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ImageFormat(Enum):
    """Supported image formats"""
    DICOM = "dicom"
    NIFTI = "nifti"
    PNG = "png"
    TIFF = "tiff"
    THUMBNAIL = "thumbnail"
    ORIGINAL = "original"


class RetrievalMode(Enum):
    """Image retrieval modes"""
    FULL_QUALITY = "full_quality"  # Original or lossless
    PREVIEW = "preview"  # Thumbnail only
    METADATA_ONLY = "metadata_only"  # Just metadata
    ALL_FORMATS = "all_formats"  # All available formats


@dataclass
class ImageData:
    """Container for retrieved image data"""
    image_hash: str
    patient_id: str
    modality: str
    file_type: str
    pixel_array: Optional[np.ndarray] = None
    metadata: Optional[Dict] = None
    thumbnail: Optional[np.ndarray] = None
    available_formats: List[str] = None
    retrieval_timestamp: str = None

    def __post_init__(self):
        if self.retrieval_timestamp is None:
            self.retrieval_timestamp = datetime.now().isoformat()
        if self.available_formats is None:
            self.available_formats = []


class MedicalImageRetriever:
    """
    Comprehensive medical image retrieval system
    Supports DICOM, NIfTI, lossless PNG/TIFF, and thumbnails
    Integrates with Neo4j and Elasticsearch for metadata queries
    """

    def __init__(self, storage_path: str,
                 neo4j_connector=None,
                 es_indexer=None,
                 cache_enabled: bool = True):
        """
        Initialize the image retriever

        Args:
            storage_path: Base path for image storage
            neo4j_connector: Optional Neo4j connector for graph queries
            es_indexer: Optional Elasticsearch indexer for search
            cache_enabled: Enable in-memory caching of recent images
        """
        self.storage_path = Path(storage_path)
        self.metadata_path = self.storage_path / "metadata"
        self.lossless_path = self.storage_path / "lossless"
        self.lossless_png_path = self.lossless_path / "lossless_png"
        self.lossless_tiff_path = self.lossless_path / "lossless_tiff"
        self.thumbnail_path = self.storage_path / "thumbnails"

        self.neo4j = neo4j_connector
        self.es = es_indexer
        self.cache_enabled = cache_enabled

        # Simple in-memory cache for recent retrievals
        self._cache = {} if cache_enabled else None
        self._cache_max_size = 100  # Maximum cached images

        # Verify storage structure exists
        self._verify_storage_structure()

    def _verify_storage_structure(self):
        """Verify that the storage directories exist"""
        if not self.storage_path.exists():
            raise ValueError(f"Storage path does not exist: {self.storage_path}")

        required_paths = [self.metadata_path]
        for path in required_paths:
            if not path.exists():
                logger.warning(f"Required path missing: {path}")

    def retrieve_by_hash(self, image_hash: str,
                         mode: RetrievalMode = RetrievalMode.FULL_QUALITY,
                         preferred_format: ImageFormat = ImageFormat.ORIGINAL) -> Optional[ImageData]:
        """
        Retrieve image by its unique hash

        Args:
            image_hash: Unique image hash identifier
            mode: Retrieval mode (full quality, preview, etc.)
            preferred_format: Preferred format for full quality retrieval

        Returns:
            ImageData object or None if not found
        """
        # Check cache first
        if self.cache_enabled and image_hash in self._cache:
            logger.debug(f"Cache hit for {image_hash}")
            return self._cache[image_hash]

        # Load metadata
        metadata = self._load_metadata(image_hash)
        if not metadata:
            logger.error(f"No metadata found for hash: {image_hash}")
            return None

        # Create base ImageData object
        image_data = ImageData(
            image_hash=image_hash,
            patient_id=metadata.get('patient_id', 'UNKNOWN'),
            modality=metadata.get('modality', 'UNKNOWN'),
            file_type=metadata.get('file_type', 'UNKNOWN'),
            metadata=metadata
        )

        # Check available formats
        available_formats = self._check_available_formats(metadata)
        image_data.available_formats = available_formats

        # Retrieve based on mode
        if mode == RetrievalMode.METADATA_ONLY:
            # Just return metadata
            pass

        elif mode == RetrievalMode.PREVIEW:
            # Load thumbnail only
            thumb = self._load_thumbnail(metadata)
            image_data.thumbnail = thumb

        elif mode == RetrievalMode.FULL_QUALITY:
            # Load full quality image in preferred format
            pixel_array = self._load_full_quality(metadata, preferred_format)
            image_data.pixel_array = pixel_array

            # Also load thumbnail for convenience
            thumb = self._load_thumbnail(metadata)
            image_data.thumbnail = thumb

        elif mode == RetrievalMode.ALL_FORMATS:
            # Load all available formats
            all_data = self._load_all_formats(metadata)
            image_data.pixel_array = all_data.get('original')
            image_data.thumbnail = all_data.get('thumbnail')
            # Store other formats in metadata
            image_data.metadata['all_formats_data'] = all_data

        # Update cache
        if self.cache_enabled:
            self._update_cache(image_hash, image_data)

        return image_data

    def retrieve_by_patient(self, patient_id: str,
                            modality: Optional[str] = None,
                            limit: int = 100) -> List[ImageData]:
        """
        Retrieve all images for a patient

        Args:
            patient_id: Patient identifier
            modality: Optional filter by modality (MRI, PET, etc.)
            limit: Maximum number of images to return

        Returns:
            List of ImageData objects
        """
        images = []

        # Search using Elasticsearch if available
        if self.es:
            results = self._search_es_by_patient(patient_id, modality, limit)
            for result in results:
                image_hash = result.get('image_hash')
                if image_hash:
                    image_data = self.retrieve_by_hash(
                        image_hash,
                        mode=RetrievalMode.PREVIEW
                    )
                    if image_data:
                        images.append(image_data)

        # Fallback to file system search
        elif self.metadata_path.exists():
            count = 0
            for metadata_file in self.metadata_path.glob("*.json"):
                if count >= limit:
                    break

                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                if metadata.get('patient_id') == patient_id:
                    if modality and metadata.get('modality') != modality:
                        continue

                    image_hash = metadata.get('image_hash')
                    if image_hash:
                        image_data = self.retrieve_by_hash(
                            image_hash,
                            mode=RetrievalMode.PREVIEW
                        )
                        if image_data:
                            images.append(image_data)
                            count += 1

        return images

    def retrieve_original_dicom(self, image_hash: str) -> Optional[pydicom.Dataset]:
        """
        Retrieve original DICOM file as pydicom Dataset

        Args:
            image_hash: Image hash identifier

        Returns:
            pydicom Dataset or None
        """
        metadata = self._load_metadata(image_hash)
        if not metadata or metadata.get('file_type') != 'DICOM':
            return None

        original_path = Path(metadata.get('original_path', ''))
        if original_path.exists():
            try:
                return pydicom.dcmread(str(original_path))
            except Exception as e:
                logger.error(f"Failed to read DICOM: {e}")

        return None

    def retrieve_original_nifti(self, image_hash: str) -> Optional[nib.Nifti1Image]:
        """
        Retrieve original NIfTI file as nibabel object

        Args:
            image_hash: Image hash identifier

        Returns:
            nibabel Nifti1Image or None
        """
        metadata = self._load_metadata(image_hash)
        if not metadata or metadata.get('file_type') != 'NIfTI':
            return None

        original_path = Path(metadata.get('original_path', ''))
        if original_path.exists():
            try:
                return nib.load(str(original_path))
            except Exception as e:
                logger.error(f"Failed to read NIfTI: {e}")

        return None

    def retrieve_lossless_png(self, image_hash: str) -> Optional[np.ndarray]:
        """
        Retrieve lossless PNG version

        Args:
            image_hash: Image hash identifier

        Returns:
            Numpy array with original pixel values or None
        """
        metadata = self._load_metadata(image_hash)
        if not metadata:
            return None

        png_path = Path(metadata.get('lossless_png_path', ''))
        if png_path.exists():
            return self._reconstruct_from_png(png_path, metadata)

        return None

    def retrieve_lossless_tiff(self, image_hash: str) -> Optional[np.ndarray]:
        """
        Retrieve lossless TIFF version

        Args:
            image_hash: Image hash identifier

        Returns:
            Numpy array with original pixel values or None
        """
        metadata = self._load_metadata(image_hash)
        if not metadata:
            return None

        tiff_path = Path(metadata.get('lossless_tiff_path', ''))
        if tiff_path.exists():
            try:
                # Read TIFF with metadata
                with tifffile.TiffFile(tiff_path) as tif:
                    pixel_array = tif.asarray()

                    # Get embedded metadata if present
                    if tif.pages[0].description:
                        try:
                            embedded_meta = json.loads(tif.pages[0].description)
                            # Apply any necessary transformations
                            if 'rescale_slope' in embedded_meta:
                                slope = embedded_meta['rescale_slope']
                                intercept = embedded_meta.get('rescale_intercept', 0)
                                pixel_array = pixel_array * slope + intercept
                        except:
                            pass

                    return pixel_array

            except Exception as e:
                logger.error(f"Failed to read TIFF: {e}")

        return None

    def search_by_criteria(self, criteria: Dict[str, Any],
                           limit: int = 100) -> List[ImageData]:
        """
        Search for images using complex criteria

        Args:
            criteria: Search criteria dictionary
                Example: {'modality': 'MRI', 'study_date': '20240101'}
            limit: Maximum results

        Returns:
            List of matching ImageData objects
        """
        results = []

        # Use Elasticsearch if available
        if self.es:
            es_results = self._search_es_by_criteria(criteria, limit)
            for result in es_results:
                image_hash = result.get('image_hash')
                if image_hash:
                    image_data = self.retrieve_by_hash(
                        image_hash,
                        mode=RetrievalMode.PREVIEW
                    )
                    if image_data:
                        results.append(image_data)

        # Use Neo4j if available and ES not present
        elif self.neo4j:
            neo4j_results = self._search_neo4j_by_criteria(criteria, limit)
            for result in neo4j_results:
                image_hash = result.get('image_hash')
                if image_hash:
                    image_data = self.retrieve_by_hash(
                        image_hash,
                        mode=RetrievalMode.PREVIEW
                    )
                    if image_data:
                        results.append(image_data)

        # Fallback to file system search
        else:
            results = self._search_filesystem_by_criteria(criteria, limit)

        return results

    def get_image_lineage(self, image_hash: str) -> Dict[str, Any]:
        """
        Get complete lineage/provenance of an image

        Args:
            image_hash: Image hash identifier

        Returns:
            Dictionary with processing history and relationships
        """
        lineage = {
            'image_hash': image_hash,
            'creation_time': None,
            'processing_steps': [],
            'derived_formats': [],
            'relationships': []
        }

        # Load metadata
        metadata = self._load_metadata(image_hash)
        if not metadata:
            return lineage

        # Extract lineage information
        lineage['creation_time'] = metadata.get('created_at')
        lineage['original_source'] = metadata.get('original_path')

        # Check which derived formats exist
        if metadata.get('lossless_png_path'):
            lineage['derived_formats'].append({
                'format': 'PNG',
                'path': metadata['lossless_png_path'],
                'lossless': True
            })

        if metadata.get('lossless_tiff_path'):
            lineage['derived_formats'].append({
                'format': 'TIFF',
                'path': metadata['lossless_tiff_path'],
                'lossless': True
            })

        if metadata.get('thumbnail_path'):
            lineage['derived_formats'].append({
                'format': 'JPEG_thumbnail',
                'path': metadata['thumbnail_path'],
                'lossless': False
            })

        # Get relationships from Neo4j if available
        if self.neo4j:
            relationships = self._get_neo4j_relationships(image_hash)
            lineage['relationships'] = relationships

        return lineage

    def verify_lossless_quality(self, image_hash: str) -> Dict[str, Any]:
        """
        Verify that stored images maintain lossless quality

        Args:
            image_hash: Image hash identifier

        Returns:
            Verification results dictionary
        """
        verification = {
            'image_hash': image_hash,
            'verified': False,
            'original_exists': False,
            'png_match': False,
            'tiff_match': False,
            'max_difference': None,
            'mean_difference': None
        }

        metadata = self._load_metadata(image_hash)
        if not metadata:
            return verification

        # Load original
        original_pixels = None
        original_path = Path(metadata.get('original_path', ''))

        if original_path.exists():
            verification['original_exists'] = True

            if metadata['file_type'] == 'DICOM':
                try:
                    ds = pydicom.dcmread(str(original_path))
                    original_pixels = ds.pixel_array
                except:
                    pass
            elif metadata['file_type'] == 'NIfTI':
                try:
                    nii = nib.load(str(original_path))
                    data = nii.get_fdata()
                    # Get the slice that was extracted
                    if len(data.shape) >= 3:
                        slice_idx = metadata.get('extracted_slice', data.shape[2] // 2)
                        original_pixels = data[:, :, slice_idx]
                    else:
                        original_pixels = data
                except:
                    pass

        if original_pixels is None:
            return verification

        # Verify PNG
        png_pixels = self.retrieve_lossless_png(image_hash)
        if png_pixels is not None and original_pixels.shape == png_pixels.shape:
            diff = np.abs(original_pixels - png_pixels)
            verification['png_match'] = diff.max() < 1e-5
            verification['max_difference'] = float(diff.max())
            verification['mean_difference'] = float(diff.mean())

        # Verify TIFF
        tiff_pixels = self.retrieve_lossless_tiff(image_hash)
        if tiff_pixels is not None and original_pixels.shape == tiff_pixels.shape:
            diff = np.abs(original_pixels - tiff_pixels)
            verification['tiff_match'] = diff.max() < 1e-5

        verification['verified'] = (
                verification['png_match'] or verification['tiff_match']
        )

        return verification

    # Private helper methods

    def _load_metadata(self, image_hash: str) -> Optional[Dict]:
        """Load metadata from JSON file"""
        metadata_file = self.metadata_path / f"{image_hash}.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                return json.load(f)
        return None

    def _check_available_formats(self, metadata: Dict) -> List[str]:
        """Check which formats are available for an image"""
        formats = []

        if Path(metadata.get('original_path', '')).exists():
            formats.append('original')

        if Path(metadata.get('lossless_png_path', '')).exists():
            formats.append('png')

        if Path(metadata.get('lossless_tiff_path', '')).exists():
            formats.append('tiff')

        if Path(metadata.get('thumbnail_path', '')).exists():
            formats.append('thumbnail')

        return formats

    def _load_thumbnail(self, metadata: Dict) -> Optional[np.ndarray]:
        """Load thumbnail image"""
        thumb_path = Path(metadata.get('thumbnail_path', ''))
        if thumb_path.exists():
            try:
                img = Image.open(thumb_path)
                return np.array(img)
            except Exception as e:
                logger.error(f"Failed to load thumbnail: {e}")
        return None

    def _load_full_quality(self, metadata: Dict,
                           preferred_format: ImageFormat) -> Optional[np.ndarray]:
        """Load full quality image in preferred format"""

        # Try preferred format first
        if preferred_format == ImageFormat.ORIGINAL:
            pixels = self._load_original_pixels(metadata)
            if pixels is not None:
                return pixels

        elif preferred_format == ImageFormat.PNG:
            pixels = self.retrieve_lossless_png(metadata['image_hash'])
            if pixels is not None:
                return pixels

        elif preferred_format == ImageFormat.TIFF:
            pixels = self.retrieve_lossless_tiff(metadata['image_hash'])
            if pixels is not None:
                return pixels

        # Fallback: try any available format
        # Priority: Original > TIFF > PNG
        pixels = self._load_original_pixels(metadata)
        if pixels is not None:
            return pixels

        pixels = self.retrieve_lossless_tiff(metadata['image_hash'])
        if pixels is not None:
            return pixels

        pixels = self.retrieve_lossless_png(metadata['image_hash'])
        if pixels is not None:
            return pixels

        return None

    def _load_original_pixels(self, metadata: Dict) -> Optional[np.ndarray]:
        """Load pixel data from original file"""
        original_path = Path(metadata.get('original_path', ''))
        if not original_path.exists():
            return None

        try:
            if metadata['file_type'] == 'DICOM':
                ds = pydicom.dcmread(str(original_path))
                return ds.pixel_array

            elif metadata['file_type'] == 'NIfTI':
                nii = nib.load(str(original_path))
                data = nii.get_fdata()
                # Return the slice that was extracted for 2D representations
                if len(data.shape) >= 3:
                    slice_idx = metadata.get('extracted_slice', data.shape[2] // 2)
                    return data[:, :, slice_idx]
                return data

        except Exception as e:
            logger.error(f"Failed to load original pixels: {e}")

        return None

    def _load_all_formats(self, metadata: Dict) -> Dict[str, np.ndarray]:
        """Load all available formats"""
        all_data = {}

        # Original
        original = self._load_original_pixels(metadata)
        if original is not None:
            all_data['original'] = original

        # PNG
        png = self.retrieve_lossless_png(metadata['image_hash'])
        if png is not None:
            all_data['png'] = png

        # TIFF
        tiff = self.retrieve_lossless_tiff(metadata['image_hash'])
        if tiff is not None:
            all_data['tiff'] = tiff

        # Thumbnail
        thumb = self._load_thumbnail(metadata)
        if thumb is not None:
            all_data['thumbnail'] = thumb

        return all_data

    def _reconstruct_from_png(self, png_path: Path, metadata: Dict) -> np.ndarray:
        """Reconstruct original values from lossless PNG"""
        img = Image.open(png_path)
        pixel_array = np.array(img)

        # Check filename for transformations
        filename = png_path.name

        # Reverse shift if applied
        if '_shift' in filename:
            shift_val = int(filename.split('_shift')[1].split('.')[0])
            pixel_array = pixel_array + shift_val

        # Reverse scale if applied
        if '_scale' in filename:
            scale_val = float(filename.split('_scale')[1].split('.')[0])
            pixel_array = pixel_array / scale_val

        # Apply DICOM rescale if present
        if metadata.get('file_type') == 'DICOM':
            slope = metadata.get('rescale_slope', 1.0)
            intercept = metadata.get('rescale_intercept', 0.0)
            pixel_array = pixel_array * slope + intercept

        return pixel_array

    def _update_cache(self, image_hash: str, image_data: ImageData):
        """Update the in-memory cache"""
        if not self.cache_enabled:
            return

        # Simple LRU: remove oldest if at capacity
        if len(self._cache) >= self._cache_max_size:
            # Remove the oldest entry (first key)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        self._cache[image_hash] = image_data

    def _search_es_by_patient(self, patient_id: str,
                              modality: Optional[str],
                              limit: int) -> List[Dict]:
        """Search Elasticsearch by patient ID"""
        if not self.es:
            return []

        try:
            query = {
                'bool': {
                    'must': [
                        {'term': {'patient_id': patient_id}}
                    ]
                }
            }

            if modality:
                query['bool']['must'].append({'term': {'modality': modality}})

            results = self.es.search_images(query, size=limit)
            return results.get('hits', {}).get('hits', [])

        except Exception as e:
            logger.error(f"ES search failed: {e}")
            return []

    def _search_es_by_criteria(self, criteria: Dict, limit: int) -> List[Dict]:
        """Search Elasticsearch by criteria"""
        if not self.es:
            return []

        try:
            query = {'bool': {'must': []}}

            for key, value in criteria.items():
                query['bool']['must'].append({'term': {key: value}})

            results = self.es.search_images(query, size=limit)
            return results.get('hits', {}).get('hits', [])

        except Exception as e:
            logger.error(f"ES search failed: {e}")
            return []

    def _search_neo4j_by_criteria(self, criteria: Dict, limit: int) -> List[Dict]:
        """Search Neo4j by criteria"""
        if not self.neo4j:
            return []

        try:
            # Build Cypher query
            where_clauses = []
            for key, value in criteria.items():
                where_clauses.append(f"i.{key} = ${key}")

            query = f"""
            MATCH (i:ImageNode)
            WHERE {' AND '.join(where_clauses)}
            RETURN i
            LIMIT {limit}
            """

            results = self.neo4j.run_query(query, criteria)
            return [r['i'] for r in results]

        except Exception as e:
            logger.error(f"Neo4j search failed: {e}")
            return []

    def _search_filesystem_by_criteria(self, criteria: Dict, limit: int) -> List[ImageData]:
        """Search filesystem by criteria"""
        results = []
        count = 0

        for metadata_file in self.metadata_path.glob("*.json"):
            if count >= limit:
                break

            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            # Check if metadata matches all criteria
            match = True
            for key, value in criteria.items():
                if metadata.get(key) != value:
                    match = False
                    break

            if match:
                image_hash = metadata.get('image_hash')
                if image_hash:
                    image_data = self.retrieve_by_hash(
                        image_hash,
                        mode=RetrievalMode.PREVIEW
                    )
                    if image_data:
                        results.append(image_data)
                        count += 1

        return results

    def _get_neo4j_relationships(self, image_hash: str) -> List[Dict]:
        """Get Neo4j relationships for an image"""
        if not self.neo4j:
            return []

        try:
            query = """
            MATCH (i:ImageNode {image_hash: $image_hash})-[r]-(n)
            RETURN type(r) as relationship, labels(n) as node_type, n as node
            """

            results = self.neo4j.run_query(query, {'image_hash': image_hash})
            relationships = []

            for r in results:
                relationships.append({
                    'type': r['relationship'],
                    'target_type': r['node_type'],
                    'target': r['node']
                })

            return relationships

        except Exception as e:
            logger.error(f"Failed to get relationships: {e}")
            return []


# Convenience functions for common operations

def quick_retrieve(storage_path: str, image_hash: str) -> Optional[np.ndarray]:
    """
    Quick function to retrieve an image's pixel data

    Args:
        storage_path: Base storage path
        image_hash: Image hash

    Returns:
        Pixel array or None
    """
    retriever = MedicalImageRetriever(storage_path)
    image_data = retriever.retrieve_by_hash(
        image_hash,
        mode=RetrievalMode.FULL_QUALITY
    )
    return image_data.pixel_array if image_data else None


def batch_retrieve(storage_path: str,
                   image_hashes: List[str],
                   mode: RetrievalMode = RetrievalMode.PREVIEW) -> List[ImageData]:
    """
    Retrieve multiple images in batch

    Args:
        storage_path: Base storage path
        image_hashes: List of image hashes
        mode: Retrieval mode

    Returns:
        List of ImageData objects
    """
    retriever = MedicalImageRetriever(storage_path)
    results = []

    for image_hash in image_hashes:
        image_data = retriever.retrieve_by_hash(image_hash, mode=mode)
        if image_data:
            results.append(image_data)

    return results


def verify_storage_integrity(storage_path: str,
                             sample_size: int = 10) -> Dict[str, Any]:
    """
    Verify integrity of stored images

    Args:
        storage_path: Base storage path
        sample_size: Number of random images to verify

    Returns:
        Verification report
    """
    import random

    retriever = MedicalImageRetriever(storage_path)
    metadata_path = Path(storage_path) / "metadata"

    # Get random sample of images
    all_metadata_files = list(metadata_path.glob("*.json"))
    sample_files = random.sample(
        all_metadata_files,
        min(sample_size, len(all_metadata_files))
    )

    report = {
        'total_checked': len(sample_files),
        'verified': 0,
        'failed': 0,
        'details': []
    }

    for metadata_file in sample_files:
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        image_hash = metadata.get('image_hash')
        if image_hash:
            verification = retriever.verify_lossless_quality(image_hash)

            if verification['verified']:
                report['verified'] += 1
            else:
                report['failed'] += 1

            report['details'].append(verification)

    report['integrity_percentage'] = (
        report['verified'] / report['total_checked'] * 100
        if report['total_checked'] > 0 else 0
    )

    return report


# Example usage and testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Medical Image Retriever")
    parser.add_argument('--storage-path', required=True, help='Image storage path')
    parser.add_argument('--mode', choices=['retrieve', 'search', 'verify'],
                        default='retrieve')
    parser.add_argument('--image-hash', help='Image hash for retrieval')
    parser.add_argument('--patient-id', help='Patient ID for search')
    parser.add_argument('--modality', help='Modality filter')
    parser.add_argument('--format', choices=['original', 'png', 'tiff'],
                        default='original')

    args = parser.parse_args()

    # Initialize retriever
    retriever = MedicalImageRetriever(args.storage_path)

    if args.mode == 'retrieve' and args.image_hash:
        # Retrieve single image
        print(f"\nRetrieving image {args.image_hash}...")

        preferred_format = ImageFormat.ORIGINAL
        if args.format == 'png':
            preferred_format = ImageFormat.PNG
        elif args.format == 'tiff':
            preferred_format = ImageFormat.TIFF

        image_data = retriever.retrieve_by_hash(
            args.image_hash,
            mode=RetrievalMode.FULL_QUALITY,
            preferred_format=preferred_format
        )

        if image_data:
            print(f"✅ Image retrieved successfully")
            print(f"   Patient ID: {image_data.patient_id}")
            print(f"   Modality: {image_data.modality}")
            print(f"   File Type: {image_data.file_type}")
            print(f"   Available Formats: {image_data.available_formats}")

            if image_data.pixel_array is not None:
                print(f"   Pixel Array Shape: {image_data.pixel_array.shape}")
                print(f"   Data Type: {image_data.pixel_array.dtype}")
                print(f"   Min/Max Values: {image_data.pixel_array.min():.2f} / {image_data.pixel_array.max():.2f}")
        else:
            print(f"❌ Image not found")

    elif args.mode == 'search' and args.patient_id:
        # Search by patient
        print(f"\nSearching images for patient {args.patient_id}...")

        images = retriever.retrieve_by_patient(
            args.patient_id,
            modality=args.modality
        )

        print(f"Found {len(images)} images")
        for i, img in enumerate(images[:10], 1):
            print(f"\n{i}. Hash: {img.image_hash}")
            print(f"   Modality: {img.modality}")
            print(f"   File Type: {img.file_type}")

    elif args.mode == 'verify':
        # Verify storage integrity
        print("\nVerifying storage integrity...")

        report = verify_storage_integrity(args.storage_path, sample_size=10)

        print(f"\n📊 Verification Report:")
        print(f"   Total Checked: {report['total_checked']}")
        print(f"   Verified: {report['verified']}")
        print(f"   Failed: {report['failed']}")
        print(f"   Integrity: {report['integrity_percentage']:.1f}%")