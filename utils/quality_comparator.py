#!/usr/bin/env python3
"""
Medical Image Quality Metrics Report Generator
===============================================
Based on Nogueira-Reis et al. research on DICOM image quality metrics.
Generates comprehensive quality assessment reports for the medical image processing pipeline.

References:
- Nogueira-Reis et al. "DICOM file format has better radiographic image quality than other file formats"
- Measures: image noise, brightness uniformity, PSNR, structural similarity
"""

import numpy as np
import pydicom
import nibabel as nib
from PIL import Image
import cv2
import json
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats, ndimage
from skimage.metrics import structural_similarity as ssim
from skimage.metrics import peak_signal_noise_ratio as psnr
from skimage.metrics import mean_squared_error as mse
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import pandas as pd
import warnings
import hashlib
import zipfile
import io
import gc

warnings.filterwarnings('ignore')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ImageQualityMetrics:
    """Quality metrics for a single image based on Nogueira-Reis methodology"""

    # Image identification
    image_hash: str
    patient_id: str
    modality: str
    file_type: str  # DICOM or NIfTI

    # Nogueira-Reis metrics (primary)
    image_noise: float = 0.0  # Mean SD of gray values in ROIs
    image_brightness: float = 0.0  # Mean gray values
    image_uniformity: float = 0.0  # SD of gray values in central ROI

    # Additional standard metrics
    psnr_value: float = 0.0  # Peak Signal-to-Noise Ratio
    mse_value: float = 0.0  # Mean Squared Error
    ssim_value: float = 0.0  # Structural Similarity Index

    # Histogram metrics
    histogram_mean: float = 0.0
    histogram_std: float = 0.0
    histogram_skewness: float = 0.0
    histogram_kurtosis: float = 0.0
    dynamic_range: float = 0.0

    # Format-specific comparisons
    tiff_noise: Optional[float] = None
    tiff_brightness: Optional[float] = None
    tiff_uniformity: Optional[float] = None
    tiff_psnr: Optional[float] = None

    png_noise: Optional[float] = None
    png_brightness: Optional[float] = None
    png_uniformity: Optional[float] = None
    png_psnr: Optional[float] = None

    # Data preservation metrics
    bit_depth_preserved: bool = False
    pixel_value_range_preserved: bool = False
    original_min_value: float = 0.0
    original_max_value: float = 0.0
    converted_min_value: float = 0.0
    converted_max_value: float = 0.0

    # ROI-based measurements (following Nogueira-Reis)
    roi_measurements: List[Dict] = field(default_factory=list)
    central_roi_stats: Dict = field(default_factory=dict)

    # Artifacts and quality issues
    has_compression_artifacts: bool = False
    has_ringing_artifacts: bool = False
    has_blocking_artifacts: bool = False
    edge_preservation_score: float = 0.0

    # Processing quality
    sharpening_quality_score: float = 0.0
    smoothing_quality_score: float = 0.0
    thumbnail_quality_score: float = 0.0


@dataclass
class QualityMetricsReport:
    """Complete quality metrics report for the pipeline"""

    timestamp: str
    config_path: str
    storage_path: str

    # Summary statistics
    total_images_analyzed: int = 0

    # Format comparison (following Nogueira-Reis)
    format_quality_comparison: Dict[str, Dict] = field(default_factory=dict)

    # Average metrics by format
    dicom_avg_metrics: Dict[str, float] = field(default_factory=dict)
    tiff_avg_metrics: Dict[str, float] = field(default_factory=dict)
    png_avg_metrics: Dict[str, float] = field(default_factory=dict)

    # Statistical significance tests
    statistical_tests: Dict[str, Dict] = field(default_factory=dict)

    # Quality preservation rates
    pixel_preservation_rate: float = 0.0
    bit_depth_preservation_rate: float = 0.0
    dynamic_range_preservation_rate: float = 0.0

    # Modality-specific results
    results_by_modality: Dict[str, Dict] = field(default_factory=dict)

    # Individual metrics
    image_metrics: List[ImageQualityMetrics] = field(default_factory=list)

    # Recommendations
    recommendations: List[str] = field(default_factory=list)


class MedicalImageQualityAnalyzer:
    """
    Analyzes medical image quality based on Nogueira-Reis et al. methodology
    """

    def __init__(self, config_path: str, sample_size: int = 100):
        """
        Initialize the quality analyzer

        Args:
            config_path: Path to config.yaml
            sample_size: Number of images to analyze
        """
        self.config_path = Path(config_path)
        self.sample_size = sample_size

        # Load configuration
        self.config = self._load_config()

        # Extract paths
        self.storage_path = Path(self.config['image_storage']['storage_path'])
        self.base_path = Path(self.config['base_path'])

        # Get enabled formats
        self.output_formats = self.config['image_storage']['output_formats']

        # Initialize directories
        self._init_directories()

        # ROI configuration (based on Nogueira-Reis methodology)
        self.roi_size = 40  # 4x4mm equivalent in pixels
        self.roi_distance = 148  # 1.48cm equivalent in pixels
        self.central_roi_size = 148  # 1.48x1.48cm equivalent

    def _load_config(self) -> Dict:
        """Load configuration from YAML"""
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def _init_directories(self):
        """Initialize directory paths"""
        self.dirs = {
            'metadata': self.storage_path / 'metadata',
            'tiff': self.storage_path / 'diagnostic_tiff',
            'png': self.storage_path / 'diagnostic_png',
            'thumbnail': self.storage_path / 'thumbnails',
            'sharpened': self.storage_path / 'sharpened_tiff',
            'smooth': self.storage_path / 'display_smooth'
        }

    def measure_image_quality_nogueira_reis(self, image_array: np.ndarray) -> Dict:
        """
        Measure image quality using Nogueira-Reis methodology

        Based on the paper's approach:
        1. Place 5 ROIs (1 central, 4 peripheral on bisector lines)
        2. Measure noise as mean SD of gray values in ROIs
        3. Measure brightness as mean gray values
        4. Measure uniformity as SD in central ROI
        """
        h, w = image_array.shape[:2]

        # Ensure float array for calculations
        img_float = image_array.astype(np.float32)

        # Define ROI positions (following paper's methodology)
        center_x, center_y = w // 2, h // 2

        # Calculate ROI positions on bisector lines
        roi_offset = self.roi_distance
        roi_positions = [
            (center_x, center_y),  # Center
            (center_x - roi_offset, center_y - roi_offset),  # Top-left
            (center_x + roi_offset, center_y - roi_offset),  # Top-right
            (center_x - roi_offset, center_y + roi_offset),  # Bottom-left
            (center_x + roi_offset, center_y + roi_offset),  # Bottom-right
        ]

        # Extract ROIs and calculate noise (SD within each ROI)
        roi_sds = []
        roi_means = []
        roi_measurements = []

        for i, (x, y) in enumerate(roi_positions):
            # Extract ROI (handle boundaries)
            x1 = max(0, x - self.roi_size // 2)
            x2 = min(w, x + self.roi_size // 2)
            y1 = max(0, y - self.roi_size // 2)
            y2 = min(h, y + self.roi_size // 2)

            roi = img_float[y1:y2, x1:x2]

            if roi.size > 0:
                roi_sd = np.std(roi)
                roi_mean = np.mean(roi)
                roi_sds.append(roi_sd)
                roi_means.append(roi_mean)

                roi_measurements.append({
                    'roi_id': i,
                    'position': 'center' if i == 0 else f'peripheral_{i}',
                    'mean': float(roi_mean),
                    'std': float(roi_sd),
                    'min': float(np.min(roi)),
                    'max': float(np.max(roi))
                })

        # Calculate image noise (mean of SDs from all ROIs)
        image_noise = np.mean(roi_sds) if roi_sds else 0

        # Extract central ROI for brightness and uniformity
        central_half_size = self.central_roi_size // 2
        cx1 = max(0, center_x - central_half_size)
        cx2 = min(w, center_x + central_half_size)
        cy1 = max(0, center_y - central_half_size)
        cy2 = min(h, center_y + central_half_size)

        central_roi = img_float[cy1:cy2, cx1:cx2]

        # Calculate brightness (mean of central ROI)
        image_brightness = np.mean(central_roi) if central_roi.size > 0 else 0

        # Calculate uniformity (SD of central ROI - lower is better)
        image_uniformity = np.std(central_roi) if central_roi.size > 0 else 0

        return {
            'image_noise': float(image_noise),
            'image_brightness': float(image_brightness),
            'image_uniformity': float(image_uniformity),
            'roi_measurements': roi_measurements,
            'central_roi_stats': {
                'mean': float(np.mean(central_roi)) if central_roi.size > 0 else 0,
                'std': float(np.std(central_roi)) if central_roi.size > 0 else 0,
                'min': float(np.min(central_roi)) if central_roi.size > 0 else 0,
                'max': float(np.max(central_roi)) if central_roi.size > 0 else 0,
                'size': central_roi.size
            }
        }

    def calculate_psnr_mse(self, original: np.ndarray, converted: np.ndarray) -> Tuple[float, float]:
        """Calculate PSNR and MSE between original and converted images"""
        try:
            # Ensure same shape
            if original.shape != converted.shape:
                # Resize converted to match original
                converted = cv2.resize(converted, (original.shape[1], original.shape[0]))

            # Normalize to same range for comparison
            original_norm = (original - original.min()) / (original.max() - original.min() + 1e-10)
            converted_norm = (converted - converted.min()) / (converted.max() - converted.min() + 1e-10)

            # Calculate MSE
            mse_val = np.mean((original_norm - converted_norm) ** 2)

            # Calculate PSNR
            if mse_val == 0:
                psnr_val = float('inf')
            else:
                max_pixel = 1.0  # Normalized
                psnr_val = 20 * np.log10(max_pixel / np.sqrt(mse_val))

            return float(psnr_val), float(mse_val)

        except Exception as e:
            logger.error(f"Error calculating PSNR/MSE: {e}")
            return 0.0, 0.0

    def calculate_ssim(self, original: np.ndarray, converted: np.ndarray) -> float:
        """Calculate Structural Similarity Index"""
        try:
            # Ensure same shape
            if original.shape != converted.shape:
                converted = cv2.resize(converted, (original.shape[1], original.shape[0]))

            # Normalize to 0-255 range
            original_norm = ((original - original.min()) / (original.max() - original.min() + 1e-10) * 255).astype(
                np.uint8)
            converted_norm = ((converted - converted.min()) / (converted.max() - converted.min() + 1e-10) * 255).astype(
                np.uint8)

            # Calculate SSIM
            ssim_val = ssim(original_norm, converted_norm)

            return float(ssim_val)

        except Exception as e:
            logger.error(f"Error calculating SSIM: {e}")
            return 0.0

    def analyze_histogram_characteristics(self, image_array: np.ndarray) -> Dict:
        """Analyze histogram characteristics of the image"""
        flat = image_array.flatten()

        # Remove outliers for robust statistics
        p1, p99 = np.percentile(flat, [1, 99])
        flat_clipped = flat[(flat >= p1) & (flat <= p99)]

        return {
            'mean': float(np.mean(flat_clipped)),
            'std': float(np.std(flat_clipped)),
            'skewness': float(stats.skew(flat_clipped)),
            'kurtosis': float(stats.kurtosis(flat_clipped)),
            'dynamic_range': float(np.max(flat) - np.min(flat)),
            'min': float(np.min(flat)),
            'max': float(np.max(flat))
        }

    def detect_compression_artifacts(self, image_array: np.ndarray) -> Dict:
        """Detect compression artifacts in the image"""
        artifacts = {
            'has_compression_artifacts': False,
            'has_ringing_artifacts': False,
            'has_blocking_artifacts': False
        }

        try:
            # Detect blocking artifacts (8x8 JPEG blocks)
            # Calculate differences at block boundaries
            h_diffs = np.abs(np.diff(image_array[::8, :], axis=0))
            v_diffs = np.abs(np.diff(image_array[:, ::8], axis=1))

            block_score = np.mean(h_diffs) + np.mean(v_diffs)
            artifacts['has_blocking_artifacts'] = block_score > np.std(image_array) * 2

            # Detect ringing artifacts (Gibbs phenomenon)
            # Use high-pass filter to detect oscillations near edges
            edges = cv2.Canny(image_array.astype(np.uint8), 50, 150)
            dilated_edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=1)

            # Check for oscillations near edges
            edge_region = image_array[dilated_edges > 0]
            if len(edge_region) > 0:
                edge_std = np.std(edge_region)
                artifacts['has_ringing_artifacts'] = edge_std > np.std(image_array) * 1.5

            # Overall compression artifact detection
            artifacts['has_compression_artifacts'] = (
                    artifacts['has_blocking_artifacts'] or
                    artifacts['has_ringing_artifacts']
            )

        except Exception as e:
            logger.error(f"Error detecting artifacts: {e}")

        return artifacts

    def measure_edge_preservation(self, original: np.ndarray, processed: np.ndarray) -> float:
        """Measure how well edges are preserved in processed image"""
        try:
            # Ensure same shape
            if original.shape != processed.shape:
                processed = cv2.resize(processed, (original.shape[1], original.shape[0]))

            # Detect edges in both images
            original_edges = cv2.Canny(original.astype(np.uint8), 50, 150)
            processed_edges = cv2.Canny(processed.astype(np.uint8), 50, 150)

            # Calculate edge preservation score
            intersection = np.logical_and(original_edges, processed_edges).sum()
            union = np.logical_or(original_edges, processed_edges).sum()

            if union > 0:
                edge_preservation = intersection / union
            else:
                edge_preservation = 1.0

            return float(edge_preservation)

        except Exception as e:
            logger.error(f"Error measuring edge preservation: {e}")
            return 0.0

    def analyze_single_image(self, metadata: Dict) -> ImageQualityMetrics:
        """Analyze quality metrics for a single image"""

        metrics = ImageQualityMetrics(
            image_hash=metadata.get('image_hash', 'unknown'),
            patient_id=metadata.get('patient_id', 'unknown'),
            modality=metadata.get('modality', 'UNKNOWN'),
            file_type=metadata.get('file_type', 'UNKNOWN')
        )

        try:
            # Load original image (from DICOM or NIfTI)
            original_array = self._load_original_image(metadata)

            if original_array is None:
                logger.warning(f"Could not load original for {metrics.image_hash}")
                return metrics

            # Measure quality on original (DICOM/NIfTI)
            original_quality = self.measure_image_quality_nogueira_reis(original_array)
            metrics.image_noise = original_quality['image_noise']
            metrics.image_brightness = original_quality['image_brightness']
            metrics.image_uniformity = original_quality['image_uniformity']
            metrics.roi_measurements = original_quality['roi_measurements']
            metrics.central_roi_stats = original_quality['central_roi_stats']

            # Histogram analysis
            hist_stats = self.analyze_histogram_characteristics(original_array)
            metrics.histogram_mean = hist_stats['mean']
            metrics.histogram_std = hist_stats['std']
            metrics.histogram_skewness = hist_stats['skewness']
            metrics.histogram_kurtosis = hist_stats['kurtosis']
            metrics.dynamic_range = hist_stats['dynamic_range']
            metrics.original_min_value = hist_stats['min']
            metrics.original_max_value = hist_stats['max']

            # Analyze converted formats
            patient_dir = metadata.get('patient_id', 'unknown')
            hash_prefix = metadata.get('image_hash', '')[:12]

            # Analyze TIFF format
            if self.output_formats.get('tiff', True):
                tiff_path = self.dirs['tiff'] / patient_dir / f"{hash_prefix}_diagnostic.tif"
                if tiff_path.exists():
                    tiff_array = self._load_tiff_image(tiff_path)
                    if tiff_array is not None:
                        # Measure TIFF quality
                        tiff_quality = self.measure_image_quality_nogueira_reis(tiff_array)
                        metrics.tiff_noise = tiff_quality['image_noise']
                        metrics.tiff_brightness = tiff_quality['image_brightness']
                        metrics.tiff_uniformity = tiff_quality['image_uniformity']

                        # Compare with original
                        psnr_val, mse_val = self.calculate_psnr_mse(original_array, tiff_array)
                        metrics.tiff_psnr = psnr_val

                        # Check bit depth preservation
                        metrics.bit_depth_preserved = self._check_bit_depth_preservation(
                            original_array, tiff_array, metadata
                        )

                        # Check pixel value range
                        metrics.converted_min_value = float(tiff_array.min())
                        metrics.converted_max_value = float(tiff_array.max())
                        metrics.pixel_value_range_preserved = self._check_range_preservation(
                            original_array, tiff_array, metadata
                        )

            # Analyze PNG format if enabled
            if self.output_formats.get('png', False):
                png_path = self.dirs['png'] / patient_dir / f"{hash_prefix}_diagnostic.png"
                if png_path.exists():
                    png_array = np.array(Image.open(png_path))
                    if png_array is not None:
                        png_quality = self.measure_image_quality_nogueira_reis(png_array)
                        metrics.png_noise = png_quality['image_noise']
                        metrics.png_brightness = png_quality['image_brightness']
                        metrics.png_uniformity = png_quality['image_uniformity']

                        psnr_val, _ = self.calculate_psnr_mse(original_array, png_array)
                        metrics.png_psnr = psnr_val

            # Analyze sharpened version
            if self.output_formats.get('sharpened_tiff', False):
                sharp_path = self.dirs['sharpened'] / patient_dir / f"{hash_prefix}_sharpened.tif"
                if sharp_path.exists():
                    sharp_array = np.array(Image.open(sharp_path))
                    metrics.sharpening_quality_score = self.measure_edge_preservation(
                        original_array, sharp_array
                    )

            # Detect artifacts
            artifact_results = self.detect_compression_artifacts(original_array)
            metrics.has_compression_artifacts = artifact_results['has_compression_artifacts']
            metrics.has_ringing_artifacts = artifact_results['has_ringing_artifacts']
            metrics.has_blocking_artifacts = artifact_results['has_blocking_artifacts']

            # Calculate overall scores
            metrics.psnr_value = metrics.tiff_psnr if metrics.tiff_psnr else 0
            metrics.mse_value = mse_val if 'mse_val' in locals() else 0
            metrics.ssim_value = self.calculate_ssim(original_array, tiff_array) if 'tiff_array' in locals() else 0

        except Exception as e:
            logger.error(f"Error analyzing image {metrics.image_hash}: {e}")

        return metrics

    def _load_original_image(self, metadata: Dict) -> Optional[np.ndarray]:
        """Load original DICOM or NIfTI image"""
        try:
            original_path = metadata.get('original_path')
            if not original_path:
                return None

            original_path = Path(original_path)
            zip_member = metadata.get('zip_member')

            if metadata.get('file_type') == 'DICOM':
                if zip_member:
                    # Load from ZIP
                    with zipfile.ZipFile(original_path, 'r') as zf:
                        with zf.open(zip_member) as f:
                            ds = pydicom.dcmread(io.BytesIO(f.read()))
                else:
                    ds = pydicom.dcmread(str(original_path))

                if hasattr(ds, 'pixel_array'):
                    return ds.pixel_array.astype(np.float32)

            elif metadata.get('file_type') == 'NIfTI':
                if zip_member:
                    # Load from ZIP
                    with zipfile.ZipFile(original_path, 'r') as zf:
                        with zf.open(zip_member) as f:
                            import tempfile
                            with tempfile.NamedTemporaryFile(suffix='.nii', delete=False) as tmp:
                                tmp.write(f.read())
                                tmp.flush()
                                nii = nib.load(tmp.name)
                            os.unlink(tmp.name)
                else:
                    nii = nib.load(str(original_path))

                data = np.asarray(nii.dataobj)
                # Extract middle slice for 2D analysis
                if len(data.shape) >= 3:
                    slice_idx = data.shape[2] // 2
                    return data[:, :, slice_idx].astype(np.float32)

        except Exception as e:
            logger.error(f"Error loading original image: {e}")

        return None

    def _load_tiff_image(self, path: Path) -> Optional[np.ndarray]:
        """Load TIFF image"""
        try:
            img = Image.open(path)
            return np.array(img).astype(np.float32)
        except Exception as e:
            logger.error(f"Error loading TIFF: {e}")
            return None

    def _check_bit_depth_preservation(self, original: np.ndarray, converted: np.ndarray,
                                      metadata: Dict) -> bool:
        """Check if bit depth is properly preserved"""
        try:
            # Get original bit depth from metadata
            original_bits = metadata.get('bits_stored', 16)

            # Check if dynamic range is preserved
            original_range = original.max() - original.min()
            converted_range = converted.max() - converted.min()

            # Allow for small numerical differences
            range_ratio = converted_range / (original_range + 1e-10)

            # Check if the conversion maintains sufficient precision
            return 0.95 <= range_ratio <= 1.05

        except Exception:
            return False

    def _check_range_preservation(self, original: np.ndarray, converted: np.ndarray,
                                  metadata: Dict) -> bool:
        """Check if pixel value range is preserved"""
        try:
            # Check if we have rescale information
            if metadata.get('tiff_offset'):
                # Offset was applied, so we expect a shift
                offset = metadata['tiff_offset']
                converted_adjusted = converted - offset

                # Check if adjusted values match original
                diff = np.abs(original - converted_adjusted)
                return np.max(diff) < 1.0
            else:
                # Direct comparison
                diff = np.abs(original - converted)
                # Allow for small rounding errors
                return np.max(diff) < 1.0

        except Exception:
            return False

    def run_quality_analysis(self, max_workers: int = 8) -> QualityMetricsReport:
        """Run complete quality analysis"""
        logger.info("=" * 70)
        logger.info("MEDICAL IMAGE QUALITY METRICS ANALYSIS")
        logger.info("Based on Nogueira-Reis et al. methodology")
        logger.info("=" * 70)

        # Initialize report
        report = QualityMetricsReport(
            timestamp=datetime.now().isoformat(),
            config_path=str(self.config_path),
            storage_path=str(self.storage_path)
        )

        # Discover processed images
        metadata_dir = self.dirs['metadata']
        metadata_files = list(metadata_dir.glob("*.json"))

        if not metadata_files:
            logger.error("No processed images found!")
            return report

        # Sample images
        import random
        sample_size = min(self.sample_size, len(metadata_files))
        sampled_files = random.sample(metadata_files, sample_size)

        logger.info(f"Analyzing {sample_size} images...")

        # Analyze images
        image_metrics = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []

            for metadata_file in sampled_files:
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)

                    future = executor.submit(self.analyze_single_image, metadata)
                    futures.append(future)
                except Exception as e:
                    logger.error(f"Error reading metadata: {e}")

            # Process results
            with tqdm(total=len(futures), desc="Analyzing quality") as pbar:
                for future in as_completed(futures):
                    try:
                        metrics = future.result(timeout=60)
                        image_metrics.append(metrics)
                        pbar.update(1)
                    except Exception as e:
                        logger.error(f"Analysis failed: {e}")
                        pbar.update(1)

        # Store results
        report.image_metrics = image_metrics
        report.total_images_analyzed = len(image_metrics)

        # Compile statistics
        self._compile_format_comparison(report)
        self._perform_statistical_tests(report)
        self._generate_recommendations(report)

        return report

    def _compile_format_comparison(self, report: QualityMetricsReport):
        """Compile format comparison following Nogueira-Reis methodology"""

        # Collect metrics by format
        dicom_metrics = []
        tiff_metrics = []
        png_metrics = []

        for metrics in report.image_metrics:
            # Original (DICOM/NIfTI) metrics
            dicom_metrics.append({
                'noise': metrics.image_noise,
                'brightness': metrics.image_brightness,
                'uniformity': metrics.image_uniformity
            })

            # TIFF metrics
            if metrics.tiff_noise is not None:
                tiff_metrics.append({
                    'noise': metrics.tiff_noise,
                    'brightness': metrics.tiff_brightness,
                    'uniformity': metrics.tiff_uniformity,
                    'psnr': metrics.tiff_psnr
                })

            # PNG metrics
            if metrics.png_noise is not None:
                png_metrics.append({
                    'noise': metrics.png_noise,
                    'brightness': metrics.png_brightness,
                    'uniformity': metrics.png_uniformity,
                    'psnr': metrics.png_psnr
                })

        # Calculate averages
        if dicom_metrics:
            report.dicom_avg_metrics = {
                'noise': np.mean([m['noise'] for m in dicom_metrics]),
                'brightness': np.mean([m['brightness'] for m in dicom_metrics]),
                'uniformity': np.mean([m['uniformity'] for m in dicom_metrics]),
                'count': len(dicom_metrics)
            }

        if tiff_metrics:
            report.tiff_avg_metrics = {
                'noise': np.mean([m['noise'] for m in tiff_metrics]),
                'brightness': np.mean([m['brightness'] for m in tiff_metrics]),
                'uniformity': np.mean([m['uniformity'] for m in tiff_metrics]),
                'avg_psnr': np.mean([m['psnr'] for m in tiff_metrics if m['psnr'] < float('inf')]),
                'count': len(tiff_metrics)
            }

        if png_metrics:
            report.png_avg_metrics = {
                'noise': np.mean([m['noise'] for m in png_metrics]),
                'brightness': np.mean([m['brightness'] for m in png_metrics]),
                'uniformity': np.mean([m['uniformity'] for m in png_metrics]),
                'avg_psnr': np.mean([m['psnr'] for m in png_metrics if m['psnr'] < float('inf')]),
                'count': len(png_metrics)
            }

        # Calculate preservation rates
        preservation_count = sum(1 for m in report.image_metrics if m.pixel_value_range_preserved)
        report.pixel_preservation_rate = (preservation_count / len(report.image_metrics) * 100
                                          if report.image_metrics else 0)

        bit_depth_count = sum(1 for m in report.image_metrics if m.bit_depth_preserved)
        report.bit_depth_preservation_rate = (bit_depth_count / len(report.image_metrics) * 100
                                              if report.image_metrics else 0)

    def _perform_statistical_tests(self, report: QualityMetricsReport):
        """Perform statistical significance tests (following Nogueira-Reis)"""

        # Prepare data for ANOVA-style comparison
        format_data = {
            'DICOM': [],
            'TIFF': [],
            'PNG': []
        }

        for metrics in report.image_metrics:
            format_data['DICOM'].append(metrics.image_noise)
            if metrics.tiff_noise is not None:
                format_data['TIFF'].append(metrics.tiff_noise)
            if metrics.png_noise is not None:
                format_data['PNG'].append(metrics.png_noise)

        # Perform tests if we have data for multiple formats
        if len([v for v in format_data.values() if len(v) > 0]) >= 2:
            # Perform ANOVA for noise comparison
            valid_formats = [(k, v) for k, v in format_data.items() if len(v) > 0]

            if len(valid_formats) >= 2:
                f_stat, p_value = stats.f_oneway(*[v for _, v in valid_formats])

                report.statistical_tests['noise_comparison'] = {
                    'test': 'One-way ANOVA',
                    'f_statistic': float(f_stat),
                    'p_value': float(p_value),
                    'significant': p_value < 0.05,
                    'interpretation': 'Significant difference in noise levels between formats' if p_value < 0.05
                    else 'No significant difference in noise levels'
                }

                # Perform post-hoc tests if significant
                if p_value < 0.05 and len(valid_formats) > 2:
                    # Tukey's HSD would go here
                    report.statistical_tests['post_hoc'] = {
                        'test': 'Tukey HSD recommended',
                        'note': 'Significant differences found, post-hoc analysis recommended'
                    }

    def _generate_recommendations(self, report: QualityMetricsReport):
        """Generate recommendations based on analysis"""

        recommendations = []

        # Check noise levels
        if report.dicom_avg_metrics and report.tiff_avg_metrics:
            noise_increase = ((report.tiff_avg_metrics['noise'] - report.dicom_avg_metrics['noise'])
                              / report.dicom_avg_metrics['noise'] * 100)

            if noise_increase > 10:
                recommendations.append(
                    f"⚠️ TIFF conversion increases noise by {noise_increase:.1f}%. "
                    "Consider reviewing conversion parameters."
                )
            elif noise_increase < 0:
                recommendations.append(
                    f"✅ TIFF conversion reduces noise by {abs(noise_increase):.1f}%. "
                    "Excellent preservation quality."
                )

        # Check preservation rates
        if report.pixel_preservation_rate < 95:
            recommendations.append(
                f"⚠️ Pixel value preservation rate is {report.pixel_preservation_rate:.1f}%. "
                "Review rescale/window settings."
            )
        else:
            recommendations.append(
                f"✅ Excellent pixel preservation rate: {report.pixel_preservation_rate:.1f}%"
            )

        # Check bit depth
        if report.bit_depth_preservation_rate < 90:
            recommendations.append(
                f"⚠️ Bit depth preservation issues detected ({report.bit_depth_preservation_rate:.1f}%). "
                "Ensure 16-bit or higher storage for diagnostic images."
            )

        # Check uniformity
        if report.tiff_avg_metrics and 'uniformity' in report.tiff_avg_metrics:
            if report.tiff_avg_metrics['uniformity'] > report.dicom_avg_metrics.get('uniformity', 0) * 1.2:
                recommendations.append(
                    "⚠️ Reduced image uniformity detected in converted images. "
                    "May indicate compression or processing artifacts."
                )

        # Check PSNR
        if report.tiff_avg_metrics and 'avg_psnr' in report.tiff_avg_metrics:
            avg_psnr = report.tiff_avg_metrics['avg_psnr']
            if avg_psnr < 35:
                recommendations.append(
                    f"⚠️ Low PSNR ({avg_psnr:.1f} dB) indicates quality loss. "
                    "Consider using lossless compression."
                )
            elif avg_psnr > 40:
                recommendations.append(
                    f"✅ Excellent PSNR ({avg_psnr:.1f} dB) indicates high fidelity conversion."
                )

        report.recommendations = recommendations

    def generate_visual_report(self, report: QualityMetricsReport, output_dir: str):
        """Generate visual quality report with plots"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Set style
        plt.style.use('seaborn-v0_8-darkgrid')

        # Create figure with subplots
        fig = plt.figure(figsize=(16, 12))

        # 1. Format Comparison (Nogueira-Reis style)
        ax1 = plt.subplot(2, 3, 1)
        if report.dicom_avg_metrics and report.tiff_avg_metrics:
            formats = ['DICOM', 'TIFF']
            noise_values = [report.dicom_avg_metrics['noise'],
                            report.tiff_avg_metrics['noise']]

            bars = ax1.bar(formats, noise_values)
            bars[0].set_color('blue')
            bars[1].set_color('orange')

            ax1.set_ylabel('Image Noise (Mean SD)')
            ax1.set_title('Image Noise by Format\n(Lower is Better)')
            ax1.grid(True, alpha=0.3)

        # 2. Brightness Comparison
        ax2 = plt.subplot(2, 3, 2)
        if report.dicom_avg_metrics and report.tiff_avg_metrics:
            brightness_values = [report.dicom_avg_metrics['brightness'],
                                 report.tiff_avg_metrics['brightness']]

            bars = ax2.bar(formats, brightness_values)
            bars[0].set_color('blue')
            bars[1].set_color('green')

            ax2.set_ylabel('Image Brightness (Mean Gray Value)')
            ax2.set_title('Image Brightness by Format')
            ax2.grid(True, alpha=0.3)

        # 3. Uniformity Comparison
        ax3 = plt.subplot(2, 3, 3)
        if report.dicom_avg_metrics and report.tiff_avg_metrics:
            uniformity_values = [report.dicom_avg_metrics['uniformity'],
                                 report.tiff_avg_metrics['uniformity']]

            bars = ax3.bar(formats, uniformity_values)
            bars[0].set_color('blue')
            bars[1].set_color('red')

            ax3.set_ylabel('Image Uniformity (SD)')
            ax3.set_title('Image Uniformity by Format\n(Lower is Better)')
            ax3.grid(True, alpha=0.3)

        # 4. PSNR Distribution
        ax4 = plt.subplot(2, 3, 4)
        psnr_values = [m.psnr_value for m in report.image_metrics
                       if m.psnr_value > 0 and m.psnr_value < float('inf')]
        if psnr_values:
            ax4.hist(psnr_values, bins=20, edgecolor='black', alpha=0.7)
            ax4.axvline(np.mean(psnr_values), color='red', linestyle='--',
                        label=f'Mean: {np.mean(psnr_values):.1f} dB')
            ax4.set_xlabel('PSNR (dB)')
            ax4.set_ylabel('Frequency')
            ax4.set_title('PSNR Distribution')
            ax4.legend()
            ax4.grid(True, alpha=0.3)

        # 5. Preservation Rates
        ax5 = plt.subplot(2, 3, 5)
        preservation_data = {
            'Pixel Values': report.pixel_preservation_rate,
            'Bit Depth': report.bit_depth_preservation_rate,
            'Dynamic Range': report.dynamic_range_preservation_rate
        }

        bars = ax5.bar(preservation_data.keys(), preservation_data.values())
        for i, bar in enumerate(bars):
            height = bar.get_height()
            color = 'green' if height > 95 else 'orange' if height > 90 else 'red'
            bar.set_color(color)
            ax5.text(bar.get_x() + bar.get_width() / 2., height + 1,
                     f'{height:.1f}%', ha='center', va='bottom')

        ax5.set_ylabel('Preservation Rate (%)')
        ax5.set_title('Quality Preservation Metrics')
        ax5.set_ylim([0, 110])
        ax5.grid(True, alpha=0.3)

        # 6. Modality Breakdown
        ax6 = plt.subplot(2, 3, 6)
        modality_counts = {}
        for m in report.image_metrics:
            modality_counts[m.modality] = modality_counts.get(m.modality, 0) + 1

        if modality_counts:
            ax6.pie(modality_counts.values(), labels=modality_counts.keys(),
                    autopct='%1.1f%%', startangle=90)
            ax6.set_title('Images by Modality')

        plt.suptitle('Medical Image Quality Metrics Report\n(Based on Nogueira-Reis et al. Methodology)',
                     fontsize=14, fontweight='bold')
        plt.tight_layout()

        # Save figure
        plot_path = output_dir / 'quality_metrics_report.png'
        plt.savefig(plot_path, dpi=150, bbox_inches='tight')
        plt.close()

        logger.info(f"Visual report saved to {plot_path}")

        return plot_path

    def save_report(self, report: QualityMetricsReport, output_path: str):
        """Save quality metrics report"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Prepare report dictionary
        report_dict = {
            'timestamp': report.timestamp,
            'config_path': report.config_path,
            'storage_path': report.storage_path,
            'total_images_analyzed': report.total_images_analyzed,

            'format_comparison': {
                'dicom_metrics': report.dicom_avg_metrics,
                'tiff_metrics': report.tiff_avg_metrics,
                'png_metrics': report.png_avg_metrics
            },

            'preservation_rates': {
                'pixel_preservation': report.pixel_preservation_rate,
                'bit_depth_preservation': report.bit_depth_preservation_rate,
                'dynamic_range_preservation': report.dynamic_range_preservation_rate
            },

            'statistical_tests': report.statistical_tests,
            'recommendations': report.recommendations,

            'summary_statistics': {
                'avg_noise_original': report.dicom_avg_metrics.get('noise', 0),
                'avg_noise_tiff': report.tiff_avg_metrics.get('noise', 0),
                'avg_brightness_original': report.dicom_avg_metrics.get('brightness', 0),
                'avg_brightness_tiff': report.tiff_avg_metrics.get('brightness', 0),
                'avg_uniformity_original': report.dicom_avg_metrics.get('uniformity', 0),
                'avg_uniformity_tiff': report.tiff_avg_metrics.get('uniformity', 0),
                'avg_psnr': report.tiff_avg_metrics.get('avg_psnr', 0)
            }
        }

        # Save JSON report
        json_path = output_path.with_suffix('.json')
        with open(json_path, 'w') as f:
            json.dump(report_dict, f, indent=2, default=str)

        logger.info(f"Report saved to {json_path}")

        # Save detailed CSV
        csv_path = output_path.with_suffix('.csv')
        self._save_detailed_csv(report, csv_path)

        return json_path

    def _save_detailed_csv(self, report: QualityMetricsReport, csv_path: Path):
        """Save detailed CSV with all metrics"""
        rows = []

        for metrics in report.image_metrics:
            row = {
                'image_hash': metrics.image_hash,
                'patient_id': metrics.patient_id,
                'modality': metrics.modality,
                'file_type': metrics.file_type,

                # Nogueira-Reis metrics
                'original_noise': metrics.image_noise,
                'original_brightness': metrics.image_brightness,
                'original_uniformity': metrics.image_uniformity,

                'tiff_noise': metrics.tiff_noise,
                'tiff_brightness': metrics.tiff_brightness,
                'tiff_uniformity': metrics.tiff_uniformity,
                'tiff_psnr': metrics.tiff_psnr,

                'png_noise': metrics.png_noise,
                'png_brightness': metrics.png_brightness,
                'png_uniformity': metrics.png_uniformity,
                'png_psnr': metrics.png_psnr,

                # Preservation metrics
                'bit_depth_preserved': metrics.bit_depth_preserved,
                'pixel_range_preserved': metrics.pixel_value_range_preserved,
                'original_min': metrics.original_min_value,
                'original_max': metrics.original_max_value,
                'converted_min': metrics.converted_min_value,
                'converted_max': metrics.converted_max_value,

                # Additional metrics
                'histogram_mean': metrics.histogram_mean,
                'histogram_std': metrics.histogram_std,
                'histogram_skewness': metrics.histogram_skewness,
                'histogram_kurtosis': metrics.histogram_kurtosis,
                'dynamic_range': metrics.dynamic_range,

                # Quality scores
                'edge_preservation': metrics.edge_preservation_score,
                'sharpening_quality': metrics.sharpening_quality_score,

                # Artifacts
                'has_compression_artifacts': metrics.has_compression_artifacts,
                'has_blocking_artifacts': metrics.has_blocking_artifacts,
                'has_ringing_artifacts': metrics.has_ringing_artifacts
            }
            rows.append(row)

        # Create DataFrame and save
        df = pd.DataFrame(rows)
        df.to_csv(csv_path, index=False)

        logger.info(f"Detailed CSV saved to {csv_path}")

    def print_summary(self, report: QualityMetricsReport):
        """Print summary to console"""
        print("\n" + "=" * 70)
        print("MEDICAL IMAGE QUALITY METRICS SUMMARY")
        print("Based on Nogueira-Reis et al. Methodology")
        print("=" * 70)

        print(f"\nImages Analyzed: {report.total_images_analyzed}")

        print("\n" + "-" * 70)
        print("FORMAT COMPARISON (Following Nogueira-Reis et al.)")
        print("-" * 70)

        # Create comparison table
        headers = ['Metric', 'DICOM (Original)', 'TIFF', 'PNG', 'Best']
        rows = []

        if report.dicom_avg_metrics:
            # Noise (lower is better)
            noise_row = ['Image Noise↓']
            noise_values = []

            noise_row.append(f"{report.dicom_avg_metrics.get('noise', 0):.3f}")
            noise_values.append(('DICOM', report.dicom_avg_metrics.get('noise', float('inf'))))

            if report.tiff_avg_metrics:
                noise_row.append(f"{report.tiff_avg_metrics.get('noise', 0):.3f}")
                noise_values.append(('TIFF', report.tiff_avg_metrics.get('noise', float('inf'))))
            else:
                noise_row.append('N/A')

            if report.png_avg_metrics:
                noise_row.append(f"{report.png_avg_metrics.get('noise', 0):.3f}")
                noise_values.append(('PNG', report.png_avg_metrics.get('noise', float('inf'))))
            else:
                noise_row.append('N/A')

            best_noise = min(noise_values, key=lambda x: x[1])[0]
            noise_row.append(best_noise)
            rows.append(noise_row)

            # Brightness
            brightness_row = ['Brightness',
                              f"{report.dicom_avg_metrics.get('brightness', 0):.1f}",
                              f"{report.tiff_avg_metrics.get('brightness', 0):.1f}" if report.tiff_avg_metrics else 'N/A',
                              f"{report.png_avg_metrics.get('brightness', 0):.1f}" if report.png_avg_metrics else 'N/A',
                              '—']
            rows.append(brightness_row)

            # Uniformity (lower SD is better)
            uniform_row = ['Uniformity↓',
                           f"{report.dicom_avg_metrics.get('uniformity', 0):.3f}",
                           f"{report.tiff_avg_metrics.get('uniformity', 0):.3f}" if report.tiff_avg_metrics else 'N/A',
                           f"{report.png_avg_metrics.get('uniformity', 0):.3f}" if report.png_avg_metrics else 'N/A',
                           '—']
            rows.append(uniform_row)

            # PSNR
            if report.tiff_avg_metrics and 'avg_psnr' in report.tiff_avg_metrics:
                psnr_row = ['PSNR (dB)↑', '—',
                            f"{report.tiff_avg_metrics['avg_psnr']:.1f}",
                            f"{report.png_avg_metrics.get('avg_psnr', 0):.1f}" if report.png_avg_metrics else 'N/A',
                            '—']
                rows.append(psnr_row)

        # Print table
        for row in [headers] + rows:
            print(f"{row[0]:<20} {row[1]:<15} {row[2]:<15} {row[3]:<15} {row[4]:<10}")

        print("\n" + "-" * 70)
        print("QUALITY PRESERVATION")
        print("-" * 70)

        print(f"Pixel Value Preservation: {report.pixel_preservation_rate:.1f}%")
        print(f"Bit Depth Preservation:   {report.bit_depth_preservation_rate:.1f}%")
        print(f"Dynamic Range Preserved:  {report.dynamic_range_preservation_rate:.1f}%")

        if report.statistical_tests:
            print("\n" + "-" * 70)
            print("STATISTICAL ANALYSIS")
            print("-" * 70)

            for test_name, test_results in report.statistical_tests.items():
                print(f"\n{test_name}:")
                print(f"  Test: {test_results.get('test', 'N/A')}")
                if 'p_value' in test_results:
                    print(f"  p-value: {test_results['p_value']:.4f}")
                    print(f"  Result: {test_results.get('interpretation', 'N/A')}")

        if report.recommendations:
            print("\n" + "-" * 70)
            print("RECOMMENDATIONS")
            print("-" * 70)

            for i, rec in enumerate(report.recommendations, 1):
                print(f"\n{i}. {rec}")

        print("\n" + "=" * 70)

        # Overall assessment
        if report.pixel_preservation_rate > 95 and report.bit_depth_preservation_rate > 90:
            print("✅ EXCELLENT: Pipeline maintains diagnostic image quality")
        elif report.pixel_preservation_rate > 90:
            print("⚠️  GOOD: Pipeline generally preserves quality with minor issues")
        else:
            print("❌ NEEDS IMPROVEMENT: Significant quality preservation issues detected")

        print("=" * 70 + "\n")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Medical Image Quality Metrics Analyzer",
        epilog="Based on Nogueira-Reis et al. research on DICOM image quality"
    )

    parser.add_argument('config_path', help='Path to config.yaml')
    parser.add_argument('-n', '--num-samples', type=int, default=100,
                        help='Number of images to analyze (default: 100)')
    parser.add_argument('-o', '--output', default='quality_metrics_report',
                        help='Output path for report (without extension)')
    parser.add_argument('--visual', action='store_true',
                        help='Generate visual report with plots')
    parser.add_argument('--workers', type=int, default=8,
                        help='Number of parallel workers')

    args = parser.parse_args()

    # Create analyzer
    analyzer = MedicalImageQualityAnalyzer(
        config_path=args.config_path,
        sample_size=args.num_samples
    )

    # Run analysis
    print("Starting quality metrics analysis...")
    report = analyzer.run_quality_analysis(max_workers=args.workers)

    # Print summary
    analyzer.print_summary(report)

    # Save report
    analyzer.save_report(report, args.output)

    # Generate visual report if requested
    if args.visual:
        import os
        output_dir = os.path.dirname(args.output) if os.path.dirname(args.output) else '.'
        analyzer.generate_visual_report(report, output_dir)

    print(f"\nReport saved to {args.output}.json")
    print(f"Detailed metrics saved to {args.output}.csv")


if __name__ == "__main__":
    main()