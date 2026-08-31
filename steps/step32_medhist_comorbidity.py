"""
Step 32: MEDHIST Category-Level Comorbidity Materialisation
===========================================================
Closes the MEDHIST half of Contribution 3 (column-to-concept mapping for
patient-level data).

The MEDHIST table (2,423 rows in the Aug 2025 cohort) records one row per
patient-visit with category-level history flags: psychiatric, neurological,
head injury, cardiovascular, respiratory, hepatic, dermatological,
musculoskeletal, endocrine, gastrointestinal, hematological, renal,
allergy, alcohol, drug, smoking, malignancy, surgery. Each flag is a 0/1
sentinel. Step~32 maps the eleven categories that have a clean SNOMED-CT
parent class onto a Comorbidity node per (patient, category) pair where
the flag is set.

Granularity discipline. SNOMED codes are at category level. A
finer-grained mapping (per disease) is not recoverable from a MEDHIST
flag alone; the Comorbidity node carries a `granularity = 'category'`
marker so downstream consumers cannot over-interpret the code.

All operations use MERGE (idempotent).

Usage:
    python -m steps.step32_medhist_comorbidity --neo4j-password <pw>
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Catalogue: (category_key, label, snomed_code, medhist_column)
# Codes are upper-tier SNOMED Clinical Finding categories chosen because
# the MEDHIST source records the presence of a category-level history
# rather than the underlying diagnosis.
# ─────────────────────────────────────────────────────────────────────

CATEGORIES: List[Tuple[str, str, str, str]] = [
    ("psychiatric",      "Mental disorder",              "74732009",  "MHPSYCH"),
    ("neurological",     "Disorder of nervous system",   "118940003", "MH2NEURL"),
    # MH3HEAD is the HEENT review-of-systems category (Head, Eyes, Ears,
    # Nose and Throat), not head trauma — see ADNIMERGE medhist reference.
    ("heent",            "Disorder of head",             "118934005", "MH3HEAD"),
    ("cardiovascular",   "Disorder of cardiovascular system", "49601007", "MH4CARD"),
    ("respiratory",      "Disorder of respiratory system", "50043002", "MH5RESP"),
    ("hepatic",          "Disorder of liver",            "235856003", "MH6HEPAT"),
    ("dermatological",   "Skin disorder",                "95320005",  "MH7DERM"),
    ("musculoskeletal",  "Disorder of musculoskeletal system", "928000", "MH8MUSCL"),
    ("endocrine",        "Endocrine disorder",           "362969004", "MH9ENDO"),
    ("gastrointestinal", "Disorder of digestive system", "53619000",  "MH10GAST"),
    ("hematological",    "Disorder of haematopoietic structure", "414022008", "MH11HEMA"),
    ("renal",            "Disorder of urinary system",   "42030000",  "MH12RENA"),
    ("allergy",          "Allergic disorder",            "609328004", "MH13ALLE"),
    ("alcohol_history",  "Personal history of alcohol misuse", "160573003", "MH14ALCH"),
    ("drug_history",     "Personal history of drug abuse", "417662000", "MH15DRUG"),
    ("smoking_history",  "Smoker",                       "77176002",  "MH16SMOK"),
    ("malignancy",       "Neoplastic disease",           "55342001",  "MH17MALI"),
    ("surgery_history",  "Personal history of surgery",  "161615003", "MH18SURG"),
]

SNOMED_PURL_PREFIX = "http://snomed.info/id/"
DEFAULT_MEDHIST_PATH = Path("inputs/Tables/Novel_Imaging_Cohort_Study_MEDHIST_05Aug2025.csv")


# ─────────────────────────────────────────────────────────────────────
# Cypher
# ─────────────────────────────────────────────────────────────────────

CYPHER_MERGE_CONCEPT = """
MERGE (c:OntologyConcept {uri: $uri})
  ON CREATE SET
    c.source_ontology = 'SNOMED-CT',
    c.code            = $code,
    c.label           = $label,
    c.granularity     = 'category',
    c.created_at      = datetime(),
    c.created_by_step = 'step32_medhist_comorbidity'
  ON MATCH SET
    c.last_seen_at    = datetime(),
    c.label           = coalesce(c.label, $label)
"""

CYPHER_BATCH_MERGE_COMORBIDITY = """
UNWIND $batch AS row
MATCH (p:Patient {ptid: row.ptid})
MERGE (m:Comorbidity {comorbidity_id: row.comorbidity_id})
  ON CREATE SET
    m.patient_id       = row.ptid,
    m.category         = row.category,
    m.snomed_code      = row.code,
    m.ontology_uri     = row.curie,
    m.label            = row.label,
    m.granularity      = 'category',
    m.source_table     = 'MEDHIST',
    m.source_column    = row.column,
    m.created_at       = datetime(),
    m.created_by_step  = 'step32_medhist_comorbidity'
  ON MATCH SET
    m.last_seen_at     = datetime()
MERGE (p)-[:HAS_COMORBIDITY]->(m)
WITH m, row
MATCH (c:OntologyConcept {uri: row.uri})
MERGE (m)-[r:MAPS_TO]->(c)
  ON CREATE SET
    r.method     = 'curated-rule',
    r.rule_id    = row.rule_id,
    r.created_at = datetime()
"""


class MedHistComorbidityStep:
    """Step 32 driver."""

    def __init__(self, connector: Neo4jConnector, medhist_path: Path = DEFAULT_MEDHIST_PATH):
        self.connector = connector
        self.medhist_path = medhist_path
        self.metrics: Dict[str, Any] = {
            "step": "step32_medhist_comorbidity",
            "concepts_written": 0,
            "comorbidities_written": 0,
            "patients_with_at_least_one_comorbidity": 0,
            "rows_processed": 0,
        }

    def _materialise_concepts(self) -> int:
        written = 0
        for _, label, code, _ in CATEGORIES:
            uri = f"{SNOMED_PURL_PREFIX}{code}"
            self.connector.run_query(
                CYPHER_MERGE_CONCEPT,
                {"uri": uri, "code": code, "label": label},
            )
            written += 1
        return written

    def _is_flag_truthy(self, value: Any) -> bool:
        # MEDHIST encodes presence as 1 (Y), absence as 0 (N) or NaN.
        # ADNI sometimes uses the strings "Y"/"N" interchangeably.
        if value is None:
            return False
        try:
            return int(value) == 1
        except (TypeError, ValueError):
            return str(value).strip().upper() == "Y"

    def execute(self) -> Dict[str, Any]:
        logger.info("Step 32: materialising MEDHIST category-level SNOMED concepts")
        self.metrics["concepts_written"] = self._materialise_concepts()
        logger.info("  %d SNOMED OntologyConcept nodes written", self.metrics["concepts_written"])

        if not self.medhist_path.exists():
            logger.warning("MEDHIST file not found at %s; skipping instance pass", self.medhist_path)
            self.metrics["data_blocked"] = True
            return self.metrics

        df = pd.read_csv(self.medhist_path, low_memory=False)
        logger.info("  %d MEDHIST rows loaded", len(df))

        # MEDHIST records one row per patient-visit. Collapse to per-patient
        # by OR-ing the flags; if a patient has the flag set on any visit,
        # they carry that comorbidity at the patient-hub level.
        per_patient: Dict[str, set] = {}
        for _, row in df.iterrows():
            ptid = row.get("PTID")
            if not isinstance(ptid, str):
                continue
            self.metrics["rows_processed"] += 1
            for category, label, code, column in CATEGORIES:
                if column not in df.columns:
                    continue
                if not self._is_flag_truthy(row.get(column)):
                    continue
                per_patient.setdefault(ptid, set()).add((category, label, code, column))

        batch: List[Dict[str, Any]] = []
        for ptid, items in per_patient.items():
            for category, label, code, column in items:
                batch.append({
                    "ptid": ptid,
                    "category": category,
                    "comorbidity_id": f"{ptid}_{category}",
                    "code": code,
                    "curie": f"SNOMED-CT:{code}",
                    "label": label,
                    "column": column,
                    "uri": f"{SNOMED_PURL_PREFIX}{code}",
                    "rule_id": f"medhist_to_snomed:{column}",
                })

        logger.info("  batch size: %d comorbidity writes queued", len(batch))
        if batch:
            written = self.connector.batch_write(
                CYPHER_BATCH_MERGE_COMORBIDITY,
                batch,
                batch_size=1000,
                param_name="batch",
            )
            self.metrics["comorbidities_written"] = written

        self.metrics["patients_with_at_least_one_comorbidity"] = len(per_patient)
        self.metrics["data_blocked"] = False
        self._print_summary()
        return self.metrics

    def _print_summary(self) -> None:
        m = self.metrics
        logger.info("=" * 60)
        logger.info("STEP 32 — MEDHIST COMORBIDITY SUMMARY")
        logger.info("=" * 60)
        logger.info("  SNOMED-CT OntologyConcepts:  %d", m["concepts_written"])
        logger.info("  MEDHIST rows processed:      %d", m["rows_processed"])
        logger.info("  Comorbidity edges written:   %d", m["comorbidities_written"])
        logger.info("  Patients with ≥1 comorbidity: %d", m["patients_with_at_least_one_comorbidity"])
        logger.info("=" * 60)


def execute_step_32(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    medhist_path: Path | None = None,
    **kwargs,
) -> Dict[str, Any]:
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)
    try:
        step = MedHistComorbidityStep(connector, medhist_path or DEFAULT_MEDHIST_PATH)
        return step.execute()
    finally:
        connector.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", required=True)
    parser.add_argument("--medhist-path", default=str(DEFAULT_MEDHIST_PATH))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    execute_step_32(args.neo4j_uri, args.neo4j_user, args.neo4j_password,
                    medhist_path=Path(args.medhist_path))
