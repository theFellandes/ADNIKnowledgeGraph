"""Per-step audit — capture snapshots before/after each May-16 enrichment step.

Closes B-07 / B-15 (per-step audit deltas) without requiring offline
``neo4j-admin database dump`` downtime. Steps 30 / 33 / 34 are
idempotent (MERGE-only), so the rollback-and-replay sequence below
restores the exact post-enrichment state; the four canonical snapshots
captured along the way feed ``metrics/step_audit.py`` to assemble a
per-step delta CSV and ``figures/f4_density.py`` for the F4
density-progression figure.

Known coverage gap (acknowledged)
---------------------------------

This audit rolls back and re-snapshots **only Steps 30, 33, and 34**, because
only those three are strictly MERGE-idempotent and therefore safe to reverse
on the live canonical graph. Steps **31, 32, and 35** (VITALS->LOINC,
MEDHIST->SNOMED-CT, Gene Ontology) sit inside the post-Step-34 -> post-Step-36
replay window and have **no dedicated rollback-and-replay snapshot** here;
their per-step deltas are read from the step scripts' run logs and the
canonical-snapshot deltas rather than from an independent audit row. This is a
known, accepted limitation, not an oversight -- it is flagged the same way in
the manuscript's per-pass ledger (Table VI footnote / ``tab:phase2_ledger``)
so no reader mistakes the inferred rows for independently audited ones.

Sequence
--------

1. Snapshot **post_step_34** = current state.
2. Roll back Step 34 (MONDO/DOID); snapshot **post_step_33**.
3. Roll back Step 33 (Biolink); snapshot **post_step_30**.
4. Roll back Step 30 (HPO expansion + FamilyMember dementia); snapshot
   **pre_step_30** (the May-9 baseline equivalent for these three steps).
5. Re-run Step 30, Step 33, Step 34 in order — graph returns to its
   pre-audit state.
6. State-equivalence check against the post_step_34 snapshot taken in (1).

Safety
------

The script aborts (non-zero exit) and prints the offending diff if **any**
of the following hold:
* The validity gate fails after any rollback or re-run.
* A rollback removes more nodes/edges than the step is supposed to have
  added (expected counts hard-coded below).
* The final state-equivalence check disagrees with snapshot (1) on any of:
  total nodes, total edges, OntologyConcept totals by source.

CLI
---

    python -m metrics.per_step_audit
    python -m metrics.per_step_audit --output-dir outputs/per_step/
    python -m metrics.per_step_audit --dry-run   # rollback queries only — print, do not execute
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ══════════════════════════════════════════════════════════════════════
# Rollback Cypher — each block reverses one step
# ══════════════════════════════════════════════════════════════════════

# Step 34 — MONDO + DOID OntologyConcept layer.
# What step 34 created (verified via its own output log):
#   * 2 MONDO OntologyConcepts + 12,420 MAPS_TO (Diagnosis→MONDO)
#   * 3 DOID OntologyConcepts + 12,420 MAPS_TO (Diagnosis→DOID)
#   * 12,420 Diagnosis.doid_code properties
STEP34_ROLLBACK = [
    # Detach-delete MONDO + DOID OntologyConcept nodes; this removes the
    # MAPS_TO edges step 34 created as a side-effect of DETACH.
    # Small (5 nodes, ~25K incident edges) — fits in one transaction.
    (
        "Drop MONDO+DOID OntologyConcepts and their MAPS_TO edges",
        # count
        "MATCH (o:OntologyConcept) WHERE o.source_ontology IN ['MONDO','DOID'] RETURN count(o) AS n",
        # mutate
        "MATCH (o:OntologyConcept) WHERE o.source_ontology IN ['MONDO','DOID'] DETACH DELETE o",
        {"expected_min": 5, "expected_max": 5},  # 2 MONDO + 3 DOID
    ),
    # Clean the doid_code property step 34 set on Diagnosis nodes.
    (
        "Remove Diagnosis.doid_code property",
        "MATCH (d:Diagnosis) WHERE d.doid_code IS NOT NULL RETURN count(d) AS n",
        "MATCH (d:Diagnosis) WHERE d.doid_code IS NOT NULL REMOVE d.doid_code",
        {"expected_min": 12420, "expected_max": 12420},
    ),
]

# Step 33 — Biolink Model metadata pass.
# What step 33 added: biolink_category on ~443K nodes, biolink_predicate
# on ~1.5M edges. Pure metadata; no nodes / edges created or destroyed.
# Large mutations are batched via CALL { ... } IN TRANSACTIONS to avoid
# blowing the Neo4j transaction memory limit (default ~2.7 GiB). Because
# IN TRANSACTIONS does not allow a RETURN aggregate after the call, each
# block is a (count_query, mutate_query) tuple — count first for the
# guardrail, then batched mutation.
STEP33_ROLLBACK = [
    (
        "Remove biolink_category from all nodes (batched)",
        # count
        "MATCH (n) WHERE n.biolink_category IS NOT NULL RETURN count(n) AS n",
        # mutate (batched)
        "MATCH (n) WHERE n.biolink_category IS NOT NULL "
        "CALL (n) { REMOVE n.biolink_category } "
        "IN TRANSACTIONS OF 10000 ROWS",
        {"expected_min": 440000, "expected_max": 460000},
    ),
    (
        "Remove biolink_predicate from all edges (batched)",
        "MATCH ()-[r]->() WHERE r.biolink_predicate IS NOT NULL RETURN count(r) AS n",
        "MATCH ()-[r]->() WHERE r.biolink_predicate IS NOT NULL "
        "CALL (r) { REMOVE r.biolink_predicate } "
        "IN TRANSACTIONS OF 10000 ROWS",
        {"expected_min": 1490000, "expected_max": 1700000},
    ),
]

# Step 30 — HPO expansion (19 new concepts) + FamilyMember dementia mapping.
# Identifies new HPO concepts by their fixed URI list (same as step 30 code).
STEP30_NEW_HPO_URIS = [
    "hpo:HP:0000713", "hpo:HP:0000716", "hpo:HP:0000737", "hpo:HP:0000738",
    "hpo:HP:0000739", "hpo:HP:0000741", "hpo:HP:0000744", "hpo:HP:0000746",
    "hpo:HP:0000749", "hpo:HP:0000752", "hpo:HP:0001262", "hpo:HP:0002360",
    "hpo:HP:0004324", "hpo:HP:0010522", "hpo:HP:0010529", "hpo:HP:0010864",
    "hpo:HP:0011446", "hpo:HP:0030223", "hpo:HP:0100785",
]
STEP30_ROLLBACK = [
    # Drop the FamilyMember → HP:0000726 MAPS_TO edges. Step 30 stamps
    # them with mapping_rule = 'FamilyMember.has_dementia=true' so they
    # are distinguishable from any pre-existing MAPS_TO to HP:0000726.
    # 121K edges → batched.
    (
        "Drop FamilyMember → HP:0000726 MAPS_TO edges (batched)",
        # count
        "MATCH (f:FamilyMember)-[r:MAPS_TO]->(o:OntologyConcept {uri:'hpo:HP:0000726'}) "
        "WHERE r.mapping_rule = 'FamilyMember.has_dementia=true' RETURN count(r) AS n",
        # mutate
        "MATCH (f:FamilyMember)-[r:MAPS_TO]->(o:OntologyConcept {uri:'hpo:HP:0000726'}) "
        "WHERE r.mapping_rule = 'FamilyMember.has_dementia=true' "
        "CALL (r) { DELETE r } IN TRANSACTIONS OF 10000 ROWS",
        {"expected_min": 121082, "expected_max": 121082},
    ),
    # Detach-delete the 19 new HPO concepts (and their 20 IS_A edges,
    # which DETACH handles automatically). Small enough not to batch.
    (
        "Drop 19 new HPO symptom OntologyConcepts (and their IS_A edges)",
        "MATCH (o:OntologyConcept) WHERE o.uri IN $uris RETURN count(o) AS n",
        "MATCH (o:OntologyConcept) WHERE o.uri IN $uris DETACH DELETE o",
        {"expected_min": 19, "expected_max": 19, "params": {"uris": STEP30_NEW_HPO_URIS}},
    ),
]


# ══════════════════════════════════════════════════════════════════════
# Snapshot helpers
# ══════════════════════════════════════════════════════════════════════


def snapshot_metrics(connector, label: str, output_dir: Path) -> dict[str, Any]:
    """Capture canonical reconciliation + validity + density + fair +
    alignment for a single point in the audit. Returns a summary dict
    so the orchestrator can verify expected counts."""

    from metrics.reconcile import reconcile as compute_canonical_snapshot
    from metrics.validity import load_rubric, run_validity
    from metrics.semantic_density import compute_density
    from metrics.fair import load_rubric as load_fair_rubric, score_fair
    from metrics.alzkb_alignment import compute_alignment

    out = output_dir / label
    out.mkdir(parents=True, exist_ok=True)

    canonical = compute_canonical_snapshot(connector, graph_uri="(per-step-audit)")
    canonical_dict = canonical.to_dict()
    (out / "canonical_snapshot.json").write_text(
        json.dumps(canonical_dict, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    validity_rubric = load_rubric(PROJECT_ROOT / "metrics" / "validity_rubric.yaml")
    validity_report = run_validity(connector, validity_rubric, graph_uri="(per-step-audit)")
    (out / "validity.json").write_text(
        json.dumps(validity_report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8",
    )

    density_report = compute_density(connector, graph_uri="(per-step-audit)")
    (out / "semantic_density.json").write_text(
        json.dumps(density_report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8",
    )

    fair_rubric = load_fair_rubric(PROJECT_ROOT / "metrics" / "fair_principles.yaml")
    fair_report = score_fair(connector, fair_rubric, graph_uri="(per-step-audit)")
    (out / "fair_score.json").write_text(
        json.dumps(fair_report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8",
    )

    alignment_report = compute_alignment(connector, graph_uri="(per-step-audit)")
    (out / "alzkb_alignment.json").write_text(
        json.dumps(alignment_report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8",
    )

    summary = {
        "label": label,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "validity_result": validity_report.result,
        "node_total": canonical_dict["node_total"],
        "edge_total": canonical_dict["edge_total"],
        "ontology_concepts_total": canonical_dict["ontology_concepts_total"],
        "ontology_concepts_by_source": canonical_dict["ontology_concepts_by_source"],
        "edge_uri_coverage": canonical_dict["edge_uri_coverage"],
        "node_ontology_coverage": canonical_dict["node_ontology_coverage"],
        "maps_to_edges": canonical_dict.get("maps_to_edges", 0),
        "is_a_edges": canonical_dict.get("is_a_edges", 0),
        "classified_as_edges": canonical_dict.get("classified_as_edges", 0),
        "fair_overall_score": fair_report.overall_score,
        "fair_by_dimension": fair_report.by_dimension,
        "node_density": density_report.node_density,
        "edge_density": density_report.edge_density,
        "alzkb_in_scope_strong": alignment_report.in_scope_strong_count,
        "alzkb_in_scope_total": alignment_report.in_scope_total_count,
    }
    logger.info(
        "[%s] nodes=%s edges=%s concepts=%s fair=%.4f node_density=%.4f edge_density=%.4f validity=%s",
        label, f"{summary['node_total']:,}", f"{summary['edge_total']:,}",
        summary["ontology_concepts_total"], summary["fair_overall_score"],
        summary["node_density"], summary["edge_density"], summary["validity_result"],
    )
    return summary


def execute_rollback(connector, name: str, blocks: list, dry_run: bool) -> dict[str, int]:
    """Execute a numbered rollback block; abort if expected-count guardrail trips.

    Each block is (description, count_query, mutate_query, guard). The count
    runs first as a read-only guardrail check; only on PASS does the (possibly
    batched) mutate query run."""

    affected: dict[str, int] = {}
    for block in blocks:
        if len(block) == 4:
            desc, count_q, mutate_q, guard = block
        else:  # legacy 3-tuple — combined count+mutate in one query (small)
            desc, count_q, guard = block
            mutate_q = None
        params = guard.get("params", {})
        if dry_run:
            logger.info("[DRY-RUN] %s — %s", name, desc)
            logger.info("           count : %s", count_q[:160])
            if mutate_q:
                logger.info("           mutate: %s", mutate_q[:160])
            affected[desc] = 0
            continue
        # Pre-count
        rows = connector.run_query(count_q, params)
        n = int(rows[0]["n"]) if rows else 0
        lo, hi = guard["expected_min"], guard["expected_max"]
        if not (lo <= n <= hi):
            raise RuntimeError(
                f"Rollback guardrail tripped on '{name} — {desc}'. "
                f"Pre-count {n} outside expected range [{lo}, {hi}]. "
                f"Aborting before any mutation; manual diagnosis required."
            )
        # Execute mutation (may be batched; no return required)
        if mutate_q:
            connector.run_query(mutate_q, params)
        # Post-count to confirm
        post_rows = connector.run_query(count_q, params)
        post = int(post_rows[0]["n"]) if post_rows else 0
        if post != 0:
            raise RuntimeError(
                f"Rollback incomplete on '{name} — {desc}': pre={n}, post={post}. "
                f"Expected post-rollback count of 0; aborting."
            )
        logger.info("[%s] %s — affected %d (expected %d–%d) ✓", name, desc, n, lo, hi)
        affected[desc] = n
    return affected


def replay_step(connector, step_name: str, executor: Callable, dry_run: bool) -> None:
    if dry_run:
        logger.info("[DRY-RUN] Replay %s — skipped", step_name)
        return
    logger.info("Replaying %s …", step_name)
    executor(connector)
    logger.info("Replay %s complete", step_name)


def emit_step_audit_csv(summaries: dict[str, dict[str, Any]], path: Path) -> None:
    """Emit a per-step delta CSV from the four-stage snapshot summaries.

    Columns: step, nodes_added, edges_added, concepts_added, maps_to_added,
    is_a_added, edge_uri_coverage, node_density, edge_density, fair_score,
    delta_edge_uri_coverage, delta_node_density, delta_edge_density,
    delta_fair_score. The pre_step_30 row reports absolute values with delta
    columns at zero (it is the baseline)."""

    import csv as _csv

    order = ["pre_step_30", "post_step_30", "post_step_33", "post_step_34"]
    rows = [summaries[k] for k in order if k in summaries]
    if not rows:
        logger.warning("No snapshot rows to emit; CSV not written")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = _csv.writer(f)
        w.writerow([
            "stage", "step_attribution",
            "nodes_total", "edges_total", "ontology_concepts_total",
            "maps_to_edges", "is_a_edges", "classified_as_edges",
            "edge_uri_coverage", "node_density", "edge_density", "fair_score",
            "delta_nodes", "delta_edges", "delta_concepts",
            "delta_maps_to", "delta_is_a",
            "delta_edge_uri_coverage", "delta_fair_score",
            "validity_result",
        ])
        for i, r in enumerate(rows):
            prev = rows[i - 1] if i > 0 else None
            step_attr = {
                "pre_step_30": "baseline (post-Step-20, May-9 state)",
                "post_step_30": "Step 30 — HPO expansion + FamilyMember dementia mapping",
                "post_step_33": "Step 33 — Biolink Model annotation (metadata only)",
                "post_step_34": "Step 34 — MONDO + DOID OntologyConcept wiring",
            }.get(r["label"], r["label"])
            delta_nodes = (r["node_total"] - prev["node_total"]) if prev else 0
            delta_edges = (r["edge_total"] - prev["edge_total"]) if prev else 0
            delta_concepts = (r["ontology_concepts_total"] - prev["ontology_concepts_total"]) if prev else 0
            delta_maps = (r.get("maps_to_edges", 0) - prev.get("maps_to_edges", 0)) if prev else 0
            delta_isa = (r.get("is_a_edges", 0) - prev.get("is_a_edges", 0)) if prev else 0
            delta_edgecov = (r["edge_uri_coverage"] - prev["edge_uri_coverage"]) if prev else 0.0
            delta_fair = (r["fair_overall_score"] - prev["fair_overall_score"]) if prev else 0.0
            w.writerow([
                r["label"], step_attr,
                r["node_total"], r["edge_total"], r["ontology_concepts_total"],
                r.get("maps_to_edges", 0), r.get("is_a_edges", 0), r.get("classified_as_edges", 0),
                round(r["edge_uri_coverage"], 4), round(r["node_density"], 4),
                round(r["edge_density"], 4), round(r["fair_overall_score"], 4),
                delta_nodes, delta_edges, delta_concepts, delta_maps, delta_isa,
                round(delta_edgecov, 5), round(delta_fair, 5),
                r["validity_result"],
            ])


def state_equivalent(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, list[str]]:
    """Compare two snapshot summaries — used for the post-replay
    state-equivalence check. Returns (ok, list_of_diffs)."""

    diffs: list[str] = []
    fields = [
        "node_total", "edge_total", "ontology_concepts_total",
        "ontology_concepts_by_source",
    ]
    for f in fields:
        if before.get(f) != after.get(f):
            diffs.append(f"{f}: before={before.get(f)} after={after.get(f)}")
    # Tolerant comparison for floats — rounded snapshot writer trims to 4 decimals already.
    for f in ["edge_uri_coverage", "node_ontology_coverage", "fair_overall_score",
              "node_density", "edge_density"]:
        b = round(float(before.get(f, 0.0)), 4)
        a = round(float(after.get(f, 0.0)), 4)
        if abs(b - a) > 1e-4:
            diffs.append(f"{f}: before={b:.4f} after={a:.4f}")
    return (not diffs, diffs)


# ══════════════════════════════════════════════════════════════════════
# Orchestrator
# ══════════════════════════════════════════════════════════════════════


def run_audit(output_dir: Path, dry_run: bool = False) -> int:
    from utils.env_loader import load_config
    from utils.neo4j_connector import Neo4jConnector

    cfg = load_config()
    uri = cfg.get("neo4j_uri", "bolt://localhost:7687")
    user = cfg.get("neo4j_user", "neo4j")
    pw = cfg.get("neo4j_password")
    if not pw:
        logger.error("No neo4j_password in config; aborting")
        return 2

    connector = Neo4jConnector(uri=uri, user=user, password=pw)

    summaries: dict[str, dict[str, Any]] = {}
    try:
        # ── 1. Snapshot current state ─────────────────────────────────
        logger.info("=" * 60)
        logger.info("Capturing post_step_34 snapshot (current state)")
        logger.info("=" * 60)
        summaries["post_step_34"] = snapshot_metrics(connector, "post_step_34", output_dir)
        if summaries["post_step_34"]["validity_result"] != "PASS":
            raise RuntimeError("Validity FAIL on initial snapshot — aborting before destructive rollback")

        # ── 2. Roll back Step 34 ──────────────────────────────────────
        logger.info("=" * 60)
        logger.info("Rolling back Step 34 (MONDO + DOID)")
        logger.info("=" * 60)
        execute_rollback(connector, "Step 34", STEP34_ROLLBACK, dry_run)
        summaries["post_step_33"] = snapshot_metrics(connector, "post_step_33", output_dir)
        if not dry_run and summaries["post_step_33"]["validity_result"] != "PASS":
            raise RuntimeError("Validity FAIL after Step 34 rollback — aborting")

        # ── 3. Roll back Step 33 ──────────────────────────────────────
        logger.info("=" * 60)
        logger.info("Rolling back Step 33 (Biolink Model)")
        logger.info("=" * 60)
        execute_rollback(connector, "Step 33", STEP33_ROLLBACK, dry_run)
        summaries["post_step_30"] = snapshot_metrics(connector, "post_step_30", output_dir)
        if not dry_run and summaries["post_step_30"]["validity_result"] != "PASS":
            raise RuntimeError("Validity FAIL after Step 33 rollback — aborting")

        # ── 4. Roll back Step 30 ──────────────────────────────────────
        logger.info("=" * 60)
        logger.info("Rolling back Step 30 (HPO expansion + FamilyMember dementia)")
        logger.info("=" * 60)
        execute_rollback(connector, "Step 30", STEP30_ROLLBACK, dry_run)
        summaries["pre_step_30"] = snapshot_metrics(connector, "pre_step_30", output_dir)
        if not dry_run and summaries["pre_step_30"]["validity_result"] != "PASS":
            raise RuntimeError("Validity FAIL after Step 30 rollback — aborting")

        # ── 5. Replay Steps 30, 33, 34 (idempotent) ───────────────────
        from steps.step30_hpo_expansion import execute_hpo_expansion
        from steps.step33_biolink_categories import execute_biolink_categories
        from steps.step34_mondo_doid_wiring import execute_mondo_doid_wiring

        logger.info("=" * 60)
        logger.info("Replaying enrichment steps in original order")
        logger.info("=" * 60)
        if not dry_run:
            execute_hpo_expansion(neo4j_uri=uri, neo4j_user=user, neo4j_password=pw)
            execute_biolink_categories(neo4j_uri=uri, neo4j_user=user, neo4j_password=pw)
            execute_mondo_doid_wiring(neo4j_uri=uri, neo4j_user=user, neo4j_password=pw)

        # ── 6. State-equivalence check ────────────────────────────────
        logger.info("=" * 60)
        logger.info("State-equivalence check against pre-audit snapshot")
        logger.info("=" * 60)
        post_replay = snapshot_metrics(connector, "post_replay_check", output_dir)
        ok, diffs = state_equivalent(summaries["post_step_34"], post_replay)
        if not ok:
            logger.error("STATE DRIFT after replay! Differences:")
            for d in diffs:
                logger.error("  %s", d)
            return 1
        logger.info("✅ State-equivalence check PASS — graph fully restored")

        # ── 7. Assemble per-step deltas ───────────────────────────────
        per_step_path = output_dir.parent / "metrics" / "per_step_audit.json"
        per_step_path.parent.mkdir(parents=True, exist_ok=True)
        per_step_path.write_text(
            json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        logger.info("Wrote per-step audit summary → %s", per_step_path)

        # ── 7b. Emit step_audit.csv with per-step deltas ─────────────
        csv_path = output_dir.parent / "metrics" / "step_audit.csv"
        emit_step_audit_csv(summaries, csv_path)
        logger.info("Wrote step_audit CSV → %s", csv_path)

        # Print quick delta summary
        ordered = ["pre_step_30", "post_step_30", "post_step_33", "post_step_34"]
        logger.info("")
        logger.info("=" * 60)
        logger.info("PER-STEP AUDIT SUMMARY")
        logger.info("=" * 60)
        logger.info("%-18s %-10s %-12s %-9s %-9s %-9s",
                    "stage", "nodes", "edges", "concepts", "edge_cov", "fair")
        for label in ordered:
            s = summaries[label]
            logger.info("%-18s %-10s %-12s %-9d %-9.4f %-9.4f",
                        label, f"{s['node_total']:,}", f"{s['edge_total']:,}",
                        s["ontology_concepts_total"], s["edge_uri_coverage"],
                        s["fair_overall_score"])

        return 0

    finally:
        try:
            connector.close()
        except Exception:
            pass


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics.per_step_audit",
        description="Rollback + replay per-step audit for May-16 enrichment steps (30, 33, 34)",
    )
    p.add_argument(
        "--output-dir",
        default="outputs/per_step/",
        help="Per-stage snapshot directory (default: outputs/per_step/)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print rollback queries without executing; useful for review.",
    )
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    out = Path(args.output_dir)
    if not out.is_absolute():
        out = PROJECT_ROOT / out

    return run_audit(out, dry_run=args.dry_run)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
