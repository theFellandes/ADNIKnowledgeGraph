"""
Step 4: Extract Family Member Data (ENHANCED)
Extracts family history with flexible column discovery and quality logging
"""

import logging
import pandas as pd
from typing import Dict, List, Any, Optional
import re
import uuid

from models.entities import FamilyMember
from utils.neo4j_connector import Neo4jConnector
from utils.batch_processor import DataValidator
from utils.data_quality_logger import get_quality_logger, log_extraction_issue

logger = logging.getLogger(__name__)


class FamilyExtractor:
    """Extract family member data from ADNI tables with enhanced discovery"""

    def __init__(self, connector: Neo4jConnector, table_data: Dict[str, pd.DataFrame]):
        self.connector = connector
        self.table_data = table_data
        self.family_members = []
        self.quality_logger = get_quality_logger()

        # Log available tables
        family_tables = [t for t in table_data.keys() if any(
            pattern in t.upper() for pattern in ['FAM', 'FHQ', 'FAMILY']
        )]
        logger.info(f"Available family-related tables: {family_tables}")

    def execute(self) -> Dict[str, Any]:
        """
        Extract and create family member records with enhanced logging

        Returns:
            Dictionary with extraction results
        """
        results = {
            'family_members_created': 0,
            'relationships_created': 0,
            'errors': [],
            'tables_processed': []
        }

        # Extract from family history tables
        logger.info("Extracting family member data...")

        # Process each potential family table
        family_tables = {
            'FAMHXPAR': self._process_parent_table_enhanced,
            'FAMHXSIB': self._process_sibling_table_enhanced,
            'FHQ': self._process_family_questionnaire_enhanced
        }

        for table_name, process_func in family_tables.items():
            if table_name in self.table_data:
                logger.info(f"Processing {table_name} table...")
                try:
                    df = self.table_data[table_name]
                    logger.info(f"  Table shape: {df.shape}")
                    logger.info(f"  Columns: {list(df.columns)[:20]}")  # First 20 columns

                    count_before = len(self.family_members)
                    process_func(df, table_name)
                    count_after = len(self.family_members)

                    extracted = count_after - count_before
                    logger.info(f"  Extracted {extracted} family members from {table_name}")
                    results['tables_processed'].append(table_name)

                except Exception as e:
                    logger.error(f"Error processing {table_name}: {e}")
                    results['errors'].append(f"{table_name}: {str(e)}")
                    log_extraction_issue('Step4_Family', table_name, str(e))
            else:
                logger.warning(f"Table {table_name} not found in loaded data")

        # Also check for family data in other tables
        self._extract_from_other_tables()

        # Deduplicate
        before_dedup = len(self.family_members)
        self._deduplicate_family_members()
        after_dedup = len(self.family_members)
        logger.info(f"Deduplicated from {before_dedup} to {after_dedup} family members")

        if len(self.family_members) == 0:
            logger.warning("⚠️ No family members extracted - investigating why...")
            self._diagnose_extraction_issues()

        # Insert into Neo4j
        logger.info("Inserting family members into Neo4j...")
        results['family_members_created'] = self._insert_family_members()

        # Create relationships
        logger.info("Creating family relationships...")
        results['relationships_created'] = self._create_family_relationships()

        return results

    def _process_parent_table_enhanced(self, df: pd.DataFrame, table_name: str) -> None:
        """Process parent family history table with flexible column discovery"""
        logger.info(f"  Analyzing {table_name} structure...")

        # Find ID columns
        id_columns = self._find_id_columns(df)
        if not id_columns:
            logger.warning(f"  No ID columns found in {table_name}")
            log_extraction_issue('Step4_Family', table_name, 'No patient ID columns found',
                               {'columns': list(df.columns)[:10]})
            return

        ptid_col = id_columns[0]
        logger.info(f"  Using ID column: {ptid_col}")

        # Look for dementia/AD columns
        dementia_columns = self._find_dementia_columns(df)
        logger.info(f"  Found dementia-related columns: {dementia_columns}")

        # Process each row
        extracted_count = 0
        for _, row in df.iterrows():
            ptid = str(row.get(ptid_col, '')).strip()
            if not ptid or pd.isna(row[ptid_col]):
                continue

            # Check mother columns
            mother_cols = [col for col in df.columns if any(
                term in col.upper() for term in ['MOM', 'MOTHER', 'MOMDEM', 'NACCMOM']
            )]

            for col in mother_cols:
                if self._indicates_dementia_flexible(row.get(col)):
                    age_col = self._find_related_age_column(df.columns, col)
                    age = self._extract_age(row, age_col) if age_col else None

                    mother = self._create_family_member(
                        patient_id=ptid,
                        relationship_type='parent',
                        gender='F',
                        has_dementia=True,
                        age_at_onset=age,
                        properties={'parent_type': 'mother', 'source_column': col}
                    )
                    self.family_members.append(mother)
                    extracted_count += 1
                    break

            # Check father columns
            father_cols = [col for col in df.columns if any(
                term in col.upper() for term in ['DAD', 'FATHER', 'DADDEM', 'NACCDAD']
            )]

            for col in father_cols:
                if self._indicates_dementia_flexible(row.get(col)):
                    age_col = self._find_related_age_column(df.columns, col)
                    age = self._extract_age(row, age_col) if age_col else None

                    father = self._create_family_member(
                        patient_id=ptid,
                        relationship_type='parent',
                        gender='M',
                        has_dementia=True,
                        age_at_onset=age,
                        properties={'parent_type': 'father', 'source_column': col}
                    )
                    self.family_members.append(father)
                    extracted_count += 1
                    break

        logger.info(f"  Extracted {extracted_count} parents with dementia from {table_name}")

    def _process_sibling_table_enhanced(self, df: pd.DataFrame, table_name: str) -> None:
        """Process sibling family history table with flexible discovery"""
        logger.info(f"  Analyzing {table_name} structure...")

        # Find ID columns
        id_columns = self._find_id_columns(df)
        if not id_columns:
            logger.warning(f"  No ID columns found in {table_name}")
            return

        ptid_col = id_columns[0]

        # Look for sibling columns
        sibling_patterns = ['SIB', 'BROTHER', 'SISTER', 'SIBLING']
        sibling_cols = []

        for col in df.columns:
            if any(pattern in col.upper() for pattern in sibling_patterns):
                sibling_cols.append(col)

        logger.info(f"  Found sibling columns: {sibling_cols[:10]}")

        extracted_count = 0
        for _, row in df.iterrows():
            ptid = str(row.get(ptid_col, '')).strip()
            if not ptid:
                continue

            for col in sibling_cols:
                if self._indicates_dementia_flexible(row.get(col)):
                    sibling = self._create_family_member(
                        patient_id=ptid,
                        relationship_type='sibling',
                        has_dementia=True,
                        properties={'source_column': col}
                    )
                    self.family_members.append(sibling)
                    extracted_count += 1

        logger.info(f"  Extracted {extracted_count} siblings with dementia from {table_name}")

    def _process_family_questionnaire_enhanced(self, df: pd.DataFrame, table_name: str) -> None:
        """Process general family history questionnaire with enhanced discovery"""
        logger.info(f"  Analyzing {table_name} structure...")

        # Find ID columns
        id_columns = self._find_id_columns(df)
        if not id_columns:
            logger.warning(f"  No ID columns found in {table_name}")
            return

        ptid_col = id_columns[0]

        # Look for any family/dementia related columns
        family_keywords = ['FAM', 'FAMILY', 'RELATIVE', 'PARENT', 'MOTHER', 'FATHER',
                          'MOM', 'DAD', 'SIBLING', 'BROTHER', 'SISTER', 'CHILD']
        dementia_keywords = ['DEM', 'ALZH', 'AD', 'MEMORY', 'COGNITIVE']

        relevant_cols = []
        for col in df.columns:
            col_upper = col.upper()
            if (any(fk in col_upper for fk in family_keywords) and
                any(dk in col_upper for dk in dementia_keywords)):
                relevant_cols.append(col)

        logger.info(f"  Found relevant columns: {relevant_cols}")

        # Also check for numeric columns that might be coded (0/1, 1/2, etc.)
        numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
        for col in numeric_cols:
            if any(term in col.upper() for term in family_keywords):
                relevant_cols.append(col)

        extracted_count = 0
        for _, row in df.iterrows():
            ptid = str(row.get(ptid_col, '')).strip()
            if not ptid:
                continue

            for col in relevant_cols:
                value = row.get(col)
                if self._indicates_dementia_flexible(value):
                    relationship = self._infer_relationship_from_column(col)

                    member = self._create_family_member(
                        patient_id=ptid,
                        relationship_type=relationship,
                        has_dementia=True,
                        properties={'source_column': col, 'value': str(value)}
                    )
                    self.family_members.append(member)
                    extracted_count += 1

        logger.info(f"  Extracted {extracted_count} family members from {table_name}")

    def _find_id_columns(self, df: pd.DataFrame) -> List[str]:
        """Find patient ID columns in dataframe"""
        id_patterns = ['PTID', 'RID', 'SUBJID', 'SUBJECT', 'ID', 'PATIENT']
        found_cols = []

        for col in df.columns:
            if any(pattern in col.upper() for pattern in id_patterns):
                # Check if it has valid patient IDs
                sample = df[col].dropna().head(5)
                if len(sample) > 0:
                    found_cols.append(col)

        return found_cols

    def _find_dementia_columns(self, df: pd.DataFrame) -> List[str]:
        """Find columns that might contain dementia information"""
        dementia_patterns = ['DEM', 'ALZH', 'AD', 'MEMORY', 'COGNITIVE', 'IMPAIR']
        found_cols = []

        for col in df.columns:
            col_upper = col.upper()
            if any(pattern in col_upper for pattern in dementia_patterns):
                found_cols.append(col)

        return found_cols

    def _indicates_dementia_flexible(self, value: Any) -> bool:
        """Check if value indicates dementia using flexible matching"""
        if pd.isna(value):
            return False

        # Handle numeric codes
        if isinstance(value, (int, float)):
            # Common codings: 1=Yes, 2=No or 0=No, 1=Yes
            return int(value) == 1

        # Handle string values
        str_val = str(value).strip().upper()

        # Direct positive indicators
        positive_indicators = ['1', 'YES', 'Y', 'TRUE', 'T', '1.0']
        if str_val in positive_indicators:
            return True

        # Check for dementia keywords
        dementia_terms = ['DEMENTIA', 'ALZHEIMER', 'AD', 'MEMORY', 'COGNITIVE', 'IMPAIR']
        return any(term in str_val for term in dementia_terms)

    def _find_related_age_column(self, columns: List[str], base_col: str) -> Optional[str]:
        """Find age column related to a dementia column"""
        base_upper = base_col.upper()

        # Look for age columns with similar prefix
        for col in columns:
            col_upper = col.upper()
            if 'AGE' in col_upper:
                # Check if it's related to the same family member
                if 'MOM' in base_upper and 'MOM' in col_upper:
                    return col
                elif 'DAD' in base_upper and 'DAD' in col_upper:
                    return col
                elif 'MOTHER' in base_upper and 'MOTHER' in col_upper:
                    return col
                elif 'FATHER' in base_upper and 'FATHER' in col_upper:
                    return col

        return None

    def _infer_relationship_from_column(self, column_name: str) -> str:
        """Infer family relationship type from column name"""
        col_upper = column_name.upper()

        if any(term in col_upper for term in ['MOTHER', 'MOM']):
            return 'parent'
        elif any(term in col_upper for term in ['FATHER', 'DAD']):
            return 'parent'
        elif any(term in col_upper for term in ['SIBLING', 'BROTHER', 'SISTER', 'SIB']):
            return 'sibling'
        elif any(term in col_upper for term in ['CHILD', 'SON', 'DAUGHTER']):
            return 'child'
        else:
            return 'other'

    def _extract_from_other_tables(self) -> None:
        """Look for family history in other clinical tables"""
        # Check all tables for family-related columns
        for table_name, df in self.table_data.items():
            # Skip if already processed
            if table_name in ['FAMHXPAR', 'FAMHXSIB', 'FHQ']:
                continue

            # Look for family columns
            family_cols = []
            for col in df.columns:
                col_upper = col.upper()
                if (('FAM' in col_upper or 'FAMILY' in col_upper or 'RELATIVE' in col_upper) and
                    any(term in col_upper for term in ['DEM', 'AD', 'ALZ', 'HISTORY'])):
                    family_cols.append(col)

            if family_cols:
                logger.info(f"Found family columns in {table_name}: {family_cols}")
                self._process_generic_family_columns(df, table_name, family_cols)

    def _process_generic_family_columns(self, df: pd.DataFrame, table_name: str, family_cols: List[str]):
        """Process family-related columns from any table"""
        id_columns = self._find_id_columns(df)
        if not id_columns:
            return

        ptid_col = id_columns[0]
        extracted_count = 0

        for _, row in df.iterrows():
            ptid = str(row.get(ptid_col, '')).strip()
            if not ptid:
                continue

            for col in family_cols:
                if self._indicates_dementia_flexible(row.get(col)):
                    relationship = self._infer_relationship_from_column(col)

                    member = self._create_family_member(
                        patient_id=ptid,
                        relationship_type=relationship,
                        has_dementia=True,
                        properties={'source_table': table_name, 'source_column': col}
                    )
                    self.family_members.append(member)
                    extracted_count += 1

        if extracted_count > 0:
            logger.info(f"  Extracted {extracted_count} family members from {table_name}")

    def _diagnose_extraction_issues(self) -> None:
        """Diagnose why no family members were extracted"""
        logger.warning("Diagnosing family extraction issues...")

        # Check FAMHXPAR
        if 'FAMHXPAR' in self.table_data:
            df = self.table_data['FAMHXPAR']
            logger.info(f"  FAMHXPAR shape: {df.shape}")
            logger.info(f"  FAMHXPAR columns: {list(df.columns)}")

            # Check for any non-null values
            for col in df.columns:
                non_null = df[col].notna().sum()
                if non_null > 0:
                    unique_vals = df[col].dropna().unique()[:5]
                    logger.info(f"    {col}: {non_null} non-null values, samples: {unique_vals}")

        # Log to quality logger
        log_extraction_issue(
            'Step4_Family',
            'All family tables',
            'No family members extracted - possible column name mismatch or all null values',
            {'tables_checked': list(self.table_data.keys())}
        )

    def _create_family_member(self, patient_id: str, relationship_type: str,
                            gender: Optional[str] = None,
                            has_dementia: Optional[bool] = None,
                            dementia_type: Optional[str] = None,
                            age_at_onset: Optional[int] = None,
                            properties: Optional[Dict] = None) -> FamilyMember:
        """Create a family member object"""
        member_id = f"fm_{patient_id}_{relationship_type}_{uuid.uuid4().hex[:6]}"

        return FamilyMember(
            member_id=member_id,
            patient_id=patient_id,
            relationship_type=relationship_type,
            gender=gender,
            has_dementia=has_dementia,
            dementia_type=dementia_type,
            age_at_onset=age_at_onset,
            properties=properties or {}
        )

    def _extract_age(self, row: pd.Series, column: str) -> Optional[int]:
        """Extract age from column"""
        if not column or column not in row:
            return None

        value = row[column]
        if pd.isna(value):
            return None

        try:
            age = int(float(value))
            if 0 < age < 120:  # Reasonable age range
                return age
        except:
            pass

        return None

    def _deduplicate_family_members(self) -> None:
        """Remove duplicate family members"""
        unique_members = {}

        for member in self.family_members:
            # Create unique key
            key = f"{member.patient_id}_{member.relationship_type}_{member.gender or 'U'}"

            if key not in unique_members:
                unique_members[key] = member
            else:
                # Merge information
                existing = unique_members[key]
                if member.has_dementia and not existing.has_dementia:
                    existing.has_dementia = True
                if member.age_at_onset and not existing.age_at_onset:
                    existing.age_at_onset = member.age_at_onset
                existing.properties.update(member.properties)

        self.family_members = list(unique_members.values())
        logger.info(f"Deduplicated to {len(self.family_members)} unique family members")

    def _insert_family_members(self) -> int:
        """Insert family member nodes into Neo4j"""
        if not self.family_members:
            logger.warning("No family members to insert")
            return 0

        member_data = [m.to_dict() for m in self.family_members]

        query = """
        UNWIND $batch as member
        MERGE (fm:FamilyMember {member_id: member.member_id})
        SET fm += member,
            fm.patient_id = member.patient_id,
            fm.relationship_type = member.relationship_type,
            fm.gender = member.gender,
            fm.has_dementia = member.has_dementia,
            fm.dementia_type = member.dementia_type,
            fm.age_at_onset = member.age_at_onset,
            fm.created_at = member.created_at
        """

        return self.connector.batch_write(query, member_data, batch_size=2000)

    def _create_family_relationships(self) -> int:
        """Create relationships between patients and family members"""
        if not self.family_members:
            return 0

        relationships = []

        for member in self.family_members:
            relationships.append({
                'patient_id': member.patient_id,
                'member_id': member.member_id,
                'relationship_type': member.relationship_type
            })

        # Base relationship
        query = """
        UNWIND $batch as rel
        MATCH (p:Patient {ptid: rel.patient_id})
        MATCH (fm:FamilyMember {member_id: rel.member_id})
        MERGE (p)-[:HAS_FAMILY_MEMBER]->(fm)
        """

        return self.connector.batch_write(query, relationships, batch_size=5000)


def execute_family_extraction(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                            table_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """
    Main execution function for family extraction

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
        extractor = FamilyExtractor(connector, table_data)
        results = extractor.execute()

        logger.info(f"✅ Created {results['family_members_created']} family members")
        return results

    finally:
        connector.close()