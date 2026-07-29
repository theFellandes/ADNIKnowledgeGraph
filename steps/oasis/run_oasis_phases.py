"""Run the four phases on the OASIS-2 scratch graph (P2).

Invokes the cohort-AGNOSTIC pipeline steps against the scratch instance (7688):

    17 constraints -> 18 ontology properties -> 20 ontology layer + MAPS_TO
    -> 33 biolink categories -> 34 MONDO/DOID wiring

SKIPPED on purpose: 19 (ICD-10 WHO API — icd10_code already set by step18's dict),
30/32/35/36 (HPO/comorbidity/Gene/NPI-Q — no OASIS source, so those labels stay 0).

Usage::

    python -m steps.oasis.run_oasis_phases
    python -m steps.oasis.run_oasis_phases --uri bolt://localhost:7688
"""

from __future__ import annotations

import argparse
import logging
import sys

from steps.step17_apply_constraints import execute_constraints
from steps.step18_add_ontology_properties import execute_ontology_properties
from steps.step20_ontology_layer import execute_ontology_layer
from steps.step33_biolink_categories import execute_biolink_categories
from steps.step34_mondo_doid_wiring import execute_mondo_doid_wiring

logger = logging.getLogger(__name__)

DEFAULT_URI = "bolt://localhost:7688"  # scratch — NOT 7687
DEFAULT_USER = "neo4j"
DEFAULT_PASSWORD = "your_password"

PHASES = [
    ("17 constraints", execute_constraints),
    ("18 ontology properties", execute_ontology_properties),
    ("20 ontology layer + MAPS_TO", execute_ontology_layer),
    ("33 biolink categories", execute_biolink_categories),
    ("34 MONDO/DOID wiring", execute_mondo_doid_wiring),
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m steps.oasis.run_oasis_phases")
    p.add_argument("--uri", default=DEFAULT_URI)
    p.add_argument("--user", default=DEFAULT_USER)
    p.add_argument("--password", default=DEFAULT_PASSWORD)
    p.add_argument("--allow-7687", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if "7687" in args.uri and not args.allow_7687:
        raise SystemExit(f"REFUSING to run against {args.uri} (canonical ADNI graph). Use 7688.")

    for label, fn in PHASES:
        logger.info("=== Phase step %s ===", label)
        try:
            result = fn(args.uri, args.user, args.password)
            logger.info("step %s OK: %s", label, result)
        except Exception as exc:  # noqa: BLE001 — report and continue so we see all failures
            logger.error("step %s FAILED: %s", label, exc, exc_info=True)
            return 1

    logger.info("All four phases complete on %s", args.uri)
    return 0


if __name__ == "__main__":
    sys.exit(main())
