"""
Patient Storage Manager for ADNI Knowledge Graph Enhancement
Implements patient-centric directory structure with quality preservation
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
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class PatientImageMetadata:
    """Metadata for patient images"""
    patient_id: str
    modality: str
    session_date: str
    image_hash: str
    file_paths: Dict[str, str]
    dicom_metadata: Dict[str, Any]
    processing_timestamp: str
    quality_metrics: Optional[Dict[str, float]] = None


@dataclass
class StorageMetadata:
    """Storage metadata for processed images"""
    storage_id: str
    patient_id: str
    study_id: str
    series_id: str
    storage_timestamp: str
    file_paths: Dict[str, str]
    dimensions: List[int]
    voxel_spacing: Optional[List[float]]
    bits_per_pixel: int
    checksums: Dict[str, str]
    quality_metrics: Dict[str, float]


class PatientStorageManager:
    """
    Manages patient-centric directory structure for medical images
    Implements the directory structure: diagnostic/{patient_id}/{modality}/{session_date}/
    """
    
    def __init__(self, base_storage_path: str = "outputs"):
        """
        Initialize patient storage manager
        
        Args:
            base_storage_path: Root directory for image storage
        """
        self.base_path = Path(base_storage_path)
        self.diagnostic_path = self.base_path / "diagnostic"
        self.metadata_path = self.base_path / "metadata"
        
        # Create base directories
        self.diagnostic_path.mkdir(parents=True, exist_ok=True)
        self.metadata_path.mkdir(parents=True, exist_ok=True)
    
    def create_patient_directory_structure(self, patient_id: str, modality: str, session_date: str) -> Path:
        """
        Create patient-based directory structure
        
        Args:
            patient_id: Patient identifier
            modality: Image modality (MRI, PET, etc.)
            session_date: Session date in YYYY-MM-DD format
            
        Returns:
            Path to the patient session directory
        """
        # Create directory structure: diagnostic/{patient_id}/{modality}/{session_date}/
        patient_dir = self.diagnostic_path / patient_id / modality / session_date
        patient_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Created directory structure: {patient_dir}")
        return patient_dir
    
    def generate_image_hash(self, image_data: np.ndarray) -> str:
        """
        Generate hash-based filename for deduplication
        
        Args:
            image_data: Image array data
            
        Returns:
            SHA-256 hash of the image data
        """
        # Convert image data to bytes for hashing
        image_bytes = image_data.tobytes()
        hash_sha256 = hashlib.sha256(image_bytes)
        return hash_sha256.hexdigest()
    
    def store_patient_image(self, 
                           patient_id: str,
                           modality: str, 
                           session_date: str,
                           image_data: Dict[str, Any],
                           dicom_metadata: Dict[str, Any]) -> PatientImageMetadata:
        """
        Store patient image with organized file structure
        
        Args:
            patient_id: Patient identifier
            modality: Image modality
            session_date: Session date
            image_data: Dictionary containing image arrays and metadata
            dicom_metadata: DICOM metadata
            
        Returns:
            PatientImageMetadata with storage information
        """
        # Create directory structure
        session_dir = self.create_patient_directory_structure(patient_id, modality, session_date)
        
        # Generate image hash for deduplication
        if 'png_array' in image_data:
            image_hash = self.generate_image_hash(image_data['png_array'])
        elif 'original_pixel_array' in image_data:
            image_hash = self.generate_image_hash(image_data['original_pixel_array'])
        else:
            image_hash = hashlib.sha256(f"{patient_id}_{modality}_{session_date}".encode()).hexdigest()[:16]
        
        file_paths = {}
        
        # Store DICOM file if available
        if 'original_pixel_array' in image_data:
            dicom_path = session_dir / f"{image_hash}.dcm"
            # Note: In real implementation, we would save the original DICOM file
            # For now, we'll just record the path
            file_paths['dicom'] = str(dicom_path)
        
        # Store PNG file
        if 'png_array' in image_data:
            png_path = session_dir / f"{image_hash}.png"
            self._save_png_image(image_data['png_array'], png_path, image_data.get('png_mode', 'L'))
            file_paths['png'] = str(png_path)
        
        # Store thumbnail
        if 'thumbnail_array' in image_data:
            thumbnail_path = session_dir / f"{image_hash}_thumb.png"
            self._save_png_image(image_data['thumbnail_array'], thumbnail_path, 'L')
            file_paths['thumbnail'] = str(thumbnail_path)
        
        # Create patient image metadata
        patient_metadata = PatientImageMetadata(
            patient_id=patient_id,
            modality=modality,
            session_date=session_date,
            image_hash=image_hash,
            file_paths=file_paths,
            dicom_metadata=dicom_metadata,
            processing_timestamp=datetime.now().isoformat(),
            quality_metrics=image_data.get('quality_metrics')
        )
        
        # Store metadata JSON
        self._store_patient_metadata(patient_metadata)
        
        # Update patient summary
        self._update_patient_summary(patient_id, patient_metadata)
        
        return patient_metadata
    
    def _save_png_image(self, image_array: np.ndarray, file_path: Path, mode: str):
        """Save image array as PNG file"""
        try:
            if mode == 'I;16':
                # 16-bit grayscale
                pil_image = Image.fromarray(image_array, mode='I;16')
            else:
                # 8-bit grayscale
                pil_image = Image.fromarray(image_array, mode='L')
            
            pil_image.save(file_path, 'PNG')
            logger.info(f"Saved PNG image: {file_path}")
            
        except Exception as e:
            logger.error(f"Error saving PNG image {file_path}: {e}")
            raise
    
    def _store_patient_metadata(self, patient_metadata: PatientImageMetadata):
        """Store patient image metadata as JSON"""
        metadata_file = self.metadata_path / f"{patient_metadata.image_hash}.json"
        
        try:
            with open(metadata_file, 'w') as f:
                json.dump(asdict(patient_metadata), f, indent=2, default=str)
            
            logger.info(f"Stored metadata: {metadata_file}")
            
        except Exception as e:
            logger.error(f"Error storing metadata {metadata_file}: {e}")
            raise
    
    def _update_patient_summary(self, patient_id: str, patient_metadata: PatientImageMetadata):
        """Update or create patient summary JSON"""
        summary_file = self.diagnostic_path / patient_id / "patient_summary.json"
        
        # Load existing summary or create new one
        if summary_file.exists():
            try:
                with open(summary_file, 'r') as f:
                    summary = json.load(f)
            except Exception as e:
                logger.warning(f"Error loading patient summary {summary_file}: {e}")
                summary = self._create_empty_patient_summary(patient_id)
        else:
            summary = self._create_empty_patient_summary(patient_id)
            # Create patient directory if it doesn't exist
            summary_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Update summary with new image
        modality = patient_metadata.modality
        session_date = patient_metadata.session_date
        
        if modality not in summary['modalities']:
            summary['modalities'][modality] = {}
        
        if session_date not in summary['modalities'][modality]:
            summary['modalities'][modality][session_date] = []
        
        # Add image info to summary
        image_info = {
            'image_hash': patient_metadata.image_hash,
            'file_paths': patient_metadata.file_paths,
            'processing_timestamp': patient_metadata.processing_timestamp,
            'quality_metrics': patient_metadata.quality_metrics
        }
        
        summary['modalities'][modality][session_date].append(image_info)
        summary['last_updated'] = datetime.now().isoformat()
        summary['total_images'] += 1
        
        # Save updated summary
        try:
            with open(summary_file, 'w') as f:
                json.dump(summary, f, indent=2, default=str)
            
            logger.info(f"Updated patient summary: {summary_file}")
            
        except Exception as e:
            logger.error(f"Error updating patient summary {summary_file}: {e}")
            raise
    
    def _create_empty_patient_summary(self, patient_id: str) -> Dict[str, Any]:
        """Create empty patient summary structure"""
        return {
            'patient_id': patient_id,
            'created': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'total_images': 0,
            'modalities': {}
        }
    
    def get_patient_summary(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Get patient summary information"""
        summary_file = self.diagnostic_path / patient_id / "patient_summary.json"
        
        if not summary_file.exists():
            return None
        
        try:
            with open(summary_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading patient summary {summary_file}: {e}")
            return None
    
    def process_dicom_for_storage(self, dicom_path: str, patient_id: str, 
                                 study_id: str, series_id: str) -> 'StorageMetadata':
        """
        Process DICOM file for storage (simplified implementation)
        
        Args:
            dicom_path: Path to DICOM file
            patient_id: Patient identifier
            study_id: Study identifier
            series_id: Series identifier
            
        Returns:
            Storage metadata object
        """
        try:
            # Read DICOM file
            dicom_data = pydicom.dcmread(dicom_path)
            
            # Extract basic metadata
            modality = getattr(dicom_data, 'Modality', 'UNKNOWN')
            study_date = getattr(dicom_data, 'StudyDate', datetime.now().strftime('%Y%m%d'))
            
            # Format study date
            if len(study_date) == 8:
                formatted_date = f"{study_date[:4]}-{study_date[4:6]}-{study_date[6:8]}"
            else:
                formatted_date = datetime.now().strftime('%Y-%m-%d')
            
            # Get image data
            image_array = dicom_data.pixel_array
            
            # Store the image using existing method
            metadata = self.store_patient_image(
                image_array=image_array,
                patient_id=patient_id,
                modality=modality,
                session_date=formatted_date,
                dicom_metadata={
                    'StudyInstanceUID': getattr(dicom_data, 'StudyInstanceUID', ''),
                    'SeriesInstanceUID': getattr(dicom_data, 'SeriesInstanceUID', ''),
                    'SOPInstanceUID': getattr(dicom_data, 'SOPInstanceUID', ''),
                    'Modality': modality,
                    'StudyDate': study_date
                }
            )
            
            # Create storage metadata object
            storage_metadata = StorageMetadata(
                storage_id=metadata.image_hash,
                patient_id=patient_id,
                study_id=study_id,
                series_id=series_id,
                storage_timestamp=metadata.processing_timestamp,
                file_paths=metadata.file_paths,
                dimensions=list(image_array.shape) if len(image_array.shape) >= 2 else [0, 0],
                voxel_spacing=self._extract_voxel_spacing(dicom_data),
                bits_per_pixel=getattr(dicom_data, 'BitsAllocated', 16),
                checksums={'diagnostic': metadata.image_hash},
                quality_metrics=self._calculate_quality_metrics(image_array)
            )
            
            return storage_metadata
            
        except Exception as e:
            logger.error(f"Failed to process DICOM {dicom_path}: {e}")
            raise
    
    def _extract_voxel_spacing(self, dicom_data) -> Optional[List[float]]:
        """Extract voxel spacing from DICOM data"""
        try:
            pixel_spacing = getattr(dicom_data, 'PixelSpacing', None)
            slice_thickness = getattr(dicom_data, 'SliceThickness', None)
            
            if pixel_spacing and slice_thickness:
                return [float(pixel_spacing[0]), float(pixel_spacing[1]), float(slice_thickness)]
            elif pixel_spacing:
                return [float(pixel_spacing[0]), float(pixel_spacing[1]), 1.0]
            else:
                return None
        except:
            return None
    
    def _calculate_quality_metrics(self, image_array: np.ndarray) -> Dict[str, float]:
        """Calculate basic quality metrics for an image"""
        try:
            # Convert to float for calculations
            img_float = image_array.astype(np.float64)
            
            # Signal-to-noise ratio (simplified)
            mean_signal = np.mean(img_float)
            std_noise = np.std(img_float)
            snr = mean_signal / std_noise if std_noise > 0 else 0
            
            # Entropy
            hist, _ = np.histogram(img_float, bins=256, density=True)
            hist = hist[hist > 0]  # Remove zeros
            entropy = -np.sum(hist * np.log2(hist))
            
            # Contrast (standard deviation)
            contrast = float(std_noise)
            
            return {
                'snr': float(snr),
                'entropy': float(entropy),
                'contrast': contrast
            }
        except Exception as e:
            logger.warning(f"Failed to calculate quality metrics: {e}")
            return {'snr': 0.0, 'entropy': 0.0, 'contrast': 0.0}

    def get_patient_images(self, patient_id: str, modality: Optional[str] = None) -> List[PatientImageMetadata]:
        """Get list of images for a patient"""
        summary = self.get_patient_summary(patient_id)
        if not summary:
            return []
        
        images = []
        modalities = [modality] if modality else summary['modalities'].keys()
        
        for mod in modalities:
            if mod in summary['modalities']:
                for session_date, session_images in summary['modalities'][mod].items():
                    for image_info in session_images:
                        # Load full metadata
                        metadata_file = self.metadata_path / f"{image_info['image_hash']}.json"
                        if metadata_file.exists():
                            try:
                                with open(metadata_file, 'r') as f:
                                    metadata_dict = json.load(f)
                                    images.append(PatientImageMetadata(**metadata_dict))
                            except Exception as e:
                                logger.error(f"Error loading image metadata {metadata_file}: {e}")
        
        return images

