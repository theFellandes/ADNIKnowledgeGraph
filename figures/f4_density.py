"""F4 — Semantic density and FAIR progression across the per-step audit.

Reads ``outputs/metrics/per_step_audit.json`` — the rollback-and-replay audit
that captures the graph at five snapshots (pre-30, post-30, post-33, post-34,
post-36) — and plots three series as the enrichment window progresses:
node-URI coverage, edge-URI coverage, and the FAIR aggregate. The node-URI
series shows the Step-36 jump (ADSXLIST ClinicalFinding A-Box); edge-URI stays
saturated; the FAIR aggregate stays inside its rubric band.

For backward compatibility the loader also accepts the older
``semantic_density_per_step.json`` shape (node/edge only, no FAIR line).

**Banned overlap (per IMPLEMENTATION_PLAN.md §7.1).** Must visibly differ
from ``outputs/eda_figures/10_ontology_coverage.svg`` (step 29 is a static
post-state heatmap; F4 is a per-step time series with multiple lines).

CLI::

    python -m figures.f4_density --input outputs/metrics/per_step_audit.json \\
                                 --output paper_outputs/f4_density.svg
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


# per_step_audit.json snapshot keys, in chronological order.
_AUDIT_ORDER = ["pre_step_30", "post_step_30", "post_step_33", "post_step_34", "post_step_36"]
_AUDIT_LABELS = {
    "pre_step_30": "pre-30",
    "post_step_30": "post-30",
    "post_step_33": "post-33",
    "post_step_34": "post-34",
    "post_step_36": "post-36",
}
# Older semantic_density_per_step.json key order.
_DENSITY_ORDER = ["pre", "17", "18", "19", "20", "30", "33", "34", "36"]


def _load_snapshots(path: Path) -> list[dict[str, float | str | None]]:
    """Return an ordered list of ``{label, node, edge, fair}`` rows.

    Accepts both ``per_step_audit.json`` (with FAIR) and the older
    ``semantic_density_per_step.json`` (node/edge only).
    """

    if not path.exists():
        raise FileNotFoundError(f"Per-step JSON not found: {path}")
    payload = json.load(open(path, "r", encoding="utf-8"))

    rows: list[dict[str, float | str | None]] = []

    # per_step_audit.json: flat dict keyed by snapshot label.
    if any(k in payload for k in _AUDIT_ORDER):
        for k in _AUDIT_ORDER:
            v = payload.get(k)
            if not isinstance(v, dict):
                continue
            node = v.get("node_ontology_coverage", v.get("node_density"))
            edge = v.get("edge_uri_coverage", v.get("edge_density"))
            fair = v.get("fair_overall_score")
            if node is None or edge is None:
                continue
            rows.append({"label": _AUDIT_LABELS.get(k, k),
                         "node": float(node), "edge": float(edge),
                         "fair": float(fair) if fair is not None else None})
        return rows

    # Older semantic_density_per_step.json shape.
    per = payload.get("per_step", payload)
    keys = [k for k in _DENSITY_ORDER if k in per] + sorted(set(per) - set(_DENSITY_ORDER))
    for k in keys:
        v = per.get(k)
        if not isinstance(v, dict):
            continue
        agg = v.get("aggregate") if isinstance(v.get("aggregate"), dict) else v
        node, edge = agg.get("node_density"), agg.get("edge_density")
        fair = agg.get("fair_overall_score")
        if node is None or edge is None:
            continue
        rows.append({"label": "pre" if k == "pre" else f"post-{k}",
                     "node": float(node), "edge": float(edge),
                     "fair": float(fair) if fair is not None else None})
    return rows


def render_progression(
    rows: list[dict],
    *,
    palette_name: str = "thesis",
    title: str = "Per-step semantic density and FAIR progression",
):
    import matplotlib.pyplot as plt

    from figures._style import apply_style

    palette = apply_style(palette_name)
    if not rows:
        raise ValueError("No per-step data — cannot render F4.")

    labels = [r["label"] for r in rows]
    node_y = [r["node"] for r in rows]
    edge_y = [r["edge"] for r in rows]
    fair_y = [r["fair"] for r in rows]
    has_fair = all(f is not None for f in fair_y)

    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    ax.plot(labels, node_y, "-o", color=palette["primary"], label="Node URI coverage", linewidth=2.4)
    ax.plot(labels, edge_y, "-s", color=palette["accent"], label="Edge URI coverage", linewidth=2.4)
    if has_fair:
        ax.plot(labels, fair_y, "-^", color=palette["secondary"], label="FAIR aggregate", linewidth=2.4)

    # Annotate the node line at every point (it carries the Step-36 jump);
    # annotate edge and FAIR at the endpoints only to avoid clutter.
    for i, y in enumerate(node_y):
        ax.annotate(f"{y:.2f}", (i, y), textcoords="offset points", xytext=(0, 9),
                    ha="center", fontsize=8, color=palette["primary"])
    for i in (0, len(rows) - 1):
        ax.annotate(f"{edge_y[i]:.2f}", (i, edge_y[i]), textcoords="offset points",
                    xytext=(0, 9), ha="center", fontsize=8, color=palette["accent"])
        if has_fair:
            ax.annotate(f"{fair_y[i]:.2f}", (i, fair_y[i]), textcoords="offset points",
                        xytext=(0, -15), ha="center", fontsize=8, color=palette["secondary"])

    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Coverage / score (fraction)")
    ax.set_xlabel("Audit snapshot")
    ax.set_title(title)
    ax.legend(loc="center left", frameon=True, framealpha=0.9)

    return fig, ax


def save_outputs(fig, base_path: Path) -> list[Path]:
    base_path = Path(base_path)
    base_path.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for ext in (".svg", ".pdf"):
        out = base_path.with_suffix(ext)
        fig.savefig(out)
        written.append(out)
    return written


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m figures.f4_density",
        description="Render the F4 semantic-density and FAIR progression.",
    )
    p.add_argument("--input", default="outputs/metrics/per_step_audit.json")
    p.add_argument("--output", default="paper_outputs/f4_density.svg")
    p.add_argument("--palette", choices=("thesis", "paper"), default="thesis")
    p.add_argument("--title", default="Per-step semantic density and FAIR progression")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )
    try:
        rows = _load_snapshots(Path(args.input))
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 2

    fig, _ = render_progression(rows, palette_name=args.palette, title=args.title)
    for p in save_outputs(fig, Path(args.output)):
        logger.info("Wrote %s", p)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
