"""
Step 3: Create Patient Records (FIXED & OPTIMIZED)
Creates patient nodes and associated visit nodes with improved performance and error handling
"""

import logging
import pandas as pd
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
import re
import numpy as np
from collections import defaultdict

from models.entities import Patient, Visit
from utils.batch_processor import DataValidator
from utils.neo4j_connector import Neo4jConnector


logger = logging.getLogger(__name__)


class PatientCreator:
    """Create patient and visit records from table data with optimized performance"""

    def __init__(self, connector: Neo4jConnector, table_data: Dict[str, pd.DataFrame]):
        self.connector = connector
        self.table_data = table_data
        self.patients = {}
        self.visits = {}

        # Pre-compute patient data for optimization
        self.patient_data_cache = defaultdict(dict)
        self._build_patient_cache()

    def _build_patient_cache(self) -> None:
        """Pre-build cache of patient data for faster lookup"""
        logger.info("Building patient data cache for optimization...")

        # Build RID to PTID mapping first
        self.rid_to_ptid = {}
        for table_name, df in self.table_data.items():
            if 'RID' in df.columns and 'PTID' in df.columns:
                temp_map = df[['RID', 'PTID']].dropna().drop_duplicates()
                for _, row in temp_map.iterrows():
                    rid_str = str(row['RID']).strip()
                    ptid_str = str(row['PTID']).strip()
                    if DataValidator.validate_patient_id(ptid_str):
                        self.rid_to_ptid[rid_str] = ptid_str

        # Cache demographic data
        demographic_tables = ['PTDEMOG', 'DEMO', 'DEMOGRAPHICS']
        for table_pattern in demographic_tables:
            for table_name, df in self.table_data.items():
                if table_pattern in table_name.upper():
                    self._cache_table_data(df, table_name, is_demographic=True)

        # Cache APOE data
        apoe_tables = ['APOERES', 'APOE', 'GENETIC']
        for table_pattern in apoe_tables:
            for table_name, df in self.table_data.items():
                if table_pattern in table_name.upper():
                    self._cache_apoe_data(df, table_name)

    def _cache_table_data(self, df: pd.DataFrame, table_name: str, is_demographic: bool = False) -> None:
        """Cache data from a specific table"""
        id_columns = ['PTID', 'RID', 'SUBJID', 'SUBJECT']

        for id_col in id_columns:
            if id_col not in df.columns:
                continue

            for _, row in df.iterrows():
                patient_id = str(row[id_col]).strip()

                # Normalize RID to PTID
                if id_col == 'RID':
                    patient_id = self.rid_to_ptid.get(patient_id, patient_id)

                if not patient_id or not DataValidator.validate_patient_id(patient_id):
                    continue

                if patient_id not in self.patient_data_cache:
                    self.patient_data_cache[patient_id] = {}

                # Cache demographic fields
                if is_demographic:
                    for field in ['PTGENDER', 'SEX', 'GENDER', 'PTSEX']:
                        if field in row and pd.notna(row[field]):
                            self.patient_data_cache[patient_id]['gender'] = self._extract_gender_value(row[field])

                    for field in ['AGE', 'PBAGE', 'AGE_AT_BASELINE']:
                        if field in row and pd.notna(row[field]):
                            self.patient_data_cache[patient_id]['age'] = DataValidator.clean_numeric(row[field])

                    for field in ['PTEDUCAT', 'EDUCATION', 'EDUC']:
                        if field in row and pd.notna(row[field]):
                            self.patient_data_cache[patient_id]['education'] = DataValidator.clean_numeric(row[field])

                # Track source table
                if 'source_tables' not in self.patient_data_cache[patient_id]:
                    self.patient_data_cache[patient_id]['source_tables'] = set()
                self.patient_data_cache[patient_id]['source_tables'].add(table_name)

    def _cache_apoe_data(self, df: pd.DataFrame, table_name: str) -> None:
        """Cache APOE genotype data"""
        id_columns = ['PTID', 'RID', 'SUBJID']

        for id_col in id_columns:
            if id_col not in df.columns:
                continue

            for _, row in df.iterrows():
                patient_id = str(row[id_col]).strip()

                if id_col == 'RID':
                    patient_id = self.rid_to_ptid.get(patient_id, patient_id)

                if not patient_id or not DataValidator.validate_patient_id(patient_id):
                    continue

                # Extract APOE alleles
                allele1 = str(row.get('APGEN1', '')).strip() if 'APGEN1' in row else ''
                allele2 = str(row.get('APGEN2', '')).strip() if 'APGEN2' in row else ''

                if allele1 and allele2:
                    apoe_genotype = f"E{allele1}/E{allele2}"
                    self.patient_data_cache[patient_id]['apoe_genotype'] = apoe_genotype

    def execute(self) -> Dict[str, Any]:
        """
        Create patient and visit records with optimized performance

        Returns:
            Dictionary with creation results
        """
        results = {
            'patients_created': 0,
            'visits_created': 0,
            'errors': []
        }

        # Extract patient records (now much faster with cache)
        logger.info("Extracting patient records from cache...")
        self._extract_patients_optimized()

        # Extract visit records
        logger.info("Extracting visit records...")
        self._extract_visits_comprehensive()

        # Insert into Neo4j with better error handling
        logger.info("Inserting patients into Neo4j...")
        results['patients_created'] = self._insert_patients_optimized()

        logger.info("Inserting visits into Neo4j...")
        results['visits_created'] = self._insert_visits()

        # Create patient-visit relationships
        logger.info("Creating patient-visit relationships...")
        self._create_patient_visit_relationships()

        return results

    def _extract_patients_optimized(self) -> None:
        """Extract unique patient records using pre-built cache"""
        # Get all unique patient IDs
        all_patient_ids = set()

        # From cache
        all_patient_ids.update(self.patient_data_cache.keys())

        # Additional scan for any missed IDs
        id_columns = ['PTID', 'RID', 'SUBJID', 'SUBJECT', 'PATIENT_ID']
        for table_name, df in self.table_data.items():
            for id_col in id_columns:
                if id_col in df.columns:
                    for id_val in df[id_col].dropna().unique():
                        id_str = str(id_val).strip()

                        # Normalize RID to PTID
                        if id_col == 'RID':
                            id_str = self.rid_to_ptid.get(id_str, id_str)

                        if id_str and DataValidator.validate_patient_id(id_str):
                            all_patient_ids.add(id_str)

        logger.info(f"Found {len(all_patient_ids)} unique patient IDs")

        # Create patient records using cached data
        for patient_id in all_patient_ids:
            patient = Patient(
                ptid=patient_id,
                rid=patient_id.split('_')[-1] if '_' in patient_id else patient_id
            )

            # Use cached data if available
            if patient_id in self.patient_data_cache:
                cached = self.patient_data_cache[patient_id]
                patient.gender = cached.get('gender')
                patient.age_at_baseline = cached.get('age')
                patient.education_years = int(cached['education']) if cached.get('education') else None
                patient.apoe_genotype = cached.get('apoe_genotype')
                patient.source_tables = list(cached.get('source_tables', []))

            self.patients[patient.ptid] = patient

        logger.info(f"Created {len(self.patients)} patient records")

    def _extract_gender_value(self, value: Any) -> Optional[str]:
        """Extract and standardize gender value"""
        if pd.isna(value):
            return None

        value_str = str(value).strip().upper()
        if value_str in ['M', 'MALE', '1', '1.0']:
            return 'M'
        elif value_str in ['F', 'FEMALE', '2', '2.0']:
            return 'F'

        return None

    def _extract_visits_comprehensive(self) -> None:
        """Extract visit records comprehensively from all tables"""
        visit_info = {}  # Key: (ptid, viscode), Value: visit data

        # Visit code columns to check
        viscode_columns = ['VISCODE', 'VISCODE2', 'VISIT', 'VISITNO', 'VISITCODE']

        # Process tables in parallel chunks for better performance
        for table_name, df in self.table_data.items():
            # Skip if no visit information
            viscode_col = None
            for vc in viscode_columns:
                if vc in df.columns:
                    viscode_col = vc
                    break

            if not viscode_col:
                continue

            # Find patient ID column
            ptid_col = None
            for pc in ['PTID', 'RID', 'SUBJID', 'SUBJECT']:
                if pc in df.columns:
                    ptid_col = pc
                    break

            if not ptid_col:
                continue

            # Vectorized extraction for better performance
            valid_mask = df[viscode_col].notna() & df[ptid_col].notna()
            valid_df = df[valid_mask]

            for _, row in valid_df.iterrows():
                ptid = str(row[ptid_col]).strip()
                viscode = str(row[viscode_col]).strip()

                # Normalize RID to PTID
                if ptid_col == 'RID':
                    ptid = self.rid_to_ptid.get(ptid, ptid)

                if not DataValidator.validate_patient_id(ptid):
                    continue

                # Normalize viscode
                viscode = self._normalize_viscode(viscode)
                visit_key = (ptid, viscode)

                if visit_key not in visit_info:
                    visit_info[visit_key] = {
                        'ptid': ptid,
                        'viscode': viscode,
                        'dates': [],
                        'sources': []
                    }

                # Collect visit dates
                date_cols = ['EXAMDATE', 'VISITDATE', 'USERDATE', 'SCANDATE', 'EXAMDT', 'VISDATE', 'DATE']
                for dc in date_cols:
                    if dc in row and pd.notna(row[dc]):
                        visit_info[visit_key]['dates'].append(str(row[dc]))

                visit_info[visit_key]['sources'].append(table_name)

        # Create visit objects
        for (ptid, viscode), info in visit_info.items():
            if ptid not in self.patients:
                continue

            visit_id = f"{ptid}_{viscode}"

            # Get best visit date
            visit_date = info['dates'][0] if info['dates'] else None

            # Convert viscode to months
            months = self._viscode_to_months(viscode)

            # Determine visit type
            visit_type = 'baseline' if viscode in ['bl', 'sc'] else 'follow-up'

            visit = Visit(
                visit_id=visit_id,
                patient_id=ptid,
                viscode=viscode,
                months_from_baseline=months,
                visit_date=visit_date,
                visit_type=visit_type
            )

            self.visits[visit_id] = visit

        logger.info(f"Extracted {len(self.visits)} visits from {len(visit_info)} unique patient-visit combinations")

    def _normalize_viscode(self, viscode: str) -> str:
        """Normalize visit code to standard format"""
        viscode = viscode.lower().strip()

        # Common mappings
        mappings = {
            'baseline': 'bl',
            'screening': 'sc',
            'scmri': 'sc',
            'month6': 'm06',
            'month12': 'm12',
            'month24': 'm24',
            'month36': 'm36',
            'month48': 'm48',
            'month60': 'm60',
            'month72': 'm72',
            'month84': 'm84',
            'month96': 'm96',
            'year1': 'm12',
            'year2': 'm24',
            'year3': 'm36',
            'year4': 'm48',
            'year5': 'm60'
        }

        # Apply mapping if exists
        if viscode in mappings:
            return mappings[viscode]

        # Clean up common patterns
        if viscode.startswith('month'):
            month_num = re.search(r'\d+', viscode)
            if month_num:
                return f"m{int(month_num.group()):02d}"

        if viscode.startswith('year'):
            year_num = re.search(r'\d+', viscode)
            if year_num:
                return f"m{int(year_num.group()) * 12:02d}"

        return viscode

    def _viscode_to_months(self, viscode: str) -> int:
        """Convert visit code to months from baseline"""
        viscode = viscode.lower().strip()

        if viscode in ['bl', 'baseline', 'sc', 'screening', 'scmri']:
            return 0

        # Month patterns (m06, m12, etc.)
        if viscode.startswith('m'):
            match = re.match(r'm(\d+)', viscode)
            if match:
                return int(match.group(1))

        # Year patterns (y1, y2, etc.)
        if viscode.startswith('y'):
            match = re.match(r'y(\d+)', viscode)
            if match:
                return int(match.group(1)) * 12

        # Try to extract any number
        numbers = re.findall(r'\d+', viscode)
        if numbers:
            return int(numbers[0])

        return 0

    def _insert_patients_optimized(self) -> int:
        """Insert patient nodes with proper RID handling"""
        patient_data = []

        for p in self.patients.values():
            data = p.to_dict()
            # Clean source_tables to remove duplicates
            data['source_tables'] = list(set(data['source_tables']))
            patient_data.append(data)

        # Fixed query that properly handles RID duplicates
        query = """
        UNWIND $batch AS patient
        MERGE (p:Patient {ptid: patient.ptid})
        ON CREATE SET 
            p.rid = patient.rid,
            p.gender = patient.gender,
            p.age_at_baseline = patient.age_at_baseline,
            p.education_years = patient.education_years,
            p.apoe_genotype = patient.apoe_genotype,
            p.source_tables = patient.source_tables,
            p.created_at = patient.created_at
        ON MATCH SET
            p.gender = COALESCE(p.gender, patient.gender),
            p.age_at_baseline = COALESCE(p.age_at_baseline, patient.age_at_baseline),
            p.education_years = COALESCE(p.education_years, patient.education_years),
            p.apoe_genotype = COALESCE(p.apoe_genotype, patient.apoe_genotype),
            p.source_tables = CASE 
                WHEN p.source_tables IS NULL THEN patient.source_tables
                ELSE p.source_tables + [x IN patient.source_tables WHERE NOT x IN p.source_tables]
            END
        """

        return self.connector.batch_write(query, patient_data, batch_size=1000)

    def _insert_visits(self) -> int:
        """Insert visit nodes into Neo4j"""
        visit_data = [v.to_dict() for v in self.visits.values()]

        query = """
        UNWIND $batch as visit
        MERGE (v:Visit {visit_id: visit.visit_id})
        SET v.patient_id = visit.patient_id,
            v.viscode = visit.viscode,
            v.months_from_baseline = visit.months_from_baseline,
            v.visit_date = visit.visit_date,
            v.visit_type = visit.visit_type,
            v.created_at = visit.created_at
        """

        return self.connector.batch_write(query, visit_data, batch_size=2000)

    def _create_patient_visit_relationships(self) -> None:
        """Create relationships between patients and visits"""
        batch_query = """
        UNWIND $batch as rel
        MATCH (p:Patient {ptid: rel.patient_id})
        MATCH (v:Visit {visit_id: rel.visit_id})
        MERGE (p)-[:HAS_VISIT]->(v)
        """

        relationships = [
            {'patient_id': visit.patient_id, 'visit_id': visit.visit_id}
            for visit in self.visits.values()
        ]

        self.connector.batch_write(batch_query, relationships, batch_size=5000)

        # Create temporal relationships
        self._create_temporal_relationships()

    def _create_temporal_relationships(self) -> None:
        """Create temporal relationships between visits"""
        query = """
        MATCH (p:Patient)
        MATCH (p)-[:HAS_VISIT]->(v1:Visit)
        MATCH (p)-[:HAS_VISIT]->(v2:Visit)
        WHERE v1.months_from_baseline < v2.months_from_baseline
        WITH v1, v2, v2.months_from_baseline - v1.months_from_baseline as months_delta
        ORDER BY v1.visit_id, months_delta
        WITH v1, COLLECT({v2: v2, delta: months_delta})[0] as next
        WHERE next IS NOT NULL
        WITH v1, next.v2 as v2, next.delta as months_delta
        MERGE (v1)-[:PRECEDES {months_delta: months_delta}]->(v2)
        """

        self.connector.execute_write_transaction(query)
        logger.info("Created temporal relationships between visits")


def execute_patient_creation(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                           table_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """
    Main execution function for patient creation

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Username
        neo4j_password: Password
        table_data: Loaded table data

    Returns:
        Creation results
    """
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        creator = PatientCreator(connector, table_data)
        results = creator.execute()

        logger.info(f"✅ Created {results['patients_created']} patients and {results['visits_created']} visits")
        return results

    finally:
        connector.close()


if __name__ == "__main__":
    # Test with sample data
    test_data = {
        'PTDEMOG': pd.DataFrame({
            'PTID': ['001_S_0001', '002_S_0002'],
            'RID': ['1', '2'],
            'PTGENDER': ['M', 'F'],
            'AGE': [75, 68]
        })
    }

    results = execute_patient_creation(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="your_password",
        table_data=test_data
    )
    print(f"Results: {results}")