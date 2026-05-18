"""F12 — Top-25 concept hubs by in-degree.

Reads ``outputs/metrics/graph_topology.json`` (produced by
``metrics.graph_topology``) and renders a horizontal bar chart of the top
OntologyConcept nodes ranked by MAPS_TO / CLASSIFIED_AS / PARTICIPATES_IN
in-degree. Bars are colour-coded by source ontology. The concepts at the
top of the chart are the load-bearing entities that carry most of the
patient-instance attachment weight (typically HP:0000726 Dementia,
SNOMED:26929004 Alzheimer's disease, and similar AD-central codes).

CLI::

    python -m figures.f12_concept_hubs
    python -m figures.f12_concept_hubs --input outputs/metrics/graph_topology.json --output paper_outputs/f12_concept_hubs.svg
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


_SOURCE_COLOUR = {
    "SNOMED-CT":   None,  # primary
    "LOINC":       None,  # accent
    "UBERON":      None,  # secondary
    "HPO":         None,  # good
    "ICD-10":      None,  # bad
    "MONDO":       None,  # muted
    "DOID":        None,
    "GO":          None,
}


def _short_uri(uri: str) -> str:
    if not uri:
        return ""
    tail = uri.rstrip("/").rsplit("/", 1)[-1]
    tail = tail.rsplit("#", 1)[-1]
    return tail


def _label_for(row: dict) -> str:
    src = row.get("source_ontology", "")
    short = _short_uri(row.get("uri", ""))
    lbl = (row.get("label") or "").strip()
    if lbl:
        return f"{src}:{short} — {lbl[:48]}"
    return f"{src}:{short}"


def render(rows: list[dict], *, palette_name: str = "thesis", title: str = "Top-25 ontology-concept hubs (by in-degree)"):
    import matplotlib.pyplot as plt
    import numpy as np

    from figures._style import apply_style

    palette = apply_style(palette_name)

    # Assign one of the seven palette colours per source ontology
    colour_pool = [
        palette["primary"],
        palette["accent"],
        palette["secondary"],
        palette["good"],
        palette["bad"],
        palette["muted"],
        palette["neutral"],
    ]
    seen_sources: list[str] = []
    source_colour: dict[str, str] = {}
    for r in rows:
        s = r.get("source_ontology", "")
        if s and s not in seen_sources:
            seen_sources.append(s)
            source_colour[s] = colour_pool[(len(seen_sources) - 1) % len(colour_pool)]

    rows = sorted(rows, key=lambda r: r.get("indegree", 0), reverse=True)
    labels = [_label_for(r) for r in rows]
    indeg = np.array([r.get("indegree", 0) for r in rows])
    colours = [source_colour.get(r.get("source_ontology", ""), palette["neutral"]) for r in rows]

    fig, ax = plt.subplots(figsize=(11, max(5.0, 0.32 * len(rows) + 1.5)))
    y = np.arange(len(rows))
    ax.barh(y, indeg, color=colours, edgecolor=palette["neutral"])

    for i, n in enumerate(indeg):
        ax.text(n + max(indeg) * 0.005, i, f"{n:,}", va="center", fontsize=8, color=palette["neutral"])

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("In-degree (incoming MAPS_TO / CLASSIFIED_AS / PARTICIPATES_IN / ENCODES edges)")
    ax.set_title(title)
    ax.set_xlim(0, max(indeg) * 1.12 if len(indeg) > 0 else 1)

    # Legend keyed by source ontology
    handles = [plt.Rectangle((0, 0), 1, 1, color=source_colour[s], edgecolor=palette["neutral"]) for s in seen_sources]
    if handles:
        ax.legend(handles, seen_sources, loc="lower right", title="Source ontology", frameon=True, framealpha=0.9, fontsize=9)

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
    p = argparse.ArgumentParser(prog="python -m figures.f12_concept_hubs")
    p.add_argument("--input", default="outputs/metrics/graph_topology.json")
    p.add_argument("--output", default="paper_outputs/f12_concept_hubs.svg")
    p.add_argument("--palette", choices=("thesis", "paper"), default="thesis")
    p.add_argument("--title", default="Top-25 ontology-concept hubs (by in-degree)")
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
        logger.error("Input not found: %s — run `python -m metrics.graph_topology` first.", inp)
        return 2

    with open(inp, "r", encoding="utf-8") as f:
        payload = json.load(f)
    rows = payload.get("top_25_hubs", [])
    if not rows:
        logger.error("No top_25_hubs entries in %s", inp)
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
