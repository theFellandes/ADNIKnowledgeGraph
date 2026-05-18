"""T-Box vs A-Box weight per source ontology.

For each of the eight source ontologies (SNOMED-CT, LOINC, UBERON, HPO, ICD-10,
MONDO, DOID, GO), this script counts:

  - T-Box weight: number of :OntologyConcept nodes with that source_ontology
  - A-Box weight: number of distinct non-concept nodes connected to one of those
                  concept nodes by a MAPS_TO edge

The A-Box / T-Box ratio is a useful indicator: a high ratio means the schema
concept is heavily used by patient instances; a ratio of zero means the concept
is declared but never instantiated.

CLI::

    python -m metrics.tbox_abox                                  # uses .env credentials
    python -m metrics.tbox_abox --output outputs/metrics/tbox_abox.json
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


DEFAULT_SOURCES: tuple[str, ...] = (
    "SNOMED-CT",
    "LOINC",
    "UBERON",
    "HPO",
    "ICD-10",
    "MONDO",
    "DOID",
    "GO",
)


@dataclass
class TBoxABoxRow:
    source_ontology: str
    tbox_concepts: int
    abox_instances: int

    @property
    def ratio(self) -> float:
        return (self.abox_instances / self.tbox_concepts) if self.tbox_concepts > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_ontology": self.source_ontology,
            "tbox_concepts": self.tbox_concepts,
            "abox_instances": self.abox_instances,
            "abox_to_tbox_ratio": round(self.ratio, 2),
        }


@dataclass
class TBoxABoxReport:
    schema_version: int
    timestamp: str
    graph_uri: str
    rows: list[TBoxABoxRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "graph_uri": self.graph_uri,
            "rows": [r.to_dict() for r in self.rows],
            "tbox_total": sum(r.tbox_concepts for r in self.rows),
            "abox_total": sum(r.abox_instances for r in self.rows),
        }


class Connector:
    def run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError


_TBOX_QUERY = (
    "MATCH (c:OntologyConcept {source_ontology: $src}) "
    "RETURN count(c) AS tbox"
)

_ABOX_QUERY = (
    "MATCH (n)-[r:MAPS_TO|CLASSIFIED_AS|PARTICIPATES_IN|ENCODES]->"
    "(c:OntologyConcept {source_ontology: $src}) "
    "WHERE NOT n:OntologyConcept "
    "RETURN count(DISTINCT n) AS abox"
)


def compute(
    connector: Connector,
    *,
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    graph_uri: str = "(unknown)",
) -> TBoxABoxReport:
    started = time.time()
    rows: list[TBoxABoxRow] = []
    for src in sources:
        tbox_row = connector.run_query(_TBOX_QUERY, {"src": src})
        abox_row = connector.run_query(_ABOX_QUERY, {"src": src})
        tbox = int(tbox_row[0]["tbox"]) if tbox_row else 0
        abox = int(abox_row[0]["abox"]) if abox_row else 0
        rows.append(TBoxABoxRow(source_ontology=src, tbox_concepts=tbox, abox_instances=abox))
    logger.debug("tbox_abox compute finished in %.2f s", time.time() - started)
    return TBoxABoxReport(
        schema_version=1,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        graph_uri=graph_uri,
        rows=rows,
    )


def write_json(report: TBoxABoxReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics.tbox_abox",
        description="Compute T-Box vs A-Box weight per source ontology.",
    )
    p.add_argument(
        "--output",
        default="outputs/metrics/tbox_abox.json",
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
        raise RuntimeError("Neo4j credentials missing — set NEO4J_URI/USER/PASSWORD or pass flags")
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

    out = Path(args.output)
    if not out.is_absolute():
        out = Path(__file__).resolve().parents[1] / out
    write_json(report, out)
    logger.info("Wrote %s", out)
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
