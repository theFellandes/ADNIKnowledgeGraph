"""
Step 33: Biolink Model Categorisation (In-Place Upgrade)
=========================================================
Annotates existing nodes with biolink:category strings and relationships
with biolink:predicate strings, per the Biolink Model schema. No data
ingestion; no new node labels; no new relationship types. Pure metadata
pass.

This closes the Biolink half of Contribution 5 (Relation Normalisation)
from the contribution table, complementing the RO URI assignment done by
step 18. Together: every relationship type carries both an `r.uri` (RO)
and an `r.biolink_predicate` (Biolink) where a mapping is semantically
clean. Where a mapping would constitute a semantic over-claim, no
biolink_predicate is set (per Hajer's §4.5 constraint).

All operations use MERGE / SET on existing nodes & edges — idempotent.

Usage:
    python -m steps.step33_biolink_categories --neo4j-password your_password
"""

from __future__ import annotations

import logging
from typing import Dict, Any

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Biolink mappings — curated per the Biolink Model 4.x classes
# ══════════════════════════════════════════════════════════════════════

# Node label → Biolink class
# Curated: only mappings where the semantic claim is defensible. Labels
# with no clean Biolink equivalent (project-internal aggregates,
# technical tile formats) are omitted intentionally.
NODE_LABEL_TO_BIOLINK: Dict[str, str] = {
    # Clinical / patient
    "Patient": "biolink:Case",
    "FamilyMember": "biolink:Case",
    "Sibling": "biolink:Case",
    "Visit": "biolink:Procedure",
    "Cohort": "biolink:Cohort",
    "ResearchCohort": "biolink:Cohort",
    "Demographics": "biolink:Attribute",
    "PatientSummary": "biolink:Attribute",

    # Disease / phenotype
    "Diagnosis": "biolink:DiseaseOrPhenotypicFeature",
    "DiseaseStage": "biolink:DiseaseOrPhenotypicFeature",
    "DiagnosisStage": "biolink:DiseaseOrPhenotypicFeature",
    "MedicalCondition": "biolink:Disease",
    "ClinicalFinding": "biolink:PhenotypicFeature",
    "ClinicalPhenotype": "biolink:PhenotypicFeature",
    "Finding": "biolink:PhenotypicFeature",
    "ImageFinding": "biolink:PhenotypicFeature",
    "LaboratoryFinding": "biolink:PhenotypicFeature",
    "PsychometricFinding": "biolink:PhenotypicFeature",

    # Biomarker / molecular
    "Biomarker": "biolink:MolecularEntity",
    "CSFBiomarker": "biolink:MolecularEntity",
    "BloodBiomarker": "biolink:MolecularEntity",
    "BiomarkerProfile": "biolink:ClinicalAttribute",
    "BiomarkerCategory": "biolink:OntologyClass",
    "BiomarkerType": "biolink:OntologyClass",
    "BiomarkerPattern": "biolink:Attribute",
    "PETBinding": "biolink:MolecularEntity",
    "PETTracer": "biolink:ChemicalEntity",

    # Cognitive / assessment
    "CognitiveAssessment": "biolink:ClinicalAttribute",
    "ClinicalAssessment": "biolink:ClinicalAttribute",
    "Assessment": "biolink:ClinicalAttribute",
    "MultimodalAssessment": "biolink:ClinicalAttribute",
    "CognitiveTrajectory": "biolink:Attribute",
    "CognitiveTest": "biolink:DiagnosticAid",
    "TestType": "biolink:NamedThing",
    "Scale": "biolink:InformationContentEntity",
    "ATNProfile": "biolink:ClinicalAttribute",
    "ATNCategory": "biolink:OntologyClass",

    # Anatomy
    "BrainRegion": "biolink:GrossAnatomicalStructure",

    # Imaging
    "ImageNode": "biolink:Image",
    "ImagingStudy": "biolink:Procedure",
    "ImagingSeries": "biolink:Dataset",
    "Series": "biolink:Dataset",
    "MRIScan": "biolink:Procedure",
    "PETScan": "biolink:Procedure",
    "BrainImagingTest": "biolink:Procedure",
    "VolumetricMeasure": "biolink:Attribute",
    "Imaging": "biolink:Procedure",

    # Genetic
    "Genetic": "biolink:Genotype",
    "GeneticMarker": "biolink:Genotype",
    "GeneticRiskProfile": "biolink:Attribute",
    "FamilyRisk": "biolink:Attribute",
    "RiskFactor": "biolink:Attribute",

    # Ontology / semantic infrastructure
    "OntologyConcept": "biolink:OntologyClass",
    "AlzKBConcept": "biolink:OntologyClass",
    "Ontology": "biolink:OntologyClass",
    "EventOntology": "biolink:OntologyClass",
    "EventType": "biolink:NamedThing",

    # Molecular (Step 35 — Contribution 4)
    "Gene": "biolink:Gene",

    # Drugs
    "Medication": "biolink:Drug",

    # Pathways / processes
    "BiologicalPathway": "biolink:Pathway",
    "Process": "biolink:BiologicalProcessOrActivity",
    "ProcessingActivity": "biolink:Activity",
    "DiagnosticProcess": "biolink:Procedure",
    "LaboratoryAssay": "biolink:Procedure",

    # Progression / temporal
    "ProgressionEvent": "biolink:Activity",
    "ProgressionPattern": "biolink:Attribute",
    "Timeline": "biolink:Attribute",
    "TemporalRegion": "biolink:Attribute",
    "ZeroDimensionalTemporalRegion": "biolink:Attribute",

    # Provenance
    "BatchIngestion": "biolink:Activity",
    "DataSource": "biolink:InformationContentEntity",
    "ParticipantFile": "biolink:InformationContentEntity",
    "Participant": "biolink:Case",
}

# Relationship type → Biolink predicate
# Curated: only where the predicate maps cleanly. Project-internal
# aggregation edges are omitted (respecting the "no over-claim"
# constraint and matching the A5 allowlist in metrics/validity_rubric.yaml).
REL_TYPE_TO_BIOLINK: Dict[str, str] = {
    # Patient → clinical
    "HAS_VISIT": "biolink:has_attribute",
    "HAS_DIAGNOSIS": "biolink:has_phenotype",
    "HAS_COGNITIVE_ASSESSMENT": "biolink:has_attribute",
    "HAS_BIOMARKER": "biolink:has_biomarker_for",
    "HAS_BIOMARKER_PROFILE": "biolink:has_attribute",
    "HAS_PHENOTYPE": "biolink:has_phenotype",
    "HAS_RISK_FACTOR": "biolink:has_phenotype",
    "HAS_AMYLOID_STATUS": "biolink:has_phenotype",
    "HAS_TAU_STATUS": "biolink:has_phenotype",
    "HAS_NEURODEGENERATION_STATUS": "biolink:has_phenotype",
    "HAS_DEMOGRAPHICS": "biolink:has_attribute",
    "HAS_GENETIC_RISK": "biolink:has_phenotype",
    "HAS_GENETIC_MARKER": "biolink:has_attribute",
    "HAS_CLINICAL_FINDING": "biolink:has_phenotype",
    "HAS_ATN_PROFILE": "biolink:has_attribute",
    "HAS_COGNITIVE_TRAJECTORY": "biolink:has_attribute",
    "HAS_MULTIMODAL_ASSESSMENT": "biolink:has_attribute",
    "HAS_IMAGE": "biolink:has_attribute",
    "HAS_FAMILY_MEMBER": "biolink:related_to",
    "HAS_PARENT": "biolink:related_to",
    "HAS_SIBLING": "biolink:related_to",
    "HAS_FAMILY_RISK": "biolink:has_phenotype",

    # Causal / temporal
    "PROGRESSED_TO": "biolink:precedes",
    "PRECEDES": "biolink:precedes",
    "FOLLOWED_BY": "biolink:precedes",
    "FOLLOWS_PROGRESSION": "biolink:related_to",
    "PROGRESSES_TO": "biolink:precedes",
    "CAN_PROGRESS_TO": "biolink:precedes",
    "EXPERIENCED_PROGRESSION": "biolink:contributes_to",
    "AT_STAGE": "biolink:has_attribute",
    "AT_DISEASE_STAGE": "biolink:has_attribute",
    "ASSOCIATED_WITH_STAGE": "biolink:related_to",
    "RESULTED_IN": "biolink:causes",

    # Diagnostic / supporting
    "SUPPORTS_DIAGNOSIS": "biolink:correlated_with",
    "CORRELATES_WITH": "biolink:correlated_with",
    "INDICATES": "biolink:correlated_with",
    "INDICATES_PATHWAY": "biolink:related_to",
    "UNDERWENT_ASSESSMENT": "biolink:participates_in",
    "INCLUDES_ASSESSMENT": "biolink:related_to",
    "IS_CLINICAL_FINDING": "biolink:related_to",
    "IS_TYPE": "biolink:category",

    # Cohort / categorisation
    "IN_COHORT": "biolink:in_cohort",
    "BELONGS_TO_COHORT": "biolink:in_cohort",
    "BELONGS_TO_CATEGORY": "biolink:category",

    # Ontology / semantic
    "MAPS_TO": "biolink:exact_match",
    "IS_A": "biolink:subclass_of",
    "CLASSIFIED_AS": "biolink:category",
    "SAME_AS": "biolink:same_as",
    "HAS_SUBTYPE": "biolink:superclass_of",
    "ALZKB_RELATES_TO": "biolink:related_to",

    # Molecular (Step 35 — Contribution 4)
    "PARTICIPATES_IN": "biolink:participates_in",
    "ENCODES": "biolink:encodes",

    # NOT mapped (project-internal aggregations — per the
    # "no semantic over-claim" constraint, intentionally left
    # without a biolink_predicate):
    #   HAS_TIMELINE, HAS_SUMMARY, HAS_DOMAIN, DEFINES_EVENT_TYPE,
    #   MATCHES_PATTERN, BATCH_INGESTED_BY, LOADED_FROM, PROCESSED_BY
}


# ══════════════════════════════════════════════════════════════════════
class BiolinkAnnotator:
    """Annotate existing nodes + relationships with Biolink categories
    and predicates. Pure metadata pass; no graph structure changes."""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector

    def execute(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {"nodes_annotated_per_label": {},
                                    "edges_annotated_per_type": {},
                                    "node_labels_skipped": [],
                                    "rel_types_skipped": []}

        # ── 1. Node-label biolink_category ────────────────────────────
        for label, category in NODE_LABEL_TO_BIOLINK.items():
            count = self._set_node_category(label, category)
            if count is not None:
                results["nodes_annotated_per_label"][label] = {
                    "biolink_category": category,
                    "nodes_updated": count,
                }
            else:
                results["node_labels_skipped"].append(label)

        # ── 2. Relationship-type biolink_predicate ────────────────────
        for rel_type, predicate in REL_TYPE_TO_BIOLINK.items():
            count = self._set_rel_predicate(rel_type, predicate)
            if count is not None:
                results["edges_annotated_per_type"][rel_type] = {
                    "biolink_predicate": predicate,
                    "edges_updated": count,
                }
            else:
                results["rel_types_skipped"].append(rel_type)

        # ── 3. Coverage tallies ───────────────────────────────────────
        results["total_labels_annotated"] = len(results["nodes_annotated_per_label"])
        results["total_nodes_annotated"] = sum(
            d["nodes_updated"] for d in results["nodes_annotated_per_label"].values()
        )
        results["total_rel_types_annotated"] = len(results["edges_annotated_per_type"])
        results["total_edges_annotated"] = sum(
            d["edges_updated"] for d in results["edges_annotated_per_type"].values()
        )

        self._print_summary(results)
        return results

    # ── Helpers ────────────────────────────────────────────────────────

    def _set_node_category(self, label: str, category: str) -> int | None:
        """Set biolink_category on every node carrying the given label.
        Returns the number of nodes updated, or None if the label has 0
        instances in the graph (still safe — just nothing to do)."""

        # Sanitize label — only A-Za-z0-9_ allowed in Neo4j labels.
        if not label.replace("_", "").isalnum():
            logger.warning("  ⚠️  Skipping unsafe label name: %r", label)
            return None

        query = (
            f"MATCH (n:`{label}`) "
            f"SET n.biolink_category = $category "
            f"RETURN count(n) AS n"
        )
        try:
            res = self.connector.run_query(query, {"category": category})
            count = int(res[0]["n"]) if res else 0
            if count == 0:
                logger.info("  ⏭️  %s: 0 instances; skipping", label)
                return None
            logger.info("  ✅ %s → %s: %d nodes", label, category, count)
            return count
        except Exception as e:
            logger.error("  ❌ %s → %s failed: %s", label, category, e)
            return None

    def _set_rel_predicate(self, rel_type: str, predicate: str) -> int | None:
        """Set biolink_predicate on every edge of the given type. Returns
        the number of edges updated, or None if 0 edges exist."""

        if not rel_type.replace("_", "").isalnum():
            logger.warning("  ⚠️  Skipping unsafe rel type name: %r", rel_type)
            return None

        query = (
            f"MATCH ()-[r:`{rel_type}`]->() "
            f"SET r.biolink_predicate = $predicate "
            f"RETURN count(r) AS n"
        )
        try:
            res = self.connector.run_query(query, {"predicate": predicate})
            count = int(res[0]["n"]) if res else 0
            if count == 0:
                logger.info("  ⏭️  %s: 0 edges; skipping", rel_type)
                return None
            logger.info("  ✅ %s → %s: %d edges", rel_type, predicate, count)
            return count
        except Exception as e:
            logger.error("  ❌ %s → %s failed: %s", rel_type, predicate, e)
            return None

    def _print_summary(self, results: Dict[str, Any]) -> None:
        logger.info("")
        logger.info("=" * 60)
        logger.info("STEP 33 — BIOLINK MODEL ANNOTATION SUMMARY")
        logger.info("=" * 60)
        logger.info(
            "  Node labels with biolink_category:  %d (of %d candidates)",
            results["total_labels_annotated"], len(NODE_LABEL_TO_BIOLINK),
        )
        logger.info("  Total nodes annotated:               %s",
                    f"{results['total_nodes_annotated']:,}")
        logger.info(
            "  Rel types with biolink_predicate:    %d (of %d candidates)",
            results["total_rel_types_annotated"], len(REL_TYPE_TO_BIOLINK),
        )
        logger.info("  Total edges annotated:               %s",
                    f"{results['total_edges_annotated']:,}")
        if results["node_labels_skipped"]:
            logger.info(
                "  Skipped node labels (0 instances): %s",
                ", ".join(results["node_labels_skipped"])[:200],
            )
        if results["rel_types_skipped"]:
            logger.info(
                "  Skipped rel types (0 edges): %s",
                ", ".join(results["rel_types_skipped"])[:200],
            )
        logger.info("=" * 60)


# ══════════════════════════════════════════════════════════════════════
# Pipeline entry point
# ══════════════════════════════════════════════════════════════════════

def execute_biolink_categories(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    **kwargs,
) -> Dict[str, Any]:
    """Main execution function for Step 33."""

    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)
    try:
        return BiolinkAnnotator(connector).execute()
    except Exception as e:
        logger.error("Step 33 failed: %s", e)
        raise
    finally:
        connector.close()


# ══════════════════════════════════════════════════════════════════════
# Standalone execution
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Step 33: Biolink Model categorisation"
    )
    parser.add_argument("--neo4j-uri", default=None)
    parser.add_argument("--neo4j-user", default=None)
    parser.add_argument("--neo4j-password", default=None)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    # Resolve credentials via env_loader when not passed on CLI.
    if not (args.neo4j_uri and args.neo4j_user and args.neo4j_password):
        from utils.env_loader import load_config
        cfg = load_config()
        args.neo4j_uri = args.neo4j_uri or cfg.get("neo4j_uri")
        args.neo4j_user = args.neo4j_user or cfg.get("neo4j_user", "neo4j")
        args.neo4j_password = args.neo4j_password or cfg.get("neo4j_password")

    execute_biolink_categories(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
    )
