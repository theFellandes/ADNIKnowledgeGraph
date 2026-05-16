"""F5 — AlzKB alignment matrix.

Reads ``metrics/output/alzkb_alignment.json`` (post-Steps-17–20) and,
optionally, a baseline alignment for the pre/post comparison. Renders a
4×2 heatmap (categories × pre/post) with cell shading for none / weak /
strong, plus the strong-match count as cell text.

Categories: Disease, Anatomy, Phenotype, Gene (the last marked
``not_implemented`` per the C4 decision).

CLI::

    python -m figures.f5_alignment --post metrics/output/alzkb_alignment.json \\
                                   --baseline metrics/output/alzkb_alignment_baseline.json \\
                                   --output paper_outputs/f5_alignment.svg
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Map a match_rate to a shading band.
def _band(category: dict[str, Any]) -> tuple[str, float]:
    """Return (label, intensity) for the heatmap cell.

    ``not_implemented: true`` cells render with a distinct stripe.
    """

    if category.get("not_implemented"):
        return "N/A", -1.0
    rate = float(category.get("match_rate", 0.0) or 0.0)
    if rate >= 0.5:
        return "strong", rate
    if rate > 0:
        return "weak", rate
    return "none", 0.0


def _load_alignment(path: Path) -> dict[str, dict[str, Any]]:
    """Returns ``{category_name → category_dict}``."""

    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return {c["name"]: c for c in payload.get("categories", []) if "name" in c}


def render_alignment_matrix(
    baseline_categories: dict[str, dict[str, Any]],
    post_categories: dict[str, dict[str, Any]],
    *,
    palette_name: str = "thesis",
    title: str = "AlzKB alignment — Baseline vs Post",
):
    import matplotlib.pyplot as plt
    import numpy as np

    from figures._style import apply_style

    palette = apply_style(palette_name)

    # Canonical category order for the rows
    category_order = ["Disease", "Anatomy", "Phenotype", "Gene"]
    columns = ["Baseline", "Post"]

    # Build the intensity matrix (rows × cols)
    intensities = np.zeros((len(category_order), 2))
    labels = [["", ""] for _ in category_order]

    sources = [baseline_categories, post_categories]
    for col, src in enumerate(sources):
        for row, cat_name in enumerate(category_order):
            cat = src.get(cat_name)
            if cat is None:
                # Missing entry — render as 'none' with a hatched-out marker
                intensities[row, col] = 0.0
                labels[row][col] = "—"
                continue
            band, intensity = _band(cat)
            intensities[row, col] = intensity if intensity >= 0 else 0.0
            if band == "N/A":
                labels[row][col] = "N/A\n(see Future Work)"
            else:
                labels[row][col] = f"{cat.get('strong_matches', 0)} / {cat.get('total', 0)}\n{band}"

    fig, ax = plt.subplots(figsize=(6.5, 4.6))

    # Custom colourmap from neutral → primary
    from matplotlib.colors import LinearSegmentedColormap

    cmap = LinearSegmentedColormap.from_list(
        "f5",
        [palette["background"], palette["muted"], palette["primary"]],
    )

    im = ax.imshow(intensities, cmap=cmap, vmin=0, vmax=1, aspect="auto")

    # Stripe out N/A cells (Gene)
    for row, cat_name in enumerate(category_order):
        for col, src in enumerate(sources):
            cat = src.get(cat_name)
            if cat and cat.get("not_implemented"):
                ax.add_patch(plt.Rectangle(
                    (col - 0.5, row - 0.5), 1, 1,
                    fill=True, facecolor=palette["background"],
                    hatch="///", edgecolor=palette["muted"], linewidth=0.5,
                ))

    ax.set_xticks(range(len(columns)))
    ax.set_xticklabels(columns)
    ax.set_yticks(range(len(category_order)))
    ax.set_yticklabels(category_order)
    ax.set_title(title)

    # Cell text
    for row in range(len(category_order)):
        for col in range(len(columns)):
            text = labels[row][col]
            if not text:
                continue
            colour = palette["background"] if intensities[row, col] > 0.5 else palette["neutral"]
            ax.text(col, row, text, ha="center", va="center",
                    fontsize=9, color=colour, fontweight="bold")

    cbar = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.04)
    cbar.set_label("Match rate")

    return fig, ax


def save_outputs(fig, base_path: Path) -> list[Path]:
    """Write SVG + PDF + PNG (300 dpi) next to the same stem."""
    base_path = Path(base_path)
    base_path.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for ext, kwargs in [(".svg", {}), (".pdf", {}), (".png", {"dpi": 300})]:
        out = base_path.with_suffix(ext)
        fig.savefig(out, **kwargs)
        written.append(out)
    return written


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m figures.f5_alignment",
        description="Render the F5 AlzKB alignment heatmap.",
    )
    p.add_argument("--baseline", default="outputs/metrics/alzkb_alignment_baseline.json")
    p.add_argument("--post", default="outputs/metrics/alzkb_alignment.json")
    p.add_argument("--output", default="paper_outputs/f5_alignment.svg")
    p.add_argument("--palette", choices=("thesis", "paper"), default="thesis")
    p.add_argument("--title", default="AlzKB alignment — Baseline vs Post")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )

    baseline = _load_alignment(Path(args.baseline))
    post = _load_alignment(Path(args.post))
    if not baseline and not post:
        logger.error("Neither baseline (%s) nor post (%s) alignment JSON exists.",
                     args.baseline, args.post)
        return 2

    fig, _ = render_alignment_matrix(baseline, post, palette_name=args.palette, title=args.title)
    for p in save_outputs(fig, Path(args.output)):
        logger.info("Wrote %s", p)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
