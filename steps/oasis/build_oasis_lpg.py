"""Build a minimal OASIS-2 labeled property graph (LPG) on the scratch Neo4j.

This is the only real new code for the OASIS-2 cross-cohort transfer experiment.
It reads the OASIS-2 longitudinal table (150 subjects / 373 visits) and MERGEs the
minimal graph using the EXACT node labels + property names that the four phases
bind on, so steps 17/18/20/33/34 then ground it with ZERO new mapping rules:

    Diagnosis.diagnosis_code   -> step18 DIAGNOSIS_MAPPINGS  -> SNOMED/ICD-10/(MONDO on AD)
    CognitiveAssessment.test_name -> step18 COGNITIVE_LOINC  -> LOINC
    BrainRegion.name           -> step18 BRAIN_REGION_UBERON -> UBERON

Diagnosis remap (per-visit, reproducible — documented in the plan):
    CDR == 0    -> 'CN'   (cognitively normal)
    CDR >= 0.5  -> 'AD'   (OASIS "Demented" = dementia of the Alzheimer type)

ISOLATION: defaults to bolt://localhost:7688 (scratch instance). NEVER point this
at 7687 (the canonical ADNI graph).

Usage::

    python -m steps.oasis.build_oasis_lpg
    python -m steps.oasis.build_oasis_lpg --csv inputs/oasis2/oasis_longitudinal.csv \
        --uri bolt://localhost:7688 --user neo4j --password your_password
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path

import pandas as pd
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

DEFAULT_CSV = "inputs/oasis2/oasis_longitudinal.csv"
DEFAULT_URI = "bolt://localhost:7688"  # scratch instance — NOT 7687
DEFAULT_USER = "neo4j"
DEFAULT_PASSWORD = "your_password"

SOURCE = "OASIS-2"


def _clean(value):
    """Convert pandas NaN/NaT to None so the Neo4j driver accepts it."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def diagnosis_from_cdr(cdr) -> str | None:
    """Per-visit diagnosis remap onto ADNI's diagnosis_code controlled values."""
    cdr = _clean(cdr)
    if cdr is None:
        return None
    return "CN" if float(cdr) == 0.0 else "AD"  # CDR >= 0.5 -> AD


def rows_from_csv(csv_path: Path) -> list[dict]:
    df = pd.read_csv(csv_path)
    rows: list[dict] = []
    for _, r in df.iterrows():
        visit_id = _clean(r.get("MRI ID"))
        if not visit_id:
            continue
        cdr = _clean(r.get("CDR"))
        rows.append(
            {
                "ptid": _clean(r.get("Subject ID")),
                "visit_id": visit_id,
                "visit": _clean(r.get("Visit")),
                "group": _clean(r.get("Group")),
                "sex": _clean(r.get("M/F")),
                "hand": _clean(r.get("Hand")),
                "age": _clean(r.get("Age")),
                "educ": _clean(r.get("EDUC")),
                "ses": _clean(r.get("SES")),
                "mr_delay": _clean(r.get("MR Delay")),
                "mmse": _clean(r.get("MMSE")),
                "cdr": cdr,
                "nwbv": _clean(r.get("nWBV")),
                "etiv": _clean(r.get("eTIV")),
                "asf": _clean(r.get("ASF")),
                "dx_code": diagnosis_from_cdr(cdr),
            }
        )
    return rows


# One UNWIND builds the whole minimal LPG. Property names match step18 binders.
_BUILD_QUERY = """
UNWIND $rows AS row
MERGE (p:Patient {ptid: row.ptid})
  ON CREATE SET p.source = $source
  SET p.sex = row.sex, p.hand = row.hand, p.educ = row.educ, p.ses = row.ses
MERGE (v:Visit {visit_id: row.visit_id})
  SET v.source = $source, v.viscode = row.visit, v.age = row.age,
      v.mr_delay = row.mr_delay, v.group = row.group
MERGE (p)-[:HAS_VISIT]->(v)

// Diagnosis (per visit) — diagnosis_code in {CN, AD}
FOREACH (_ IN CASE WHEN row.dx_code IS NOT NULL THEN [1] ELSE [] END |
  MERGE (d:Diagnosis {visit_id: row.visit_id})
    SET d.diagnosis_code = row.dx_code, d.source = $source,
        d.cdr = row.cdr, d.group = row.group
  MERGE (v)-[:HAS_DIAGNOSIS]->(d)
)

// CognitiveAssessment — MMSE
FOREACH (_ IN CASE WHEN row.mmse IS NOT NULL THEN [1] ELSE [] END |
  MERGE (cm:CognitiveAssessment {visit_id: row.visit_id, test_name: 'MMSE'})
    SET cm.value = row.mmse, cm.source = $source
  MERGE (v)-[:HAS_COGNITIVE_ASSESSMENT]->(cm)
)

// CognitiveAssessment — CDR
FOREACH (_ IN CASE WHEN row.cdr IS NOT NULL THEN [1] ELSE [] END |
  MERGE (cc:CognitiveAssessment {visit_id: row.visit_id, test_name: 'CDR'})
    SET cc.value = row.cdr, cc.source = $source
  MERGE (v)-[:HAS_COGNITIVE_ASSESSMENT]->(cc)
)

// BrainRegion — whole-brain volume (name MUST equal the BRAIN_REGION_UBERON key)
FOREACH (_ IN CASE WHEN row.nwbv IS NOT NULL THEN [1] ELSE [] END |
  MERGE (b:BrainRegion {visit_id: row.visit_id, name: 'Whole Brain'})
    SET b.nwbv = row.nwbv, b.etiv = row.etiv, b.asf = row.asf, b.source = $source
  MERGE (v)-[:HAS_IMAGE]->(b)
)
"""

_COUNT_QUERY = """
MATCH (n)
WITH labels(n)[0] AS label, count(n) AS n
RETURN label, n ORDER BY label
"""


def build(driver, rows: list[dict]) -> None:
    with driver.session() as session:
        session.run(_BUILD_QUERY, rows=rows, source=SOURCE)


def summarize(driver) -> None:
    with driver.session() as session:
        logger.info("Node counts by label:")
        for rec in session.run(_COUNT_QUERY):
            logger.info("  %-22s %d", rec["label"], rec["n"])
        dx = session.run(
            "MATCH (d:Diagnosis) RETURN d.diagnosis_code AS code, count(*) AS n ORDER BY code"
        )
        logger.info("Diagnosis codes: %s", {r["code"]: r["n"] for r in dx})
        rels = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS n ORDER BY t"
        )
        logger.info("Relationships: %s", {r["t"]: r["n"] for r in rels})


def _safety_check(uri: str) -> None:
    if "7687" in uri:
        raise SystemExit(
            "REFUSING to run against %s — that is the canonical ADNI graph (7687). "
            "Use the scratch instance bolt://localhost:7688." % uri
        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m steps.oasis.build_oasis_lpg")
    p.add_argument("--csv", default=DEFAULT_CSV)
    p.add_argument("--uri", default=DEFAULT_URI)
    p.add_argument("--user", default=DEFAULT_USER)
    p.add_argument("--password", default=DEFAULT_PASSWORD)
    p.add_argument("--allow-7687", action="store_true",
                   help="override the 7687 safety guard (NOT recommended)")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    if not args.allow_7687:
        _safety_check(args.uri)

    repo_root = Path(__file__).resolve().parents[2]
    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = repo_root / csv_path
    if not csv_path.exists():
        logger.error("CSV not found: %s", csv_path)
        return 2

    rows = rows_from_csv(csv_path)
    logger.info("Loaded %d visit rows (%d subjects) from %s",
                len(rows), len({r["ptid"] for r in rows}), csv_path.name)

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    try:
        driver.verify_connectivity()
        build(driver, rows)
        summarize(driver)
    finally:
        driver.close()
    logger.info("OASIS-2 LPG build complete on %s", args.uri)
    return 0


if __name__ == "__main__":
    sys.exit(main())
