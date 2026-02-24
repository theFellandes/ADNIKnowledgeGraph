"""
Step 17: Apply Composite Unique Constraints & Performance Indexes
=================================================================
Creates semantic-layer constraints that ensure data integrity for the
Knowledge Graph upgrade.  All statements are idempotent (IF NOT EXISTS).

Builds on top of Step 1's single-property constraints by adding:
  - Composite uniqueness constraints for observation nodes
  - OntologyConcept URI constraint (new node type)
  - Additional performance indexes for semantic queries

Usage:
    python steps/step17_apply_constraints.py --neo4j-password your_password
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Constraint & Index Definitions
# ──────────────────────────────────────────────────────────────────────

# Core uniqueness constraints (single property)
# Some may already exist from Step 1 — we use IF NOT EXISTS for safety.
CORE_CONSTRAINTS: List[Tuple[str, str, List[str]]] = [
    # (constraint_name, label, [properties])
    ("patient_ptid_unique", "Patient", ["ptid"]),
    ("visit_id_unique", "Visit", ["visit_id"]),
    ("mri_image_id_unique", "MRIScan", ["image_id"]),
    ("pet_image_id_unique", "PETScan", ["image_id"]),
    ("ontology_uri_unique", "OntologyConcept", ["uri"]),
]

# Composite uniqueness constraints — Neo4j 5.x required
COMPOSITE_CONSTRAINTS: List[Tuple[str, str, List[str]]] = [
    ("brain_region_unique", "BrainRegion", ["name", "hemisphere"]),
    ("assess_unique", "CognitiveAssessment", ["visit_id", "test_name"]),
    ("csf_unique", "CSFBiomarker", ["visit_id", "assay"]),
    ("blood_unique", "BloodBiomarker", ["visit_id", "analyte"]),
    ("vol_unique", "VolumetricMeasure", ["visit_id", "region_name", "hemisphere"]),
    ("atn_unique", "ATNProfile", ["patient_id", "visit_id"]),
    ("dx_unique", "Diagnosis", ["visit_id", "dx_label"]),
]

# Performance indexes for semantic-layer queries
PERFORMANCE_INDEXES: List[Tuple[str, str, List[str]]] = [
    # (index_name, label, [properties])
    ("idx_patient_rid", "Patient", ["rid"]),
    ("idx_visit_ptid", "Visit", ["ptid"]),
    ("idx_visit_viscode", "Visit", ["viscode"]),
    ("idx_dx_label", "Diagnosis", ["dx_label"]),
    ("idx_assess_test_name", "CognitiveAssessment", ["test_name"]),
    ("idx_csf_assay", "CSFBiomarker", ["assay"]),
    ("idx_blood_analyte", "BloodBiomarker", ["analyte"]),
    ("idx_vol_region", "VolumetricMeasure", ["region_name"]),
    ("idx_ontology_code", "OntologyConcept", ["code"]),
    ("idx_ontology_source", "OntologyConcept", ["source_ontology"]),
    ("idx_ontology_label", "OntologyConcept", ["label"]),
    ("idx_brain_hemisphere", "BrainRegion", ["hemisphere"]),
    ("idx_atn_patient", "ATNProfile", ["patient_id"]),
    ("idx_medication_rxnorm", "Medication", ["rxnorm_code"]),
    ("idx_batch_id", "BatchIngestion", ["batch_id"]),
]


# ──────────────────────────────────────────────────────────────────────
class ConstraintManager:
    """Manages composite constraints and indexes for the KG schema."""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector

    def execute(self) -> Dict[str, Any]:
        """
        Apply all constraints and indexes.

        Returns:
            Dict with counts of created, existing, and errored items.
        """
        results = {
            "constraints_created": 0,
            "constraints_existing": 0,
            "constraints_errors": 0,
            "indexes_created": 0,
            "indexes_existing": 0,
            "indexes_errors": 0,
            "details": {"constraints": [], "indexes": []},
        }

        # ── 1. Verify Neo4j version ───────────────────────────────────
        version_info = self._check_neo4j_version()
        results["neo4j_version"] = version_info.get("version", "unknown")
        supports_composite = version_info.get("supports_composite", False)
        if not supports_composite:
            logger.warning(
                "⚠️  Neo4j < 5.x detected — composite constraints will be "
                "attempted but may fail. Consider upgrading."
            )

        # ── 2. Get existing constraints/indexes for dedup ─────────────
        existing_constraints = self._get_existing_constraint_names()
        existing_indexes = self._get_existing_index_names()

        # ── 3. Create core uniqueness constraints ─────────────────────
        logger.info("Creating core uniqueness constraints...")
        for name, label, props in CORE_CONSTRAINTS:
            status = self._create_constraint(name, label, props, existing_constraints)
            results["details"]["constraints"].append(
                {"name": name, "label": label, "properties": props, "status": status}
            )
            if status == "created":
                results["constraints_created"] += 1
            elif status == "existing":
                results["constraints_existing"] += 1
            else:
                results["constraints_errors"] += 1

        # ── 4. Create composite constraints ───────────────────────────
        logger.info("Creating composite uniqueness constraints...")
        for name, label, props in COMPOSITE_CONSTRAINTS:
            status = self._create_constraint(name, label, props, existing_constraints)
            results["details"]["constraints"].append(
                {"name": name, "label": label, "properties": props, "status": status}
            )
            if status == "created":
                results["constraints_created"] += 1
            elif status == "existing":
                results["constraints_existing"] += 1
            else:
                results["constraints_errors"] += 1

        # ── 5. Create performance indexes ─────────────────────────────
        logger.info("Creating performance indexes...")
        for name, label, props in PERFORMANCE_INDEXES:
            status = self._create_index(name, label, props, existing_indexes)
            results["details"]["indexes"].append(
                {"name": name, "label": label, "properties": props, "status": status}
            )
            if status == "created":
                results["indexes_created"] += 1
            elif status == "existing":
                results["indexes_existing"] += 1
            else:
                results["indexes_errors"] += 1

        # ── 6. Summary ───────────────────────────────────────────────
        total_c = len(CORE_CONSTRAINTS) + len(COMPOSITE_CONSTRAINTS)
        total_i = len(PERFORMANCE_INDEXES)
        logger.info("")
        logger.info("=" * 60)
        logger.info("STEP 17 — CONSTRAINT SUMMARY")
        logger.info("=" * 60)
        logger.info(
            f"  Constraints: {results['constraints_created']} created, "
            f"{results['constraints_existing']} existing, "
            f"{results['constraints_errors']} errors "
            f"(total defined: {total_c})"
        )
        logger.info(
            f"  Indexes:     {results['indexes_created']} created, "
            f"{results['indexes_existing']} existing, "
            f"{results['indexes_errors']} errors "
            f"(total defined: {total_i})"
        )
        logger.info("=" * 60)

        return results

    # ── Helpers ───────────────────────────────────────────────────────

    def _check_neo4j_version(self) -> Dict[str, Any]:
        """Get Neo4j version and check composite constraint support."""
        try:
            res = self.connector.run_query(
                "CALL dbms.components() "
                "YIELD name, versions, edition "
                "RETURN name, versions, edition"
            )
            if res:
                version_str = res[0]["versions"][0]
                major = int(version_str.split(".")[0])
                info = {
                    "version": version_str,
                    "edition": res[0]["edition"],
                    "supports_composite": major >= 5,
                }
                logger.info(
                    f"  Neo4j {info['version']} ({info['edition']}) — "
                    f"composite constraints: {'✅' if info['supports_composite'] else '❌'}"
                )
                return info
        except Exception as e:
            logger.warning(f"  Could not determine Neo4j version: {e}")
        return {"version": "unknown", "supports_composite": False}

    def _get_existing_constraint_names(self) -> set:
        """Fetch names of all existing constraints."""
        try:
            res = self.connector.run_query("SHOW CONSTRAINTS")
            names = {r.get("name", "") for r in res if r.get("name")}
            logger.info(f"  Found {len(names)} existing constraints")
            return names
        except Exception as e:
            logger.warning(f"  Could not list constraints: {e}")
            return set()

    def _get_existing_index_names(self) -> set:
        """Fetch names of all existing indexes."""
        try:
            res = self.connector.run_query("SHOW INDEXES")
            names = {r.get("name", "") for r in res if r.get("name")}
            logger.info(f"  Found {len(names)} existing indexes")
            return names
        except Exception as e:
            logger.warning(f"  Could not list indexes: {e}")
            return set()

    def _create_constraint(
        self,
        name: str,
        label: str,
        properties: List[str],
        existing: set,
    ) -> str:
        """
        Create a uniqueness constraint.  Returns 'created', 'existing', or 'error'.
        """
        if name in existing:
            logger.debug(f"  ⏭️  Constraint already exists: {name}")
            return "existing"

        props_clause = ", ".join(f"n.{p}" for p in properties)
        query = (
            f"CREATE CONSTRAINT {name} IF NOT EXISTS "
            f"FOR (n:{label}) "
            f"REQUIRE ({props_clause}) IS UNIQUE"
        )

        try:
            self.connector.execute_write_transaction(query)
            logger.info(f"  ✅ Created constraint: {name} on {label}({', '.join(properties)})")
            return "created"
        except Exception as e:
            err_msg = str(e).lower()
            if "already exists" in err_msg or "equivalent" in err_msg:
                logger.debug(f"  ⏭️  Constraint equivalent exists: {name}")
                return "existing"
            logger.error(f"  ❌ Failed to create constraint {name}: {e}")
            return "error"

    def _create_index(
        self,
        name: str,
        label: str,
        properties: List[str],
        existing: set,
    ) -> str:
        """
        Create a range index.  Returns 'created', 'existing', or 'error'.
        """
        if name in existing:
            logger.debug(f"  ⏭️  Index already exists: {name}")
            return "existing"

        props_clause = ", ".join(f"n.{p}" for p in properties)
        query = (
            f"CREATE INDEX {name} IF NOT EXISTS "
            f"FOR (n:{label}) "
            f"ON ({props_clause})"
        )

        try:
            self.connector.execute_write_transaction(query)
            logger.info(f"  ✅ Created index: {name} on {label}({', '.join(properties)})")
            return "created"
        except Exception as e:
            err_msg = str(e).lower()
            if "already exists" in err_msg or "equivalent" in err_msg:
                logger.debug(f"  ⏭️  Index equivalent exists: {name}")
                return "existing"
            logger.error(f"  ❌ Failed to create index {name}: {e}")
            return "error"


# ──────────────────────────────────────────────────────────────────────
# Pipeline entry point
# ──────────────────────────────────────────────────────────────────────

def execute_constraints(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    **kwargs,
) -> Dict[str, Any]:
    """
    Main execution function for Step 17 — Apply Constraints.

    Args:
        neo4j_uri:      Neo4j connection URI
        neo4j_user:     Username
        neo4j_password: Password

    Returns:
        Dict with constraint/index creation results.
    """
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)
    try:
        manager = ConstraintManager(connector)
        return manager.execute()
    except Exception as e:
        logger.error(f"Step 17 failed: {e}")
        raise
    finally:
        connector.close()


# ──────────────────────────────────────────────────────────────────────
# Standalone execution
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Step 17: Apply KG Constraints")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="your_password")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    results = execute_constraints(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
    )

    print(f"\nConstraints created: {results['constraints_created']}")
    print(f"Constraints existing: {results['constraints_existing']}")
    print(f"Indexes created: {results['indexes_created']}")
    print(f"Indexes existing: {results['indexes_existing']}")
