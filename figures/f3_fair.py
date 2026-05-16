"""F3 — FAIR scorecard (per-principle bar chart, baseline vs post).

Reads ``metrics/output/fair_score_baseline.json`` and ``fair_score_post.json``
(produced by ``metrics.fair``) and produces
``paper_outputs/f3_fair.{svg,pdf}``.

If the baseline file is absent the chart shows only the post bars and adds a
note in the figure caption — useful for early progress reports where the
baseline snapshot doesn't yet exist.

CLI::

    python -m figures.f3_fair                       # default paths
    python -m figures.f3_fair --baseline ... --post ... --output ...
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _load_principle_scores(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    out: dict[str, float] = {}
    for pid, entry in payload.get("principles", {}).items():
        if isinstance(entry, dict):
            out[pid] = float(entry.get("score", 0.0))
    return out


def render_scorecard(
    baseline_scores: dict[str, float],
    post_scores: dict[str, float],
    *,
    palette_name: str = "thesis",
    title: str = "FAIR Scorecard — Baseline vs Post",
):
    """Build the matplotlib figure. Returns (fig, ax) so callers can save / show."""

    import matplotlib.pyplot as plt
    import numpy as np

    from figures._style import apply_style

    palette = apply_style(palette_name)

    principle_ids = list(post_scores.keys() or baseline_scores.keys())
    if not principle_ids:
        raise ValueError("No principle scores in either baseline or post — nothing to plot.")

    x = np.arange(len(principle_ids))
    width = 0.4

    baseline_vals = [baseline_scores.get(pid, 0.0) for pid in principle_ids]
    post_vals = [post_scores.get(pid, 0.0) for pid in principle_ids]

    fig, ax = plt.subplots(figsize=(11, 4.6))

    if baseline_scores:
        ax.bar(x - width / 2, baseline_vals, width, color=palette["muted"],
               edgecolor=palette["neutral"], label="Baseline (pre Steps 17–20)")
    ax.bar(
        x + (width / 2 if baseline_scores else 0),
        post_vals,
        width,
        color=palette["primary"],
        edgecolor=palette["neutral"],
        label="Post (after Steps 17–20)" if baseline_scores else "Score",
    )

    for i, v in enumerate(post_vals):
        ax.text(x[i] + (width / 2 if baseline_scores else 0), v + 0.02,
                f"{v:.2f}", ha="center", va="bottom", fontsize=8,
                color=palette["neutral"])

    ax.set_xticks(x)
    ax.set_xticklabels(principle_ids, rotation=0, fontsize=9)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Score (0 = no, 0.5 = partial, 1 = yes)")
    ax.set_title(title)
    ax.axhline(0.5, color=palette["accent"], linestyle="--", linewidth=0.8, alpha=0.6)
    ax.legend(loc="lower right", frameon=True, framealpha=0.9)

    return fig, ax


def save_outputs(fig, base_path: Path) -> list[Path]:
    """Write SVG + PDF + PNG next to the same stem.

    PNG (300 dpi) is included so the reportlab-based thesis PDF generator
    can embed a raster version when SVG embedding fails — svglib trips on
    certain matplotlib stroke-dasharray values.
    """
    base_path = Path(base_path)
    base_path.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for ext, kwargs in [(".svg", {}), (".pdf", {}), (".png", {"dpi": 300})]:
        out = base_path.with_suffix(ext)
        fig.savefig(out, **kwargs)
        written.append(out)
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m figures.f3_fair",
        description="Render the F3 FAIR scorecard.",
    )
    p.add_argument("--baseline", default="outputs/metrics/fair_score_baseline.json")
    p.add_argument("--post", default="outputs/metrics/fair_score.json")
    p.add_argument("--output", default="paper_outputs/f3_fair.svg")
    p.add_argument("--palette", choices=("thesis", "paper"), default="thesis")
    p.add_argument("--title", default="FAIR Scorecard — Baseline vs Post")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )

    baseline = _load_principle_scores(Path(args.baseline))
    post = _load_principle_scores(Path(args.post))

    if not post and not baseline:
        logger.error("Neither baseline (%s) nor post (%s) file present — cannot render.",
                     args.baseline, args.post)
        return 2

    fig, _ = render_scorecard(baseline, post, palette_name=args.palette, title=args.title)
    paths = save_outputs(fig, Path(args.output))
    for p in paths:
        logger.info("Wrote %s", p)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
