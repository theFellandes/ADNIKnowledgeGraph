"""
Step 18: Add Ontology Properties (In-Place Upgrade)
=====================================================
Enriches existing nodes with semantic codes (SNOMED-CT, LOINC, UBERON,
ICD-10, RxNorm, NCI Thesaurus) and adds URI properties to relationships.

All operations use SET (idempotent — re-running is safe).

Usage:
    python -m steps.step18_add_ontology_properties --neo4j-password your_password
"""

import logging
from typing import Dict, Any, List, Tuple

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Ontology Mapping Dictionaries
# ══════════════════════════════════════════════════════════════════════

# ── Diagnosis mappings ────────────────────────────────────────────────
# Keyed by diagnosis_code (actual values in graph: CN, MCI, AD, etc.)
DIAGNOSIS_MAPPINGS: Dict[str, Dict[str, str]] = {
    "CN": {
        "snomed_code": "17621005",
        "snomed_label": "Normal (finding)",
        "icd10_code": "Z03.89",
        "icd10_label": "No diagnosis or condition",
        "mondo_code": "",
        "rdf_type": "ncit:C94342",  # Cognitively Normal
    },
    "MCI": {
        "snomed_code": "386806002",
        "snomed_label": "Mild cognitive impairment",
        "icd10_code": "F06.7",
        "icd10_label": "Mild cognitive disorder",
        "mondo_code": "MONDO:0024647",
        "rdf_type": "ncit:C100044",
    },
    "LMCI": {
        "snomed_code": "386806002",
        "snomed_label": "Mild cognitive impairment (late)",
        "icd10_code": "F06.7",
        "icd10_label": "Mild cognitive disorder",
        "mondo_code": "MONDO:0024647",
        "rdf_type": "ncit:C100044",
    },
    "EMCI": {
        "snomed_code": "386806002",
        "snomed_label": "Mild cognitive impairment (early)",
        "icd10_code": "F06.7",
        "icd10_label": "Mild cognitive disorder",
        "mondo_code": "MONDO:0024647",
        "rdf_type": "ncit:C100044",
    },
    "AD": {
        "snomed_code": "26929004",
        "snomed_label": "Alzheimer's disease",
        "icd10_code": "G30.9",
        "icd10_label": "Alzheimer disease, unspecified",
        "mondo_code": "MONDO:0004975",
        "rdf_type": "ncit:C2866",
    },
    "Dementia": {
        "snomed_code": "52448006",
        "snomed_label": "Dementia",
        "icd10_code": "F03.9",
        "icd10_label": "Unspecified dementia",
        "mondo_code": "MONDO:0001627",
        "rdf_type": "ncit:C4786",
    },
    "SMC": {
        "snomed_code": "386807006",
        "snomed_label": "Subjective memory complaint",
        "icd10_code": "R41.3",
        "icd10_label": "Other amnesia",
        "mondo_code": "",
        "rdf_type": "ncit:C176715",
    },
}

# ── CognitiveAssessment → LOINC ──────────────────────────────────────
# Keyed by test_name (actual values in graph)
COGNITIVE_LOINC: Dict[str, Dict[str, str]] = {
    "MMSE": {
        "loinc_code": "72106-8",
        "loinc_label": "Mini-Mental State Examination total score",
    },
    "CDR": {
        "loinc_code": "72172-0",
        "loinc_label": "Clinical Dementia Rating global score",
    },
    "FAQ": {
        "loinc_code": "71130-0",
        "loinc_label": "Functional Activities Questionnaire total score",
    },
    "ADAS-Cog": {
        "loinc_code": "72194-4",
        "loinc_label": "Alzheimer's Disease Assessment Scale-Cognitive total score",
    },
    "MoCA": {
        "loinc_code": "72133-2",
        "loinc_label": "Montreal Cognitive Assessment total score",
    },
    "Logical Memory": {
        "loinc_code": "72026-8",
        "loinc_label": "Logical Memory - Delayed Recall",
    },
}

# ── Biomarker (CSF) → LOINC ──────────────────────────────────────────
# Keyed by analyte (actual values in graph)
BIOMARKER_LOINC: Dict[str, Dict[str, str]] = {
    "ABETA42": {
        "loinc_code": "13967-5",
        "loinc_label": "Beta-amyloid 42 in CSF",
    },
    "ABETA40": {
        "loinc_code": "83235-5",
        "loinc_label": "Beta-amyloid 40 in CSF",
    },
    "TAU": {
        "loinc_code": "15201-7",
        "loinc_label": "Total tau in CSF",
    },
    "PTAU181": {
        "loinc_code": "62731-6",
        "loinc_label": "Phosphorylated tau 181 in CSF",
    },
    "PTAU": {
        "loinc_code": "62731-6",
        "loinc_label": "Phosphorylated tau in CSF",
    },
}

# ── BrainRegion → UBERON ─────────────────────────────────────────────
# Keyed by name (actual values in graph)
BRAIN_REGION_UBERON: Dict[str, Dict[str, str]] = {
    "Hippocampus": {
        "uberon_code": "UBERON:0002421",
        "uberon_label": "hippocampal formation",
    },
    "Cerebral Cortex": {
        "uberon_code": "UBERON:0000956",
        "uberon_label": "cerebral cortex",
    },
    "Ventricles": {
        "uberon_code": "UBERON:0004086",
        "uberon_label": "brain ventricle",
    },
    "Cerebellum": {
        "uberon_code": "UBERON:0002037",
        "uberon_label": "cerebellum",
    },
    "Frontal Lobe": {
        "uberon_code": "UBERON:0000203",
        "uberon_label": "frontal lobe",
    },
    "Temporal Lobe": {
        "uberon_code": "UBERON:0001871",
        "uberon_label": "temporal lobe",
    },
    "Parietal Lobe": {
        "uberon_code": "UBERON:0001872",
        "uberon_label": "parietal lobe",
    },
    "Occipital Lobe": {
        "uberon_code": "UBERON:0002021",
        "uberon_label": "occipital lobe",
    },
    "Brainstem": {
        "uberon_code": "UBERON:0002298",
        "uberon_label": "brainstem",
    },
    "Thalamus": {
        "uberon_code": "UBERON:0001897",
        "uberon_label": "thalamus",
    },
    "Basal Ganglia": {
        "uberon_code": "UBERON:0002420",
        "uberon_label": "basal ganglion",
    },
    "Whole Brain": {
        "uberon_code": "UBERON:0000955",
        "uberon_label": "brain",
    },
}

# ── Relationship URIs ─────────────────────────────────────────────────
RELATIONSHIP_URIS: Dict[str, str] = {
    "HAS_VISIT": "ro:RO_0000056",                # participates_in
    "HAS_COGNITIVE_ASSESSMENT": "ro:RO_0002234",  # has_output
    "UNDERWENT_ASSESSMENT": "ro:RO_0002234",      # has_output
    "INCLUDES_ASSESSMENT": "ro:RO_0002234",       # has_output
    "FOLLOWED_BY": "time:intervalBefore",
    "PRECEDES": "time:intervalBefore",
    "PROGRESSED_TO": "ro:RO_0002411",             # causally_upstream_of
    "HAS_DIAGNOSIS": "ro:RO_0000091",             # has_disposition
    "SUPPORTS_DIAGNOSIS": "ro:RO_0000091",        # has_disposition
    "IS_CLINICAL_FINDING": "ro:RO_0000052",       # inheres_in
    "RESULTED_IN": "ro:RO_0002234",               # has_output
    "HAS_CLINICAL_FINDING": "ro:RO_0000052",      # inheres_in
    "HAS_BIOMARKER": "ro:RO_0000056",             # participates_in
    "HAS_IMAGE": "ro:RO_0000056",                 # participates_in
    "HAS_FAMILY_MEMBER": "ro:RO_0002351",         # has_member
    "HAS_SIBLING": "ro:RO_0002351",               # has_member
    "HAS_PARENT": "ro:RO_0002351",                # has_member
    "IS_TYPE": "rdfs:subClassOf",
    "BELONGS_TO_CATEGORY": "rdfs:subClassOf",
    "HAS_ATN_PROFILE": "ro:RO_0000086",           # has_quality
    "HAS_MULTIMODAL_ASSESSMENT": "ro:RO_0002234",
    "HAS_COGNITIVE_TRAJECTORY": "ro:RO_0002234",
    "CORRELATES_WITH": "ro:RO_0002610",           # correlated_with
    "INDICATES_PATHWAY": "ro:RO_0002610",
    "ASSOCIATED_WITH_STAGE": "ro:RO_0002610",
    "BELONGS_TO_COHORT": "ro:RO_0001015",         # location_of
    "IN_COHORT": "ro:RO_0001015",
    "EXPERIENCED_PROGRESSION": "ro:RO_0002411",   # causally_upstream_of
    "HAS_TRAJECTORY": "ro:RO_0002234",
    "HAS_PHENOTYPE": "ro:RO_0000086",             # has_quality
    # Semantic layer (added by Steps 19-20)
    "MAPS_TO": "skos:exactMatch",
    "IS_A": "rdfs:subClassOf",
    "CLASSIFIED_AS": "skos:closeMatch",
    "SAME_AS": "owl:sameAs",
    "CAUSES": "ro:RO_0002411",
}


# ══════════════════════════════════════════════════════════════════════
class OntologyPropertyManager:
    """Adds semantic ontology properties to existing nodes and relationships."""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector

    def execute(self) -> Dict[str, Any]:
        """Add all ontology properties and return coverage report."""
        results: Dict[str, Any] = {
            "diagnosis": {},
            "cognitive_assessment": {},
            "biomarker": {},
            "brain_region": {},
            "patient": {},
            "visit": {},
            "relationships": {},
        }

        # 1. Diagnosis ontology codes
        results["diagnosis"] = self._enrich_diagnosis_nodes()

        # 2. CognitiveAssessment LOINC codes
        results["cognitive_assessment"] = self._enrich_cognitive_assessments()

        # 3. Biomarker LOINC codes (CSF only — that's what exists in graph)
        results["biomarker"] = self._enrich_biomarkers()

        # 4. BrainRegion UBERON codes
        results["brain_region"] = self._enrich_brain_regions()

        # 5. Patient rdf_type and SNOMED code
        results["patient"] = self._set_rdf_type("Patient", "ncit:C16960", "Research Subject")
        self._enrich_patients()

        # 5b. DiseaseStage SNOMED/ICD-10 codes (CN, SMC, EMCI, LMCI, AD)
        results["disease_stage"] = self._enrich_disease_stages()

        # 6. Visit rdf_type
        results["visit"] = self._set_rdf_type("Visit", "ncit:C159705", "Clinical Visit")

        # 7. Relationship URIs
        results["relationships"] = self._enrich_relationships()

        # ── Coverage Report ──
        self._print_coverage_report(results)

        return results

    # ── Node enrichment methods ────────────────────────────────────

    def _enrich_diagnosis_nodes(self) -> Dict[str, Any]:
        """Set SNOMED, ICD-10, MONDO codes on Diagnosis nodes by diagnosis_code."""
        logger.info("Enriching Diagnosis nodes with SNOMED/ICD-10/MONDO codes...")
        total_updated = 0

        for dx_code, mappings in DIAGNOSIS_MAPPINGS.items():
            query = """
                MATCH (d:Diagnosis)
                WHERE d.diagnosis_code = $dx_code
                SET d.snomed_code = $snomed_code,
                    d.snomed_label = $snomed_label,
                    d.icd10_code = $icd10_code,
                    d.icd10_label = $icd10_label,
                    d.mondo_code = $mondo_code,
                    d.rdf_type = $rdf_type
                RETURN count(d) AS updated
            """
            params = {"dx_code": dx_code, **mappings}
            # Filter out empty mondo_code
            if not mappings.get("mondo_code"):
                query = query.replace(
                    "d.mondo_code = $mondo_code,",
                    ""
                )
                del params["mondo_code"]

            res = self.connector.run_query(query, params)
            cnt = res[0]["updated"] if res else 0
            total_updated += cnt
            if cnt > 0:
                logger.info(f"  ✅ {dx_code}: {cnt:,} nodes → SNOMED {mappings['snomed_code']}")

        # Get total for coverage
        total = self._count_nodes("Diagnosis")
        pct = (total_updated / total * 100) if total else 0
        logger.info(f"  Diagnosis coverage: {total_updated:,}/{total:,} ({pct:.1f}%)")

        return {"updated": total_updated, "total": total, "pct": round(pct, 1)}

    def _enrich_cognitive_assessments(self) -> Dict[str, Any]:
        """Set LOINC codes on CognitiveAssessment nodes by test_name."""
        logger.info("Enriching CognitiveAssessment nodes with LOINC codes...")
        total_updated = 0

        for test_name, mappings in COGNITIVE_LOINC.items():
            query = """
                MATCH (c:CognitiveAssessment)
                WHERE c.test_name = $test_name
                SET c.loinc_code = $loinc_code,
                    c.loinc_label = $loinc_label
                RETURN count(c) AS updated
            """
            params = {"test_name": test_name, **mappings}
            res = self.connector.run_query(query, params)
            cnt = res[0]["updated"] if res else 0
            total_updated += cnt
            if cnt > 0:
                logger.info(f"  ✅ {test_name}: {cnt:,} nodes → LOINC {mappings['loinc_code']}")

        total = self._count_nodes("CognitiveAssessment")
        pct = (total_updated / total * 100) if total else 0
        logger.info(f"  CognitiveAssessment coverage: {total_updated:,}/{total:,} ({pct:.1f}%)")

        return {"updated": total_updated, "total": total, "pct": round(pct, 1)}

    def _enrich_biomarkers(self) -> Dict[str, Any]:
        """Set LOINC codes on Biomarker nodes (CSF type) by analyte."""
        logger.info("Enriching Biomarker (CSF) nodes with LOINC codes...")
        total_updated = 0

        for analyte, mappings in BIOMARKER_LOINC.items():
            query = """
                MATCH (b:Biomarker)
                WHERE b.analyte = $analyte AND b.biomarker_type = 'CSF'
                SET b.loinc_code = $loinc_code,
                    b.loinc_label = $loinc_label
                RETURN count(b) AS updated
            """
            params = {"analyte": analyte, **mappings}
            res = self.connector.run_query(query, params)
            cnt = res[0]["updated"] if res else 0
            total_updated += cnt
            if cnt > 0:
                logger.info(f"  ✅ {analyte}: {cnt:,} nodes → LOINC {mappings['loinc_code']}")

        total_csf = self._count_nodes_where("Biomarker", "n.biomarker_type = 'CSF'")
        pct = (total_updated / total_csf * 100) if total_csf else 0
        logger.info(f"  Biomarker (CSF) coverage: {total_updated:,}/{total_csf:,} ({pct:.1f}%)")

        return {"updated": total_updated, "total": total_csf, "pct": round(pct, 1)}

    def _enrich_brain_regions(self) -> Dict[str, Any]:
        """Set UBERON codes on BrainRegion nodes by name."""
        logger.info("Enriching BrainRegion nodes with UBERON codes...")
        total_updated = 0

        for region_name, mappings in BRAIN_REGION_UBERON.items():
            query = """
                MATCH (b:BrainRegion)
                WHERE b.name = $region_name
                SET b.uberon_code = $uberon_code,
                    b.uberon_label = $uberon_label
                RETURN count(b) AS updated
            """
            params = {"region_name": region_name, **mappings}
            res = self.connector.run_query(query, params)
            cnt = res[0]["updated"] if res else 0
            total_updated += cnt
            if cnt > 0:
                logger.info(f"  ✅ {region_name}: {cnt} → UBERON {mappings['uberon_code']}")

        total = self._count_nodes("BrainRegion")
        pct = (total_updated / total * 100) if total else 0
        logger.info(f"  BrainRegion coverage: {total_updated}/{total} ({pct:.1f}%)")

        return {"updated": total_updated, "total": total, "pct": round(pct, 1)}

    def _enrich_disease_stages(self) -> Dict[str, Any]:
        """Add SNOMED/ICD-10 codes to DiseaseStage reference nodes.

        DiseaseStage nodes (CN, SMC, EMCI, LMCI, AD) are created in step 9
        but lack ontology codes. We reuse DIAGNOSIS_MAPPINGS keyed by stage_id.
        """
        logger.info("Enriching DiseaseStage nodes with SNOMED/ICD-10 codes...")
        total_updated = 0

        for stage_id, mappings in DIAGNOSIS_MAPPINGS.items():
            query = """
                MATCH (ds:DiseaseStage {stage_id: $stage_id})
                SET ds.snomed_code = $snomed_code,
                    ds.snomed_label = $snomed_label,
                    ds.icd10_code = $icd10_code,
                    ds.icd10_label = $icd10_label,
                    ds.rdf_type = $rdf_type,
                    ds.ontology_uri = 'http://snomed.info/id/' + $snomed_code,
                    ds.source_ontology = 'SNOMED-CT'
                RETURN count(ds) AS updated
            """
            params = {
                "stage_id": stage_id,
                "snomed_code": mappings["snomed_code"],
                "snomed_label": mappings["snomed_label"],
                "icd10_code": mappings["icd10_code"],
                "icd10_label": mappings["icd10_label"],
                "rdf_type": mappings["rdf_type"],
            }
            res = self.connector.run_query(query, params)
            cnt = res[0]["updated"] if res else 0
            total_updated += cnt
            if cnt > 0:
                logger.info(f"  ✅ DiseaseStage {stage_id}: SNOMED {mappings['snomed_code']}")

        total = self._count_nodes("DiseaseStage")
        pct = (total_updated / total * 100) if total else 0
        logger.info(f"  DiseaseStage coverage: {total_updated}/{total} ({pct:.1f}%)")
        return {"updated": total_updated, "total": total, "pct": round(pct, 1)}

    def _enrich_patients(self) -> Dict[str, Any]:
        """Add SNOMED-CT code to Patient nodes (SNOMED 116154003 = Patient)."""
        logger.info("Enriching Patient nodes with SNOMED code...")
        query = """
            MATCH (p:Patient)
            SET p.snomed_code = '116154003',
                p.snomed_label = 'Patient',
                p.ontology_uri = 'http://snomed.info/id/116154003',
                p.source_ontology = 'SNOMED-CT'
            RETURN count(p) AS updated
        """
        res = self.connector.run_query(query)
        cnt = res[0]["updated"] if res else 0
        logger.info(f"  Patient SNOMED enrichment: {cnt:,} nodes")
        return {"updated": cnt, "total": cnt, "pct": 100.0}

    def _set_rdf_type(self, label: str, rdf_type: str, description: str) -> Dict[str, Any]:
        """Set rdf_type property on all nodes of a given label."""
        logger.info(f"Setting rdf_type on {label} nodes ({rdf_type})...")
        query = f"""
            MATCH (n:{label})
            SET n.rdf_type = $rdf_type
            RETURN count(n) AS updated
        """
        res = self.connector.run_query(query, {"rdf_type": rdf_type})
        cnt = res[0]["updated"] if res else 0
        logger.info(f"  ✅ {label}: {cnt:,} nodes → rdf_type={rdf_type}")
        return {"updated": cnt, "total": cnt, "pct": 100.0}

    # ── Relationship enrichment ─────────────────────────────────────

    def _enrich_relationships(self) -> Dict[str, Any]:
        """Add URI properties to existing relationship types."""
        logger.info("Enriching relationships with URI properties...")
        results = {}

        # Get existing relationship types first
        existing_types = set()
        try:
            res = self.connector.run_query(
                "MATCH ()-[r]->() RETURN DISTINCT type(r) AS t"
            )
            existing_types = {r["t"] for r in res}
        except Exception as e:
            logger.warning(f"  Could not query rel types: {e}")

        for rel_type, uri in RELATIONSHIP_URIS.items():
            if rel_type not in existing_types:
                continue  # Skip types not in graph yet

            query = f"""
                MATCH ()-[r:{rel_type}]->()
                WHERE r.uri IS NULL
                SET r.uri = $uri
                RETURN count(r) AS updated
            """
            try:
                res = self.connector.run_query(query, {"uri": uri})
                cnt = res[0]["updated"] if res else 0
                if cnt > 0:
                    logger.info(f"  ✅ {rel_type}: {cnt:,} rels → uri={uri}")
                results[rel_type] = cnt
            except Exception as e:
                logger.warning(f"  ⚠️  Could not enrich {rel_type}: {e}")
                results[rel_type] = f"error: {e}"

        return results

    # ── Utility methods ─────────────────────────────────────────────

    def _count_nodes(self, label: str) -> int:
        res = self.connector.run_query(f"MATCH (n:{label}) RETURN count(n) AS cnt")
        return res[0]["cnt"] if res else 0

    def _count_nodes_where(self, label: str, where: str) -> int:
        res = self.connector.run_query(
            f"MATCH (n:{label}) WHERE {where} RETURN count(n) AS cnt"
        )
        return res[0]["cnt"] if res else 0

    def _print_coverage_report(self, results: Dict[str, Any]):
        """Print a summary coverage report."""
        logger.info("")
        logger.info("=" * 60)
        logger.info("STEP 18 — ONTOLOGY PROPERTY COVERAGE REPORT")
        logger.info("=" * 60)
        for category, data in results.items():
            if isinstance(data, dict) and "pct" in data:
                logger.info(
                    f"  {category:.<30} "
                    f"{data.get('updated', '?'):>6,}/{data.get('total', '?'):>6,} "
                    f"({data['pct']:.1f}%)"
                )
            elif isinstance(data, dict) and category == "relationships":
                enriched = sum(v for v in data.values() if isinstance(v, int))
                logger.info(f"  {'relationships':.<30} {enriched:>6,} rels enriched")
        logger.info("=" * 60)


# ══════════════════════════════════════════════════════════════════════
# Pipeline entry point
# ══════════════════════════════════════════════════════════════════════

def execute_ontology_properties(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    **kwargs,
) -> Dict[str, Any]:
    """
    Main execution function for Step 18 — Add Ontology Properties.

    Args:
        neo4j_uri:      Neo4j connection URI
        neo4j_user:     Username
        neo4j_password: Password

    Returns:
        Dict with enrichment results and coverage report.
    """
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)
    try:
        manager = OntologyPropertyManager(connector)
        return manager.execute()
    except Exception as e:
        logger.error(f"Step 18 failed: {e}")
        raise
    finally:
        connector.close()


# ══════════════════════════════════════════════════════════════════════
# Standalone execution
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Step 18: Add Ontology Properties")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="your_password")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    results = execute_ontology_properties(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
    )
