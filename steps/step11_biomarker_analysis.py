"""
Step 11: FIXED Comprehensive Biomarker Analysis
Properly extracts biomarkers from ACTUAL ADNI table columns
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict

from models.entities import Biomarker
from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


class ComprehensiveBiomarkerAnalyzer:
    """Fixed biomarker extraction for ADNI data - using actual column names"""

    def __init__(self, connector: Neo4jConnector, table_data: Dict[str, pd.DataFrame]):
        self.connector = connector
        self.table_data = table_data
        self.biomarkers = []
        self.biomarker_profiles = []

        # ADNI biomarker thresholds based on research
        self.thresholds = {
            'ABETA42': {'cutoff': 192, 'direction': 'below', 'unit': 'pg/mL'},
            'TAU': {'cutoff': 93, 'direction': 'above', 'unit': 'pg/mL'},
            'PTAU': {'cutoff': 23, 'direction': 'above', 'unit': 'pg/mL'}
        }

        self.stats = {
            'biomarkers_extracted': 0,
            'profiles_created': 0,
            'csf_markers': 0,
            'blood_markers': 0,
            'genetic_markers': 0
        }

    def execute(self) -> Dict[str, Any]:
        """Execute biomarker extraction"""
        logger.info("\n" + "="*60)
        logger.info("COMPREHENSIVE BIOMARKER ANALYSIS")
        logger.info("="*60)

        # Extract biomarkers from actual ADNI tables
        self._extract_csf_biomarkers_from_upenn()
        self._extract_genetic_markers_from_apoeres()
        self._extract_lab_biomarkers()
        self._extract_plasma_biomarkers()

        # Create profiles
        self._create_biomarker_profiles()

        # Insert to Neo4j
        self._insert_to_neo4j()
        self._create_biomarker_relationships()

        logger.info(f"\n✅ Biomarker Analysis Complete:")
        logger.info(f"   Total biomarkers: {self.stats['biomarkers_extracted']}")
        logger.info(f"   CSF markers: {self.stats['csf_markers']}")
        logger.info(f"   Blood markers: {self.stats['blood_markers']}")
        logger.info(f"   Genetic markers: {self.stats['genetic_markers']}")

        return self.stats

    def _extract_csf_biomarkers_from_upenn(self):
        """Extract CSF biomarkers from UPENNBIOMK_ROCHE_ELECSYS table"""
        table_name = 'UPENNBIOMK_ROCHE_ELECSYS'

        if table_name not in self.table_data:
            # Try to find similar table
            for tbl in self.table_data.keys():
                if 'UPENN' in tbl.upper() or 'ELECSYS' in tbl.upper():
                    table_name = tbl
                    break

        if table_name in self.table_data:
            df = self.table_data[table_name]
            logger.info(f"Processing CSF table: {table_name} with {len(df)} records")

            for _, row in df.iterrows():
                ptid = self._get_value(row, ['PTID', 'RID'])
                if not ptid:
                    continue

                viscode = self._get_value(row, ['VISCODE2', 'VISCODE']) or 'bl'
                visit_id = f"{ptid}_{viscode}"

                # Extract ABETA42
                if 'ABETA42' in row.index and pd.notna(row['ABETA42']):
                    try:
                        value = float(row['ABETA42'])
                        biomarker = {
                            'biomarker_id': f"bio_{ptid}_{viscode}_ABETA42",
                            'patient_id': str(ptid),
                            'visit_id': visit_id,
                            'viscode': viscode,
                            'biomarker_type': 'CSF',
                            'analyte': 'ABETA42',
                            'value': value,
                            'unit': 'pg/mL',
                            'specimen_type': 'CSF',
                            'abnormal_flag': value < 192,  # Below threshold is abnormal
                            'source_table': table_name
                        }
                        self.biomarkers.append(biomarker)
                        self.stats['csf_markers'] += 1
                        self.stats['biomarkers_extracted'] += 1
                    except (ValueError, TypeError):
                        pass

                # Extract TAU
                if 'TAU' in row.index and pd.notna(row['TAU']):
                    try:
                        value = float(row['TAU'])
                        biomarker = {
                            'biomarker_id': f"bio_{ptid}_{viscode}_TAU",
                            'patient_id': str(ptid),
                            'visit_id': visit_id,
                            'viscode': viscode,
                            'biomarker_type': 'CSF',
                            'analyte': 'TAU',
                            'value': value,
                            'unit': 'pg/mL',
                            'specimen_type': 'CSF',
                            'abnormal_flag': value > 93,  # Above threshold is abnormal
                            'source_table': table_name
                        }
                        self.biomarkers.append(biomarker)
                        self.stats['csf_markers'] += 1
                        self.stats['biomarkers_extracted'] += 1
                    except (ValueError, TypeError):
                        pass

                # Extract PTAU
                if 'PTAU' in row.index and pd.notna(row['PTAU']):
                    try:
                        value = float(row['PTAU'])
                        biomarker = {
                            'biomarker_id': f"bio_{ptid}_{viscode}_PTAU",
                            'patient_id': str(ptid),
                            'visit_id': visit_id,
                            'viscode': viscode,
                            'biomarker_type': 'CSF',
                            'analyte': 'PTAU181',
                            'value': value,
                            'unit': 'pg/mL',
                            'specimen_type': 'CSF',
                            'abnormal_flag': value > 23,  # Above threshold is abnormal
                            'source_table': table_name
                        }
                        self.biomarkers.append(biomarker)
                        self.stats['csf_markers'] += 1
                        self.stats['biomarkers_extracted'] += 1
                    except (ValueError, TypeError):
                        pass

    def _extract_genetic_markers_from_apoeres(self):
        """Extract APOE genetic markers from APOERES table"""
        table_name = 'APOERES'

        if table_name not in self.table_data:
            # Try to find the table
            for tbl in self.table_data.keys():
                if 'APOE' in tbl.upper():
                    table_name = tbl
                    break

        if table_name in self.table_data:
            df = self.table_data[table_name]
            logger.info(f"Processing genetic table: {table_name} with {len(df)} records")

            for _, row in df.iterrows():
                ptid = self._get_value(row, ['PTID', 'RID'])
                if not ptid:
                    continue

                genotype = self._get_value(row, ['GENOTYPE'])
                if genotype and pd.notna(genotype):
                    # Parse APOE genotype (format could be like "3/3", "3/4", "4/4")
                    genotype_str = str(genotype)
                    risk_score = self._calculate_apoe_risk(genotype_str)

                    biomarker = {
                        'biomarker_id': f"bio_{ptid}_APOE",
                        'patient_id': str(ptid),
                        'visit_id': f"{ptid}_baseline",
                        'viscode': 'bl',
                        'biomarker_type': 'Genetic',
                        'analyte': 'APOE',
                        'value': risk_score,
                        'unit': 'risk_score',
                        'specimen_type': 'Blood',
                        'abnormal_flag': '4' in genotype_str,
                        'source_table': table_name,
                        'genotype': genotype_str,
                        'e4_copies': genotype_str.count('4')
                    }

                    self.biomarkers.append(biomarker)
                    self.stats['genetic_markers'] += 1
                    self.stats['biomarkers_extracted'] += 1

    def _extract_lab_biomarkers(self):
        """Extract lab biomarkers from LABDATA table"""
        table_name = 'LABDATA'

        if table_name in self.table_data:
            df = self.table_data[table_name]
            logger.info(f"Processing lab table: {table_name} with {len(df)} records")

            # Map LABDATA columns to biomarkers
            biomarker_columns = {
                'RCT11': {'name': 'VITAMIN_B12', 'unit': 'pg/mL', 'threshold': 200, 'direction': 'below'},
                'HMT7': {'name': 'HOMOCYSTEINE', 'unit': 'μmol/L', 'threshold': 15, 'direction': 'above'},
                'RCT392': {'name': 'CHOLESTEROL', 'unit': 'mg/dL', 'threshold': 200, 'direction': 'above'}
            }

            for _, row in df.iterrows():
                ptid = self._get_value(row, ['PTID', 'RID'])
                if not ptid:
                    continue

                viscode = self._get_value(row, ['VISCODE2', 'VISCODE']) or 'bl'
                visit_id = f"{ptid}_{viscode}"

                for col, info in biomarker_columns.items():
                    if col in row.index and pd.notna(row[col]):
                        try:
                            value = float(row[col])

                            abnormal = False
                            if info.get('threshold'):
                                if info['direction'] == 'above':
                                    abnormal = value > info['threshold']
                                else:
                                    abnormal = value < info['threshold']

                            biomarker = {
                                'biomarker_id': f"bio_{ptid}_{viscode}_{info['name']}",
                                'patient_id': str(ptid),
                                'visit_id': visit_id,
                                'viscode': viscode,
                                'biomarker_type': 'Blood',
                                'analyte': info['name'],
                                'value': value,
                                'unit': info['unit'],
                                'specimen_type': 'Blood',
                                'abnormal_flag': abnormal,
                                'source_table': table_name,
                                'source_column': col
                            }

                            self.biomarkers.append(biomarker)
                            self.stats['blood_markers'] += 1
                            self.stats['biomarkers_extracted'] += 1
                        except (ValueError, TypeError):
                            continue

    def _extract_plasma_biomarkers(self):
        """Extract plasma biomarkers from JANSSEN_PLASMA_P217_TAU table"""
        table_name = 'JANSSEN_PLASMA_P217_TAU'

        if table_name in self.table_data:
            df = self.table_data[table_name]
            logger.info(f"Processing plasma table: {table_name} with {len(df)} records")

            for _, row in df.iterrows():
                ptid = self._get_value(row, ['PTID', 'RID'])
                if not ptid:
                    continue

                viscode = self._get_value(row, ['VISCODE2']) or 'bl'
                visit_id = f"{ptid}_{viscode}"

                if 'DILUTION_CORRECTED_CONC' in row.index and pd.notna(row['DILUTION_CORRECTED_CONC']):
                    try:
                        value = float(row['DILUTION_CORRECTED_CONC'])

                        biomarker = {
                            'biomarker_id': f"bio_{ptid}_{viscode}_PTAU217",
                            'patient_id': str(ptid),
                            'visit_id': visit_id,
                            'viscode': viscode,
                            'biomarker_type': 'Plasma',
                            'analyte': 'PTAU217',
                            'value': value,
                            'unit': 'pg/mL',
                            'specimen_type': 'Plasma',
                            'abnormal_flag': False,  # No established threshold yet
                            'source_table': table_name
                        }

                        self.biomarkers.append(biomarker)
                        self.stats['blood_markers'] += 1
                        self.stats['biomarkers_extracted'] += 1
                    except (ValueError, TypeError):
                        pass

    def _get_value(self, row, columns: List[str]) -> Optional[str]:
        """Get first non-null value from list of possible column names"""
        for col in columns:
            if col in row.index and pd.notna(row[col]):
                return str(row[col]).strip()
        return None

    def _calculate_apoe_risk(self, genotype: str) -> float:
        """Calculate APOE risk score based on genotype"""
        if '4/4' in genotype or '44' in genotype:
            return 12.0  # Homozygous E4
        elif '4' in genotype:
            return 3.0   # Heterozygous E4
        elif '2' in genotype:
            return 0.6   # E2 protective
        else:
            return 1.0   # E3/E3 baseline

    def _create_biomarker_profiles(self):
        """Create biomarker profiles for patients"""
        patient_biomarkers = defaultdict(lambda: defaultdict(list))

        for bio in self.biomarkers:
            patient_id = bio['patient_id']
            biomarker_type = bio['biomarker_type']
            patient_biomarkers[patient_id][biomarker_type].append(bio)

        for patient_id, biomarker_types in patient_biomarkers.items():
            csf_markers = {}
            blood_markers = {}
            genetic_markers = {}

            # Process CSF markers
            for bio in biomarker_types.get('CSF', []):
                if bio['viscode'] == 'bl':  # Use baseline values for profile
                    csf_markers[bio['analyte']] = {
                        'value': bio['value'],
                        'abnormal': bio['abnormal_flag']
                    }

            # Process blood/plasma markers
            for bio in biomarker_types.get('Blood', []) + biomarker_types.get('Plasma', []):
                if bio['viscode'] == 'bl':
                    blood_markers[bio['analyte']] = {
                        'value': bio['value'],
                        'abnormal': bio['abnormal_flag']
                    }

            # Process genetic markers
            for bio in biomarker_types.get('Genetic', []):
                genetic_markers[bio['analyte']] = {
                    'value': bio['value'],
                    'abnormal': bio['abnormal_flag'],
                    'genotype': bio.get('genotype')
                }

            # Determine ATN status
            atn_status = self._determine_atn_status(csf_markers)

            # Calculate risk score
            risk_score = self._calculate_risk_score(csf_markers, genetic_markers, atn_status)

            profile = {
                'patient_id': patient_id,
                'csf_markers': csf_markers,
                'blood_markers': blood_markers,
                'genetic_markers': genetic_markers,
                'atn_status': atn_status,
                'risk_score': risk_score
            }

            self.biomarker_profiles.append(profile)
            self.stats['profiles_created'] += 1

    def _determine_atn_status(self, csf_markers: Dict) -> Dict[str, str]:
        """Determine ATN (Amyloid-Tau-Neurodegeneration) status"""
        a_status = 'A?'
        if 'ABETA42' in csf_markers:
            a_status = 'A+' if csf_markers['ABETA42']['abnormal'] else 'A-'

        t_status = 'T?'
        if 'PTAU181' in csf_markers:
            t_status = 'T+' if csf_markers['PTAU181']['abnormal'] else 'T-'

        n_status = 'N?'
        if 'TAU' in csf_markers:
            n_status = 'N+' if csf_markers['TAU']['abnormal'] else 'N-'

        return {
            'A': a_status,
            'T': t_status,
            'N': n_status,
            'profile': f"{a_status}/{t_status}/{n_status}"
        }

    def _calculate_risk_score(self, csf_markers: Dict, genetic_markers: Dict, atn_status: Dict) -> float:
        """Calculate AD risk score based on biomarkers"""
        risk_score = 0.0

        # ATN contribution
        if atn_status['A'] == 'A+':
            risk_score += 3.0
        if atn_status['T'] == 'T+':
            risk_score += 2.5
        if atn_status['N'] == 'N+':
            risk_score += 2.0

        # Genetic contribution
        if 'APOE' in genetic_markers:
            risk_score += genetic_markers['APOE']['value'] * 0.5

        return min(risk_score, 10.0)

    def _insert_to_neo4j(self):
        """Insert biomarkers into Neo4j"""
        if not self.biomarkers:
            logger.warning("No biomarkers to insert")
            return

        logger.info(f"Inserting {len(self.biomarkers)} biomarkers into Neo4j...")

        # Insert Biomarker nodes
        query = """
        UNWIND $batch as bio
        MERGE (b:Biomarker {biomarker_id: bio.biomarker_id})
        SET b += bio,
            b.created_at = datetime()
        """

        batch_size = 500
        for i in range(0, len(self.biomarkers), batch_size):
            batch = self.biomarkers[i:i+batch_size]
            self.connector.batch_write(query, batch, batch_size=batch_size)

        # Create BiomarkerProfile nodes
        if self.biomarker_profiles:
            profile_query = """
            UNWIND $batch as profile
            MERGE (bp:BiomarkerProfile {patient_id: profile.patient_id})
            SET bp.risk_score = profile.risk_score,
                bp.atn_status = profile.atn_status,
                bp.csf_count = profile.csf_count,
                bp.blood_count = profile.blood_count,
                bp.genetic_count = profile.genetic_count,
                bp.created_at = datetime()
            """

            profile_data = []
            for profile in self.biomarker_profiles:
                profile_data.append({
                    'patient_id': profile['patient_id'],
                    'risk_score': profile['risk_score'],
                    'atn_status': profile['atn_status']['profile'],
                    'csf_count': len(profile['csf_markers']),
                    'blood_count': len(profile['blood_markers']),
                    'genetic_count': len(profile['genetic_markers'])
                })

            self.connector.batch_write(profile_query, profile_data, batch_size=500)

    def _create_biomarker_relationships(self):
        """Create biomarker relationships"""
        logger.info("Creating biomarker relationships...")

        queries = [
            # Link biomarkers to patients
            """
            MATCH (b:Biomarker)
            WHERE b.patient_id IS NOT NULL
            MATCH (p:Patient {ptid: b.patient_id})
            MERGE (p)-[:HAS_BIOMARKER]->(b)
            """,

            # Link biomarkers to visits
            """
            MATCH (b:Biomarker)
            WHERE b.visit_id IS NOT NULL
            MATCH (v:Visit {visit_id: b.visit_id})
            MERGE (v)-[:HAS_BIOMARKER]->(b)
            """,

            # Link profiles to patients
            """
            MATCH (bp:BiomarkerProfile)
            MATCH (p:Patient {ptid: bp.patient_id})
            MERGE (p)-[:HAS_BIOMARKER_PROFILE]->(bp)
            """
        ]

        for query in queries:
            try:
                self.connector.execute_write_transaction(query)
            except Exception as e:
                logger.warning(f"Failed to create some relationships: {e}")

        logger.info("✅ Biomarker relationships created")


def execute_biomarker_analysis_fixed(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                                     table_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """Execute fixed biomarker analysis"""
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        analyzer = ComprehensiveBiomarkerAnalyzer(connector, table_data)
        results = analyzer.execute()
        return results
    except Exception as e:
        logger.error(f"Biomarker analysis failed: {e}")
        raise
    finally:
        connector.close()