"""F8 — Per-node-label A-Box coverage bar chart.

Reads ``outputs/metrics/semantic_density.json`` (the ``per_label`` array) and
renders one horizontal bar per node label. Zero-coverage labels are grouped at
the bottom with a footnote explaining they are derived or aggregation labels
that have no semantically meaningful ontology mapping.

CLI::

    python -m figures.f8_label_coverage
    python -m figures.f8_label_coverage --input outputs/metrics/semantic_density.json --output paper_outputs/f8_label_coverage.svg
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def render(rows: list[dict], *, palette_name: str = "thesis", title: str = "Per-node-label A-Box coverage"):
    import matplotlib.pyplot as plt

    from figures._style import apply_style

    palette = apply_style(palette_name)
    # Sort by coverage desc, then total desc.
    rows = sorted(rows, key=lambda r: (r.get("coverage", 0.0), r.get("total", 0)), reverse=True)
    names = [r["name"] for r in rows]
    covs = [float(r.get("coverage", 0.0)) for r in rows]
    totals = [int(r.get("total", 0)) for r in rows]
    colors = [palette["primary"] if c > 0 else palette["muted"] for c in covs]

    fig, ax = plt.subplots(figsize=(8.5, max(6, len(names) * 0.22)))
    y = list(range(len(names)))
    ax.barh(y, covs, color=colors, edgecolor=palette["neutral"])
    ax.set_yticks(y)
    ax.set_yticklabels([f"{n} (n={t:,})" for n, t in zip(names, totals)], fontsize=6)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("A-Box coverage (fraction of nodes with ontology code)")
    ax.axvline(0.95, color=palette["accent"], linestyle="--", linewidth=0.8, alpha=0.6)
    ax.set_title(title)
    ax.text(
        0.02,
        -0.04,
        "Zero-coverage labels are derived aggregations or browser-side preview helpers without a meaningful ontology mapping.",
        transform=ax.transAxes,
        fontsize=7,
        color=palette["neutral"],
    )
    fig.tight_layout()
    return fig, ax


def save_outputs(fig, base_path: Path) -> list[Path]:
    base_path = Path(base_path)
    base_path.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for ext, kwargs in [(".svg", {}), (".pdf", {}), (".png", {"dpi": 300})]:
        out = base_path.with_suffix(ext)
        fig.savefig(out, **kwargs)
        written.append(out)
    return written


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m figures.f8_label_coverage")
    p.add_argument("--input", default="outputs/metrics/semantic_density.json")
    p.add_argument("--output", default="paper_outputs/f8_label_coverage.svg")
    p.add_argument("--palette", choices=("thesis", "paper"), default="thesis")
    p.add_argument("--title", default="Per-node-label A-Box coverage")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )
    repo_root = Path(__file__).resolve().parents[1]
    inp = Path(args.input)
    if not inp.is_absolute():
        inp = repo_root / inp
    if not inp.exists():
        logger.error("Input not found: %s", inp)
        return 2

    with open(inp, "r", encoding="utf-8") as f:
        payload = json.load(f)
    rows = payload.get("per_label", [])
    if not rows:
        logger.error("No per_label rows in %s", inp)
        return 2

    fig, _ = render(rows, palette_name=args.palette, title=args.title)
    out = Path(args.output)
    if not out.is_absolute():
        out = repo_root / out
    for p in save_outputs(fig, out):
        logger.info("Wrote %s", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
