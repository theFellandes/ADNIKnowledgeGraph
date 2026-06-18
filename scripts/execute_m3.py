"""M3 migration: remove the three miswired AlzKB SAME_AS edges.

Surgical + reversible:
  1. Re-derive the exact 3 target edges; ABORT unless exactly 3 are present.
  2. Write an exact rollback Cypher (recreates the 3 edges with original props)
     to backups/20260617/M3_rollback.cypher BEFORE any delete.
  3. DELETE the 3 edges in one write transaction.
  4. Re-verify post-state and print a before/after summary.

The three edges (all written by step24_alzkb_bridge.py):
  - bp_neuroinflammation (GO:0150076) -SAME_AS-> HP:0002354  (the sole, invalid Phenotype match)
  - disease_MCI         (DOID:0060903)-SAME_AS-> HP:0100543  (Disease wired to an HPO phenotype)
  - disease_dementia    (DOID:1307)   -SAME_AS-> HP:0000726  (spurious 2nd edge; SNOMED bridge kept)
"""

from __future__ import annotations

import sys
from pathlib import Path

from utils.env_loader import load_config
from utils.neo4j_connector import Neo4jConnector

ROLLBACK_PATH = Path("backups/20260617/M3_rollback.cypher")

MATCH_TARGETS = (
    "MATCH (a:AlzKBConcept)-[r:SAME_AS]->(o:OntologyConcept) "
    "WHERE (a.alzkb_id='alzkb:bp_neuroinflammation' AND o.uri='hpo:HP:0002354') "
    "   OR (a.alzkb_id='alzkb:disease_MCI'           AND o.uri='hpo:HP:0100543') "
    "   OR (a.alzkb_id='alzkb:disease_dementia'      AND o.uri='hpo:HP:0000726') "
)


def _scalar(conn, q):
    rows = conn.run_query(q)
    return rows[0][list(rows[0].keys())[0]] if rows else None


def main() -> int:
    cfg = load_config()
    uri = cfg.get("neo4j_uri", "bolt://localhost:7687")
    user = cfg.get("neo4j_user", "neo4j")
    pw = cfg.get("neo4j_password") or "your_password"
    conn = Neo4jConnector(uri=uri, user=user, password=pw)
    try:
        # ---- BEFORE ----
        before = {
            "node_total": _scalar(conn, "MATCH (n) RETURN count(n) AS c"),
            "edge_total": _scalar(conn, "MATCH ()-[r]->() RETURN count(r) AS c"),
            "same_as_total": _scalar(conn, "MATCH ()-[r:SAME_AS]->() RETURN count(r) AS c"),
        }

        targets = conn.run_query(
            MATCH_TARGETS
            + "RETURN a.alzkb_id AS alzkb_id, o.uri AS o_uri, o.code AS o_code, "
              "o.label AS o_label, properties(r) AS r_props"
        )
        if len(targets) != 3:
            print(f"[ABORT] expected exactly 3 target edges, found {len(targets)}. "
                  f"No mutation performed.\n{targets}")
            return 3

        # ---- ROLLBACK FILE (written before delete) ----
        lines = [
            "// M3 rollback — recreates the 3 SAME_AS edges removed on 2026-06-17.",
            "// Run only if M3 must be reversed. Idempotent via MERGE.",
            "",
        ]
        for t in targets:
            rp = t["r_props"] or {}
            sets = [
                "r.biolink_predicate=$bp",
                "r.uri=$uri",
                "r.match_method=$mm",
            ]
            created = rp.get("created_at")
            lines.append(
                "MATCH (a:AlzKBConcept {alzkb_id:%r}), (o:OntologyConcept {uri:%r})"
                % (t["alzkb_id"], t["o_uri"])
            )
            lines.append("MERGE (a)-[r:SAME_AS]->(o)")
            set_clause = (
                "SET r.biolink_predicate=%r, r.uri=%r, r.match_method=%r"
                % (
                    rp.get("biolink_predicate", "biolink:same_as"),
                    rp.get("uri", "owl:sameAs"),
                    rp.get("match_method", "manual"),
                )
            )
            if created is not None:
                set_clause += ", r.created_at=datetime(%r)" % str(created)
            lines.append(set_clause + ";")
            lines.append("")
        ROLLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        ROLLBACK_PATH.write_text("\n".join(lines), encoding="utf-8")
        print(f"[ok] rollback written to {ROLLBACK_PATH}")

        # ---- DELETE ----
        conn.execute_write_transaction(MATCH_TARGETS + "DELETE r")

        # ---- AFTER ----
        after = {
            "node_total": _scalar(conn, "MATCH (n) RETURN count(n) AS c"),
            "edge_total": _scalar(conn, "MATCH ()-[r]->() RETURN count(r) AS c"),
            "same_as_total": _scalar(conn, "MATCH ()-[r:SAME_AS]->() RETURN count(r) AS c"),
        }
        leftover = _scalar(conn, MATCH_TARGETS + "RETURN count(r) AS c")

        # Per-category strong-match recomputation (mirrors metrics/alzkb_alignment.py)
        disease = _scalar(conn,
            "MATCH (a:AlzKBConcept)-[:SAME_AS]->(o:OntologyConcept) "
            "WHERE toUpper(o.source_ontology)='SNOMED-CT' AND a.source_type IN ['Disease'] "
            "RETURN count(DISTINCT o) AS c")
        anatomy = _scalar(conn,
            "MATCH (a:AlzKBConcept)-[:SAME_AS]->(o:OntologyConcept) "
            "WHERE toUpper(o.source_ontology)='UBERON' AND a.source_type IN ['Anatomy'] "
            "RETURN count(DISTINCT o) AS c")
        phenotype = _scalar(conn,
            "MATCH (a:AlzKBConcept)-[:SAME_AS]->(o:OntologyConcept) "
            "WHERE toUpper(o.source_ontology)='HPO' "
            "AND a.source_type IN ['Symptom','BiologicalProcess'] "
            "RETURN count(DISTINCT o) AS c")
        gene = _scalar(conn,
            "MATCH (a:AlzKBConcept)-[:SAME_AS]->(g:Gene) "
            "WHERE a.source_type='Gene' RETURN count(DISTINCT g) AS c")

        print("\n=== M3 result ===")
        for k in before:
            print(f"{k:16s} {before[k]} -> {after[k]}")
        print(f"leftover target edges (expect 0): {leftover}")
        print(f"strong matches  Disease={disease} Anatomy={anatomy} "
              f"Phenotype={phenotype} Gene={gene}")
        in_scope_with_match = sum(1 for v in (disease, anatomy, phenotype, gene) if v and v > 0)
        print(f"in-scope categories with >=1 strong match: {in_scope_with_match} of 4")

        ok = (
            after["same_as_total"] == before["same_as_total"] - 3
            and after["edge_total"] == before["edge_total"] - 3
            and after["node_total"] == before["node_total"]
            and leftover == 0
            and phenotype == 0
            and disease == 2 and anatomy == 2 and gene == 5
            and in_scope_with_match == 3
        )
        print(f"\nVERIFY: {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 4
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
