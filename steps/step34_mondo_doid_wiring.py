"""
Step 34: MONDO + DOID OntologyConcept layer wiring
====================================================
Wires the existing ``Diagnosis.mondo_code`` properties (set by step 18)
into the OntologyConcept layer, and adds three DOID concepts (AD,
dementia, MCI) per the contribution-table commitment.

Closes the second half of Contribution 7's interoperability claim:
the graph now distinguishes 7 source ontologies (SNOMED-CT, LOINC,
UBERON, HPO, ICD-10, **MONDO, DOID**) rather than 5, giving Diagnosis
nodes identifier overlap with AlzKB's molecular-side Disease entities
that use DOID.

All operations use MERGE — idempotent.

Usage:
    python -m steps.step34_mondo_doid_wiring --neo4j-password your_password
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Tuple

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# MONDO + DOID concept definitions
# ══════════════════════════════════════════════════════════════════════

# Curated label lookup for MONDO codes that already exist as Diagnosis
# properties. Codes not in this map are still wired (with code-as-label)
# so completeness is independent of this dict; the lookup just adds a
# human-readable label.
MONDO_LABELS: Dict[str, str] = {
    # MONDO:0024647 removed 2026-06-17 — it is "urolithiasis", not MCI (OLS4-verified).
    # MCI has no MONDO disease term; it stays grounded by SNOMED 386806002 / ICD-10 F06.7 / DOID:0080832.
    "MONDO:0004975": "Alzheimer's disease",
    "MONDO:0001627": "Dementia",
    "MONDO:0011913": "Alzheimer disease, late-onset",
    "MONDO:0019262": "Late-onset Alzheimer disease",
}

# Three DOID concepts to add explicitly (per contribution table).
# Maps the canonical Diagnosis.diagnosis_code values to DOID identifiers.
DOID_CONCEPTS: List[Tuple[str, str, List[str]]] = [
    # (doid_code, label, list_of_diagnosis_codes_to_map_from)
    ("DOID:10652",   "Alzheimer's disease",      ["AD"]),
    ("DOID:1307",    "Dementia",                 ["Dementia"]),
    ("DOID:0080832", "Mild cognitive impairment", ["MCI", "LMCI", "EMCI"]),
]


# ══════════════════════════════════════════════════════════════════════
class MondoDoidWirer:
    """Create MONDO + DOID OntologyConcept nodes and wire MAPS_TO from
    existing Diagnosis nodes."""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector

    def execute(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {}

        # ── 1. MONDO concepts + MAPS_TO ────────────────────────────────
        results["mondo_concepts_created"] = self._create_mondo_concepts()
        results["mondo_maps_to_edges"] = self._wire_diagnosis_to_mondo()

        # ── 2. DOID concepts + MAPS_TO ────────────────────────────────
        results["doid_concepts_created"] = self._create_doid_concepts()
        results["doid_maps_to_edges"] = self._wire_diagnosis_to_doid()

        # ── 3. Add diagnosis_code → DOID property on Diagnosis nodes ──
        # Makes the DOID identifier discoverable from the Diagnosis node
        # itself, mirroring the existing `mondo_code` property pattern.
        results["doid_code_property_added"] = self._set_doid_code_property()

        self._print_summary(results)
        return results

    # ── MONDO ───────────────────────────────────────────────────────────

    def _create_mondo_concepts(self) -> int:
        """For every distinct MONDO code on Diagnosis nodes, create an
        OntologyConcept(source_ontology='MONDO') node."""

        # First, harvest the codes from the graph.
        rows = self.connector.run_query(
            "MATCH (d:Diagnosis) "
            "WHERE d.mondo_code IS NOT NULL AND d.mondo_code <> '' "
            "RETURN DISTINCT d.mondo_code AS code"
        )
        codes = [r["code"] for r in rows]
        logger.info("Found %d distinct MONDO codes on Diagnosis nodes", len(codes))

        count = 0
        for code in codes:
            label = MONDO_LABELS.get(code, code)
            uri = "mondo:" + code.replace("MONDO:", "")
            obo_url = "http://purl.obolibrary.org/obo/MONDO_" + code.replace("MONDO:", "")
            query = (
                "MERGE (o:OntologyConcept {uri: $uri}) "
                "ON CREATE SET o.code = $code, "
                "              o.label = $label, "
                "              o.source_ontology = 'MONDO', "
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
                logger.error("  ❌ MONDO concept %s failed: %s", code, e)

        logger.info("  ✅ %d MONDO OntologyConcept nodes created/updated", count)
        return count

    def _wire_diagnosis_to_mondo(self) -> int:
        """Create MAPS_TO from Diagnosis → MONDO OntologyConcept via mondo_code."""

        query = (
            "MATCH (d:Diagnosis) "
            "WHERE d.mondo_code IS NOT NULL AND d.mondo_code <> '' "
            "WITH d, 'mondo:' + replace(d.mondo_code, 'MONDO:', '') AS uri "
            "MATCH (o:OntologyConcept {uri: uri}) "
            "MERGE (d)-[r:MAPS_TO]->(o) "
            "ON CREATE SET r.uri = 'skos:exactMatch', "
            "              r.biolink_predicate = 'biolink:exact_match', "
            "              r.source_ontology = 'MONDO' "
            "ON MATCH SET r.uri = coalesce(r.uri, 'skos:exactMatch'), "
            "             r.biolink_predicate = coalesce(r.biolink_predicate, 'biolink:exact_match') "
            "RETURN count(r) AS created"
        )
        try:
            res = self.connector.run_query(query)
            count = int(res[0]["created"]) if res else 0
            logger.info("  ✅ %s Diagnosis → MONDO MAPS_TO edges", f"{count:,}")
            return count
        except Exception as e:
            logger.error("  ❌ Diagnosis → MONDO MAPS_TO failed: %s", e)
            return 0

    # ── DOID ───────────────────────────────────────────────────────────

    def _create_doid_concepts(self) -> int:
        count = 0
        for doid_code, label, _diagnoses in DOID_CONCEPTS:
            uri = "doid:" + doid_code.replace("DOID:", "")
            obo_url = "http://purl.obolibrary.org/obo/DOID_" + doid_code.replace("DOID:", "")
            query = (
                "MERGE (o:OntologyConcept {uri: $uri}) "
                "ON CREATE SET o.code = $code, "
                "              o.label = $label, "
                "              o.source_ontology = 'DOID', "
                "              o.purl = $purl, "
                "              o.biolink_category = 'biolink:OntologyClass' "
                "ON MATCH SET o.label = $label, "
                "             o.purl = $purl, "
                "             o.biolink_category = 'biolink:OntologyClass'"
            )
            try:
                self.connector.run_query(query, {
                    "uri": uri, "code": doid_code, "label": label, "purl": obo_url,
                })
                count += 1
                logger.info("  ✅ DOID concept %s (%s)", doid_code, label)
            except Exception as e:
                logger.error("  ❌ DOID concept %s failed: %s", doid_code, e)
        logger.info("  ✅ %d DOID OntologyConcept nodes created/updated", count)
        return count

    def _wire_diagnosis_to_doid(self) -> int:
        total = 0
        for doid_code, label, dx_codes in DOID_CONCEPTS:
            uri = "doid:" + doid_code.replace("DOID:", "")
            # Match Diagnosis nodes via diagnosis_code (the canonical column).
            query = (
                "MATCH (d:Diagnosis), (o:OntologyConcept {uri: $uri}) "
                "WHERE d.diagnosis_code IN $codes "
                "MERGE (d)-[r:MAPS_TO]->(o) "
                "ON CREATE SET r.uri = 'skos:exactMatch', "
                "              r.biolink_predicate = 'biolink:exact_match', "
                "              r.source_ontology = 'DOID' "
                "ON MATCH SET r.uri = coalesce(r.uri, 'skos:exactMatch'), "
                "             r.biolink_predicate = coalesce(r.biolink_predicate, 'biolink:exact_match') "
                "RETURN count(r) AS created"
            )
            try:
                res = self.connector.run_query(query, {"uri": uri, "codes": dx_codes})
                created = int(res[0]["created"]) if res else 0
                logger.info(
                    "  ✅ %s → %s: %s MAPS_TO edges (diagnosis_code in %s)",
                    doid_code, label, f"{created:,}", dx_codes,
                )
                total += created
            except Exception as e:
                logger.error("  ❌ Diagnosis → %s MAPS_TO failed: %s", doid_code, e)
        return total

    # ── doid_code property on Diagnosis ──────────────────────────────

    def _set_doid_code_property(self) -> int:
        """Set d.doid_code property on Diagnosis nodes, mirroring the
        existing mondo_code pattern from step 18. Discoverable by
        downstream metric scripts."""

        rows_total = 0
        for doid_code, _label, dx_codes in DOID_CONCEPTS:
            query = (
                "MATCH (d:Diagnosis) "
                "WHERE d.diagnosis_code IN $codes "
                "SET d.doid_code = $doid "
                "RETURN count(d) AS n"
            )
            try:
                res = self.connector.run_query(query, {"codes": dx_codes, "doid": doid_code})
                rows_total += int(res[0]["n"]) if res else 0
            except Exception as e:
                logger.error("  ❌ doid_code property for %s failed: %s", doid_code, e)
        logger.info("  ✅ doid_code property set on %s Diagnosis nodes", f"{rows_total:,}")
        return rows_total

    # ── Summary ────────────────────────────────────────────────────────

    def _print_summary(self, results: Dict[str, Any]) -> None:
        logger.info("")
        logger.info("=" * 60)
        logger.info("STEP 34 — MONDO + DOID WIRING SUMMARY")
        logger.info("=" * 60)
        logger.info("  MONDO OntologyConcepts: %d", results.get("mondo_concepts_created", 0))
        logger.info("  MONDO MAPS_TO edges:    %s",
                    f"{results.get('mondo_maps_to_edges', 0):,}")
        logger.info("  DOID OntologyConcepts:  %d", results.get("doid_concepts_created", 0))
        logger.info("  DOID MAPS_TO edges:     %s",
                    f"{results.get('doid_maps_to_edges', 0):,}")
        logger.info("  doid_code property set: %s",
                    f"{results.get('doid_code_property_added', 0):,} Diagnosis nodes")
        logger.info("=" * 60)


# ══════════════════════════════════════════════════════════════════════
# Pipeline entry point
# ══════════════════════════════════════════════════════════════════════

def execute_mondo_doid_wiring(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    **kwargs,
) -> Dict[str, Any]:
    """Main execution for Step 34."""

    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)
    try:
        return MondoDoidWirer(connector).execute()
    except Exception as e:
        logger.error("Step 34 failed: %s", e)
        raise
    finally:
        connector.close()


# ══════════════════════════════════════════════════════════════════════
# Standalone execution
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Step 34: MONDO + DOID OntologyConcept layer wiring"
    )
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

    execute_mondo_doid_wiring(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
    )
