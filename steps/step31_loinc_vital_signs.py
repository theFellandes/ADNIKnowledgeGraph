"""
Step 31: LOINC Vital-Signs Materialisation
==========================================
Closes the LOINC vital-signs half of Contribution 3 (column-to-concept
mapping for patient-level data) from the contribution table.

The VITALS table (15,696 rows in the Aug 2025 cohort) carries one row per
patient-visit with measurements for systolic and diastolic blood pressure,
weight, height, pulse, respiratory rate, and temperature. The Phase~1
loader caches the table into pandas but never writes the rows into Neo4j
as Biomarker instances. Step~31 closes that gap by:

1. Materialising six LOINC OntologyConcept nodes for the canonical vital
   signs: systolic BP (8480-6), diastolic BP (8462-4), body weight
   (29463-7), body height (8302-2), heart rate (8867-4), and a derived
   body mass index (39156-5).
2. Writing one Biomarker node per (patient, visit, vital-sign) row whose
   value falls inside the clinical plausibility range.
3. Connecting each Biomarker to its parent Visit through HAS_BIOMARKER
   and to its LOINC concept through MAPS_TO.

All operations use MERGE (idempotent). Re-running the step on a graph
that has already been migrated only updates the last_seen_at marker on
existing nodes and edges.

Usage:
    python -m steps.step31_loinc_vital_signs --neo4j-password <pw>
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Catalogue: (biomarker_type, loinc_code, label, vitals_column, unit,
#             value_range_low, value_range_high)
# vitals_column = None → derived (BMI from weight + height).
# ─────────────────────────────────────────────────────────────────────

VITAL_SIGNS: List[Tuple[str, str, str, str | None, str, float, float]] = [
    ("SystolicBP",    "8480-6",  "Systolic blood pressure",  "VSBPSYS",  "mmHg",   60.0, 260.0),
    ("DiastolicBP",   "8462-4",  "Diastolic blood pressure", "VSBPDIA",  "mmHg",   30.0, 180.0),
    ("BodyWeight",    "29463-7", "Body weight",              "VSWEIGHT", "kg",     25.0, 250.0),
    ("BodyHeight",    "8302-2",  "Body height",              "VSHEIGHT", "cm",    100.0, 230.0),
    ("HeartRate",     "8867-4",  "Heart rate",               "VSPULSE",  "bpm",    30.0, 220.0),
    ("BodyMassIndex", "39156-5", "Body mass index (BMI)",    None,       "kg/m^2", 10.0,  80.0),
]

LOINC_PURL_PREFIX = "http://purl.bioontology.org/ontology/LNC/"
DEFAULT_VITALS_PATH = Path("inputs/Tables/Novel_Imaging_Cohort_Study_VITALS_05Aug2025.csv")


# ─────────────────────────────────────────────────────────────────────
# Cypher statements
# ─────────────────────────────────────────────────────────────────────

CYPHER_MERGE_LOINC_CONCEPT = """
MERGE (c:OntologyConcept {uri: $uri})
  ON CREATE SET
    c.source_ontology = 'LOINC',
    c.code            = $code,
    c.label           = $label,
    c.unit            = $unit,
    c.created_at      = datetime(),
    c.created_by_step = 'step31_loinc_vital_signs'
  ON MATCH SET
    c.last_seen_at    = datetime(),
    c.label           = coalesce(c.label, $label),
    c.unit            = coalesce(c.unit, $unit)
"""

CYPHER_BATCH_MERGE_BIOMARKER = """
UNWIND $batch AS row
MATCH (v:Visit {visit_id: row.visit_id})
MERGE (b:Biomarker {biomarker_id: row.biomarker_id})
  ON CREATE SET
    b.patient_id      = row.ptid,
    b.viscode         = row.viscode,
    b.visit_id        = row.visit_id,
    b.biomarker_type  = row.btype,
    b.loinc_code      = row.code,
    b.ontology_uri    = row.curie,
    b.value           = row.value,
    b.unit            = row.unit,
    b.source_table    = 'VITALS',
    b.source_column   = row.column,
    b.created_at      = datetime(),
    b.created_by_step = 'step31_loinc_vital_signs'
  ON MATCH SET
    b.last_seen_at    = datetime(),
    b.value           = coalesce(b.value, row.value)
MERGE (v)-[:HAS_BIOMARKER]->(b)
WITH b, row
MATCH (c:OntologyConcept {uri: row.uri})
MERGE (b)-[r:MAPS_TO]->(c)
  ON CREATE SET
    r.method     = 'curated-rule',
    r.rule_id    = row.rule_id,
    r.created_at = datetime()
"""


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _bmi(weight_kg: float | None, height_cm: float | None) -> float | None:
    if weight_kg is None or height_cm is None or height_cm <= 0:
        return None
    height_m = height_cm / 100.0
    return round(weight_kg / (height_m * height_m), 2)


class LoincVitalSignsStep:
    """Step 31 driver."""

    def __init__(self, connector: Neo4jConnector, vitals_path: Path = DEFAULT_VITALS_PATH):
        self.connector = connector
        self.vitals_path = vitals_path
        self.metrics: Dict[str, Any] = {
            "step": "step31_loinc_vital_signs",
            "concepts_written": 0,
            "biomarkers_written": 0,
            "rows_skipped_no_visit": 0,
            "rows_skipped_out_of_range": 0,
            "rows_processed": 0,
        }

    # ── concept layer ────────────────────────────────────────────────

    def _materialise_concepts(self) -> int:
        written = 0
        for biomarker_type, code, label, _, unit, _, _ in VITAL_SIGNS:
            uri = f"{LOINC_PURL_PREFIX}{code}"
            self.connector.run_query(
                CYPHER_MERGE_LOINC_CONCEPT,
                {"uri": uri, "code": code, "label": label, "unit": unit},
            )
            written += 1
        return written

    # ── orchestration ────────────────────────────────────────────────

    def execute(self) -> Dict[str, Any]:
        logger.info("Step 31: materialising LOINC vital-sign concepts")
        self.metrics["concepts_written"] = self._materialise_concepts()
        logger.info("  %d LOINC OntologyConcept nodes written", self.metrics["concepts_written"])

        if not self.vitals_path.exists():
            logger.warning("VITALS file not found at %s; skipping instance pass", self.vitals_path)
            self.metrics["data_blocked"] = True
            return self.metrics

        logger.info("Step 31: reading VITALS from %s", self.vitals_path)
        df = pd.read_csv(self.vitals_path, low_memory=False)
        logger.info("  %d rows loaded", len(df))

        batch: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            ptid = row.get("PTID")
            viscode = row.get("VISCODE")
            if not isinstance(ptid, str) or not isinstance(viscode, str):
                self.metrics["rows_skipped_no_visit"] += 1
                continue
            self.metrics["rows_processed"] += 1

            # ADNI VITALS records per-row units: VSWTUNIT 1 = pounds, 2 = kilograms;
            # VSHTUNIT 1 = inches, 2 = centimetres. Normalise to kg / cm before the
            # plausibility bands so imperial rows are converted rather than stored
            # mislabelled (weight) or silently dropped (height).
            weight = _safe_float(row.get("VSWEIGHT"))
            wt_unit = _safe_float(row.get("VSWTUNIT"))
            if weight is not None and wt_unit == 1:
                weight = round(weight * 0.453592, 2)
            height = _safe_float(row.get("VSHEIGHT"))
            ht_unit = _safe_float(row.get("VSHTUNIT"))
            if height is not None and ht_unit == 1:
                height = round(height * 2.54, 2)

            for biomarker_type, code, _, column, unit, lo, hi in VITAL_SIGNS:
                if biomarker_type == "BodyMassIndex":
                    value = _bmi(weight, height)
                    source_col = "derived(VSWEIGHT,VSHEIGHT)"
                elif biomarker_type == "BodyWeight":
                    value = weight
                    source_col = column
                elif biomarker_type == "BodyHeight":
                    value = height
                    source_col = column
                else:
                    value = _safe_float(row.get(column))
                    source_col = column
                if value is None or not (lo <= value <= hi):
                    self.metrics["rows_skipped_out_of_range"] += 1
                    continue
                visit_id = f"{ptid}_{viscode}"
                biomarker_id = f"{visit_id}_{biomarker_type}"
                batch.append({
                    "ptid": ptid,
                    "viscode": viscode,
                    "visit_id": visit_id,
                    "biomarker_id": biomarker_id,
                    "btype": biomarker_type,
                    "code": code,
                    "curie": f"LOINC:{code}",
                    "value": value,
                    "unit": unit,
                    "column": source_col,
                    "uri": f"{LOINC_PURL_PREFIX}{code}",
                    "rule_id": f"vitals_to_loinc:{source_col}",
                })

        logger.info("  batch size: %d biomarker writes queued", len(batch))
        if batch:
            written = self.connector.batch_write(
                CYPHER_BATCH_MERGE_BIOMARKER,
                batch,
                batch_size=1000,
                param_name="batch",
            )
            self.metrics["biomarkers_written"] = written

        self.metrics["data_blocked"] = False
        self._print_summary()
        return self.metrics

    def _print_summary(self) -> None:
        m = self.metrics
        logger.info("=" * 60)
        logger.info("STEP 31 — LOINC VITAL SIGNS SUMMARY")
        logger.info("=" * 60)
        logger.info("  LOINC OntologyConcepts: %d", m["concepts_written"])
        logger.info("  VITALS rows processed:  %d", m["rows_processed"])
        logger.info("  Biomarker writes:       %d", m["biomarkers_written"])
        logger.info("  Skipped (no visit):     %d", m["rows_skipped_no_visit"])
        logger.info("  Skipped (out of range): %d", m["rows_skipped_out_of_range"])
        logger.info("=" * 60)


def execute_step_31(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    vitals_path: Path | None = None,
    **kwargs,
) -> Dict[str, Any]:
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)
    try:
        step = LoincVitalSignsStep(connector, vitals_path or DEFAULT_VITALS_PATH)
        return step.execute()
    finally:
        connector.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", required=True)
    parser.add_argument("--vitals-path", default=str(DEFAULT_VITALS_PATH))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    execute_step_31(args.neo4j_uri, args.neo4j_user, args.neo4j_password,
                    vitals_path=Path(args.vitals_path))
