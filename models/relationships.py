"""
Relationship definitions for ADNI Knowledge Graph
Based on AD-DPC ontology and enhanced with causal relationships
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime


class RelationshipType(Enum):
    """Enumeration of all relationship types in the graph"""

    # Patient relationships
    HAS_VISIT = "hasVisit"
    HAS_DIAGNOSIS = "hasDiagnosis"
    HAS_FAMILY_MEMBER = "hasFamilyMember"
    HAS_GENETIC_PROFILE = "hasGeneticProfile"

    # Visit relationships
    AT_TIME = "atTime"
    PRECEDES = "precedes"
    FOLLOWS = "follows"

    # Assessment relationships
    HAS_COGNITIVE_ASSESSMENT = "hasCognitiveAssessment"
    HAS_BIOMARKER = "hasBiomarker"
    HAS_IMAGING = "hasImaging"

    # Imaging relationships
    HAS_IMAGE = "hasImage"
    DERIVED_FROM = "derivedFrom"
    HAS_VOLUMETRIC_MEASURE = "hasVolumetricMeasure"
    HAS_PET_BINDING = "hasPETBinding"

    # Clinical relationships
    IS_OUTPUT_OF = "isOutputOf"
    REVEALS = "reveals"
    INDICATES = "indicates"
    SUPPORTS_DIAGNOSIS = "supportsDiagnosis"

    # Enhanced Family relationships
    HAS_PARENT = "hasParent"
    HAS_SIBLING = "hasSibling"
    HAS_CHILD = "hasChild"
    IS_PARENT_OF = "isParentOf"
    IS_CHILD_OF = "isChildOf"
    IS_SIBLING_OF = "isSiblingOf"
    IS_SPOUSE_OF = "isSpouseOf"
    IS_GRANDPARENT_OF = "isGrandparentOf"
    IS_GRANDCHILD_OF = "isGrandchildOf"
    IS_AUNT_UNCLE_OF = "isAuntUncleOf"
    IS_NIECE_NEPHEW_OF = "isNieceNephewOf"
    IS_COUSIN_OF = "isCousinOf"

    # Causal relationships
    CAUSES = "causes"
    INCREASES_RISK_OF = "increasesRiskOf"
    ASSOCIATED_WITH = "associatedWith"
    PRECEDES_CAUSALLY = "precedesCausally"

    # Provenance relationships
    WAS_GENERATED_BY = "wasGeneratedBy"
    USED = "used"
    WAS_DERIVED_FROM = "wasDerivedFrom"

    # Temporal relationships
    OCCURRED_BEFORE = "occurredBefore"
    OCCURRED_AFTER = "occurredAfter"
    CONCURRENT_WITH = "concurrentWith"


@dataclass
class Relationship:
    """Generic relationship between two entities"""
    from_id: str
    from_type: str
    to_id: str
    to_type: str
    relationship_type: RelationshipType
    properties: Dict[str, Any] = None

    def __post_init__(self):
        if self.properties is None:
            self.properties = {}

    def to_cypher_pattern(self) -> str:
        """Generate Cypher pattern for this relationship"""
        props = ""
        if self.properties:
            prop_strs = [f"{k}: ${k}" for k in self.properties.keys()]
            props = f" {{{', '.join(prop_strs)}}}"

        return f"(:{self.from_type} {{id: $from_id}})-[:{self.relationship_type.value}{props}]->(:{self.to_type} {{id: $to_id}})"


# Specific relationship classes for complex relationships

@dataclass
class FamilyRelationship(Relationship):
    """Family relationship with validation and integrity checking"""
    def __init__(self, from_id: str, from_type: str, to_id: str, to_type: str,
                 relationship_type: RelationshipType,
                 relationship_strength: float = 1.0,
                 confidence: float = 1.0,
                 source: str = "ADNI_family_history",
                 bidirectional: bool = True):
        super().__init__(from_id, from_type, to_id, to_type, relationship_type)
        self.properties.update({
            'relationship_strength': relationship_strength,
            'confidence': confidence,
            'source': source,
            'bidirectional': bidirectional,
            'created_at': datetime.now().isoformat()
        })

    def get_inverse_relationship(self) -> Optional['FamilyRelationship']:
        """Get the inverse relationship for bidirectional family connections"""
        if not self.properties.get('bidirectional', True):
            return None
        
        inverse_map = {
            RelationshipType.HAS_PARENT: RelationshipType.HAS_CHILD,
            RelationshipType.HAS_CHILD: RelationshipType.HAS_PARENT,
            RelationshipType.IS_PARENT_OF: RelationshipType.IS_CHILD_OF,
            RelationshipType.IS_CHILD_OF: RelationshipType.IS_PARENT_OF,
            RelationshipType.IS_SIBLING_OF: RelationshipType.IS_SIBLING_OF,
            RelationshipType.HAS_SIBLING: RelationshipType.HAS_SIBLING,
            RelationshipType.IS_SPOUSE_OF: RelationshipType.IS_SPOUSE_OF,
            RelationshipType.IS_GRANDPARENT_OF: RelationshipType.IS_GRANDCHILD_OF,
            RelationshipType.IS_GRANDCHILD_OF: RelationshipType.IS_GRANDPARENT_OF,
            RelationshipType.IS_AUNT_UNCLE_OF: RelationshipType.IS_NIECE_NEPHEW_OF,
            RelationshipType.IS_NIECE_NEPHEW_OF: RelationshipType.IS_AUNT_UNCLE_OF,
            RelationshipType.IS_COUSIN_OF: RelationshipType.IS_COUSIN_OF
        }
        
        inverse_type = inverse_map.get(self.relationship_type)
        if not inverse_type:
            return None
        
        return FamilyRelationship(
            from_id=self.to_id,
            from_type=self.to_type,
            to_id=self.from_id,
            to_type=self.from_type,
            relationship_type=inverse_type,
            relationship_strength=self.properties.get('relationship_strength', 1.0),
            confidence=self.properties.get('confidence', 1.0),
            source=self.properties.get('source', 'ADNI_family_history'),
            bidirectional=False  # Prevent infinite recursion
        )

    def validate_relationship_integrity(self) -> Tuple[bool, List[str]]:
        """Validate family relationship for logical consistency"""
        errors = []
        
        # Check for self-relationships
        if self.from_id == self.to_id:
            errors.append("Family member cannot have relationship with themselves")
        
        # Validate relationship strength
        strength = self.properties.get('relationship_strength', 1.0)
        if not 0.0 <= strength <= 1.0:
            errors.append(f"Relationship strength must be between 0.0 and 1.0, got {strength}")
        
        # Validate confidence
        confidence = self.properties.get('confidence', 1.0)
        if not 0.0 <= confidence <= 1.0:
            errors.append(f"Confidence must be between 0.0 and 1.0, got {confidence}")
        
        return len(errors) == 0, errors


@dataclass
class TemporalRelationship(Relationship):
    """Enhanced temporal relationship with time-based properties and family history support"""
    def __init__(self, from_id: str, from_type: str, to_id: str, to_type: str,
                 relationship_type: RelationshipType, 
                 months_delta: int = None,
                 start_date: str = None,
                 end_date: str = None,
                 duration_months: int = None):
        super().__init__(from_id, from_type, to_id, to_type, relationship_type)
        
        if months_delta is not None:
            self.properties['months_delta'] = months_delta
            self.properties['temporal_distance'] = abs(months_delta)
        
        if start_date is not None:
            self.properties['start_date'] = start_date
        
        if end_date is not None:
            self.properties['end_date'] = end_date
        
        if duration_months is not None:
            self.properties['duration_months'] = duration_months
        
        self.properties['created_at'] = datetime.now().isoformat()

    def is_concurrent(self, other: 'TemporalRelationship') -> bool:
        """Check if this temporal relationship overlaps with another"""
        if not all([
            self.properties.get('start_date'),
            self.properties.get('end_date'),
            other.properties.get('start_date'),
            other.properties.get('end_date')
        ]):
            return False
        
        # Simple date overlap check (assumes ISO format dates)
        self_start = self.properties['start_date']
        self_end = self.properties['end_date']
        other_start = other.properties['start_date']
        other_end = other.properties['end_date']
        
        return not (self_end < other_start or other_end < self_start)


@dataclass
class CausalRelationship(Relationship):
    """Causal relationship with strength and confidence"""
    def __init__(self, from_id: str, from_type: str, to_id: str, to_type: str,
                 relationship_type: RelationshipType,
                 causal_strength: float = None,
                 confidence: float = None,
                 evidence: str = None):
        super().__init__(from_id, from_type, to_id, to_type, relationship_type)
        if causal_strength is not None:
            self.properties['causal_strength'] = causal_strength
        if confidence is not None:
            self.properties['confidence'] = confidence
        if evidence is not None:
            self.properties['evidence'] = evidence


@dataclass
class ProvenanceRelationship(Relationship):
    """Provenance relationship tracking data lineage"""
    def __init__(self, from_id: str, from_type: str, to_id: str, to_type: str,
                 relationship_type: RelationshipType,
                 activity: str = None,
                 timestamp: str = None,
                 agent: str = None):
        super().__init__(from_id, from_type, to_id, to_type, relationship_type)
        if activity is not None:
            self.properties['activity'] = activity
        if timestamp is not None:
            self.properties['timestamp'] = timestamp
        if agent is not None:
            self.properties['agent'] = agent


# Relationship builders for common patterns

class RelationshipBuilder:
    """Enhanced helper class to build common relationship patterns including family relationships"""

    @staticmethod
    def patient_to_visit(patient_id: str, visit_id: str) -> Relationship:
        return Relationship(
            from_id=patient_id,
            from_type="Patient",
            to_id=visit_id,
            to_type="Visit",
            relationship_type=RelationshipType.HAS_VISIT
        )

    @staticmethod
    def visit_to_assessment(visit_id: str, assessment_id: str, assessment_type: str) -> Relationship:
        rel_type = RelationshipType.HAS_COGNITIVE_ASSESSMENT
        return Relationship(
            from_id=visit_id,
            from_type="Visit",
            to_id=assessment_id,
            to_type=assessment_type,
            relationship_type=rel_type
        )

    @staticmethod
    def visit_to_imaging(visit_id: str, study_id: str) -> Relationship:
        return Relationship(
            from_id=visit_id,
            from_type="Visit",
            to_id=study_id,
            to_type="ImagingStudy",
            relationship_type=RelationshipType.HAS_IMAGING
        )

    @staticmethod
    def study_to_image(study_id: str, image_id: str) -> Relationship:
        return Relationship(
            from_id=study_id,
            from_type="ImagingStudy",
            to_id=image_id,
            to_type="ImageNode",
            relationship_type=RelationshipType.HAS_IMAGE
        )

    @staticmethod
    def temporal_sequence(earlier_visit_id: str, later_visit_id: str, months_delta: int) -> TemporalRelationship:
        return TemporalRelationship(
            from_id=earlier_visit_id,
            from_type="Visit",
            to_id=later_visit_id,
            to_type="Visit",
            relationship_type=RelationshipType.PRECEDES,
            months_delta=months_delta
        )

    @staticmethod
    def genetic_risk(gene_id: str, diagnosis_id: str, risk_level: float) -> CausalRelationship:
        return CausalRelationship(
            from_id=gene_id,
            from_type="GeneticMarker",
            to_id=diagnosis_id,
            to_type="Diagnosis",
            relationship_type=RelationshipType.INCREASES_RISK_OF,
            causal_strength=risk_level,
            evidence="ADNI cohort analysis"
        )

    # Enhanced family relationship builders
    @staticmethod
    def patient_to_family_member(patient_id: str, family_member_id: str, 
                                confidence: float = 1.0) -> FamilyRelationship:
        """Create general family member relationship"""
        return FamilyRelationship(
            from_id=patient_id,
            from_type="Patient",
            to_id=family_member_id,
            to_type="FamilyMember",
            relationship_type=RelationshipType.HAS_FAMILY_MEMBER,
            confidence=confidence
        )

    @staticmethod
    def parent_child_relationship(parent_id: str, child_id: str, 
                                 confidence: float = 1.0) -> List[FamilyRelationship]:
        """Create bidirectional parent-child relationships"""
        relationships = []
        
        # Parent has child
        relationships.append(FamilyRelationship(
            from_id=parent_id,
            from_type="FamilyMember",
            to_id=child_id,
            to_type="Patient",
            relationship_type=RelationshipType.IS_PARENT_OF,
            confidence=confidence
        ))
        
        # Child has parent
        relationships.append(FamilyRelationship(
            from_id=child_id,
            from_type="Patient",
            to_id=parent_id,
            to_type="FamilyMember",
            relationship_type=RelationshipType.HAS_PARENT,
            confidence=confidence
        ))
        
        return relationships

    @staticmethod
    def sibling_relationship(sibling1_id: str, sibling2_id: str, 
                           confidence: float = 1.0) -> List[FamilyRelationship]:
        """Create bidirectional sibling relationships"""
        relationships = []
        
        # Sibling 1 -> Sibling 2
        relationships.append(FamilyRelationship(
            from_id=sibling1_id,
            from_type="Patient",
            to_id=sibling2_id,
            to_type="FamilyMember",
            relationship_type=RelationshipType.IS_SIBLING_OF,
            confidence=confidence
        ))
        
        # Sibling 2 -> Sibling 1
        relationships.append(FamilyRelationship(
            from_id=sibling2_id,
            from_type="FamilyMember",
            to_id=sibling1_id,
            to_type="Patient",
            relationship_type=RelationshipType.IS_SIBLING_OF,
            confidence=confidence
        ))
        
        return relationships

    @staticmethod
    def create_family_relationships_batch(patient_id: str, family_members: List[Dict[str, Any]]) -> List[FamilyRelationship]:
        """Create batch family relationships from family member data"""
        relationships = []
        
        for member_data in family_members:
            member_id = member_data.get('member_id')
            relationship_type = member_data.get('relationship_type', '').lower()
            confidence = member_data.get('confidence', 1.0)
            
            if not member_id or not relationship_type:
                continue
            
            # Map relationship types to Neo4j relationships
            if relationship_type in ['parent', 'mother', 'father']:
                relationships.extend(
                    RelationshipBuilder.parent_child_relationship(member_id, patient_id, confidence)
                )
            elif relationship_type in ['sibling', 'brother', 'sister']:
                relationships.extend(
                    RelationshipBuilder.sibling_relationship(patient_id, member_id, confidence)
                )
            elif relationship_type in ['child', 'son', 'daughter']:
                relationships.extend(
                    RelationshipBuilder.parent_child_relationship(patient_id, member_id, confidence)
                )
            else:
                # Generic family member relationship
                relationships.append(
                    RelationshipBuilder.patient_to_family_member(patient_id, member_id, confidence)
                )
        
        return relationships


class FamilyRelationshipValidator:
    """Validator for family relationship integrity and consistency"""
    
    @staticmethod
    def validate_family_tree_integrity(relationships: List[FamilyRelationship]) -> Tuple[bool, List[str]]:
        """Validate entire family tree for logical consistency"""
        errors = []
        
        # Check for circular relationships
        parent_child_map = {}
        for rel in relationships:
            if rel.relationship_type == RelationshipType.IS_PARENT_OF:
                parent_id = rel.from_id
                child_id = rel.to_id
                
                if parent_id not in parent_child_map:
                    parent_child_map[parent_id] = []
                parent_child_map[parent_id].append(child_id)
        
        # Check for cycles in parent-child relationships
        def has_cycle(node, visited, rec_stack):
            visited.add(node)
            rec_stack.add(node)
            
            for child in parent_child_map.get(node, []):
                if child not in visited:
                    if has_cycle(child, visited, rec_stack):
                        return True
                elif child in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        visited = set()
        for parent in parent_child_map:
            if parent not in visited:
                if has_cycle(parent, visited, set()):
                    errors.append("Circular parent-child relationship detected")
                    break
        
        # Validate individual relationships
        for rel in relationships:
            is_valid, rel_errors = rel.validate_relationship_integrity()
            if not is_valid:
                errors.extend(rel_errors)
        
        return len(errors) == 0, errors

    @staticmethod
    def suggest_missing_relationships(existing_relationships: List[FamilyRelationship]) -> List[FamilyRelationship]:
        """Suggest missing bidirectional relationships"""
        suggestions = []
        existing_pairs = set()
        
        for rel in existing_relationships:
            existing_pairs.add((rel.from_id, rel.to_id, rel.relationship_type))
        
        for rel in existing_relationships:
            inverse = rel.get_inverse_relationship()
            if inverse and (inverse.from_id, inverse.to_id, inverse.relationship_type) not in existing_pairs:
                suggestions.append(inverse)
        
        return suggestions