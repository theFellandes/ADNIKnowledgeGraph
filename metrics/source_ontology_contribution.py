"""Source-ontology contribution to edge URI coverage.

Decomposes the aggregate edge URI coverage by the vocabulary that supplies
each edge's predicate URI. The MAKO graph carries six URI namespaces:

  - RO   (OBO Relation Ontology)
  - Biolink Model
  - SKOS (RDF/SKOS legacy edges)
  - RDFS (rdf-schema:subClassOf / domain / range)
  - OWL  (owl:equivalentClass / sameAs)
  - Internal-MAKO (project-internal aggregation predicates)

The output JSON lists each source's edge count and its share of the total
edges-with-URI. The thesis cites this breakdown in Section 4.4 to resolve
the otherwise-opaque 99.68% edge URI coverage into its component sources.

CLI::

    python -m metrics.source_ontology_contribution
    python -m metrics.source_ontology_contribution --output outputs/metrics/source_ontology_contribution.json
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
class SourceRow:
    source: str
    edges_with_uri: int

    def to_dict(self, total: int) -> dict[str, Any]:
        share = (self.edges_with_uri / total) if total > 0 else 0.0
        return {
            "source": self.source,
            "edges_with_uri": self.edges_with_uri,
            "share": round(share, 6),
        }


@dataclass
class SourceContributionReport:
    schema_version: int
    timestamp: str
    graph_uri: str
    total_edges_with_uri: int
    sources: list[SourceRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "graph_uri": self.graph_uri,
            "total_edges_with_uri": self.total_edges_with_uri,
            "sources": [r.to_dict(self.total_edges_with_uri) for r in self.sources],
        }


_QUERY = """
MATCH ()-[r]->()
WITH r,
     coalesce(r.uri, r.ro_uri, r.biolink_predicate, '') AS u,
     r.biolink_predicate AS bp
WHERE u <> '' OR bp IS NOT NULL
WITH u, bp,
     CASE
       WHEN u STARTS WITH 'ro:RO_'                                     THEN 'RO'
       WHEN u STARTS WITH 'http://purl.obolibrary.org/obo/RO_'         THEN 'RO'
       WHEN u STARTS WITH 'biolink:'                                   THEN 'Biolink'
       WHEN u STARTS WITH 'https://w3id.org/biolink/'                  THEN 'Biolink'
       WHEN u STARTS WITH 'http://w3id.org/biolink/'                   THEN 'Biolink'
       WHEN u STARTS WITH 'skos:'                                      THEN 'SKOS'
       WHEN u STARTS WITH 'http://www.w3.org/2004/02/skos/'            THEN 'SKOS'
       WHEN u STARTS WITH 'rdfs:'                                      THEN 'RDFS'
       WHEN u STARTS WITH 'http://www.w3.org/2000/01/rdf-schema#'      THEN 'RDFS'
       WHEN u STARTS WITH 'owl:'                                       THEN 'OWL'
       WHEN u STARTS WITH 'http://www.w3.org/2002/07/owl#'             THEN 'OWL'
       WHEN u STARTS WITH 'time:'                                      THEN 'OWL-Time'
       WHEN u STARTS WITH 'http://www.w3.org/2006/time#'               THEN 'OWL-Time'
       WHEN u STARTS WITH 'http://purl.obolibrary.org/obo/'            THEN 'OBO (other)'
       WHEN u CONTAINS 'theFellandes' OR u CONTAINS 'mako/'            THEN 'Internal-MAKO'
       WHEN u = '' AND bp IS NOT NULL                                  THEN 'Biolink'
       ELSE 'Other'
     END AS source
RETURN source, count(*) AS edges_with_uri
ORDER BY edges_with_uri DESC
"""


class Connector:
    def run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError


def compute(connector: Connector, *, graph_uri: str = "(unknown)") -> SourceContributionReport:
    started = time.time()
    rows = connector.run_query(_QUERY) or []
    source_rows: list[SourceRow] = []
    total = 0
    for r in rows:
        src = str(r.get("source", "Other"))
        n = int(r.get("edges_with_uri", 0) or 0)
        source_rows.append(SourceRow(source=src, edges_with_uri=n))
        total += n
    logger.debug("source_ontology_contribution compute finished in %.2f s", time.time() - started)
    return SourceContributionReport(
        schema_version=1,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        graph_uri=graph_uri,
        total_edges_with_uri=total,
        sources=source_rows,
    )


def write_json(report: SourceContributionReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics.source_ontology_contribution",
        description="Decompose edge URI coverage by source ontology namespace.",
    )
    p.add_argument(
        "--output",
        default="outputs/metrics/source_ontology_contribution.json",
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
