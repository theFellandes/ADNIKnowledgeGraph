"""
Step 6: FIXED Clinical Findings Extraction for ADNI Data
Handles Novel Imaging Cohort Study table naming convention
Extracts from DXSUM, ARM, BLCHANGE, and cognitive assessments
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
    """Fixed ADNI findings extractor with proper table name matching"""

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

        # Normalize table names for easier matching
        self.normalized_tables = self._normalize_table_names()

        # Log available tables for debugging
        self._log_available_tables()

    def _normalize_table_names(self) -> Dict[str, str]:
        """Create a mapping of simplified names to actual table names"""
        normalized = {}
        for table_name in self.table_data.keys():
            # Remove prefix and suffix to get core table name
            core_name = table_name
            if 'Novel_Imaging_Cohort_Study_' in core_name:
                core_name = core_name.replace('Novel_Imaging_Cohort_Study_', '')
            if '_05Aug2025' in core_name:
                core_name = core_name.replace('_05Aug2025', '')
            normalized[core_name] = table_name
        return normalized

    def _get_table(self, table_pattern: str) -> Optional[pd.DataFrame]:
        """Get table by pattern, handling the naming convention"""
        # Direct match in normalized names
        if table_pattern in self.normalized_tables:
            actual_name = self.normalized_tables[table_pattern]
            return self._preprocess_dataframe(self.table_data[actual_name])

        # Pattern matching
        for norm_name, actual_name in self.normalized_tables.items():
            if table_pattern.upper() in norm_name.upper():
                return self._preprocess_dataframe(self.table_data[actual_name])

        return None

    def _find_table(self, patterns: List[str]) -> Optional[Tuple[str, pd.DataFrame]]:
        """Find a table by matching patterns (case-insensitive)"""
        for pattern in patterns:
            if pattern in self.normalized_tables:
                actual_name = self.normalized_tables[pattern]
                return actual_name, self._preprocess_dataframe(self.table_data[actual_name])

            # Pattern matching
            for norm_name, actual_name in self.normalized_tables.items():
                if pattern.upper() in norm_name.upper():
                    return actual_name, self._preprocess_dataframe(self.table_data[actual_name])

        return None, None

    def _preprocess_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Preprocess DataFrame to handle nullable dtypes safely"""
        df_copy = df.copy()

        # Convert problematic nullable integer columns to regular float
        for col in df_copy.columns:
            if df_copy[col].dtype.name in ['Int64', 'Int32', 'Int16', 'Int8']:
                df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce')

        return df_copy

    def _log_available_tables(self):
        """Log diagnosis-related tables found"""
        logger.info("\n" + "="*60)
        logger.info("DIAGNOSIS TABLES AVAILABLE:")

        diagnosis_tables = ['DXSUM', 'ARM', 'BLCHANGE', 'ADSXLIST']
        for table in diagnosis_tables:
            df = self._get_table(table)
            if df is not None:
                actual_name = self.normalized_tables.get(table, table)
                logger.info(f"  ✅ {table} -> {actual_name}: {len(df)} rows")

                # Log diagnosis-related columns
                dx_cols = [col for col in df.columns if any(
                    dx in col.upper() for dx in ['DX', 'DIAGNOSIS', 'ARM', 'PREDX']
                )]
                if dx_cols:
                    logger.info(f"     Diagnosis columns: {dx_cols[:5]}")
            else:
                logger.info(f"  ❌ {table}: NOT FOUND")
        logger.info("="*60 + "\n")

    def execute(self) -> Dict[str, Any]:
        """Execute comprehensive extraction"""
        results = {
            'diagnoses': 0,
            'cognitive_assessments': 0,
            'biomarkers': 0,
            'volumetric_measures': 0,
            'pet_bindings': 0,
            'errors': []
        }

        logger.info("\n" + "=" * 60)
        logger.info("ADNI CLINICAL FINDINGS EXTRACTION (COMPREHENSIVE)")
        logger.info("=" * 60)

        # 1. Extract Diagnoses from multiple sources
        logger.info("\n1. Extracting Diagnoses from all sources...")
        dx_count = self._extract_diagnoses_comprehensive()
        results['diagnoses'] = dx_count
        logger.info(f"   ✅ Total diagnoses extracted: {dx_count}")

        # 2. Extract Cognitive Assessments
        logger.info("\n2. Extracting Cognitive Assessments...")
        cog_count = self._extract_cognitive_assessments()
        results['cognitive_assessments'] = cog_count
        logger.info(f"   ✅ Extracted {cog_count} cognitive assessments")

        # 3. Extract Biomarkers
        logger.info("\n3. Extracting Biomarkers...")
        bio_count = self._extract_biomarkers()
        results['biomarkers'] = bio_count
        logger.info(f"   ✅ Extracted {bio_count} biomarkers")

        # 4. Extract Imaging Measures
        logger.info("\n4. Extracting Imaging Measures...")
        vol_count, pet_count = self._extract_imaging_measures()
        results['volumetric_measures'] = vol_count
        results['pet_bindings'] = pet_count
        logger.info(f"   ✅ Extracted {vol_count} volumetric and {pet_count} PET measures")

        # Log summary
        self._log_extraction_summary(results)

        return results

    def _extract_diagnoses_comprehensive(self) -> int:
        """Extract diagnoses from all available sources"""
        total_count = 0
        diagnosed_patients = set()

        # 1. Extract from DXSUM (primary source)
        dxsum_df = self._get_table('DXSUM')
        if dxsum_df is not None:
            count = self._extract_from_dxsum(dxsum_df)
            total_count += count
            logger.info(f"   - DXSUM: {count} diagnoses")

        # 2. Extract from ARM (screening diagnoses)
        arm_df = self._get_table('ARM')
        if arm_df is not None:
            count = self._extract_from_arm(arm_df)
            total_count += count
            logger.info(f"   - ARM: {count} diagnoses")

        # 3. Extract from BLCHANGE (baseline changes)
        blchange_df = self._get_table('BLCHANGE')
        if blchange_df is not None:
            count = self._extract_from_blchange(blchange_df)
            total_count += count
            logger.info(f"   - BLCHANGE: {count} diagnoses")

        # 4. Extract from CDR scores (derived diagnoses)
        cdr_df = self._get_table('CDR')
        if cdr_df is not None:
            count = self._extract_from_cdr(cdr_df)
            total_count += count
            logger.info(f"   - CDR (derived): {count} diagnoses")

        # 5. Extract from MMSE scores (derived diagnoses)
        mmse_df = self._get_table('MMSE')
        if mmse_df is not None:
            count = self._extract_from_mmse(mmse_df)
            total_count += count
            logger.info(f"   - MMSE (derived): {count} diagnoses")

        return total_count

    def _extract_from_dxsum(self, df: pd.DataFrame) -> int:
        """Extract diagnoses from DXSUM table"""
        count = 0

        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            if not ptid:
                continue

            viscode = str(row.get('VISCODE2', row.get('VISCODE', 'bl'))).strip()
            visit_id = f"{ptid}_{viscode}"

            # Get diagnosis from multiple columns
            dx_code = None
            confidence = 0.95

            # Primary diagnosis column
            if 'DIAGNOSIS' in row and pd.notna(row['DIAGNOSIS']):
                dx_val = row['DIAGNOSIS']
                dx_code = self._map_diagnosis_code(dx_val)

            # Check individual diagnosis flags if primary not found
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
                # Extract confidence if available
                if 'DXCONFID' in row and pd.notna(row['DXCONFID']):
                    conf_val = row['DXCONFID']
                    if conf_val == 1:
                        confidence = 0.95
                    elif conf_val == 2:
                        confidence = 0.75
                    elif conf_val == 3:
                        confidence = 0.50

                diagnosis_id = f"dx_{ptid}_{viscode}_{dx_code}"

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

    def _extract_from_arm(self, df: pd.DataFrame) -> int:
        """Extract screening diagnoses from ARM table"""
        count = 0

        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            if not ptid:
                continue

            arm_value = row.get('ARM')
            if pd.notna(arm_value):
                # Map ARM values to diagnosis codes
                dx_code = self._map_arm_to_diagnosis(str(arm_value))

                if dx_code:
                    diagnosis_id = f"dx_{ptid}_screening_{dx_code}"

                    diagnosis = Diagnosis(
                        diagnosis_id=diagnosis_id,
                        patient_id=ptid,
                        visit_id=f"{ptid}_screening",
                        diagnosis_code=dx_code,
                        diagnosis_text=self._get_diagnosis_text(dx_code),
                        confidence=1.0,
                        criteria_used="ADNI Screening",
                        source_table='ARM'
                    )

                    self.diagnoses.append(diagnosis)
                    count += 1

        return count

    def _extract_from_blchange(self, df: pd.DataFrame) -> int:
        """Extract baseline diagnoses from BLCHANGE table"""
        count = 0

        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            if not ptid:
                continue

            # BCPREDX contains baseline predicted diagnosis
            if 'BCPREDX' in row and pd.notna(row['BCPREDX']):
                dx_value = row['BCPREDX']
                dx_code = self._map_diagnosis_value(dx_value)

                if dx_code:
                    viscode = str(row.get('VISCODE2', row.get('VISCODE', 'bl'))).strip()
                    visit_id = f"{ptid}_{viscode}"
                    diagnosis_id = f"dx_{ptid}_{viscode}_{dx_code}_predicted"

                    diagnosis = Diagnosis(
                        diagnosis_id=diagnosis_id,
                        patient_id=ptid,
                        visit_id=visit_id,
                        diagnosis_code=dx_code,
                        diagnosis_text=self._get_diagnosis_text(dx_code),
                        confidence=0.85,  # Predicted diagnosis
                        criteria_used="ADNI Baseline Prediction",
                        source_table='BLCHANGE'
                    )

                    self.diagnoses.append(diagnosis)
                    count += 1

        return count

    def _extract_from_cdr(self, df: pd.DataFrame) -> int:
        """Extract derived diagnoses from CDR scores"""
        count = 0

        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            if not ptid:
                continue

            cdr_global = row.get('CDGLOBAL')
            if pd.notna(cdr_global):
                # Map CDR score to diagnosis
                if cdr_global == 0:
                    dx_code = 'CN'
                elif cdr_global <= 0.5:
                    dx_code = 'MCI'
                elif cdr_global >= 1:
                    dx_code = 'AD'
                else:
                    continue

                viscode = str(row.get('VISCODE2', row.get('VISCODE', 'bl'))).strip()
                visit_id = f"{ptid}_{viscode}"
                diagnosis_id = f"dx_{ptid}_{viscode}_{dx_code}_CDR"

                diagnosis = Diagnosis(
                    diagnosis_id=diagnosis_id,
                    patient_id=ptid,
                    visit_id=visit_id,
                    diagnosis_code=dx_code,
                    diagnosis_text=self._get_diagnosis_text(dx_code),
                    confidence=0.8,
                    criteria_used="Derived from CDR",
                    source_table='CDR'
                )

                self.diagnoses.append(diagnosis)
                count += 1

        return count

    def _extract_from_mmse(self, df: pd.DataFrame) -> int:
        """Extract derived diagnoses from MMSE scores"""
        count = 0

        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            if not ptid:
                continue

            mmse_score = row.get('MMSCORE')
            if pd.notna(mmse_score):
                # Map MMSE score to diagnosis
                if mmse_score >= 27:
                    dx_code = 'CN'
                elif mmse_score >= 21:
                    dx_code = 'MCI'
                else:
                    dx_code = 'AD'

                viscode = str(row.get('VISCODE2', row.get('VISCODE', 'bl'))).strip()
                visit_id = f"{ptid}_{viscode}"
                diagnosis_id = f"dx_{ptid}_{viscode}_{dx_code}_MMSE"

                diagnosis = Diagnosis(
                    diagnosis_id=diagnosis_id,
                    patient_id=ptid,
                    visit_id=visit_id,
                    diagnosis_code=dx_code,
                    diagnosis_text=self._get_diagnosis_text(dx_code),
                    confidence=0.75,
                    criteria_used="Derived from MMSE",
                    source_table='MMSE'
                )

                self.diagnoses.append(diagnosis)
                count += 1

        return count

    def _extract_cognitive_assessments(self) -> int:
        """Extract cognitive assessments from available tables"""
        count = 0

        # Define test mappings
        tests = [
            ('MMSE', 'MMSCORE', 'MMSE'),
            ('CDR', 'CDGLOBAL', 'CDR'),
            ('ADAS', 'TOTSCORE', 'ADAS-Cog'),
            ('MOCA', 'MOCA', 'MoCA'),
            ('FAQ', 'FAQTOTAL', 'FAQ'),
            ('NEUROBAT', 'LIMMTOTAL', 'Logical Memory')
        ]

        for table_name, score_col, test_name in tests:
            df = self._get_table(table_name)
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
                        if table_name == 'ADAS' and 'TOTAL13' in row:
                            score = row.get('TOTAL13')
                        elif table_name == 'CDR' and 'CDRSB' in row:
                            score = row.get('CDRSB')

                    if pd.notna(score):
                        viscode = str(row.get('VISCODE2', row.get('VISCODE', 'bl'))).strip()
                        visit_id = f"{ptid}_{viscode}"
                        assessment_id = f"cog_{ptid}_{viscode}_{test_name.replace(' ', '_')}"

                        # Extract subscores for CDR
                        subscores = {}
                        if table_name == 'CDR':
                            for sub in ['CDMEMORY', 'CDORIENT', 'CDJUDGE', 'CDCOMMUN', 'CDHOME', 'CDCARE']:
                                if sub in row and pd.notna(row[sub]):
                                    subscores[sub.lower()] = float(row[sub])

                            # Add CDR Sum of Boxes
                            if 'CDRSB' in row and pd.notna(row['CDRSB']):
                                subscores['cdr_sob'] = float(row['CDRSB'])

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

    def _extract_biomarkers(self) -> int:
        """Extract biomarkers from available tables"""
        count = 0

        # Check for UPENNBIOMK_ROCHE_ELECSYS
        elecsys_df = self._get_table('UPENNBIOMK_ROCHE_ELECSYS')
        if elecsys_df is not None:
            logger.info(f"   Processing UPENNBIOMK_ROCHE_ELECSYS...")

            for _, row in elecsys_df.iterrows():
                ptid = str(row.get('PTID', '')).strip()
                if not ptid:
                    continue

                viscode = str(row.get('VISCODE2', 'bl')).strip()
                visit_id = f"{ptid}_{viscode}"

                # Extract CSF biomarkers
                biomarkers_map = {
                    'ABETA42': ('Aβ42', 600),  # threshold
                    'ABETA40': ('Aβ40', None),
                    'TAU': ('Total Tau', 400),
                    'PTAU': ('p-Tau181', 80)
                }

                for col, (analyte, threshold) in biomarkers_map.items():
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
                            unit='pg/mL',
                            specimen_type='CSF',
                            abnormal_flag=self._check_abnormal(analyte, value, threshold),
                            source_table='UPENNBIOMK_ROCHE_ELECSYS'
                        )

                        self.biomarkers.append(biomarker)
                        count += 1

        # Extract APOE genotype
        apoe_df = self._get_table('APOERES')
        if apoe_df is not None:
            logger.info(f"   Processing APOERES (APOE genotype)...")

            for _, row in apoe_df.iterrows():
                ptid = str(row.get('PTID', '')).strip()
                if not ptid:
                    continue

                genotype = row.get('GENOTYPE')
                if pd.notna(genotype):
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
                        assay_info={'genotype': str(genotype)}
                    )

                    self.biomarkers.append(biomarker)
                    count += 1

        return count

    def _extract_imaging_measures(self) -> Tuple[int, int]:
        """Extract volumetric and PET measures"""
        vol_count = 0
        pet_count = 0

        # Process FreeSurfer volumes
        fs_df = self._get_table('UCSFFSX7')
        if fs_df is not None:
            logger.info(f"   Processing UCSFFSX7 volumes...")

            for _, row in fs_df.iterrows():
                ptid = str(row.get('PTID', row.get('RID', ''))).strip()
                if not ptid:
                    continue

                viscode = str(row.get('VISCODE2', row.get('VISCODE', 'bl'))).strip()
                visit_id = f"{ptid}_{viscode}"

                # Extract hippocampal volumes
                volumes = {
                    'Hippocampus_L': row.get('ST29SV'),
                    'Hippocampus_R': row.get('ST88SV'),
                    'Ventricles': row.get('ST11SV')
                }

                for region, value in volumes.items():
                    if pd.notna(value):
                        measure_id = f"vol_{ptid}_{viscode}_{region}"

                        measure = VolumetricMeasure(
                            measure_id=measure_id,
                            image_id=f"img_{ptid}_{viscode}",
                            patient_id=ptid,
                            visit_id=visit_id,
                            region=region,
                            volume=float(value),
                            unit='mm³',
                            processing_method='FreeSurfer',
                            hemisphere='left' if '_L' in region else ('right' if '_R' in region else 'bilateral')
                        )

                        self.volumetric_measures.append(measure)
                        vol_count += 1

        # Process PET measures
        amy_df = self._get_table('UCBERKELEY_AMY_6MM')
        if amy_df is not None:
            logger.info(f"   Processing UCBERKELEY_AMY_6MM PET data...")

            for _, row in amy_df.iterrows():
                ptid = str(row.get('PTID', row.get('RID', ''))).strip()
                if not ptid:
                    continue

                viscode = str(row.get('VISCODE2', row.get('VISCODE', 'bl'))).strip()
                visit_id = f"{ptid}_{viscode}"

                if 'SUMMARY_SUVR' in row and pd.notna(row['SUMMARY_SUVR']):
                    suvr = float(row['SUMMARY_SUVR'])
                    binding_id = f"pet_{ptid}_{viscode}_amyloid"

                    binding = PETBinding(
                        binding_id=binding_id,
                        image_id=f"img_{ptid}_{viscode}_PET",
                        patient_id=ptid,
                        visit_id=visit_id,
                        tracer='Amyloid',
                        region='Global',
                        suvr=suvr,
                        reference_region='Cerebellum',
                        abnormal_flag=suvr > 1.11  # Threshold for amyloid positivity
                    )

                    self.pet_bindings.append(binding)
                    pet_count += 1

        return vol_count, pet_count

    # Helper methods
    def _safe_equals(self, value, target) -> bool:
        """Safely compare values that might be pd.NA"""
        if pd.isna(value):
            return False
        try:
            return value == target
        except:
            return False

    def _map_diagnosis_code(self, diagnosis_value) -> Optional[str]:
        """Map ADNI diagnosis numeric codes to standard codes"""
        if pd.isna(diagnosis_value):
            return None

        # Convert to int/float for comparison
        try:
            dx_val = float(diagnosis_value)
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
        except (ValueError, TypeError):
            # If it's a string, try string mapping
            return self._map_adni_diagnosis(diagnosis_value)

        return None

    def _map_adni_diagnosis(self, dx_value) -> Optional[str]:
        """Map ADNI diagnosis string values to standard codes"""
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

    def _map_arm_to_diagnosis(self, arm_value: str) -> Optional[str]:
        """Map ARM study values to diagnosis codes"""
        arm_upper = str(arm_value).upper()

        if 'CN' in arm_upper or 'CONTROL' in arm_upper:
            return 'CN'
        elif 'EMCI' in arm_upper:
            return 'EMCI'
        elif 'LMCI' in arm_upper:
            return 'LMCI'
        elif 'SMC' in arm_upper:
            return 'SMC'
        elif 'MCI' in arm_upper:
            return 'MCI'
        elif 'AD' in arm_upper or 'ALZHEIMER' in arm_upper:
            return 'AD'

        # Numeric codes
        try:
            val = int(arm_value)
            if val == 1:
                return 'CN'
            elif val == 2:
                return 'MCI'
            elif val == 3:
                return 'AD'
        except:
            pass

        return None

    def _map_diagnosis_value(self, value) -> Optional[str]:
        """Map various diagnosis values to standard codes"""
        if pd.isna(value):
            return None

        # Handle numeric codes
        try:
            val = float(value)
            if val == 1:
                return 'CN'
            elif val == 2:
                return 'MCI'
            elif val == 3:
                return 'AD'
        except:
            pass

        # Handle string values
        str_val = str(value).upper()
        if 'CN' in str_val or 'NORMAL' in str_val:
            return 'CN'
        elif 'MCI' in str_val:
            return 'MCI'
        elif 'AD' in str_val or 'ALZHEIMER' in str_val:
            return 'AD'

        return None

    def _get_diagnosis_text(self, code: str) -> str:
        """Get full diagnosis text from code"""
        texts = {
            'CN': 'Cognitively Normal',
            'SMC': 'Subjective Memory Concern',
            'EMCI': 'Early Mild Cognitive Impairment',
            'LMCI': 'Late Mild Cognitive Impairment',
            'MCI': 'Mild Cognitive Impairment',
            'AD': "Alzheimer's Disease"
        }
        return texts.get(code, code)

    def _check_abnormal(self, analyte: str, value: float, threshold: Optional[float]) -> bool:
        """Check if biomarker value is abnormal"""
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
            return value > 2
        else:
            return value > threshold if threshold else False

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
            return 1.0

        try:
            genotype_str = str(genotype)
        except:
            return 1.0

        if '4/4' in genotype_str or 'E4/E4' in genotype_str:
            return 12.0  # Highest risk
        elif '3/4' in genotype_str or 'E3/E4' in genotype_str:
            return 3.0   # High risk
        elif '2/4' in genotype_str or 'E2/E4' in genotype_str:
            return 2.5   # Moderate risk
        elif '3/3' in genotype_str or 'E3/E3' in genotype_str:
            return 1.0   # Normal risk
        elif '2/2' in genotype_str or '2/3' in genotype_str:
            return 0.6   # Protective
        else:
            return 1.0

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
            dx_sources = {}
            for d in self.diagnoses:
                dx_counts[d.diagnosis_code] = dx_counts.get(d.diagnosis_code, 0) + 1
                if hasattr(d, 'source_table'):
                    source = d.source_table
                    dx_sources[source] = dx_sources.get(source, 0) + 1

            logger.info("\nDiagnosis breakdown by code:")
            for dx_code, count in sorted(dx_counts.items()):
                logger.info(f"  {dx_code}: {count}")

            logger.info("\nDiagnosis breakdown by source:")
            for source, count in sorted(dx_sources.items()):
                logger.info(f"  {source}: {count}")

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

        logger.info("="*60)


def execute_findings_extraction_fixed(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                                     table_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """Execute fixed findings extraction with comprehensive diagnosis sources"""
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