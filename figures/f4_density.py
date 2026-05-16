"""F4 — Semantic density progression.

Reads ``metrics/output/semantic_density_per_step.json`` (produced by
``metrics.semantic_density`` aggregated across snapshots) and produces a
two-line chart: node-URI coverage and edge-URI coverage as steps progress
from pre → post-17 → post-18 → post-19 → post-20.

**Banned overlap (per IMPLEMENTATION_PLAN.md §7.1).** Must visibly differ
from ``outputs/eda_figures/10_ontology_coverage.svg`` (step 29 is a static
post-state heatmap; F4 is a per-step time series with two lines).

JSON shape::

    {
        "per_step": {
            "pre":  {"node_density": 0.10, "edge_density": 0.12},
            "17":   {"node_density": 0.18, "edge_density": 0.21},
            "18":   {"node_density": 0.42, "edge_density": 0.48},
            "19":   {"node_density": 0.55, "edge_density": 0.62},
            "20":   {"node_density": 0.85, "edge_density": 0.95}
        }
    }

CLI::

    python -m figures.f4_density --input metrics/output/semantic_density_per_step.json \\
                                 --output paper_outputs/f4_density.svg
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_CANONICAL_ORDER = ["pre", "17", "18", "19", "20"]


def _load_per_step(path: Path) -> dict[str, dict[str, float]]:
    if not path.exists():
        raise FileNotFoundError(f"Per-step density JSON not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    per_step = payload.get("per_step", {}) or payload
    out: dict[str, dict[str, float]] = {}
    for k, v in per_step.items():
        if not isinstance(v, dict):
            continue
        agg = v.get("aggregate") if isinstance(v.get("aggregate"), dict) else v
        nd = agg.get("node_density")
        ed = agg.get("edge_density")
        if nd is not None and ed is not None:
            out[str(k)] = {"node_density": float(nd), "edge_density": float(ed)}
    return out


def render_progression(
    per_step: dict[str, dict[str, float]],
    *,
    palette_name: str = "thesis",
    title: str = "Semantic density progression — Steps 17–20",
):
    import matplotlib.pyplot as plt

    from figures._style import apply_style

    palette = apply_style(palette_name)

    # Order: canonical labels first, then any extra in alphabetical order.
    ordered = [k for k in _CANONICAL_ORDER if k in per_step]
    extra = sorted(set(per_step) - set(ordered))
    ordered.extend(extra)

    if not ordered:
        raise ValueError("No per-step data — cannot render F4.")

    x_labels = ["pre" if k == "pre" else f"post-{k}" for k in ordered]
    node_y = [per_step[k]["node_density"] for k in ordered]
    edge_y = [per_step[k]["edge_density"] for k in ordered]

    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    ax.plot(x_labels, node_y, "-o", color=palette["primary"], label="Node URI coverage", linewidth=2.4)
    ax.plot(x_labels, edge_y, "-s", color=palette["accent"], label="Edge URI coverage", linewidth=2.4)
    for i, y in enumerate(node_y):
        ax.annotate(f"{y:.2f}", (i, y), textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=8, color=palette["primary"])
    for i, y in enumerate(edge_y):
        ax.annotate(f"{y:.2f}", (i, y), textcoords="offset points", xytext=(0, -15),
                    ha="center", fontsize=8, color=palette["accent"])

    ax.set_ylim(0, 1.1)
    ax.set_ylabel("URI coverage (fraction)")
    ax.set_xlabel("Pipeline state")
    ax.set_title(title)
    ax.legend(loc="lower right", frameon=True, framealpha=0.9)

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
        description="Render the F4 semantic density progression.",
    )
    p.add_argument("--input", default="outputs/metrics/semantic_density_per_step.json")
    p.add_argument("--output", default="paper_outputs/f4_density.svg")
    p.add_argument("--palette", choices=("thesis", "paper"), default="thesis")
    p.add_argument("--title", default="Semantic density progression — Steps 17–20")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )
    try:
        per_step = _load_per_step(Path(args.input))
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 2

    fig, _ = render_progression(per_step, palette_name=args.palette, title=args.title)
    for p in save_outputs(fig, Path(args.output)):
        logger.info("Wrote %s", p)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
