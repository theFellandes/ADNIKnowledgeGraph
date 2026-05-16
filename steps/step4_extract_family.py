"""
Step 4: Extract Family Member Data (FIXED)
Fixed version with proper relationship classification and Neo4j insertion
"""

import logging
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
import re
import uuid
import hashlib
from dataclasses import dataclass
from datetime import datetime

from models.entities import FamilyMember
from utils.neo4j_connector import Neo4jConnector
from utils.batch_processor import DataValidator

logger = logging.getLogger(__name__)


@dataclass
class FamilyTree:
    """Data structure for managing family relationships"""
    patient_id: str
    family_members: List[FamilyMember]
    relationships: List[Dict[str, Any]]

    def add_member(self, member: FamilyMember):
        """Add a family member to the tree"""
        self.family_members.append(member)

    def get_members_by_type(self, relationship_type: str) -> List[FamilyMember]:
        """Get all family members of a specific relationship type"""
        return [m for m in self.family_members if m.relationship_type == relationship_type]


class FixedFamilyRelationshipExtractor:
    """Fixed family relationship extractor with better parsing and Neo4j integration"""

    def __init__(self, neo4j_connector: Neo4jConnector):
        self.neo4j = neo4j_connector
        self.family_trees: Dict[str, FamilyTree] = {}
        self.extraction_stats = {
            'patients_processed': 0,
            'family_members_extracted': 0,
            'relationships_created': 0,
            'errors': []
        }

    def extract_family_data(self, patient_data: Dict[str, pd.DataFrame]) -> Dict[str, FamilyTree]:
        """Extract family relationships from ADNI data with improved parsing"""

        logger.info("Starting family relationship extraction (FIXED)...")

        # Process family history tables
        family_extracted = False

        # Look for specific family tables
        for table_name, df in patient_data.items():
            table_upper = table_name.upper()

            # Process different types of family tables
            if 'FAMHX' in table_upper or 'FAMILY' in table_upper or 'FHQ' in table_upper:
                logger.info(f"Processing family table: {table_name}")
                self._process_family_table(df, table_name)
                family_extracted = True

            # Also check for family data in other tables
            elif any(col for col in df.columns if self._is_family_column(col)):
                logger.info(f"Found family data in table: {table_name}")
                self._extract_from_clinical_table(df, table_name)
                family_extracted = True

        if not family_extracted:
            logger.warning("No family history data found in any tables")

        logger.info(f"Family extraction completed. Processed {len(self.family_trees)} patients")
        logger.info(f"Total family members extracted: {self.extraction_stats['family_members_extracted']}")

        return self.family_trees

    def _is_family_column(self, column_name: str) -> bool:
        """Check if a column contains family data"""
        col_upper = column_name.upper()

        # Family relationship keywords
        family_keywords = ['MOTHER', 'FATHER', 'MOM', 'DAD', 'PARENT',
                          'SIBLING', 'BROTHER', 'SISTER', 'SIB',
                          'CHILD', 'SON', 'DAUGHTER', 'OFFSPRING',
                          'FAMILY', 'RELATIVE']

        # Dementia/AD keywords
        dementia_keywords = ['DEM', 'ALZH', 'AD', 'MEMORY', 'COGNITIVE']

        # Check if column has both family and dementia keywords
        has_family = any(kw in col_upper for kw in family_keywords)
        has_dementia = any(kw in col_upper for kw in dementia_keywords)

        return has_family and (has_dementia or 'ONSET' in col_upper or 'AGE' in col_upper)

    def _process_family_table(self, df: pd.DataFrame, table_name: str) -> None:
        """Process a dedicated family history table"""

        # Find patient ID column
        ptid_col = self._find_patient_id_column(df)
        if not ptid_col:
            logger.warning(f"No patient ID column found in {table_name}")
            return

        processed_count = 0

        for _, row in df.iterrows():
            ptid = self._extract_patient_id(row, ptid_col)
            if not ptid:
                continue

            # Ensure family tree exists
            if ptid not in self.family_trees:
                self.family_trees[ptid] = FamilyTree(ptid, [], [])

            family_tree = self.family_trees[ptid]

            # Extract family members from all columns
            for col in df.columns:
                if col == ptid_col:
                    continue

                # Process each column that might contain family data
                family_member = self._extract_family_member_from_column(row, col, table_name, ptid)
                if family_member:
                    # Update patient_id
                    family_member.patient_id = ptid

                    # Check for duplicates before adding
                    if not self._is_duplicate_member(family_tree, family_member):
                        family_tree.add_member(family_member)
                        processed_count += 1

        logger.info(f"Extracted {processed_count} family members from {table_name}")
        self.extraction_stats['family_members_extracted'] += processed_count

    def _extract_from_clinical_table(self, df: pd.DataFrame, table_name: str) -> None:
        """Extract family data from general clinical tables"""

        # Find patient ID column
        ptid_col = self._find_patient_id_column(df)
        if not ptid_col:
            return

        # Find family-related columns
        family_cols = [col for col in df.columns if self._is_family_column(col)]

        if not family_cols:
            return

        processed_count = 0

        for _, row in df.iterrows():
            ptid = self._extract_patient_id(row, ptid_col)
            if not ptid:
                continue

            # Ensure family tree exists
            if ptid not in self.family_trees:
                self.family_trees[ptid] = FamilyTree(ptid, [], [])

            family_tree = self.family_trees[ptid]

            # Process each family column
            for col in family_cols:
                family_member = self._extract_family_member_from_column(row, col, table_name, ptid)
                if family_member:
                    family_member.patient_id = ptid

                    if not self._is_duplicate_member(family_tree, family_member):
                        family_tree.add_member(family_member)
                        processed_count += 1

        if processed_count > 0:
            logger.info(f"Extracted {processed_count} family members from {table_name}")
            self.extraction_stats['family_members_extracted'] += processed_count

    def _extract_family_member_from_column(self, row: pd.Series, column: str,
                                          table_name: str, ptid: str) -> Optional[FamilyMember]:
        """Extract family member information from a specific column"""

        value = row.get(column)

        # Skip if no value or not indicating dementia
        if pd.isna(value) or value == '' or value == 0:
            return None

        # Determine relationship type from column name
        relationship_type = self._determine_relationship_type(column)

        # Skip if can't determine relationship
        if relationship_type == 'unknown':
            return None

        # Check if value indicates dementia
        has_dementia = self._indicates_dementia(value)

        if not has_dementia:
            return None

        # Determine gender based on relationship
        gender = self._determine_gender(column, relationship_type)

        # Extract age if available
        age_at_onset = self._extract_age_from_column(row, column)

        # Create family member
        deterministic_key = f"{ptid}_{relationship_type}_{column}"
        member_id = f"fm_{hashlib.md5(deterministic_key.encode()).hexdigest()[:12]}"

        return FamilyMember(
            member_id=member_id,
            patient_id="",  # Will be set by caller
            relationship_type=relationship_type,
            gender=gender,
            has_dementia=has_dementia,
            dementia_type=self._extract_dementia_type(column),
            age_at_onset=age_at_onset,
            properties={
                'source_table': table_name,
                'source_column': column,
                'value': str(value)
            }
        )

    def _determine_relationship_type(self, column_name: str) -> str:
        """Determine family relationship type from column name (FIXED)"""
        col_upper = column_name.upper()

        # Parent detection (most specific first)
        if any(term in col_upper for term in ['MOTHER', 'MOM', 'MOMDEM', 'NACCMOM']):
            return 'parent'
        elif any(term in col_upper for term in ['FATHER', 'DAD', 'DADDEM', 'NACCDAD']):
            return 'parent'
        elif 'PARENT' in col_upper:
            return 'parent'

        # Sibling detection
        elif any(term in col_upper for term in ['SIBLING', 'BROTHER', 'SISTER', 'SIB']):
            return 'sibling'

        # Child detection
        elif any(term in col_upper for term in ['CHILD', 'SON', 'DAUGHTER', 'OFFSPRING']):
            return 'child'

        # Other family members
        elif any(term in col_upper for term in ['GRANDPARENT', 'GRANDMOTHER', 'GRANDFATHER']):
            return 'grandparent'
        elif any(term in col_upper for term in ['AUNT', 'UNCLE']):
            return 'other_relative'
        elif any(term in col_upper for term in ['COUSIN']):
            return 'other_relative'

        # General family
        elif 'FAMILY' in col_upper or 'RELATIVE' in col_upper:
            # Try to be more specific based on additional context
            if '1ST' in col_upper or 'FIRST' in col_upper:
                return 'parent'  # First degree relatives often parents
            else:
                return 'other_relative'

        else:
            return 'unknown'

    def _determine_gender(self, column_name: str, relationship_type: str) -> Optional[str]:
        """Determine gender based on column name and relationship"""
        col_upper = column_name.upper()

        if any(term in col_upper for term in ['MOTHER', 'MOM', 'GRANDMOTHER']):
            return 'F'
        elif any(term in col_upper for term in ['FATHER', 'DAD', 'GRANDFATHER']):
            return 'M'
        elif 'SISTER' in col_upper:
            return 'F'
        elif 'BROTHER' in col_upper:
            return 'M'
        elif 'DAUGHTER' in col_upper:
            return 'F'
        elif 'SON' in col_upper:
            return 'M'
        elif 'AUNT' in col_upper:
            return 'F'
        elif 'UNCLE' in col_upper:
            return 'M'

        return None  # Return None if gender cannot be determined

    def _indicates_dementia(self, value: Any) -> bool:
        """Check if value indicates dementia"""
        if pd.isna(value):
            return False

        # Handle numeric codes
        if isinstance(value, (int, float)):
            return int(value) == 1 or int(value) == 2  # Sometimes 2 also indicates presence

        # Handle string values
        str_val = str(value).strip().upper()

        # Direct positive indicators
        positive_indicators = ['1', '2', 'YES', 'Y', 'TRUE', 'T', '1.0', '2.0']
        if str_val in positive_indicators:
            return True

        # Check for dementia keywords
        dementia_terms = ['DEMENTIA', 'ALZHEIMER', 'AD', 'MEMORY', 'COGNITIVE', 'IMPAIR']
        return any(term in str_val for term in dementia_terms)

    def _extract_dementia_type(self, column_name: str) -> Optional[str]:
        """Extract dementia type from column name"""
        col_upper = column_name.upper()

        if 'ALZH' in col_upper or 'AD' in col_upper:
            return "Alzheimer's Disease"
        elif 'VASCULAR' in col_upper:
            return 'Vascular Dementia'
        elif 'LEWY' in col_upper:
            return 'Lewy Body Dementia'
        elif 'FRONTOTEMPORAL' in col_upper or 'FTD' in col_upper:
            return 'Frontotemporal Dementia'
        elif 'DEMENTIA' in col_upper:
            return 'Dementia (unspecified)'

        return None

    def _extract_age_from_column(self, row: pd.Series, base_col: str) -> Optional[int]:
        """Try to extract age at onset from related columns"""
        # Look for age column with similar prefix
        base_prefix = base_col.split('_')[0] if '_' in base_col else base_col[:3]

        for col in row.index:
            if 'AGE' in col.upper() and base_prefix.upper() in col.upper():
                value = row[col]
                if not pd.isna(value):
                    try:
                        age = int(float(value))
                        if 30 <= age <= 120:  # Reasonable age range
                            return age
                    except:
                        pass

        return None

    def _is_duplicate_member(self, family_tree: FamilyTree, new_member: FamilyMember) -> bool:
        """Check if this family member already exists"""
        for existing in family_tree.family_members:
            if (existing.relationship_type == new_member.relationship_type and
                existing.gender == new_member.gender and
                existing.has_dementia == new_member.has_dementia):
                return True
        return False

    def _find_patient_id_column(self, df: pd.DataFrame) -> Optional[str]:
        """Find the patient ID column in the dataframe"""
        id_patterns = ['PTID', 'RID', 'SUBJID', 'SUBJECT', 'ID', 'PATIENT']

        for col in df.columns:
            col_upper = col.upper()
            if any(pattern in col_upper for pattern in id_patterns):
                # Verify it contains valid patient IDs
                sample = df[col].dropna().head(5)
                if len(sample) > 0 and all(str(val).strip() for val in sample):
                    return col
        return None

    def _extract_patient_id(self, row: pd.Series, ptid_col: str) -> Optional[str]:
        """Extract and validate patient ID from row"""
        if ptid_col not in row:
            return None

        ptid = str(row[ptid_col]).strip()
        return ptid if ptid and not pd.isna(row[ptid_col]) else None

    def create_family_nodes_in_neo4j(self) -> int:
        """Create family member nodes in Neo4j"""

        logger.info("Creating family member nodes in Neo4j...")

        # Setup constraints and indexes
        self.neo4j.create_constraint('FamilyMember', 'member_id')
        self.neo4j.create_index('FamilyMember', 'patient_id')
        self.neo4j.create_index('FamilyMember', 'relationship_type')

        # Collect all family members
        all_members = []
        for family_tree in self.family_trees.values():
            all_members.extend(family_tree.family_members)

        if not all_members:
            logger.warning("No family members to create")
            return 0

        logger.info(f"Creating {len(all_members)} family member nodes...")

        # Prepare data for batch insert
        member_data = []
        for member in all_members:
            member_dict = {
                'member_id': member.member_id,
                'patient_id': member.patient_id,
                'relationship_type': member.relationship_type,
                'gender': member.gender if member.gender is not None else 'U',  # Use 'U' for unknown
                'has_dementia': member.has_dementia if member.has_dementia is not None else False,
                'dementia_type': member.dementia_type,
                'age_at_onset': member.age_at_onset,
                'source_table': member.properties.get('source_table'),
                'source_column': member.properties.get('source_column'),
                'created_at': datetime.now().isoformat()
            }
            # Remove None values to avoid Neo4j issues
            member_dict = {k: v for k, v in member_dict.items() if v is not None}
            member_data.append(member_dict)

        # Create family member nodes
        query = """
        UNWIND $batch as member
        MERGE (fm:FamilyMember {member_id: member.member_id})
        SET fm += member,
            fm.updated_at = datetime()
        """

        created_count = self.neo4j.batch_write(query, member_data, batch_size=1000)
        logger.info(f"Created {created_count} family member nodes")

        # Connect family members to patients
        connect_query = """
        UNWIND $batch as member
        MATCH (p:Patient {ptid: member.patient_id})
        MATCH (fm:FamilyMember {member_id: member.member_id})
        MERGE (p)-[:HAS_FAMILY_MEMBER]->(fm)
        """

        self.neo4j.batch_write(connect_query, member_data, batch_size=1000)
        logger.info("Connected family members to patients")

        # Create specific relationship types (FIXED to handle null gender and correct parameter passing)
        self._create_typed_relationships_fixed()

        return created_count

    def _create_typed_relationships_fixed(self):
        """Create specific typed relationships with proper null handling and correct parameter passing"""

        for family_tree in self.family_trees.values():
            patient_id = family_tree.patient_id

            # Create parent relationships
            parents = family_tree.get_members_by_type('parent')
            if parents:
                parent_data = []
                for parent in parents:
                    data = {
                        'patient_id': patient_id,
                        'member_id': parent.member_id
                    }
                    # Only add gender if it's not None
                    if parent.gender is not None:
                        data['gender'] = parent.gender
                    parent_data.append(data)

                # Use different queries based on whether gender is present
                for data in parent_data:
                    if 'gender' in data:
                        query = """
                        MATCH (p:Patient {ptid: $patient_id})
                        MATCH (fm:FamilyMember {member_id: $member_id})
                        MERGE (p)-[:HAS_PARENT {gender: $gender}]->(fm)
                        """
                    else:
                        query = """
                        MATCH (p:Patient {ptid: $patient_id})
                        MATCH (fm:FamilyMember {member_id: $member_id})
                        MERGE (p)-[:HAS_PARENT]->(fm)
                        """

                    # FIXED: Pass parameters as a dictionary, not as keyword arguments
                    self.neo4j.execute_write_transaction(query, data)

            # Create sibling relationships
            siblings = family_tree.get_members_by_type('sibling')
            if siblings:
                for sibling in siblings:
                    data = {
                        'patient_id': patient_id,
                        'member_id': sibling.member_id
                    }

                    # Create relationship without gender property if it's null
                    if sibling.gender is not None:
                        query = """
                        MATCH (p:Patient {ptid: $patient_id})
                        MATCH (fm:FamilyMember {member_id: $member_id})
                        MERGE (p)-[:HAS_SIBLING {gender: $gender}]->(fm)
                        """
                        data['gender'] = sibling.gender
                    else:
                        query = """
                        MATCH (p:Patient {ptid: $patient_id})
                        MATCH (fm:FamilyMember {member_id: $member_id})
                        MERGE (p)-[:HAS_SIBLING]->(fm)
                        """

                    # FIXED: Pass parameters as a dictionary, not as keyword arguments
                    self.neo4j.execute_write_transaction(query, data)

            # Create child relationships
            children = family_tree.get_members_by_type('child')
            if children:
                for child in children:
                    data = {
                        'patient_id': patient_id,
                        'member_id': child.member_id
                    }

                    if child.gender is not None:
                        query = """
                        MATCH (p:Patient {ptid: $patient_id})
                        MATCH (fm:FamilyMember {member_id: $member_id})
                        MERGE (p)-[:HAS_CHILD {gender: $gender}]->(fm)
                        """
                        data['gender'] = child.gender
                    else:
                        query = """
                        MATCH (p:Patient {ptid: $patient_id})
                        MATCH (fm:FamilyMember {member_id: $member_id})
                        MERGE (p)-[:HAS_CHILD]->(fm)
                        """

                    # FIXED: Pass parameters as a dictionary, not as keyword arguments
                    self.neo4j.execute_write_transaction(query, data)


def execute_family_extraction_fixed(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                                    table_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """
    Fixed execution function for family extraction
    """
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        extractor = FixedFamilyRelationshipExtractor(connector)

        # Extract family data
        family_trees = extractor.extract_family_data(table_data)

        # Create nodes in Neo4j
        nodes_created = extractor.create_family_nodes_in_neo4j()

        results = {
            'family_members_created': nodes_created,
            'patients_with_family': len(family_trees),
            'extraction_stats': extractor.extraction_stats
        }

        logger.info(f"✅ Created {nodes_created} family member nodes")
        logger.info(f"✅ Processed {len(family_trees)} patients with family data")

        return results

    except Exception as e:
        logger.error(f"Family extraction failed: {e}")
        raise
    finally:
        connector.close()