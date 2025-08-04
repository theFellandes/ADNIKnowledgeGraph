"""
Relationship definitions for ADNI Knowledge Graph
Based on AD-DPC ontology and enhanced with causal relationships
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any


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

    # Family relationships
    IS_PARENT_OF = "isParentOf"
    IS_CHILD_OF = "isChildOf"
    IS_SIBLING_OF = "isSiblingOf"

    # Causal relationships
    CAUSES = "causes"
    INCREASES_RISK_OF = "increasesRiskOf"
    ASSOCIATED_WITH = "associatedWith"
    PRECEDES_CAUSALLY = "precedesCausally"

    # Provenance relationships
    WAS_GENERATED_BY = "wasGeneratedBy"
    USED = "used"
    WAS_DERIVED_FROM = "wasDerivedFrom"


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
class TemporalRelationship(Relationship):
    """Temporal relationship with time-based properties"""

    def __init__(self, from_id: str, from_type: str, to_id: str, to_type: str,
                 relationship_type: RelationshipType, months_delta: int = None):
        super().__init__(from_id, from_type, to_id, to_type, relationship_type)
        if months_delta is not None:
            self.properties['months_delta'] = months_delta
            self.properties['temporal_distance'] = abs(months_delta)


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
    """Helper class to build common relationship patterns"""

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