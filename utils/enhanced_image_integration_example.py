"""
Example integration of the Enhanced Image Storage System
Demonstrates how to use the MedicalImageProcessor and PatientStorageManager together
"""

import logging
from pathlib import Path
from utils.image_processor import MedicalImageProcessor, ImageQualityAnalyzer
from utils.medical_image_storage import PatientStorageManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_patient_dicom_with_enhanced_system(dicom_path: str, 
                                             patient_id: str, 
                                             modality: str, 
                                             session_date: str,
                                             base_storage_path: str = "outputs"):
    """
    Example function showing how to process a DICOM file with the enhanced system
    
    Args:
        dicom_path: Path to DICOM file
        patient_id: Patient identifier
        modality: Image modality (MRI, PET, etc.)
        session_date: Session date in YYYY-MM-DD format
        base_storage_path: Base path for storage
        
    Returns:
        Dictionary with processing results
    """
    
    # Initialize components
    quality_analyzer = ImageQualityAnalyzer(
        min_psnr=30.0,
        min_ssim=0.8,
        min_snr=10.0,
        min_contrast=20.0
    )
    
    image_processor = MedicalImageProcessor(
        preserve_bit_depth=True,
        thumbnail_size=(256, 256),
        quality_analyzer=quality_analyzer
    )
    
    storage_manager = PatientStorageManager(base_storage_path)
    
    try:
        # Step 1: Process DICOM with quality preservation
        logger.info(f"Processing DICOM: {dicom_path}")
        processing_result = image_processor.process_dicom_with_quality_preservation(dicom_path)
        
        if not processing_result['success']:
            logger.error(f"Failed to process DICOM: {processing_result.get('error')}")
            return processing_result
        
        # Step 2: Store with organized file structure
        logger.info(f"Storing images for patient {patient_id}")
        storage_metadata = storage_manager.store_patient_image(
            patient_id=patient_id,
            modality=modality,
            session_date=session_date,
            image_data=processing_result,
            dicom_metadata=processing_result['metadata']
        )
        
        # Step 3: Log quality report if available
        if processing_result.get('quality_report'):
            logger.info("Quality Analysis Report:")
            logger.info(processing_result['quality_report'])
        
        # Step 4: Return comprehensive results
        return {
            'success': True,
            'patient_id': patient_id,
            'image_hash': processing_result['image_hash'],
            'storage_metadata': storage_metadata,
            'quality_metrics': processing_result['quality_metrics'],
            'file_paths': storage_metadata.file_paths,
            'processing_status': processing_result['processing_status']
        }
        
    except Exception as e:
        logger.error(f"Error in enhanced image processing: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def demonstrate_quality_analysis():
    """
    Demonstrate the quality analysis capabilities
    """
    import numpy as np
    
    # Create sample images for demonstration
    original = np.random.randint(0, 256, (512, 512), dtype=np.uint8)
    
    # Simulate processed image with slight degradation
    processed = original.copy()
    noise = np.random.normal(0, 5, original.shape).astype(np.int16)
    processed = np.clip(processed.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # Initialize quality analyzer
    quality_analyzer = ImageQualityAnalyzer()
    
    # Perform comprehensive analysis
    quality_analysis = quality_analyzer.comprehensive_quality_analysis(original, processed)
    
    # Generate report
    report = quality_analyzer.generate_quality_report(quality_analysis)
    
    print("Sample Quality Analysis Report:")
    print(report)
    
    return quality_analysis


def get_patient_image_summary(patient_id: str, base_storage_path: str = "outputs"):
    """
    Example function to retrieve patient image summary
    """
    storage_manager = PatientStorageManager(base_storage_path)
    
    # Get patient summary
    summary = storage_manager.get_patient_summary(patient_id)
    if summary:
        logger.info(f"Patient {patient_id} has {summary['total_images']} images")
        logger.info(f"Available modalities: {list(summary['modalities'].keys())}")
        return summary
    else:
        logger.warning(f"No images found for patient {patient_id}")
        return None


if __name__ == "__main__":
    # Demonstrate quality analysis with sample data
    print("Demonstrating Enhanced Image Quality Analysis:")
    demonstrate_quality_analysis()