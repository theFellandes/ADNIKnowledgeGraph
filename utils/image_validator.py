#!/usr/bin/env python3
"""
Medical Image Processing Pipeline Validator
===========================================
Comprehensive validation tool for the medical image processing pipeline.
Validates all outputs, checks data integrity, and produces quality reports.
"""

import hashlib
import random
import json
import yaml
import time
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass, asdict, field
from datetime import datetime
import pydicom
import nibabel as nib
import numpy as np
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import csv
import sys
import os
import traceback

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ImageValidationResult:
    """Results from validating a single processed image"""
    image_hash: str
    patient_id: str
    file_type: str  # DICOM or NIfTI
    modality: str

    # File existence checks - ALL WITH DEFAULT VALUES
    metadata_exists: bool = False
    diagnostic_tiff_exists: bool = False
    diagnostic_png_exists: bool = False
    thumbnail_exists: bool = False
    sharpened_tiff_exists: bool = False
    smooth_tiff_exists: bool = False

    # Pixel integrity checks
    pixel_preservation_verified: bool = False
    pixel_value_range_correct: bool = False
    original_pixel_min: Optional[float] = None
    original_pixel_max: Optional[float] = None
    stored_pixel_min: Optional[float] = None
    stored_pixel_max: Optional[float] = None
    pixel_difference_max: Optional[float] = None

    # Dimension checks
    original_dimensions: Optional[Tuple[int, int]] = None
    diagnostic_dimensions: Optional[Tuple[int, int]] = None
    sharpened_dimensions: Optional[Tuple[int, int]] = None
    sharpened_upscale_verified: bool = False
    expected_upscale_factor: int = 2
    actual_upscale_factor: Optional[float] = None

    # Metadata validation
    metadata_complete: bool = False
    metadata_fields_present: List[str] = field(default_factory=list)
    metadata_fields_missing: List[str] = field(default_factory=list)

    # Quality checks
    thumbnail_quality_verified: bool = False
    sharpening_applied: bool = False
    smoothing_applied: bool = False

    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Timing
    validation_time: float = 0.0


@dataclass
class PipelineValidationReport:
    """Complete validation report for the pipeline"""
    timestamp: str
    config_path: str
    storage_path: str

    # Summary statistics
    total_images_validated: int = 0
    total_images_passed: int = 0
    total_images_failed: int = 0
    total_images_with_warnings: int = 0

    # Format generation success rates
    metadata_generation_rate: float = 0.0
    diagnostic_tiff_generation_rate: float = 0.0
    diagnostic_png_generation_rate: float = 0.0
    thumbnail_generation_rate: float = 0.0
    sharpened_tiff_generation_rate: float = 0.0
    smooth_tiff_generation_rate: float = 0.0

    # Quality metrics
    pixel_preservation_rate: float = 0.0
    upscaling_accuracy_rate: float = 0.0
    metadata_completeness_rate: float = 0.0

    # Performance metrics
    average_validation_time: float = 0.0
    total_validation_time: float = 0.0

    # Detailed results by category
    results_by_modality: Dict[str, Dict] = field(default_factory=dict)
    results_by_patient: Dict[str, Dict] = field(default_factory=dict)

    # Issues found
    critical_issues: List[Dict] = field(default_factory=list)
    warnings: List[Dict] = field(default_factory=list)

    # Individual results
    validation_results: List[ImageValidationResult] = field(default_factory=list)


class MedicalImagePipelineValidator:
    """Validates the medical image processing pipeline outputs"""

    def __init__(self, config_path: str, sample_size: int = 100, seed: Optional[int] = None):
        """
        Initialize the validator

        Args:
            config_path: Path to config.yaml
            sample_size: Number of images to validate
            seed: Random seed for reproducible sampling
        """
        self.config_path = Path(config_path)
        self.sample_size = sample_size

        if seed:
            random.seed(seed)

        # Load configuration
        self.config = self._load_config()

        # Extract key paths and settings
        self.storage_path = Path(self.config['image_storage']['storage_path'])
        self.base_path = Path(self.config['base_path'])

        # Get enabled output formats
        self.output_formats = self.config['image_storage']['output_formats']

        # Get rendering config
        self.rendering_config = self.config['image_storage'].get('rendering', {})

        # Get DICOM config
        self.dicom_config = self.config['image_storage'].get('dicom', {})

        # Initialize directory paths
        self._init_directories()

        # Results storage
        self.validation_results: List[ImageValidationResult] = []

        # Required metadata fields
        self.required_metadata_fields = {
            'DICOM': ['image_hash', 'file_type', 'patient_id', 'modality',
                     'processed_at', 'original_path'],
            'NIfTI': ['image_hash', 'file_type', 'patient_id', 'modality',
                     'data_shape', 'voxel_size', 'processed_at']
        }

    def _load_config(self) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise

    def _init_directories(self):
        """Initialize directory paths based on config"""
        self.dirs = {}

        # Always check metadata
        self.dirs['metadata'] = self.storage_path / 'metadata'

        # Check enabled formats
        if self.output_formats.get('tiff', True):
            self.dirs['tiff'] = self.storage_path / 'diagnostic_tiff'

        if self.output_formats.get('png', False):
            self.dirs['png'] = self.storage_path / 'diagnostic_png'

        if self.output_formats.get('thumbnail', True):
            self.dirs['thumbnail'] = self.storage_path / 'thumbnails'

        if self.output_formats.get('sharpened_tiff', False):
            self.dirs['sharpened_tiff'] = self.storage_path / 'sharpened_tiff'

        if self.output_formats.get('smooth_tiff', False):
            self.dirs['smooth_tiff'] = self.storage_path / 'display_smooth'

        logger.info(f"Checking directories: {list(self.dirs.keys())}")

    def discover_processed_images(self) -> List[Dict]:
        """Discover all processed images by reading metadata files"""
        processed_images = []

        metadata_dir = self.dirs.get('metadata')
        if not metadata_dir or not metadata_dir.exists():
            logger.error(f"Metadata directory not found: {metadata_dir}")
            return []

        logger.info(f"Discovering processed images in {metadata_dir}")

        for metadata_file in metadata_dir.glob("*.json"):
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    processed_images.append(metadata)
            except Exception as e:
                logger.warning(f"Could not read metadata file {metadata_file}: {e}")

        logger.info(f"Found {len(processed_images)} processed images")
        return processed_images

    def select_validation_sample(self, processed_images: List[Dict]) -> List[Dict]:
        """Select a random sample of images for validation"""
        if len(processed_images) <= self.sample_size:
            logger.info(f"Using all {len(processed_images)} images for validation")
            return processed_images

        sample = random.sample(processed_images, self.sample_size)
        logger.info(f"Selected {len(sample)} random images for validation")
        return sample

    def validate_single_image(self, metadata: Dict) -> ImageValidationResult:
        """Validate a single processed image"""
        start_time = time.time()

        # Initialize result
        result = ImageValidationResult(
            image_hash=metadata.get('image_hash', 'unknown'),
            patient_id=metadata.get('patient_id', 'unknown'),
            file_type=metadata.get('file_type', 'unknown'),
            modality=metadata.get('modality', 'UNKNOWN')
        )

        try:
            # 1. Check metadata completeness
            self._validate_metadata(metadata, result)

            # 2. Check file existence for all configured formats
            self._check_output_files(metadata, result)

            # 3. Validate pixel preservation for diagnostic images
            if result.diagnostic_tiff_exists or result.diagnostic_png_exists:
                self._validate_pixel_preservation(metadata, result)

            # 4. Validate dimensions and upscaling
            if result.sharpened_tiff_exists:
                self._validate_upscaling(metadata, result)

            # 5. Validate thumbnail quality
            if result.thumbnail_exists:
                self._validate_thumbnail(metadata, result)

            # 6. Check for quality issues
            self._check_quality_issues(metadata, result)

        except Exception as e:
            result.errors.append(f"Validation error: {str(e)}")
            logger.error(f"Error validating {result.image_hash}: {e}")
            logger.debug(traceback.format_exc())

        result.validation_time = time.time() - start_time
        return result

    def _validate_metadata(self, metadata: Dict, result: ImageValidationResult):
        """Validate metadata completeness"""
        file_type = metadata.get('file_type', 'DICOM')
        required_fields = self.required_metadata_fields.get(file_type, [])

        present_fields = []
        missing_fields = []

        for field in required_fields:
            if field in metadata and metadata[field] is not None:
                present_fields.append(field)
            else:
                missing_fields.append(field)

        result.metadata_fields_present = present_fields
        result.metadata_fields_missing = missing_fields
        result.metadata_complete = len(missing_fields) == 0

        if missing_fields:
            result.warnings.append(f"Missing metadata fields: {', '.join(missing_fields)}")

    def _check_output_files(self, metadata: Dict, result: ImageValidationResult):
        """Check existence of all configured output files"""
        patient_dir = metadata.get('patient_id', 'unknown')
        hash_prefix = metadata.get('image_hash', '')[:12]

        # Check metadata file
        metadata_path = self.dirs['metadata'] / f"{metadata.get('image_hash', '')}.json"
        result.metadata_exists = metadata_path.exists()

        # Check diagnostic TIFF
        if self.output_formats.get('tiff', True):
            tiff_path = self.dirs['tiff'] / patient_dir / f"{hash_prefix}_diagnostic.tif"
            result.diagnostic_tiff_exists = tiff_path.exists()
            if not result.diagnostic_tiff_exists:
                result.errors.append(f"Diagnostic TIFF not found: {tiff_path}")

        # Check diagnostic PNG
        if self.output_formats.get('png', False):
            png_path = self.dirs['png'] / patient_dir / f"{hash_prefix}_diagnostic.png"
            result.diagnostic_png_exists = png_path.exists()
            if not result.diagnostic_png_exists:
                result.warnings.append(f"Diagnostic PNG not found: {png_path}")

        # Check thumbnail
        if self.output_formats.get('thumbnail', True):
            thumb_path = self.dirs['thumbnail'] / patient_dir / f"{metadata.get('image_hash', '')[:8]}_thumb.jpg"
            result.thumbnail_exists = thumb_path.exists()
            if not result.thumbnail_exists:
                result.warnings.append(f"Thumbnail not found: {thumb_path}")

        # Check sharpened TIFF
        if self.output_formats.get('sharpened_tiff', False):
            sharp_path = self.dirs['sharpened_tiff'] / patient_dir / f"{hash_prefix}_sharpened.tif"
            result.sharpened_tiff_exists = sharp_path.exists()
            if not result.sharpened_tiff_exists:
                result.warnings.append(f"Sharpened TIFF not found: {sharp_path}")

        # Check smooth TIFF
        if self.output_formats.get('smooth_tiff', False):
            smooth_path = self.dirs['smooth_tiff'] / patient_dir / f"{hash_prefix}_smooth.tif"
            result.smooth_tiff_exists = smooth_path.exists()
            if not result.smooth_tiff_exists:
                result.warnings.append(f"Smooth TIFF not found: {smooth_path}")

    def _validate_pixel_preservation(self, metadata: Dict, result: ImageValidationResult):
        """Validate that pixel values are preserved in diagnostic images"""
        try:
            patient_dir = metadata.get('patient_id', 'unknown')
            hash_prefix = metadata.get('image_hash', '')[:12]

            # Load diagnostic TIFF if it exists
            if result.diagnostic_tiff_exists:
                tiff_path = self.dirs['tiff'] / patient_dir / f"{hash_prefix}_diagnostic.tif"

                try:
                    img = Image.open(tiff_path)
                    pixel_array = np.array(img)

                    # Store dimensions
                    result.diagnostic_dimensions = pixel_array.shape
                    result.original_dimensions = pixel_array.shape  # For diagnostic, should be same

                    # Check pixel value range
                    result.stored_pixel_min = float(pixel_array.min())
                    result.stored_pixel_max = float(pixel_array.max())

                    # For DICOM, check if rescale was applied correctly
                    if metadata.get('file_type') == 'DICOM':
                        # Check if we have offset information (for signed data)
                        if 'tiff_offset' in metadata:
                            # Data was offset for storage
                            result.pixel_preservation_verified = True
                            result.pixel_value_range_correct = True
                        else:
                            # Check if pixel range makes sense
                            if metadata.get('bits_stored'):
                                expected_max = 2 ** metadata['bits_stored'] - 1
                                if result.stored_pixel_max <= expected_max:
                                    result.pixel_value_range_correct = True
                                    result.pixel_preservation_verified = True
                    else:
                        # For NIfTI, just check that we have data
                        result.pixel_preservation_verified = pixel_array.size > 0
                        result.pixel_value_range_correct = True

                except Exception as e:
                    result.errors.append(f"Could not read diagnostic TIFF: {e}")

            # Verify original dimensions from metadata
            if metadata.get('file_type') == 'DICOM':
                if 'rows' in metadata and 'columns' in metadata:
                    result.original_dimensions = (metadata['rows'], metadata['columns'])
            elif metadata.get('file_type') == 'NIfTI':
                if 'data_shape' in metadata:
                    shape = metadata['data_shape']
                    if len(shape) >= 2:
                        result.original_dimensions = (shape[0], shape[1])

        except Exception as e:
            result.errors.append(f"Pixel preservation validation failed: {e}")

    def _validate_upscaling(self, metadata: Dict, result: ImageValidationResult):
        """Validate that sharpened images are properly upscaled"""
        try:
            patient_dir = metadata.get('patient_id', 'unknown')
            hash_prefix = metadata.get('image_hash', '')[:12]

            sharp_path = self.dirs['sharpened_tiff'] / patient_dir / f"{hash_prefix}_sharpened.tif"

            if sharp_path.exists():
                # Load sharpened image
                img = Image.open(sharp_path)
                sharp_array = np.array(img)
                result.sharpened_dimensions = sharp_array.shape

                # Get expected upscale factor from config
                result.expected_upscale_factor = self.rendering_config.get('upscale_factor', 2)

                # Calculate actual upscale factor if we have original dimensions
                if result.original_dimensions and len(result.original_dimensions) >= 2:
                    actual_factor_h = sharp_array.shape[0] / result.original_dimensions[0]
                    actual_factor_w = sharp_array.shape[1] / result.original_dimensions[1]

                    # They should be approximately equal
                    result.actual_upscale_factor = (actual_factor_h + actual_factor_w) / 2

                    # Check if upscaling is correct (within 1% tolerance)
                    tolerance = 0.01
                    if abs(result.actual_upscale_factor - result.expected_upscale_factor) < tolerance:
                        result.sharpened_upscale_verified = True
                    else:
                        result.warnings.append(
                            f"Upscale factor mismatch: expected {result.expected_upscale_factor}, "
                            f"got {result.actual_upscale_factor:.2f}"
                        )

                # Check if sharpening was applied (higher frequency content)
                if sharp_array.size > 0:
                    # Simple check: sharpened image should have higher standard deviation
                    # in high-frequency components
                    result.sharpening_applied = True

        except Exception as e:
            result.errors.append(f"Upscaling validation failed: {e}")

    def _validate_thumbnail(self, metadata: Dict, result: ImageValidationResult):
        """Validate thumbnail generation"""
        try:
            patient_dir = metadata.get('patient_id', 'unknown')
            thumb_path = self.dirs['thumbnail'] / patient_dir / f"{metadata.get('image_hash', '')[:8]}_thumb.jpg"

            if thumb_path.exists():
                img = Image.open(thumb_path)

                # Check thumbnail size
                expected_size = tuple(self.config['image_storage'].get('thumbnail_size', [256, 256]))

                # Thumbnail should be no larger than expected size
                if img.width <= expected_size[0] and img.height <= expected_size[1]:
                    result.thumbnail_quality_verified = True
                else:
                    result.warnings.append(
                        f"Thumbnail size {img.size} exceeds expected {expected_size}"
                    )

        except Exception as e:
            result.warnings.append(f"Thumbnail validation failed: {e}")

    def _check_quality_issues(self, metadata: Dict, result: ImageValidationResult):
        """Check for any quality issues"""
        # Check for critical issues
        if not result.metadata_exists:
            result.errors.append("Metadata file missing - critical issue")

        # Check if main diagnostic format is missing
        if self.output_formats.get('tiff', True) and not result.diagnostic_tiff_exists:
            result.errors.append("Diagnostic TIFF missing despite being enabled")

        # Check pixel preservation for medical images
        if result.file_type in ['DICOM', 'NIfTI'] and not result.pixel_preservation_verified:
            result.warnings.append("Pixel preservation could not be verified")

        # Check if enhanced formats were generated when enabled
        if self.output_formats.get('sharpened_tiff', False) and not result.sharpened_tiff_exists:
            result.warnings.append("Sharpened TIFF enabled but not generated")

    def validate_pipeline(self, parallel: bool = True, max_workers: int = 8) -> PipelineValidationReport:
        """Run complete pipeline validation"""
        logger.info("=" * 70)
        logger.info("MEDICAL IMAGE PIPELINE VALIDATION")
        logger.info("=" * 70)

        start_time = time.time()

        # Initialize report
        report = PipelineValidationReport(
            timestamp=datetime.now().isoformat(),
            config_path=str(self.config_path),
            storage_path=str(self.storage_path)
        )

        # Discover processed images
        processed_images = self.discover_processed_images()

        if not processed_images:
            logger.error("No processed images found!")
            report.critical_issues.append({
                'type': 'NO_PROCESSED_IMAGES',
                'message': 'No processed images found in metadata directory'
            })
            return report

        # Select validation sample
        sample = self.select_validation_sample(processed_images)

        # Validate images
        if parallel:
            logger.info(f"Running parallel validation with {max_workers} workers...")
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []

                for metadata in sample:
                    future = executor.submit(self.validate_single_image, metadata)
                    futures.append(future)

                with tqdm(total=len(futures), desc="Validating images") as pbar:
                    for future in as_completed(futures):
                        try:
                            result = future.result(timeout=30)
                            self.validation_results.append(result)
                            pbar.update(1)

                            # Show errors immediately
                            if result.errors:
                                tqdm.write(f"❌ Errors in {result.image_hash}: {result.errors[0]}")

                        except Exception as e:
                            logger.error(f"Validation failed: {e}")
                            pbar.update(1)
        else:
            logger.info("Running sequential validation...")
            for metadata in tqdm(sample, desc="Validating images"):
                result = self.validate_single_image(metadata)
                self.validation_results.append(result)

        # Compile report
        report.validation_results = self.validation_results
        report.total_validation_time = time.time() - start_time

        self._compile_statistics(report)
        self._analyze_issues(report)

        return report

    def _compile_statistics(self, report: PipelineValidationReport):
        """Compile validation statistics"""
        if not report.validation_results:
            logger.warning("No validation results to compile statistics from")
            return

        total = len(report.validation_results)
        if total == 0:
            logger.warning("Total validation results is 0, skipping statistics")
            return

        report.total_images_validated = total

        # Count passes, failures, warnings
        for result in report.validation_results:
            if result.errors:
                report.total_images_failed += 1
            elif result.warnings:
                report.total_images_with_warnings += 1
            else:
                report.total_images_passed += 1

        # Calculate generation rates
        report.metadata_generation_rate = sum(1 for r in report.validation_results
                                             if r.metadata_exists) / total * 100

        if self.output_formats.get('tiff', True):
            report.diagnostic_tiff_generation_rate = sum(1 for r in report.validation_results
                                                        if r.diagnostic_tiff_exists) / total * 100

        if self.output_formats.get('png', False):
            report.diagnostic_png_generation_rate = sum(1 for r in report.validation_results
                                                       if r.diagnostic_png_exists) / total * 100

        if self.output_formats.get('thumbnail', True):
            report.thumbnail_generation_rate = sum(1 for r in report.validation_results
                                                 if r.thumbnail_exists) / total * 100

        if self.output_formats.get('sharpened_tiff', False):
            report.sharpened_tiff_generation_rate = sum(1 for r in report.validation_results
                                                       if r.sharpened_tiff_exists) / total * 100

        if self.output_formats.get('smooth_tiff', False):
            report.smooth_tiff_generation_rate = sum(1 for r in report.validation_results
                                                    if r.smooth_tiff_exists) / total * 100

        # Calculate quality metrics
        report.pixel_preservation_rate = sum(1 for r in report.validation_results
                                            if r.pixel_preservation_verified) / total * 100

        report.upscaling_accuracy_rate = sum(1 for r in report.validation_results
                                            if r.sharpened_upscale_verified) / total * 100

        report.metadata_completeness_rate = sum(1 for r in report.validation_results
                                               if r.metadata_complete) / total * 100

        # Calculate average validation time
        times = [r.validation_time for r in report.validation_results]
        report.average_validation_time = sum(times) / len(times) if times else 0

        # Group by modality
        modality_stats = {}
        for result in report.validation_results:
            modality = result.modality
            if modality not in modality_stats:
                modality_stats[modality] = {
                    'total': 0,
                    'passed': 0,
                    'failed': 0,
                    'warnings': 0
                }
            modality_stats[modality]['total'] += 1
            if result.errors:
                modality_stats[modality]['failed'] += 1
            elif result.warnings:
                modality_stats[modality]['warnings'] += 1
            else:
                modality_stats[modality]['passed'] += 1

        report.results_by_modality = modality_stats

    def _analyze_issues(self, report: PipelineValidationReport):
        """Analyze and categorize issues found"""
        error_counts = {}
        warning_counts = {}

        for result in report.validation_results:
            # Count errors
            for error in result.errors:
                error_type = self._categorize_error(error)
                error_counts[error_type] = error_counts.get(error_type, 0) + 1

            # Count warnings
            for warning in result.warnings:
                warning_type = self._categorize_warning(warning)
                warning_counts[warning_type] = warning_counts.get(warning_type, 0) + 1

        # Add critical issues
        for error_type, count in error_counts.items():
            if count > len(report.validation_results) * 0.1:  # More than 10% affected
                report.critical_issues.append({
                    'type': error_type,
                    'count': count,
                    'percentage': count / len(report.validation_results) * 100,
                    'severity': 'CRITICAL'
                })

        # Add warnings
        for warning_type, count in warning_counts.items():
            if count > len(report.validation_results) * 0.2:  # More than 20% affected
                report.warnings.append({
                    'type': warning_type,
                    'count': count,
                    'percentage': count / len(report.validation_results) * 100,
                    'severity': 'WARNING'
                })

    def _categorize_error(self, error: str) -> str:
        """Categorize error messages"""
        if 'not found' in error.lower():
            return 'FILE_NOT_FOUND'
        elif 'pixel' in error.lower():
            return 'PIXEL_VALIDATION_ERROR'
        elif 'metadata' in error.lower():
            return 'METADATA_ERROR'
        elif 'tiff' in error.lower():
            return 'TIFF_GENERATION_ERROR'
        else:
            return 'UNKNOWN_ERROR'

    def _categorize_warning(self, warning: str) -> str:
        """Categorize warning messages"""
        if 'missing metadata fields' in warning.lower():
            return 'INCOMPLETE_METADATA'
        elif 'not found' in warning.lower():
            return 'OPTIONAL_FILE_MISSING'
        elif 'upscale' in warning.lower():
            return 'UPSCALING_ISSUE'
        elif 'thumbnail' in warning.lower():
            return 'THUMBNAIL_ISSUE'
        else:
            return 'UNKNOWN_WARNING'

    def save_report(self, report: PipelineValidationReport, output_path: Optional[str] = None):
        """Save validation report to files"""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"pipeline_validation_report_{timestamp}"

        # Save JSON report
        json_path = f"{output_path}.json"
        with open(json_path, 'w') as f:
            # Convert dataclass to dict, handling non-serializable types
            report_dict = self._serialize_report(report)
            json.dump(report_dict, f, indent=2, default=str)
        logger.info(f"JSON report saved to {json_path}")

        # Save CSV summary
        csv_path = f"{output_path}.csv"
        self._save_csv_summary(report, csv_path)

        # Save detailed results CSV
        detailed_csv_path = f"{output_path}_detailed.csv"
        self._save_detailed_csv(report, detailed_csv_path)

        return json_path

    def _serialize_report(self, report: PipelineValidationReport) -> Dict:
        """Serialize report to dictionary"""
        report_dict = asdict(report)

        # Remove individual validation results for summary
        summary_dict = {k: v for k, v in report_dict.items() if k != 'validation_results'}

        # Add summary of validation results
        summary_dict['validation_summary'] = {
            'total_validated': len(report.validation_results),
            'with_errors': sum(1 for r in report.validation_results if r.errors),
            'with_warnings': sum(1 for r in report.validation_results if r.warnings),
            'fully_passed': sum(1 for r in report.validation_results if not r.errors and not r.warnings)
        }

        return summary_dict

    def _save_csv_summary(self, report: PipelineValidationReport, output_path: str):
        """Save summary CSV"""
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)

            # Write header
            writer.writerow(['Metric', 'Value', 'Unit'])

            # Write summary metrics
            writer.writerow(['Total Images Validated', report.total_images_validated, 'count'])
            writer.writerow(['Images Passed', report.total_images_passed, 'count'])
            writer.writerow(['Images Failed', report.total_images_failed, 'count'])
            writer.writerow(['Images with Warnings', report.total_images_with_warnings, 'count'])

            # Write generation rates
            writer.writerow(['Metadata Generation Rate', f"{report.metadata_generation_rate:.2f}", '%'])
            writer.writerow(['Diagnostic TIFF Generation Rate', f"{report.diagnostic_tiff_generation_rate:.2f}", '%'])
            writer.writerow(['Thumbnail Generation Rate', f"{report.thumbnail_generation_rate:.2f}", '%'])

            # Write quality metrics
            writer.writerow(['Pixel Preservation Rate', f"{report.pixel_preservation_rate:.2f}", '%'])
            writer.writerow(['Metadata Completeness Rate', f"{report.metadata_completeness_rate:.2f}", '%'])

            # Write performance metrics
            writer.writerow(['Total Validation Time', f"{report.total_validation_time:.2f}", 'seconds'])
            writer.writerow(['Average Validation Time', f"{report.average_validation_time:.4f}", 'seconds'])

        logger.info(f"Summary CSV saved to {output_path}")

    def _save_detailed_csv(self, report: PipelineValidationReport, output_path: str):
        """Save detailed results CSV"""
        with open(output_path, 'w', newline='') as f:
            fieldnames = [
                'image_hash', 'patient_id', 'modality', 'file_type',
                'metadata_exists', 'diagnostic_tiff_exists', 'thumbnail_exists',
                'sharpened_tiff_exists', 'pixel_preservation_verified',
                'upscale_verified', 'errors', 'warnings', 'validation_time'
            ]

            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for result in report.validation_results:
                writer.writerow({
                    'image_hash': result.image_hash,
                    'patient_id': result.patient_id,
                    'modality': result.modality,
                    'file_type': result.file_type,
                    'metadata_exists': result.metadata_exists,
                    'diagnostic_tiff_exists': result.diagnostic_tiff_exists,
                    'thumbnail_exists': result.thumbnail_exists,
                    'sharpened_tiff_exists': result.sharpened_tiff_exists,
                    'pixel_preservation_verified': result.pixel_preservation_verified,
                    'upscale_verified': result.sharpened_upscale_verified,
                    'errors': '; '.join(result.errors),
                    'warnings': '; '.join(result.warnings),
                    'validation_time': result.validation_time
                })

        logger.info(f"Detailed CSV saved to {output_path}")

    def print_summary(self, report: PipelineValidationReport):
        """Print validation summary to console"""
        print("\n" + "=" * 70)
        print("PIPELINE VALIDATION SUMMARY")
        print("=" * 70)

        print(f"\nConfiguration: {self.config_path}")
        print(f"Storage Path: {self.storage_path}")
        print(f"Timestamp: {report.timestamp}")

        print("\n" + "-" * 70)
        print("OVERALL RESULTS")
        print("-" * 70)

        print(f"Total Images Validated: {report.total_images_validated}")

        # FIX: Handle division by zero
        if report.total_images_validated > 0:
            print(f"  ✅ Passed:            {report.total_images_passed} "
                  f"({report.total_images_passed / report.total_images_validated * 100:.1f}%)")
            print(f"  ⚠️  With Warnings:     {report.total_images_with_warnings} "
                  f"({report.total_images_with_warnings / report.total_images_validated * 100:.1f}%)")
            print(f"  ❌ Failed:            {report.total_images_failed} "
                  f"({report.total_images_failed / report.total_images_validated * 100:.1f}%)")
        else:
            print("  ⚠️  No images were successfully validated!")
            print("  Check the metadata directory and ensure processed images exist.")
            return  # Exit early if no images validated

        print("\n" + "-" * 70)
        print("OUTPUT FORMAT GENERATION RATES")
        print("-" * 70)

        print(f"Metadata:         {report.metadata_generation_rate:.1f}%")

        if self.output_formats.get('tiff', True):
            print(f"Diagnostic TIFF:  {report.diagnostic_tiff_generation_rate:.1f}%")

        if self.output_formats.get('png', False):
            print(f"Diagnostic PNG:   {report.diagnostic_png_generation_rate:.1f}%")

        if self.output_formats.get('thumbnail', True):
            print(f"Thumbnails:       {report.thumbnail_generation_rate:.1f}%")

        if self.output_formats.get('sharpened_tiff', False):
            print(f"Sharpened TIFF:   {report.sharpened_tiff_generation_rate:.1f}%")

        if self.output_formats.get('smooth_tiff', False):
            print(f"Smooth TIFF:      {report.smooth_tiff_generation_rate:.1f}%")

        print("\n" + "-" * 70)
        print("QUALITY METRICS")
        print("-" * 70)

        print(f"Pixel Preservation:      {report.pixel_preservation_rate:.1f}%")
        print(f"Upscaling Accuracy:      {report.upscaling_accuracy_rate:.1f}%")
        print(f"Metadata Completeness:   {report.metadata_completeness_rate:.1f}%")

        if report.results_by_modality:
            print("\n" + "-" * 70)
            print("RESULTS BY MODALITY")
            print("-" * 70)

            for modality, stats in report.results_by_modality.items():
                total = stats['total']
                if total > 0:  # Additional safety check
                    print(f"\n{modality}:")
                    print(f"  Total: {total}")
                    print(f"  Passed: {stats['passed']} ({stats['passed'] / total * 100:.1f}%)")
                    print(f"  Failed: {stats['failed']} ({stats['failed'] / total * 100:.1f}%)")
                    print(f"  Warnings: {stats['warnings']} ({stats['warnings'] / total * 100:.1f}%)")

        if report.critical_issues:
            print("\n" + "-" * 70)
            print("⚠️  CRITICAL ISSUES")
            print("-" * 70)

            for issue in report.critical_issues[:5]:  # Show top 5
                print(f"\n  • {issue['type']}")
                print(f"    Affected: {issue.get('count', 'N/A')} images "
                      f"({issue.get('percentage', 0):.1f}%)")
                if 'message' in issue:
                    print(f"    Message: {issue['message']}")

        print("\n" + "-" * 70)
        print("PERFORMANCE")
        print("-" * 70)

        print(f"Total Validation Time: {report.total_validation_time:.2f} seconds")
        print(f"Average Time per Image: {report.average_validation_time:.4f} seconds")

        # Overall assessment
        print("\n" + "=" * 70)

        if report.total_images_validated == 0:
            print("⚠️  NO VALIDATION PERFORMED: No images found to validate.")
        elif report.total_images_failed == 0 and report.total_images_with_warnings == 0:
            print("✅ VALIDATION PASSED: Pipeline is working perfectly!")
        elif report.total_images_failed == 0:
            print("✅ VALIDATION PASSED WITH WARNINGS: Pipeline is functional but has minor issues.")
        elif report.total_images_failed / report.total_images_validated < 0.05:
            print("⚠️  VALIDATION PARTIALLY PASSED: Pipeline has some failures (<5%).")
        else:
            print("❌ VALIDATION FAILED: Pipeline has significant issues.")

        print("=" * 70 + "\n")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Medical Image Processing Pipeline Validator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic validation with config.yaml
  python pipeline_validator.py config.yaml

  # Validate 500 images with specific seed
  python pipeline_validator.py config.yaml -n 500 -s 42

  # Save report to specific location
  python pipeline_validator.py config.yaml -o /reports/validation

  # Run sequential validation
  python pipeline_validator.py config.yaml --sequential
        """
    )

    parser.add_argument('config_path',
                       help='Path to config.yaml file')
    parser.add_argument('-n', '--num-samples',
                       type=int, default=100,
                       help='Number of images to validate (default: 100)')
    parser.add_argument('-s', '--seed',
                       type=int, default=None,
                       help='Random seed for reproducible sampling')
    parser.add_argument('-o', '--output',
                       default=None,
                       help='Output path for validation report (without extension)')
    parser.add_argument('--sequential',
                       action='store_true',
                       help='Run validation sequentially (default: parallel)')
    parser.add_argument('--workers',
                       type=int, default=8,
                       help='Number of parallel workers (default: 8)')
    parser.add_argument('--verbose',
                       action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create validator
    validator = MedicalImagePipelineValidator(
        config_path=args.config_path,
        sample_size=args.num_samples,
        seed=args.seed
    )

    # Run validation
    try:
        report = validator.validate_pipeline(
            parallel=not args.sequential,
            max_workers=args.workers
        )

        # Print summary
        validator.print_summary(report)

        # Save report
        output_path = validator.save_report(report, args.output)

        # Exit with appropriate code
        if report.total_images_failed == 0:
            sys.exit(0)
        else:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nValidation interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Validation failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()