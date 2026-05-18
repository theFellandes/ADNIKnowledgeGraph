"""Metrics runner — single entrypoint for the FAIR / density / alignment pipeline.

::

    python -m metrics --all              # validity → density → fair → alignment → step audit
    python -m metrics --validity         # only the KG validity gate (Sultan's gate)
    python -m metrics --density --fair   # multi-select
    python -m metrics --output-dir metrics/output/2026-05-09/

Exit codes::

    0 — every requested step passed (validity PASS, others succeeded)
    1 — at least one requested step failed (typically validity)
    2 — runtime / connection error

The runner gates downstream metrics on the validity check. If validity fails,
density / FAIR / alignment do not run unless ``--ignore-validity`` is set.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Step result
# ---------------------------------------------------------------------------


@dataclass
class StepOutcome:
    name: str
    status: str              # "ok" | "fail" | "skipped" | "error"
    output_path: Path | None = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def _run_validity(connector, output_dir: Path) -> StepOutcome:
    from metrics.validity import (
        load_rubric,
        run_validity,
        write_json,
        write_markdown,
        render_progress_report,
    )

    rubric_path = PROJECT_ROOT / "metrics" / "validity_rubric.yaml"
    rubric = load_rubric(rubric_path)
    report = run_validity(connector, rubric, graph_uri=getattr(connector, "uri", "(connected)"))

    ts = report.timestamp.replace(":", "").replace("-", "").replace("+0000", "Z").replace("+00:00", "Z")
    json_path = output_dir / "validity_reports" / f"kg_validity_{ts}.json"
    md_path = output_dir / "validity_reports" / f"kg_validity_{ts}.md"
    write_json(report, json_path)
    write_markdown(report, md_path)

    # Sultan-facing progress report (human-readable; updated each run).
    canonical_path = output_dir / "metrics" / "canonical_snapshot.json"
    progress_md = output_dir / "validity_reports" / "kg_validity_progress_report.md"
    try:
        render_progress_report(
            json_path=json_path,
            canonical_snapshot_path=canonical_path if canonical_path.exists() else None,
            output_path=progress_md,
        )
    except Exception as exc:
        logger.warning("Could not render progress report: %s", exc)

    notes = [f"Result: {report.result}"]
    failed = [a.id for a in report.assertions.values() if a.result != "PASS"]
    if failed:
        notes.append(f"Failed assertions: {failed}")
    return StepOutcome(
        name="validity",
        status="ok" if report.result == "PASS" else "fail",
        output_path=md_path,
        notes=notes,
    )


def _run_density(connector, output_dir: Path) -> StepOutcome:
    from metrics.semantic_density import compute_density, write_json

    report = compute_density(connector, graph_uri=getattr(connector, "uri", "(connected)"))
    out = output_dir / "metrics" / "semantic_density.json"
    write_json(report, out)
    return StepOutcome(
        name="density",
        status="ok",
        output_path=out,
        notes=[f"node_density={round(report.node_density,4)}",
               f"edge_density={round(report.edge_density,4)}"],
    )


def _run_fair(connector, output_dir: Path) -> StepOutcome:
    from metrics.fair import load_rubric, score_fair, write_json

    rubric_path = PROJECT_ROOT / "metrics" / "fair_principles.yaml"
    rubric = load_rubric(rubric_path)
    report = score_fair(connector, rubric, graph_uri=getattr(connector, "uri", "(connected)"))
    out = output_dir / "metrics" / "fair_score.json"
    write_json(report, out)
    return StepOutcome(
        name="fair",
        status="ok",
        output_path=out,
        notes=[f"overall_score={round(report.overall_score,4)}",
               f"by_dimension={ {k: round(v,3) for k,v in report.by_dimension.items()} }"],
    )


def _run_alignment(connector, output_dir: Path) -> StepOutcome:
    from metrics.alzkb_alignment import compute_alignment, write_json

    report = compute_alignment(connector, graph_uri=getattr(connector, "uri", "(connected)"))
    out = output_dir / "metrics" / "alzkb_alignment.json"
    write_json(report, out)
    return StepOutcome(
        name="alignment",
        status="ok",
        output_path=out,
        notes=[f"strong: {report.in_scope_strong_count}/{report.in_scope_total_count} in-scope"],
    )


def _run_step_audit(output_dir: Path) -> StepOutcome:
    """Step audit consumes per-step JSONs already written. If the per-step
    files don't exist (the operator hasn't run snapshots yet), we emit an
    empty CSV with just the header so downstream figure scripts don't break."""

    from metrics.step_audit import (
        build_audit_rows,
        load_density_per_step,
        load_fair_per_step,
        write_csv,
    )

    fair_per_step = load_fair_per_step(output_dir / "metrics" / "fair_score_per_step.json")
    density_per_step = load_density_per_step(output_dir / "metrics" / "semantic_density_per_step.json")
    rows = build_audit_rows([], fair_per_step=fair_per_step, density_per_step=density_per_step)
    out = output_dir / "metrics" / "step_audit.csv"
    write_csv(rows, out)
    notes = [f"per-step entries: fair={len(fair_per_step)} density={len(density_per_step)}"]
    if not fair_per_step:
        notes.append("(fair per-step file missing — populate via M2.6)")
    if not density_per_step:
        notes.append("(density per-step file missing — populate via M3.5)")
    return StepOutcome(name="step_audit", status="ok", output_path=out, notes=notes)


def _run_tbox_abox(connector, output_dir: Path) -> StepOutcome:
    from metrics.tbox_abox import compute, write_json

    report = compute(connector, graph_uri=getattr(connector, "uri", "(connected)"))
    out = output_dir / "metrics" / "tbox_abox.json"
    write_json(report, out)
    d = report.to_dict()
    return StepOutcome(
        name="tbox_abox",
        status="ok",
        output_path=out,
        notes=[f"tbox_total={d['tbox_total']}", f"abox_total={d['abox_total']}"],
    )


def _run_mapping_rules(output_dir: Path) -> StepOutcome:
    from metrics.mapping_rules import compute, write_json

    payload = compute(PROJECT_ROOT / "ontology" / "mappings")
    out = output_dir / "metrics" / "mapping_rules.json"
    write_json(payload, out)
    return StepOutcome(
        name="mapping_rules",
        status="ok",
        output_path=out,
        notes=[
            f"files={len(payload['files'])}",
            f"per_file_sum={payload['per_file_sum']}",
            f"index_total={payload.get('index_total')}",
        ],
    )


def _run_duplicity(connector, output_dir: Path) -> StepOutcome:
    from metrics.duplicity_check import compute, write_json

    report = compute(connector, graph_uri=getattr(connector, "uri", "(connected)"))
    out = output_dir / "metrics" / "duplicity_check.json"
    write_json(report, out)
    failed = [p.label for p in report.probes if not p.ok]
    notes = [
        f"probes={len(report.probes)}",
        f"duplicates_total={sum(p.duplicates for p in report.probes)}",
    ]
    if failed:
        notes.append(f"failed_probes={failed}")
    return StepOutcome(
        name="duplicity",
        status="ok" if report.all_ok else "fail",
        output_path=out,
        notes=notes,
    )


def _run_source_contribution(connector, output_dir: Path) -> StepOutcome:
    from metrics.source_ontology_contribution import compute, write_json

    report = compute(connector, graph_uri=getattr(connector, "uri", "(connected)"))
    out = output_dir / "metrics" / "source_ontology_contribution.json"
    write_json(report, out)
    d = report.to_dict()
    top_source = d["sources"][0]["source"] if d.get("sources") else "(none)"
    return StepOutcome(
        name="source_contribution",
        status="ok",
        output_path=out,
        notes=[
            f"total_edges_with_uri={d['total_edges_with_uri']}",
            f"top_source={top_source}",
            f"sources={len(d.get('sources', []))}",
        ],
    )


def _run_graph_topology(connector, output_dir: Path) -> StepOutcome:
    from metrics.graph_topology import compute, write_json

    report = compute(connector, top_k=25, graph_uri=getattr(connector, "uri", "(connected)"))
    out = output_dir / "metrics" / "graph_topology.json"
    write_json(report, out)
    d = report.to_dict()
    top_hub = d["top_25_hubs"][0] if d.get("top_25_hubs") else None
    notes = [
        f"hubs={len(d.get('top_25_hubs', []))}",
        f"orphan_labels={len(d.get('orphans_by_label', []))}",
    ]
    if top_hub:
        notes.append(f"top_hub={top_hub.get('source_ontology', '')}:{top_hub.get('label', '')} indegree={top_hub.get('indegree', 0)}")
    cc_avail = d.get("connected_components", {}).get("available", False)
    notes.append(f"cc_available={cc_avail}")
    return StepOutcome(
        name="graph_topology",
        status="ok",
        output_path=out,
        notes=notes,
    )


def _run_render_prompts(output_dir: Path) -> StepOutcome:
    from metrics.render_audit_prompts import render_prompts

    rendered = render_prompts(
        metrics_dir=output_dir / "metrics",
        audit_dir=output_dir / "audit",
        validity_dir=output_dir / "validity_reports",
    )
    return StepOutcome(
        name="render_prompts",
        status="ok",
        output_path=rendered[0] if rendered else None,
        notes=[f"rendered={len(rendered)}"] + [f"  {p}" for p in rendered],
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


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


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics",
        description="Run the MAKO metrics pipeline (validity, FAIR, density, AlzKB alignment, step audit).",
    )
    p.add_argument("--all", action="store_true", help="Run every step in canonical order")
    p.add_argument("--validity", action="store_true", help="Run KG validity gate")
    p.add_argument("--density", action="store_true", help="Compute semantic density")
    p.add_argument("--fair", action="store_true", help="Score FAIR principles")
    p.add_argument("--alignment", action="store_true", help="Compute AlzKB alignment")
    p.add_argument("--tbox-abox", action="store_true", help="Compute T-Box vs A-Box weight per source ontology")
    p.add_argument("--mapping-rules", action="store_true", help="Count mapping rules per source CSV")
    p.add_argument("--duplicity", action="store_true", help="Audit composite uniqueness on every label")
    p.add_argument("--source-contribution", action="store_true", help="Decompose edge URI coverage by source ontology namespace")
    p.add_argument("--graph-topology", action="store_true", help="Top-25 concept hubs, orphan inventory, connected components")
    p.add_argument("--step-audit", action="store_true", help="Assemble per-step audit CSV")
    p.add_argument("--render-prompts", action="store_true", help="Render outputs/audit/*.md.j2 templates against the current JSONs")
    p.add_argument(
        "--output-dir",
        default="outputs",
        help="Base output directory. Validity → <out>/validity_reports/, others → <out>/metrics/",
    )
    p.add_argument(
        "--ignore-validity",
        action="store_true",
        help="Continue downstream steps even if the validity gate fails (NOT recommended).",
    )
    p.add_argument("--neo4j-uri", default=None)
    p.add_argument("--user", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--quiet", action="store_true")
    return p


def _selected(args: argparse.Namespace) -> list[str]:
    if args.all:
        return [
            "validity", "density", "fair", "alignment",
            "tbox_abox", "mapping_rules", "duplicity",
            "source_contribution", "graph_topology",
            "step_audit", "render_prompts",
        ]
    selected: list[str] = []
    if args.validity:
        selected.append("validity")
    if args.density:
        selected.append("density")
    if args.fair:
        selected.append("fair")
    if args.alignment:
        selected.append("alignment")
    if args.tbox_abox:
        selected.append("tbox_abox")
    if args.mapping_rules:
        selected.append("mapping_rules")
    if args.duplicity:
        selected.append("duplicity")
    if args.source_contribution:
        selected.append("source_contribution")
    if args.graph_topology:
        selected.append("graph_topology")
    if args.step_audit:
        selected.append("step_audit")
    if args.render_prompts:
        selected.append("render_prompts")
    return selected


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    selected = _selected(args)
    if not selected:
        print(
            "Nothing to do — pass --all or one of --validity / --density / --fair / "
            "--alignment / --tbox-abox / --mapping-rules / --duplicity / "
            "--source-contribution / --graph-topology / --step-audit / --render-prompts",
            file=sys.stderr,
        )
        return 2

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    needs_connector = any(
        s in selected
        for s in (
            "validity", "density", "fair", "alignment",
            "tbox_abox", "duplicity", "source_contribution", "graph_topology",
        )
    )

    connector = None
    if needs_connector:
        try:
            uri, user, pw = _resolve_credentials(args)
            from utils.neo4j_connector import Neo4jConnector

            connector = Neo4jConnector(uri=uri, user=user, password=pw)
        except Exception as exc:
            logger.error("Connection setup failed: %s", exc)
            return 2

    outcomes: list[StepOutcome] = []
    overall_status = 0
    try:
        for step in selected:
            try:
                if step == "validity":
                    outcome = _run_validity(connector, output_dir)
                elif step == "density":
                    outcome = _run_density(connector, output_dir)
                elif step == "fair":
                    outcome = _run_fair(connector, output_dir)
                elif step == "alignment":
                    outcome = _run_alignment(connector, output_dir)
                elif step == "tbox_abox":
                    outcome = _run_tbox_abox(connector, output_dir)
                elif step == "mapping_rules":
                    outcome = _run_mapping_rules(output_dir)
                elif step == "duplicity":
                    outcome = _run_duplicity(connector, output_dir)
                elif step == "source_contribution":
                    outcome = _run_source_contribution(connector, output_dir)
                elif step == "graph_topology":
                    outcome = _run_graph_topology(connector, output_dir)
                elif step == "step_audit":
                    outcome = _run_step_audit(output_dir)
                elif step == "render_prompts":
                    outcome = _run_render_prompts(output_dir)
                else:  # pragma: no cover
                    outcome = StepOutcome(name=step, status="skipped",
                                          notes=[f"unknown step: {step}"])
            except Exception as exc:
                logger.exception("Step %s raised", step)
                outcome = StepOutcome(name=step, status="error", notes=[f"{type(exc).__name__}: {exc}"])

            outcomes.append(outcome)
            logger.info(
                "[%s] %s — %s",
                outcome.status.upper(),
                outcome.name,
                "; ".join(outcome.notes) if outcome.notes else "",
            )

            # Validity gate: if it fails, short-circuit unless --ignore-validity
            if step == "validity" and outcome.status != "ok" and not args.ignore_validity:
                logger.warning(
                    "Validity gate FAILED — stopping pipeline. Pass --ignore-validity to override."
                )
                overall_status = 1
                break

            if outcome.status == "fail" and overall_status == 0:
                overall_status = 1
            if outcome.status == "error":
                overall_status = 1
    finally:
        if connector is not None:
            try:
                connector.close()
            except Exception:
                pass

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "selected": selected,
        "overall_status": overall_status,
        "outcomes": [
            {
                "name": o.name,
                "status": o.status,
                "output_path": str(o.output_path) if o.output_path else None,
                "notes": o.notes,
            }
            for o in outcomes
        ],
    }
    summary_path = output_dir / "metrics" / "runner_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))
    return overall_status


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
