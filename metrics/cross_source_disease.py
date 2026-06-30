"""Cross-source AlzKB Disease alignment via shared canonical PURLs (T06).

Reviewer ask (supervisor review): the naive AlzKB Disease bridge is SNOMED-CT-keyed
(2/35 strong). This module measures an INDEPENDENT, second-route Disease alignment
on shared **DOID** identifiers (and MONDO where present): an AlzKB ``Disease`` node
(``properties.disease_id`` = a DOID) matches a MAKO Diagnosis grounding iff MAKO
carries the SAME DOID (via a :OntologyConcept(source_ontology='DOID')) or the
co-referent MONDO PURL.

Integrity note: this is reported as a CONFIRMATION of the existing 2 bridges via a
second identifier route, NOT as an uplift. The measured result is whatever the live
graph yields; the supervisor email's hope that it "should raise the Disease figure"
is not assumed.

CLI::

    python -m metrics.cross_source_disease
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _norm_doid(s: str) -> str | None:
    """Normalise any DOID serialisation to canonical ``DOID:NNNN``."""
    if not s:
        return None
    m = re.search(r"DOID[:_](\d+)", s, re.IGNORECASE)
    return f"DOID:{m.group(1)}" if m else None


def measure(connector) -> dict[str, Any]:
    # AlzKB Disease nodes carry their DOID in the properties JSON string.
    alzkb_rows = connector.run_query(
        "MATCH (a:AlzKBConcept) WHERE a.source_type='Disease' "
        "RETURN a.label AS label, a.properties AS props")
    alzkb_doids: dict[str, str] = {}
    for r in alzkb_rows:
        try:
            pid = json.loads(r["props"] or "{}").get("disease_id", "")
        except (json.JSONDecodeError, TypeError):
            pid = ""
        d = _norm_doid(pid)
        if d:
            alzkb_doids[d] = r["label"]

    # MAKO Disease-side DOID groundings (OntologyConcept, any DOID serialisation).
    mako_rows = connector.run_query(
        "MATCH (o:OntologyConcept) WHERE toUpper(o.source_ontology)='DOID' "
        "RETURN o.uri AS uri, o.label AS label")
    mako_doids: dict[str, str] = {}
    for r in mako_rows:
        d = _norm_doid(r["uri"])
        if d:
            mako_doids[d] = r["label"]

    shared = sorted(set(alzkb_doids) & set(mako_doids))
    matches = [{"doid": d, "alzkb_label": alzkb_doids[d], "mako_label": mako_doids[d]} for d in shared]

    # Naive (existing) bridge count for the honesty comparison.
    naive = connector.run_query(
        "MATCH (a:AlzKBConcept)-[:SAME_AS]->(o:OntologyConcept) "
        "WHERE a.source_type='Disease' AND toUpper(o.source_ontology)='SNOMED-CT' "
        "RETURN count(DISTINCT o) AS n")
    naive_n = int(naive[0]["n"]) if naive else 0

    return {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": ("Cross-source Disease alignment on shared DOID PURLs: an AlzKB Disease "
                   "node (properties.disease_id) matches a MAKO Diagnosis grounding iff MAKO "
                   "carries the same DOID via a DOID OntologyConcept. Reported as a second-route "
                   "confirmation of the existing bridges, not an uplift."),
        "alzkb_disease_doids": alzkb_doids,
        "mako_disease_doids": mako_doids,
        "shared_doids": matches,
        "cross_source_disease_strong": len(shared),
        "naive_snomed_disease_strong": naive_n,
        "uplift_vs_naive": len(shared) - naive_n,
        "note": ("MCI does not cross-match: AlzKB MCI=DOID:0060903 differs from MAKO MCI=DOID:0080832, "
                 "and MONDO has no MCI term. EOAD/LOAD/Tauopathy have no MAKO DOID grounding. So the "
                 "shared-PURL route confirms AD (DOID:10652) and Dementia (DOID:1307) — the same two "
                 "bridges as the SNOMED-CT route, via a second identifier system; no uplift."),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m metrics.cross_source_disease")
    p.add_argument("--output", default="outputs/metrics/cross_source_disease.json")
    p.add_argument("--neo4j-uri", default=None)
    p.add_argument("--user", default=None)
    p.add_argument("--password", default=None)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    uri, user, pw = args.neo4j_uri, args.user, args.password
    if not (uri and user and pw):
        from utils.env_loader import load_config
        cfg = load_config()
        uri = uri or cfg.get("neo4j_uri")
        user = user or cfg.get("neo4j_user", "neo4j")
        pw = pw or cfg.get("neo4j_password")

    from utils.neo4j_connector import Neo4jConnector
    connector = Neo4jConnector(uri=uri, user=user, password=pw)
    try:
        result = measure(connector)
    finally:
        connector.close()

    out = Path(args.output)
    if not out.is_absolute():
        out = PROJECT_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info("Wrote %s", out)
    print(json.dumps({
        "cross_source_disease_strong": result["cross_source_disease_strong"],
        "naive_snomed_disease_strong": result["naive_snomed_disease_strong"],
        "uplift_vs_naive": result["uplift_vs_naive"],
        "shared_doids": [m["doid"] for m in result["shared_doids"]],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
