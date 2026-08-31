"""
Step 36: ADSXLIST symptom-flag A-Box
====================================
Writes the patient-side A-Box for the HPO-mappable adverse-symptom
columns in the ADSXLIST table (4,884 rows in the Aug 2025 cohort). Each
(visit, symptom-flag = 1) pair becomes a ClinicalFinding node connected
to the parent Visit through HAS_CLINICAL_FINDING and to the HPO
OntologyConcept materialised by Step 30 through MAPS_TO.

The mapping catalogue lives at `ontology/mappings/adsxlist_to_hpo.csv`
and covers 27 ADSXLIST columns spanning the gastrointestinal, neurological,
respiratory, dermatological, urogenital, musculoskeletal, and
neuropsychiatric branches of HPO.

All operations use MERGE (idempotent).

Usage:
    python -m steps.step36_adsxlist_abox --neo4j-password <pw>
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


HPO_PURL_PREFIX = "http://purl.obolibrary.org/obo/HP_"
DEFAULT_ADSXLIST_PATH = Path("inputs/Tables/Novel_Imaging_Cohort_Study_ADSXLIST_05Aug2025.csv")
DEFAULT_RULE_PATH = Path("ontology/mappings/adsxlist_to_hpo.csv")


# ─────────────────────────────────────────────────────────────────────
# Cypher
# ─────────────────────────────────────────────────────────────────────

CYPHER_MERGE_HPO_CONCEPT = """
MERGE (c:OntologyConcept {uri: $uri})
  ON CREATE SET
    c.source_ontology = 'HPO',
    c.code            = $code,
    c.label           = $label,
    c.created_at      = datetime(),
    c.created_by_step = 'step36_adsxlist_abox'
  ON MATCH SET
    c.last_seen_at    = datetime(),
    c.label           = coalesce(c.label, $label)
"""

CYPHER_BATCH_MERGE_FINDING = """
UNWIND $batch AS row
MATCH (v:Visit {visit_id: row.visit_id})
MATCH (c:OntologyConcept {uri: row.uri})
MERGE (f:ClinicalFinding {finding_id: row.finding_id})
  ON CREATE SET
    f.patient_id      = row.ptid,
    f.viscode         = row.viscode,
    f.visit_id        = row.visit_id,
    f.hpo_code        = row.code,
    f.label           = row.label,
    f.ontology_uri    = row.curie,
    f.source_table    = 'ADSXLIST',
    f.source_column   = row.column,
    f.created_at      = datetime(),
    f.created_by_step = 'step36_adsxlist_abox'
  ON MATCH SET
    f.last_seen_at    = datetime()
MERGE (v)-[:HAS_CLINICAL_FINDING]->(f)
MERGE (f)-[r:MAPS_TO]->(c)
  ON CREATE SET
    r.method     = 'curated-rule',
    r.rule_id    = row.rule_id,
    r.created_at = datetime()
"""


def _read_rule_catalogue(path: Path) -> List[Tuple[str, str, str]]:
    """Read (column, hpo_curie, label) triples from the CSV catalogue."""
    if not path.exists():
        logger.warning("Rule catalogue not found at %s", path)
        return []
    rules: List[Tuple[str, str, str]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            target = (row.get("target_uri") or "").replace("hpo:", "")
            column = row.get("source_column") or ""
            label = row.get("target_label") or ""
            if not target.startswith("HP:") or not column:
                continue
            rules.append((column, target, label))
    return rules


class AdsxlistAboxStep:
    """Step 36 driver."""

    def __init__(
        self,
        connector: Neo4jConnector,
        adsxlist_path: Path = DEFAULT_ADSXLIST_PATH,
        rule_path: Path = DEFAULT_RULE_PATH,
    ):
        self.connector = connector
        self.adsxlist_path = adsxlist_path
        self.rule_path = rule_path
        self.metrics: Dict[str, Any] = {
            "step": "step36_adsxlist_abox",
            "rules_evaluated": 0,
            "rows_processed": 0,
            "findings_written": 0,
            "visits_with_findings": 0,
            "concepts_ensured": 0,
        }

    def _ensure_concepts(self, rules: List[Tuple[str, str, str]]) -> int:
        """Ensure every HPO target concept exists at the OntologyConcept layer."""
        count = 0
        seen: set = set()
        for _, code, label in rules:
            if code in seen:
                continue
            seen.add(code)
            uri = f"{HPO_PURL_PREFIX}{code.replace('HP:', '')}"
            self.connector.run_query(
                CYPHER_MERGE_HPO_CONCEPT,
                {"uri": uri, "code": code, "label": label},
            )
            count += 1
        return count

    def _is_truthy(self, value: Any) -> bool:
        # ADSXLIST symptom flags are coded 1 = Absent, 2 = Present
        # (ADNI diagnostic checklist convention; see ADNIMERGE adsxlist docs).
        if value is None:
            return False
        try:
            return int(value) == 2
        except (TypeError, ValueError):
            return str(value).strip().upper() == "Y"

    def execute(self) -> Dict[str, Any]:
        rules = _read_rule_catalogue(self.rule_path)
        self.metrics["rules_evaluated"] = len(rules)
        logger.info("Step 36: %d ADSXLIST→HPO rules loaded", len(rules))

        if not rules:
            logger.warning("Step 36: no rules — nothing to do")
            return self.metrics

        self.metrics["concepts_ensured"] = self._ensure_concepts(rules)
        logger.info("  %d HPO OntologyConcept nodes ensured", self.metrics["concepts_ensured"])

        if not self.adsxlist_path.exists():
            logger.warning("ADSXLIST file not found at %s; skipping instance pass",
                           self.adsxlist_path)
            self.metrics["data_blocked"] = True
            return self.metrics

        df = pd.read_csv(self.adsxlist_path, low_memory=False)
        logger.info("  %d ADSXLIST rows loaded", len(df))

        visit_keys: set = set()
        batch: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            ptid = row.get("PTID")
            viscode = row.get("VISCODE")
            if not isinstance(ptid, str) or not isinstance(viscode, str):
                continue
            self.metrics["rows_processed"] += 1
            for column, code, label in rules:
                if column not in df.columns:
                    continue
                if not self._is_truthy(row.get(column)):
                    continue
                visit_id = f"{ptid}_{viscode}"
                finding_id = f"{visit_id}_{code.replace('HP:','HP')}"
                batch.append({
                    "ptid": ptid,
                    "viscode": viscode,
                    "visit_id": visit_id,
                    "finding_id": finding_id,
                    "code": code,
                    "label": label,
                    "curie": f"HPO:{code}",
                    "column": column,
                    "uri": f"{HPO_PURL_PREFIX}{code.replace('HP:', '')}",
                    "rule_id": f"adsxlist_to_hpo:{column}",
                })
                visit_keys.add(visit_id)

        logger.info("  batch size: %d finding writes queued", len(batch))
        if batch:
            written = self.connector.batch_write(
                CYPHER_BATCH_MERGE_FINDING,
                batch,
                batch_size=1000,
                param_name="batch",
            )
            self.metrics["findings_written"] = written

        self.metrics["visits_with_findings"] = len(visit_keys)
        self.metrics["data_blocked"] = False
        self._print_summary()
        return self.metrics

    def _print_summary(self) -> None:
        m = self.metrics
        logger.info("=" * 60)
        logger.info("STEP 36 — ADSXLIST → HPO A-BOX SUMMARY")
        logger.info("=" * 60)
        logger.info("  Rules evaluated:        %d", m["rules_evaluated"])
        logger.info("  HPO concepts ensured:   %d", m["concepts_ensured"])
        logger.info("  ADSXLIST rows processed: %d", m["rows_processed"])
        logger.info("  ClinicalFindings written: %d", m["findings_written"])
        logger.info("  Visits with findings:   %d", m["visits_with_findings"])
        logger.info("=" * 60)


def execute_step_36(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    adsxlist_path: Path | None = None,
    rule_path: Path | None = None,
    **kwargs,
) -> Dict[str, Any]:
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)
    try:
        step = AdsxlistAboxStep(
            connector,
            adsxlist_path or DEFAULT_ADSXLIST_PATH,
            rule_path or DEFAULT_RULE_PATH,
        )
        return step.execute()
    finally:
        connector.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", required=True)
    parser.add_argument("--adsxlist-path", default=str(DEFAULT_ADSXLIST_PATH))
    parser.add_argument("--rule-path", default=str(DEFAULT_RULE_PATH))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    execute_step_36(
        args.neo4j_uri,
        args.neo4j_user,
        args.neo4j_password,
        adsxlist_path=Path(args.adsxlist_path),
        rule_path=Path(args.rule_path),
    )
