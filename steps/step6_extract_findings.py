"""
Step 6: Extract Clinical Findings
Extracts cognitive assessments, biomarkers, diagnoses, and other clinical findings
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
    """Extract clinical findings from ADNI tables"""

    # Cognitive test configurations
    COGNITIVE_TESTS = {
        'MMSE': {
            'table': 'MMSE',
            'score_col': 'MMSCORE',
            'max_score': 30,
            'impairment_thresholds': {
                'severe': (0, 9),
                'moderate': (10, 18),
                'mild': (19, 23),
                'normal': (24, 30)
            }
        },
        'CDR': {
            'table': 'CDR',
            'score_col': 'CDGLOBAL',
            'subscores': ['CDMEMORY', 'CDORIENT', 'CDJUDGE', 'CDCOMMUN', 'CDHOME', 'CDCARE'],
            'severity_map': {
                0: 'normal',
                0.5: 'questionable',
                1: 'mild',
                2: 'moderate',
                3: 'severe'
            }
        },
        'ADAS-Cog': {
            'table': 'ADAS',
            'score_col': 'TOTSCORE',
            'subscores': ['Q1SCORE', 'Q2SCORE', 'Q3SCORE', 'Q4SCORE', 'Q5SCORE',
                          'Q6SCORE', 'Q7SCORE', 'Q8SCORE', 'Q9SCORE', 'Q10SCORE',
                          'Q11SCORE', 'Q12SCORE', 'Q13SCORE', 'Q14SCORE'],
            'higher_worse': True
        },
        'MoCA': {
            'table': 'MOCA',
            'score_col': 'MCATOT',
            'max_score': 30,
            'impairment_threshold': 26
        },
        'FAQ': {
            'table': 'FAQ',
            'score_col': 'FAQTOTAL',
            'functional_test': True
        },
        'RAVLT': {
            'table': 'NEUROBAT',
            'score_cols': ['RAVLT_immediate', 'RAVLT_learning', 'RAVLT_forgetting'],
            'memory_test': True
        }
    }

    # Biomarker configurations
    BIOMARKER_CONFIGS = {
        'CSF': {
            'tables': ['BIOMARK', 'ELECSYS'],
            'markers': {
                'ABETA42': {'unit': 'pg/mL', 'abnormal_threshold': 600, 'lower_abnormal': True},
                'TAU': {'unit': 'pg/mL', 'abnormal_threshold': 400, 'lower_abnormal': False},
                'PTAU': {'unit': 'pg/mL', 'abnormal_threshold': 80, 'lower_abnormal': False},
                'PTAU181P': {'unit': 'pg/mL', 'abnormal_threshold': 80, 'lower_abnormal': False}
            }
        },
        'PLASMA': {
            'tables': ['LABDATA'],
            'markers': {
                'NFL': {'unit': 'pg/mL', 'abnormal_threshold': 50, 'lower_abnormal': False},
                'GFAP': {'unit': 'pg/mL', 'abnormal_threshold': 200, 'lower_abnormal': False}
            }
        }
    }

    def __init__(self, connector: Neo4jConnector, table_data: Dict[str, pd.DataFrame]):
        self.connector = connector
        self.table_data = table_data
        self.cognitive_assessments = []
        self.biomarkers = []
        self.diagnoses = []
        self.volumetric_measures = []
        self.pet_bindings = []

    def execute(self) -> Dict[str, Any]:
        """
        Extract all clinical findings

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

        # Extract cognitive assessments
        logger.info("Extracting cognitive assessments...")
        cog_results = self._extract_cognitive_assessments()
        results['cognitive_assessments'] = cog_results['count']
        results['errors'].extend(cog_results['errors'])

        # Extract biomarkers
        logger.info("Extracting biomarker data...")
        bio_results = self._extract_biomarkers()
        results['biomarkers'] = bio_results['count']
        results['errors'].extend(bio_results['errors'])

        # Extract diagnoses
        logger.info("Extracting diagnoses...")
        dx_results = self._extract_diagnoses()
        results['diagnoses'] = dx_results['count']
        results['errors'].extend(dx_results['errors'])

        # Extract volumetric measures
        logger.info("Extracting volumetric measures...")
        vol_results = self._extract_volumetric_measures()
        results['volumetric_measures'] = vol_results['count']
        results['errors'].extend(vol_results['errors'])

        # Extract PET binding values
        logger.info("Extracting PET binding values...")
        pet_results = self._extract_pet_bindings()
        results['pet_bindings'] = pet_results['count']
        results['errors'].extend(pet_results['errors'])

        return results

    def _extract_cognitive_assessments(self) -> Dict[str, Any]:
        """Extract cognitive test results"""
        results = {'count': 0, 'errors': []}

        for test_name, config in self.COGNITIVE_TESTS.items():
            try:
                # Check if table exists
                table_name = config['table']
                if table_name not in self.table_data:
                    logger.warning(f"Table {table_name} not found for test {test_name}")
                    continue

                df = self.table_data[table_name]

                # Process each row
                for _, row in df.iterrows():
                    assessment = self._process_cognitive_row(row, test_name, config)
                    if assessment:
                        self.cognitive_assessments.append(assessment)
                        results['count'] += 1

            except Exception as e:
                logger.error(f"Error extracting {test_name}: {e}")
                results['errors'].append(f"{test_name}: {str(e)}")

        logger.info(f"Extracted {results['count']} cognitive assessments")
        return results

    def _process_cognitive_row(self, row: pd.Series, test_name: str,
                               config: Dict[str, Any]) -> Optional[CognitiveAssessment]:
        """Process a single cognitive assessment row"""
        # Extract patient and visit info
        ptid = str(row.get('PTID', '')).strip()
        viscode = str(row.get('VISCODE', '')).strip()

        if not ptid or not viscode:
            return None

        # Generate IDs
        assessment_id = f"cog_{ptid}_{test_name}_{viscode}_{uuid.uuid4().hex[:6]}"
        visit_id = f"{ptid}_{viscode}"

        # Extract primary score
        total_score = None
        if 'score_col' in config:
            score_val = row.get(config['score_col'])
            total_score = DataValidator.clean_numeric(score_val)
        elif 'score_cols' in config:
            # Multiple score columns (e.g., RAVLT)
            scores = []
            for col in config['score_cols']:
                if col in row:
                    val = DataValidator.clean_numeric(row[col])
                    if val is not None:
                        scores.append(val)
            if scores:
                total_score = np.mean(scores)  # Or other aggregation

        # Extract subscores
        subscores = {}
        if 'subscores' in config:
            for subscore_col in config['subscores']:
                if subscore_col in row:
                    val = DataValidator.clean_numeric(row[subscore_col])
                    if val is not None:
                        subscores[subscore_col] = val

        # Determine clinical significance
        clinical_significance = self._determine_cognitive_significance(
            test_name, total_score, config
        )

        # Create assessment object
        assessment = CognitiveAssessment(
            assessment_id=assessment_id,
            patient_id=ptid,
            visit_id=visit_id,
            test_name=test_name,
            test_version=row.get('VERSION', None),
            total_score=total_score,
            subscores=subscores,
            clinical_significance=clinical_significance,
            source_table=config['table']
        )

        return assessment

    def _determine_cognitive_significance(self, test_name: str, score: Optional[float],
                                          config: Dict[str, Any]) -> Optional[str]:
        """Determine clinical significance of cognitive score"""
        if score is None:
            return None

        # MMSE
        if test_name == 'MMSE' and 'impairment_thresholds' in config:
            for severity, (min_val, max_val) in config['impairment_thresholds'].items():
                if min_val <= score <= max_val:
                    return severity

        # CDR
        elif test_name == 'CDR' and 'severity_map' in config:
            return config['severity_map'].get(score, 'unknown')

        # MoCA
        elif test_name == 'MoCA' and 'impairment_threshold' in config:
            return 'impaired' if score < config['impairment_threshold'] else 'normal'

        # ADAS-Cog (higher scores = worse)
        elif test_name == 'ADAS-Cog' and config.get('higher_worse'):
            if score >= 30:
                return 'severe'
            elif score >= 20:
                return 'moderate'
            elif score >= 10:
                return 'mild'
            else:
                return 'normal'

        return None

    def _extract_biomarkers(self) -> Dict[str, Any]:
        """Extract biomarker measurements"""
        results = {'count': 0, 'errors': []}

        for biomarker_type, config in self.BIOMARKER_CONFIGS.items():
            for table_name in config['tables']:
                if table_name not in self.table_data:
                    continue

                df = self.table_data[table_name]

                try:
                    # Process each row
                    for _, row in df.iterrows():
                        markers = self._process_biomarker_row(
                            row, biomarker_type, config['markers']
                        )

                        for marker in markers:
                            self.biomarkers.append(marker)
                            results['count'] += 1

                except Exception as e:
                    logger.error(f"Error extracting from {table_name}: {e}")
                    results['errors'].append(f"{table_name}: {str(e)}")

        logger.info(f"Extracted {results['count']} biomarker measurements")
        return results

    def _process_biomarker_row(self, row: pd.Series, biomarker_type: str,
                               marker_configs: Dict[str, Dict]) -> List[Biomarker]:
        """Process biomarker measurements from a row"""
        markers = []

        # Extract patient and visit info
        ptid = str(row.get('PTID', '')).strip()
        viscode = str(row.get('VISCODE', '')).strip()

        if not ptid or not viscode:
            return markers

        visit_id = f"{ptid}_{viscode}"

        # Check each configured marker
        for marker_name, marker_config in marker_configs.items():
            # Look for marker column
            marker_cols = [col for col in row.index if marker_name in col.upper()]

            for col in marker_cols:
                value = DataValidator.clean_numeric(row[col])
                if value is None:
                    continue

                # Generate ID
                biomarker_id = f"bio_{ptid}_{marker_name}_{viscode}_{uuid.uuid4().hex[:6]}"

                # Determine if abnormal
                abnormal_flag = None
                if 'abnormal_threshold' in marker_config:
                    threshold = marker_config['abnormal_threshold']
                    lower_abnormal = marker_config.get('lower_abnormal', False)

                    if lower_abnormal:
                        abnormal_flag = value < threshold
                    else:
                        abnormal_flag = value > threshold

                # Create biomarker object
                biomarker = Biomarker(
                    biomarker_id=biomarker_id,
                    patient_id=ptid,
                    visit_id=visit_id,
                    biomarker_type=biomarker_type,
                    analyte=marker_name,
                    value=value,
                    unit=marker_config.get('unit', 'unknown'),
                    specimen_type=biomarker_type,
                    abnormal_flag=abnormal_flag,
                    source_table=row.get('TABLE_NAME', 'unknown')
                )

                markers.append(biomarker)

        return markers

    def _extract_diagnoses(self) -> Dict[str, Any]:
        """Extract clinical diagnoses"""
        results = {'count': 0, 'errors': []}

        # Primary diagnosis table
        if 'DXSUM' not in self.table_data:
            logger.warning("DXSUM table not found")
            return results

        df = self.table_data['DXSUM']

        try:
            for _, row in df.iterrows():
                diagnosis = self._process_diagnosis_row(row)
                if diagnosis:
                    self.diagnoses.append(diagnosis)
                    results['count'] += 1

        except Exception as e:
            logger.error(f"Error extracting diagnoses: {e}")
            results['errors'].append(str(e))

        logger.info(f"Extracted {results['count']} diagnoses")
        return results

    def _process_diagnosis_row(self, row: pd.Series) -> Optional[Diagnosis]:
        """Process a diagnosis row"""
        # Extract patient and visit info
        ptid = str(row.get('PTID', '')).strip()
        viscode = str(row.get('VISCODE', '')).strip()

        if not ptid or not viscode:
            return None

        # Generate IDs
        diagnosis_id = f"dx_{ptid}_{viscode}_{uuid.uuid4().hex[:6]}"
        visit_id = f"{ptid}_{viscode}"

        # Extract diagnosis code
        dx_code = row.get('DIAGNOSIS', row.get('DXCHANGE', ''))
        if pd.isna(dx_code):
            return None

        # Map diagnosis code
        diagnosis_map = {
            '1': ('CN', 'Cognitively Normal'),
            '2': ('MCI', 'Mild Cognitive Impairment'),
            '3': ('AD', 'Alzheimer\'s Disease'),
            '4': ('SMC', 'Subjective Memory Concern'),
            '5': ('EMCI', 'Early Mild Cognitive Impairment'),
            '6': ('LMCI', 'Late Mild Cognitive Impairment'),
            '7': ('CN', 'Cognitively Normal'),
            '8': ('MCI', 'MCI to Normal Reversion'),
            '9': ('AD', 'AD to MCI Reversion')
        }

        dx_code_str = str(dx_code).strip()
        if dx_code_str in diagnosis_map:
            diagnosis_code, diagnosis_text = diagnosis_map[dx_code_str]
        else:
            diagnosis_code = f"OTHER_{dx_code_str}"
            diagnosis_text = f"Other diagnosis: {dx_code_str}"

        # Extract confidence if available
        confidence = DataValidator.clean_numeric(row.get('DXCONFID'))

        # Create diagnosis object
        diagnosis = Diagnosis(
            diagnosis_id=diagnosis_id,
            patient_id=ptid,
            visit_id=visit_id,
            diagnosis_code=diagnosis_code,
            diagnosis_text=diagnosis_text,
            confidence=confidence,
            criteria_used=row.get('DXMETHOD', None),
            source_table='DXSUM'
        )

        return diagnosis

    def _extract_volumetric_measures(self) -> Dict[str, Any]:
        """Extract brain volumetric measurements"""
        results = {'count': 0, 'errors': []}

        # Tables with volumetric data
        volume_tables = ['UCSFFSX7', 'FOXLABBSI', 'MRI3META']

        for table_name in volume_tables:
            if table_name not in self.table_data:
                continue

            df = self.table_data[table_name]

            try:
                if table_name == 'UCSFFSX7':
                    measures = self._process_freesurfer_volumes(df)
                else:
                    measures = self._process_general_volumes(df, table_name)

                self.volumetric_measures.extend(measures)
                results['count'] += len(measures)

            except Exception as e:
                logger.error(f"Error extracting from {table_name}: {e}")
                results['errors'].append(f"{table_name}: {str(e)}")

        logger.info(f"Extracted {results['count']} volumetric measures")
        return results

    def _process_freesurfer_volumes(self, df: pd.DataFrame) -> List[VolumetricMeasure]:
        """Process FreeSurfer volumetric data"""
        measures = []

        # Key regions to extract
        region_mappings = {
            'Hippocampus': ['HippVol', 'HIPPL', 'HIPPR'],
            'Amygdala': ['AmygVol', 'AMYGL', 'AMYGR'],
            'Ventricles': ['VentVol', 'LATVENTL', 'LATVENTR'],
            'Entorhinal': ['EntCtx', 'ENTL', 'ENTR'],
            'Fusiform': ['FusCtx', 'FUSL', 'FUSR'],
            'MidTemp': ['MidTempCtx', 'MIDTEMPL', 'MIDTEMPR']
        }

        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            viscode = str(row.get('VISCODE', '')).strip()

            if not ptid or not viscode:
                continue

            visit_id = f"{ptid}_{viscode}"

            # Look for image ID
            image_id = None  # Would need to match with processed images

            for region_name, column_patterns in region_mappings.items():
                for pattern in column_patterns:
                    # Find matching columns
                    matching_cols = [col for col in df.columns if pattern in col.upper()]

                    for col in matching_cols:
                        value = DataValidator.clean_numeric(row[col])
                        if value is None:
                            continue

                        # Determine hemisphere
                        hemisphere = None
                        if col.endswith('L'):
                            hemisphere = 'left'
                        elif col.endswith('R'):
                            hemisphere = 'right'

                        # Generate ID
                        measure_id = f"vol_{ptid}_{region_name}_{viscode}_{uuid.uuid4().hex[:6]}"

                        # Create measure object
                        measure = VolumetricMeasure(
                            measure_id=measure_id,
                            image_id=image_id or f"img_{ptid}_{viscode}",
                            patient_id=ptid,
                            visit_id=visit_id,
                            region=region_name.lower(),
                            volume=value,
                            unit="mm³",
                            hemisphere=hemisphere,
                            processing_method='FreeSurfer'
                        )

                        measures.append(measure)

        return measures

    def _process_general_volumes(self, df: pd.DataFrame,
                                 table_name: str) -> List[VolumetricMeasure]:
        """Process general volumetric data"""
        measures = []

        # Process based on table type
        # This is simplified - would need specific logic for each table

        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            viscode = str(row.get('VISCODE', '')).strip()

            if not ptid or not viscode:
                continue

            # Extract any numeric columns that look like volumes
            for col in df.columns:
                if any(term in col.upper() for term in ['VOL', 'VOLUME', 'SIZE']):
                    value = DataValidator.clean_numeric(row[col])
                    if value is None:
                        continue

                    # Create simplified measure
                    measure_id = f"vol_{ptid}_{col}_{viscode}_{uuid.uuid4().hex[:6]}"
                    visit_id = f"{ptid}_{viscode}"

                    measure = VolumetricMeasure(
                        measure_id=measure_id,
                        image_id=f"img_{ptid}_{viscode}",
                        patient_id=ptid,
                        visit_id=visit_id,
                        region=col.lower(),
                        volume=value,
                        unit="mm³",
                        processing_method=table_name
                    )

                    measures.append(measure)

        return measures

    def _extract_pet_bindings(self) -> Dict[str, Any]:
        """Extract PET binding values"""
        results = {'count': 0, 'errors': []}

        # PET-specific tables
        pet_tables = {
            'AV45META': 'AV45',  # Amyloid
            'TAUMETA': 'AV1451',  # Tau
            'AMYMETA': 'AV45',  # Alternative amyloid
            'PETC3': 'FDG'  # Metabolism
        }

        for table_name, default_tracer in pet_tables.items():
            if table_name not in self.table_data:
                continue

            df = self.table_data[table_name]

            try:
                bindings = self._process_pet_binding_table(df, default_tracer)
                self.pet_bindings.extend(bindings)
                results['count'] += len(bindings)

            except Exception as e:
                logger.error(f"Error extracting from {table_name}: {e}")
                results['errors'].append(f"{table_name}: {str(e)}")

        logger.info(f"Extracted {results['count']} PET binding values")
        return results

    def _process_pet_binding_table(self, df: pd.DataFrame,
                                   default_tracer: str) -> List[PETBinding]:
        """Process PET binding data from a table"""
        bindings = []

        # Common PET regions
        regions = [
            'FRONTAL', 'TEMPORAL', 'PARIETAL', 'CINGULATE',
            'COMPOSITE', 'GLOBAL', 'PRECUNEUS'
        ]

        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            viscode = str(row.get('VISCODE', '')).strip()

            if not ptid or not viscode:
                continue

            visit_id = f"{ptid}_{viscode}"

            # Extract tracer if specified
            tracer = row.get('TRACER', default_tracer)

            # Look for SUVR columns
            for col in df.columns:
                if 'SUVR' not in col.upper():
                    continue

                value = DataValidator.clean_numeric(row[col])
                if value is None:
                    continue

                # Determine region from column name
                region = 'unknown'
                for r in regions:
                    if r in col.upper():
                        region = r.lower()
                        break

                # Generate ID
                binding_id = f"pet_{ptid}_{tracer}_{region}_{viscode}_{uuid.uuid4().hex[:6]}"

                # Determine if abnormal (simplified)
                abnormal_flag = None
                if tracer == 'AV45' and value > 1.11:  # Common threshold
                    abnormal_flag = True
                elif tracer == 'AV1451' and value > 1.3:
                    abnormal_flag = True

                # Create binding object
                binding = PETBinding(
                    binding_id=binding_id,
                    image_id=f"img_{ptid}_{viscode}_PET",
                    patient_id=ptid,
                    visit_id=visit_id,
                    tracer=tracer,
                    region=region,
                    suvr=value,
                    reference_region=row.get('REFERENCE', 'cerebellum'),
                    abnormal_flag=abnormal_flag
                )

                bindings.append(binding)

        return bindings

    def get_findings_summary(self) -> Dict[str, Any]:
        """Get summary of extracted findings"""
        summary = {
            'cognitive': {
                'total': len(self.cognitive_assessments),
                'by_test': {},
                'by_significance': {}
            },
            'biomarkers': {
                'total': len(self.biomarkers),
                'by_type': {},
                'abnormal_count': 0
            },
            'diagnoses': {
                'total': len(self.diagnoses),
                'by_code': {}
            },
            'volumetric': {
                'total': len(self.volumetric_measures),
                'by_region': {}
            },
            'pet': {
                'total': len(self.pet_bindings),
                'by_tracer': {},
                'abnormal_count': 0
            }
        }

        # Cognitive summary
        for assessment in self.cognitive_assessments:
            test = assessment.test_name
            summary['cognitive']['by_test'][test] = \
                summary['cognitive']['by_test'].get(test, 0) + 1

            if assessment.clinical_significance:
                sig = assessment.clinical_significance
                summary['cognitive']['by_significance'][sig] = \
                    summary['cognitive']['by_significance'].get(sig, 0) + 1

        # Biomarker summary
        for biomarker in self.biomarkers:
            btype = biomarker.biomarker_type
            summary['biomarkers']['by_type'][btype] = \
                summary['biomarkers']['by_type'].get(btype, 0) + 1

            if biomarker.abnormal_flag:
                summary['biomarkers']['abnormal_count'] += 1

        # Diagnosis summary
        for diagnosis in self.diagnoses:
            code = diagnosis.diagnosis_code
            summary['diagnoses']['by_code'][code] = \
                summary['diagnoses']['by_code'].get(code, 0) + 1

        # Volumetric summary
        for measure in self.volumetric_measures:
            region = measure.region
            summary['volumetric']['by_region'][region] = \
                summary['volumetric']['by_region'].get(region, 0) + 1

        # PET summary
        for binding in self.pet_bindings:
            tracer = binding.tracer
            summary['pet']['by_tracer'][tracer] = \
                summary['pet']['by_tracer'].get(tracer, 0) + 1

            if binding.abnormal_flag:
                summary['pet']['abnormal_count'] += 1

        return summary


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