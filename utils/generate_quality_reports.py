#!/usr/bin/env python3
"""
Data Quality Reports Generator Script
Generates comprehensive data quality reports for ADNI Knowledge Graph
"""

import os
import sys
import logging
from pathlib import Path

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.metadata_generator import MetadataGenerator

# Try to import optional dependencies
try:
    from utils.neo4j_connector import Neo4jConnector
except ImportError:
    Neo4jConnector = None
    logger.warning("Neo4j connector not available")


def main():
    """Generate data quality reports"""
    logger.info("Starting data quality report generation...")
    
    try:
        # Initialize connectors (with error handling for missing services)
        neo4j_connector = None
        
        if Neo4jConnector:
            try:
                # Try to connect to Neo4j
                neo4j_connector = Neo4jConnector(
                    uri="bolt://localhost:7687",
                    user="neo4j",
                    password="password"
                )
                if not neo4j_connector.verify_connection():
                    logger.warning("Neo4j connection failed, proceeding without Neo4j data")
                    neo4j_connector = None
            except Exception as e:
                logger.warning(f"Could not connect to Neo4j: {e}")
        
        # Initialize MetadataGenerator
        metadata_generator = MetadataGenerator(
            neo4j_connector=neo4j_connector,
            elasticsearch_indexer=None,  # Not needed for quality reports
            output_base_path="outputs"
        )
        
        # Generate data quality reports
        logger.info("Generating data completeness analysis...")
        completeness_analysis = metadata_generator._analyze_data_completeness()
        
        logger.info("Generating image quality assessment...")
        image_quality_assessment = metadata_generator._assess_image_quality()
        
        logger.info("Generating family relationship integrity check...")
        family_integrity = metadata_generator._check_family_integrity()
        
        logger.info("Generating processing statistics...")
        processing_stats = metadata_generator._generate_processing_stats()
        
        # Generate complete quality report
        quality_report = metadata_generator.generate_data_quality_reports()
        
        # Generate individual quality report files
        generate_individual_reports(metadata_generator, {
            "completeness_analysis": completeness_analysis,
            "image_quality_assessment": image_quality_assessment,
            "family_integrity": family_integrity,
            "processing_stats": processing_stats
        })
        
        logger.info("Data quality report generation completed successfully!")
        
        # Print summary
        print_quality_summary(quality_report)
        
    except Exception as e:
        logger.error(f"Error generating data quality reports: {e}")
        sys.exit(1)
    
    finally:
        # Clean up connections
        if neo4j_connector:
            neo4j_connector.close()


def generate_individual_reports(metadata_generator, quality_data):
    """Generate individual quality report files"""
    
    # Data completeness report
    if "error" not in quality_data["completeness_analysis"]:
        completeness_doc = create_completeness_report(quality_data["completeness_analysis"])
        completeness_file = os.path.join(metadata_generator.research_path, "quality_metrics", "data_completeness_report.md")
        with open(completeness_file, 'w') as f:
            f.write(completeness_doc)
        logger.info(f"Data completeness report saved to {completeness_file}")
    
    # Image quality report
    if "error" not in quality_data["image_quality_assessment"]:
        image_quality_doc = create_image_quality_report(quality_data["image_quality_assessment"])
        image_quality_file = os.path.join(metadata_generator.research_path, "quality_metrics", "image_quality_report.md")
        with open(image_quality_file, 'w') as f:
            f.write(image_quality_doc)
        logger.info(f"Image quality report saved to {image_quality_file}")
    
    # Family integrity report
    if "error" not in quality_data["family_integrity"]:
        family_doc = create_family_integrity_report(quality_data["family_integrity"])
        family_file = os.path.join(metadata_generator.research_path, "quality_metrics", "family_integrity_report.md")
        with open(family_file, 'w') as f:
            f.write(family_doc)
        logger.info(f"Family integrity report saved to {family_file}")
    
    # Processing statistics report
    if "error" not in quality_data["processing_stats"]:
        processing_doc = create_processing_stats_report(quality_data["processing_stats"])
        processing_file = os.path.join(metadata_generator.research_path, "quality_metrics", "processing_statistics_report.md")
        with open(processing_file, 'w') as f:
            f.write(processing_doc)
        logger.info(f"Processing statistics report saved to {processing_file}")


def create_completeness_report(completeness_data):
    """Create data completeness report in Markdown format"""
    
    doc = """# Data Completeness Report

## Overview
This report analyzes data completeness across all modalities in the ADNI Knowledge Graph.

"""
    
    # Patient data completeness
    if "patients" in completeness_data:
        patient_data = completeness_data["patients"]
        doc += f"""## Patient Data Completeness

- **Total Patients**: {patient_data.get('total_count', 0):,}
- **Gender Completeness**: {patient_data.get('gender_completeness', 0):.1f}%
- **Age Completeness**: {patient_data.get('age_completeness', 0):.1f}%
- **Education Completeness**: {patient_data.get('education_completeness', 0):.1f}%
- **APOE Completeness**: {patient_data.get('apoe_completeness', 0):.1f}%

### Patient Data Quality Assessment
"""
        
        # Quality assessment based on completeness percentages
        completeness_scores = [
            patient_data.get('gender_completeness', 0),
            patient_data.get('age_completeness', 0),
            patient_data.get('education_completeness', 0),
            patient_data.get('apoe_completeness', 0)
        ]
        avg_completeness = sum(completeness_scores) / len(completeness_scores)
        
        if avg_completeness >= 90:
            doc += "✅ **Excellent**: Patient data completeness is excellent (>90%)\n\n"
        elif avg_completeness >= 75:
            doc += "⚠️ **Good**: Patient data completeness is good (75-90%)\n\n"
        elif avg_completeness >= 50:
            doc += "⚠️ **Fair**: Patient data completeness needs improvement (50-75%)\n\n"
        else:
            doc += "❌ **Poor**: Patient data completeness is poor (<50%)\n\n"
    
    # Imaging data completeness
    if "imaging" in completeness_data:
        imaging_data = completeness_data["imaging"]
        doc += f"""## Imaging Data Completeness

- **Total Images**: {imaging_data.get('total_count', 0):,}
- **DICOM Completeness**: {imaging_data.get('dicom_completeness', 0):.1f}%
- **PNG Completeness**: {imaging_data.get('png_completeness', 0):.1f}%
- **Thumbnail Completeness**: {imaging_data.get('thumbnail_completeness', 0):.1f}%
- **Processing Completeness**: {imaging_data.get('processing_completeness', 0):.1f}%

### Imaging Data Quality Assessment
"""
        
        processing_completeness = imaging_data.get('processing_completeness', 0)
        if processing_completeness >= 95:
            doc += "✅ **Excellent**: Image processing is nearly complete (>95%)\n\n"
        elif processing_completeness >= 80:
            doc += "⚠️ **Good**: Most images have been processed (80-95%)\n\n"
        elif processing_completeness >= 50:
            doc += "⚠️ **In Progress**: Image processing is ongoing (50-80%)\n\n"
        else:
            doc += "❌ **Needs Attention**: Many images still need processing (<50%)\n\n"
    
    # Family data completeness
    if "family" in completeness_data:
        family_data = completeness_data["family"]
        doc += f"""## Family Data Completeness

- **Total Family Members**: {family_data.get('total_count', 0):,}
- **AD Status Completeness**: {family_data.get('ad_status_completeness', 0):.1f}%
- **Age Completeness**: {family_data.get('age_completeness', 0):.1f}%
- **Gender Completeness**: {family_data.get('gender_completeness', 0):.1f}%

### Family Data Quality Assessment
"""
        
        ad_status_completeness = family_data.get('ad_status_completeness', 0)
        if ad_status_completeness >= 80:
            doc += "✅ **Good**: Family AD status information is well documented\n\n"
        elif ad_status_completeness >= 50:
            doc += "⚠️ **Fair**: Some family AD status information is missing\n\n"
        else:
            doc += "❌ **Poor**: Significant family AD status information is missing\n\n"
    
    doc += """## Recommendations

### High Priority
- Focus on completing missing critical data fields
- Implement data validation checks for new entries
- Establish data quality monitoring processes

### Medium Priority
- Improve data collection procedures for optional fields
- Implement automated data quality alerts
- Create data quality dashboards for ongoing monitoring

### Low Priority
- Enhance data documentation and metadata
- Implement data quality scoring systems
- Create data quality training materials
"""
    
    return doc


def create_image_quality_report(image_quality_data):
    """Create image quality assessment report in Markdown format"""
    
    doc = """# Image Quality Assessment Report

## Overview
This report analyzes the quality of processed medical images in the ADNI Knowledge Graph.

"""
    
    if "no_data" in image_quality_data:
        doc += "❌ **No Data**: No image quality metrics found in the database.\n\n"
        doc += "This may indicate that image processing has not been completed or quality metrics are not being calculated.\n\n"
        return doc
    
    total_images = image_quality_data.get("total_images_with_metrics", 0)
    avg_psnr = image_quality_data.get("average_psnr", 0)
    avg_ssim = image_quality_data.get("average_ssim", 0)
    avg_quality = image_quality_data.get("average_quality_score", 0)
    validation_rate = image_quality_data.get("validation_pass_rate", 0)
    
    doc += f"""## Quality Metrics Summary

- **Total Images with Metrics**: {total_images:,}
- **Average PSNR**: {avg_psnr:.2f} dB
- **Average SSIM**: {avg_ssim:.3f}
- **Average Quality Score**: {avg_quality:.3f}
- **Validation Pass Rate**: {validation_rate:.1f}%

"""
    
    # Quality distribution
    if "quality_distribution" in image_quality_data:
        dist = image_quality_data["quality_distribution"]
        doc += f"""## Quality Distribution

- **Excellent (≥0.9)**: {dist.get('excellent', 0):,} images
- **Good (0.7-0.9)**: {dist.get('good', 0):,} images
- **Fair (0.5-0.7)**: {dist.get('fair', 0):,} images
- **Poor (<0.5)**: {dist.get('poor', 0):,} images

"""
    
    # Quality assessment
    doc += "## Quality Assessment\n\n"
    
    if avg_quality >= 0.8:
        doc += "✅ **Excellent**: Image quality is excellent with high fidelity preservation\n\n"
    elif avg_quality >= 0.6:
        doc += "⚠️ **Good**: Image quality is good with acceptable fidelity\n\n"
    elif avg_quality >= 0.4:
        doc += "⚠️ **Fair**: Image quality is fair but may need improvement\n\n"
    else:
        doc += "❌ **Poor**: Image quality is poor and needs immediate attention\n\n"
    
    if validation_rate >= 95:
        doc += "✅ **Validation**: Excellent validation pass rate\n\n"
    elif validation_rate >= 80:
        doc += "⚠️ **Validation**: Good validation pass rate\n\n"
    else:
        doc += "❌ **Validation**: Low validation pass rate - review processing pipeline\n\n"
    
    doc += """## Technical Details

### PSNR (Peak Signal-to-Noise Ratio)
- **Good**: >30 dB
- **Acceptable**: 20-30 dB
- **Poor**: <20 dB

### SSIM (Structural Similarity Index)
- **Excellent**: >0.9
- **Good**: 0.7-0.9
- **Fair**: 0.5-0.7
- **Poor**: <0.5

## Recommendations

### Immediate Actions
- Review images with poor quality scores
- Investigate validation failures
- Check processing pipeline parameters

### Process Improvements
- Implement quality thresholds for automatic rejection
- Add quality monitoring alerts
- Regular quality audits of processed images

### Long-term Enhancements
- Implement advanced quality metrics
- Machine learning-based quality assessment
- Automated quality improvement algorithms
"""
    
    return doc


def create_family_integrity_report(family_data):
    """Create family relationship integrity report in Markdown format"""
    
    doc = """# Family Relationship Integrity Report

## Overview
This report analyzes the integrity and consistency of family relationship data in the ADNI Knowledge Graph.

"""
    
    orphaned = family_data.get("orphaned_family_members", 0)
    circular = family_data.get("circular_relationships", 0)
    inconsistent = family_data.get("inconsistent_parent_child", 0)
    
    doc += f"""## Integrity Issues Summary

- **Orphaned Family Members**: {orphaned:,}
- **Circular Relationships**: {circular:,}
- **Inconsistent Parent-Child Relationships**: {inconsistent:,}

"""
    
    # AD status distribution
    if "ad_status_distribution" in family_data:
        ad_dist = family_data["ad_status_distribution"]
        total = ad_dist.get("total", 0)
        with_ad = ad_dist.get("with_ad", 0)
        without_ad = ad_dist.get("without_ad", 0)
        unknown = ad_dist.get("unknown", 0)
        
        doc += f"""## AD Status Distribution

- **Total Family Members**: {total:,}
- **With AD**: {with_ad:,} ({(with_ad/total*100) if total > 0 else 0:.1f}%)
- **Without AD**: {without_ad:,} ({(without_ad/total*100) if total > 0 else 0:.1f}%)
- **Unknown Status**: {unknown:,} ({(unknown/total*100) if total > 0 else 0:.1f}%)

"""
    
    # Overall assessment
    doc += "## Integrity Assessment\n\n"
    
    total_issues = orphaned + circular + inconsistent
    if total_issues == 0:
        doc += "✅ **Excellent**: No integrity issues detected in family relationships\n\n"
    elif total_issues <= 5:
        doc += "⚠️ **Good**: Minor integrity issues detected - should be reviewed\n\n"
    elif total_issues <= 20:
        doc += "⚠️ **Fair**: Several integrity issues detected - needs attention\n\n"
    else:
        doc += "❌ **Poor**: Many integrity issues detected - requires immediate action\n\n"
    
    # Detailed issue analysis
    if orphaned > 0:
        doc += f"""### Orphaned Family Members
{orphaned} family members are not connected to any patient records. This may indicate:
- Data import issues
- Missing patient records
- Incorrect patient ID references

**Action Required**: Review and fix orphaned family member records.

"""
    
    if circular > 0:
        doc += f"""### Circular Relationships
{circular} circular relationships detected in family trees. This indicates:
- Logical inconsistencies in family data
- Data entry errors
- Import/processing bugs

**Action Required**: Identify and resolve circular relationship patterns.

"""
    
    if inconsistent > 0:
        doc += f"""### Inconsistent Parent-Child Relationships
{inconsistent} parent-child relationships lack proper bidirectional connections. This may indicate:
- Incomplete relationship creation
- Processing pipeline issues
- Data synchronization problems

**Action Required**: Create missing bidirectional relationships.

"""
    
    doc += """## Recommendations

### Immediate Actions
1. Fix orphaned family member records
2. Resolve circular relationship patterns
3. Create missing bidirectional relationships
4. Implement relationship validation checks

### Process Improvements
1. Add family relationship validation to data import
2. Implement automated integrity checking
3. Create family tree visualization tools
4. Regular integrity audits

### Data Quality Enhancements
1. Improve family history data collection
2. Implement relationship confidence scoring
3. Add temporal relationship tracking
4. Create family risk assessment tools
"""
    
    return doc


def create_processing_stats_report(processing_data):
    """Create processing statistics report in Markdown format"""
    
    doc = """# Processing Statistics Report

## Overview
This report provides statistics on data processing success and failure rates across different components.

"""
    
    # Image processing statistics
    if "image_processing" in processing_data:
        img_stats = processing_data["image_processing"]
        total = img_stats.get("total", 0)
        completed = img_stats.get("completed", 0)
        failed = img_stats.get("failed", 0)
        pending = img_stats.get("pending", 0)
        processing = img_stats.get("processing", 0)
        success_rate = img_stats.get("success_rate", 0)
        
        doc += f"""## Image Processing Statistics

- **Total Images**: {total:,}
- **Completed**: {completed:,} ({(completed/total*100) if total > 0 else 0:.1f}%)
- **Failed**: {failed:,} ({(failed/total*100) if total > 0 else 0:.1f}%)
- **Pending**: {pending:,} ({(pending/total*100) if total > 0 else 0:.1f}%)
- **Currently Processing**: {processing:,} ({(processing/total*100) if total > 0 else 0:.1f}%)
- **Success Rate**: {success_rate:.1f}%

### Image Processing Assessment
"""
        
        if success_rate >= 95:
            doc += "✅ **Excellent**: Very high image processing success rate\n\n"
        elif success_rate >= 85:
            doc += "⚠️ **Good**: Good image processing success rate\n\n"
        elif success_rate >= 70:
            doc += "⚠️ **Fair**: Moderate image processing success rate - investigate failures\n\n"
        else:
            doc += "❌ **Poor**: Low image processing success rate - immediate attention required\n\n"
    
    # Family extraction statistics
    if "family_extraction" in processing_data:
        fam_stats = processing_data["family_extraction"]
        total_patients = fam_stats.get("total_patients", 0)
        total_family = fam_stats.get("total_family_members", 0)
        without_family = fam_stats.get("patients_without_family", 0)
        extraction_rate = fam_stats.get("family_extraction_rate", 0)
        
        doc += f"""## Family Extraction Statistics

- **Total Patients**: {total_patients:,}
- **Total Family Members**: {total_family:,}
- **Patients Without Family Data**: {without_family:,}
- **Family Extraction Rate**: {extraction_rate:.1f}%
- **Average Family Members per Patient**: {(total_family/total_patients) if total_patients > 0 else 0:.1f}

### Family Extraction Assessment
"""
        
        if extraction_rate >= 80:
            doc += "✅ **Good**: High family data extraction rate\n\n"
        elif extraction_rate >= 60:
            doc += "⚠️ **Fair**: Moderate family data extraction rate\n\n"
        else:
            doc += "❌ **Poor**: Low family data extraction rate - review data sources\n\n"
    
    doc += """## Processing Performance Analysis

### Success Factors
- Robust error handling and retry mechanisms
- Quality validation at each processing step
- Comprehensive logging and monitoring
- Efficient batch processing

### Common Failure Patterns
- Corrupted or invalid input files
- Network connectivity issues
- Resource constraints (memory, disk space)
- Data format inconsistencies

## Recommendations

### Immediate Actions
1. Investigate and resolve high-failure processing steps
2. Retry failed processing jobs
3. Monitor resource utilization
4. Review error logs for patterns

### Process Improvements
1. Implement automated retry mechanisms
2. Add processing queue management
3. Improve error handling and recovery
4. Implement processing checkpoints

### Monitoring Enhancements
1. Real-time processing dashboards
2. Automated failure alerts
3. Performance trend analysis
4. Resource utilization monitoring

### Optimization Opportunities
1. Parallel processing implementation
2. Resource allocation optimization
3. Processing pipeline tuning
4. Caching strategy improvements
"""
    
    return doc


def print_quality_summary(quality_report):
    """Print a summary of the quality report"""
    
    print("\n" + "="*60)
    print("DATA QUALITY REPORT SUMMARY")
    print("="*60)
    
    # Completeness summary
    completeness = quality_report.get("completeness_analysis", {})
    if "error" not in completeness:
        if "patients" in completeness:
            patient_data = completeness["patients"]
            print(f"Patient Data:")
            print(f"  - Total Patients: {patient_data.get('total_count', 0):,}")
            print(f"  - Average Completeness: {(patient_data.get('gender_completeness', 0) + patient_data.get('age_completeness', 0) + patient_data.get('education_completeness', 0) + patient_data.get('apoe_completeness', 0))/4:.1f}%")
        
        if "imaging" in completeness:
            imaging_data = completeness["imaging"]
            print(f"Imaging Data:")
            print(f"  - Total Images: {imaging_data.get('total_count', 0):,}")
            print(f"  - Processing Complete: {imaging_data.get('processing_completeness', 0):.1f}%")
    else:
        print(f"Completeness Analysis: {completeness['error']}")
    
    # Image quality summary
    image_quality = quality_report.get("image_quality_assessment", {})
    if "error" not in image_quality and "no_data" not in image_quality:
        print(f"Image Quality:")
        print(f"  - Images with Metrics: {image_quality.get('total_images_with_metrics', 0):,}")
        print(f"  - Average Quality Score: {image_quality.get('average_quality_score', 0):.3f}")
        print(f"  - Validation Pass Rate: {image_quality.get('validation_pass_rate', 0):.1f}%")
    else:
        print(f"Image Quality: {image_quality.get('error', image_quality.get('no_data', 'Unknown'))}")
    
    # Family integrity summary
    family_integrity = quality_report.get("family_relationship_integrity", {})
    if "error" not in family_integrity:
        orphaned = family_integrity.get("orphaned_family_members", 0)
        circular = family_integrity.get("circular_relationships", 0)
        inconsistent = family_integrity.get("inconsistent_parent_child", 0)
        total_issues = orphaned + circular + inconsistent
        print(f"Family Integrity:")
        print(f"  - Total Issues: {total_issues}")
        print(f"  - Orphaned Members: {orphaned}")
        print(f"  - Circular Relationships: {circular}")
    else:
        print(f"Family Integrity: {family_integrity['error']}")
    
    # Processing statistics summary
    processing = quality_report.get("processing_statistics", {})
    if "error" not in processing:
        if "image_processing" in processing:
            img_stats = processing["image_processing"]
            print(f"Processing Statistics:")
            print(f"  - Image Success Rate: {img_stats.get('success_rate', 0):.1f}%")
        if "family_extraction" in processing:
            fam_stats = processing["family_extraction"]
            print(f"  - Family Extraction Rate: {fam_stats.get('family_extraction_rate', 0):.1f}%")
    else:
        print(f"Processing Statistics: {processing['error']}")
    
    print("\nQuality report files generated in outputs/research/quality_metrics/")
    print("="*60)


if __name__ == "__main__":
    main()