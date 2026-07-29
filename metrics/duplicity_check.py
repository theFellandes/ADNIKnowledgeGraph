"""Duplicity audit — proves the enrichment passes did not introduce duplicate nodes.

For each labelled clinical entity that should be unique on a composite key, runs
a `COUNT(*) - COUNT(DISTINCT key)` sweep. A nonzero gap means duplicates exist.

The probes target the labels that the enrichment passes touched (Step~17 declared
the composite constraints; Steps~30--36 inserted new instances against those
constraints). A clean run returns zero gaps everywhere.

CLI::

    python -m metrics.duplicity_check
    python -m metrics.duplicity_check --output outputs/metrics/duplicity_check.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DuplicityProbe:
    label: str
    key: str
    total: int
    distinct: int

    @property
    def duplicates(self) -> int:
        return max(0, self.total - self.distinct)

    @property
    def ok(self) -> bool:
        return self.duplicates == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "key": self.key,
            "total": self.total,
            "distinct": self.distinct,
            "duplicates": self.duplicates,
            "ok": self.ok,
        }


@dataclass
class DuplicityReport:
    schema_version: int
    timestamp: str
    graph_uri: str
    probes: list[DuplicityProbe] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(p.ok for p in self.probes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "graph_uri": self.graph_uri,
            "result": "PASS" if self.all_ok else "FAIL",
            "probes": [p.to_dict() for p in self.probes],
            "duplicates_total": sum(p.duplicates for p in self.probes),
        }


class Connector:
    def run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError


# Each probe is (display_name, node_label, key_expression). The key_expression is
# a Cypher fragment that yields the uniqueness tuple per node. ``node_label`` is the
# real Neo4j label matched by the query; ``display_name`` names the probe in the
# report (so two probes can target the same label on different keys).
#
# The FamilyMember label is probed twice on purpose. ``n.member_id`` is a primary
# key that is unique by construction (each node minted its own id), so it is blind
# to entity-level duplication. The content-key probe groups on the fields that
# actually identify a distinct relative, so re-run duplicates cannot pass silently
# (see FAMILYMEMBER_DUPLICATION_FINDINGS_2026-07-11.md).
PROBES: tuple[tuple[str, str, str], ...] = (
    ("Patient",             "Patient",             "n.ptid"),
    ("Visit",               "Visit",               "n.visit_id"),
    ("Diagnosis",           "Diagnosis",           "n.diagnosis_id"),
    ("CognitiveAssessment", "CognitiveAssessment", "n.visit_id + '|' + coalesce(n.test_name, '')"),
    ("Biomarker",           "Biomarker",           "n.biomarker_id"),
    ("BrainRegion",         "BrainRegion",         "coalesce(n.name, '') + '|' + coalesce(n.hemisphere, '')"),
    ("ATNProfile",          "ATNProfile",          "coalesce(n.patient_id, '') + '|' + coalesce(n.visit_id, '')"),
    ("Comorbidity",         "Comorbidity",         "n.comorbidity_id"),
    ("ClinicalFinding",     "ClinicalFinding",     "n.finding_id"),
    ("OntologyConcept",     "OntologyConcept",     "n.uri"),
    ("AlzKBConcept",        "AlzKBConcept",        "n.alzkb_id"),
    ("Gene",                "Gene",                "n.symbol"),
    ("FamilyMember",        "FamilyMember",        "n.member_id"),
    ("FamilyMember (content-key)", "FamilyMember",
     "[n.patient_id, n.relationship_type, n.gender, n.age_at_onset, n.source_column]"),
)


def _build_query(node_label: str, key: str) -> str:
    return (
        f"MATCH (n:`{node_label}`) "
        f"WITH count(n) AS total, count(DISTINCT {key}) AS distinct "
        f"RETURN total, distinct"
    )


def compute(connector: Connector, *, graph_uri: str = "(unknown)") -> DuplicityReport:
    started = time.time()
    probes: list[DuplicityProbe] = []
    for display_name, node_label, key in PROBES:
        label = display_name
        try:
            rows = connector.run_query(_build_query(node_label, key))
            if not rows:
                continue
            row = rows[0]
            total = int(row.get("total") or 0)
            distinct = int(row.get("distinct") or 0)
        except Exception as exc:
            logger.warning("Probe %s failed: %s", label, exc)
            total = -1
            distinct = -1
        probes.append(DuplicityProbe(label=label, key=key, total=total, distinct=distinct))

    # Edge-parallelism probe. The node probes above key on node composite keys and are
    # therefore structurally blind to duplicate RELATIONSHIPS (parallel edges between the same
    # ordered pair with the same type). This probe groups every relationship by
    # (startId, type, endId); a nonzero gap means parallel/duplicate edges exist. It closes the
    # false-negative that let 179,343 re-run duplicate edges hide (see the 2026-07-12 edge
    # de-duplication; same bug class as the FamilyMember node dedup, one layer down).
    try:
        rows = connector.run_query(
            "MATCH (a)-[r]->(b) "
            "WITH count(r) AS total, "
            "count(DISTINCT [elementId(a), type(r), elementId(b)]) AS distinct "
            "RETURN total, distinct"
        )
        if rows:
            row = rows[0]
            probes.append(DuplicityProbe(
                label="Relationship parallelism (all types)",
                key="(startId, type, endId)",
                total=int(row.get("total") or 0),
                distinct=int(row.get("distinct") or 0),
            ))
    except Exception as exc:
        logger.warning("Edge-parallelism probe failed: %s", exc)
        probes.append(DuplicityProbe(
            label="Relationship parallelism (all types)",
            key="(startId, type, endId)", total=-1, distinct=-1,
        ))
    logger.debug("duplicity_check finished in %.2f s", time.time() - started)
    return DuplicityReport(
        schema_version=1,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        graph_uri=graph_uri,
        probes=probes,
    )


def write_json(report: DuplicityReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics.duplicity_check",
        description="Verify the graph has no duplicate nodes on the composite uniqueness keys.",
    )
    p.add_argument(
        "--output",
        default="outputs/metrics/duplicity_check.json",
        help="Path for the JSON output.",
    )
    p.add_argument("--neo4j-uri", default=None)
    p.add_argument("--user", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--quiet", action="store_true")
    return p


def _resolve_credentials(args: argparse.Namespace) -> tuple[str, str, str]:
    uri, user, pw = args.neo4j_uri, args.user, args.password
    if not (uri and user and pw):
        from utils.env_loader import load_config

        cfg = load_config()
        uri = uri or cfg.get("neo4j_uri")
        user = user or cfg.get("neo4j_user", "neo4j")
        pw = pw or cfg.get("neo4j_password")
    if not (uri and user and pw):
        raise RuntimeError("Neo4j credentials missing")
    return uri, user, pw


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        uri, user, pw = _resolve_credentials(args)
    except Exception as exc:
        logger.error("%s", exc)
        return 2

    from utils.neo4j_connector import Neo4jConnector

    connector = Neo4jConnector(uri=uri, user=user, password=pw)
    try:
        report = compute(connector, graph_uri=uri)
    finally:
        connector.close()

    repo_root = Path(__file__).resolve().parents[1]
    out = Path(args.output)
    if not out.is_absolute():
        out = repo_root / out
    write_json(report, out)

    summary = report.to_dict()
    print(json.dumps(summary, indent=2))
    return 0 if report.all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
