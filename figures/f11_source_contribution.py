"""F11 — Source-ontology contribution to edge URI coverage.

Reads ``outputs/metrics/source_ontology_contribution.json`` and renders a
horizontal bar chart, one bar per URI-namespace source, sorted descending.
Each bar shows the edge count and its share of the aggregate edge URI
coverage over the post-dedup canonical relationship total. Same layout family as f6 / f7 / f8 / f9 so the chapter reads
visually consistent.

CLI::

    python -m figures.f11_source_contribution
    python -m figures.f11_source_contribution --input outputs/metrics/source_ontology_contribution.json --output paper_outputs/f11_source_contribution.svg
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Post-dedup canonical relationship total (outputs/metrics/canonical_snapshot.json).
TOTAL_EDGES = 1_558_383


def render(rows: list[dict], *, palette_name: str = "thesis", title: str = "Source-ontology contribution to edge URI coverage"):
    import matplotlib.pyplot as plt
    import numpy as np

    from figures._style import apply_style

    palette = apply_style(palette_name)

    rows = sorted(rows, key=lambda r: r.get("edges_with_uri", 0), reverse=True)
    names = [r["source"] for r in rows]
    counts = np.array([r["edges_with_uri"] for r in rows])
    shares = np.array([r.get("share", 0.0) for r in rows])
    total = int(counts.sum())

    fig, ax = plt.subplots(figsize=(10, max(3.8, 0.55 * len(names) + 1.0)))
    y = np.arange(len(names))
    bars = ax.barh(y, counts, color=palette["primary"], edgecolor=palette["neutral"])

    max_c = counts.max() if len(counts) else 1
    for i, (c, s) in enumerate(zip(counts, shares)):
        ax.text(
            c + max_c * 0.01,
            i,
            f"{c:,} ({s*100:.2f} %)",
            va="center",
            fontsize=9,
            color=palette["neutral"],
        )

    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.set_xlabel(f"Edges carrying a predicate URI (total = {total:,} of {TOTAL_EDGES:,} = {100.0 * total / TOTAL_EDGES:.2f} %)")
    ax.set_title(title)
    ax.set_xlim(0, max_c * 1.35)
    ax.set_xscale("symlog")

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
    p = argparse.ArgumentParser(prog="python -m figures.f11_source_contribution")
    p.add_argument("--input", default="outputs/metrics/source_ontology_contribution.json")
    p.add_argument("--output", default="paper_outputs/f11_source_contribution.svg")
    p.add_argument("--palette", choices=("thesis", "paper"), default="thesis")
    p.add_argument("--title", default="Source-ontology contribution to edge URI coverage")
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
        logger.error("Input not found: %s — run `python -m metrics.source_ontology_contribution` first.", inp)
        return 2

    with open(inp, "r", encoding="utf-8") as f:
        payload = json.load(f)
    rows = payload.get("sources", [])
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
