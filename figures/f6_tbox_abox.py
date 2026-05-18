"""F6 — T-Box vs A-Box weight per source ontology.

Reads ``outputs/metrics/tbox_abox.json`` (produced by ``metrics.tbox_abox``)
and renders a stacked horizontal bar chart, one bar per source ontology, with
T-Box concept count and A-Box instance count on a shared axis.

CLI::

    python -m figures.f6_tbox_abox
    python -m figures.f6_tbox_abox --input outputs/metrics/tbox_abox.json --output paper_outputs/f6_tbox_abox.svg
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def render(rows: list[dict], *, palette_name: str = "thesis", title: str = "T-Box vs A-Box weight per source ontology"):
    import matplotlib.pyplot as plt
    import numpy as np

    from figures._style import apply_style

    palette = apply_style(palette_name)
    rows = sorted(rows, key=lambda r: r["tbox_concepts"] + r["abox_instances"], reverse=True)
    sources = [r["source_ontology"] for r in rows]
    tbox = np.array([r["tbox_concepts"] for r in rows])
    abox = np.array([r["abox_instances"] for r in rows])

    fig, ax = plt.subplots(figsize=(9, 5))
    y = np.arange(len(sources))
    ax.barh(y, tbox, color=palette["primary"], edgecolor=palette["neutral"], label="T-Box (concept nodes)")
    ax.barh(y, abox, left=tbox, color=palette["muted"], edgecolor=palette["neutral"], label="A-Box (mapped instance nodes)")

    for i, (t, a) in enumerate(zip(tbox, abox)):
        if t > 0:
            ax.text(t / 2, i, f"{t}", ha="center", va="center", fontsize=8, color=palette["neutral"])
        if a > 0:
            ax.text(t + a / 2, i, f"{a:,}", ha="center", va="center", fontsize=8, color=palette["neutral"])

    ax.set_yticks(y)
    ax.set_yticklabels(sources)
    ax.invert_yaxis()
    ax.set_xlabel("Node count (T-Box concepts + A-Box instances)")
    ax.set_title(title)
    ax.set_xscale("symlog")
    ax.legend(loc="lower right", frameon=True, framealpha=0.9)
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
    p = argparse.ArgumentParser(prog="python -m figures.f6_tbox_abox")
    p.add_argument("--input", default="outputs/metrics/tbox_abox.json")
    p.add_argument("--output", default="paper_outputs/f6_tbox_abox.svg")
    p.add_argument("--palette", choices=("thesis", "paper"), default="thesis")
    p.add_argument("--title", default="T-Box vs A-Box weight per source ontology")
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
        logger.error("Input not found: %s — run `python -m metrics.tbox_abox` first.", inp)
        return 2

    with open(inp, "r", encoding="utf-8") as f:
        payload = json.load(f)
    rows = payload.get("rows", [])
    if not rows:
        logger.error("No rows in %s", inp)
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
