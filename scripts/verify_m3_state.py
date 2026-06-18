"""Read-only verification of the live graph state ahead of the M3 migration.

Prints current node/edge totals, the SAME_AS edge inventory, the Phenotype
strong-match path, and the exact 3 edges M3 targets (with full properties so a
rollback script can be authored). Mutates nothing.
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
    pw = cfg.get("neo4j_password")
    candidates = [pw, "your_password"]
    conn = None
    for cand in candidates:
        if not cand:
            continue
        try:
            c = Neo4jConnector(uri=uri, user=user, password=cand)
            if c.verify_connection():
                conn = c
                print(f"[ok] connected to {uri} as {user} (pw source: "
                      f"{'config/.env' if cand == pw else 'fallback your_password'})")
                break
            c.close()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] auth attempt failed: {exc}")
    if conn is None:
        print("[fatal] could not connect to Neo4j with any candidate credential")
        return 2

    try:
        out = {}
        out["node_total"] = conn.run_query("MATCH (n) RETURN count(n) AS c")[0]["c"]
        out["edge_total"] = conn.run_query("MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
        out["same_as_total"] = conn.run_query(
            "MATCH ()-[r:SAME_AS]->() RETURN count(r) AS c")[0]["c"]
        out["mondo_concepts"] = conn.run_query(
            "MATCH (o:OntologyConcept) WHERE o.source_ontology='MONDO' "
            "RETURN count(o) AS c")[0]["c"]
        out["ontology_concept_total"] = conn.run_query(
            "MATCH (o:OntologyConcept) RETURN count(o) AS c")[0]["c"]

        # Full SAME_AS inventory
        out["same_as_inventory"] = conn.run_query(
            "MATCH (a:AlzKBConcept)-[r:SAME_AS]->(o:OntologyConcept) "
            "RETURN a.alzkb_id AS alzkb_id, a.source_type AS alzkb_type, "
            "o.uri AS o_uri, o.code AS o_code, o.source_ontology AS o_src, "
            "o.label AS o_label "
            "ORDER BY a.source_type, a.alzkb_id"
        )

        # Phenotype strong-match path (what the metric counts as Phenotype=1)
        out["phenotype_strong_paths"] = conn.run_query(
            "MATCH (a:AlzKBConcept)-[:SAME_AS]->(o:OntologyConcept) "
            "WHERE toUpper(o.source_ontology)='HPO' "
            "  AND a.source_type IN ['Symptom','BiologicalProcess'] "
            "RETURN a.alzkb_id AS alzkb_id, a.source_type AS alzkb_type, "
            "a.label AS alzkb_label, o.uri AS o_uri, o.code AS o_code, "
            "o.label AS o_label"
        )

        # The exact 3 edges M3 targets, with all edge + endpoint properties
        out["m3_target_edges"] = conn.run_query(
            "MATCH (a:AlzKBConcept)-[r:SAME_AS]->(o:OntologyConcept) "
            "WHERE (a.alzkb_id='alzkb:bp_neuroinflammation' AND o.uri='hpo:HP:0002354') "
            "   OR (a.alzkb_id='alzkb:disease_MCI'           AND o.uri='hpo:HP:0100543') "
            "   OR (a.alzkb_id='alzkb:disease_dementia'      AND o.uri='hpo:HP:0000726') "
            "RETURN a.alzkb_id AS alzkb_id, a.source_type AS alzkb_type, "
            "labels(a) AS a_labels, properties(a) AS a_props, "
            "o.uri AS o_uri, o.code AS o_code, o.source_ontology AS o_src, "
            "o.label AS o_label, properties(r) AS r_props, type(r) AS r_type"
        )

        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
