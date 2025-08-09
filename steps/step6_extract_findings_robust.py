"""
Step 6: FIXED Clinical Findings Extraction for ADNI Data
Now properly extracts diagnoses, biomarkers, and cognitive assessments
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import re
import uuid

from models.entities import (
    CognitiveAssessment, Biomarker, Diagnosis,
    VolumetricMeasure, PETBinding
)
from utils.neo4j_connector import Neo4jConnector
from utils.batch_processor import DataValidator

logger = logging.getLogger(__name__)


class ADNIFindingsExtractor:
    """Fixed ADNI findings extractor with proper table detection"""

    def __init__(self, connector: Neo4jConnector, table_data: Dict[str, pd.DataFrame]):
        self.connector = connector
        self.table_data = table_data

        # Collections for extracted entities
        self.cognitive_assessments = []
        self.biomarkers = []
        self.diagnoses = []
        self.volumetric_measures = []
        self.pet_bindings = []

        # Track what we've processed
        self.processed_patients = set()
        self.extraction_stats = {
            'tables_processed': 0,
            'rows_processed': 0,
            'errors': []
        }

        # Log available tables for debugging
        self._log_available_tables()

    def _map_diagnosis_code(self, diagnosis_value) -> Optional[str]:
        """Map ADNI diagnosis numeric codes to standard codes"""
        if pd.isna(diagnosis_value):
            return None

        # Convert to int/float for comparison
        try:
            dx_val = float(diagnosis_value)
        except (ValueError, TypeError):
            # If it's a string, try string mapping
            return self._map_adni_diagnosis(diagnosis_value)

        # ADNI DXSUM uses numeric codes:
        # 1 = Cognitively Normal (CN)
        # 2 = Mild Cognitive Impairment (MCI)
        # 3 = Alzheimer's Disease (AD)
        if dx_val == 1 or dx_val == 1.0:
            return 'CN'
        elif dx_val == 2 or dx_val == 2.0:
            return 'MCI'
        elif dx_val == 3 or dx_val == 3.0:
            return 'AD'
        else:
            return None

    def _check_abnormal(self, analyte: str, value: float, threshold: Optional[float]) -> bool:
        """Check if a biomarker value is abnormal based on threshold"""
        if threshold is None:
            return False

        # For Amyloid-beta markers, LOW values are abnormal
        if 'Aβ' in analyte or 'ABETA' in analyte.upper():
            return value < threshold

        # For Tau markers, HIGH values are abnormal
        elif 'Tau' in analyte or 'TAU' in analyte.upper():
            return value > threshold

        # For APOE risk score, HIGH values indicate risk
        elif analyte == 'APOE Genotype':
            return value > threshold

        # Default: higher than threshold is abnormal
        else:
            return value > threshold if threshold else False

    def _log_available_tables(self):
        """Log all available tables for debugging"""
        logger.info("\n" + "="*60)
        logger.info("AVAILABLE TABLES IN TABLE_DATA:")
        logger.info("="*60)

        # Group tables by category
        diagnosis_tables = []
        cognitive_tables = []
        biomarker_tables = []
        imaging_tables = []
        other_tables = []

        for table_name in sorted(self.table_data.keys()):
            table_upper = table_name.upper()
            row_count = len(self.table_data[table_name])

            if 'DXSUM' in table_upper or 'DIAGNOSIS' in table_upper:
                diagnosis_tables.append(f"  - {table_name}: {row_count} rows")
            elif any(test in table_upper for test in ['MMSE', 'CDR', 'ADAS', 'MOCA', 'FAQ', 'NEUROBAT']):
                cognitive_tables.append(f"  - {table_name}: {row_count} rows")
            elif any(marker in table_upper for marker in ['BIOMK', 'BIOMARK', 'CSF', 'ELECSYS', 'LABDATA', 'APOERES']):
                biomarker_tables.append(f"  - {table_name}: {row_count} rows")
            elif any(img in table_upper for img in ['UCSFFSX', 'UCBERKELEY', 'FOXLABBSI']):
                imaging_tables.append(f"  - {table_name}: {row_count} rows")
            else:
                other_tables.append(f"  - {table_name}: {row_count} rows")

        if diagnosis_tables:
            logger.info("Diagnosis Tables:")
            for t in diagnosis_tables:
                logger.info(t)

        if cognitive_tables:
            logger.info("\nCognitive Tables:")
            for t in cognitive_tables:
                logger.info(t)

        if biomarker_tables:
            logger.info("\nBiomarker Tables:")
            for t in biomarker_tables:
                logger.info(t)

        if imaging_tables:
            logger.info("\nImaging Tables:")
            for t in imaging_tables:
                logger.info(t)

        logger.info(f"\nTotal tables available: {len(self.table_data)}")
        logger.info("="*60 + "\n")

    def execute(self) -> Dict[str, Any]:
        """Execute comprehensive extraction with fixed table detection"""
        results = {
            'cognitive_assessments': 0,
            'biomarkers': 0,
            'diagnoses': 0,
            'volumetric_measures': 0,
            'pet_bindings': 0,
            'errors': []
        }

        logger.info("\n" + "=" * 60)
        logger.info("ADNI CLINICAL FINDINGS EXTRACTION (FIXED)")
        logger.info("=" * 60)

        # 1. Extract Diagnoses
        logger.info("\n1. Extracting Diagnoses...")
        dx_count = self._extract_diagnoses_fixed()
        results['diagnoses'] = dx_count
        logger.info(f"   ✅ Extracted {dx_count} diagnoses")

        # 2. Extract Cognitive Assessments
        logger.info("\n2. Extracting Cognitive Assessments...")
        cog_count = self._extract_cognitive_assessments_fixed()
        results['cognitive_assessments'] = cog_count
        logger.info(f"   ✅ Extracted {cog_count} cognitive assessments")

        # 3. Extract Biomarkers
        logger.info("\n3. Extracting Biomarkers...")
        bio_count = self._extract_biomarkers_fixed()
        results['biomarkers'] = bio_count
        logger.info(f"   ✅ Extracted {bio_count} biomarkers")

        # 4. Extract Imaging Measures
        logger.info("\n4. Extracting Imaging Measures...")
        vol_count, pet_count = self._extract_imaging_measures_fixed()
        results['volumetric_measures'] = vol_count
        results['pet_bindings'] = pet_count
        logger.info(f"   ✅ Extracted {vol_count} volumetric and {pet_count} PET measures")

        # Log summary
        self._log_extraction_summary(results)

        # Debug extraction
        self._debug_extraction()

        return results

    def _debug_extraction(self):
        """Debug what's being extracted"""
        logger.info("\n" + "=" * 60)
        logger.info("DEBUG: Extraction Status")
        logger.info("=" * 60)
        logger.info(f"Diagnoses extracted: {len(self.diagnoses)}")
        if self.diagnoses:
            sample = self.diagnoses[:5]
            for d in sample:
                logger.info(f"  Sample: {d.patient_id} - {d.diagnosis_code} - {d.visit_id}")

        logger.info(f"\nBiomarkers extracted: {len(self.biomarkers)}")
        if self.biomarkers:
            sample = self.biomarkers[:5]
            for b in sample:
                logger.info(f"  Sample: {b.patient_id} - {b.analyte}: {b.value} {b.unit}")

        logger.info(f"\nCognitive assessments: {len(self.cognitive_assessments)}")
        if self.cognitive_assessments:
            sample = self.cognitive_assessments[:5]
            for c in sample:
                logger.info(f"  Sample: {c.patient_id} - {c.test_name}: {c.total_score}")
        logger.info("=" * 60)

    def _preprocess_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Preprocess DataFrame to handle nullable dtypes safely"""
        # Create a copy to avoid modifying original
        df_copy = df.copy()

        # Convert problematic nullable integer columns to regular float
        for col in df_copy.columns:
            if df_copy[col].dtype.name in ['Int64', 'Int32', 'Int16', 'Int8']:
                # Convert nullable integers to regular floats (NaN compatible)
                df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce')

        return df_copy

    def _safe_equals(self, value, target) -> bool:
        """Safely compare values that might be pd.NA"""
        if pd.isna(value):
            return False
        try:
            return value == target
        except:
            return False

    def _safe_get_numeric(self, value) -> Optional[float]:
        """Safely convert to numeric, handling pd.NA"""
        if pd.isna(value):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _find_table(self, patterns: List[str]) -> Optional[Tuple[str, pd.DataFrame]]:
        """Find a table by matching patterns (case-insensitive)"""
        for table_name, df in self.table_data.items():
            table_upper = table_name.upper()
            for pattern in patterns:
                if pattern.upper() in table_upper:
                    logger.debug(f"Found table '{table_name}' matching pattern '{pattern}'")
                    # Preprocess the dataframe to handle nullable dtypes
                    df_processed = self._preprocess_dataframe(df)
                    return table_name, df_processed
        return None, None


    def _extract_diagnoses_from_dxsum(self) -> int:
        """Extract diagnoses specifically from DXSUM table"""
        count = 0

        # Look for DXSUM table
        if 'DXSUM' in self.table_data:
            df = self.table_data['DXSUM']
            logger.info(f"Processing DXSUM table with {len(df)} rows")

            for _, row in df.iterrows():
                ptid = str(row.get('PTID', '')).strip()
                viscode = str(row.get('VISCODE2', row.get('VISCODE', 'bl'))).strip()

                # Get overall diagnosis
                diagnosis_value = row.get('DIAGNOSIS')

                # Map diagnosis codes
                if pd.notna(diagnosis_value):
                    dx_code = self._map_diagnosis_code(diagnosis_value)
                else:
                    # Check individual flags
                    if row.get('DXAD') == 1:
                        dx_code = 'AD'
                    elif row.get('DXMCI') == 1:
                        dx_code = 'MCI'
                    elif row.get('DXNORM') == 1:
                        dx_code = 'CN'
                    else:
                        continue

                # Create diagnosis entity
                diagnosis = Diagnosis(
                    diagnosis_id=f"dx_{ptid}_{viscode}_{dx_code}",
                    patient_id=ptid,
                    visit_id=f"{ptid}_{viscode}",
                    diagnosis_code=dx_code,
                    confidence=row.get('DXCONFID', 0.95) / 100.0 if row.get('DXCONFID') else 0.95
                )

                self.diagnoses.append(diagnosis)
                count += 1

        return count

    def _extract_biomarkers_from_elecsys(self) -> int:
        """Extract biomarkers from UPENNBIOMK_ROCHE_ELECSYS table"""
        count = 0

        if 'UPENNBIOMK_ROCHE_ELECSYS' in self.table_data:
            df = self.table_data['UPENNBIOMK_ROCHE_ELECSYS']
            logger.info(f"Processing UPENNBIOMK_ROCHE_ELECSYS with {len(df)} rows")

            for _, row in df.iterrows():
                ptid = str(row.get('PTID', '')).strip()
                viscode = str(row.get('VISCODE2', 'bl')).strip()
                visit_id = f"{ptid}_{viscode}"

                # Extract each biomarker
                biomarkers = [
                    ('ABETA40', 'Aβ40', None),
                    ('ABETA42', 'Aβ42', 600),  # threshold
                    ('TAU', 'Total Tau', 400),
                    ('PTAU', 'p-Tau181', 80)
                ]

                for col, analyte, threshold in biomarkers:
                    if col in row and pd.notna(row[col]):
                        value = float(row[col])

                        biomarker = Biomarker(
                            biomarker_id=f"bio_{ptid}_{viscode}_{col}",
                            patient_id=ptid,
                            visit_id=visit_id,
                            biomarker_type='CSF',
                            analyte=analyte,
                            value=value,
                            unit='pg/mL',
                            abnormal_flag=self._check_abnormal(analyte, value, threshold)
                        )

                        self.biomarkers.append(biomarker)
                        count += 1

        return count

    def _extract_diagnoses_fixed(self) -> int:
        """Extract diagnoses from DXSUM table - main method"""
        count = 0

        # Look for DXSUM table specifically
        if 'DXSUM' not in self.table_data:
            logger.warning("   ⚠️ DXSUM table not found!")
            return 0

        df = self._preprocess_dataframe(self.table_data['DXSUM'])
        logger.info(f"   Processing DXSUM table with {len(df)} rows...")
        logger.info(f"   Columns found: {list(df.columns)[:15]}...")

        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            if not ptid:
                continue

            viscode = str(row.get('VISCODE2', row.get('VISCODE', 'bl'))).strip()
            visit_id = f"{ptid}_{viscode}"

            # Extract diagnosis
            dx_code = None

            # Method 1: Check DIAGNOSIS column (numeric code)
            if 'DIAGNOSIS' in row and pd.notna(row['DIAGNOSIS']):
                dx_code = self._map_diagnosis_code(row['DIAGNOSIS'])

            # Method 2: Check individual diagnosis flags
            if not dx_code:
                if self._safe_equals(row.get('DXAD'), 1):
                    dx_code = 'AD'
                elif self._safe_equals(row.get('DXMCI'), 1):
                    dx_code = 'MCI'
                    # Check MCI subtype
                    if 'DXMDES' in row and pd.notna(row['DXMDES']):
                        mci_des = int(row['DXMDES'])
                        if mci_des == 1:
                            dx_code = 'EMCI'
                        elif mci_des == 2:
                            dx_code = 'LMCI'
                elif self._safe_equals(row.get('DXNORM'), 1):
                    dx_code = 'CN'

            if dx_code:
                diagnosis_id = f"dx_{ptid}_{viscode}_{dx_code}"

                # Extract confidence
                confidence = 0.95
                if 'DXCONFID' in row and pd.notna(row['DXCONFID']):
                    conf_val = float(row['DXCONFID'])
                    if conf_val == 1:
                        confidence = 0.95
                    elif conf_val == 2:
                        confidence = 0.75
                    elif conf_val == 3:
                        confidence = 0.50

                diagnosis = Diagnosis(
                    diagnosis_id=diagnosis_id,
                    patient_id=ptid,
                    visit_id=visit_id,
                    diagnosis_code=dx_code,
                    diagnosis_text=self._get_diagnosis_text(dx_code),
                    confidence=confidence,
                    criteria_used="ADNI Clinical Criteria",
                    source_table='DXSUM'
                )

                self.diagnoses.append(diagnosis)
                count += 1

        return count

    def _extract_biomarkers_fixed(self) -> int:
        """Extract biomarkers from UPENNBIOMK_ROCHE_ELECSYS table - main method"""
        count = 0

        # Look for the specific Elecsys table
        if 'UPENNBIOMK_ROCHE_ELECSYS' not in self.table_data:
            logger.warning("   ⚠️ UPENNBIOMK_ROCHE_ELECSYS table not found!")
            # Try alternative table name
            if 'UPENNBIOMK' in self.table_data:
                df = self._preprocess_dataframe(self.table_data['UPENNBIOMK'])
                table_name = 'UPENNBIOMK'
            else:
                return 0
        else:
            df = self._preprocess_dataframe(self.table_data['UPENNBIOMK_ROCHE_ELECSYS'])
            table_name = 'UPENNBIOMK_ROCHE_ELECSYS'

        logger.info(f"   Processing {table_name} with {len(df)} rows...")
        logger.info(f"   Columns: {list(df.columns)}")

        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            if not ptid:
                continue

            viscode = str(row.get('VISCODE2', 'bl')).strip()
            visit_id = f"{ptid}_{viscode}"

            # Extract each biomarker
            biomarkers_map = {
                'ABETA42': ('Aβ42', 'pg/mL', 600),
                'ABETA40': ('Aβ40', 'pg/mL', None),
                'TAU': ('Total Tau', 'pg/mL', 400),
                'PTAU': ('p-Tau181', 'pg/mL', 80)
            }

            for col, (analyte, unit, threshold) in biomarkers_map.items():
                if col in row and pd.notna(row[col]):
                    value = float(row[col])
                    biomarker_id = f"bio_{ptid}_{viscode}_{col}"

                    biomarker = Biomarker(
                        biomarker_id=biomarker_id,
                        patient_id=ptid,
                        visit_id=visit_id,
                        biomarker_type='CSF',
                        analyte=analyte,
                        value=value,
                        unit=unit,
                        specimen_type='CSF',
                        abnormal_flag=self._check_abnormal(analyte, value, threshold),
                        source_table=table_name
                    )

                    self.biomarkers.append(biomarker)
                    count += 1

        # Also process APOE genotype
        if 'APOERES' in self.table_data:
            apoe_count = self._extract_apoe_genotypes()
            count += apoe_count

        return count

    def _extract_apoe_genotypes(self) -> int:
        """Extract APOE genotype data"""
        count = 0
        df = self._preprocess_dataframe(self.table_data['APOERES'])

        logger.info(f"   Processing APOERES (APOE genotype) with {len(df)} rows...")

        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            if not ptid:
                continue

            if 'GENOTYPE' in row and pd.notna(row['GENOTYPE']):
                genotype = str(row['GENOTYPE'])
                viscode = str(row.get('VISCODE', 'bl')).strip()
                visit_id = f"{ptid}_{viscode}"
                biomarker_id = f"bio_{ptid}_APOE_{viscode}"

                # Calculate risk score
                risk_score = self._apoe_risk_score(genotype)

                biomarker = Biomarker(
                    biomarker_id=biomarker_id,
                    patient_id=ptid,
                    visit_id=visit_id,
                    biomarker_type='Genetic',
                    analyte='APOE Genotype',
                    value=risk_score,
                    unit='risk_score',
                    specimen_type='Blood',
                    abnormal_flag=risk_score > 2,
                    source_table='APOERES',
                    assay_info={'genotype': genotype}
                )

                self.biomarkers.append(biomarker)
                count += 1

        return count

    def _extract_cognitive_assessments_fixed(self) -> int:
        """Extract cognitive assessments with fixed table detection"""
        count = 0

        # Process each cognitive test type
        cognitive_tests = [
            ('MMSE', 'MMSCORE', 'MMSE'),
            ('CDR', 'CDGLOBAL', 'CDR'),
            ('ADAS', 'TOTSCORE', 'ADAS-Cog'),
            ('MOCA', 'MOCA', 'MoCA'),
            ('FAQ', 'FAQTOTAL', 'FAQ'),
            ('NEUROBAT', 'LIMMTOTAL', 'Logical Memory')
        ]

        for table_pattern, score_col, test_name in cognitive_tests:
            table_name, df = self._find_table([table_pattern])

            if df is not None:
                logger.info(f"   Processing {table_name} ({test_name})...")

                for _, row in df.iterrows():
                    ptid = str(row.get('PTID', row.get('RID', ''))).strip()
                    if not ptid:
                        continue

                    # Get score
                    score = row.get(score_col)
                    if pd.isna(score):
                        # Try alternative score columns
                        if table_pattern == 'ADAS' and 'TOTAL13' in row:
                            score = row.get('TOTAL13')
                        elif table_pattern == 'CDR' and 'CDRSB' in row:
                            score = row.get('CDRSB')

                    if pd.notna(score):
                        viscode = str(row.get('VISCODE', row.get('VISCODE2', 'bl'))).strip()
                        visit_id = f"{ptid}_{viscode}"
                        assessment_id = f"cog_{ptid}_{viscode}_{test_name.replace(' ', '_')}"

                        # Extract subscores for CDR
                        subscores = {}
                        if table_pattern == 'CDR':
                            for sub in ['CDMEMORY', 'CDORIENT', 'CDJUDGE', 'CDCOMMUN', 'CDHOME', 'CDCARE']:
                                if sub in row and pd.notna(row[sub]):
                                    subscores[sub.lower()] = float(row[sub])

                        assessment = CognitiveAssessment(
                            assessment_id=assessment_id,
                            patient_id=ptid,
                            visit_id=visit_id,
                            test_name=test_name,
                            test_version='1.0',
                            total_score=float(score),
                            subscores=subscores,
                            clinical_significance=self._interpret_score(test_name, float(score)),
                            source_table=table_name
                        )

                        self.cognitive_assessments.append(assessment)
                        count += 1

        return count

    def _extract_biomarkers_fixed(self) -> int:
        """Extract biomarkers with fixed table detection"""
        count = 0

        # Process UPENNBIOMK table
        biomarker_patterns = ['UPENNBIOMK', 'ELECSYS', 'BIOMARK', 'CSF']
        table_name, df = self._find_table(biomarker_patterns)

        if df is not None:
            logger.info(f"   Processing {table_name} biomarkers...")

            for _, row in df.iterrows():
                ptid = str(row.get('PTID', row.get('RID', ''))).strip()
                if not ptid:
                    continue

                viscode = str(row.get('VISCODE2', row.get('VISCODE', 'bl'))).strip()
                visit_id = f"{ptid}_{viscode}"

                # Extract each biomarker type
                biomarkers_map = {
                    'ABETA42': ('Aβ42', 'pg/mL', 600),  # threshold
                    'ABETA40': ('Aβ40', 'pg/mL', None),
                    'TAU': ('Total Tau', 'pg/mL', 400),
                    'PTAU': ('p-Tau181', 'pg/mL', 80)
                }

                for col, (analyte, unit, threshold) in biomarkers_map.items():
                    if col in row and pd.notna(row[col]):
                        value = float(row[col])
                        biomarker_id = f"bio_{ptid}_{viscode}_{col}"

                        # Check if abnormal based on threshold
                        abnormal = False
                        if threshold:
                            if 'ABETA' in col:
                                abnormal = value < threshold
                            else:
                                abnormal = value > threshold

                        biomarker = Biomarker(
                            biomarker_id=biomarker_id,
                            patient_id=ptid,
                            visit_id=visit_id,
                            biomarker_type='CSF',
                            analyte=analyte,
                            value=value,
                            unit=unit,
                            specimen_type='CSF',
                            abnormal_flag=abnormal,
                            source_table=table_name
                        )

                        self.biomarkers.append(biomarker)
                        count += 1

        # Process APOERES (genetic biomarker)
        apoe_patterns = ['APOERES', 'APOE', 'GENETIC']
        table_name, df = self._find_table(apoe_patterns)

        if df is not None:
            logger.info(f"   Processing {table_name} (APOE genotype)...")

            for _, row in df.iterrows():
                ptid = str(row.get('PTID', row.get('RID', ''))).strip()
                if not ptid:
                    continue

                genotype = row.get('GENOTYPE')
                if pd.notna(genotype):
                    viscode = str(row.get('VISCODE', 'bl')).strip()
                    visit_id = f"{ptid}_{viscode}"
                    biomarker_id = f"bio_{ptid}_APOE"

                    # Calculate risk score
                    risk_score = self._apoe_risk_score(genotype)

                    biomarker = Biomarker(
                        biomarker_id=biomarker_id,
                        patient_id=ptid,
                        visit_id=visit_id,
                        biomarker_type='Genetic',
                        analyte='APOE Genotype',
                        value=risk_score,
                        unit='risk_score',
                        specimen_type='Blood',
                        abnormal_flag=risk_score > 2,
                        source_table=table_name,
                        assay_info={'genotype': str(genotype)}
                    )

                    self.biomarkers.append(biomarker)
                    count += 1

        return count

    def _extract_imaging_measures_fixed(self) -> Tuple[int, int]:
        """Extract volumetric and PET measures with fixed table detection"""
        vol_count = 0
        pet_count = 0

        # Process FreeSurfer volumes
        fs_patterns = ['UCSFFSX', 'FREESURFER', 'FOXLABBSI']
        table_name, df = self._find_table(fs_patterns)

        if df is not None:
            logger.info(f"   Processing {table_name} volumes...")

            for _, row in df.iterrows():
                ptid = str(row.get('PTID', row.get('RID', ''))).strip()
                if not ptid:
                    continue

                viscode = str(row.get('VISCODE', row.get('VISCODE2', 'bl'))).strip()
                visit_id = f"{ptid}_{viscode}"

                # Extract key volumes
                volume_cols = {
                    'ST29SV': ('Hippocampus_L', 'mm³'),
                    'ST88SV': ('Hippocampus_R', 'mm³'),
                    'ST11SV': ('Ventricles', 'mm³'),
                    'HIPPOVOL_L': ('Hippocampus_L', 'mm³'),
                    'HIPPOVOL_R': ('Hippocampus_R', 'mm³'),
                    'VENTVOL': ('Ventricles', 'mm³')
                }

                for col, (region, unit) in volume_cols.items():
                    if col in row and pd.notna(row[col]):
                        value = float(row[col])
                        measure_id = f"vol_{ptid}_{viscode}_{region}"

                        measure = VolumetricMeasure(
                            measure_id=measure_id,
                            image_id=f"img_{ptid}_{viscode}",
                            patient_id=ptid,
                            visit_id=visit_id,
                            region=region,
                            volume=value,
                            unit=unit,
                            processing_method='FreeSurfer',
                            hemisphere='left' if '_L' in region else ('right' if '_R' in region else 'bilateral')
                        )

                        self.volumetric_measures.append(measure)
                        vol_count += 1

        # Process PET data
        pet_patterns = ['UCBERKELEY_AMY', 'UCBERKELEY_TAU', 'AV45META']

        for pattern in pet_patterns:
            table_name, df = self._find_table([pattern])

            if df is not None:
                logger.info(f"   Processing {table_name} PET data...")

                # Determine tracer type
                tracer = 'Unknown'
                if 'AMY' in pattern or 'AV45' in pattern:
                    tracer = 'Amyloid'
                elif 'TAU' in pattern:
                    tracer = 'Tau'

                for _, row in df.iterrows():
                    ptid = str(row.get('PTID', row.get('RID', ''))).strip()
                    if not ptid:
                        continue

                    viscode = str(row.get('VISCODE2', row.get('VISCODE', 'bl'))).strip()
                    visit_id = f"{ptid}_{viscode}"

                    # Extract SUVR values
                    suvr_col = 'SUMMARY_SUVR' if 'SUMMARY_SUVR' in row else 'META_TEMPORAL_SUVR'

                    if suvr_col in row and pd.notna(row[suvr_col]):
                        suvr = float(row[suvr_col])
                        binding_id = f"pet_{ptid}_{viscode}_{tracer}_summary"

                        binding = PETBinding(
                            binding_id=binding_id,
                            image_id=f"img_{ptid}_{viscode}_PET",
                            patient_id=ptid,
                            visit_id=visit_id,
                            tracer=tracer,
                            region='Global',
                            suvr=suvr,
                            reference_region='Cerebellum',
                            abnormal_flag=suvr > 1.11 if tracer == 'Amyloid' else suvr > 1.3
                        )

                        self.pet_bindings.append(binding)
                        pet_count += 1

        return vol_count, pet_count

    # Helper methods remain the same
    def _map_adni_diagnosis(self, dx_value) -> Optional[str]:
        """Map ADNI diagnosis values to standard codes"""
        if pd.isna(dx_value):
            return None

        dx_str = str(dx_value).strip().upper()

        diagnosis_map = {
            '1': 'CN', '1.0': 'CN', 'CN': 'CN', 'NL': 'CN', 'NORMAL': 'CN',
            'CTL': 'CN', 'CONTROL': 'CN', 'HC': 'CN',
            '2': 'MCI', '2.0': 'MCI', 'MCI': 'MCI',
            'EMCI': 'EMCI', 'LMCI': 'LMCI',
            '3': 'AD', '3.0': 'AD', 'AD': 'AD', 'DEMENTIA': 'AD',
            'DEM': 'AD', 'ALZHEIMER': 'AD',
            'SMC': 'SMC', 'SCD': 'SMC'
        }

        return diagnosis_map.get(dx_str)

    def _get_diagnosis_text(self, code: str) -> str:
        """Get full diagnosis text"""
        texts = {
            'CN': 'Cognitively Normal',
            'SMC': 'Subjective Memory Concern',
            'EMCI': 'Early Mild Cognitive Impairment',
            'LMCI': 'Late Mild Cognitive Impairment',
            'MCI': 'Mild Cognitive Impairment',
            'AD': "Alzheimer's Disease"
        }
        return texts.get(code, code)

    def _interpret_score(self, test_name: str, score: float) -> str:
        """Interpret cognitive test score"""
        if test_name == 'MMSE':
            if score >= 27:
                return 'normal'
            elif score >= 21:
                return 'mild_impairment'
            elif score >= 10:
                return 'moderate_impairment'
            else:
                return 'severe_impairment'
        elif test_name == 'ADAS-Cog':
            if score <= 10:
                return 'normal'
            elif score <= 20:
                return 'mild_impairment'
            elif score <= 40:
                return 'moderate_impairment'
            else:
                return 'severe_impairment'
        elif test_name == 'CDR':
            if score == 0:
                return 'normal'
            elif score <= 0.5:
                return 'questionable'
            elif score <= 1:
                return 'mild'
            elif score <= 2:
                return 'moderate'
            else:
                return 'severe'
        elif test_name == 'MoCA':
            if score >= 26:
                return 'normal'
            elif score >= 18:
                return 'mild_impairment'
            else:
                return 'moderate_severe_impairment'
        elif test_name == 'FAQ':
            if score <= 3:
                return 'normal'
            elif score <= 9:
                return 'mild_impairment'
            else:
                return 'significant_impairment'
        else:
            return 'unknown'

    def _apoe_risk_score(self, genotype) -> float:
        """Calculate APOE risk score"""
        if pd.isna(genotype):
            return 0

        try:
            genotype_str = str(genotype)
        except:
            return 0

        if '4/4' in genotype_str or 'E4/E4' in genotype_str:
            return 10  # Highest risk
        elif '3/4' in genotype_str or 'E3/E4' in genotype_str:
            return 5   # High risk
        elif '2/4' in genotype_str or 'E2/E4' in genotype_str:
            return 3   # Moderate risk
        elif '3/3' in genotype_str or 'E3/E3' in genotype_str:
            return 1   # Normal risk
        elif '2' in genotype_str:
            return 0.5  # Protective
        else:
            return 1

    def _log_extraction_summary(self, results: Dict[str, Any]):
        """Log detailed extraction summary"""
        logger.info("\n" + "="*60)
        logger.info("EXTRACTION SUMMARY")
        logger.info("="*60)

        # Count unique patients
        unique_patients = set()
        for d in self.diagnoses:
            unique_patients.add(d.patient_id)
        for c in self.cognitive_assessments:
            unique_patients.add(c.patient_id)
        for b in self.biomarkers:
            unique_patients.add(b.patient_id)

        logger.info(f"Unique patients with findings: {len(unique_patients)}")

        # Diagnosis breakdown
        if self.diagnoses:
            dx_counts = {}
            for d in self.diagnoses:
                dx_counts[d.diagnosis_code] = dx_counts.get(d.diagnosis_code, 0) + 1

            logger.info("\nDiagnosis breakdown:")
            for dx_code, count in sorted(dx_counts.items()):
                logger.info(f"  {dx_code}: {count}")

        # Test breakdown
        if self.cognitive_assessments:
            test_counts = {}
            for c in self.cognitive_assessments:
                test_counts[c.test_name] = test_counts.get(c.test_name, 0) + 1

            logger.info("\nCognitive test breakdown:")
            for test, count in sorted(test_counts.items()):
                logger.info(f"  {test}: {count}")

        # Biomarker breakdown
        if self.biomarkers:
            bio_counts = {}
            for b in self.biomarkers:
                bio_counts[b.analyte] = bio_counts.get(b.analyte, 0) + 1

            logger.info("\nBiomarker breakdown:")
            for analyte, count in sorted(bio_counts.items()):
                logger.info(f"  {analyte}: {count}")


def execute_findings_extraction_fixed(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                                     table_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """Execute fixed findings extraction"""
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        extractor = ADNIFindingsExtractor(connector, table_data)
        results = extractor.execute()

        # Store extractor for batch insertion
        results['extractor'] = extractor

        logger.info(f"\n✅ Findings extraction completed")
        logger.info(f"   Diagnoses: {results['diagnoses']}")
        logger.info(f"   Cognitive Assessments: {results['cognitive_assessments']}")
        logger.info(f"   Biomarkers: {results['biomarkers']}")
        logger.info(f"   Volumetric Measures: {results['volumetric_measures']}")
        logger.info(f"   PET Bindings: {results['pet_bindings']}")

        return results

    except Exception as e:
        logger.error(f"Findings extraction failed: {e}")
        raise
    finally:
        connector.close()