"""
Step 20: Ontology Layer + MAPS_TO
==================================
Builds the full semantic ontology layer:
  - Creates OntologyConcept nodes for SNOMED-CT (~20), LOINC (~10),
    UBERON (~12), HPO (~5) concepts
  - Builds IS_A hierarchies within each ontology
  - Creates MAPS_TO relationships from data nodes to OntologyConcepts

All operations use MERGE (idempotent).

Usage:
    python -m steps.step20_ontology_layer --neo4j-password your_password
"""

import logging
from typing import Dict, Any, List, Tuple

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Ontology Concept Definitions
# ══════════════════════════════════════════════════════════════════════
# Each concept: (code, label, source_ontology, parent_code_or_None)

SNOMED_CONCEPTS: List[Tuple[str, str, str]] = [
    # (code, label, parent_code)
    # Disease hierarchy
    ("64572001", "Disease", None),
    ("118940003", "Disorder of nervous system", "64572001"),
    ("230258005", "Neurodegenerative disorder", "118940003"),
    ("52448006", "Dementia", "230258005"),
    ("26929004", "Alzheimer's disease", "52448006"),
    ("386806002", "Mild cognitive impairment", "230258005"),
    ("17621005", "Normal (finding)", None),
    ("386807006", "Subjective memory complaint", None),
    # Clinical findings
    ("373930000", "Cognitive function finding", None),
    ("386807006", "Memory finding", "373930000"),
    # Biomarker-related
    ("102862007", "Cerebrospinal fluid analysis", None),
    ("259565002", "Amyloid beta protein", "102862007"),
    ("85916004", "Tau protein", "102862007"),
    # Risk factors
    ("609495001", "Genetic risk factor", None),
    ("414482005", "APOE genotype", "609495001"),
    # Demographics
    ("125676002", "Sex", None),
    ("397669002", "Age", None),
    ("105421008", "Educational attainment", None),
]

LOINC_CONCEPTS: List[Tuple[str, str, str]] = [
    # Cognitive assessments
    ("72106-8", "MMSE total score", None),
    ("72172-0", "CDR global score", None),
    ("71130-0", "FAQ total score", None),
    ("72194-4", "ADAS-Cog total score", None),
    ("72133-2", "MoCA total score", None),
    ("72026-8", "Logical Memory - Delayed Recall", None),
    # CSF biomarkers
    ("13967-5", "Beta-amyloid 42 in CSF", None),
    ("83235-5", "Beta-amyloid 40 in CSF", None),
    ("15201-7", "Total tau in CSF", None),
    ("62731-6", "Phosphorylated tau 181 in CSF", None),
]

UBERON_CONCEPTS: List[Tuple[str, str, str]] = [
    # Brain regions (top down)
    ("0000955", "Brain", None),
    ("0000956", "Cerebral cortex", "0000955"),
    ("0002421", "Hippocampal formation", "0000956"),
    ("0002728", "Entorhinal cortex", "0000956"),
    ("0001876", "Amygdala", "0000955"),
    ("0016525", "Frontal lobe", "0000956"),  # was 0000203 (=pallium); corrected to UBERON:0016525 (frontal lobe), OLS4-verified 2026-06-17
    ("0001871", "Temporal lobe", "0000956"),
    ("0001872", "Parietal lobe", "0000956"),
    ("0002021", "Occipital lobe", "0000956"),
    ("0002298", "Brainstem", "0000955"),
    ("0001897", "Thalamus", "0000955"),
    ("0002420", "Basal ganglion", "0000955"),
    ("0002037", "Cerebellum", "0000955"),
    ("0004086", "Brain ventricle", "0000955"),
]

HPO_CONCEPTS: List[Tuple[str, str, str]] = [
    ("HP:0100543", "Cognitive impairment", None),
    ("HP:0000726", "Dementia", "HP:0100543"),
    ("HP:0002354", "Memory impairment", "HP:0100543"),
    ("HP:0001268", "Mental deterioration", "HP:0100543"),
    ("HP:0000708", "Behavioral abnormality", None),
]

# Ontology prefix → source_ontology label
ONTOLOGY_PREFIXES = {
    "snomed": "SNOMED-CT",
    "loinc": "LOINC",
    "uberon": "UBERON",
    "hpo": "HPO",
}


# ══════════════════════════════════════════════════════════════════════
class OntologyLayerBuilder:
    """Builds the full ontology layer with concepts, hierarchies, and MAPS_TO."""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector

    def execute(self) -> Dict[str, Any]:
        """Build complete ontology layer."""
        results: Dict[str, Any] = {}

        # ── 1. Create concept nodes per ontology ──────────────────────
        for ontology, concepts, prefix in [
            ("SNOMED-CT", SNOMED_CONCEPTS, "snomed"),
            ("LOINC", LOINC_CONCEPTS, "loinc"),
            ("UBERON", UBERON_CONCEPTS, "uberon"),
            ("HPO", HPO_CONCEPTS, "hpo"),
        ]:
            created = self._create_concepts(ontology, concepts, prefix)
            results[f"{prefix}_concepts"] = created

        # ── 2. Build IS_A hierarchies ─────────────────────────────────
        for ontology, concepts, prefix in [
            ("SNOMED-CT", SNOMED_CONCEPTS, "snomed"),
            ("LOINC", LOINC_CONCEPTS, "loinc"),
            ("UBERON", UBERON_CONCEPTS, "uberon"),
            ("HPO", HPO_CONCEPTS, "hpo"),
        ]:
            edges = self._create_hierarchy(ontology, concepts, prefix)
            results[f"{prefix}_is_a"] = edges

        # ── 3. Create MAPS_TO relationships ──────────────────────────
        results["maps_to"] = {}
        results["maps_to"]["diagnosis_snomed"] = self._maps_to_diagnosis_snomed()
        results["maps_to"]["cognitive_loinc"] = self._maps_to_cognitive_loinc()
        results["maps_to"]["biomarker_loinc"] = self._maps_to_biomarker_loinc()
        results["maps_to"]["brain_region_uberon"] = self._maps_to_brain_region_uberon()

        # ── Summary ──────────────────────────────────────────────────
        self._print_summary(results)
        return results

    # ── Concept creation ──────────────────────────────────────────────

    def _create_concepts(
        self, ontology: str, concepts: list, prefix: str
    ) -> int:
        """Create OntologyConcept nodes for one ontology."""
        logger.info(f"Creating {ontology} OntologyConcept nodes ({len(concepts)})...")
        count = 0
        for code, label, _parent in concepts:
            uri = f"{prefix}:{code}"
            query = """
                MERGE (o:OntologyConcept {uri: $uri})
                ON CREATE SET
                    o.code = $code,
                    o.label = $label,
                    o.source_ontology = $ontology
                ON MATCH SET
                    o.label = $label
                RETURN o.uri AS uri
            """
            try:
                self.connector.run_query(query, {
                    "uri": uri, "code": code,
                    "label": label, "ontology": ontology,
                })
                count += 1
            except Exception as e:
                logger.error(f"  ❌ Concept {uri} failed: {e}")

        logger.info(f"  ✅ {count} {ontology} concepts created/updated")
        return count

    def _create_hierarchy(
        self, ontology: str, concepts: list, prefix: str
    ) -> int:
        """Create IS_A edges within an ontology."""
        logger.info(f"Building {ontology} IS_A hierarchy...")
        count = 0
        for code, _label, parent_code in concepts:
            if not parent_code:
                continue
            child_uri = f"{prefix}:{code}"
            parent_uri = f"{prefix}:{parent_code}"
            query = """
                MATCH (child:OntologyConcept {uri: $child_uri})
                MATCH (parent:OntologyConcept {uri: $parent_uri})
                MERGE (child)-[r:IS_A]->(parent)
                ON CREATE SET r.uri = 'rdfs:subClassOf'
                RETURN type(r) AS t
            """
            try:
                res = self.connector.run_query(query, {
                    "child_uri": child_uri,
                    "parent_uri": parent_uri,
                })
                if res:
                    count += 1
            except Exception as e:
                logger.error(f"  ❌ IS_A {child_uri} → {parent_uri}: {e}")

        logger.info(f"  ✅ {count} {ontology} IS_A edges")
        return count

    # ── MAPS_TO relationships ─────────────────────────────────────────

    def _maps_to_diagnosis_snomed(self) -> int:
        """Create MAPS_TO from Diagnosis → SNOMED-CT OntologyConcept via snomed_code."""
        logger.info("Creating MAPS_TO: Diagnosis → SNOMED-CT...")
        query = """
            MATCH (d:Diagnosis)
            WHERE d.snomed_code IS NOT NULL
            WITH d, 'snomed:' + d.snomed_code AS uri
            MATCH (o:OntologyConcept {uri: uri})
            MERGE (d)-[r:MAPS_TO]->(o)
            ON CREATE SET r.uri = 'skos:exactMatch'
            RETURN count(r) AS created
        """
        try:
            res = self.connector.run_query(query)
            count = res[0]["created"] if res else 0
            logger.info(f"  ✅ {count:,} Diagnosis → SNOMED MAPS_TO edges")
            return count
        except Exception as e:
            logger.error(f"  ❌ Diagnosis MAPS_TO failed: {e}")
            return 0

    def _maps_to_cognitive_loinc(self) -> int:
        """Create MAPS_TO from CognitiveAssessment → LOINC OntologyConcept via loinc_code."""
        logger.info("Creating MAPS_TO: CognitiveAssessment → LOINC...")
        query = """
            MATCH (c:CognitiveAssessment)
            WHERE c.loinc_code IS NOT NULL
            WITH c, 'loinc:' + c.loinc_code AS uri
            MATCH (o:OntologyConcept {uri: uri})
            MERGE (c)-[r:MAPS_TO]->(o)
            ON CREATE SET r.uri = 'skos:exactMatch'
            RETURN count(r) AS created
        """
        try:
            res = self.connector.run_query(query)
            count = res[0]["created"] if res else 0
            logger.info(f"  ✅ {count:,} CognitiveAssessment → LOINC MAPS_TO edges")
            return count
        except Exception as e:
            logger.error(f"  ❌ CognitiveAssessment MAPS_TO failed: {e}")
            return 0

    def _maps_to_biomarker_loinc(self) -> int:
        """Create MAPS_TO from Biomarker (CSF) → LOINC OntologyConcept via loinc_code."""
        logger.info("Creating MAPS_TO: Biomarker → LOINC...")
        query = """
            MATCH (b:Biomarker)
            WHERE b.loinc_code IS NOT NULL
            WITH b, 'loinc:' + b.loinc_code AS uri
            MATCH (o:OntologyConcept {uri: uri})
            MERGE (b)-[r:MAPS_TO]->(o)
            ON CREATE SET r.uri = 'skos:exactMatch'
            RETURN count(r) AS created
        """
        try:
            res = self.connector.run_query(query)
            count = res[0]["created"] if res else 0
            logger.info(f"  ✅ {count:,} Biomarker → LOINC MAPS_TO edges")
            return count
        except Exception as e:
            logger.error(f"  ❌ Biomarker MAPS_TO failed: {e}")
            return 0

    def _maps_to_brain_region_uberon(self) -> int:
        """Create MAPS_TO from BrainRegion → UBERON OntologyConcept via uberon_code."""
        logger.info("Creating MAPS_TO: BrainRegion → UBERON...")
        # uberon_code is stored as 'UBERON:0002421' but OntologyConcept.uri
        # uses 'uberon:0002421' — normalize by replacing the prefix
        query = """
            MATCH (b:BrainRegion)
            WHERE b.uberon_code IS NOT NULL
            WITH b, replace(b.uberon_code, 'UBERON:', 'uberon:') AS uri
            MATCH (o:OntologyConcept {uri: uri})
            MERGE (b)-[r:MAPS_TO]->(o)
            ON CREATE SET r.uri = 'skos:exactMatch'
            RETURN count(r) AS created
        """
        try:
            res = self.connector.run_query(query)
            count = res[0]["created"] if res else 0
            logger.info(f"  ✅ {count} BrainRegion → UBERON MAPS_TO edges")
            return count
        except Exception as e:
            logger.error(f"  ❌ BrainRegion MAPS_TO failed: {e}")
            return 0

    # ── Report ────────────────────────────────────────────────────────

    def _print_summary(self, results: Dict[str, Any]):
        """Print summary."""
        logger.info("")
        logger.info("=" * 60)
        logger.info("STEP 20 — ONTOLOGY LAYER SUMMARY")
        logger.info("=" * 60)
        logger.info(f"  SNOMED-CT concepts:  {results.get('snomed_concepts', 0)}")
        logger.info(f"  LOINC concepts:      {results.get('loinc_concepts', 0)}")
        logger.info(f"  UBERON concepts:     {results.get('uberon_concepts', 0)}")
        logger.info(f"  HPO concepts:        {results.get('hpo_concepts', 0)}")
        total_concepts = sum(
            results.get(f"{p}_concepts", 0)
            for p in ["snomed", "loinc", "uberon", "hpo"]
        )
        logger.info(f"  Total concepts:      {total_concepts}")
        logger.info("  ─────────────────────")
        logger.info(f"  SNOMED IS_A edges:   {results.get('snomed_is_a', 0)}")
        logger.info(f"  LOINC IS_A edges:    {results.get('loinc_is_a', 0)}")
        logger.info(f"  UBERON IS_A edges:   {results.get('uberon_is_a', 0)}")
        logger.info(f"  HPO IS_A edges:      {results.get('hpo_is_a', 0)}")
        total_isa = sum(
            results.get(f"{p}_is_a", 0)
            for p in ["snomed", "loinc", "uberon", "hpo"]
        )
        logger.info(f"  Total IS_A:          {total_isa}")
        logger.info("  ─────────────────────")
        maps = results.get("maps_to", {})
        for key, count in maps.items():
            logger.info(f"  MAPS_TO {key}: {count:,}")
        total_maps = sum(v for v in maps.values() if isinstance(v, int))
        logger.info(f"  Total MAPS_TO:       {total_maps:,}")
        logger.info("=" * 60)


# ══════════════════════════════════════════════════════════════════════
# Pipeline entry point
# ══════════════════════════════════════════════════════════════════════

def execute_ontology_layer(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    **kwargs,
) -> Dict[str, Any]:
    """Main execution function for Step 20."""
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)
    try:
        builder = OntologyLayerBuilder(connector)
        return builder.execute()
    except Exception as e:
        logger.error(f"Step 20 failed: {e}")
        raise
    finally:
        connector.close()


# ══════════════════════════════════════════════════════════════════════
# Standalone execution
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Step 20: Ontology Layer + MAPS_TO")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="your_password")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    results = execute_ontology_layer(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
    )
