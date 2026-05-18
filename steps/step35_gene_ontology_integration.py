"""
Step 35: Gene Ontology integration (closes Contribution 4)
============================================================
Bridges the molecular-clinical gap by materialising:

1. **Gene nodes** for APOE (primary, the only patient-side gene with data)
   plus four optional AD-relevant genes (APP, PSEN1, PSEN2, MAPT) that AlzKB
   already carries on its side. Each Gene node carries the standard external
   identifiers (NCBI Gene, HGNC, UniProt) so cross-KG alignment is direct.
2. **10 GO OntologyConcept nodes** (source_ontology='GO') spanning the three
   Gene Ontology aspects — Molecular Function, Biological Process, Cellular
   Component — restricted to terms with well-characterised APOE involvement.
3. **PARTICIPATES_IN** relationships: APOE Gene → its 10 GO terms.
4. **ENCODES** relationships: GeneticMarker → Gene for the 2,426 markers in
   the graph (all currently carry gene='APOE').
5. **SAME_AS** relationships: AlzKBConcept(source_type='Gene') → Gene for the
   five genes we materialise — this is what flips the AlzKB Gene-category
   alignment from N/A to a measurable match.

Effects on metrics:
* Source ontologies in the graph: 7 → **8** (GO added).
* OntologyConcept count: +10 (all GO).
* New node label `:Gene` with 5 instances.
* New relationship types `PARTICIPATES_IN` and `ENCODES`.
* AlzKB alignment: Gene category goes from `not_implemented: true` to a
  measurable per-category rate.

This closes the only outstanding contribution-table item (C4 — Gene
Ontology) that had been deferred since the original v3 plan. All other
contribution-table items (HPO expansion, LOINC vitals, MEDHIST, Biolink,
MONDO/DOID) are either implemented (Steps 30, 33, 34) or
data-ingestion-blocked.

All operations use MERGE (idempotent).

Usage:
    python -m steps.step35_gene_ontology_integration --neo4j-password your_password
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Tuple

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Gene catalogue — APOE + 4 AD-relevant genes already present in AlzKB
# ══════════════════════════════════════════════════════════════════════
# (symbol, ncbi_gene_id, hgnc_id, uniprot_id, full_name)

GENE_CATALOGUE: List[Tuple[str, str, str, str, str]] = [
    ("APOE",  "348",  "HGNC:613",  "P02649", "Apolipoprotein E"),
    ("APP",   "351",  "HGNC:620",  "P05067", "Amyloid beta precursor protein"),
    ("PSEN1", "5663", "HGNC:9508", "P49768", "Presenilin 1"),
    ("PSEN2", "5664", "HGNC:9509", "P49810", "Presenilin 2"),
    ("MAPT",  "4137", "HGNC:6893", "P10636", "Microtubule associated protein tau"),
]


# ══════════════════════════════════════════════════════════════════════
# GO concept catalogue — APOE-relevant terms across MF / BP / CC
# ══════════════════════════════════════════════════════════════════════
# (go_code, label, aspect)
#   MF = Molecular Function
#   BP = Biological Process
#   CC = Cellular Component
# Each is annotated against APOE in UniProt / GOA at the time of writing.

GO_CONCEPTS: List[Tuple[str, str, str]] = [
    # Molecular Function
    ("GO:0001540", "Amyloid-beta binding",                "MF"),
    ("GO:0008289", "Lipid binding",                       "MF"),
    ("GO:0005509", "Calcium ion binding",                 "MF"),
    # Biological Process
    ("GO:0042632", "Cholesterol homeostasis",             "BP"),
    ("GO:0006869", "Lipid transport",                     "BP"),
    ("GO:0042157", "Lipoprotein metabolic process",       "BP"),
    ("GO:0007568", "Aging",                               "BP"),
    # Cellular Component
    ("GO:0005576", "Extracellular region",                "CC"),
    ("GO:0034364", "High-density lipoprotein particle",   "CC"),
    ("GO:0034362", "Low-density lipoprotein particle",    "CC"),
]


# Aspect → root concept (3 GO top-of-tree concepts). We do NOT materialise
# the roots themselves; we only annotate `o.go_aspect` on the 10 leaves so
# downstream queries can group by aspect.
ASPECT_NAMES = {
    "MF": "Molecular Function",
    "BP": "Biological Process",
    "CC": "Cellular Component",
}


# ══════════════════════════════════════════════════════════════════════
class GeneOntologyIntegrator:
    """Materialise Gene nodes + GO OntologyConcept layer + bridging edges."""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector

    def execute(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {}

        results["gene_nodes_created"] = self._create_gene_nodes()
        results["go_concepts_created"] = self._create_go_concepts()
        results["participates_in_edges"] = self._wire_apoe_participates_in()
        results["encodes_edges"] = self._wire_genetic_marker_encodes()
        results["alzkb_same_as_edges"] = self._wire_alzkb_same_as()

        self._print_summary(results)
        return results

    # ── Gene nodes ────────────────────────────────────────────────────

    def _create_gene_nodes(self) -> int:
        count = 0
        for symbol, ncbi, hgnc, uniprot, full_name in GENE_CATALOGUE:
            query = (
                "MERGE (g:Gene {symbol: $symbol}) "
                "ON CREATE SET "
                "    g.ncbi_gene_id = $ncbi, "
                "    g.hgnc_id = $hgnc, "
                "    g.uniprot_id = $uniprot, "
                "    g.full_name = $full_name, "
                "    g.biolink_category = 'biolink:Gene', "
                "    g.source = 'NCBI Gene + HGNC + UniProt', "
                "    g.uri = 'http://identifiers.org/ncbigene/' + $ncbi "
                "ON MATCH SET "
                "    g.ncbi_gene_id = $ncbi, "
                "    g.hgnc_id = $hgnc, "
                "    g.uniprot_id = $uniprot, "
                "    g.full_name = $full_name, "
                "    g.biolink_category = coalesce(g.biolink_category, 'biolink:Gene'), "
                "    g.uri = 'http://identifiers.org/ncbigene/' + $ncbi "
                "RETURN g.symbol AS s"
            )
            try:
                self.connector.run_query(query, {
                    "symbol": symbol, "ncbi": ncbi, "hgnc": hgnc,
                    "uniprot": uniprot, "full_name": full_name,
                })
                count += 1
                logger.info("  ✅ Gene %s (NCBI:%s, HGNC:%s, UniProt:%s)",
                            symbol, ncbi, hgnc, uniprot)
            except Exception as e:
                logger.error("  ❌ Gene %s failed: %s", symbol, e)
        return count

    # ── GO OntologyConcept nodes ──────────────────────────────────────

    def _create_go_concepts(self) -> int:
        count = 0
        for code, label, aspect in GO_CONCEPTS:
            # Match the existing OntologyConcept URI scheme: lowercase prefix
            # then identifier. Step 20 uses 'snomed:64572001', 'hpo:HP:0100543'
            # etc. — we follow the same `<prefix>:<code>` pattern.
            uri = "go:" + code  # e.g. 'go:GO:0001540'
            purl = "http://purl.obolibrary.org/obo/" + code.replace(":", "_")
            query = (
                "MERGE (o:OntologyConcept {uri: $uri}) "
                "ON CREATE SET "
                "    o.code = $code, "
                "    o.label = $label, "
                "    o.source_ontology = 'GO', "
                "    o.purl = $purl, "
                "    o.go_aspect = $aspect, "
                "    o.go_aspect_name = $aspect_name, "
                "    o.biolink_category = 'biolink:OntologyClass' "
                "ON MATCH SET "
                "    o.label = $label, "
                "    o.go_aspect = $aspect, "
                "    o.go_aspect_name = $aspect_name, "
                "    o.biolink_category = coalesce(o.biolink_category, 'biolink:OntologyClass')"
            )
            try:
                self.connector.run_query(query, {
                    "uri": uri, "code": code, "label": label, "purl": purl,
                    "aspect": aspect, "aspect_name": ASPECT_NAMES[aspect],
                })
                count += 1
                logger.info("  ✅ GO %s [%s] %s", code, aspect, label)
            except Exception as e:
                logger.error("  ❌ GO concept %s failed: %s", code, e)
        return count

    # ── PARTICIPATES_IN (Gene → GO) ───────────────────────────────────

    def _wire_apoe_participates_in(self) -> int:
        """APOE → all 10 GO concepts. Other genes get no PARTICIPATES_IN
        edges in this step — the GO annotation set is restricted to APOE
        because that is the gene with patient-side data."""

        total = 0
        for code, _label, _aspect in GO_CONCEPTS:
            uri = "go:" + code
            query = (
                "MATCH (g:Gene {symbol: 'APOE'}), (o:OntologyConcept {uri: $uri}) "
                "MERGE (g)-[r:PARTICIPATES_IN]->(o) "
                "ON CREATE SET "
                "    r.uri = 'ro:RO_0000056', "
                "    r.biolink_predicate = 'biolink:participates_in', "
                "    r.source = 'GOA APOE annotation set' "
                "ON MATCH SET "
                "    r.uri = coalesce(r.uri, 'ro:RO_0000056'), "
                "    r.biolink_predicate = coalesce(r.biolink_predicate, 'biolink:participates_in')"
            )
            try:
                self.connector.run_query(query, {"uri": uri})
                total += 1
            except Exception as e:
                logger.error("  ❌ APOE PARTICIPATES_IN %s failed: %s", code, e)
        logger.info("  ✅ %d PARTICIPATES_IN edges (APOE → GO)", total)
        return total

    # ── ENCODES (GeneticMarker → Gene) ────────────────────────────────

    def _wire_genetic_marker_encodes(self) -> int:
        """GeneticMarker.gene='APOE' → Gene(symbol='APOE'). All 2,426
        existing GeneticMarker nodes carry gene='APOE' (verified May 16)."""

        query = (
            "MATCH (m:GeneticMarker) "
            "WHERE m.gene IS NOT NULL "
            "MATCH (g:Gene {symbol: m.gene}) "
            "MERGE (m)-[r:ENCODES]->(g) "
            "ON CREATE SET "
            "    r.uri = 'ro:RO_0002205', "
            "    r.biolink_predicate = 'biolink:encodes', "
            "    r.source = 'GeneticMarker.gene field' "
            "ON MATCH SET "
            "    r.uri = coalesce(r.uri, 'ro:RO_0002205'), "
            "    r.biolink_predicate = coalesce(r.biolink_predicate, 'biolink:encodes') "
            "RETURN count(r) AS created"
        )
        try:
            res = self.connector.run_query(query)
            n = int(res[0]["created"]) if res else 0
            logger.info("  ✅ %s ENCODES edges (GeneticMarker → Gene)", f"{n:,}")
            return n
        except Exception as e:
            logger.error("  ❌ GeneticMarker → Gene ENCODES failed: %s", e)
            return 0

    # ── SAME_AS (AlzKBConcept → Gene) ─────────────────────────────────

    def _wire_alzkb_same_as(self) -> int:
        """AlzKBConcept(source_type='Gene') already has a `label` field
        matching the gene symbol (verified May 16: e.g. label='APOE',
        alzkb_id='alzkb:gene_APOE'). Link to our :Gene by shared symbol."""

        query = (
            "MATCH (a:AlzKBConcept) "
            "WHERE a.source_type = 'Gene' "
            "MATCH (g:Gene {symbol: a.label}) "
            "MERGE (a)-[r:SAME_AS]->(g) "
            "ON CREATE SET "
            "    r.uri = 'skos:exactMatch', "
            "    r.biolink_predicate = 'biolink:same_as', "
            "    r.source = 'Step 35 — Gene symbol exact match' "
            "ON MATCH SET "
            "    r.uri = coalesce(r.uri, 'skos:exactMatch'), "
            "    r.biolink_predicate = coalesce(r.biolink_predicate, 'biolink:same_as') "
            "RETURN count(r) AS created"
        )
        try:
            res = self.connector.run_query(query)
            n = int(res[0]["created"]) if res else 0
            logger.info("  ✅ %d SAME_AS edges (AlzKBConcept Gene → Gene)", n)
            return n
        except Exception as e:
            logger.error("  ❌ AlzKB → Gene SAME_AS failed: %s", e)
            return 0

    # ── Summary ────────────────────────────────────────────────────────

    def _print_summary(self, results: Dict[str, Any]) -> None:
        logger.info("")
        logger.info("=" * 60)
        logger.info("STEP 35 — GENE ONTOLOGY INTEGRATION SUMMARY")
        logger.info("=" * 60)
        logger.info("  Gene nodes:               %d", results.get("gene_nodes_created", 0))
        logger.info("  GO OntologyConcepts:      %d", results.get("go_concepts_created", 0))
        logger.info("  PARTICIPATES_IN (Gene→GO):%d", results.get("participates_in_edges", 0))
        logger.info("  ENCODES (GeneticMarker→Gene):%s",
                    f"{results.get('encodes_edges', 0):,}")
        logger.info("  SAME_AS (AlzKB Gene→Gene):  %d",
                    results.get("alzkb_same_as_edges", 0))
        logger.info("=" * 60)


# ══════════════════════════════════════════════════════════════════════
# Pipeline entry point
# ══════════════════════════════════════════════════════════════════════


def execute_gene_ontology_integration(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    **kwargs,
) -> Dict[str, Any]:
    """Main execution for Step 35."""

    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)
    try:
        return GeneOntologyIntegrator(connector).execute()
    except Exception as e:
        logger.error("Step 35 failed: %s", e)
        raise
    finally:
        connector.close()


# ══════════════════════════════════════════════════════════════════════
# Standalone execution
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Step 35: Gene Ontology integration (Contribution 4)"
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

    execute_gene_ontology_integration(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
    )
