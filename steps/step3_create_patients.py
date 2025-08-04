"""
Step 3: Create Patient Records
Creates patient nodes and associated visit nodes
"""

import logging
import pandas as pd
from typing import Dict, List, Any, Optional
from datetime import datetime
import re

from models.entities import Patient, Visit
from utils.batch_processor import DataValidator
from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


class PatientCreator:
    """Create patient and visit records from table data"""

    def __init__(self, connector: Neo4jConnector, table_data: Dict[str, pd.DataFrame]):
        self.connector = connector
        self.table_data = table_data
        self.patients = {}
        self.visits = {}

    def execute(self) -> Dict[str, Any]:
        """
        Create patient and visit records

        Returns:
            Dictionary with creation results
        """
        results = {
            'patients_created': 0,
            'visits_created': 0,
            'errors': []
        }

        # Extract patient records
        logger.info("Extracting patient records from tables...")
        self._extract_patients()

        # Extract visit records
        logger.info("Extracting visit records...")
        self._extract_visits()

        # Insert into Neo4j
        logger.info("Inserting patients into Neo4j...")
        results['patients_created'] = self._insert_patients()

        logger.info("Inserting visits into Neo4j...")
        results['visits_created'] = self._insert_visits()

        # Create patient-visit relationships
        logger.info("Creating patient-visit relationships...")
        self._create_patient_visit_relationships()

        return results

    def _extract_patients(self) -> None:
        """Extract unique patient records from tables"""
        # Primary demographic tables
        demo_tables = ['PTDEMOG', 'ARM', 'INCLUSIO']

        # Find main demographic table
        main_table = None
        for table_name in demo_tables:
            if table_name in self.table_data:
                main_table = self.table_data[table_name]
                break

        if main_table is None:
            # Fallback: use any table with patient info
            for table_name, df in self.table_data.items():
                if 'PTID' in df.columns or 'RID' in df.columns:
                    main_table = df
                    break

        if main_table is None:
            raise ValueError("No table found with patient identifiers")

        # Group by patient
        patient_groups = {}
        if 'PTID' in main_table.columns:
            patient_groups = main_table.groupby('PTID')
        elif 'RID' in main_table.columns:
            patient_groups = main_table.groupby('RID')

        # Process each patient
        for patient_id, group in patient_groups:
            # Get first row for baseline data
            row = group.iloc[0]

            # Create patient object
            patient = self._create_patient_from_row(patient_id, row)

            # Enhance with data from other tables
            self._enhance_patient_data(patient)

            self.patients[patient.ptid] = patient

        logger.info(f"Extracted {len(self.patients)} unique patients")

    def _create_patient_from_row(self, patient_id: str, row: pd.Series) -> Patient:
        """Create patient object from table row"""
        # Extract basic info
        ptid = str(row.get('PTID', patient_id)).strip()
        rid = str(row.get('RID', '')).strip()

        # Demographics
        gender = self._extract_gender(row)
        age_baseline = DataValidator.clean_numeric(row.get('AGE', row.get('PBAGE', None)))
        education = DataValidator.clean_numeric(row.get('PTEDUCAT', row.get('EDUCATION', None)))

        # Create patient
        patient = Patient(
            ptid=ptid,
            rid=rid,
            gender=gender,
            age_at_baseline=age_baseline,
            education_years=int(education) if education else None
        )

        # Add all demographic fields
        demo_fields = ['PTRACCAT', 'PTETHCAT', 'PTMARRY', 'SITE', 'VISCODE',
                       'COLPROT', 'ORIGPROT', 'FLDSTRENG']

        for field in demo_fields:
            if field in row and pd.notna(row[field]):
                patient.demographic_data[field] = DataValidator.clean_string(row[field])

        return patient

    def _extract_gender(self, row: pd.Series) -> Optional[str]:
        """Extract and standardize gender"""
        gender_fields = ['PTGENDER', 'SEX', 'GENDER']

        for field in gender_fields:
            if field in row and pd.notna(row[field]):
                value = str(row[field]).strip().upper()
                if value in ['M', 'MALE', '1']:
                    return 'M'
                elif value in ['F', 'FEMALE', '2']:
                    return 'F'

        return None

    def _enhance_patient_data(self, patient: Patient) -> None:
        """Enhance patient with data from other tables"""
        # APOE genotype
        if 'APOERES' in self.table_data:
            apoe_df = self.table_data['APOERES']
            patient_apoe = apoe_df[apoe_df['PTID'] == patient.ptid]

            if not patient_apoe.empty:
                row = patient_apoe.iloc[0]
                allele1 = row.get('APGEN1', '')
                allele2 = row.get('APGEN2', '')
                if allele1 and allele2:
                    patient.apoe_genotype = f"E{allele1}/E{allele2}"

        # Baseline diagnosis
        if 'DXSUM' in self.table_data:
            dx_df = self.table_data['DXSUM']
            baseline_dx = dx_df[(dx_df['PTID'] == patient.ptid) &
                                (dx_df['VISCODE'].str.lower() == 'bl')]

            if not baseline_dx.empty:
                dx_code = baseline_dx.iloc[0].get('DIAGNOSIS', '')
                patient.clinical_data['baseline_diagnosis'] = self._map_diagnosis_code(dx_code)

        # Add source tables
        for table_name, df in self.table_data.items():
            if 'PTID' in df.columns and patient.ptid in df['PTID'].values:
                patient.source_tables.append(table_name)

    def _map_diagnosis_code(self, code: Any) -> str:
        """Map diagnosis code to text"""
        if pd.isna(code):
            return 'Unknown'

        code = str(code).strip()
        mapping = {
            '1': 'CN',  # Cognitively Normal
            '2': 'MCI',  # Mild Cognitive Impairment
            '3': 'AD',  # Alzheimer's Disease
            '4': 'SMC',  # Subjective Memory Concern
            '5': 'EMCI',  # Early MCI
            '6': 'LMCI',  # Late MCI
            'CN': 'CN',
            'MCI': 'MCI',
            'AD': 'AD',
            'Dementia': 'AD'
        }

        return mapping.get(code, f'Other_{code}')

    def _extract_visits(self) -> None:
        """Extract visit records for all patients"""
        # Tables that contain visit information
        visit_tables = ['DXSUM', 'MMSE', 'CDR', 'ADAS', 'BIOMARK', 'VITALS']

        all_visits = {}

        for table_name in visit_tables:
            if table_name not in self.table_data:
                continue

            df = self.table_data[table_name]

            # Must have patient ID and visit code
            if 'PTID' not in df.columns or 'VISCODE' not in df.columns:
                continue

            # Group by patient and visit
            for (ptid, viscode), group in df.groupby(['PTID', 'VISCODE']):
                if ptid not in self.patients:
                    continue

                visit_key = f"{ptid}_{viscode}"

                if visit_key not in all_visits:
                    # Create new visit
                    visit = self._create_visit(ptid, viscode, group.iloc[0])
                    all_visits[visit_key] = visit
                else:
                    # Enhance existing visit
                    self._enhance_visit(all_visits[visit_key], group.iloc[0])

        self.visits = all_visits
        logger.info(f"Extracted {len(self.visits)} visits")

    def _create_visit(self, ptid: str, viscode: str, row: pd.Series) -> Visit:
        """Create visit object"""
        visit_id = f"{ptid}_{viscode}"

        # Convert viscode to months
        months = self._viscode_to_months(viscode)

        # Determine visit type
        visit_type = 'baseline' if viscode.lower() in ['bl', 'sc'] else 'follow-up'

        # Extract visit date if available
        visit_date = None
        date_fields = ['EXAMDATE', 'VISITDATE', 'USERDATE']
        for field in date_fields:
            if field in row and pd.notna(row[field]):
                visit_date = str(row[field])
                break

        return Visit(
            visit_id=visit_id,
            patient_id=ptid,
            viscode=viscode,
            months_from_baseline=months,
            visit_date=visit_date,
            visit_type=visit_type
        )

    def _viscode_to_months(self, viscode: str) -> int:
        """Convert visit code to months from baseline"""
        viscode = viscode.lower().strip()

        if viscode in ['bl', 'baseline', 'sc', 'screening']:
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

        return 0

    def _enhance_visit(self, visit: Visit, row: pd.Series) -> None:
        """Enhance visit with additional data"""
        # Update visit date if not set
        if not visit.visit_date:
            date_fields = ['EXAMDATE', 'VISITDATE', 'USERDATE']
            for field in date_fields:
                if field in row and pd.notna(row[field]):
                    visit.visit_date = str(row[field])
                    break

    def _insert_patients(self) -> int:
        """Insert patient nodes into Neo4j"""
        patient_data = [p.to_dict() for p in self.patients.values()]

        query = """
        UNWIND $batch as patient
        MERGE (p:Patient {ptid: patient.ptid})
        SET p += patient,
            p.gender = patient.gender,
            p.age_at_baseline = patient.age_at_baseline,
            p.education_years = patient.education_years,
            p.apoe_genotype = patient.apoe_genotype,
            p.created_at = patient.created_at
        """

        return self.connector.batch_write(query, patient_data, batch_size=1000)

    def _insert_visits(self) -> int:
        """Insert visit nodes into Neo4j"""
        visit_data = [v.to_dict() for v in self.visits.values()]

        query = """
        UNWIND $batch as visit
        MERGE (v:Visit {visit_id: visit.visit_id})
        SET v += visit,
            v.patient_id = visit.patient_id,
            v.viscode = visit.viscode,
            v.months_from_baseline = visit.months_from_baseline,
            v.visit_date = visit.visit_date,
            v.visit_type = visit.visit_type,
            v.created_at = visit.created_at
        """

        return self.connector.batch_write(query, visit_data, batch_size=2000)

    def _create_patient_visit_relationships(self) -> None:
        """Create relationships between patients and visits"""
        query = """
        MATCH (p:Patient {ptid: $patient_id})
        MATCH (v:Visit {visit_id: $visit_id})
        MERGE (p)-[:HAS_VISIT]->(v)
        """

        relationships = []
        for visit in self.visits.values():
            relationships.append({
                'patient_id': visit.patient_id,
                'visit_id': visit.visit_id
            })

        # Create relationships in batches
        batch_query = """
        UNWIND $batch as rel
        MATCH (p:Patient {ptid: rel.patient_id})
        MATCH (v:Visit {visit_id: rel.visit_id})
        MERGE (p)-[:HAS_VISIT]->(v)
        """

        self.connector.batch_write(batch_query, relationships, batch_size=5000)

        # Create temporal relationships between visits
        self._create_temporal_relationships()

    def _create_temporal_relationships(self) -> None:
        """Create temporal relationships between visits"""
        query = """
        MATCH (p:Patient)
        MATCH (p)-[:HAS_VISIT]->(v1:Visit)
        MATCH (p)-[:HAS_VISIT]->(v2:Visit)
        WHERE v1.months_from_baseline < v2.months_from_baseline
        WITH v1, v2, v2.months_from_baseline - v1.months_from_baseline as months_delta
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