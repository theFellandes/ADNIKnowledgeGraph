"""
Enhanced image processing utilities for DICOM and standard image formats with quality preservation
"""

import os
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
from PIL import Image
import pydicom
from io import BytesIO
from skimage.metrics import peak_signal_noise_ratio, structural_similarity
import cv2
from datetime import datetime

logger = logging.getLogger(__name__)


class ImageQualityAnalyzer:
    """Comprehensive image quality analysis and validation for medical imaging"""
    
    def __init__(self, 
                 min_psnr: float = 30.0, 
                 min_ssim: float = 0.8,
                 min_snr: float = 10.0,
                 min_contrast: float = 20.0):
        """
        Initialize quality analyzer
        
        Args:
            min_psnr: Minimum acceptable PSNR value
            min_ssim: Minimum acceptable SSIM value
            min_snr: Minimum acceptable Signal-to-Noise Ratio
            min_contrast: Minimum acceptable contrast value
        """
        self.min_psnr = min_psnr
        self.min_ssim = min_ssim
        self.min_snr = min_snr
        self.min_contrast = min_contrast
        self.quality_thresholds = {
            'excellent': {'psnr': 40.0, 'ssim': 0.95, 'snr': 20.0},
            'good': {'psnr': 35.0, 'ssim': 0.85, 'snr': 15.0},
            'acceptable': {'psnr': 30.0, 'ssim': 0.8, 'snr': 10.0},
            'poor': {'psnr': 25.0, 'ssim': 0.7, 'snr': 5.0}
        }
    
    def calculate_psnr(self, original: np.ndarray, processed: np.ndarray) -> float:
        """Calculate Peak Signal-to-Noise Ratio between original and processed images"""
        try:
            # Ensure both images have the same shape
            if original.shape != processed.shape:
                processed = cv2.resize(processed, (original.shape[1], original.shape[0]))
            
            return peak_signal_noise_ratio(original, processed, data_range=255)
        except Exception as e:
            logger.error(f"Error calculating PSNR: {e}")
            return 0.0
    
    def calculate_ssim(self, original: np.ndarray, processed: np.ndarray) -> float:
        """Calculate Structural Similarity Index between original and processed images"""
        try:
            # Ensure both images have the same shape
            if original.shape != processed.shape:
                processed = cv2.resize(processed, (original.shape[1], original.shape[0]))
            
            # Convert to grayscale if needed
            if len(original.shape) == 3:
                original = cv2.cvtColor(original, cv2.COLOR_RGB2GRAY)
            if len(processed.shape) == 3:
                processed = cv2.cvtColor(processed, cv2.COLOR_RGB2GRAY)
            
            return structural_similarity(original, processed, data_range=255)
        except Exception as e:
            logger.error(f"Error calculating SSIM: {e}")
            return 0.0
    
    def calculate_snr(self, image: np.ndarray) -> float:
        """Calculate Signal-to-Noise Ratio for medical image quality assessment"""
        try:
            # Use the method from medical imaging literature
            # Signal: mean of pixels above 75th percentile
            # Noise: std of pixels below 25th percentile (background)
            signal_threshold = np.percentile(image, 75)
            noise_threshold = np.percentile(image, 25)
            
            signal_pixels = image[image >= signal_threshold]
            noise_pixels = image[image <= noise_threshold]
            
            if len(signal_pixels) == 0 or len(noise_pixels) == 0:
                return 0.0
            
            signal = np.mean(signal_pixels)
            noise = np.std(noise_pixels)
            
            return float(signal / noise) if noise > 0 else 0.0
        except Exception as e:
            logger.error(f"Error calculating SNR: {e}")
            return 0.0
    
    def calculate_contrast(self, image: np.ndarray) -> float:
        """Calculate image contrast using standard deviation"""
        try:
            return float(np.std(image))
        except Exception as e:
            logger.error(f"Error calculating contrast: {e}")
            return 0.0
    
    def calculate_sharpness(self, image: np.ndarray) -> float:
        """Calculate image sharpness using Laplacian variance"""
        try:
            if len(image.shape) == 3:
                image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            
            laplacian = cv2.Laplacian(image.astype(np.float32), cv2.CV_64F)
            return float(laplacian.var())
        except Exception as e:
            logger.error(f"Error calculating sharpness: {e}")
            return 0.0
    
    def calculate_entropy(self, image: np.ndarray) -> float:
        """Calculate image entropy (information content)"""
        try:
            hist, _ = np.histogram(image.flatten(), bins=256, range=(0, 256))
            hist = hist[hist > 0]  # Remove zero entries
            prob = hist / hist.sum()
            return float(-np.sum(prob * np.log2(prob)))
        except Exception as e:
            logger.error(f"Error calculating entropy: {e}")
            return 0.0
    
    def detect_artifacts(self, image: np.ndarray) -> Dict[str, Any]:
        """Detect common imaging artifacts"""
        artifacts = {
            'motion_blur': False,
            'noise_level': 'low',
            'intensity_uniformity': 'good',
            'edge_preservation': 'good'
        }
        
        try:
            # Motion blur detection using edge analysis
            edges = cv2.Canny(image.astype(np.uint8), 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            artifacts['motion_blur'] = edge_density < 0.05  # Low edge density indicates blur
            
            # Noise level assessment
            noise_std = np.std(image - cv2.GaussianBlur(image.astype(np.float32), (5, 5), 0))
            if noise_std > 15:
                artifacts['noise_level'] = 'high'
            elif noise_std > 8:
                artifacts['noise_level'] = 'medium'
            else:
                artifacts['noise_level'] = 'low'
            
            # Intensity uniformity (for background regions)
            # Simple check using coefficient of variation in low-intensity regions
            background_mask = image < np.percentile(image, 25)
            if np.sum(background_mask) > 0:
                background_pixels = image[background_mask]
                cv_background = np.std(background_pixels) / (np.mean(background_pixels) + 1e-6)
                if cv_background > 0.3:
                    artifacts['intensity_uniformity'] = 'poor'
                elif cv_background > 0.15:
                    artifacts['intensity_uniformity'] = 'fair'
            
        except Exception as e:
            logger.error(f"Error detecting artifacts: {e}")
        
        return artifacts
    
    def comprehensive_quality_analysis(self, 
                                     original: np.ndarray, 
                                     processed: np.ndarray) -> Dict[str, Any]:
        """
        Perform comprehensive quality analysis comparing original and processed images
        
        Returns:
            Dictionary with comprehensive quality metrics and analysis
        """
        # Basic quality metrics
        psnr = self.calculate_psnr(original, processed)
        ssim = self.calculate_ssim(original, processed)
        
        # Individual image metrics
        original_snr = self.calculate_snr(original)
        processed_snr = self.calculate_snr(processed)
        
        original_contrast = self.calculate_contrast(original)
        processed_contrast = self.calculate_contrast(processed)
        
        original_sharpness = self.calculate_sharpness(original)
        processed_sharpness = self.calculate_sharpness(processed)
        
        original_entropy = self.calculate_entropy(original)
        processed_entropy = self.calculate_entropy(processed)
        
        # Artifact detection
        processed_artifacts = self.detect_artifacts(processed)
        
        # Quality assessment
        quality_passed = (psnr >= self.min_psnr and 
                         ssim >= self.min_ssim and 
                         processed_snr >= self.min_snr and
                         processed_contrast >= self.min_contrast)
        
        # Determine quality grade
        quality_grade = self._determine_quality_grade(psnr, ssim, processed_snr)
        
        # Calculate preservation ratios
        snr_preservation = processed_snr / (original_snr + 1e-6)
        contrast_preservation = processed_contrast / (original_contrast + 1e-6)
        sharpness_preservation = processed_sharpness / (original_sharpness + 1e-6)
        entropy_preservation = processed_entropy / (original_entropy + 1e-6)
        
        return {
            # Comparison metrics
            'psnr': psnr,
            'ssim': ssim,
            
            # Original image metrics
            'original_metrics': {
                'snr': original_snr,
                'contrast': original_contrast,
                'sharpness': original_sharpness,
                'entropy': original_entropy
            },
            
            # Processed image metrics
            'processed_metrics': {
                'snr': processed_snr,
                'contrast': processed_contrast,
                'sharpness': processed_sharpness,
                'entropy': processed_entropy
            },
            
            # Preservation ratios
            'preservation_ratios': {
                'snr_preservation': snr_preservation,
                'contrast_preservation': contrast_preservation,
                'sharpness_preservation': sharpness_preservation,
                'entropy_preservation': entropy_preservation
            },
            
            # Quality assessment
            'quality_passed': quality_passed,
            'quality_grade': quality_grade,
            'quality_score': self._calculate_composite_quality_score(psnr, ssim, processed_snr, processed_contrast),
            
            # Thresholds used
            'thresholds': {
                'min_psnr': self.min_psnr,
                'min_ssim': self.min_ssim,
                'min_snr': self.min_snr,
                'min_contrast': self.min_contrast
            },
            
            # Artifact detection
            'artifacts': processed_artifacts,
            
            # Recommendations
            'recommendations': self._generate_quality_recommendations(
                psnr, ssim, processed_snr, processed_contrast, processed_artifacts
            )
        }
    
    def _determine_quality_grade(self, psnr: float, ssim: float, snr: float) -> str:
        """Determine overall quality grade based on metrics"""
        for grade, thresholds in self.quality_thresholds.items():
            if (psnr >= thresholds['psnr'] and 
                ssim >= thresholds['ssim'] and 
                snr >= thresholds['snr']):
                return grade
        return 'unacceptable'
    
    def _calculate_composite_quality_score(self, psnr: float, ssim: float, 
                                         snr: float, contrast: float) -> float:
        """Calculate composite quality score (0-1 scale)"""
        # Normalize each metric to 0-1 scale
        psnr_norm = min(psnr / 50.0, 1.0)  # Normalize PSNR (50 is excellent)
        ssim_norm = ssim  # SSIM is already 0-1
        snr_norm = min(snr / 30.0, 1.0)  # Normalize SNR (30 is excellent)
        contrast_norm = min(contrast / 100.0, 1.0)  # Normalize contrast
        
        # Weighted average (PSNR and SSIM are most important for medical imaging)
        weights = [0.3, 0.4, 0.2, 0.1]  # PSNR, SSIM, SNR, Contrast
        score = (weights[0] * psnr_norm + 
                weights[1] * ssim_norm + 
                weights[2] * snr_norm + 
                weights[3] * contrast_norm)
        
        return float(score)
    
    def _generate_quality_recommendations(self, psnr: float, ssim: float, 
                                        snr: float, contrast: float, 
                                        artifacts: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on quality analysis"""
        recommendations = []
        
        if psnr < self.min_psnr:
            recommendations.append(f"PSNR ({psnr:.2f}) below threshold ({self.min_psnr}). Consider using lossless compression.")
        
        if ssim < self.min_ssim:
            recommendations.append(f"SSIM ({ssim:.3f}) below threshold ({self.min_ssim}). Image structure may be degraded.")
        
        if snr < self.min_snr:
            recommendations.append(f"SNR ({snr:.2f}) below threshold ({self.min_snr}). Consider noise reduction preprocessing.")
        
        if contrast < self.min_contrast:
            recommendations.append(f"Contrast ({contrast:.2f}) below threshold ({self.min_contrast}). Image may appear flat.")
        
        if artifacts['motion_blur']:
            recommendations.append("Motion blur detected. Check acquisition parameters.")
        
        if artifacts['noise_level'] == 'high':
            recommendations.append("High noise level detected. Consider denoising filters.")
        
        if artifacts['intensity_uniformity'] == 'poor':
            recommendations.append("Poor intensity uniformity. Check for bias field correction.")
        
        if not recommendations:
            recommendations.append("Image quality meets all criteria for diagnostic use.")
        
        return recommendations
    
    def validate_quality(self, original: np.ndarray, processed: np.ndarray) -> Dict[str, Any]:
        """
        Validate image quality by comparing original and processed images
        (Maintained for backward compatibility)
        
        Returns:
            Dictionary with quality metrics and validation results
        """
        return self.comprehensive_quality_analysis(original, processed)
    
    def generate_quality_report(self, quality_analysis: Dict[str, Any], 
                              image_info: Dict[str, Any] = None) -> str:
        """Generate a formatted quality report"""
        report_lines = [
            "=" * 60,
            "MEDICAL IMAGE QUALITY ANALYSIS REPORT",
            "=" * 60,
            ""
        ]
        
        if image_info:
            report_lines.extend([
                f"Image Hash: {image_info.get('image_hash', 'N/A')}",
                f"Patient ID: {image_info.get('patient_id', 'N/A')}",
                f"Modality: {image_info.get('modality', 'N/A')}",
                f"Processing Time: {image_info.get('processing_timestamp', 'N/A')}",
                ""
            ])
        
        # Quality summary
        report_lines.extend([
            "QUALITY SUMMARY:",
            f"  Overall Grade: {quality_analysis['quality_grade'].upper()}",
            f"  Quality Score: {quality_analysis['quality_score']:.3f}/1.000",
            f"  Quality Passed: {'YES' if quality_analysis['quality_passed'] else 'NO'}",
            ""
        ])
        
        # Comparison metrics
        report_lines.extend([
            "COMPARISON METRICS:",
            f"  PSNR: {quality_analysis['psnr']:.2f} dB (threshold: {quality_analysis['thresholds']['min_psnr']})",
            f"  SSIM: {quality_analysis['ssim']:.3f} (threshold: {quality_analysis['thresholds']['min_ssim']})",
            ""
        ])
        
        # Processed image metrics
        pm = quality_analysis['processed_metrics']
        report_lines.extend([
            "PROCESSED IMAGE METRICS:",
            f"  SNR: {pm['snr']:.2f} (threshold: {quality_analysis['thresholds']['min_snr']})",
            f"  Contrast: {pm['contrast']:.2f} (threshold: {quality_analysis['thresholds']['min_contrast']})",
            f"  Sharpness: {pm['sharpness']:.2f}",
            f"  Entropy: {pm['entropy']:.2f}",
            ""
        ])
        
        # Preservation ratios
        pr = quality_analysis['preservation_ratios']
        report_lines.extend([
            "PRESERVATION RATIOS:",
            f"  SNR Preservation: {pr['snr_preservation']:.3f}",
            f"  Contrast Preservation: {pr['contrast_preservation']:.3f}",
            f"  Sharpness Preservation: {pr['sharpness_preservation']:.3f}",
            f"  Entropy Preservation: {pr['entropy_preservation']:.3f}",
            ""
        ])
        
        # Artifacts
        artifacts = quality_analysis['artifacts']
        report_lines.extend([
            "ARTIFACT DETECTION:",
            f"  Motion Blur: {'DETECTED' if artifacts['motion_blur'] else 'NOT DETECTED'}",
            f"  Noise Level: {artifacts['noise_level'].upper()}",
            f"  Intensity Uniformity: {artifacts['intensity_uniformity'].upper()}",
            f"  Edge Preservation: {artifacts['edge_preservation'].upper()}",
            ""
        ])
        
        # Recommendations
        report_lines.extend([
            "RECOMMENDATIONS:",
        ])
        for i, rec in enumerate(quality_analysis['recommendations'], 1):
            report_lines.append(f"  {i}. {rec}")
        
        report_lines.extend([
            "",
            "=" * 60
        ])
        
        return "\n".join(report_lines)


class MedicalImageProcessor:
    """Enhanced medical image processor with quality preservation and comprehensive metadata extraction"""
    
    def __init__(self, 
                 preserve_bit_depth: bool = True,
                 thumbnail_size: Tuple[int, int] = (256, 256),
                 quality_analyzer: Optional[ImageQualityAnalyzer] = None):
        """
        Initialize enhanced medical image processor
        
        Args:
            preserve_bit_depth: Whether to preserve original bit depth in PNG conversion
            thumbnail_size: Size for thumbnail generation
            quality_analyzer: Quality analyzer instance
        """
        self.preserve_bit_depth = preserve_bit_depth
        self.thumbnail_size = thumbnail_size
        self.quality_analyzer = quality_analyzer or ImageQualityAnalyzer()
    
    def process_dicom_with_quality_preservation(self, dicom_path: str) -> Dict[str, Any]:
        """
        Process DICOM file with quality preservation and comprehensive validation
        
        Args:
            dicom_path: Path to DICOM file
            
        Returns:
            Dictionary with processed image data, metadata, and quality metrics
        """
        try:
            # Read DICOM
            ds = pydicom.dcmread(dicom_path)
            
            # Extract comprehensive metadata
            metadata = self._extract_comprehensive_dicom_metadata(ds)
            
            # Generate image hash for deduplication
            image_hash = self._generate_image_hash(dicom_path)
            
            if not hasattr(ds, 'pixel_array'):
                logger.warning(f"No pixel data in DICOM: {dicom_path}")
                return {
                    'success': False,
                    'error': 'No pixel data',
                    'metadata': metadata,
                    'image_hash': image_hash
                }
            
            # Extract pixel data
            original_pixel_array = ds.pixel_array
            
            # Convert to high-quality PNG while preserving bit depth
            png_array, png_mode = self._convert_to_png_array(original_pixel_array)
            
            # Generate optimized thumbnail
            thumbnail_array = self.generate_optimized_thumbnail(png_array, self.thumbnail_size)
            
            # Validate image quality with comprehensive analysis
            quality_metrics = self.quality_analyzer.comprehensive_quality_analysis(
                self._normalize_for_comparison(original_pixel_array),
                self._normalize_for_comparison(png_array)
            )
            
            # Generate quality report if quality analysis was comprehensive
            quality_report = None
            if 'quality_grade' in quality_metrics:
                image_info = {
                    'image_hash': image_hash,
                    'processing_timestamp': datetime.now().isoformat()
                }
                quality_report = self.quality_analyzer.generate_quality_report(quality_metrics, image_info)
                
                # Log quality report for monitoring
                if quality_metrics['quality_passed']:
                    logger.info(f"Image quality validation passed for {image_hash}")
                else:
                    logger.warning(f"Image quality validation failed for {image_hash}")
                    logger.warning(f"Quality report:\n{quality_report}")
            
            return {
                'success': True,
                'image_hash': image_hash,
                'metadata': metadata,
                'original_pixel_array': original_pixel_array,
                'png_array': png_array,
                'png_mode': png_mode,
                'thumbnail_array': thumbnail_array,
                'quality_metrics': quality_metrics,
                'quality_report': quality_report,
                'original_shape': original_pixel_array.shape,
                'original_dtype': str(original_pixel_array.dtype),
                'processing_status': 'completed' if quality_metrics['quality_passed'] else 'quality_warning'
            }
            
        except Exception as e:
            logger.error(f"Error processing DICOM {dicom_path}: {e}")
            return {
                'success': False,
                'error': str(e),
                'image_hash': self._generate_image_hash(dicom_path) if os.path.exists(dicom_path) else None
            }
    
    def _extract_comprehensive_dicom_metadata(self, ds) -> Dict[str, Any]:
        """Extract comprehensive metadata from DICOM dataset"""
        metadata = {}
        
        # Essential patient and study information
        essential_fields = [
            'PatientID', 'PatientName', 'PatientAge', 'PatientSex', 'PatientBirthDate',
            'StudyInstanceUID', 'StudyDate', 'StudyTime', 'StudyDescription',
            'SeriesInstanceUID', 'SeriesDate', 'SeriesTime', 'SeriesDescription', 'SeriesNumber',
            'SOPInstanceUID', 'SOPClassUID', 'InstanceNumber',
            'Modality', 'BodyPartExamined', 'PatientPosition'
        ]
        
        # Image acquisition parameters
        acquisition_fields = [
            'SliceThickness', 'PixelSpacing', 'ImageOrientationPatient',
            'ImagePositionPatient', 'SliceLocation', 'SpacingBetweenSlices',
            'Rows', 'Columns', 'BitsAllocated', 'BitsStored', 'HighBit',
            'PixelRepresentation', 'PhotometricInterpretation',
            'SamplesPerPixel', 'PlanarConfiguration'
        ]
        
        # Equipment information
        equipment_fields = [
            'Manufacturer', 'ManufacturerModelName', 'DeviceSerialNumber',
            'SoftwareVersions', 'InstitutionName', 'StationName'
        ]
        
        # MRI specific fields
        mri_fields = [
            'MagneticFieldStrength', 'ImagingFrequency', 'EchoTime', 'RepetitionTime',
            'InversionTime', 'FlipAngle', 'SequenceName', 'ScanningSequence',
            'SequenceVariant', 'ScanOptions', 'MRAcquisitionType',
            'EchoTrainLength', 'PixelBandwidth'
        ]
        
        # PET specific fields
        pet_fields = [
            'RadiopharmaceuticalInformationSequence', 'Radiopharmaceutical',
            'RadionuclideTotalDose', 'RadiopharmaceuticalStartTime',
            'RadionuclideHalfLife', 'Units', 'DecayCorrection',
            'AttenuationCorrectionMethod', 'ReconstructionMethod',
            'ScatterCorrectionMethod', 'RandomsCorrectionMethod',
            'DeadTimeCorrectionMethod', 'CollimatorType'
        ]
        
        # CT specific fields
        ct_fields = [
            'KVP', 'XRayTubeCurrent', 'ExposureTime', 'FilterType',
            'ConvolutionKernel', 'PatientOrientation', 'GantryDetectorTilt',
            'TableHeight', 'RotationDirection', 'ExposureModulationType'
        ]
        
        all_fields = essential_fields + acquisition_fields + equipment_fields + mri_fields + pet_fields + ct_fields
        
        for field in all_fields:
            if hasattr(ds, field):
                value = getattr(ds, field)
                metadata[field] = self._serialize_dicom_value(value)
        
        # Handle special sequences
        self._extract_sequence_metadata(ds, metadata)
        
        # Add processing timestamp
        from datetime import datetime
        metadata['processing_timestamp'] = datetime.now().isoformat()
        
        return metadata
    
    def _serialize_dicom_value(self, value) -> Any:
        """Serialize DICOM values to JSON-compatible format"""
        if isinstance(value, (list, tuple)):
            return [self._serialize_dicom_value(v) for v in value]
        elif isinstance(value, pydicom.valuerep.DSfloat):
            return float(value)
        elif isinstance(value, pydicom.valuerep.IS):
            return int(value)
        elif isinstance(value, pydicom.uid.UID):
            return str(value)
        elif hasattr(value, 'value'):
            return self._serialize_dicom_value(value.value)
        else:
            return str(value)
    
    def _extract_sequence_metadata(self, ds, metadata: Dict[str, Any]):
        """Extract metadata from DICOM sequences"""
        # Handle PET radiopharmaceutical information
        if hasattr(ds, 'RadiopharmaceuticalInformationSequence'):
            try:
                radio_seq = ds.RadiopharmaceuticalInformationSequence[0]
                radio_info = {}
                for elem in radio_seq:
                    if elem.keyword:
                        radio_info[elem.keyword] = self._serialize_dicom_value(elem.value)
                metadata['RadiopharmaceuticalInfo'] = radio_info
            except Exception as e:
                logger.warning(f"Error extracting radiopharmaceutical info: {e}")
        
        # Handle other important sequences as needed
        sequence_fields = [
            'ReferencedImageSequence',
            'SourceImageSequence',
            'DerivationCodeSequence'
        ]
        
        for seq_field in sequence_fields:
            if hasattr(ds, seq_field):
                try:
                    seq_data = []
                    for item in getattr(ds, seq_field):
                        item_data = {}
                        for elem in item:
                            if elem.keyword:
                                item_data[elem.keyword] = self._serialize_dicom_value(elem.value)
                        seq_data.append(item_data)
                    metadata[seq_field] = seq_data
                except Exception as e:
                    logger.warning(f"Error extracting sequence {seq_field}: {e}")
    
    def _convert_to_png_array(self, pixel_array: np.ndarray) -> Tuple[np.ndarray, str]:
        """Convert DICOM pixel array to PNG-compatible array with quality preservation"""
        if self.preserve_bit_depth and pixel_array.dtype in [np.uint16, np.int16]:
            # For 16-bit images, preserve bit depth
            if pixel_array.dtype == np.int16:
                # Convert signed to unsigned
                pixel_array = pixel_array.astype(np.int32) + 32768
                pixel_array = np.clip(pixel_array, 0, 65535).astype(np.uint16)
            
            return pixel_array, 'I;16'  # 16-bit grayscale
        else:
            # Convert to 8-bit with proper normalization
            if pixel_array.dtype != np.uint8:
                pmin, pmax = pixel_array.min(), pixel_array.max()
                if pmax > pmin:
                    pixel_array = ((pixel_array - pmin) / (pmax - pmin) * 255).astype(np.uint8)
                else:
                    pixel_array = np.zeros_like(pixel_array, dtype=np.uint8)
            
            return pixel_array, 'L'  # 8-bit grayscale
    
    def _generate_thumbnail(self, image_array: np.ndarray) -> np.ndarray:
        """Generate high-quality thumbnail optimized for web display"""
        # Convert to PIL Image for high-quality resizing
        if image_array.dtype == np.uint16:
            # Convert 16-bit to 8-bit for thumbnail with proper scaling
            image_8bit = (image_array / 256).astype(np.uint8)
            pil_image = Image.fromarray(image_8bit, mode='L')
        else:
            pil_image = Image.fromarray(image_array, mode='L')
        
        # Use high-quality resampling
        pil_image.thumbnail(self.thumbnail_size, Image.Resampling.LANCZOS)
        
        return np.array(pil_image)
    
    def generate_optimized_thumbnail(self, image_array: np.ndarray, 
                                   size: Tuple[int, int] = (256, 256),
                                   enhance_contrast: bool = True,
                                   apply_sharpening: bool = True) -> np.ndarray:
        """
        Generate optimized thumbnail with quality enhancements for diagnostic preview
        
        Args:
            image_array: Input image array
            size: Thumbnail size (width, height)
            enhance_contrast: Whether to apply contrast enhancement
            apply_sharpening: Whether to apply sharpening filter
            
        Returns:
            Optimized thumbnail array
        """
        # Normalize to 8-bit for thumbnail processing
        if image_array.dtype == np.uint16:
            # Use full dynamic range for better contrast
            normalized = (image_array / 65535.0 * 255).astype(np.uint8)
        elif image_array.max() > 255:
            # Scale to 8-bit
            pmin, pmax = image_array.min(), image_array.max()
            normalized = ((image_array - pmin) / (pmax - pmin) * 255).astype(np.uint8)
        else:
            normalized = image_array.astype(np.uint8)
        
        # Apply contrast enhancement if requested
        if enhance_contrast:
            normalized = self._enhance_contrast(normalized)
        
        # Convert to PIL for high-quality resizing
        pil_image = Image.fromarray(normalized, mode='L')
        
        # Calculate aspect-preserving size
        original_size = pil_image.size
        aspect_ratio = original_size[0] / original_size[1]
        
        if aspect_ratio > 1:
            # Landscape
            new_width = size[0]
            new_height = int(size[0] / aspect_ratio)
        else:
            # Portrait or square
            new_height = size[1]
            new_width = int(size[1] * aspect_ratio)
        
        # Resize with high-quality resampling
        thumbnail = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Convert back to numpy array
        thumbnail_array = np.array(thumbnail)
        
        # Apply sharpening if requested
        if apply_sharpening:
            thumbnail_array = self._apply_sharpening(thumbnail_array)
        
        return thumbnail_array
    
    def _enhance_contrast(self, image_array: np.ndarray) -> np.ndarray:
        """Apply adaptive contrast enhancement for better thumbnail visibility"""
        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        import cv2
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(image_array)
        return enhanced
    
    def _apply_sharpening(self, image_array: np.ndarray) -> np.ndarray:
        """Apply subtle sharpening to improve thumbnail clarity"""
        import cv2
        # Create sharpening kernel
        kernel = np.array([[-1, -1, -1],
                          [-1,  9, -1],
                          [-1, -1, -1]]) * 0.1
        
        # Apply sharpening
        sharpened = cv2.filter2D(image_array, -1, kernel)
        
        # Blend with original (50% sharpened, 50% original)
        result = cv2.addWeighted(image_array, 0.5, sharpened, 0.5, 0)
        
        return np.clip(result, 0, 255).astype(np.uint8)
    
    def create_thumbnail_with_caching_strategy(self, image_array: np.ndarray, 
                                             image_hash: str,
                                             cache_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Create thumbnail with caching strategy for performance optimization
        
        Args:
            image_array: Input image array
            image_hash: Unique hash for the image
            cache_dir: Directory for caching thumbnails
            
        Returns:
            Dictionary with thumbnail data and caching information
        """
        cache_info = {
            'cache_hit': False,
            'cache_path': None,
            'generation_time': None
        }
        
        # Check cache if directory provided
        if cache_dir:
            cache_path = Path(cache_dir) / f"{image_hash}_thumb.png"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            if cache_path.exists():
                try:
                    # Load cached thumbnail
                    cached_thumbnail = np.array(Image.open(cache_path))
                    cache_info['cache_hit'] = True
                    cache_info['cache_path'] = str(cache_path)
                    
                    return {
                        'thumbnail_array': cached_thumbnail,
                        'cache_info': cache_info
                    }
                except Exception as e:
                    logger.warning(f"Error loading cached thumbnail {cache_path}: {e}")
        
        # Generate new thumbnail
        import time
        start_time = time.time()
        
        thumbnail_array = self.generate_optimized_thumbnail(image_array)
        
        generation_time = time.time() - start_time
        cache_info['generation_time'] = generation_time
        
        # Cache the thumbnail if cache directory provided
        if cache_dir:
            try:
                cache_path = Path(cache_dir) / f"{image_hash}_thumb.png"
                Image.fromarray(thumbnail_array, mode='L').save(cache_path, 'PNG')
                cache_info['cache_path'] = str(cache_path)
                logger.info(f"Cached thumbnail: {cache_path}")
            except Exception as e:
                logger.error(f"Error caching thumbnail: {e}")
        
        return {
            'thumbnail_array': thumbnail_array,
            'cache_info': cache_info
        }
    
    def _normalize_for_comparison(self, array: np.ndarray) -> np.ndarray:
        """Normalize array to 0-255 range for quality comparison"""
        if array.dtype == np.uint8:
            return array
        
        pmin, pmax = array.min(), array.max()
        if pmax > pmin:
            return ((array - pmin) / (pmax - pmin) * 255).astype(np.uint8)
        else:
            return np.zeros_like(array, dtype=np.uint8)
    
    def _generate_image_hash(self, file_path: str) -> str:
        """Generate SHA-256 hash for image deduplication"""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"Error generating hash for {file_path}: {e}")
            return hashlib.sha256(file_path.encode()).hexdigest()


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