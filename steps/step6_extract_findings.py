"""
Step 6: Extract Clinical Findings (ENHANCED)
Extracts cognitive assessments, biomarkers, diagnoses with improved table discovery
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


class FindingsExtractor:
    """Extract clinical findings from ADNI tables with enhanced table discovery"""

    def __init__(self, connector: Neo4jConnector, table_data: Dict[str, pd.DataFrame]):
        self.connector = connector
        self.table_data = table_data
        self.cognitive_assessments = []
        self.biomarkers = []
        self.diagnoses = []
        self.volumetric_measures = []
        self.pet_bindings = []

        # Debug: Log available tables
        logger.info(f"Available tables for findings extraction: {list(table_data.keys())}")

        # Discover actual table and column names
        self._discover_table_structure()

    def _discover_table_structure(self) -> None:
        """Discover actual table structure and column names"""
        self.discovered_tables = {
            'cognitive': [],
            'biomarker': [],
            'diagnosis': [],
            'imaging': []
        }

        # Discover cognitive tables
        cognitive_patterns = ['MMSE', 'CDR', 'ADAS', 'MOCA', 'RAVLT', 'FAQ', 'NEUROBAT', 'COG']
        for table_name in self.table_data.keys():
            if any(pattern in table_name.upper() for pattern in cognitive_patterns):
                self.discovered_tables['cognitive'].append(table_name)
                logger.info(f"Found cognitive table: {table_name}")

        # Discover biomarker tables
        biomarker_patterns = ['CSF', 'BIOMARK', 'ELECSYS', 'LAB', 'PLASMA', 'BLOOD', 'ABETA', 'TAU', 'PTAU']
        for table_name in self.table_data.keys():
            if any(pattern in table_name.upper() for pattern in biomarker_patterns):
                self.discovered_tables['biomarker'].append(table_name)
                logger.info(f"Found biomarker table: {table_name}")

        # Discover diagnosis tables
        diagnosis_patterns = ['DX', 'DIAG', 'DXSUM', 'BLCHANGE', 'ADNIMERGE', 'REGISTRY']
        for table_name in self.table_data.keys():
            if any(pattern in table_name.upper() for pattern in diagnosis_patterns):
                self.discovered_tables['diagnosis'].append(table_name)
                logger.info(f"Found diagnosis table: {table_name}")

        # Discover imaging tables
        imaging_patterns = ['UCSF', 'FSX', 'VOLUME', 'MRI', 'PET', 'SUVR', 'FREESURFER']
        for table_name in self.table_data.keys():
            if any(pattern in table_name.upper() for pattern in imaging_patterns):
                self.discovered_tables['imaging'].append(table_name)
                logger.info(f"Found imaging table: {table_name}")

        # Log discovery results
        for category, tables in self.discovered_tables.items():
            logger.info(f"{category.upper()} tables found: {len(tables)}")

    def execute(self) -> Dict[str, Any]:
        """
        Extract all clinical findings with enhanced discovery

        Returns:
            Dictionary with extraction results
        """
        results = {
            'cognitive_assessments': 0,
            'biomarkers': 0,
            'diagnoses': 0,
            'volumetric_measures': 0,
            'pet_bindings': 0,
            'errors': []
        }

        # Extract each type of finding
        for extraction_func, result_key in [
            (self._extract_cognitive_assessments_enhanced, 'cognitive_assessments'),
            (self._extract_biomarkers_enhanced, 'biomarkers'),
            (self._extract_diagnoses_enhanced, 'diagnoses'),
            (self._extract_volumetric_measures, 'volumetric_measures'),
            (self._extract_pet_bindings, 'pet_bindings')
        ]:
            try:
                logger.info(f"Extracting {result_key}...")
                extraction_results = extraction_func()
                results[result_key] = extraction_results['count']
                results['errors'].extend(extraction_results['errors'])
            except Exception as e:
                logger.error(f"Failed to extract {result_key}: {e}")
                results['errors'].append(f"{result_key}: {str(e)}")

        return results

    def _extract_cognitive_assessments_enhanced(self) -> Dict[str, Any]:
        """Extract cognitive assessments with flexible discovery"""
        results = {'count': 0, 'errors': []}

        # Process discovered cognitive tables
        for table_name in self.discovered_tables['cognitive']:
            try:
                df = self.table_data[table_name]
                logger.info(f"Processing cognitive table {table_name} with {len(df)} rows")

                # Find ID columns
                ptid_col = self._find_column(df, ['PTID', 'RID', 'SUBJID', 'SUBJECT', 'ID'])
                viscode_col = self._find_column(df, ['VISCODE', 'VISCODE2', 'VISIT', 'VISITCODE', 'VISNO'])

                if not ptid_col or not viscode_col:
                    logger.warning(f"Missing ID columns in {table_name}")
                    continue

                # Find score columns (any numeric column that might be a score)
                score_columns = []
                for col in df.columns:
                    col_upper = col.upper()
                    if any(term in col_upper for term in ['SCORE', 'TOTAL', 'SUM', 'RESULT']):
                        if pd.api.types.is_numeric_dtype(df[col]):
                            score_columns.append(col)

                if not score_columns:
                    # Try any numeric column
                    score_columns = [col for col in df.columns
                                   if pd.api.types.is_numeric_dtype(df[col])
                                   and col not in [ptid_col, viscode_col]][:5]  # Take first 5

                logger.info(f"Found score columns in {table_name}: {score_columns}")

                # Extract test name from table name
                test_name = self._extract_test_name(table_name)

                # Process rows
                for _, row in df.iterrows():
                    ptid = str(row.get(ptid_col, '')).strip()
                    viscode = str(row.get(viscode_col, '')).strip()

                    if not ptid or not viscode or pd.isna(row[ptid_col]) or pd.isna(row[viscode_col]):
                        continue

                    # Try each score column
                    for score_col in score_columns:
                        score_value = row.get(score_col)
                        if pd.isna(score_value):
                            continue

                        total_score = DataValidator.clean_numeric(score_value)
                        if total_score is None:
                            continue

                        # Generate IDs
                        assessment_id = f"cog_{ptid}_{test_name}_{viscode}_{uuid.uuid4().hex[:6]}"
                        visit_id = f"{ptid}_{viscode}"

                        # Create assessment
                        assessment = CognitiveAssessment(
                            assessment_id=assessment_id,
                            patient_id=ptid,
                            visit_id=visit_id,
                            test_name=f"{test_name}_{score_col}",
                            test_version=None,
                            total_score=total_score,
                            subscores={},
                            clinical_significance=None,
                            source_table=table_name
                        )

                        self.cognitive_assessments.append(assessment)
                        results['count'] += 1
                        break  # Only take first valid score

            except Exception as e:
                logger.error(f"Error processing cognitive table {table_name}: {e}")
                results['errors'].append(f"{table_name}: {str(e)}")

        logger.info(f"Extracted {results['count']} cognitive assessments")
        return results

    def _extract_biomarkers_enhanced(self) -> Dict[str, Any]:
        """Extract biomarkers with enhanced discovery"""
        results = {'count': 0, 'errors': []}

        # Process discovered biomarker tables
        for table_name in self.discovered_tables['biomarker']:
            try:
                df = self.table_data[table_name]
                logger.info(f"Processing biomarker table {table_name} with {len(df)} rows")

                # Find ID columns
                ptid_col = self._find_column(df, ['PTID', 'RID', 'SUBJID', 'ID'])
                viscode_col = self._find_column(df, ['VISCODE', 'VISCODE2', 'VISIT'])

                if not ptid_col or not viscode_col:
                    logger.warning(f"Missing ID columns in {table_name}")
                    continue

                # Find potential biomarker columns
                biomarker_keywords = ['ABETA', 'TAU', 'PTAU', 'NFL', 'GFAP', 'CSF', 'PLASMA']
                biomarker_columns = []

                for col in df.columns:
                    col_upper = col.upper()
                    if any(keyword in col_upper for keyword in biomarker_keywords):
                        if pd.api.types.is_numeric_dtype(df[col]):
                            biomarker_columns.append(col)

                # Also check for any numeric columns with reasonable values
                if not biomarker_columns:
                    for col in df.columns:
                        if pd.api.types.is_numeric_dtype(df[col]) and col not in [ptid_col, viscode_col]:
                            # Check if values are in reasonable range for biomarkers
                            col_values = df[col].dropna()
                            if len(col_values) > 0:
                                mean_val = col_values.mean()
                                if 0 < mean_val < 10000:  # Reasonable range for pg/mL
                                    biomarker_columns.append(col)

                logger.info(f"Found biomarker columns in {table_name}: {biomarker_columns[:10]}")  # Log first 10

                # Process rows
                for _, row in df.iterrows():
                    ptid = str(row.get(ptid_col, '')).strip()
                    viscode = str(row.get(viscode_col, '')).strip()

                    if not ptid or not viscode:
                        continue

                    visit_id = f"{ptid}_{viscode}"

                    # Process each biomarker column
                    for bio_col in biomarker_columns[:5]:  # Limit to first 5 to avoid explosion
                        value = DataValidator.clean_numeric(row[bio_col])
                        if value is None or value <= 0:
                            continue

                        # Determine analyte name from column
                        analyte = self._extract_analyte_name(bio_col)

                        # Generate ID
                        biomarker_id = f"bio_{ptid}_{analyte}_{viscode}_{uuid.uuid4().hex[:6]}"

                        # Determine specimen type
                        specimen_type = 'CSF' if 'CSF' in table_name.upper() else 'PLASMA'

                        # Create biomarker
                        biomarker = Biomarker(
                            biomarker_id=biomarker_id,
                            patient_id=ptid,
                            visit_id=visit_id,
                            biomarker_type=specimen_type,
                            analyte=analyte,
                            value=value,
                            unit='pg/mL',
                            specimen_type=specimen_type,
                            abnormal_flag=None,
                            source_table=table_name
                        )

                        self.biomarkers.append(biomarker)
                        results['count'] += 1

            except Exception as e:
                logger.error(f"Error processing biomarker table {table_name}: {e}")
                results['errors'].append(f"{table_name}: {str(e)}")

        logger.info(f"Extracted {results['count']} biomarker measurements")
        return results

    def _extract_diagnoses_enhanced(self) -> Dict[str, Any]:
        """Extract diagnoses with enhanced discovery"""
        results = {'count': 0, 'errors': []}

        # Check if ADNIMERGE table exists (it usually has diagnosis info)
        if 'ADNIMERGE' in self.table_data:
            df = self.table_data['ADNIMERGE']
            logger.info(f"Processing ADNIMERGE table with {len(df)} rows")

            # ADNIMERGE typically has DX column
            if 'DX' in df.columns:
                count = self._process_adnimerge_diagnoses(df)
                results['count'] += count

        # Process other diagnosis tables
        for table_name in self.discovered_tables['diagnosis']:
            if table_name == 'ADNIMERGE':
                continue  # Already processed

            try:
                df = self.table_data[table_name]
                logger.info(f"Processing diagnosis table {table_name} with {len(df)} rows")

                # Find ID columns
                ptid_col = self._find_column(df, ['PTID', 'RID', 'SUBJID'])
                viscode_col = self._find_column(df, ['VISCODE', 'VISCODE2', 'VISIT'])

                if not ptid_col or not viscode_col:
                    continue

                # Find diagnosis columns
                dx_columns = []
                dx_keywords = ['DX', 'DIAGNOSIS', 'DXCHANGE', 'DXCURREN', 'STATUS', 'GROUP']

                for col in df.columns:
                    col_upper = col.upper()
                    if any(keyword in col_upper for keyword in dx_keywords):
                        dx_columns.append(col)

                logger.info(f"Found diagnosis columns in {table_name}: {dx_columns}")

                # Process rows
                for _, row in df.iterrows():
                    ptid = str(row.get(ptid_col, '')).strip()
                    viscode = str(row.get(viscode_col, '')).strip()

                    if not ptid or not viscode:
                        continue

                    # Check each diagnosis column
                    for dx_col in dx_columns:
                        if dx_col not in row or pd.isna(row[dx_col]):
                            continue

                        dx_value = str(row[dx_col]).strip()

                        # Generate IDs
                        diagnosis_id = f"dx_{ptid}_{viscode}_{uuid.uuid4().hex[:6]}"
                        visit_id = f"{ptid}_{viscode}"

                        # Map diagnosis value
                        diagnosis_code, diagnosis_text = self._map_diagnosis_flexible(dx_value)

                        if not diagnosis_code:
                            continue

                        # Create diagnosis
                        diagnosis = Diagnosis(
                            diagnosis_id=diagnosis_id,
                            patient_id=ptid,
                            visit_id=visit_id,
                            diagnosis_code=diagnosis_code,
                            diagnosis_text=diagnosis_text,
                            confidence=None,
                            criteria_used=None,
                            source_table=table_name
                        )

                        self.diagnoses.append(diagnosis)
                        results['count'] += 1
                        break  # Only take first valid diagnosis

            except Exception as e:
                logger.error(f"Error processing diagnosis table {table_name}: {e}")
                results['errors'].append(f"{table_name}: {str(e)}")

        logger.info(f"Extracted {results['count']} diagnoses")
        return results

    def _process_adnimerge_diagnoses(self, df: pd.DataFrame) -> int:
        """Process diagnoses from ADNIMERGE table specifically"""
        count = 0

        # ADNIMERGE has specific structure
        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            viscode = str(row.get('VISCODE', row.get('VISCODE2', ''))).strip()
            dx = str(row.get('DX', row.get('DX_bl', ''))).strip()

            if not ptid or not viscode or not dx or pd.isna(row.get('PTID')):
                continue

            # Generate IDs
            diagnosis_id = f"dx_{ptid}_{viscode}_{uuid.uuid4().hex[:6]}"
            visit_id = f"{ptid}_{viscode}"

            # Map diagnosis
            diagnosis_code, diagnosis_text = self._map_diagnosis_flexible(dx)

            if not diagnosis_code:
                continue

            # Create diagnosis
            diagnosis = Diagnosis(
                diagnosis_id=diagnosis_id,
                patient_id=ptid,
                visit_id=visit_id,
                diagnosis_code=diagnosis_code,
                diagnosis_text=diagnosis_text,
                confidence=None,
                criteria_used=None,
                source_table='ADNIMERGE'
            )

            self.diagnoses.append(diagnosis)
            count += 1

        return count

    def _extract_test_name(self, table_name: str) -> str:
        """Extract test name from table name"""
        table_upper = table_name.upper()

        if 'MMSE' in table_upper:
            return 'MMSE'
        elif 'CDR' in table_upper:
            return 'CDR'
        elif 'ADAS' in table_upper:
            return 'ADAS'
        elif 'MOCA' in table_upper:
            return 'MoCA'
        elif 'RAVLT' in table_upper:
            return 'RAVLT'
        elif 'FAQ' in table_upper:
            return 'FAQ'
        else:
            return table_name.replace('_', '').upper()[:10]

    def _extract_analyte_name(self, column_name: str) -> str:
        """Extract analyte name from column name"""
        col_upper = column_name.upper()

        if 'ABETA' in col_upper or 'AB42' in col_upper:
            return 'ABETA42'
        elif 'AB40' in col_upper:
            return 'ABETA40'
        elif 'PTAU' in col_upper:
            return 'PTAU'
        elif 'TAU' in col_upper:
            return 'TAU'
        elif 'NFL' in col_upper:
            return 'NFL'
        elif 'GFAP' in col_upper:
            return 'GFAP'
        else:
            # Clean column name
            return column_name.replace('_', '').replace('.', '').upper()[:20]

    def _map_diagnosis_flexible(self, dx_value: str) -> Tuple[Optional[str], Optional[str]]:
        """Map diagnosis value to code and text with flexible matching"""
        if not dx_value:
            return (None, None)

        dx_upper = str(dx_value).strip().upper()

        # Handle common patterns
        if dx_upper in ['CN', 'NL', 'NORMAL', 'CTL', 'CONTROL', '1', '1.0']:
            return ('CN', 'Cognitively Normal')
        elif dx_upper in ['MCI', '2', '2.0']:
            return ('MCI', 'Mild Cognitive Impairment')
        elif dx_upper in ['AD', 'DEMENTIA', 'DEM', '3', '3.0']:
            return ('AD', 'Alzheimer\'s Disease')
        elif dx_upper in ['EMCI', 'EARLY MCI']:
            return ('EMCI', 'Early Mild Cognitive Impairment')
        elif dx_upper in ['LMCI', 'LATE MCI']:
            return ('LMCI', 'Late Mild Cognitive Impairment')
        elif dx_upper in ['SMC', 'MEMORY']:
            return ('SMC', 'Subjective Memory Concern')
        elif 'DEMENTIA' in dx_upper or 'ALZHEIMER' in dx_upper:
            return ('AD', 'Alzheimer\'s Disease')
        elif 'MCI' in dx_upper:
            return ('MCI', 'Mild Cognitive Impairment')
        elif 'NORMAL' in dx_upper or 'CONTROL' in dx_upper:
            return ('CN', 'Cognitively Normal')
        else:
            # Return as-is if can't map
            return (dx_upper[:10], dx_value[:50])

    def _find_column(self, df: pd.DataFrame, patterns: List[str]) -> Optional[str]:
        """Find column matching any of the patterns (case-insensitive)"""
        for pattern in patterns:
            pattern_upper = pattern.upper()
            for col in df.columns:
                if pattern_upper == col.upper() or pattern_upper in col.upper():
                    return col
        return None

    def _extract_volumetric_measures(self) -> Dict[str, Any]:
        """Extract brain volumetric measurements"""
        results = {'count': 0, 'errors': []}

        for table_name in self.discovered_tables['imaging']:
            try:
                df = self.table_data[table_name]

                # Process volumetric data
                if any(term in table_name.upper() for term in ['UCSF', 'FSX', 'FREESURFER']):
                    measures = self._process_volumetric_table(df, table_name)
                    self.volumetric_measures.extend(measures)
                    results['count'] += len(measures)

            except Exception as e:
                logger.error(f"Error extracting volumetric from {table_name}: {e}")
                results['errors'].append(f"{table_name}: {str(e)}")

        logger.info(f"Extracted {results['count']} volumetric measures")
        return results

    def _process_volumetric_table(self, df: pd.DataFrame, table_name: str) -> List[VolumetricMeasure]:
        """Process volumetric data from a table"""
        measures = []

        # Find ID columns
        ptid_col = self._find_column(df, ['PTID', 'RID', 'SUBJID'])
        viscode_col = self._find_column(df, ['VISCODE', 'VISCODE2', 'VISIT'])

        if not ptid_col or not viscode_col:
            return measures

        # Find volume columns
        volume_keywords = ['VOL', 'VOLUME', 'SIZE', 'THICKNESS', 'HIPPO', 'VENT']
        volume_columns = []

        for col in df.columns:
            col_upper = col.upper()
            if any(keyword in col_upper for keyword in volume_keywords):
                if pd.api.types.is_numeric_dtype(df[col]):
                    volume_columns.append(col)

        # Limit to prevent explosion
        volume_columns = volume_columns[:10]

        # Process rows (limit for performance)
        for _, row in df.head(1000).iterrows():
            ptid = str(row.get(ptid_col, '')).strip()
            viscode = str(row.get(viscode_col, '')).strip()

            if not ptid or not viscode:
                continue

            visit_id = f"{ptid}_{viscode}"

            for vol_col in volume_columns:
                value = DataValidator.clean_numeric(row[vol_col])
                if value is None or value <= 0:
                    continue

                # Extract region from column name
                region = self._extract_region_name(vol_col)

                # Generate ID
                measure_id = f"vol_{ptid}_{region}_{viscode}_{uuid.uuid4().hex[:6]}"

                # Create measure
                measure = VolumetricMeasure(
                    measure_id=measure_id,
                    image_id=f"img_{ptid}_{viscode}",
                    patient_id=ptid,
                    visit_id=visit_id,
                    region=region,
                    volume=value,
                    unit="mm³",
                    hemisphere=None,
                    processing_method=table_name
                )

                measures.append(measure)

        return measures

    def _extract_region_name(self, column_name: str) -> str:
        """Extract brain region from column name"""
        col_upper = column_name.upper()

        if 'HIPPO' in col_upper:
            return 'hippocampus'
        elif 'VENT' in col_upper:
            return 'ventricles'
        elif 'ENTORH' in col_upper:
            return 'entorhinal'
        elif 'FUSIFORM' in col_upper:
            return 'fusiform'
        elif 'TEMP' in col_upper:
            return 'temporal'
        elif 'FRONT' in col_upper:
            return 'frontal'
        elif 'PARIET' in col_upper:
            return 'parietal'
        else:
            return column_name.replace('_', '').lower()[:20]

    def _extract_pet_bindings(self) -> Dict[str, Any]:
        """Extract PET binding values"""
        results = {'count': 0, 'errors': []}

        # Look for PET tables
        pet_tables = []
        pet_keywords = ['PET', 'SUVR', 'AV45', 'FDG', 'TAU', 'PIB', 'FLOR']

        for table_name in self.table_data.keys():
            if any(keyword in table_name.upper() for keyword in pet_keywords):
                pet_tables.append(table_name)
                logger.info(f"Found PET table: {table_name}")

        for table_name in pet_tables:
            try:
                df = self.table_data[table_name]
                bindings = self._process_pet_table(df, table_name)
                self.pet_bindings.extend(bindings)
                results['count'] += len(bindings)
            except Exception as e:
                logger.error(f"Error extracting PET from {table_name}: {e}")
                results['errors'].append(f"{table_name}: {str(e)}")

        logger.info(f"Extracted {results['count']} PET binding values")
        return results

    def _process_pet_table(self, df: pd.DataFrame, table_name: str) -> List[PETBinding]:
        """Process PET binding data from a table"""
        bindings = []

        # Find ID columns
        ptid_col = self._find_column(df, ['PTID', 'RID', 'SUBJID'])
        viscode_col = self._find_column(df, ['VISCODE', 'VISCODE2', 'VISIT'])

        if not ptid_col or not viscode_col:
            return bindings

        # Determine tracer from table name
        tracer = 'UNKNOWN'
        if 'AV45' in table_name.upper():
            tracer = 'AV45'
        elif 'FDG' in table_name.upper():
            tracer = 'FDG'
        elif 'TAU' in table_name.upper() or 'AV1451' in table_name.upper():
            tracer = 'TAU'
        elif 'PIB' in table_name.upper():
            tracer = 'PIB'

        # Find SUVR columns
        suvr_columns = []
        for col in df.columns:
            if 'SUVR' in col.upper() and pd.api.types.is_numeric_dtype(df[col]):
                suvr_columns.append(col)

        # Limit columns
        suvr_columns = suvr_columns[:5]

        # Process rows (limit for performance)
        for _, row in df.head(500).iterrows():
            ptid = str(row.get(ptid_col, '')).strip()
            viscode = str(row.get(viscode_col, '')).strip()

            if not ptid or not viscode:
                continue

            visit_id = f"{ptid}_{viscode}"

            for suvr_col in suvr_columns:
                value = DataValidator.clean_numeric(row[suvr_col])
                if value is None or value <= 0:
                    continue

                # Extract region from column name
                region = self._extract_region_from_pet_column(suvr_col)

                # Generate ID
                binding_id = f"pet_{ptid}_{tracer}_{region}_{viscode}_{uuid.uuid4().hex[:6]}"

                # Create binding
                binding = PETBinding(
                    binding_id=binding_id,
                    image_id=f"img_{ptid}_{viscode}_PET",
                    patient_id=ptid,
                    visit_id=visit_id,
                    tracer=tracer,
                    region=region,
                    suvr=value,
                    reference_region='cerebellum',
                    abnormal_flag=None
                )

                bindings.append(binding)

        return bindings

    def _extract_region_from_pet_column(self, column_name: str) -> str:
        """Extract region from PET column name"""
        col_upper = column_name.upper()

        if 'FRONT' in col_upper:
            return 'frontal'
        elif 'TEMP' in col_upper:
            return 'temporal'
        elif 'PARIET' in col_upper:
            return 'parietal'
        elif 'OCCIP' in col_upper:
            return 'occipital'
        elif 'CING' in col_upper:
            return 'cingulate'
        elif 'COMP' in col_upper or 'GLOBAL' in col_upper:
            return 'composite'
        else:
            return 'unknown'

    def get_findings_summary(self) -> Dict[str, Any]:
        """Get summary of extracted findings"""
        return {
            'cognitive': {
                'total': len(self.cognitive_assessments),
                'tables_used': list(set(a.source_table for a in self.cognitive_assessments))
            },
            'biomarkers': {
                'total': len(self.biomarkers),
                'tables_used': list(set(b.source_table for b in self.biomarkers))
            },
            'diagnoses': {
                'total': len(self.diagnoses),
                'tables_used': list(set(d.source_table for d in self.diagnoses))
            },
            'volumetric': {
                'total': len(self.volumetric_measures),
                'tables_used': list(set(m.processing_method for m in self.volumetric_measures))
            },
            'pet': {
                'total': len(self.pet_bindings)
            }
        }


def execute_findings_extraction(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                              table_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """
    Main execution function for findings extraction

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Username
        neo4j_password: Password
        table_data: Loaded table data

    Returns:
        Extraction results
    """
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        extractor = FindingsExtractor(connector, table_data)
        results = extractor.execute()

        # Add summary
        summary = extractor.get_findings_summary()
        results['summary'] = summary

        # Store extractor for next steps
        results['extractor'] = extractor

        logger.info(f"✅ Extracted clinical findings:")
        logger.info(f"   - Cognitive assessments: {results['cognitive_assessments']}")
        logger.info(f"   - Biomarkers: {results['biomarkers']}")
        logger.info(f"   - Diagnoses: {results['diagnoses']}")
        logger.info(f"   - Volumetric measures: {results['volumetric_measures']}")
        logger.info(f"   - PET bindings: {results['pet_bindings']}")

        logger.info(f"   Tables used for cognitive: {summary['cognitive']['tables_used']}")
        logger.info(f"   Tables used for biomarkers: {summary['biomarkers']['tables_used']}")
        logger.info(f"   Tables used for diagnoses: {summary['diagnoses']['tables_used']}")

        return results

    finally:
        connector.close()


if __name__ == "__main__":
    # Test with sample data
    test_data = {
        'MMSE': pd.DataFrame({
            'PTID': ['001_S_0001', '001_S_0001'],
            'VISCODE': ['bl', 'm12'],
            'MMSCORE': [28, 25]
        }),
        'DXSUM': pd.DataFrame({
            'PTID': ['001_S_0001', '001_S_0001'],
            'VISCODE': ['bl', 'm12'],
            'DIAGNOSIS': [1, 2]  # CN to MCI
        })
    }

    results = execute_findings_extraction(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="your_password",
        table_data=test_data
    )

    print(f"Results: {results['summary']}")