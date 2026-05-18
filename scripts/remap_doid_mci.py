"""One-shot remap: DOID:0050169 → DOID:0080832 for mild cognitive impairment.

Background
==========
Step 34 (``steps/step34_mondo_doid_wiring.py``) originally hardcoded the
MCI concept as ``DOID:0050169``. Direct lookup against the OBO Foundry
Disease Ontology shows that ``DOID:0050169`` is actually *cutaneous
lupus erythematosus*. The canonical DOID for mild cognitive impairment
is ``DOID:0080832`` (verified against EBI OLS, 2026-05-16).

This script fixes the live Neo4j graph idempotently:

  1. Renames the ``OntologyConcept {source_ontology:'DOID', code:'0050169'}``
     node's ``code``, ``label`` and ``uri`` properties.
  2. Updates every ``MAPS_TO`` edge that carries an old DOID URI to the
     new URI.
  3. Updates the ``Diagnosis.doid_code`` property where it carries the
     old value.

The source-of-truth files have already been patched so a fresh Step 34
re-run writes the canonical code directly:

* ``steps/step34_mondo_doid_wiring.py`` (DOID_CONCEPTS list)
* ``ontology/mappings/diagnosis_to_doid.csv``
* ``ontology/mappings/index.csv``
* ``Thesis/OğuzhanGüngör_Tez (1)/thesis.tex``

This script is the bridge that brings the live graph into sync with those
files in the meantime.

Usage
=====

    python scripts/remap_doid_mci.py

Credentials come from the project's canonical loader at
``utils/env_loader.py`` (config.yaml → .env → os.environ).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Make the project root importable so utils.* resolves when the script
# is invoked directly.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.env_loader import load_config  # noqa: E402
from utils.neo4j_connector import Neo4jConnector  # noqa: E402

logger = logging.getLogger(__name__)


OLD_CODE = "0050169"
NEW_CODE = "0080832"
LABEL = "Mild cognitive impairment"

OLD_DOID_PREFIXED = f"DOID:{OLD_CODE}"
NEW_DOID_PREFIXED = f"DOID:{NEW_CODE}"

# Cover the URI shapes Step 34 might have written: bare CURIE, prefixed
# CURIE, and the canonical OBO PURL.
URI_CANDIDATES_OLD = [
    OLD_CODE,
    OLD_DOID_PREFIXED,
    f"doid:{OLD_CODE}",
    f"http://purl.obolibrary.org/obo/DOID_{OLD_CODE}",
]
NEW_PURL = f"http://purl.obolibrary.org/obo/DOID_{NEW_CODE}"


REMAP_STEPS = [
    (
        "OntologyConcept code",
        """
        MATCH (o:OntologyConcept {source_ontology: 'DOID'})
        WHERE o.code IN $old_codes
        SET o.code  = $new_code,
            o.label = $label,
            o.uri   = $new_purl
        RETURN count(o) AS updated
        """,
        lambda: {
            "old_codes": [OLD_CODE, OLD_DOID_PREFIXED, f"doid:{OLD_CODE}"],
            "new_code": NEW_CODE,
            "label": LABEL,
            "new_purl": NEW_PURL,
        },
    ),
    (
        "MAPS_TO edge uri",
        """
        MATCH ()-[r:MAPS_TO]->()
        WHERE r.uri IN $uri_candidates_old
        SET r.uri = $new_purl
        RETURN count(r) AS updated
        """,
        lambda: {
            "uri_candidates_old": URI_CANDIDATES_OLD,
            "new_purl": NEW_PURL,
        },
    ),
    (
        "Diagnosis.doid_code property",
        """
        MATCH (d:Diagnosis)
        WHERE d.doid_code IN $old_codes
        SET d.doid_code = $new_doid_prefixed
        RETURN count(d) AS updated
        """,
        lambda: {
            "old_codes": [OLD_CODE, OLD_DOID_PREFIXED, f"doid:{OLD_CODE}"],
            "new_doid_prefixed": NEW_DOID_PREFIXED,
        },
    ),
]


VERIFICATION_QUERY = """
MATCH (o:OntologyConcept {source_ontology: 'DOID'})
RETURN o.code AS code, o.label AS label, o.uri AS uri
ORDER BY o.code
""".strip()


def main() -> int:
    cfg = load_config()
    uri = cfg.get("neo4j_uri", "bolt://localhost:7687")
    user = cfg.get("neo4j_user", "neo4j")
    pwd = cfg.get("neo4j_password")
    if not pwd:
        logger.error(
            "No neo4j_password resolved by utils.env_loader. "
            "Set NEO4J_PASSWORD in .env (placeholders like 'your_password' "
            "are filtered out by the loader)."
        )
        return 2

    connector = Neo4jConnector(uri=uri, user=user, password=pwd)
    if not connector.verify_connection():
        logger.error("Neo4j connection verification failed; aborting.")
        connector.close()
        return 1

    logger.info("Connected to %s as %s", uri, user)

    summary: dict[str, int] = {}
    try:
        for label, query, params_fn in REMAP_STEPS:
            params = params_fn()
            # run_query handles both reads and writes (it commits via
            # session.execute_write under the hood per neo4j_connector.py).
            rows = connector.run_query(query, params)
            updated = int(rows[0]["updated"]) if rows else 0
            summary[label] = updated
            logger.info("  %s: %d row(s) updated", label, updated)

        logger.info("Verification — DOID OntologyConcepts after remap:")
        for rec in connector.run_query(VERIFICATION_QUERY):
            logger.info(
                "    code=%s  label=%s  uri=%s",
                rec.get("code"), rec.get("label"), rec.get("uri"),
            )
    finally:
        connector.close()

    print()
    print("--- summary ---")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print("--- done ---")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(main())
