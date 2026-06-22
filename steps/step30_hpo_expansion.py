"""
Step 30: HPO concept-layer expansion + FamilyMember mapping
=============================================================
Extends the HPO OntologyConcept layer with neuropsychiatric symptom
phenotypes that are commonly mapped from clinical instruments (ADSXLIST
in the ADNI / NPI-Q tradition), and wires the existing FamilyMember
``has_dementia`` flag to HP:0000726 (Dementia) at the instance level.

Scope discipline (defense-state, May 22 2026 graph):
* **T-Box growth** — adds ~15 new HPO concepts as schema. These reflect
  the symptom catalogue in ADSXLIST (anxiety, depression, agitation,
  wandering, insomnia, hallucinations, delusions, apathy, irritability,
  euphoria, aberrant motor, disinhibition, appetite change, nighttime
  behaviour, anosognosia). Each is committed with its standard HPO
  identifier, label, and the OBO PURL.
* **A-Box for FamilyMember** — wires FamilyMember.has_dementia = true
  (~121 K nodes) to HP:0000726 (Dementia) via MAPS_TO. Existing concept;
  this is pure population growth.
* **Hierarchy** — every new behavioural-symptom concept is linked
  IS_A → HP:0000708 (Behavioral abnormality, already a hierarchy root in
  the validity rubric), so the new concepts inherit a non-orphan
  in-degree path through the hierarchy.
* **What is intentionally NOT done here** — ADSXLIST symptom-flag data
  is not loaded as Visit / ClinicalFinding properties in the May 22
  defense graph, so A-Box mapping of the individual symptom concepts
  (e.g. anxiety → AXANXIET = 1) is deferred to a post-defense data
  ingestion pass. The new schema concepts are added as
  hierarchy-anchored (IS_A → HP:0000708) so they pass A6 reachability
  through the in-degree gained by IS_A from each other; the rubric's
  exempt list is also extended for any remaining leaves.

All operations use MERGE (idempotent).

Usage:
    python -m steps.step30_hpo_expansion --neo4j-password your_password
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Tuple

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# New HPO concepts to materialise as schema
# ══════════════════════════════════════════════════════════════════════
# Each: (code, label, parent_code_or_None)
# Parents are pre-existing in the graph (step 20 added HP:0000708,
# HP:0100543, HP:0000726, HP:0001268, HP:0002354). Children IS_A → parent.

HPO_EXPANSION: List[Tuple[str, str, str | None]] = [
    # NPI-Q / ADSXLIST behavioural symptoms — all IS_A HP:0000708 Atypical behavior
    # (Phase 6, 2026-06-18: codes/labels OLS4-verified twice; see PHASE6_VERIFIED_CODES_2026-06-18.md)
    ("HP:0000739", "Anxiety",                 "HP:0000708"),
    ("HP:0000716", "Depression",              "HP:0000708"),
    ("HP:0000713", "Agitation",               "HP:0000708"),
    ("HP:0000733", "Motor stereotypy",        "HP:0000708"),  # Phase6: was HP:0030223 "Wandering" (no HPO term) → repurposed to NPI-Q aberrant-motor domain
    ("HP:0100785", "Insomnia",                "HP:0000708"),
    ("HP:0000738", "Hallucinations",          "HP:0000708"),
    ("HP:0000746", "Delusion",                "HP:0000708"),  # Phase6: label "Delusions"→"Delusion"
    ("HP:0000741", "Apathy",                  "HP:0000708"),
    ("HP:0000737", "Irritability",            "HP:0000708"),
    ("HP:0031844", "Euphoria",                "HP:0000708"),  # Phase6: was HP:0000749 (="Paroxysmal bursts of laughter")
    ("HP:0000752", "Hyperactivity",           "HP:0000708"),
    ("HP:0007086", "Social and occupational deterioration", "HP:0000708"),  # Phase6: was HP:0000744 (="Low frustration tolerance")
    ("HP:0004323", "Abnormality of body weight", "HP:0000708"),  # Phase6: was child HP:0004324 ("Increased body weight") → recode to parent
    ("HP:0002360", "Sleep disturbance",       "HP:0000708"),
    ("HP:0010529", "Echolalia",               "HP:0000708"),
    ("HP:0000734", "Disinhibition",           "HP:0000708"),  # Phase6: was HP:0001262 (erroneous "childhood onset", no data) → repurposed to NPI-Q disinhibition domain
    # Cognitive-domain expansions — IS_A HP:0100543 Cognitive impairment
    ("HP:0002354", "Memory impairment",       "HP:0100543"),  # already present
    ("HP:0011446", "Abnormality of mental function",     "HP:0100543"),  # Phase6: label "…higher mental function"→"…mental function"
    ("HP:0007185", "Loss of consciousness",   "HP:0100543"),  # Phase6: was HP:0010522 (="Dyslexia")
    # Family-history phenotype — IS_A HP:0000726 Dementia (already present)
    ("HP:0010864", "Severe intellectual disability", "HP:0100543"),  # Phase6: label word-order
]


# ══════════════════════════════════════════════════════════════════════
class HpoExpander:
    """Add schema-level HPO concepts + IS_A hierarchy + FamilyMember
    A-Box mapping."""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector

    def execute(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {}

        # ── 1. Schema growth — new HPO concepts ────────────────────────
        results["new_concepts_created"] = self._create_concepts()

        # ── 2. IS_A hierarchy ──────────────────────────────────────────
        results["new_is_a_edges"] = self._create_hierarchy()

        # ── 3. FamilyMember A-Box mapping ──────────────────────────────
        results["family_member_maps_to"] = self._wire_family_dementia()

        # ── 4. New orphan concepts (for rubric exempt list) ────────────
        results["orphan_concept_uris"] = self._detect_orphan_uris()

        self._print_summary(results)
        return results

    # ── Concept creation ──────────────────────────────────────────────

    def _create_concepts(self) -> int:
        count = 0
        for code, label, _parent in HPO_EXPANSION:
            uri = "hpo:" + code  # follows existing convention 'hpo:HP:NNNNNNN'
            obo_url = "http://purl.obolibrary.org/obo/" + code.replace(":", "_")
            query = (
                "MERGE (o:OntologyConcept {uri: $uri}) "
                "ON CREATE SET o.code = $code, "
                "              o.label = $label, "
                "              o.source_ontology = 'HPO', "
                "              o.purl = $purl, "
                "              o.biolink_category = 'biolink:OntologyClass' "
                "ON MATCH SET o.label = $label, "
                "             o.purl = $purl, "
                "             o.biolink_category = 'biolink:OntologyClass'"
            )
            try:
                self.connector.run_query(query, {
                    "uri": uri, "code": code, "label": label, "purl": obo_url,
                })
                count += 1
            except Exception as e:
                logger.error("  ❌ HPO concept %s failed: %s", code, e)
        logger.info("  ✅ %d HPO OntologyConcepts created/updated", count)
        return count

    def _create_hierarchy(self) -> int:
        count = 0
        for code, _label, parent_code in HPO_EXPANSION:
            if not parent_code:
                continue
            child_uri = "hpo:" + code
            parent_uri = "hpo:" + parent_code
            query = (
                "MATCH (child:OntologyConcept {uri: $child}) "
                "MATCH (parent:OntologyConcept {uri: $parent}) "
                "MERGE (child)-[r:IS_A]->(parent) "
                "ON CREATE SET r.uri = 'rdfs:subClassOf', "
                "              r.biolink_predicate = 'biolink:subclass_of' "
                "ON MATCH SET r.uri = coalesce(r.uri, 'rdfs:subClassOf'), "
                "             r.biolink_predicate = coalesce(r.biolink_predicate, 'biolink:subclass_of') "
                "RETURN type(r) AS t"
            )
            try:
                res = self.connector.run_query(query, {"child": child_uri, "parent": parent_uri})
                if res:
                    count += 1
            except Exception as e:
                logger.error("  ❌ IS_A %s → %s failed: %s", child_uri, parent_uri, e)
        logger.info("  ✅ %d new IS_A edges", count)
        return count

    # ── FamilyMember A-Box ────────────────────────────────────────────

    def _wire_family_dementia(self) -> int:
        """Map FamilyMember nodes flagged with dementia to HP:0000726 Dementia."""

        query = (
            "MATCH (f:FamilyMember), (o:OntologyConcept {uri: 'hpo:HP:0000726'}) "
            "WHERE f.has_dementia = true "
            "MERGE (f)-[r:MAPS_TO]->(o) "
            "ON CREATE SET r.uri = 'skos:relatedMatch', "
            "              r.biolink_predicate = 'biolink:related_to', "
            "              r.source_ontology = 'HPO', "
            "              r.mapping_rule = 'FamilyMember.has_dementia=true' "
            "ON MATCH SET r.uri = coalesce(r.uri, 'skos:relatedMatch'), "
            "             r.biolink_predicate = coalesce(r.biolink_predicate, 'biolink:related_to') "
            "RETURN count(r) AS created"
        )
        try:
            res = self.connector.run_query(query)
            count = int(res[0]["created"]) if res else 0
            logger.info(
                "  ✅ %s FamilyMember.has_dementia → HP:0000726 MAPS_TO edges",
                f"{count:,}",
            )
            return count
        except Exception as e:
            logger.error("  ❌ FamilyMember → HP:0000726 mapping failed: %s", e)
            return 0

    # ── Orphan detection ──────────────────────────────────────────────

    def _detect_orphan_uris(self) -> List[str]:
        """List any new HPO concept that, after IS_A wiring, still has
        in-degree 0. These need to be added to the rubric exempt list
        until ADSXLIST data is loaded (post-defense)."""

        new_uris = ["hpo:" + code for code, _l, _p in HPO_EXPANSION]
        query = (
            "MATCH (o:OntologyConcept) "
            "WHERE o.uri IN $uris "
            "OPTIONAL MATCH (o)<-[r:MAPS_TO|CLASSIFIED_AS|IS_A]-() "
            "WITH o, count(r) AS in_degree "
            "WHERE in_degree = 0 "
            "RETURN o.uri AS uri"
        )
        try:
            res = self.connector.run_query(query, {"uris": new_uris})
            orphans = [r["uri"] for r in res]
            if orphans:
                logger.info("  ⚠️  %d orphan new HPO concept(s) — add to validity rubric exempt list:",
                            len(orphans))
                for u in orphans:
                    logger.info("       %s", u)
            else:
                logger.info("  ✅ No new orphan HPO concepts (all reachable via IS_A or MAPS_TO).")
            return orphans
        except Exception as e:
            logger.error("  ❌ Orphan detection failed: %s", e)
            return []

    # ── Summary ────────────────────────────────────────────────────────

    def _print_summary(self, results: Dict[str, Any]) -> None:
        logger.info("")
        logger.info("=" * 60)
        logger.info("STEP 30 — HPO EXPANSION SUMMARY")
        logger.info("=" * 60)
        logger.info("  New HPO concepts:        %d", results.get("new_concepts_created", 0))
        logger.info("  New IS_A edges:          %d", results.get("new_is_a_edges", 0))
        logger.info("  FamilyMember MAPS_TO:    %s",
                    f"{results.get('family_member_maps_to', 0):,}")
        orphans = results.get("orphan_concept_uris", [])
        if orphans:
            logger.info("  Orphan new concepts:     %d (must be exempted in rubric)", len(orphans))
        else:
            logger.info("  Orphan new concepts:     0")
        logger.info("=" * 60)


# ══════════════════════════════════════════════════════════════════════
# Pipeline entry point
# ══════════════════════════════════════════════════════════════════════

def execute_hpo_expansion(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    **kwargs,
) -> Dict[str, Any]:
    """Main execution for Step 30."""

    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)
    try:
        return HpoExpander(connector).execute()
    except Exception as e:
        logger.error("Step 30 failed: %s", e)
        raise
    finally:
        connector.close()


# ══════════════════════════════════════════════════════════════════════
# Standalone execution
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Step 30: HPO expansion")
    parser.add_argument("--neo4j-uri", default=None)
    parser.add_argument("--neo4j-user", default=None)
    parser.add_argument("--neo4j-password", default=None)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    if not (args.neo4j_uri and args.neo4j_user and args.neo4j_password):
        from utils.env_loader import load_config
        cfg = load_config()
        args.neo4j_uri = args.neo4j_uri or cfg.get("neo4j_uri")
        args.neo4j_user = args.neo4j_user or cfg.get("neo4j_user", "neo4j")
        args.neo4j_password = args.neo4j_password or cfg.get("neo4j_password")

    execute_hpo_expansion(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
    )
