"""
Enhanced ADNI Knowledge Graph Pipeline for Neo4j - WITH PET SUPPORT
==================================================================

This improved pipeline addresses:
1. Speed optimizations with better batching and parallel processing
2. Fixed logging issues for patient statistics
3. Improved node/relation quality based on AD-DPC ontology
4. Image blob storage capability
5. Neo4j syntax compatibility fixes
6. **NEW: Full PET image support alongside MRI**

Key Improvements:
- Separated family members into individual nodes
- Enhanced temporal modeling with better relationships
- Optimized batch processing with configurable sizes
- Fixed Neo4j queries for compatibility
- Added image blob storage functionality
- Improved error handling and logging
- **NEW: PET image processing with Updated_PET folder**
- **NEW: Enhanced PET metadata extraction**
- **NEW: Dual modality support (MRI + PET)**
"""

import os
import pandas as pd
import pydicom
from PIL import Image
import numpy as np
from neo4j import GraphDatabase
import logging
from pathlib import Path
import json
from datetime import datetime
import re
import concurrent.futures
from typing import Dict, List, Any, Optional, Tuple
import threading
from dataclasses import dataclass
import uuid
import tempfile
import csv
from collections import defaultdict
import base64
import io
from functools import lru_cache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class PatientRecord:
    """Enhanced data structure for patient information"""
    ptid: str
    rid: str
    demographic_data: Dict[str, Any]
    clinical_data: Dict[str, Any]
    assessment_data: Dict[str, Any]
    family_history_data: Dict[str, Any]
    source_tables: List[str]
    created_at: str


@dataclass
class FamilyMember:
    """Data structure for family member information"""
    member_id: str
    patient_id: str
    relationship_type: str
    gender: Optional[str]
    has_dementia: Optional[bool]
    age_at_onset: Optional[int]
    properties: Dict[str, Any]


@dataclass
class ImageMetadata:
    """Enhanced data structure for image metadata with blob support and modality type"""
    image_id: str
    patient_id: str
    original_path: str
    converted_path: str
    modality: str
    modality_type: str  # NEW: 'MRI' or 'PET'
    study_date: str
    series_description: str
    acquisition_parameters: Dict[str, Any]
    dicom_metadata: Dict[str, Any]
    anatomical_region: str
    slice_thickness: Optional[float]
    pixel_spacing: Optional[Tuple[float, float]]
    pet_tracer: Optional[str]  # NEW: For PET tracer information
    image_blob: Optional[str]
    thumbnail_blob: Optional[str]


@dataclass
class ClinicalFinding:
    """Extended clinical finding structure"""
    finding_id: str
    patient_id: str
    rid: str
    ptid: str
    months: int
    viscode: str
    finding_type: str
    finding_subtype: str
    assessment_name: str
    table_source: str
    temporal_region_id: str
    properties: Dict[str, Any]
    confidence_score: float
    clinical_significance: str


class OptimizedADNIKnowledgeGraphPipeline:
    """
    Optimized pipeline class implementing the AD-DPC ontology with performance improvements
    **NOW WITH FULL PET SUPPORT**
    """

    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                 base_path: str = "inputs", max_workers: int = 8):
        """Initialize the optimized pipeline with enhanced configuration including PET support"""

        # Neo4j connection with optimized settings
        self.driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password),
            max_connection_pool_size=50,
            connection_acquisition_timeout=60
        )

        # Path configuration - Enhanced for PET support
        self.base_path = Path(base_path)
        self.tables_path = self.base_path / "Tables"

        # MRI paths (existing)
        self.mri_images_path = self.base_path / "Images"  # Original MRI DICOMs
        self.updated_mri_images_path = self.base_path / "Updated"  # Converted MRI images

        # PET paths (NEW)
        self.pet_images_path = self.base_path / "PET"  # Original PET DICOMs
        self.updated_pet_images_path = self.base_path / "Updated_PET"  # Converted PET images

        self.temp_dir = Path("outputs/temp_processing")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Optimized performance settings
        self.max_workers = max_workers
        self.batch_size = 5000
        self.image_batch_size = 100
        self.lock = threading.Lock()

        # Cache for frequently accessed data
        self._patient_cache = {}
        self._temporal_cache = {}

        # NEW: Create Updated_PET directory if it doesn't exist
        self.updated_pet_images_path.mkdir(exist_ok=True)

    def close_connection(self):
        """Close the Neo4j connection"""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j connection closed")

    def clear_database(self):
        """Clear all nodes and relationships from the database - Optimized version"""
        logger.info("Clearing existing database...")

        with self.driver.session() as session:
            try:
                # Use periodic commit for large deletions
                session.run("""
                    CALL apoc.periodic.iterate(
                        'MATCH (n) RETURN n',
                        'DETACH DELETE n',
                        {batchSize: 10000, parallel: false}
                    )
                """)
                logger.info("✅ Database cleared using APOC batch deletion")
            except Exception as e:
                logger.warning(f"APOC batch deletion failed: {e}")
                # Fallback with standard deletion
                session.run("MATCH (n) DETACH DELETE n")
                logger.info("✅ Database cleared using standard deletion")

    def create_comprehensive_constraints_and_indexes(self):
        """Create comprehensive constraints and indexes - Fixed syntax"""
        logger.info("Creating comprehensive database schema...")

        with self.driver.session() as session:
            # Core entity constraints
            constraints = [
                "CREATE CONSTRAINT patient_ptid_unique IF NOT EXISTS FOR (p:Patient) REQUIRE p.ptid IS UNIQUE",
                "CREATE CONSTRAINT patient_rid_unique IF NOT EXISTS FOR (p:Patient) REQUIRE p.rid IS UNIQUE",
                "CREATE CONSTRAINT participant_file_unique IF NOT EXISTS FOR (pf:ParticipantFile) REQUIRE pf.participant_file_id IS UNIQUE",
                "CREATE CONSTRAINT family_member_unique IF NOT EXISTS FOR (fm:FamilyMember) REQUIRE fm.member_id IS UNIQUE",
                "CREATE CONSTRAINT temporal_region_unique IF NOT EXISTS FOR (t:ZeroDimensionalTemporalRegion) REQUIRE t.temporal_id IS UNIQUE",
                "CREATE CONSTRAINT clinical_finding_unique IF NOT EXISTS FOR (cf:ClinicalFinding) REQUIRE cf.finding_id IS UNIQUE",
                "CREATE CONSTRAINT psychometric_finding_unique IF NOT EXISTS FOR (pf:PsychometricFinding) REQUIRE pf.finding_id IS UNIQUE",
                "CREATE CONSTRAINT laboratory_finding_unique IF NOT EXISTS FOR (lf:LaboratoryFinding) REQUIRE lf.finding_id IS UNIQUE",
                "CREATE CONSTRAINT image_finding_unique IF NOT EXISTS FOR (if:ImageFinding) REQUIRE if.finding_id IS UNIQUE",
                "CREATE CONSTRAINT assessment_unique IF NOT EXISTS FOR (a:Assessment) REQUIRE a.assessment_id IS UNIQUE",
                "CREATE CONSTRAINT diagnostic_process_unique IF NOT EXISTS FOR (dp:DiagnosticProcess) REQUIRE dp.process_id IS UNIQUE",
                "CREATE CONSTRAINT imaging_study_unique IF NOT EXISTS FOR (is:ImagingStudy) REQUIRE is.study_id IS UNIQUE",
                "CREATE CONSTRAINT imaging_series_unique IF NOT EXISTS FOR (iser:ImagingSeries) REQUIRE iser.series_id IS UNIQUE",
                "CREATE CONSTRAINT image_node_unique IF NOT EXISTS FOR (img:ImageNode) REQUIRE img.image_id IS UNIQUE",
                "CREATE CONSTRAINT diagnosis_unique IF NOT EXISTS FOR (d:Diagnosis) REQUIRE d.diagnosis_id IS UNIQUE",
                "CREATE CONSTRAINT scale_unique IF NOT EXISTS FOR (s:Scale) REQUIRE s.scale_id IS UNIQUE",
                "CREATE CONSTRAINT biomarker_unique IF NOT EXISTS FOR (b:Biomarker) REQUIRE b.biomarker_id IS UNIQUE"
            ]

            for constraint in constraints:
                try:
                    session.run(constraint)
                    constraint_name = constraint.split('FOR')[1].split('REQUIRE')[0].strip()
                    logger.info(f"✅ Created constraint: {constraint_name}")
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        logger.warning(f"⚠️ Constraint creation issue: {e}")

            # Comprehensive performance indexes - Enhanced for PET
            indexes = [
                "CREATE INDEX patient_diagnosis_idx IF NOT EXISTS FOR (p:Patient) ON (p.diagnosis)",
                "CREATE INDEX patient_age_idx IF NOT EXISTS FOR (p:Patient) ON (p.age_at_baseline)",
                "CREATE INDEX patient_gender_idx IF NOT EXISTS FOR (p:Patient) ON (p.gender)",
                "CREATE INDEX patient_education_idx IF NOT EXISTS FOR (p:Patient) ON (p.education_years)",
                "CREATE INDEX family_relationship_idx IF NOT EXISTS FOR (fm:FamilyMember) ON (fm.relationship_type)",
                "CREATE INDEX family_dementia_idx IF NOT EXISTS FOR (fm:FamilyMember) ON (fm.has_dementia)",
                "CREATE INDEX temporal_months_idx IF NOT EXISTS FOR (t:ZeroDimensionalTemporalRegion) ON (t.months)",
                "CREATE INDEX finding_months_idx IF NOT EXISTS FOR (cf:ClinicalFinding) ON (cf.months)",
                "CREATE INDEX finding_type_idx IF NOT EXISTS FOR (cf:ClinicalFinding) ON (cf.finding_type)",
                "CREATE INDEX image_patient_idx IF NOT EXISTS FOR (img:ImageNode) ON (img.patient_id)",
                "CREATE INDEX image_modality_idx IF NOT EXISTS FOR (img:ImageNode) ON (img.modality)",
                "CREATE INDEX image_modality_type_idx IF NOT EXISTS FOR (img:ImageNode) ON (img.modality_type)",  # NEW
                "CREATE INDEX image_pet_tracer_idx IF NOT EXISTS FOR (img:ImageNode) ON (img.pet_tracer)",  # NEW
                "CREATE INDEX patient_temporal_composite_idx IF NOT EXISTS FOR (t:ZeroDimensionalTemporalRegion) ON (t.ptid, t.months)",
                "CREATE INDEX finding_patient_composite_idx IF NOT EXISTS FOR (cf:ClinicalFinding) ON (cf.ptid, cf.months)"
            ]

            for index in indexes:
                try:
                    session.run(index)
                    index_name = index.split()[2]
                    logger.info(f"✅ Created index: {index_name}")
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        logger.warning(f"⚠️ Index creation issue: {e}")

    def load_and_process_tables(self) -> Dict[str, pd.DataFrame]:
        """Load and process all CSV tables with enhanced metadata extraction - Optimized"""
        logger.info("Loading and processing table data...")

        if not self.tables_path.exists():
            logger.error(f"Tables directory not found: {self.tables_path}")
            return {}

        table_files = list(self.tables_path.glob("*.csv"))
        table_data = {}

        def load_single_table(csv_file: Path) -> Tuple[str, Optional[pd.DataFrame]]:
            """Load a single CSV table with enhanced processing"""
            try:
                # Read CSV with proper settings
                df = pd.read_csv(
                    csv_file,
                    low_memory=False,
                    na_values=['', 'NaN', 'NULL', 'null', 'N/A', 'n/a', '-', '--'],
                    keep_default_na=True,
                    encoding='utf-8'
                )

                table_name = csv_file.stem

                # Basic data cleaning
                df.columns = df.columns.str.strip()

                logger.info(f"✅ Loaded table '{table_name}' with {len(df)} records and {len(df.columns)} columns")
                return table_name, df
            except Exception as e:
                logger.error(f"❌ Error loading {csv_file}: {e}")
                return csv_file.stem, None

        # Load tables concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(load_single_table, csv_file): csv_file
                for csv_file in table_files
            }

            for future in concurrent.futures.as_completed(future_to_file):
                table_name, df = future.result()
                if df is not None:
                    table_data[table_name] = df

        logger.info(f"✅ Successfully loaded {len(table_data)} tables")
        return table_data

    def extract_family_members(self, table_data: Dict[str, pd.DataFrame]) -> List[FamilyMember]:
        """Extract family member information from tables"""
        logger.info("Extracting family member information...")

        family_members = []

        # Look for family history tables
        family_tables = []
        for table_name, df in table_data.items():
            if any(fam_key in table_name.upper() for fam_key in ['FAMHX', 'FAMILY', 'RELATIVE']):
                family_tables.append((table_name, df))

        for table_name, df in family_tables:
            for _, row in df.iterrows():
                data = row.to_dict()

                # Extract patient identifier
                ptid = str(data.get('PTID', data.get('SUBJID', ''))).strip()
                rid = str(data.get('RID', '')).strip()

                if not ptid and not rid:
                    continue

                # Determine relationship type from table name
                relationship_type = 'unknown'
                if 'PAR' in table_name.upper() or 'PARENT' in table_name.upper():
                    relationship_type = 'parent'
                elif 'SIB' in table_name.upper() or 'SIBLING' in table_name.upper():
                    relationship_type = 'sibling'
                elif 'CHILD' in table_name.upper():
                    relationship_type = 'child'

                # Extract family member data
                member_properties = {}
                has_dementia = None
                age_at_onset = None
                gender = None

                for key, value in data.items():
                    if pd.notna(value):
                        clean_key = str(key).strip()
                        clean_value = value if isinstance(value, (int, float)) else str(value).strip()

                        # Check for dementia status
                        if any(dem_key in clean_key.upper() for dem_key in ['DEMENTIA', 'AD', 'ALZHEIMER']):
                            if isinstance(value, (int, float)):
                                has_dementia = bool(value)
                            elif str(value).upper() in ['YES', 'Y', '1', 'TRUE']:
                                has_dementia = True
                            elif str(value).upper() in ['NO', 'N', '0', 'FALSE']:
                                has_dementia = False

                        # Check for age at onset
                        elif 'ONSET' in clean_key.upper() and 'AGE' in clean_key.upper():
                            try:
                                age_at_onset = int(float(value))
                            except:
                                pass

                        # Check for gender
                        elif 'GENDER' in clean_key.upper() or 'SEX' in clean_key.upper():
                            gender = str(value)

                        member_properties[clean_key] = clean_value

                # Create family member record
                member_id = f"fm_{ptid}_{relationship_type}_{uuid.uuid4().hex[:6]}"

                family_member = FamilyMember(
                    member_id=member_id,
                    patient_id=ptid,
                    relationship_type=relationship_type,
                    gender=gender,
                    has_dementia=has_dementia,
                    age_at_onset=age_at_onset,
                    properties=member_properties
                )

                family_members.append(family_member)

        logger.info(f"✅ Extracted {len(family_members)} family member records")
        return family_members

    def create_enhanced_patient_records(self, table_data: Dict[str, pd.DataFrame]) -> List[PatientRecord]:
        """Create enhanced patient records with family history separation"""
        logger.info("Creating enhanced patient records...")

        # Find the main demographic table
        main_table = None
        main_table_name = ""

        for table_name, df in table_data.items():
            if any(col in df.columns for col in ['RID', 'PTID', 'SUBJID']) and any(
                    col in df.columns for col in ['AGE', 'GENDER', 'SEX']):
                main_table = df
                main_table_name = table_name
                break

        if main_table is None:
            # Fallback to any table with patient identifiers
            for table_name, df in table_data.items():
                if any(col in df.columns for col in ['RID', 'PTID', 'SUBJID']):
                    main_table = df
                    main_table_name = table_name
                    break

        if main_table is None:
            raise ValueError("No table found with patient identifiers (RID/PTID/SUBJID)")

        logger.info(f"Using '{main_table_name}' as main patient table")

        # Group by patient to handle multiple visits
        patient_records = {}

        for _, row in main_table.iterrows():
            data = row.to_dict()

            # Extract patient identifiers
            ptid = str(data.get('PTID', data.get('SUBJID', ''))).strip()
            rid = str(data.get('RID', '')).strip()

            if not ptid and not rid:
                continue

            # Use PTID as primary key
            patient_key = ptid if ptid else rid
            if not patient_key:
                continue

            # Categorize data
            demographic_data = {}
            clinical_data = {}
            assessment_data = {}
            family_history_data = {}

            for key, value in data.items():
                if pd.notna(value):
                    clean_key = str(key).strip()
                    clean_value = value if isinstance(value, (int, float)) else str(value).strip()

                    # Categorize based on key patterns
                    if any(demo_key in clean_key.upper() for demo_key in
                           ['AGE', 'GENDER', 'SEX', 'EDUCATION', 'RACE', 'ETHNIC', 'MARITAL']):
                        demographic_data[clean_key] = clean_value
                    elif any(fam_key in clean_key.upper() for fam_key in
                             ['FAMILY', 'RELATIVE', 'PARENT', 'SIBLING', 'MOTHER', 'FATHER']):
                        family_history_data[clean_key] = clean_value
                    elif any(clin_key in clean_key.upper() for clin_key in
                             ['MEDICAL', 'HISTORY', 'DIAGNOSIS', 'MEDICATION', 'SURGERY']):
                        clinical_data[clean_key] = clean_value
                    elif any(assess_key in clean_key.upper() for assess_key in
                             ['MMSE', 'MOCA', 'CDR', 'ADAS', 'FAQ', 'RAVLT', 'SCORE']):
                        assessment_data[clean_key] = clean_value
                    else:
                        clinical_data[clean_key] = clean_value

            # Create or update patient record
            if patient_key not in patient_records:
                patient_records[patient_key] = PatientRecord(
                    ptid=ptid,
                    rid=rid,
                    demographic_data=demographic_data,
                    clinical_data=clinical_data,
                    assessment_data=assessment_data,
                    family_history_data=family_history_data,
                    source_tables=[main_table_name],
                    created_at=datetime.now().isoformat()
                )
            else:
                # Merge data for existing patient
                existing_record = patient_records[patient_key]
                existing_record.demographic_data.update(demographic_data)
                existing_record.clinical_data.update(clinical_data)
                existing_record.assessment_data.update(assessment_data)
                existing_record.family_history_data.update(family_history_data)
                if main_table_name not in existing_record.source_tables:
                    existing_record.source_tables.append(main_table_name)

        logger.info(f"✅ Created {len(patient_records)} enhanced patient records")
        return list(patient_records.values())

    def process_images_with_metadata(self, store_blobs: bool = True,
                                   process_mri: bool = True,
                                   process_pet: bool = True) -> List[ImageMetadata]:
        """
        Process images with comprehensive metadata extraction for both MRI and PET
        **ENHANCED WITH FULL PET SUPPORT**
        """
        logger.info(f"Processing images with metadata extraction (blob storage: {store_blobs})")
        logger.info(f"MRI processing: {process_mri}, PET processing: {process_pet}")

        all_image_metadata = []

        # Process MRI images
        if process_mri:
            logger.info("Processing MRI images...")
            mri_metadata = self._process_modality_images(
                original_path=self.mri_images_path,
                updated_path=self.updated_mri_images_path,
                modality_type='MRI',
                store_blobs=store_blobs
            )
            all_image_metadata.extend(mri_metadata)
            logger.info(f"✅ Processed {len(mri_metadata)} MRI images")

        # Process PET images
        if process_pet:
            logger.info("Processing PET images...")
            pet_metadata = self._process_modality_images(
                original_path=self.pet_images_path,
                updated_path=self.updated_pet_images_path,
                modality_type='PET',
                store_blobs=store_blobs
            )
            all_image_metadata.extend(pet_metadata)
            logger.info(f"✅ Processed {len(pet_metadata)} PET images")

        logger.info(f"✅ Total processed images: {len(all_image_metadata)}")
        return all_image_metadata

    def _process_modality_images(self, original_path: Path, updated_path: Path,
                                 modality_type: str, store_blobs: bool) -> List[ImageMetadata]:
        """
        Process images for a specific modality (MRI or PET) with BATCH PROCESSING
        Handles large datasets efficiently by processing patients in batches
        """
        if not updated_path.exists():
            logger.warning(f"{modality_type} updated images directory not found: {updated_path}")
            return []

        # Get all patient directories
        patient_dirs = [item for item in updated_path.iterdir() if item.is_dir()]
        total_patients = len(patient_dirs)

        logger.info(f"Found {total_patients} patient directories in {updated_path}")

        if total_patients == 0:
            return []

        # Batch processing parameters
        patient_batch_size = 50  # Process 50 patients at a time
        all_processed_images = []

        # Process patients in batches
        for batch_start in range(0, total_patients, patient_batch_size):
            batch_end = min(batch_start + patient_batch_size, total_patients)
            patient_batch = patient_dirs[batch_start:batch_end]

            logger.info(
                f"Processing patient batch {batch_start // patient_batch_size + 1}/{(total_patients - 1) // patient_batch_size + 1} "
                f"(patients {batch_start + 1}-{batch_end}/{total_patients})")

            # Collect image files for this batch of patients
            batch_image_files = []

            for patient_dir in patient_batch:
                patient_id = patient_dir.name

                # Look for series directories within patient directory
                series_dirs = [item for item in patient_dir.iterdir() if item.is_dir()]

                if series_dirs:
                    # Handle nested structure (patient/series/timestamp/images)
                    for series_dir in series_dirs:
                        series_name = series_dir.name

                        # Look for timestamp directories within series directory
                        timestamp_dirs = [item for item in series_dir.iterdir() if item.is_dir()]

                        if timestamp_dirs:
                            # Images are in timestamp directories
                            for timestamp_dir in timestamp_dirs:
                                for image_file in timestamp_dir.iterdir():
                                    if image_file.is_file() and image_file.suffix.lower() in ['.png', '.jpg', '.jpeg']:
                                        # Include series and timestamp info in metadata
                                        image_info = (patient_id, image_file, series_name, timestamp_dir.name)
                                        batch_image_files.append(image_info)
                        else:
                            # Images might be directly in series directory
                            for image_file in series_dir.iterdir():
                                if image_file.is_file() and image_file.suffix.lower() in ['.png', '.jpg', '.jpeg']:
                                    image_info = (patient_id, image_file, series_name, None)
                                    batch_image_files.append(image_info)
                else:
                    # Images might be directly in patient directory (original structure)
                    for image_file in patient_dir.iterdir():
                        if image_file.is_file() and image_file.suffix.lower() in ['.png', '.jpg', '.jpeg']:
                            image_info = (patient_id, image_file, None, None)
                            batch_image_files.append(image_info)

            logger.info(f"  Found {len(batch_image_files)} images in this batch")

            # Process images in this batch
            if batch_image_files:
                batch_processed = self._process_image_batch(
                    batch_image_files,
                    original_path,
                    modality_type,
                    store_blobs
                )
                all_processed_images.extend(batch_processed)
                logger.info(f"  Processed {len(batch_processed)} images successfully")

            # Force garbage collection after each batch to free memory
            import gc
            gc.collect()

        logger.info(f"Total {modality_type} images processed: {len(all_processed_images)}")
        return all_processed_images

    def _process_image_batch(self, image_files: List[tuple], original_path: Path,
                             modality_type: str, store_blobs: bool) -> List[ImageMetadata]:
        """
        Process a batch of images in parallel
        """

        def process_single_image(image_info: tuple) -> Optional[ImageMetadata]:
            """Process a single image with comprehensive metadata extraction"""
            patient_id, image_path, series_name, timestamp = image_info

            try:
                filename = image_path.name

                # Enhanced metadata extraction using directory structure
                metadata = self._parse_adni_filename(filename, modality_type)

                # Add series information from directory structure
                if series_name:
                    metadata['series_description'] = series_name
                    # Update anatomical region based on series name
                    metadata['anatomical_region'] = self._determine_anatomical_region(
                        series_name.lower(), modality_type
                    )

                # Add timestamp information
                if timestamp:
                    # Try to parse timestamp as study date
                    try:
                        # Format: 20110602_075657
                        date_part = timestamp.split('_')[0]
                        if len(date_part) == 8 and date_part.isdigit():
                            metadata['study_date'] = date_part
                    except:
                        pass

                # Try to extract DICOM metadata if original exists (with timeout)
                dicom_metadata = {}
                try:
                    # Use a simple approach to avoid long searches
                    # Only look for DICOM if we have small dataset or if specifically needed
                    if len(image_files) < 100:  # Only for small batches
                        dicom_metadata = self._extract_dicom_metadata_simple(
                            patient_id, filename, original_path, modality_type
                        )
                except Exception as e:
                    logger.debug(f"Skipping DICOM metadata extraction: {e}")

                # Process image blob if requested
                image_blob = None
                thumbnail_blob = None
                blob_paths = {}

                if store_blobs:
                    blob_paths = self._save_image_blob_to_disk(
                        image_path, patient_id, modality_type,
                        f"img_{modality_type.lower()}_{patient_id}_{uuid.uuid4().hex[:8]}"
                    )

                # For PET images, try to extract tracer from series name
                if modality_type == 'PET' and series_name:
                    pet_tracer = self._extract_pet_tracer(series_name, [patient_id, series_name])
                    if pet_tracer:
                        metadata['pet_tracer'] = pet_tracer

                return ImageMetadata(
                    image_id=f"img_{modality_type.lower()}_{patient_id}_{uuid.uuid4().hex[:8]}",
                    patient_id=patient_id,
                    original_path=str(image_path),
                    converted_path=self._save_processed_image(
                        image_path, patient_id, modality_type, series_name
                    ),
                    modality=metadata.get('modality', modality_type),
                    modality_type=modality_type,
                    study_date=metadata.get('study_date', ''),
                    series_description=metadata.get('series_description', ''),
                    acquisition_parameters=metadata.get('acquisition_params', {}),
                    dicom_metadata=dicom_metadata,
                    anatomical_region=metadata.get('anatomical_region', ''),
                    slice_thickness=metadata.get('slice_thickness'),
                    pixel_spacing=metadata.get('pixel_spacing'),
                    pet_tracer=metadata.get('pet_tracer'),
                    image_blob=blob_paths.get('full_blob_path'),  # Store path instead of blob
                    thumbnail_blob=blob_paths.get('thumbnail_blob_path')  # Store path instead of blob
                )

            except Exception as e:
                logger.error(f"❌ Error processing {modality_type} image {image_path}: {e}")
                return None

        # Process images concurrently within the batch
        processed_images = []

        # Use ThreadPoolExecutor for I/O bound tasks
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(self.max_workers, 16)) as executor:
            # Submit all tasks
            future_to_image = {
                executor.submit(process_single_image, image_info): image_info
                for image_info in image_files
            }

            # Process completed tasks with progress tracking
            from tqdm import tqdm

            for future in tqdm(concurrent.futures.as_completed(future_to_image),
                               total=len(image_files),
                               desc=f"Processing {modality_type} images",
                               leave=False):
                try:
                    result = future.result(timeout=30)  # 30 second timeout per image
                    if result:
                        processed_images.append(result)
                except concurrent.futures.TimeoutError:
                    image_info = future_to_image[future]
                    logger.warning(f"Timeout processing image: {image_info[1]}")
                except Exception as e:
                    logger.error(f"Error in future: {e}")

        return processed_images

    def _save_image_blob_to_disk(self, image_path: Path, patient_id: str,
                                 modality_type: str, image_id: str) -> Dict[str, str]:
        """Save image as JPG blob to disk instead of Neo4j"""
        try:
            # Create blob directory structure
            blob_dir = self.base_path / "image_blobs" / modality_type / patient_id
            blob_dir.mkdir(parents=True, exist_ok=True)

            # Read and convert image
            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # Save full size (max 800x800)
                full_path = blob_dir / f"{image_id}_full.jpg"
                img_full = img.copy()
                img_full.thumbnail((800, 800), Image.Resampling.LANCZOS)
                img_full.save(full_path, format='JPEG', quality=85)

                # Save thumbnail
                thumb_path = blob_dir / f"{image_id}_thumb.jpg"
                img.thumbnail((150, 150), Image.Resampling.LANCZOS)
                img.save(thumb_path, format='JPEG', quality=70)

            return {
                'full_blob_path': str(full_path),
                'thumbnail_blob_path': str(thumb_path)
            }
        except Exception as e:
            logger.warning(f"Failed to save image blob for {image_path}: {e}")
            return {}

    def _save_processed_image(self, image_path: Path, patient_id: str,
                              modality_type: str, series_name: str = None) -> str:
        """Save processed image to Updated or Updated_PET folder"""
        try:
            # Determine output directory
            if modality_type == 'MRI':
                output_base = self.updated_mri_images_path
            else:
                output_base = self.updated_pet_images_path

            # Create patient directory
            patient_dir = output_base / patient_id
            if series_name:
                patient_dir = patient_dir / series_name
            patient_dir.mkdir(parents=True, exist_ok=True)

            # Generate output filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f"{patient_id}_{modality_type}_{timestamp}.jpg"
            output_path = patient_dir / output_filename

            # Save as JPG
            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.save(output_path, format='JPEG', quality=90)

            return str(output_path)
        except Exception as e:
            logger.error(f"Failed to save processed image: {e}")
            return str(image_path)

    def _extract_dicom_metadata_simple(self, patient_id: str, filename: str,
                                       original_path: Path, modality_type: str) -> Dict[str, Any]:
        """
        Simplified DICOM metadata extraction - faster version for large datasets
        """
        dicom_metadata = {}

        try:
            # Only look in the patient's directory, not recursively
            patient_dicom_path = original_path / patient_id
            if not patient_dicom_path.exists():
                return dicom_metadata

            # Quick scan - just get first DICOM file we find
            for item in patient_dicom_path.iterdir():
                if item.is_file() and item.suffix.lower() == '.dcm':
                    try:
                        ds = pydicom.dcmread(str(item), stop_before_pixels=True, force=True)

                        # Extract only essential fields
                        essential_fields = [
                            'StudyDate', 'SeriesDescription', 'Modality',
                            'SliceThickness', 'PixelSpacing'
                        ]

                        for field in essential_fields:
                            if hasattr(ds, field):
                                value = getattr(ds, field)
                                if value is not None:
                                    if isinstance(value, (list, tuple)):
                                        dicom_metadata[field.lower()] = list(value)
                                    else:
                                        dicom_metadata[field.lower()] = str(value)

                        # Got some metadata, that's enough
                        break

                    except Exception:
                        continue

        except Exception as e:
            logger.debug(f"Error in simple DICOM extraction: {e}")

        return dicom_metadata

    def _parse_adni_filename(self, filename: str, modality_type: str) -> Dict[str, Any]:
        """
        Parse ADNI filename to extract metadata - Enhanced for PET support
        **ENHANCED WITH PET-SPECIFIC PARSING**
        """
        metadata = {
            'modality': modality_type,
            'series_description': '',
            'study_date': '',
            'acquisition_params': {},
            'anatomical_region': '',
            'pet_tracer': None
        }

        try:
            # ADNI filename pattern: ADNI_xxx_S_xxxx_[PT/MR]_series_description_timestamp
            parts = filename.split('_')

            if len(parts) >= 5:
                # Find modality indicator
                modality_found = False
                for i, part in enumerate(parts):
                    if part in ['MR', 'MRI'] and modality_type == 'MRI':
                        metadata['modality'] = 'MRI'
                        modality_found = True
                        if i + 1 < len(parts):
                            # Extract series description for MRI
                            series_parts = parts[i + 1:-1]  # Exclude timestamp
                            metadata['series_description'] = '_'.join(series_parts)
                        break
                    elif part in ['PT', 'PET'] and modality_type == 'PET':
                        metadata['modality'] = 'PET'
                        modality_found = True
                        if i + 1 < len(parts):
                            # Extract series description for PET
                            series_parts = parts[i + 1:-1]  # Exclude timestamp
                            series_desc = '_'.join(series_parts)
                            metadata['series_description'] = series_desc

                            # Extract PET tracer information
                            metadata['pet_tracer'] = self._extract_pet_tracer(series_desc, parts)
                        break

                # If modality not found in filename, use the modality_type
                if not modality_found:
                    metadata['modality'] = modality_type

                # Determine anatomical region based on series description
                series_desc = metadata['series_description'].lower()
                metadata['anatomical_region'] = self._determine_anatomical_region(
                    series_desc, modality_type
                )

                # Extract date if present in filename
                for part in parts:
                    if re.match(r'\d{8}', part):  # YYYYMMDD format
                        metadata['study_date'] = part
                        break

        except Exception as e:
            logger.debug(f"Error parsing {modality_type} filename {filename}: {e}")

        return metadata

    def _extract_pet_tracer(self, series_desc: str, filename_parts: List[str]) -> Optional[str]:
        """
        Extract PET tracer information from filename and series description
        **NEW METHOD FOR PET TRACER EXTRACTION**
        """
        series_lower = series_desc.lower()

        # Common PET tracers in ADNI
        tracer_patterns = {
            'FDG': ['fdg', 'fluorodeoxyglucose'],
            'AV45': ['av45', 'florbetapir', 'amyvid'],
            'PIB': ['pib', 'pittsburgh'],
            'AV1451': ['av1451', 'tau', 'flortaucipir'],
            'AV133': ['av133'],
            'MK6240': ['mk6240'],
            'RO948': ['ro948', 'ro-948']
        }

        # Check series description first
        for tracer, patterns in tracer_patterns.items():
            if any(pattern in series_lower for pattern in patterns):
                return tracer

        # Check filename parts
        for part in filename_parts:
            part_lower = part.lower()
            for tracer, patterns in tracer_patterns.items():
                if any(pattern in part_lower for pattern in patterns):
                    return tracer

        # Default inference based on common ADNI patterns
        if any(term in series_lower for term in ['glucose', 'metabolic']):
            return 'FDG'
        elif any(term in series_lower for term in ['amyloid', 'plaque']):
            return 'AV45'
        elif any(term in series_lower for term in ['tau', 'tangle']):
            return 'AV1451'

        return None

    def _determine_anatomical_region(self, series_desc: str, modality_type: str) -> str:
        """
        Determine anatomical region from series description
        **ENHANCED FOR BOTH MRI AND PET**
        """
        if any(term in series_desc for term in ['hippocampus', 'hippo']):
            return 'hippocampus'
        elif any(term in series_desc for term in ['cortex', 'cortical']):
            return 'cortex'
        elif any(term in series_desc for term in ['ventricle', 'ventricular']):
            return 'ventricles'
        elif any(term in series_desc for term in ['cerebellum']):
            return 'cerebellum'
        elif any(term in series_desc for term in ['frontal']):
            return 'frontal_lobe'
        elif any(term in series_desc for term in ['temporal']):
            return 'temporal_lobe'
        elif any(term in series_desc for term in ['parietal']):
            return 'parietal_lobe'
        elif any(term in series_desc for term in ['occipital']):
            return 'occipital_lobe'
        elif any(term in series_desc for term in ['whole', 'brain']) or modality_type == 'PET':
            return 'whole_brain'
        else:
            return 'brain'

    def _extract_dicom_metadata(self, patient_id: str, filename: str,
                              original_path: Path, modality_type: str) -> Dict[str, Any]:
        """
        Extract metadata from original DICOM file if available
        **ENHANCED FOR BOTH MRI AND PET**
        """
        dicom_metadata = {}

        try:
            # Look for corresponding DICOM file in original images folder
            patient_dicom_path = original_path / patient_id
            if patient_dicom_path.exists():
                # Use more efficient search pattern
                dicom_files = list(patient_dicom_path.rglob("*.dcm"))[:10]  # Limit search

                for dicom_file in dicom_files:
                    if patient_id in dicom_file.name:
                        try:
                            ds = pydicom.dcmread(str(dicom_file), stop_before_pixels=True)

                            # Helper function for value conversion
                            def convert_dicom_value(value):
                                if value is None:
                                    return None
                                if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
                                    try:
                                        return list(value)
                                    except:
                                        return str(value)
                                elif isinstance(value, (int, float)):
                                    return value
                                else:
                                    return str(value)

                            # Extract essential metadata (common for both MRI and PET)
                            essential_fields = [
                                'StudyDate', 'SeriesDescription', 'Modality',
                                'SliceThickness', 'PixelSpacing', 'StudyID',
                                'SeriesNumber', 'InstanceNumber', 'PatientAge',
                                'StudyTime', 'AcquisitionTime'
                            ]

                            # PET-specific fields
                            if modality_type == 'PET':
                                pet_fields = [
                                    'RadiopharmaceuticalInformationSequence',
                                    'Radiopharmaceutical', 'RadiopharmaceuticalRoute',
                                    'RadiopharmaceuticalVolume', 'RadionuclideTotalDose',
                                    'RadiopharmaceuticalStartTime', 'RadionuclideHalfLife',
                                    'Units', 'DecayCorrection', 'AttenuationCorrectionMethod',
                                    'ReconstructionMethod'
                                ]
                                essential_fields.extend(pet_fields)

                            # MRI-specific fields
                            elif modality_type == 'MRI':
                                mri_fields = [
                                    'MagneticFieldStrength', 'ImagingFrequency',
                                    'EchoTime', 'RepetitionTime', 'InversionTime',
                                    'FlipAngle', 'MRAcquisitionType', 'SequenceName',
                                    'ScanningSequence', 'SequenceVariant'
                                ]
                                essential_fields.extend(mri_fields)

                            for field in essential_fields:
                                if hasattr(ds, field):
                                    dicom_metadata[field.lower()] = convert_dicom_value(
                                        getattr(ds, field, None)
                                    )

                            # Special handling for PET radiopharmaceutical information
                            if modality_type == 'PET' and hasattr(ds, 'RadiopharmaceuticalInformationSequence'):
                                try:
                                    radio_seq = ds.RadiopharmaceuticalInformationSequence
                                    if radio_seq:
                                        radio_info = radio_seq[0]
                                        if hasattr(radio_info, 'Radiopharmaceutical'):
                                            dicom_metadata['radiopharmaceutical'] = str(radio_info.Radiopharmaceutical)
                                        if hasattr(radio_info, 'RadionuclideTotalDose'):
                                            dicom_metadata['radionuclide_total_dose'] = float(radio_info.RadionuclideTotalDose)
                                except Exception as e:
                                    logger.debug(f"Error extracting PET radiopharmaceutical info: {e}")

                            break  # Use first matching DICOM file
                        except Exception as e:
                            logger.debug(f"Error reading DICOM {dicom_file}: {e}")
                            continue
        except Exception as e:
            logger.debug(f"Error extracting DICOM metadata for {patient_id} ({modality_type}): {e}")

        return dicom_metadata

    def create_clinical_findings_from_tables(self, table_data: Dict[str, pd.DataFrame],
                                             patient_records: List[PatientRecord]) -> List[ClinicalFinding]:
        """Create comprehensive clinical findings from all tables - Optimized"""
        logger.info("Creating comprehensive clinical findings...")

        # Create patient lookup for validation
        patient_lookup = {record.ptid: record for record in patient_records}

        # Enhanced finding categories based on research paper
        finding_categories = {
            'psychometric': {
                'keywords': ['ADAS', 'MMSE', 'MOCA', 'CDR', 'FAQ', 'RAVLT', 'BNT',
                             'AMNART', 'NEUROBAT', 'CLOCK', 'LOGICAL'],
                'subtype_mapping': {
                    'ADAS': 'cognitive_assessment',
                    'MMSE': 'global_cognitive',
                    'MOCA': 'global_cognitive',
                    'CDR': 'functional_assessment',
                    'FAQ': 'functional_assessment',
                    'RAVLT': 'memory_assessment',
                    'BNT': 'language_assessment',
                    'CLOCK': 'visuospatial_assessment',
                    'LOGICAL': 'memory_assessment'
                }
            },
            'biomarker': {
                'keywords': ['TAU', 'ELECSYS', 'BIOMARK', 'LABDATA', 'APOERES',
                             'ABETA', 'PTAU', 'NFL', 'GFAP'],
                'subtype_mapping': {
                    'TAU': 'csf_biomarker',
                    'ELECSYS': 'csf_biomarker',
                    'BIOMARK': 'blood_biomarker',
                    'LABDATA': 'laboratory_test',
                    'ABETA': 'amyloid_biomarker',
                    'PTAU': 'tau_biomarker',
                    'NFL': 'neurodegeneration_marker'
                }
            },
            'imaging': {
                'keywords': ['MRI', 'PET', 'VOLUME', 'THICKNESS', 'FDG', 'AV45', 'TAU_PET'],
                'subtype_mapping': {
                    'MRI': 'structural_imaging',
                    'PET': 'molecular_imaging',
                    'VOLUME': 'volumetric_analysis',
                    'THICKNESS': 'cortical_thickness',
                    'FDG': 'metabolic_imaging',
                    'AV45': 'amyloid_imaging',
                    'TAU_PET': 'tau_imaging'
                }
            },
            'clinical': {
                'keywords': ['PTDEMOG', 'MEDICAL', 'VITALS', 'PHYSICAL', 'NEURO'],
                'subtype_mapping': {
                    'PTDEMOG': 'demographic_data',
                    'MEDICAL': 'medical_history',
                    'VITALS': 'vital_signs',
                    'PHYSICAL': 'physical_exam',
                    'NEURO': 'neurological_exam'
                }
            },
            'behavioral': {
                'keywords': ['NPI', 'NPIQ', 'GDS', 'CSSRS', 'ANXIETY', 'DEPRESSION'],
                'subtype_mapping': {
                    'NPI': 'neuropsychiatric_assessment',
                    'GDS': 'depression_scale',
                    'ANXIETY': 'anxiety_assessment',
                    'DEPRESSION': 'mood_assessment'
                }
            },
            'genetic': {
                'keywords': ['GENETIC', 'APOE', 'SNP', 'GWAS', 'MUTATION'],
                'subtype_mapping': {
                    'GENETIC': 'genetic_analysis',
                    'APOE': 'apoe_genotyping',
                    'SNP': 'snp_analysis',
                    'GWAS': 'genome_wide_association'
                }
            }
        }

        all_findings = []

        # Process tables in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_table = {}

            for table_name, df in table_data.items():
                # Skip family history tables (processed separately)
                if any(fam_key in table_name.upper() for fam_key in ['FAMHX', 'FAMILY']):
                    continue

                # Determine finding category and subtype
                finding_type = 'clinical'  # default
                finding_subtype = 'general_clinical'

                for category, info in finding_categories.items():
                    for keyword in info['keywords']:
                        if keyword in table_name.upper():
                            finding_type = category
                            finding_subtype = info['subtype_mapping'].get(keyword, f'{category}_general')
                            break
                    if finding_type != 'clinical':
                        break

                # Submit table processing task
                future = executor.submit(
                    self._process_table_for_findings,
                    df, table_name, finding_type, finding_subtype, patient_lookup
                )
                future_to_table[future] = table_name

            # Collect results
            for future in concurrent.futures.as_completed(future_to_table):
                table_name = future_to_table[future]
                try:
                    table_findings = future.result()
                    all_findings.extend(table_findings)
                    logger.info(f"Processed {len(table_findings)} findings from {table_name}")
                except Exception as e:
                    logger.error(f"Error processing table {table_name}: {e}")

        logger.info(f"✅ Created {len(all_findings)} clinical findings from {len(table_data)} tables")
        return all_findings

    def _process_table_for_findings(self, df: pd.DataFrame, table_name: str,
                                    finding_type: str, finding_subtype: str,
                                    patient_lookup: Dict[str, PatientRecord]) -> List[ClinicalFinding]:
        """Process a single table to extract clinical findings - Optimized"""
        findings = []

        # Process in chunks for large dataframes
        chunk_size = 1000
        for chunk_start in range(0, len(df), chunk_size):
            chunk_end = min(chunk_start + chunk_size, len(df))
            chunk = df.iloc[chunk_start:chunk_end]

            for _, row in chunk.iterrows():
                data = row.to_dict()

                # Extract patient identifiers
                ptid = str(data.get('PTID', data.get('SUBJID', ''))).strip()
                rid = str(data.get('RID', '')).strip()

                if not ptid and not rid:
                    continue

                # Skip if patient not in our records
                if ptid not in patient_lookup and rid not in [p.rid for p in patient_lookup.values()]:
                    continue

                # Extract temporal information
                viscode = str(data.get('VISCODE', data.get('VISCODE2', 'bl'))).strip()
                months = self._convert_viscode_to_months(viscode)

                # Clean and categorize the data
                cleaned_properties = {}
                assessment_scores = {}
                clinical_notes = {}

                for key, value in data.items():
                    if pd.notna(value) and key not in ['PTID', 'SUBJID', 'RID', 'VISCODE', 'VISCODE2']:
                        clean_key = str(key).strip()

                        # Skip if value is too large (potential blob data)
                        if isinstance(value, str) and len(value) > 1000:
                            continue

                        clean_value = value if isinstance(value, (int, float)) else str(value).strip()

                        # Categorize based on value type and key pattern
                        if isinstance(value, (int, float)) and any(score_key in clean_key.upper()
                                                                   for score_key in ['SCORE', 'TOTAL', 'SUM']):
                            assessment_scores[clean_key] = clean_value
                        elif 'NOTE' in clean_key.upper() or 'COMMENT' in clean_key.upper():
                            clinical_notes[clean_key] = clean_value[:500]  # Limit note length
                        else:
                            cleaned_properties[clean_key] = clean_value

                # Calculate confidence score based on data completeness
                confidence_score = min(1.0, len(cleaned_properties) / 10.0)

                # Determine clinical significance
                clinical_significance = self._determine_clinical_significance(
                    finding_type, finding_subtype, assessment_scores, cleaned_properties
                )

                # Create finding
                finding_id = f"{table_name}_{ptid}_{rid}_{months}_{uuid.uuid4().hex[:6]}"
                temporal_region_id = f"temporal_{ptid}_{months}"

                finding = ClinicalFinding(
                    finding_id=finding_id,
                    patient_id=ptid,
                    rid=rid,
                    ptid=ptid,
                    months=months,
                    viscode=viscode,
                    finding_type=finding_type,
                    finding_subtype=finding_subtype,
                    assessment_name=table_name,
                    table_source=table_name,
                    temporal_region_id=temporal_region_id,
                    properties=cleaned_properties,
                    confidence_score=confidence_score,
                    clinical_significance=clinical_significance
                )

                findings.append(finding)

        return findings

    @lru_cache(maxsize=1000)
    def _convert_viscode_to_months(self, viscode: str) -> int:
        """Convert VISCODE to months following ADNI convention - Cached for performance"""
        if not viscode or viscode.lower() in ['bl', 'baseline', 'sc', 'screening']:
            return 0

        try:
            viscode_str = str(viscode).lower().strip()

            # Handle 'm' prefix (e.g., 'm06', 'm12')
            if viscode_str.startswith('m'):
                return int(viscode_str[1:])

            # Handle numeric values
            if viscode_str.isdigit():
                return int(viscode_str)

            # Handle other patterns
            if 'month' in viscode_str:
                numbers = re.findall(r'\d+', viscode_str)
                if numbers:
                    return int(numbers[0])

            # Handle year patterns
            if 'y' in viscode_str or 'year' in viscode_str:
                numbers = re.findall(r'\d+', viscode_str)
                if numbers:
                    return int(numbers[0]) * 12

            return 0
        except (ValueError, AttributeError):
            return 0

    def _determine_clinical_significance(self, finding_type: str, finding_subtype: str,
                                         assessment_scores: Dict[str, Any],
                                         properties: Dict[str, Any]) -> str:
        """Determine clinical significance based on finding characteristics - Enhanced"""

        significance = 'normal'

        try:
            if finding_type == 'psychometric':
                # MMSE scoring (lower scores indicate impairment)
                mmse_keys = [k for k in assessment_scores.keys() if 'MMSE' in k.upper()]
                if mmse_keys:
                    mmse_scores = [float(assessment_scores[k]) for k in mmse_keys
                                   if isinstance(assessment_scores[k], (int, float))]
                    if mmse_scores:
                        max_mmse = max(mmse_scores)
                        if max_mmse < 10:
                            significance = 'severe_impairment'
                        elif max_mmse < 20:
                            significance = 'moderate_impairment'
                        elif max_mmse < 24:
                            significance = 'mild_impairment'
                        else:
                            significance = 'normal'

                # CDR scoring (higher scores indicate more impairment)
                cdr_keys = [k for k in assessment_scores.keys() if 'CDR' in k.upper() and 'SUM' in k.upper()]
                if cdr_keys:
                    cdr_scores = [float(assessment_scores[k]) for k in cdr_keys
                                  if isinstance(assessment_scores[k], (int, float))]
                    if cdr_scores:
                        max_cdr = max(cdr_scores)
                        if max_cdr >= 10:
                            significance = 'severe_impairment'
                        elif max_cdr >= 4.5:
                            significance = 'moderate_impairment'
                        elif max_cdr >= 0.5:
                            significance = 'mild_impairment'
                        else:
                            significance = 'normal'

            elif finding_type == 'biomarker':
                # Check for abnormal biomarker patterns
                if finding_subtype in ['csf_biomarker', 'amyloid_biomarker', 'tau_biomarker']:
                    # Look for specific biomarker values
                    for key, value in properties.items():
                        if isinstance(value, (int, float)):
                            # Amyloid beta 42 (lower values indicate pathology)
                            if 'ABETA42' in key.upper() and float(value) < 600:
                                significance = 'abnormal'
                            # Tau (higher values indicate pathology)
                            elif 'TAU' in key.upper() and 'PTAU' not in key.upper() and float(value) > 400:
                                significance = 'abnormal'
                            # Phosphorylated tau (higher values indicate pathology)
                            elif 'PTAU' in key.upper() and float(value) > 80:
                                significance = 'abnormal'

            elif finding_type == 'genetic':
                # APOE4 status
                apoe_keys = [k for k in properties.keys() if 'APOE' in k.upper()]
                for key in apoe_keys:
                    value = str(properties[key])
                    if '4/4' in value:
                        significance = 'very_high_risk'
                    elif '3/4' in value or '4/3' in value:
                        significance = 'high_risk'
                    elif '2/4' in value or '4/2' in value:
                        significance = 'moderate_risk'
                    elif '2/2' in value or '2/3' in value:
                        significance = 'protective'

            elif finding_type == 'imaging':
                # Check for volumetric abnormalities
                if 'VOLUME' in finding_subtype.upper():
                    for key, value in properties.items():
                        if 'HIPPO' in key.upper() and isinstance(value, (int, float)):
                            # Hippocampal volume (lower values indicate atrophy)
                            if float(value) < 3000:  # mm³
                                significance = 'severe_atrophy'
                            elif float(value) < 3500:
                                significance = 'moderate_atrophy'
                            elif float(value) < 4000:
                                significance = 'mild_atrophy'

        except Exception as e:
            logger.debug(f"Error determining clinical significance: {e}")

        return significance

    def create_batch_files_for_insertion(self, patient_records: List[PatientRecord],
                                         family_members: List[FamilyMember],
                                         image_metadata: List[ImageMetadata],
                                         clinical_findings: List[ClinicalFinding]) -> Dict[str, str]:
        """Create optimized batch files for Neo4j insertion - Enhanced version"""
        logger.info("Creating optimized batch files for insertion...")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        batch_files = {}

        # 1. Create patients batch file
        patients_data = []
        for record in patient_records:
            patient_entry = {
                'ptid': record.ptid,
                'rid': record.rid,
                'participant_file_id': f"pf_{record.ptid}_{record.rid}",
                'demographic_data': record.demographic_data,
                'clinical_data': record.clinical_data,
                'assessment_data': record.assessment_data,
                'family_history_data': record.family_history_data,
                'source_tables': record.source_tables,
                'created_at': record.created_at,
                'display_label': record.ptid,
                'patient_label': f"Patient_{record.ptid}"
            }
            patients_data.append(patient_entry)

        patients_file = self.temp_dir / f"patients_batch_{timestamp}.json"
        with open(patients_file, 'w') as f:
            json.dump(patients_data, f, indent=2)
        batch_files['patients'] = str(patients_file)

        # 2. Create family members batch file
        family_data = []
        for member in family_members:
            family_entry = {
                'member_id': member.member_id,
                'patient_id': member.patient_id,
                'relationship_type': member.relationship_type,
                'gender': member.gender,
                'has_dementia': member.has_dementia,
                'age_at_onset': member.age_at_onset,
                'properties': member.properties,
                'created_at': datetime.now().isoformat()
            }
            family_data.append(family_entry)

        family_file = self.temp_dir / f"family_batch_{timestamp}.json"
        with open(family_file, 'w') as f:
            json.dump(family_data, f, indent=2)
        batch_files['family'] = str(family_file)

        # 3. Create images batch file - Enhanced for PET support
        images_data = []
        for img in image_metadata:
            study_id = f"study_{img.modality_type.lower()}_{img.patient_id}_{img.study_date or 'unknown'}"
            series_id = f"series_{img.modality_type.lower()}_{img.patient_id}_{img.modality}_{uuid.uuid4().hex[:6]}"

            image_entry = {
                'image_id': img.image_id,
                'patient_id': img.patient_id,
                'study_id': study_id,
                'series_id': series_id,
                'original_path': img.original_path,
                'converted_path': img.converted_path,
                'modality': img.modality,
                'modality_type': img.modality_type,  # NEW
                'study_date': img.study_date,
                'series_description': img.series_description,
                'acquisition_parameters': img.acquisition_parameters,
                'dicom_metadata': img.dicom_metadata,
                'anatomical_region': img.anatomical_region,
                'slice_thickness': img.slice_thickness,
                'pixel_spacing': img.pixel_spacing,
                'pet_tracer': img.pet_tracer,  # NEW
                'has_blob': img.image_blob is not None,
                'image_blob': img.image_blob,
                'thumbnail_blob': img.thumbnail_blob,
                'created_at': datetime.now().isoformat()
            }
            images_data.append(image_entry)

        images_file = self.temp_dir / f"images_batch_{timestamp}.json"
        with open(images_file, 'w') as f:
            json.dump(images_data, f, indent=2)
        batch_files['images'] = str(images_file)

        # 4. Create findings batch file
        findings_data = []
        for finding in clinical_findings:
            finding_entry = {
                'finding_id': finding.finding_id,
                'patient_id': finding.patient_id,
                'rid': finding.rid,
                'ptid': finding.ptid,
                'months': finding.months,
                'viscode': finding.viscode,
                'finding_type': finding.finding_type,
                'finding_subtype': finding.finding_subtype,
                'assessment_name': finding.assessment_name,
                'table_source': finding.table_source,
                'temporal_region_id': finding.temporal_region_id,
                'properties': finding.properties,
                'confidence_score': finding.confidence_score,
                'clinical_significance': finding.clinical_significance,
                'created_at': datetime.now().isoformat()
            }
            findings_data.append(finding_entry)

        findings_file = self.temp_dir / f"findings_batch_{timestamp}.json"
        with open(findings_file, 'w') as f:
            json.dump(findings_data, f, indent=2)
        batch_files['findings'] = str(findings_file)

        logger.info(f"✅ Created batch files:")
        logger.info(f"  - Patients: {patients_file} ({len(patients_data)} records)")
        logger.info(f"  - Family: {family_file} ({len(family_data)} records)")
        logger.info(f"  - Images: {images_file} ({len(images_data)} records)")
        logger.info(f"  - Findings: {findings_file} ({len(findings_data)} records)")

        return batch_files

    def batch_insert_patients_enhanced(self, patients_file: str) -> None:
        """Enhanced batch insertion for patients with AD-DPC compliance - Optimized"""
        logger.info("Starting enhanced patient insertion...")

        with open(patients_file, 'r') as f:
            patients_data = json.load(f)

        with self.driver.session() as session:
            # Use larger batches for better performance
            batch_size = self.batch_size

            for batch_start in range(0, len(patients_data), batch_size):
                batch = patients_data[batch_start:batch_start + batch_size]

                # Enhanced patient insertion with proper labeling
                query = """
                UNWIND $batch as patient_data

                // Create Patient node with display label
                MERGE (p:Patient {ptid: patient_data.ptid})
                SET p += patient_data.demographic_data,
                    p += patient_data.clinical_data,
                    p += patient_data.assessment_data,
                    p.rid = patient_data.rid,
                    p.display_label = patient_data.ptid,
                    p.patient_label = patient_data.patient_label,
                    p.source_tables = patient_data.source_tables,
                    p.created_at = patient_data.created_at

                // Create ParticipantFile node (AD-DPC compliance)
                MERGE (pf:ParticipantFile {participant_file_id: patient_data.participant_file_id})
                SET pf.ptid = patient_data.ptid,
                    pf.rid = patient_data.rid,
                    pf.participant_id = patient_data.ptid,
                    pf.created_at = patient_data.created_at

                // Create AD-DPC relationships
                MERGE (p)-[:hasGenericDependent]->(pf)
                MERGE (pf)-[:genericallyDependsOn]->(p)

                // Create Constitutional node for demographic data
                MERGE (const:Constitutional {constitutional_id: patient_data.ptid + '_constitutional'})
                SET const += patient_data.demographic_data,
                    const.ptid = patient_data.ptid,
                    const.created_at = patient_data.created_at

                MERGE (pf)-[:hasMemberPartAtAllTimes]->(const)

                // Create FamilyHistory node if family data exists
                FOREACH (ignored IN CASE WHEN size(keys(patient_data.family_history_data)) > 0 THEN [1] ELSE [] END |
                    MERGE (fh:FamilyHistory {family_history_id: patient_data.ptid + '_family_history'})
                    SET fh += patient_data.family_history_data,
                        fh.ptid = patient_data.ptid,
                        fh.created_at = patient_data.created_at
                    MERGE (p)-[:hasFamilyHistory]->(fh)
                )
                """

                session.run(query, batch=batch)
                logger.info(
                    f"✅ Inserted patient batch {batch_start // batch_size + 1}/{(len(patients_data) - 1) // batch_size + 1}")

    def batch_insert_family_members(self, family_file: str) -> None:
        """Batch insertion for family members"""
        logger.info("Starting family member insertion...")

        with open(family_file, 'r') as f:
            family_data = json.load(f)

        if not family_data:
            logger.info("No family member data to insert")
            return

        with self.driver.session() as session:
            batch_size = self.batch_size

            for batch_start in range(0, len(family_data), batch_size):
                batch = family_data[batch_start:batch_start + batch_size]

                query = """
                UNWIND $batch as family_data

                // Find the patient
                MATCH (p:Patient {ptid: family_data.patient_id})

                // Create FamilyMember node
                MERGE (fm:FamilyMember {member_id: family_data.member_id})
                SET fm += family_data.properties,
                    fm.patient_id = family_data.patient_id,
                    fm.relationship_type = family_data.relationship_type,
                    fm.gender = family_data.gender,
                    fm.has_dementia = family_data.has_dementia,
                    fm.age_at_onset = family_data.age_at_onset,
                    fm.created_at = family_data.created_at

                // Create relationships based on type
                FOREACH (ignored IN CASE WHEN family_data.relationship_type = 'parent' THEN [1] ELSE [] END |
                    MERGE (p)-[:hasParent]->(fm)
                    MERGE (fm)-[:isParentOf]->(p)
                )

                FOREACH (ignored IN CASE WHEN family_data.relationship_type = 'sibling' THEN [1] ELSE [] END |
                    MERGE (p)-[:hasSibling]->(fm)
                    MERGE (fm)-[:isSiblingOf]->(p)
                )

                FOREACH (ignored IN CASE WHEN family_data.relationship_type = 'child' THEN [1] ELSE [] END |
                    MERGE (p)-[:hasChild]->(fm)
                    MERGE (fm)-[:isChildOf]->(p)
                )

                // General relationship
                MERGE (p)-[:hasRelative]->(fm)
                MERGE (fm)-[:isRelativeOf]->(p)
                """

                session.run(query, batch=batch)
                logger.info(
                    f"✅ Inserted family member batch {batch_start // batch_size + 1}/{(len(family_data) - 1) // batch_size + 1}")

    def batch_insert_images_enhanced(self, images_file: str) -> None:
        """Enhanced batch insertion for images with blob support and PET support - Optimized"""
        logger.info("Starting enhanced image insertion (MRI + PET support)...")

        with open(images_file, 'r') as f:
            images_data = json.load(f)

        with self.driver.session() as session:
            # Use smaller batch size for images due to blob data
            batch_size = self.image_batch_size

            for batch_start in range(0, len(images_data), batch_size):
                batch = images_data[batch_start:batch_start + batch_size]

                # Enhanced query with PET tracer support
                query = """
                UNWIND $batch as image_data

                // Find the patient and participant file
                MATCH (p:Patient {ptid: image_data.patient_id})
                OPTIONAL MATCH (pf:ParticipantFile {ptid: image_data.patient_id})

                // Create ImagingStudy
                MERGE (study:ImagingStudy {study_id: image_data.study_id})
                SET study.patient_id = image_data.patient_id,
                    study.study_date = image_data.study_date,
                    study.modality = image_data.modality,
                    study.modality_type = image_data.modality_type,
                    study.created_at = image_data.created_at

                // Create ImagingSeries
                MERGE (series:ImagingSeries {series_id: image_data.series_id})
                SET series.patient_id = image_data.patient_id,
                    series.modality = image_data.modality,
                    series.modality_type = image_data.modality_type,
                    series.series_description = image_data.series_description,
                    series.anatomical_region = image_data.anatomical_region,
                    series.created_at = image_data.created_at

                // Create ImageNode with enhanced properties
                MERGE (img:ImageNode {image_id: image_data.image_id})
                SET img.patient_id = image_data.patient_id,
                    img.original_path = image_data.original_path,
                    img.converted_path = image_data.converted_path,
                    img.modality = image_data.modality,
                    img.modality_type = image_data.modality_type,
                    img.study_date = image_data.study_date,
                    img.series_description = image_data.series_description,
                    img.anatomical_region = image_data.anatomical_region,
                    img.slice_thickness = image_data.slice_thickness,
                    img.pet_tracer = image_data.pet_tracer,
                    img.has_blob = image_data.has_blob,
                    img.created_at = image_data.created_at

                // Add acquisition parameters
                SET img += image_data.acquisition_parameters

                // Add DICOM metadata if exists
                FOREACH (ignored IN CASE WHEN size(keys(image_data.dicom_metadata)) > 0 THEN [1] ELSE [] END |
                    SET img += image_data.dicom_metadata
                )

                // Store image blob if provided
                FOREACH (ignored IN CASE WHEN image_data.image_blob IS NOT NULL THEN [1] ELSE [] END |
                    SET img.image_blob = image_data.image_blob,
                        img.thumbnail_blob = image_data.thumbnail_blob
                )

                // Create modality-specific test nodes (AD-DPC compliance)
                FOREACH (ignored IN CASE WHEN image_data.modality_type = 'MRI' THEN [1] ELSE [] END |
                    MERGE (mri_test:MRITest {test_id: 'MRI_' + image_data.patient_id + '_' + image_data.study_date})
                    SET mri_test.test_name = 'MRI',
                        mri_test.test_description = image_data.series_description,
                        mri_test.modality = image_data.modality,
                        mri_test.created_at = image_data.created_at
                    MERGE (img)-[:isOutputOf]->(mri_test)
                )

                FOREACH (ignored IN CASE WHEN image_data.modality_type = 'PET' THEN [1] ELSE [] END |
                    MERGE (pet_test:PETTest {test_id: 'PET_' + image_data.patient_id + '_' + image_data.study_date})
                    SET pet_test.test_name = 'PET',
                        pet_test.test_description = image_data.series_description,
                        pet_test.modality = image_data.modality,
                        pet_test.tracer = image_data.pet_tracer,
                        pet_test.created_at = image_data.created_at
                    MERGE (img)-[:isOutputOf]->(pet_test)
                )

                // Create hierarchical relationships
                MERGE (p)-[:hasImagingStudy]->(study)
                MERGE (study)-[:containsImagingSeries]->(series)
                MERGE (series)-[:containsImage]->(img)
                MERGE (img)-[:belongsToPatient]->(p)

                // AD-DPC relationships if participant file exists
                FOREACH (ignored IN CASE WHEN pf IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (pf)-[:hasMemberPartAtAllTimes]->(img)
                )

                // Create ImageFinding node for AD-DPC compliance
                MERGE (imgfinding:ImageFinding {finding_id: image_data.image_id + '_finding'})
                SET imgfinding.patient_id = image_data.patient_id,
                    imgfinding.image_id = image_data.image_id,
                    imgfinding.modality = image_data.modality,
                    imgfinding.modality_type = image_data.modality_type,
                    imgfinding.anatomical_region = image_data.anatomical_region,
                    imgfinding.pet_tracer = image_data.pet_tracer,
                    imgfinding.created_at = image_data.created_at

                MERGE (img)-[:revealsAnatomicalFinding]->(imgfinding)

                // Link to participant file if exists
                FOREACH (ignored IN CASE WHEN pf IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (pf)-[:hasMemberPartAtAllTimes]->(imgfinding)
                )
                """

                session.run(query, batch=batch)
                logger.info(
                    f"✅ Inserted image batch {batch_start // batch_size + 1}/{(len(images_data) - 1) // batch_size + 1}")

    def batch_insert_findings_enhanced(self, findings_file: str) -> None:
        """Enhanced batch insertion for clinical findings - Optimized"""
        logger.info("Starting enhanced clinical findings insertion...")

        with open(findings_file, 'r') as f:
            findings_data = json.load(f)

        with self.driver.session() as session:
            # First, create temporal regions efficiently
            temporal_regions = {}
            for finding in findings_data:
                temporal_id = finding['temporal_region_id']
                if temporal_id not in temporal_regions:
                    temporal_regions[temporal_id] = {
                        'temporal_id': temporal_id,
                        'ptid': finding['ptid'],
                        'months': finding['months'],
                        'viscode': finding['viscode'],
                        'created_at': finding['created_at']
                    }

            # Insert temporal regions in batches
            temporal_batch = list(temporal_regions.values())
            batch_size = self.batch_size

            for batch_start in range(0, len(temporal_batch), batch_size):
                batch = temporal_batch[batch_start:batch_start + batch_size]

                temporal_query = """
                UNWIND $batch as temporal_data
                MERGE (t:ZeroDimensionalTemporalRegion {temporal_id: temporal_data.temporal_id})
                SET t.ptid = temporal_data.ptid,
                    t.months = temporal_data.months,
                    t.viscode = temporal_data.viscode,
                    t.created_at = temporal_data.created_at
                """
                session.run(temporal_query, batch=batch)

            logger.info(f"✅ Created {len(temporal_regions)} temporal regions")

            # Group findings by type for optimized insertion
            findings_by_type = defaultdict(list)
            for finding in findings_data:
                findings_by_type[finding['finding_type']].append(finding)

            # Insert findings by type
            for finding_type, type_findings in findings_by_type.items():
                logger.info(f"Inserting {len(type_findings)} {finding_type} findings...")

                # Dynamic node label based on finding type
                finding_labels = {
                    'psychometric': 'PsychometricFinding',
                    'biomarker': 'BiomarkerFinding',
                    'imaging': 'ImagingFinding',
                    'clinical': 'ClinicalFinding',
                    'behavioral': 'BehavioralFinding',
                    'genetic': 'GeneticFinding'
                }

                finding_label = finding_labels.get(finding_type, 'ClinicalFinding')

                for batch_start in range(0, len(type_findings), batch_size):
                    batch = type_findings[batch_start:batch_start + batch_size]

                    query = f"""
                    UNWIND $batch as finding_data

                    // Find patient and participant file
                    MATCH (p:Patient {{ptid: finding_data.ptid}})
                    OPTIONAL MATCH (pf:ParticipantFile {{ptid: finding_data.ptid}})
                    MATCH (t:ZeroDimensionalTemporalRegion {{temporal_id: finding_data.temporal_region_id}})

                    // Create specific finding type with secondary label
                    MERGE (f:ClinicalFinding:{finding_label} {{finding_id: finding_data.finding_id}})
                    SET f += finding_data.properties,
                        f.patient_id = finding_data.patient_id,
                        f.rid = finding_data.rid,
                        f.ptid = finding_data.ptid,
                        f.months = finding_data.months,
                        f.viscode = finding_data.viscode,
                        f.finding_type = finding_data.finding_type,
                        f.finding_subtype = finding_data.finding_subtype,
                        f.assessment_name = finding_data.assessment_name,
                        f.table_source = finding_data.table_source,
                        f.confidence_score = finding_data.confidence_score,
                        f.clinical_significance = finding_data.clinical_significance,
                        f.created_at = finding_data.created_at

                    // Create relationships
                    MERGE (f)-[:belongsToPatient]->(p)
                    MERGE (f)-[:existsAt]->(t)
                    MERGE (t)-[:contains]->(f)

                    // AD-DPC relationships if participant file exists
                    FOREACH (ignored IN CASE WHEN pf IS NOT NULL THEN [1] ELSE [] END |
                        MERGE (pf)-[:hasMemberPartAtAllTimes]->(f)
                    )

                    // Create Assessment node if it doesn't exist
                    MERGE (a:Assessment {{assessment_id: finding_data.assessment_name + '_' + finding_data.ptid}})
                    SET a.assessment_name = finding_data.assessment_name,
                        a.assessment_type = finding_data.finding_type,
                        a.patient_id = finding_data.patient_id,
                        a.created_at = finding_data.created_at

                    MERGE (f)-[:isOutputOf]->(a)
                    MERGE (p)-[:undergoesAssessment]->(a)
                    """

                    session.run(query, batch=batch)

                logger.info(f"✅ Inserted {len(type_findings)} {finding_type} findings")

    def create_comprehensive_relationships(self) -> None:
        """Create comprehensive relationships based on extended AD-DPC ontology - Enhanced for PET"""
        logger.info("Creating comprehensive relationships based on extended AD-DPC ontology...")

        with self.driver.session() as session:
            # 1. Enhanced diagnostic relationships
            logger.info("Creating diagnostic relationships...")
            diagnostic_query = """
            // Find findings with diagnostic information
            MATCH (f:ClinicalFinding)
            WHERE f.clinical_significance IN ['mild_impairment', 'moderate_impairment', 'severe_impairment']
               OR any(key in keys(f) WHERE key CONTAINS 'DIAGNOSIS' OR key CONTAINS 'DX')

            WITH f
            MATCH (p:Patient {ptid: f.ptid})
            MATCH (t:ZeroDimensionalTemporalRegion {ptid: f.ptid, months: f.months})

            // Create Diagnosis node
            MERGE (d:Diagnosis {diagnosis_id: f.ptid + '_diagnosis_' + f.months})
            SET d.patient_id = f.ptid,
                d.months = f.months,
                d.severity = f.clinical_significance,
                d.confidence_score = f.confidence_score,
                d.based_on_assessment = f.assessment_name,
                d.created_at = datetime()

            MERGE (p)-[:hasDiagnosis]->(d)
            MERGE (d)-[:existsAt]->(t)
            MERGE (f)-[:supportsDiagnosis]->(d)
            """
            session.run(diagnostic_query)

            # 2. Enhanced biomarker relationships with PET integration
            logger.info("Creating biomarker pathway relationships...")
            biomarker_query = """
            // Create biological pathway nodes
            MERGE (amyloid_pathway:BiologicalPathway {pathway_id: 'amyloid_cascade'})
            SET amyloid_pathway.pathway_name = 'Amyloid Cascade Pathway',
                amyloid_pathway.description = 'Amyloid beta processing and aggregation',
                amyloid_pathway.created_at = datetime()

            MERGE (tau_pathway:BiologicalPathway {pathway_id: 'tau_pathology'})
            SET tau_pathway.pathway_name = 'Tau Pathology Pathway',
                tau_pathway.description = 'Tau protein hyperphosphorylation and aggregation',
                tau_pathway.created_at = datetime()

            MERGE (neuro_pathway:BiologicalPathway {pathway_id: 'neurodegeneration'})
            SET neuro_pathway.pathway_name = 'Neurodegeneration Pathway',
                neuro_pathway.description = 'Neuronal loss and synaptic dysfunction',
                neuro_pathway.created_at = datetime()

            MERGE (metabolism_pathway:BiologicalPathway {pathway_id: 'glucose_metabolism'})
            SET metabolism_pathway.pathway_name = 'Glucose Metabolism Pathway',
                metabolism_pathway.description = 'Brain glucose metabolism and energy utilization',
                metabolism_pathway.created_at = datetime()

            // Link biomarker findings to pathways
            WITH amyloid_pathway, tau_pathway, neuro_pathway, metabolism_pathway
            MATCH (bf:BiomarkerFinding)

            FOREACH (ignored IN CASE 
                WHEN any(key in keys(bf) WHERE key CONTAINS 'ABETA') THEN [1] 
                ELSE [] END |
                MERGE (bf)-[:participatesInBiologicalPathway]->(amyloid_pathway)
            )

            FOREACH (ignored IN CASE 
                WHEN any(key in keys(bf) WHERE key CONTAINS 'TAU') THEN [1] 
                ELSE [] END |
                MERGE (bf)-[:participatesInBiologicalPathway]->(tau_pathway)
            )

            FOREACH (ignored IN CASE 
                WHEN any(key in keys(bf) WHERE key CONTAINS 'NFL' OR key CONTAINS 'GFAP') THEN [1] 
                ELSE [] END |
                MERGE (bf)-[:participatesInBiologicalPathway]->(neuro_pathway)
            )

            // Link PET imaging findings to pathways
            WITH amyloid_pathway, tau_pathway, metabolism_pathway
            MATCH (img:ImageNode)
            WHERE img.modality_type = 'PET'

            FOREACH (ignored IN CASE 
                WHEN img.pet_tracer = 'AV45' OR img.pet_tracer = 'PIB' THEN [1] 
                ELSE [] END |
                MERGE (img)-[:revealsPathwayActivity]->(amyloid_pathway)
            )

            FOREACH (ignored IN CASE 
                WHEN img.pet_tracer = 'AV1451' OR img.pet_tracer = 'MK6240' THEN [1] 
                ELSE [] END |
                MERGE (img)-[:revealsPathwayActivity]->(tau_pathway)
            )

            FOREACH (ignored IN CASE 
                WHEN img.pet_tracer = 'FDG' THEN [1] 
                ELSE [] END |
                MERGE (img)-[:revealsPathwayActivity]->(metabolism_pathway)
            )
            """
            session.run(biomarker_query)

            # 3. Enhanced PET-specific relationships
            logger.info("Creating PET-specific relationships...")

            # Split into separate queries to avoid syntax issues
            # First, create PET tracer nodes
            pet_tracer_query = """
            MATCH (img:ImageNode)
            WHERE img.modality_type = 'PET' AND img.pet_tracer IS NOT NULL

            WITH DISTINCT img.pet_tracer as tracer_name
            MERGE (tracer:PETTracer {tracer_id: tracer_name})
            SET tracer.tracer_name = tracer_name,
                tracer.tracer_type = CASE tracer_name
                    WHEN 'FDG' THEN 'metabolic'
                    WHEN 'AV45' THEN 'amyloid'
                    WHEN 'PIB' THEN 'amyloid'
                    WHEN 'AV1451' THEN 'tau'
                    WHEN 'MK6240' THEN 'tau'
                    ELSE 'other'
                END,
                tracer.created_at = datetime()
            """
            session.run(pet_tracer_query)

            # Second, link PET images to tracers
            pet_image_tracer_query = """
            MATCH (img:ImageNode)
            WHERE img.modality_type = 'PET' AND img.pet_tracer IS NOT NULL
            MATCH (tracer:PETTracer {tracer_name: img.pet_tracer})
            MERGE (img)-[:usesTracer]->(tracer)
            """
            session.run(pet_image_tracer_query)

            # Third, create temporal PET progression relationships
            pet_progression_query = """
            MATCH (p:Patient)
            MATCH (p)<-[:belongsToPatient]-(img1:ImageNode)
            MATCH (p)<-[:belongsToPatient]-(img2:ImageNode)
            WHERE img1.modality_type = 'PET' 
              AND img2.modality_type = 'PET'
              AND img1.pet_tracer = img2.pet_tracer
              AND img1.study_date < img2.study_date
              AND img1 <> img2

            MERGE (img1)-[:precedesPETScan {
                tracer: img1.pet_tracer,
                interval_type: 'longitudinal'
            }]->(img2)
            """
            session.run(pet_progression_query)

            # 4. Enhanced multimodal imaging relationships
            logger.info("Creating multimodal imaging relationships...")

            # Split multimodal query for better syntax compliance
            multimodal_session_query = """
            MATCH (p:Patient)
            MATCH (p)<-[:belongsToPatient]-(mri:ImageNode)
            MATCH (p)<-[:belongsToPatient]-(pet:ImageNode)
            WHERE mri.modality_type = 'MRI' 
              AND pet.modality_type = 'PET'
              AND abs(duration.between(date(mri.study_date), date(pet.study_date)).days) <= 30

            MERGE (mms:MultimodalSession {
                session_id: p.ptid + '_multimodal_' + mri.study_date + '_' + pet.study_date
            })
            SET mms.patient_id = p.ptid,
                mms.mri_date = mri.study_date,
                mms.pet_date = pet.study_date,
                mms.pet_tracer = pet.pet_tracer,
                mms.modalities = ['MRI', 'PET'],
                mms.created_at = datetime()

            MERGE (mri)-[:participatesInSession]->(mms)
            MERGE (pet)-[:participatesInSession]->(mms)
            MERGE (p)-[:hasMultimodalSession]->(mms)
            """
            session.run(multimodal_session_query)

            # Create complementary imaging relationships
            complementary_imaging_query = """
            MATCH (p:Patient)
            MATCH (p)<-[:belongsToPatient]-(mri:ImageNode)
            MATCH (p)<-[:belongsToPatient]-(pet:ImageNode)
            WHERE mri.modality_type = 'MRI' 
              AND pet.modality_type = 'PET'
              AND abs(duration.between(date(mri.study_date), date(pet.study_date)).days) <= 30

            MERGE (mri)-[:complementedBy {
                modality_pair: 'MRI-PET',
                pet_tracer: pet.pet_tracer
            }]->(pet)
            """
            session.run(complementary_imaging_query)

            # 5. Enhanced genetic risk relationships
            logger.info("Creating genetic risk relationships...")
            genetic_query = """
            // Process genetic findings
            MATCH (gf:GeneticFinding)
            MATCH (p:Patient {ptid: gf.ptid})

            // Create genetic risk profile
            MERGE (grp:GeneticRiskProfile {profile_id: gf.ptid + '_genetic_risk'})
            SET grp.patient_id = gf.ptid,
                grp.created_at = datetime()

            // Determine APOE status and risk level
            WITH gf, grp, p,
                 [key in keys(gf) WHERE key CONTAINS 'APOE'][0] as apoe_key
            WHERE apoe_key IS NOT NULL

            SET grp.apoe_genotype = gf[apoe_key],
                grp.risk_level = CASE 
                    WHEN toString(gf[apoe_key]) CONTAINS '4/4' THEN 'very_high'
                    WHEN toString(gf[apoe_key]) CONTAINS '3/4' OR toString(gf[apoe_key]) CONTAINS '4/3' THEN 'high'
                    WHEN toString(gf[apoe_key]) CONTAINS '2/4' OR toString(gf[apoe_key]) CONTAINS '4/2' THEN 'moderate'
                    WHEN toString(gf[apoe_key]) CONTAINS '2/2' OR toString(gf[apoe_key]) CONTAINS '2/3' THEN 'protective'
                    ELSE 'normal'
                END

            MERGE (p)-[:hasGeneticRiskProfile]->(grp)
            MERGE (gf)-[:contributesToProfile]->(grp)
            """
            session.run(genetic_query)

            # 6. Enhanced temporal progression relationships
            logger.info("Creating temporal progression relationships...")

            # Use batched approach for temporal relationships
            try:
                session.run("""
                    CALL apoc.periodic.iterate(
                        'MATCH (t1:ZeroDimensionalTemporalRegion) RETURN t1',
                        'MATCH (t2:ZeroDimensionalTemporalRegion)
                         WHERE t1.ptid = t2.ptid 
                           AND t1.months < t2.months
                           AND t2.months - t1.months <= 24
                         MERGE (t1)-[:precedesVisit {interval_months: t2.months - t1.months}]->(t2)
                         MERGE (t2)-[:followsVisit {interval_months: t2.months - t1.months}]->(t1)',
                        {batchSize: 1000, parallel: false}
                    )
                """)
            except:
                # Fallback if APOC not available
                session.run("""
                    MATCH (t1:ZeroDimensionalTemporalRegion)
                    MATCH (t2:ZeroDimensionalTemporalRegion)
                    WHERE t1.ptid = t2.ptid 
                      AND t1.months < t2.months
                      AND t2.months - t1.months <= 24
                    MERGE (t1)-[:precedesVisit {interval_months: t2.months - t1.months}]->(t2)
                    MERGE (t2)-[:followsVisit {interval_months: t2.months - t1.months}]->(t1)
                """)

            # 7. Family risk relationships
            logger.info("Creating family risk relationships...")
            family_risk_query = """
            // Calculate family risk based on affected relatives
            MATCH (p:Patient)-[:hasRelative]->(fm:FamilyMember)
            WHERE fm.has_dementia = true

            WITH p, count(fm) as affected_relatives,
                 sum(CASE WHEN fm.relationship_type = 'parent' THEN 2 
                          WHEN fm.relationship_type = 'sibling' THEN 1 
                          ELSE 0.5 END) as risk_score

            MERGE (fr:FamilyRisk {risk_id: p.ptid + '_family_risk'})
            SET fr.patient_id = p.ptid,
                fr.affected_relatives = affected_relatives,
                fr.risk_score = risk_score,
                fr.risk_category = CASE 
                    WHEN risk_score >= 4 THEN 'very_high'
                    WHEN risk_score >= 2 THEN 'high'
                    WHEN risk_score >= 1 THEN 'moderate'
                    ELSE 'low'
                END,
                fr.created_at = datetime()

            MERGE (p)-[:hasFamilyRisk]->(fr)

            WITH p, fr
            MATCH (p)-[:hasRelative]->(fm:FamilyMember)
            WHERE fm.has_dementia = true
            MERGE (fm)-[:contributesToRisk]->(fr)
            """
            session.run(family_risk_query)

            # 8. Create research cohorts with enhanced PET criteria
            logger.info("Creating research cohort relationships...")
            cohort_query = """
            // Create cohorts based on multiple criteria including PET availability
            MATCH (p:Patient)
            OPTIONAL MATCH (p)-[:hasDiagnosis]->(d:Diagnosis)
            OPTIONAL MATCH (p)-[:hasGeneticRiskProfile]->(grp:GeneticRiskProfile)
            OPTIONAL MATCH (p)<-[:belongsToPatient]-(pet:ImageNode)
            WHERE pet.modality_type = 'PET'

            WITH p, d, grp,
                 CASE 
                    WHEN d.severity = 'severe_impairment' THEN 'AD'
                    WHEN d.severity IN ['mild_impairment', 'moderate_impairment'] THEN 'MCI'
                    ELSE 'CN'
                 END as clinical_group,
                 coalesce(grp.risk_level, 'unknown') as genetic_risk,
                 CASE WHEN pet IS NOT NULL THEN 'with_PET' ELSE 'no_PET' END as imaging_status

            // Create cohort based on clinical, genetic, and imaging status
            WITH clinical_group + '_' + genetic_risk + '_' + imaging_status as cohort_name,
                 collect(p) as patients
            WHERE size(patients) >= 2

            MERGE (cohort:ResearchCohort {cohort_id: 'cohort_' + cohort_name})
            SET cohort.cohort_name = cohort_name,
                cohort.patient_count = size(patients),
                cohort.created_at = datetime()

            WITH cohort, patients
            UNWIND patients as patient
            MERGE (patient)-[:belongsToCohort]->(cohort)
            """
            session.run(cohort_query)

            logger.info("✅ Created comprehensive relationships based on extended AD-DPC ontology")

    def create_ad_ontology_relationships(self) -> None:
        """Create relationships based on AD-DPC ontology paper"""
        logger.info("Creating AD-specific ontology relationships...")

        with self.driver.session() as session:
            # 1. Create disease progression relationships
            self._create_disease_progression_relationships(session)

            # 2. Create symptom-biomarker correlations
            self._create_symptom_biomarker_correlations(session)

            # 3. Create imaging-clinical correlations
            self._create_imaging_clinical_correlations(session)

            # 4. Create treatment response relationships
            self._create_treatment_relationships(session)

            # 5. Create additional relationships
            self._create_enhanced_ad_relationships(session)

    def _create_disease_progression_relationships(self, session):
        """Create disease stage progression relationships"""

        # Create disease stages
        stage_query = """
        // Create disease stage nodes
        MERGE (preclinical:DiseaseStage {stage_id: 'preclinical'})
        SET preclinical.stage_name = 'Preclinical AD',
            preclinical.description = 'Biomarker positive, cognitively normal'

        MERGE (mci:DiseaseStage {stage_id: 'mci'})
        SET mci.stage_name = 'Mild Cognitive Impairment',
            mci.description = 'Mild cognitive decline with biomarker evidence'

        MERGE (mild_ad:DiseaseStage {stage_id: 'mild_ad'})
        SET mild_ad.stage_name = 'Mild AD',
            mild_ad.description = 'Early stage Alzheimer\'s disease'

        MERGE (moderate_ad:DiseaseStage {stage_id: 'moderate_ad'})
        SET moderate_ad.stage_name = 'Moderate AD',
            moderate_ad.description = 'Moderate stage Alzheimer\'s disease'

        MERGE (severe_ad:DiseaseStage {stage_id: 'severe_ad'})
        SET severe_ad.stage_name = 'Severe AD',
            severe_ad.description = 'Advanced Alzheimer\'s disease'

        // Create progression relationships
        MERGE (preclinical)-[:progressesTo]->(mci)
        MERGE (mci)-[:progressesTo]->(mild_ad)
        MERGE (mild_ad)-[:progressesTo]->(moderate_ad)
        MERGE (moderate_ad)-[:progressesTo]->(severe_ad)
        """
        session.run(stage_query)

        # Link patients to disease stages
        patient_stage_query = """
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[:hasDiagnosis]->(d:Diagnosis)
        OPTIONAL MATCH (p)<-[:belongsToPatient]-(pf:PsychometricFinding)
        WHERE pf.clinical_significance IS NOT NULL

        WITH p, d, collect(pf) as findings

        // Determine disease stage based on findings
        WITH p, d, findings,
             CASE 
                WHEN d.severity = 'severe_impairment' THEN 'severe_ad'
                WHEN d.severity = 'moderate_impairment' THEN 'moderate_ad'
                WHEN d.severity = 'mild_impairment' THEN 'mci'
                WHEN any(f in findings WHERE f.clinical_significance = 'abnormal') THEN 'preclinical'
                ELSE 'normal'
             END as stage_id

        WHERE stage_id <> 'normal'
        MATCH (stage:DiseaseStage {stage_id: stage_id})
        MERGE (p)-[:hasCurrentStage]->(stage)
        """
        session.run(patient_stage_query)

    def _create_symptom_biomarker_correlations(self, session):
        """Create correlations between symptoms and biomarkers"""

        correlation_query = """
        // Find patients with both cognitive scores and biomarkers
        MATCH (p:Patient)
        MATCH (p)<-[:belongsToPatient]-(cf:PsychometricFinding)
        MATCH (p)<-[:belongsToPatient]-(bf:BiomarkerFinding)
        WHERE cf.months = bf.months  // Same timepoint

        // Create symptom nodes
        MERGE (symptom:CognitiveSymptom {
            symptom_id: cf.finding_subtype + '_' + cf.clinical_significance
        })
        SET symptom.symptom_type = cf.finding_subtype,
            symptom.severity = cf.clinical_significance

        // Create biomarker pattern nodes
        MERGE (pattern:BiomarkerPattern {
            pattern_id: bf.finding_subtype + '_' + bf.clinical_significance
        })
        SET pattern.biomarker_type = bf.finding_subtype,
            pattern.pattern_type = bf.clinical_significance

        // Create correlation
        MERGE (symptom)-[:correlatesWith {
            confidence: (cf.confidence_score + bf.confidence_score) / 2.0,
            timepoint: cf.months
        }]->(pattern)

        // Link to patient
        MERGE (p)-[:exhibits]->(symptom)
        MERGE (p)-[:hasBiomarkerPattern]->(pattern)
        """
        session.run(correlation_query)

    def _create_imaging_clinical_correlations(self, session):
        """Create relationships between imaging findings and clinical symptoms"""

        imaging_correlation_query = """
        // Correlate brain atrophy with cognitive decline
        MATCH (p:Patient)
        MATCH (p)<-[:belongsToPatient]-(img:ImageNode)
        WHERE img.anatomical_region IS NOT NULL
        MATCH (p)<-[:belongsToPatient]-(cf:ClinicalFinding)
        WHERE cf.finding_type = 'psychometric'
          AND abs(cf.months - 0) <= 6  // Within 6 months

        // Create brain region nodes
        MERGE (region:BrainRegion {region_id: img.anatomical_region})
        SET region.region_name = img.anatomical_region

        // Create atrophy finding
        MERGE (atrophy:AtrophyFinding {
            finding_id: p.ptid + '_' + region.region_id + '_atrophy'
        })
        SET atrophy.patient_id = p.ptid,
            atrophy.region = region.region_id,
            atrophy.modality = img.modality_type

        // Link relationships
        MERGE (img)-[:revealsAtrophyIn]->(region)
        MERGE (region)-[:showsAtrophy]->(atrophy)
        MERGE (atrophy)-[:associatedWith]->(cf)
        MERGE (p)-[:hasAtrophyIn]->(region)
        """
        session.run(imaging_correlation_query)

    def _create_treatment_relationships(self, session):
        """Create treatment and intervention relationships"""

        treatment_query = """
        // Create treatment categories
        MERGE (pharm:TreatmentCategory {category_id: 'pharmacological'})
        SET pharm.category_name = 'Pharmacological Interventions'

        MERGE (lifestyle:TreatmentCategory {category_id: 'lifestyle'})
        SET lifestyle.category_name = 'Lifestyle Interventions'

        MERGE (cognitive:TreatmentCategory {category_id: 'cognitive'})
        SET cognitive.category_name = 'Cognitive Training'

        // Link to research protocols
        MATCH (p:Patient)
        MATCH (p)-[:belongsToCohort]->(c:ResearchCohort)

        // Create protocol nodes
        MERGE (protocol:ResearchProtocol {
            protocol_id: c.cohort_id + '_protocol'
        })
        SET protocol.cohort_name = c.cohort_name,
            protocol.patient_count = c.patient_count

        MERGE (c)-[:followsProtocol]->(protocol)
        MERGE (p)-[:participatesInProtocol]->(protocol)
        """
        session.run(treatment_query)

    def _create_enhanced_ad_relationships(self, session):
        """Create additional relationships based on AD-DPC ontology paper"""

        # 1. Create pathophysiological process relationships
        pathophysiology_query = """
        // Create core AD pathophysiological processes
        MERGE (abeta:PathophysiologicalProcess {process_id: 'abeta_accumulation'})
        SET abeta.process_name = 'Amyloid Beta Accumulation',
            abeta.description = 'Progressive accumulation of amyloid beta plaques'

        MERGE (tau:PathophysiologicalProcess {process_id: 'tau_pathology'})
        SET tau.process_name = 'Tau Pathology',
            tau.description = 'Neurofibrillary tangle formation'

        MERGE (neuro:PathophysiologicalProcess {process_id: 'neurodegeneration'})
        SET neuro.process_name = 'Neurodegeneration',
            neuro.description = 'Progressive neuronal loss'

        MERGE (inflam:PathophysiologicalProcess {process_id: 'neuroinflammation'})
        SET inflam.process_name = 'Neuroinflammation',
            inflam.description = 'Chronic brain inflammation'

        // Create process cascade relationships
        MERGE (abeta)-[:triggers]->(tau)
        MERGE (tau)-[:causes]->(neuro)
        MERGE (abeta)-[:promotes]->(inflam)
        MERGE (inflam)-[:accelerates]->(neuro)
        """
        session.run(pathophysiology_query)

        # 2. Link imaging findings to pathophysiological processes
        imaging_pathophysiology_query = """
        // Link PET findings to pathophysiological processes
        MATCH (img:ImageNode)
        WHERE img.modality_type = 'PET'

        WITH img
        MATCH (abeta:PathophysiologicalProcess {process_id: 'abeta_accumulation'})
        MATCH (tau:PathophysiologicalProcess {process_id: 'tau_pathology'})
        MATCH (neuro:PathophysiologicalProcess {process_id: 'neurodegeneration'})

        // Amyloid PET
        FOREACH (ignored IN CASE 
            WHEN img.pet_tracer IN ['AV45', 'PIB'] THEN [1] 
            ELSE [] END |
            MERGE (img)-[:detects]->(abeta)
        )

        // Tau PET
        FOREACH (ignored IN CASE 
            WHEN img.pet_tracer IN ['AV1451', 'MK6240'] THEN [1] 
            ELSE [] END |
            MERGE (img)-[:detects]->(tau)
        )

        // FDG PET (metabolism)
        FOREACH (ignored IN CASE 
            WHEN img.pet_tracer = 'FDG' THEN [1] 
            ELSE [] END |
            MERGE (img)-[:indicates]->(neuro)
        )
        """
        session.run(imaging_pathophysiology_query)

        # 3. Create cognitive domain relationships
        cognitive_domains_query = """
        // Create cognitive domains
        MERGE (memory:CognitiveDomain {domain_id: 'memory'})
        SET memory.domain_name = 'Memory',
            memory.description = 'Episodic and semantic memory'

        MERGE (exec:CognitiveDomain {domain_id: 'executive'})
        SET exec.domain_name = 'Executive Function',
            exec.description = 'Planning, attention, and cognitive control'

        MERGE (lang:CognitiveDomain {domain_id: 'language'})
        SET lang.domain_name = 'Language',
            lang.description = 'Verbal fluency and comprehension'

        MERGE (visuo:CognitiveDomain {domain_id: 'visuospatial'})
        SET visuo.domain_name = 'Visuospatial',
            visuo.description = 'Spatial orientation and visual processing'

        // Link assessments to cognitive domains
        WITH memory, exec, lang, visuo
        MATCH (pf:PsychometricFinding)

        // Memory assessments
        FOREACH (ignored IN CASE 
            WHEN pf.finding_subtype IN ['memory_assessment', 'global_cognitive'] THEN [1] 
            ELSE [] END |
            MERGE (pf)-[:assesses]->(memory)
        )

        // Executive function assessments
        FOREACH (ignored IN CASE 
            WHEN pf.finding_subtype IN ['functional_assessment', 'cognitive_assessment'] THEN [1] 
            ELSE [] END |
            MERGE (pf)-[:assesses]->(exec)
        )

        // Language assessments
        FOREACH (ignored IN CASE 
            WHEN pf.finding_subtype = 'language_assessment' THEN [1] 
            ELSE [] END |
            MERGE (pf)-[:assesses]->(lang)
        )

        // Visuospatial assessments
        FOREACH (ignored IN CASE 
            WHEN pf.finding_subtype = 'visuospatial_assessment' THEN [1] 
            ELSE [] END |
            MERGE (pf)-[:assesses]->(visuo)
        )
        """
        session.run(cognitive_domains_query)

        # 4. Create brain connectivity relationships
        brain_connectivity_query = """
        // Create brain network nodes
        MERGE (dmn:BrainNetwork {network_id: 'default_mode'})
        SET dmn.network_name = 'Default Mode Network',
            dmn.description = 'Resting state network affected early in AD'

        MERGE (hippo:BrainNetwork {network_id: 'hippocampal'})
        SET hippo.network_name = 'Hippocampal Network',
            hippo.description = 'Memory formation network'

        // Link brain regions to networks
        MATCH (img:ImageNode)
        WHERE img.anatomical_region IS NOT NULL

        WITH img, dmn, hippo

        // Hippocampal network connections
        FOREACH (ignored IN CASE 
            WHEN img.anatomical_region IN ['hippocampus', 'temporal_lobe'] THEN [1] 
            ELSE [] END |
            MERGE (img)-[:locatedIn]->(hippo)
        )

        // Default mode network connections
        FOREACH (ignored IN CASE 
            WHEN img.anatomical_region IN ['cortex', 'parietal_lobe'] THEN [1] 
            ELSE [] END |
            MERGE (img)-[:locatedIn]->(dmn)
        )
        """
        session.run(brain_connectivity_query)

    def generate_comprehensive_report(self) -> None:
        """Generate a comprehensive report of the created knowledge graph - Enhanced for PET"""
        logger.info("=" * 60)
        logger.info("COMPREHENSIVE ADNI KNOWLEDGE GRAPH REPORT (MRI + PET)")
        logger.info("=" * 60)

        with self.driver.session() as session:

            # 1. Node Statistics
            logger.info("\n📊 NODE STATISTICS:")

            # Define all node labels including PET-specific ones
            node_labels = [
                'Patient', 'ParticipantFile', 'ImageNode', 'ImagingStudy', 'ImagingSeries',
                'ZeroDimensionalTemporalRegion', 'Constitutional', 'Diagnosis',
                'PsychometricFinding', 'BiomarkerFinding', 'GeneticFinding',
                'ClinicalFinding', 'BehavioralFinding', 'ImagingFinding',
                'Assessment', 'MRITest', 'PETTest', 'FamilyMember', 'FamilyHistory',
                'FamilyRisk', 'GeneticRiskProfile', 'BiologicalPathway',
                'MultimodalAssessment', 'MultimodalSession', 'ResearchCohort',
                'PETTracer'  # NEW
            ]

            total_nodes = 0
            for label in node_labels:
                try:
                    result = session.run(f"MATCH (n:{label}) RETURN count(n) as count")
                    count = result.single()['count']
                    if count > 0:
                        logger.info(f"  {label:<30} : {count:>8,}")
                        total_nodes += count
                except Exception:
                    continue

            logger.info(f"  {'TOTAL NODES':<30} : {total_nodes:>8,}")

            # 2. Relationship Statistics
            logger.info("\n🔗 RELATIONSHIP STATISTICS:")
            rel_query = """
            MATCH ()-[r]->()
            RETURN type(r) as relationship_type, count(r) as count
            ORDER BY count DESC
            LIMIT 25
            """
            result = session.run(rel_query)
            total_relationships = 0
            for record in result:
                count = record['count']
                logger.info(f"  {record['relationship_type']:<30} : {count:>8,}")
                total_relationships += count

            # Total relationships
            total_rel_result = session.run("MATCH ()-[r]->() RETURN count(r) as total")
            total_relationships = total_rel_result.single()['total']
            logger.info(f"  {'TOTAL RELATIONSHIPS':<30} : {total_relationships:>8,}")

            # 3. Patient Statistics - Enhanced
            logger.info("\n👥 PATIENT STATISTICS:")

            # Total patients
            total_patients_result = session.run("MATCH (p:Patient) RETURN count(p) as count")
            total_patients = total_patients_result.single()['count']
            logger.info(f"  Total patients                 : {total_patients:>8,}")

            # Patients with MRI images
            patients_with_mri = session.run("""
                MATCH (p:Patient)<-[:belongsToPatient]-(img:ImageNode)
                WHERE img.modality_type = 'MRI'
                RETURN count(DISTINCT p) as count
            """).single()['count']
            logger.info(f"  Patients with MRI images       : {patients_with_mri:>8,}")

            # Patients with PET images - NEW
            patients_with_pet = session.run("""
                MATCH (p:Patient)<-[:belongsToPatient]-(img:ImageNode)
                WHERE img.modality_type = 'PET'
                RETURN count(DISTINCT p) as count
            """).single()['count']
            logger.info(f"  Patients with PET images       : {patients_with_pet:>8,}")

            # Patients with both MRI and PET - NEW
            patients_with_both = session.run("""
                MATCH (p:Patient)<-[:belongsToPatient]-(mri:ImageNode)
                MATCH (p)<-[:belongsToPatient]-(pet:ImageNode)
                WHERE mri.modality_type = 'MRI' AND pet.modality_type = 'PET'
                RETURN count(DISTINCT p) as count
            """).single()['count']
            logger.info(f"  Patients with both MRI & PET   : {patients_with_both:>8,}")

            # Patients with findings
            patients_with_findings = session.run("""
                MATCH (p:Patient)
                WHERE (p)<-[:belongsToPatient]-(:ClinicalFinding)
                   OR (p)-[:undergoesAssessment]->()<-[:isOutputOf]-(:ClinicalFinding)
                RETURN count(DISTINCT p) as count
            """).single()['count']
            logger.info(f"  Patients with findings         : {patients_with_findings:>8,}")

            # Patients with diagnoses
            patients_with_diagnoses = session.run("""
                MATCH (p:Patient)
                WHERE (p)-[:hasDiagnosis]->()
                RETURN count(DISTINCT p) as count
            """).single()['count']
            logger.info(f"  Patients with diagnoses        : {patients_with_diagnoses:>8,}")

            # Patients with family members
            patients_with_family = session.run("""
                MATCH (p:Patient)
                WHERE (p)-[:hasRelative]->()
                RETURN count(DISTINCT p) as count
            """).single()['count']
            logger.info(f"  Patients with family data      : {patients_with_family:>8,}")

            # Patients with genetic data
            patients_with_genetic = session.run("""
                MATCH (p:Patient)
                WHERE (p)-[:hasGeneticRiskProfile]->()
                   OR (p)<-[:belongsToPatient]-(:GeneticFinding)
                RETURN count(DISTINCT p) as count
            """).single()['count']
            logger.info(f"  Patients with genetic data     : {patients_with_genetic:>8,}")

            # 4. Enhanced Imaging Statistics
            logger.info("\n🖼️  IMAGING STATISTICS:")

            # Images by modality type - Enhanced
            modality_type_stats = session.run("""
                MATCH (img:ImageNode)
                RETURN img.modality_type as modality_type, count(*) as count
                ORDER BY count DESC
            """)
            for record in modality_type_stats:
                if record['modality_type']:
                    logger.info(f"  {record['modality_type']:<20} images : {record['count']:>8,}")

            # Images by specific modality
            imaging_stats = session.run("""
                MATCH (img:ImageNode)
                RETURN img.modality as modality, img.modality_type as type, count(*) as count
                ORDER BY type, count DESC
            """)
            logger.info("\n  Detailed modality breakdown:")
            for record in imaging_stats:
                if record['modality'] and record['type']:
                    logger.info(f"    {record['type']}-{record['modality']:<15} : {record['count']:>8,}")

            # PET tracer statistics - NEW
            logger.info("\n  PET Tracer Statistics:")
            pet_tracer_stats = session.run("""
                MATCH (img:ImageNode)
                WHERE img.modality_type = 'PET' AND img.pet_tracer IS NOT NULL
                RETURN img.pet_tracer as tracer, count(*) as count
                ORDER BY count DESC
            """)
            for record in pet_tracer_stats:
                if record['tracer']:
                    logger.info(f"    {record['tracer']:<20} : {record['count']:>8,}")

            # Images with blobs
            images_with_blobs = session.run("""
                MATCH (img:ImageNode)
                WHERE img.has_blob = true
                RETURN count(img) as count
            """).single()['count']
            logger.info(f"\n  Images with blob data          : {images_with_blobs:>8,}")

            # Multimodal sessions - NEW
            multimodal_sessions = session.run("""
                MATCH (mms:MultimodalSession)
                RETURN count(mms) as count
            """).single()['count']
            logger.info(f"  Multimodal sessions            : {multimodal_sessions:>8,}")

            # 5. Temporal Coverage
            logger.info("\n⏰ TEMPORAL COVERAGE:")
            temporal_stats = session.run("""
                MATCH (t:ZeroDimensionalTemporalRegion)
                RETURN min(t.months) as min_months, 
                       max(t.months) as max_months,
                       count(DISTINCT t.months) as unique_timepoints
            """).single()

            if temporal_stats['min_months'] is not None:
                logger.info(f"  Min months from baseline       : {temporal_stats['min_months']:>8}")
                logger.info(f"  Max months from baseline       : {temporal_stats['max_months']:>8}")
                logger.info(f"  Unique timepoints              : {temporal_stats['unique_timepoints']:>8}")

            # 6. Finding Statistics by Type
            logger.info("\n📋 FINDINGS BY TYPE:")
            findings_by_type = session.run("""
                MATCH (f:ClinicalFinding)
                RETURN f.finding_type as type, count(f) as count
                ORDER BY count DESC
            """)
            for record in findings_by_type:
                if record['type']:
                    logger.info(f"  {record['type'].capitalize():<20} findings : {record['count']:>8,}")

            # 7. Family Member Statistics
            logger.info("\n👨‍👩‍👧‍👦 FAMILY MEMBER STATISTICS:")

            # Total family members
            total_family = session.run("MATCH (fm:FamilyMember) RETURN count(fm) as count").single()['count']
            logger.info(f"  Total family members           : {total_family:>8,}")

            # Family members by relationship
            family_by_rel = session.run("""
                MATCH (fm:FamilyMember)
                RETURN fm.relationship_type as rel_type, count(fm) as count
                ORDER BY count DESC
            """)
            for record in family_by_rel:
                if record['rel_type']:
                    logger.info(f"  {record['rel_type'].capitalize():<20} : {record['count']:>8,}")

            # Family members with dementia
            family_with_dementia = session.run("""
                MATCH (fm:FamilyMember)
                WHERE fm.has_dementia = true
                RETURN count(fm) as count
            """).single()['count']
            logger.info(f"  Family with dementia           : {family_with_dementia:>8,}")

            # 8. Enhanced PET-Specific Statistics
            logger.info("\n🧠 PET-SPECIFIC STATISTICS:")

            # PET tracers
            pet_tracers = session.run("""
                MATCH (pt:PETTracer)
                RETURN pt.tracer_name as tracer, pt.tracer_type as type, count(pt) as count
                ORDER BY count DESC
            """)
            for record in pet_tracers:
                if record['tracer']:
                    logger.info(f"  {record['tracer']:<15} ({record['type']:<10}) : {record['count']:>8,}")

            # Biological pathways
            pathway_stats = session.run("""
                MATCH (bp:BiologicalPathway)
                RETURN bp.pathway_name as pathway, count(bp) as count
                ORDER BY count DESC
            """)
            logger.info("\n  Biological Pathways:")
            for record in pathway_stats:
                if record['pathway']:
                    logger.info(f"    {record['pathway']:<30} : {record['count']:>8,}")

            # PET-pathway connections
            pet_pathway_connections = session.run("""
                MATCH (img:ImageNode)-[:revealsPathwayActivity]->(bp:BiologicalPathway)
                WHERE img.modality_type = 'PET'
                RETURN bp.pathway_name as pathway, count(img) as image_count
                ORDER BY image_count DESC
            """)
            logger.info("\n  PET-Pathway Connections:")
            for record in pet_pathway_connections:
                if record['pathway']:
                    logger.info(f"    {record['pathway']:<30} : {record['image_count']:>8,} images")

            # 9. Data Quality Metrics
            logger.info("\n📈 DATA QUALITY METRICS:")

            # Average confidence scores
            avg_confidence = session.run("""
                MATCH (f:ClinicalFinding)
                WHERE f.confidence_score IS NOT NULL
                RETURN avg(f.confidence_score) as avg_confidence
            """).single()

            if avg_confidence['avg_confidence']:
                logger.info(f"  Avg confidence score           : {avg_confidence['avg_confidence']:>8.2f}")

            # Clinical significance distribution
            significance_dist = session.run("""
                MATCH (f:ClinicalFinding)
                WHERE f.clinical_significance IS NOT NULL
                RETURN f.clinical_significance as significance, count(f) as count
                ORDER BY count DESC
            """)
            logger.info("\n  Clinical Significance Distribution:")
            for record in significance_dist:
                if record['significance']:
                    logger.info(f"    {record['significance']:<25} : {record['count']:>8,}")

            # Completeness metrics
            complete_patients = session.run("""
                MATCH (p:Patient)
                WHERE p.gender IS NOT NULL 
                  AND p.age_at_baseline IS NOT NULL
                  AND p.education_years IS NOT NULL
                RETURN count(p) as complete_patients
            """).single()['complete_patients']

            if total_patients > 0:
                completeness = (complete_patients / total_patients) * 100
                logger.info(f"\n  Patient data completeness      : {completeness:>8.1f}%")

            # 10. Research Cohort Statistics
            logger.info("\n🔬 RESEARCH COHORT STATISTICS:")
            cohort_stats = session.run("""
                MATCH (c:ResearchCohort)
                RETURN c.cohort_name as name, c.patient_count as count
                ORDER BY count DESC
            """)
            for record in cohort_stats:
                if record['name']:
                    logger.info(f"  {record['name']:<35} : {record['count']:>8,} patients")

            # 11. Performance Metrics
            logger.info("\n⚡ PERFORMANCE METRICS:")

            # Index usage
            try:
                index_count = session.run("""
                    SHOW INDEXES
                    YIELD name
                    RETURN count(*) as count
                """).single()['count']
                logger.info(f"  Total indexes                  : {index_count:>8,}")
            except:
                logger.info("  Total indexes                  : Unable to retrieve")

            # Constraint count
            try:
                constraint_count = session.run("""
                    SHOW CONSTRAINTS
                    YIELD name
                    RETURN count(*) as count
                """).single()['count']
                logger.info(f"  Total constraints              : {constraint_count:>8,}")
            except:
                logger.info("  Total constraints              : Unable to retrieve")

            logger.info("\n" + "=" * 60)
            logger.info("✅ ENHANCED KNOWLEDGE GRAPH CREATION COMPLETED SUCCESSFULLY")
            logger.info("🧠 MRI + PET MULTIMODAL SUPPORT ENABLED")
            logger.info("=" * 60)


def main():
    """
    Main execution function for the Enhanced ADNI Knowledge Graph Pipeline with PET Support.

    This function orchestrates the entire pipeline execution with improved
    performance, better error handling, enhanced data modeling, and full PET support.
    """

    # =============================================================================
    # CONFIGURATION SECTION
    # =============================================================================

    # Neo4j Configuration - Update these with your actual credentials
    NEO4J_URI = "bolt://localhost:7687"  # or "neo4j://localhost:7687" for newer versions
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "your_password"  # Change this to your actual password

    # Path Configuration
    BASE_PATH = "inputs"  # Directory containing Tables, Images, and PET folders
    MAX_WORKERS = 8  # Number of concurrent threads for better performance

    # =============================================================================
    # EXECUTION CONTROL FLAGS
    # =============================================================================
    # These flags allow you to control which steps of the pipeline execute

    CLEAR_DATABASE = True  # WARNING: This will delete all existing data!
    CREATE_SCHEMA = True  # Create constraints and indexes
    LOAD_TABLES = True  # Load and process CSV tables
    PROCESS_IMAGES = True  # Process and extract image metadata
    PROCESS_MRI = True  # Process MRI images from Images/Updated folders
    PROCESS_PET = True  # Process PET images from PET/Updated_PET folders **NEW**
    STORE_IMAGE_BLOBS = False  # Store image data as blobs (increases database size)
    CREATE_PATIENT_RECORDS = True  # Create enhanced patient records
    EXTRACT_FAMILY = True  # Extract family member information
    CREATE_FINDINGS = True  # Extract clinical findings from tables
    INSERT_PATIENTS = True  # Insert patients into Neo4j
    INSERT_FAMILY = True  # Insert family members into Neo4j
    INSERT_IMAGES = True  # Insert images and metadata into Neo4j
    INSERT_FINDINGS = True  # Insert clinical findings into Neo4j
    CREATE_RELATIONSHIPS = True  # Create comprehensive relationships
    GENERATE_REPORT = True  # Generate final pipeline report

    # =============================================================================
    # PIPELINE EXECUTION
    # =============================================================================

    # Initialize the pipeline with error handling
    pipeline = None
    start_time = datetime.now()

    try:
        logger.info("🚀 Starting Enhanced ADNI Knowledge Graph Pipeline with PET Support...")
        logger.info(f"📁 Base path: {BASE_PATH}")
        logger.info(f"🔧 Max workers: {MAX_WORKERS}")
        logger.info(f"🔗 Neo4j URI: {NEO4J_URI}")
        logger.info(f"📸 Image blob storage: {'Enabled' if STORE_IMAGE_BLOBS else 'Disabled'}")
        logger.info(f"🧠 MRI processing: {'Enabled' if PROCESS_MRI else 'Disabled'}")
        logger.info(f"🧠 PET processing: {'Enabled' if PROCESS_PET else 'Disabled'}")

        # Initialize pipeline
        pipeline = OptimizedADNIKnowledgeGraphPipeline(
            neo4j_uri=NEO4J_URI,
            neo4j_user=NEO4J_USER,
            neo4j_password=NEO4J_PASSWORD,
            base_path=BASE_PATH,
            max_workers=MAX_WORKERS
        )

        # Test Neo4j connection
        logger.info("🔍 Testing Neo4j connection...")
        with pipeline.driver.session() as session:
            result = session.run("RETURN 'Connection successful' as message")
            logger.info(f"✅ {result.single()['message']}")

        # =============================================================================
        # STEP 1: DATABASE PREPARATION
        # =============================================================================

        if CLEAR_DATABASE:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 1: CLEARING DATABASE")
            logger.info("=" * 50)

            # Add confirmation prompt for safety
            confirmation = input("⚠️  WARNING: This will delete all data in the database. Continue? (yes/no): ")
            if confirmation.lower() != 'yes':
                logger.info("❌ Database clearing cancelled by user")
                return

            pipeline.clear_database()
            logger.info("✅ Database cleared successfully")

        if CREATE_SCHEMA:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 2: CREATING DATABASE SCHEMA")
            logger.info("=" * 50)

            pipeline.create_comprehensive_constraints_and_indexes()
            logger.info("✅ Database schema created successfully")

        # =============================================================================
        # STEP 2: DATA LOADING AND PROCESSING
        # =============================================================================

        # Load and process tables
        table_data = {}
        if LOAD_TABLES:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 3: LOADING TABLE DATA")
            logger.info("=" * 50)

            table_data = pipeline.load_and_process_tables()
            if not table_data:
                logger.error("❌ No table data loaded. Please check the Tables directory.")
                return
            logger.info(f"✅ Loaded {len(table_data)} tables successfully")

        # Create patient records
        patient_records = []
        if CREATE_PATIENT_RECORDS:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 4: CREATING PATIENT RECORDS")
            logger.info("=" * 50)

            if not table_data:
                logger.error("❌ Cannot create patient records: No table data available")
                return

            patient_records = pipeline.create_enhanced_patient_records(table_data)
            logger.info(f"✅ Created {len(patient_records)} patient records successfully")

        # Extract family members
        family_members = []
        if EXTRACT_FAMILY:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 5: EXTRACTING FAMILY MEMBERS")
            logger.info("=" * 50)

            if not table_data:
                logger.error("❌ Cannot extract family members: No table data available")
                return

            family_members = pipeline.extract_family_members(table_data)
            logger.info(f"✅ Extracted {len(family_members)} family member records")

        # Process images (MRI and/or PET)
        image_metadata = []
        if PROCESS_IMAGES:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 6: PROCESSING IMAGES (MRI + PET)")
            logger.info("=" * 50)

            image_metadata = pipeline.process_images_with_metadata(
                store_blobs=STORE_IMAGE_BLOBS,
                process_mri=PROCESS_MRI,
                process_pet=PROCESS_PET
            )
            logger.info(f"✅ Processed {len(image_metadata)} total images successfully")

        # Create clinical findings
        clinical_findings = []
        if CREATE_FINDINGS:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 7: CREATING CLINICAL FINDINGS")
            logger.info("=" * 50)

            if not table_data or not patient_records:
                logger.error("❌ Cannot create findings: Missing table data or patient records")
                return

            clinical_findings = pipeline.create_clinical_findings_from_tables(table_data, patient_records)
            logger.info(f"✅ Created {len(clinical_findings)} clinical findings successfully")

        # =============================================================================
        # STEP 3: BATCH FILE CREATION
        # =============================================================================

        logger.info("\n" + "=" * 50)
        logger.info("STEP 8: CREATING BATCH FILES")
        logger.info("=" * 50)

        batch_files = pipeline.create_batch_files_for_insertion(
            patient_records, family_members, image_metadata, clinical_findings
        )
        logger.info("✅ Batch files created successfully")

        # =============================================================================
        # STEP 4: NEO4J INSERTION
        # =============================================================================

        if INSERT_PATIENTS:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 9: INSERTING PATIENTS")
            logger.info("=" * 50)

            pipeline.batch_insert_patients_enhanced(batch_files['patients'])
            logger.info("✅ Patients inserted successfully")

        if INSERT_FAMILY and family_members:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 10: INSERTING FAMILY MEMBERS")
            logger.info("=" * 50)

            pipeline.batch_insert_family_members(batch_files['family'])
            logger.info("✅ Family members inserted successfully")

        if INSERT_IMAGES and image_metadata:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 11: INSERTING IMAGES (MRI + PET)")
            logger.info("=" * 50)

            pipeline.batch_insert_images_enhanced(batch_files['images'])
            logger.info("✅ Images inserted successfully")

        if INSERT_FINDINGS and clinical_findings:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 12: INSERTING FINDINGS")
            logger.info("=" * 50)

            pipeline.batch_insert_findings_enhanced(batch_files['findings'])
            logger.info("✅ Findings inserted successfully")

        # =============================================================================
        # STEP 5: RELATIONSHIP CREATION
        # =============================================================================

        if CREATE_RELATIONSHIPS:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 13: CREATING RELATIONSHIPS")
            logger.info("=" * 50)

            pipeline.create_comprehensive_relationships()

            # Add AD-specific relationships
            pipeline.create_ad_ontology_relationships()

            logger.info("✅ Relationships created successfully")

        # =============================================================================
        # STEP 6: FINAL REPORT
        # =============================================================================

        if GENERATE_REPORT:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 14: GENERATING FINAL REPORT")
            logger.info("=" * 50)

            pipeline.generate_comprehensive_report()

        # =============================================================================
        # STEP 7: KG SCHEMA MIGRATION (Steps 17–20)
        # =============================================================================
        # These steps transform the LPG into a semantic Knowledge Graph by adding
        # ontology codes, ICD-10 integration, and MAPS_TO/IS_A relationships.
        # They use the modular step files from the steps/ directory.

        RUN_CONSTRAINTS = True       # Step 17: Composite constraints + indexes
        RUN_ONTOLOGY_PROPS = True    # Step 18: Add ontology codes to existing nodes
        RUN_ICD10 = True             # Step 19: ICD-10 integration
        RUN_ONTOLOGY_LAYER = True    # Step 20: Full ontology layer + MAPS_TO

        if RUN_CONSTRAINTS:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 17: APPLYING KG CONSTRAINTS & INDEXES")
            logger.info("=" * 50)
            from steps.step17_apply_constraints import execute_constraints
            execute_constraints(
                neo4j_uri=NEO4J_URI,
                neo4j_user=NEO4J_USER,
                neo4j_password=NEO4J_PASSWORD,
            )
            logger.info("✅ KG constraints applied successfully")

        if RUN_ONTOLOGY_PROPS:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 18: ADDING ONTOLOGY PROPERTIES")
            logger.info("=" * 50)
            from steps.step18_add_ontology_properties import execute_ontology_properties
            execute_ontology_properties(
                neo4j_uri=NEO4J_URI,
                neo4j_user=NEO4J_USER,
                neo4j_password=NEO4J_PASSWORD,
            )
            logger.info("✅ Ontology properties added successfully")

        if RUN_ICD10:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 19: ICD-10 INTEGRATION")
            logger.info("=" * 50)
            from steps.step19_icd10_integration import execute_icd10_integration
            execute_icd10_integration(
                neo4j_uri=NEO4J_URI,
                neo4j_user=NEO4J_USER,
                neo4j_password=NEO4J_PASSWORD,
            )
            logger.info("✅ ICD-10 integration completed successfully")

        if RUN_ONTOLOGY_LAYER:
            logger.info("\n" + "=" * 50)
            logger.info("STEP 20: ONTOLOGY LAYER + MAPS_TO")
            logger.info("=" * 50)
            from steps.step20_ontology_layer import execute_ontology_layer
            execute_ontology_layer(
                neo4j_uri=NEO4J_URI,
                neo4j_user=NEO4J_USER,
                neo4j_password=NEO4J_PASSWORD,
            )
            logger.info("✅ Ontology layer built successfully")

        # Calculate execution time
        end_time = datetime.now()
        duration = end_time - start_time

        logger.info("\n" + "🎉" + "=" * 58 + "🎉")
        logger.info("🎉  ENHANCED ADNI KNOWLEDGE GRAPH PIPELINE COMPLETED      🎉")
        logger.info("🎉  WITH FULL MRI + PET MULTIMODAL SUPPORT                🎉")
        logger.info(f"🎉  Total execution time: {duration}                      🎉")
        logger.info("🎉" + "=" * 58 + "🎉")

    except KeyboardInterrupt:
        logger.info("\n❌ Pipeline execution interrupted by user")

    except Exception as e:
        logger.error(f"\n❌ Pipeline execution failed with error: {str(e)}")
        logger.error("Full error details:", exc_info=True)

    finally:
        # Always close the Neo4j connection
        if pipeline:
            pipeline.close_connection()
            logger.info("🔌 Neo4j connection closed")


def validate_environment():
    """
    Validate that the required environment and dependencies are available.
    **Enhanced for PET support**
    """
    logger.info("🔍 Validating environment...")

    # Check required directories - Enhanced for PET
    required_dirs = [
        "inputs",
        "inputs/Tables",
        "inputs/Images",      # MRI original DICOMs
        "inputs/Updated",     # MRI converted images
        "inputs/PET",         # PET original DICOMs **NEW**
        "inputs/Updated_PET"  # PET converted images **NEW**
    ]
    missing_dirs = []

    for dir_path in required_dirs:
        if not Path(dir_path).exists():
            missing_dirs.append(dir_path)

    if missing_dirs:
        logger.warning(f"⚠️  Missing directories: {missing_dirs}")
        logger.info("📁 Please ensure your directory structure looks like:")
        logger.info("   inputs/")
        logger.info("   ├── Tables/        (CSV files)")
        logger.info("   ├── Images/        (Original MRI DICOM files)")
        logger.info("   ├── Updated/       (Converted MRI PNG/JPG files)")
        logger.info("   ├── PET/           (Original PET DICOM files) **NEW**")
        logger.info("   └── Updated_PET/   (Converted PET PNG/JPG files) **NEW**")

    # Check for required Python packages
    required_packages = {
        "pandas": "pandas",
        "pydicom": "pydicom",
        "PIL": "Pillow",
        "numpy": "numpy",
        "neo4j": "neo4j"
    }

    missing_packages = []
    for import_name, package_name in required_packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing_packages.append(package_name)

    if missing_packages:
        logger.warning(f"⚠️  Missing Python packages: {missing_packages}")
        logger.info("📦 Install missing packages with:")
        logger.info(f"   pip install {' '.join(missing_packages)}")
        return False

    # Check Neo4j APOC plugin
    logger.info("⚠️  Note: This pipeline works better with Neo4j APOC plugin installed")
    logger.info("   If you see APOC-related warnings, the pipeline will use fallback methods")

    logger.info("✅ Environment validation passed")
    return True


def print_usage_instructions():
    """
    Print helpful usage instructions for running the enhanced pipeline.
    **Enhanced for PET support**
    """
    print("\n" + "=" * 70)
    print("ENHANCED ADNI KNOWLEDGE GRAPH PIPELINE - WITH PET SUPPORT")
    print("=" * 70)
    print("\n📋 BEFORE RUNNING:")
    print("1. Update Neo4j credentials in the main() function")
    print("2. Ensure your data directory structure is correct:")
    print("   inputs/Tables/     - Contains CSV files from ADNI")
    print("   inputs/Images/     - Contains original MRI DICOM files")
    print("   inputs/Updated/    - Contains converted MRI image files")
    print("   inputs/PET/        - Contains original PET DICOM files **NEW**")
    print("   inputs/Updated_PET/ - Contains converted PET image files **NEW**")
    print("3. Start your Neo4j database server")
    print("4. (Optional) Install APOC plugin for better performance")
    print("\n🚀 TO RUN THE PIPELINE:")
    print("   python enhanced_adni_pet_pipeline.py")
    print("\n⚙️  TO CUSTOMIZE EXECUTION:")
    print("   Edit the boolean flags in main() to enable/disable steps")
    print("   - PROCESS_MRI: Enable/disable MRI image processing")
    print("   - PROCESS_PET: Enable/disable PET image processing **NEW**")
    print("\n🆕 NEW PET FEATURES:")
    print("   - PET tracer identification (FDG, AV45, AV1451, etc.)")
    print("   - PET-specific metadata extraction")
    print("   - Biological pathway integration")
    print("   - Multimodal MRI-PET session detection")
    print("   - Enhanced research cohorts with PET criteria")
    print("\n🆘 FOR HELP:")
    print("   Check the logs for detailed execution information")
    print("=" * 70)


if __name__ == "__main__":
    """
    Entry point for the Enhanced ADNI Knowledge Graph Pipeline with PET Support.
    """

    # Print usage instructions
    print_usage_instructions()

    # Validate environment before proceeding
    if not validate_environment():
        logger.error("❌ Environment validation failed. Please fix the issues above.")
        exit(1)

    # Ask user if they want to proceed
    proceed = input("\n🚀 Ready to run the enhanced pipeline with PET support? (yes/no): ")
    if proceed.lower() != 'yes':
        logger.info("👋 Pipeline execution cancelled by user")
        exit(0)

    # Execute the main pipeline
    main()