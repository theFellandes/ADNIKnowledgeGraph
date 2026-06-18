"""Read-only inventory to seed the valid-phenotype-bridge research.

Dumps every AlzKBConcept (grouped by source_type, with embedded identifiers)
and every HPO OntologyConcept on the MAKO side. Mutates nothing.
"""

from __future__ import annotations

import json
import sys

from utils.env_loader import load_config
from utils.neo4j_connector import Neo4jConnector


def main() -> int:
    cfg = load_config()
    uri = cfg.get("neo4j_uri", "bolt://localhost:7687")
    user = cfg.get("neo4j_user", "neo4j")
    pw = cfg.get("neo4j_password") or "your_password"
    conn = Neo4jConnector(uri=uri, user=user, password=pw)
    try:
        out = {}
        out["alzkb_by_type"] = conn.run_query(
            "MATCH (a:AlzKBConcept) "
            "RETURN a.source_type AS source_type, count(*) AS n "
            "ORDER BY source_type"
        )
        out["alzkb_concepts"] = conn.run_query(
            "MATCH (a:AlzKBConcept) "
            "RETURN a.source_type AS source_type, a.alzkb_id AS alzkb_id, "
            "a.label AS label, a.properties AS properties "
            "ORDER BY a.source_type, a.alzkb_id"
        )
        out["hpo_concepts"] = conn.run_query(
            "MATCH (o:OntologyConcept) WHERE toUpper(o.source_ontology)='HPO' "
            "RETURN o.code AS code, o.label AS label, o.uri AS uri "
            "ORDER BY o.code"
        )
        # Which AlzKB Symptom/BiologicalProcess nodes carry an HPO id in props?
        out["alzkb_symptom_like"] = conn.run_query(
            "MATCH (a:AlzKBConcept) "
            "WHERE a.source_type IN ['Symptom','BiologicalProcess','Phenotype'] "
            "RETURN a.source_type AS source_type, a.alzkb_id AS alzkb_id, "
            "a.label AS label, a.properties AS properties "
            "ORDER BY a.source_type, a.alzkb_id"
        )
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
