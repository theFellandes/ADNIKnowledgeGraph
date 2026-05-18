"""F7 — Per-edge-type URI coverage bar chart.

Reads ``outputs/metrics/semantic_density.json`` (the ``per_edge_type`` array)
and renders one horizontal bar per relationship type, sorted by coverage. The
five intentionally-unannotated types (HAS_TIMELINE, HAS_SUMMARY, MATCHES_PATTERN,
HAS_DOMAIN, DEFINES_EVENT_TYPE) are highlighted in a distinct colour and
flagged with a footnote.

CLI::

    python -m figures.f7_edge_uri
    python -m figures.f7_edge_uri --input outputs/metrics/semantic_density.json --output paper_outputs/f7_edge_uri.svg
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


ALLOWLISTED_UNANNOTATED = {
    "HAS_TIMELINE",
    "HAS_SUMMARY",
    "MATCHES_PATTERN",
    "HAS_DOMAIN",
    "DEFINES_EVENT_TYPE",
}


def render(rows: list[dict], *, palette_name: str = "thesis", title: str = "Per-edge-type URI coverage"):
    import matplotlib.pyplot as plt

    from figures._style import apply_style

    palette = apply_style(palette_name)
    # Sort by coverage desc, ties broken by total desc.
    rows = sorted(rows, key=lambda r: (r.get("coverage", 0.0), r.get("total", 0)), reverse=True)
    names = [r["name"] for r in rows]
    covs = [float(r.get("coverage", 0.0)) for r in rows]
    colors = [
        palette["accent"] if n in ALLOWLISTED_UNANNOTATED else palette["primary"]
        for n in names
    ]

    fig, ax = plt.subplots(figsize=(8.5, max(6, len(names) * 0.18)))
    y = list(range(len(names)))
    ax.barh(y, covs, color=colors, edgecolor=palette["neutral"])
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=6)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("URI coverage (fraction of edges with formal URI)")
    ax.axvline(0.95, color=palette["accent"], linestyle="--", linewidth=0.8, alpha=0.6)
    ax.set_title(title)
    # Footnote.
    ax.text(
        0.02,
        -0.06,
        "Highlighted rows are project-internal aggregation edges in the rubric's allowlist (0.0 by design).",
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
    p = argparse.ArgumentParser(prog="python -m figures.f7_edge_uri")
    p.add_argument("--input", default="outputs/metrics/semantic_density.json")
    p.add_argument("--output", default="paper_outputs/f7_edge_uri.svg")
    p.add_argument("--palette", choices=("thesis", "paper"), default="thesis")
    p.add_argument("--title", default="Per-edge-type URI coverage")
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
    rows = payload.get("per_edge_type", [])
    if not rows:
        logger.error("No per_edge_type rows in %s", inp)
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
