"""
Step 4: Extract Family Member Data
Extracts family history and creates family member nodes
"""

import logging
import pandas as pd
from typing import Dict, List, Any, Optional
import re
import uuid

from models.entities import FamilyMember
from utils.neo4j_connector import Neo4jConnector
from utils.batch_processor import DataValidator

logger = logging.getLogger(__name__)


class FamilyExtractor:
    """Extract family member data from ADNI tables"""

    # Family relationship patterns
    RELATIONSHIP_PATTERNS = {
        'parent': ['MOTHER', 'FATHER', 'PARENT', 'MOM', 'DAD'],
        'sibling': ['SIBLING', 'BROTHER', 'SISTER', 'SIB'],
        'child': ['CHILD', 'SON', 'DAUGHTER'],
        'grandparent': ['GRANDMOTHER', 'GRANDFATHER', 'GRANDPARENT'],
        'other': ['AUNT', 'UNCLE', 'COUSIN', 'RELATIVE']
    }

    def __init__(self, connector: Neo4jConnector, table_data: Dict[str, pd.DataFrame]):
        self.connector = connector
        self.table_data = table_data
        self.family_members = []

    def execute(self) -> Dict[str, Any]:
        """
        Extract and create family member records

        Returns:
            Dictionary with extraction results
        """
        results = {
            'family_members_created': 0,
            'relationships_created': 0,
            'errors': []
        }

        # Extract from family history tables
        logger.info("Extracting family member data...")
        self._extract_from_family_tables()

        # Extract from other tables
        self._extract_from_other_tables()

        # Deduplicate
        self._deduplicate_family_members()

        # Insert into Neo4j
        logger.info("Inserting family members into Neo4j...")
        results['family_members_created'] = self._insert_family_members()

        # Create relationships
        logger.info("Creating family relationships...")
        results['relationships_created'] = self._create_family_relationships()

        return results

    def _extract_from_family_tables(self) -> None:
        """Extract from dedicated family history tables"""
        family_tables = ['FAMHXPAR', 'FAMHXSIB', 'FHQ']

        for table_name in family_tables:
            if table_name not in self.table_data:
                continue

            df = self.table_data[table_name]
            logger.info(f"Processing family table: {table_name} ({len(df)} rows)")

            if table_name == 'FAMHXPAR':
                self._process_parent_table(df)
            elif table_name == 'FAMHXSIB':
                self._process_sibling_table(df)
            elif table_name == 'FHQ':
                self._process_family_questionnaire(df)

    def _process_parent_table(self, df: pd.DataFrame) -> None:
        """Process parent family history table"""
        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            if not ptid:
                continue

            # Mother information
            if self._has_parent_dementia(row, 'NACCMOM'):
                mother = self._create_family_member(
                    patient_id=ptid,
                    relationship_type='parent',
                    gender='F',
                    has_dementia=True,
                    age_at_onset=self._extract_age(row, 'NACCMAGE'),
                    properties={'parent_type': 'mother'}
                )
                self.family_members.append(mother)

            # Father information
            if self._has_parent_dementia(row, 'NACCDAD'):
                father = self._create_family_member(
                    patient_id=ptid,
                    relationship_type='parent',
                    gender='M',
                    has_dementia=True,
                    age_at_onset=self._extract_age(row, 'NACCDAGE'),
                    properties={'parent_type': 'father'}
                )
                self.family_members.append(father)

    def _process_sibling_table(self, df: pd.DataFrame) -> None:
        """Process sibling family history table"""
        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            if not ptid:
                continue

            # Check multiple sibling columns
            for i in range(1, 16):  # Up to 15 siblings
                sib_col = f'NACCSIB{i}'
                if sib_col in row and self._has_relative_dementia(row, sib_col):
                    sibling = self._create_family_member(
                        patient_id=ptid,
                        relationship_type='sibling',
                        has_dementia=True,
                        age_at_onset=self._extract_age(row, f'NACCAGE{i}'),
                        properties={'sibling_number': i}
                    )
                    self.family_members.append(sibling)

    def _process_family_questionnaire(self, df: pd.DataFrame) -> None:
        """Process general family history questionnaire"""
        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            if not ptid:
                continue

            # Extract family history patterns
            for col in df.columns:
                col_upper = col.upper()

                # Determine relationship type from column name
                relationship = self._determine_relationship(col_upper)
                if not relationship:
                    continue

                # Check if has dementia
                if self._indicates_dementia(row[col]):
                    member = self._create_family_member(
                        patient_id=ptid,
                        relationship_type=relationship,
                        has_dementia=True,
                        properties={'source_column': col}
                    )
                    self.family_members.append(member)

    def _extract_from_other_tables(self) -> None:
        """Extract family history from other clinical tables"""
        # Look for family history columns in all tables
        for table_name, df in self.table_data.items():
            if table_name in ['FAMHXPAR', 'FAMHXSIB', 'FHQ']:
                continue  # Already processed

            # Check for family-related columns
            family_cols = [col for col in df.columns
                           if any(term in col.upper() for term in ['FAMILY', 'RELATIVE', 'PARENT', 'SIBLING'])]

            if family_cols:
                logger.info(f"Found family columns in {table_name}: {family_cols}")
                self._process_general_table(df, family_cols)

    def _process_general_table(self, df: pd.DataFrame, family_cols: List[str]) -> None:
        """Process family data from general tables"""
        for _, row in df.iterrows():
            ptid = str(row.get('PTID', '')).strip()
            if not ptid:
                continue

            for col in family_cols:
                value = row.get(col)
                if pd.isna(value):
                    continue

                # Determine if indicates family history
                if self._indicates_family_history(value):
                    relationship = self._determine_relationship(col)
                    if relationship:
                        member = self._create_family_member(
                            patient_id=ptid,
                            relationship_type=relationship,
                            has_dementia=True,
                            properties={'source_column': col, 'value': str(value)}
                        )
                        self.family_members.append(member)

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

    def _has_parent_dementia(self, row: pd.Series, column: str) -> bool:
        """Check if parent has dementia from specific column"""
        if column not in row:
            return False

        value = row[column]
        if pd.isna(value):
            return False

        # NACC coding: 0=No, 1=Yes, 8=Unknown
        if isinstance(value, (int, float)):
            return int(value) == 1

        # String values
        str_val = str(value).strip().upper()
        return str_val in ['1', 'YES', 'Y', 'TRUE']

    def _has_relative_dementia(self, row: pd.Series, column: str) -> bool:
        """Check if relative has dementia"""
        return self._has_parent_dementia(row, column)

    def _indicates_dementia(self, value: Any) -> bool:
        """Check if value indicates dementia"""
        if pd.isna(value):
            return False

        if isinstance(value, (int, float)):
            return int(value) == 1

        str_val = str(value).strip().upper()
        dementia_terms = ['DEMENTIA', 'ALZHEIMER', 'AD', 'MEMORY', 'COGNITIVE']

        return any(term in str_val for term in dementia_terms) or str_val in ['1', 'YES', 'Y']

    def _indicates_family_history(self, value: Any) -> bool:
        """Check if value indicates positive family history"""
        return self._indicates_dementia(value)

    def _determine_relationship(self, column_name: str) -> Optional[str]:
        """Determine relationship type from column name"""
        col_upper = column_name.upper()

        for relationship, patterns in self.RELATIONSHIP_PATTERNS.items():
            if any(pattern in col_upper for pattern in patterns):
                return relationship

        return None

    def _extract_age(self, row: pd.Series, column: str) -> Optional[int]:
        """Extract age from column"""
        if column not in row:
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

        count = self.connector.batch_write(query, relationships, batch_size=5000)

        # Specific relationship types
        specific_query = """
        MATCH (p:Patient)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember)
        WHERE fm.relationship_type = $rel_type
        MERGE (p)-[r:HAS_FAMILY_MEMBER {type: $rel_type}]->(fm)
        WITH p, fm, r
        WHERE fm.relationship_type = 'parent'
        MERGE (p)-[:HAS_PARENT]->(fm)
        MERGE (fm)-[:IS_PARENT_OF]->(p)
        """

        for rel_type in ['parent', 'sibling', 'child']:
            self.connector.execute_write_transaction(specific_query, {'rel_type': rel_type})

        return count


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


if __name__ == "__main__":
    # Test with sample data
    test_data = {
        'FAMHXPAR': pd.DataFrame({
            'PTID': ['001_S_0001', '002_S_0002'],
            'NACCMOM': [1, 0],  # Mother with dementia
            'NACCDAD': [0, 1],  # Father with dementia
            'NACCMAGE': [75, None],
            'NACCDAGE': [None, 80]
        })
    }

    results = execute_family_extraction(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="your_password",
        table_data=test_data
    )
    print(f"Results: {results}")