"""MAKO Metrics + Figures Orchestrator.

Single entrypoint that runs the full metric pipeline and regenerates every
figure for the C7 paper / thesis.

Phases::

    1. KG Validity (Sultan's gate)        — outputs/validity_reports/
    2. Semantic Density                    — outputs/metrics/semantic_density.json
    3. FAIR Score                          — outputs/metrics/fair_score.json
    4. AlzKB Alignment                     — outputs/metrics/alzkb_alignment.json
    5. Step Audit                          — outputs/metrics/step_audit.csv
    6. Figures F1-F5                       — paper_outputs/

Phase 1 (validity) is a hard gate: if it fails, downstream metrics do NOT run
unless ``--ignore-validity`` is set.

Usage — broad strokes::

    python main.py                    # everything in canonical order
    python main.py --metrics          # metrics only (phases 1-5)
    python main.py --figures          # figures only (phase 6) — assumes JSONs exist
    python main.py --validity-only    # just the validity gate
    python main.py --ignore-validity  # let downstream run even if validity fails
    python main.py --quiet            # suppress info logging
    python main.py --no-figures       # metrics only, even with --all (alias for --metrics)

Usage — individual metric phases (multi-select, can combine)::

    python main.py --validity         # KG validity only (Sultan's gate)
    python main.py --density          # semantic density only
    python main.py --fair             # FAIR scoring only
    python main.py --alignment        # AlzKB alignment only (needs step 24 to have run)
    python main.py --step-audit       # step audit CSV only
    python main.py --validity --fair  # multi-select: just those two

When per-metric flags are passed, figures auto-skip; add nothing or pass
``--figures`` afterward to render them too.

Outputs all anchor on the project root so the same command produces the same
paths regardless of which directory you invoke it from.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger("main")

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Phase wrappers — each returns 0 on success, non-zero on failure
# ---------------------------------------------------------------------------


def _runner_args_common(args: argparse.Namespace) -> list[str]:
    """Build the runner args common to every metric invocation."""

    out: list[str] = []
    if args.quiet:
        out.append("--quiet")
    out.extend(["--output-dir", str(args.metrics_output_dir)])
    if args.neo4j_uri:
        out.extend(["--neo4j-uri", args.neo4j_uri])
    if args.user:
        out.extend(["--user", args.user])
    if args.password:
        out.extend(["--password", args.password])
    return out


def phase_metrics(args: argparse.Namespace, *, selected: list[str] | None = None) -> int:
    """Run the metric phases. ``selected`` is a list of step names to include
    (validity / density / fair / alignment / step_audit). If omitted, runs
    every step in canonical order via the runner's ``--all``."""

    from metrics.runner import main as runner_main

    runner_args: list[str] = []
    if selected is None:
        runner_args.append("--all")
    else:
        for step in selected:
            runner_args.append(f"--{step.replace('_', '-')}")
    if args.ignore_validity:
        runner_args.append("--ignore-validity")
    runner_args.extend(_runner_args_common(args))
    return runner_main(runner_args)


def phase_validity_only(args: argparse.Namespace) -> int:
    """Just phase 1 — useful for Sultan's progress report without the rest."""

    return phase_metrics(args, selected=["validity"])


def phase_thesis_report(args: argparse.Namespace) -> int:
    """Phase 7 — consolidate every metric output + EDA figure into a single
    thesis-ready Markdown report and, when ``--pdf`` is set, an
    independently composed reportlab PDF. Reads only; never writes to Neo4j.

    The PDF path uses ``metrics/thesis_pdf.py`` — a manually composed
    scientific-paper-style document — and falls back to the Markdown→PDF
    converter (``tools/md_to_pdf.py``) only if reportlab is unavailable."""

    from metrics.thesis_report import gather_inputs, write_report

    inputs = gather_inputs(
        project_root=PROJECT_ROOT,
        metrics_output_dir=args.metrics_output_dir,
        paper_output_dir=args.paper_output_dir,
        eda_figures_dir=PROJECT_ROOT / "outputs" / "eda_figures",
        ontology_mappings_dir=PROJECT_ROOT / "ontology" / "mappings",
        include_eda=not args.no_eda,
    )
    output_dir = PROJECT_ROOT / "outputs" / "thesis_report"
    # Always write Markdown; never use the legacy md→pdf path here.
    written = write_report(inputs, output_dir, write_pdf=False)
    for kind, path in written.items():
        logger.info("Thesis report %s: %s", kind, path)

    if args.pdf:
        try:
            from metrics.thesis_pdf import build_pdf

            pdf_path = build_pdf(
                metrics_dir=args.metrics_output_dir,
                paper_dir=args.paper_output_dir,
                eda_dir=PROJECT_ROOT / "outputs" / "eda_figures",
                mappings_dir=PROJECT_ROOT / "ontology" / "mappings",
                output_path=output_dir / "MAKO_evaluation.pdf",
            )
            logger.info("Thesis report pdf: %s", pdf_path)
        except ImportError as exc:
            logger.warning(
                "reportlab/svglib not installed — falling back to "
                "Markdown→PDF converter. Install with `pip install "
                "reportlab svglib` for the scientific-style PDF. (%s)", exc,
            )
            from tools.md_to_pdf import md_to_pdf

            fallback = md_to_pdf(
                output_dir / "thesis_report.md",
                output_dir / "thesis_report.pdf",
            )
            logger.info("Thesis report pdf (fallback): %s", fallback)
    return 0


def _prune_validity_reports(metrics_output_dir: Path, keep_recent: int = 5) -> None:
    """Retention policy (B-06): keep the most recent ``keep_recent`` validity
    reports plus *every* PASSing report; delete everything else.

    Operates on pairs of (.json, .md) sharing the same timestamp prefix.
    Errors are logged but never raise — pruning is best-effort.
    """

    import json as _json

    reports_dir = metrics_output_dir / "validity_reports"
    if not reports_dir.is_dir():
        return

    # Group .json + .md by their shared timestamp prefix.
    bundles: dict[str, dict[str, Path]] = {}
    for path in reports_dir.iterdir():
        if path.suffix not in (".json", ".md"):
            continue
        # filenames look like kg_validity_<TIMESTAMP>.json/.md
        stem = path.stem  # kg_validity_<TIMESTAMP>
        bundles.setdefault(stem, {})[path.suffix] = path

    if len(bundles) <= keep_recent:
        return

    # Determine pass/fail per bundle (read the JSON's `result` field)
    sortable: list[tuple[str, bool, dict[str, Path]]] = []
    for stem, files in bundles.items():
        is_pass = False
        json_path = files.get(".json")
        if json_path:
            try:
                payload = _json.loads(json_path.read_text(encoding="utf-8"))
                is_pass = payload.get("result") == "PASS"
            except Exception:
                pass
        sortable.append((stem, is_pass, files))

    # Sort by timestamp (the stem itself is timestamp-suffixed and sorts naturally)
    sortable.sort(key=lambda t: t[0], reverse=True)

    keep_stems: set[str] = set()
    for i, (stem, is_pass, _files) in enumerate(sortable):
        if i < keep_recent or is_pass:
            keep_stems.add(stem)

    deleted = 0
    for stem, _is_pass, files in sortable:
        if stem in keep_stems:
            continue
        for p in files.values():
            try:
                p.unlink()
                deleted += 1
            except OSError as exc:
                logger.warning("Could not delete %s: %s", p, exc)
    if deleted:
        logger.info("Pruned %d old validity report file(s); kept %d bundle(s).",
                    deleted, len(keep_stems))


def _runner_summary(metrics_dir: Path) -> dict[str, str]:
    """Read the latest runner_summary.json and return ``{step_name: status}``.

    Returns an empty dict if the file is missing — callers fall back to "trust
    the JSONs on disk" behaviour. Used by phase_figures to detect stale
    metric outputs (B-02): if the runner's last run shows a step "skipped"
    or "fail", the corresponding metric JSON on disk is from an earlier
    successful run and rendering it would publish stale numbers.
    """

    import json as _json

    summary_path = metrics_dir / "metrics" / "runner_summary.json"
    if not summary_path.exists():
        return {}
    try:
        payload = _json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        logger.warning("Couldn't parse %s: %s", summary_path, exc)
        return {}
    return {o["name"]: o.get("status", "?") for o in payload.get("outcomes", [])}


def phase_figures(args: argparse.Namespace) -> int:
    """Phase 6 — render every figure script.

    Figures read JSON from outputs/metrics/ and emit SVG + PDF under
    paper_outputs/. F1 and F2 are static (no JSON dependency). F3 / F4 / F5
    skip gracefully when their input JSON is missing OR when the runner
    summary shows the corresponding metric didn't successfully run in the
    most recent invocation (B-02 — stale-JSON guard).
    """

    from figures import f1_dependency, f2_schema, f3_fair, f4_density, f5_alignment

    paper_outputs = args.paper_output_dir
    paper_outputs.mkdir(parents=True, exist_ok=True)

    metrics_dir = args.metrics_output_dir / "metrics"  # runner writes here
    fair_post = metrics_dir / "fair_score.json"
    fair_baseline = metrics_dir / "fair_score_baseline.json"
    density_per_step = metrics_dir / "semantic_density_per_step.json"
    alignment_post = metrics_dir / "alzkb_alignment.json"
    alignment_baseline = metrics_dir / "alzkb_alignment_baseline.json"

    summary = _runner_summary(args.metrics_output_dir)

    def _fresh(metric_name: str) -> bool:
        """True if the runner just ran this metric successfully, OR there's no
        runner summary at all (we fall back to trusting on-disk JSONs).

        ``--ignore-validity`` opts out of staleness gating entirely — the
        operator has explicitly said they're OK with stale data."""

        if args.ignore_validity:
            return True
        if not summary:
            return True
        return summary.get(metric_name) == "ok"

    failures: list[str] = []

    # F1 — Functional dependency diagram (no data dep)
    logger.info("[figures] F1 dependency diagram")
    rc = f1_dependency.main([
        "--mmd", str(paper_outputs / "f1_dependency.mmd"),
        "--svg", str(paper_outputs / "f1_dependency.svg"),
    ] + (["--quiet"] if args.quiet else []))
    if rc != 0:
        failures.append("F1")

    # F2 — Schema before/after (no data dep)
    logger.info("[figures] F2 schema")
    rc = f2_schema.main([
        "--mmd", str(paper_outputs / "f2_schema.mmd"),
        "--svg", str(paper_outputs / "f2_schema.svg"),
    ] + (["--quiet"] if args.quiet else []))
    if rc != 0:
        failures.append("F2")

    # F3 — FAIR scorecard (needs at least the post JSON)
    if not fair_post.exists():
        logger.warning("[figures] F3 skipped — %s missing (run metrics first)", fair_post)
    elif not _fresh("fair"):
        logger.warning(
            "[figures] F3 skipped — %s exists but the most recent runner_summary "
            "shows fair did not run successfully (status=%s). Rendering it would "
            "publish stale numbers. Re-run with `python main.py --fair` after "
            "fixing the upstream issue, or pass --ignore-validity to override.",
            fair_post, summary.get("fair", "missing"),
        )
        failures.append("F3-stale")
    else:
        logger.info("[figures] F3 FAIR scorecard")
        rc = f3_fair.main([
            "--baseline", str(fair_baseline),
            "--post", str(fair_post),
            "--output", str(paper_outputs / "f3_fair.svg"),
        ] + (["--quiet"] if args.quiet else []))
        if rc != 0:
            failures.append("F3")

    # F4 — Semantic density progression (needs per-step JSON from snapshots)
    if density_per_step.exists():
        logger.info("[figures] F4 density progression")
        rc = f4_density.main([
            "--input", str(density_per_step),
            "--output", str(paper_outputs / "f4_density.svg"),
        ] + (["--quiet"] if args.quiet else []))
        if rc != 0:
            failures.append("F4")
    else:
        logger.warning(
            "[figures] F4 skipped — %s missing. F4 needs per-step density JSONs "
            "aggregated from snapshots (M1.* + M3.5). For now you have a single "
            "density.json but not the per-step series.",
            density_per_step,
        )

    # F5 — AlzKB alignment matrix (needs at least the post JSON)
    if not alignment_post.exists():
        logger.warning("[figures] F5 skipped — %s missing (run metrics first)", alignment_post)
    elif not _fresh("alignment"):
        logger.warning(
            "[figures] F5 skipped — %s exists but the most recent runner_summary "
            "shows alignment did not run successfully (status=%s). Re-run "
            "metrics or pass --ignore-validity.",
            alignment_post, summary.get("alignment", "missing"),
        )
        failures.append("F5-stale")
    else:
        logger.info("[figures] F5 alignment matrix")
        rc = f5_alignment.main([
            "--baseline", str(alignment_baseline),
            "--post", str(alignment_post),
            "--output", str(paper_outputs / "f5_alignment.svg"),
        ] + (["--quiet"] if args.quiet else []))
        if rc != 0:
            failures.append("F5")

    if failures:
        logger.error("Figure generation failures: %s", failures)
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


METRIC_STEPS = ("validity", "density", "fair", "alignment", "step_audit")


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python main.py",
        description="MAKO metrics + figures orchestrator (validity → metrics → figures).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ----- Phase selection (the broad strokes) ---------------------------
    phase = p.add_argument_group("phase selection")
    phase.add_argument("--metrics", action="store_true",
                       help="Run only the metric pipeline (phases 1-5). No figures.")
    phase.add_argument("--no-figures", dest="metrics", action="store_true",
                       help="Alias for --metrics.")
    phase.add_argument("--figures", action="store_true",
                       help="Run only figure generation (phase 6). Assumes metric JSONs exist.")
    phase.add_argument("--report", action="store_true",
                       help="Generate thesis report only (phase 7). Reads metric JSONs + step-29 figures.")
    phase.add_argument("--no-report", dest="skip_report", action="store_true",
                       help="Skip the thesis report phase (default: report runs after metrics+figures).")

    # ----- Per-metric flags (multi-select) -------------------------------
    metrics_grp = p.add_argument_group(
        "individual metric phases",
        description=(
            "Pick one or more to run only those metric steps (skipping the rest). "
            "Combine freely: e.g. --validity --alignment runs only those two. "
            "If figures are also enabled (default), they run after the selected metrics."
        ),
    )
    metrics_grp.add_argument("--validity", action="store_true",
                             help="Run KG validity gate only.")
    metrics_grp.add_argument("--validity-only", action="store_true",
                             help="Run validity AND skip figures (legacy alias).")
    metrics_grp.add_argument("--density", action="store_true",
                             help="Compute semantic density only.")
    metrics_grp.add_argument("--fair", action="store_true",
                             help="Score FAIR principles only.")
    metrics_grp.add_argument("--alignment", action="store_true",
                             help="Compute AlzKB alignment only.")
    metrics_grp.add_argument("--step-audit", action="store_true",
                             help="Assemble per-step audit CSV only.")

    # ----- Paths and credentials ----------------------------------------
    p.add_argument("--metrics-output-dir", type=Path,
                   default=PROJECT_ROOT / "outputs",
                   help="Where metric JSONs land (default: <project_root>/outputs)")
    p.add_argument("--paper-output-dir", type=Path,
                   default=PROJECT_ROOT / "paper_outputs",
                   help="Where figure SVG/PDF land (default: <project_root>/paper_outputs)")

    p.add_argument("--ignore-validity", action="store_true",
                   help="Continue downstream even if the validity gate fails (NOT recommended).")
    p.add_argument("--no-eda", action="store_true",
                   help="Skip embedding step-29 EDA figures in the thesis report.")
    p.add_argument("--pdf", action="store_true",
                   help="Also render the thesis report as PDF (requires pandoc).")
    p.add_argument("--neo4j-uri", default=None)
    p.add_argument("--user", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--quiet", action="store_true")
    return p


def _selected_metric_steps(args: argparse.Namespace) -> list[str] | None:
    """Return the list of per-metric flags the user selected, or None if
    they want every metric step (the canonical --all behaviour)."""

    flags = {
        "validity": args.validity,
        "density": args.density,
        "fair": args.fair,
        "alignment": args.alignment,
        "step_audit": args.step_audit,
    }
    chosen = [name for name, on in flags.items() if on]
    return chosen or None


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    started = time.time()

    selected_metrics = _selected_metric_steps(args)
    has_per_metric = selected_metrics is not None

    # Decide which phases to run
    run_metrics = True
    run_figures = True
    run_report = not bool(args.skip_report)
    validity_only = bool(args.validity_only)

    if args.metrics:
        run_figures = False
        run_report = False
    if args.figures:
        run_metrics = False
        run_report = False
    if args.report:
        run_metrics = False
        run_figures = False
        run_report = True
    if validity_only:
        run_metrics = True
        run_figures = False
        run_report = False
        selected_metrics = ["validity"]
        has_per_metric = True
    elif has_per_metric and not args.figures:
        # User picked specific metric phases; default to "no figures or report
        # unless they explicitly add them" since most per-metric runs are
        # quick checks.
        run_figures = False
        run_report = False

    overall = 0

    if not run_metrics and not run_figures and not run_report:
        logger.warning("Nothing to do — no phase selected.")
        return 2

    if run_metrics:
        if selected_metrics is None:
            logger.info("=" * 60)
            logger.info("PHASE: METRICS  (validity → density → fair → alignment → step audit)")
            logger.info("=" * 60)
        else:
            logger.info("=" * 60)
            logger.info("PHASE: METRICS  (selected: %s)", ", ".join(selected_metrics))
            logger.info("=" * 60)
        rc = phase_metrics(args, selected=selected_metrics)
        if rc != 0:
            overall = rc
            if not args.ignore_validity and not run_figures:
                return overall

    if run_figures:
        logger.info("=" * 60)
        logger.info("PHASE: FIGURES  (F1 → F2 → F3 → F4 → F5)")
        logger.info("=" * 60)
        rc = phase_figures(args)
        if rc != 0 and overall == 0:
            overall = rc

    if run_report:
        logger.info("=" * 60)
        logger.info("PHASE: THESIS REPORT  (consolidate → outputs/thesis_report/)")
        logger.info("=" * 60)
        rc = phase_thesis_report(args)
        if rc != 0 and overall == 0:
            overall = rc

    # Retention policy: keep last 5 + every PASS, delete the rest (B-06).
    _prune_validity_reports(args.metrics_output_dir, keep_recent=5)

    elapsed = time.time() - started
    logger.info("=" * 60)
    logger.info("DONE — exit=%d, elapsed=%.1fs", overall, elapsed)
    logger.info("Validity reports: %s", args.metrics_output_dir / "validity_reports")
    logger.info("Metric JSONs:     %s", args.metrics_output_dir / "metrics")
    logger.info("Paper figures:    %s", args.paper_output_dir)
    logger.info("=" * 60)
    return overall


if __name__ == "__main__":
    sys.exit(main())
