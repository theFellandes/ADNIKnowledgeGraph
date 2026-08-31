"""F10 — Cumulative deltas across enrichment passes.

Reads ``outputs/metrics/per_step_audit.json`` and renders a two-panel chart:
the top panel shows cumulative node and edge counts across the captured
snapshots; the bottom panel shows cumulative OntologyConcept count and
edge-URI coverage on a twin y-axis.

CLI::

    python -m figures.f10_step_deltas
    python -m figures.f10_step_deltas --input outputs/metrics/per_step_audit.json --output paper_outputs/f10_step_deltas.svg
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


# Order of snapshots in the per_step_audit JSON output.
SNAPSHOT_ORDER = (
    "pre_step_30",
    "post_step_30",
    "post_step_33",
    "post_step_34",
    "post_step_35",
    "post_step_36",
)


def _ordered_snapshots(payload: dict) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for key in SNAPSHOT_ORDER:
        if key in payload:
            out.append((key, payload[key]))
    # Append any unexpected keys at the end so we don't silently drop them.
    for k, v in payload.items():
        if k not in SNAPSHOT_ORDER and isinstance(v, dict):
            out.append((k, v))
    return out


# The intermediate rollback-replay checkpoints (pre_step_30 .. post_step_34)
# were measured on the PRE-deduplication graph and still include the
# FamilyMember re-run surplus documented in the JSON's _provenance note
# (116,425 duplicate nodes; 356,354 duplicate edges). post_step_36 is the
# post-dedup canonical snapshot. Subtract the surplus from the intermediate
# rows so the plotted series is comparable end to end and matches the
# dedup-adjusted tables in the manuscripts.
DEDUP_NODE_SURPLUS = 116_425
DEDUP_EDGE_SURPLUS = 356_354
FINAL_SNAPSHOT = "post_step_36"


def _dedup_adjusted(snapshots: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for k, v in snapshots:
        if k != FINAL_SNAPSHOT:
            v = dict(v)
            v["node_total"] = int(v.get("node_total", 0)) - DEDUP_NODE_SURPLUS
            v["edge_total"] = int(v.get("edge_total", 0)) - DEDUP_EDGE_SURPLUS
        out.append((k, v))
    return out


def render(snapshots: list[tuple[str, dict]], *, palette_name: str = "thesis", title: str = "Cumulative deltas across enrichment passes"):
    import matplotlib.pyplot as plt

    from figures._style import apply_style

    palette = apply_style(palette_name)
    labels = [k.replace("_", " ") for k, _ in snapshots]
    nodes = [int(v.get("node_total", 0)) for _, v in snapshots]
    edges = [int(v.get("edge_total", 0)) for _, v in snapshots]
    concepts = [int(v.get("ontology_concepts_total", 0)) for _, v in snapshots]
    edge_cov = [float(v.get("edge_uri_coverage", 0.0)) for _, v in snapshots]

    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
    x = list(range(len(labels)))

    ax_top.plot(x, nodes, marker="o", color=palette["primary"], label="Nodes")
    ax_top.plot(x, edges, marker="s", color=palette["accent"], label="Edges")
    ax_top.set_ylabel("Count")
    ax_top.legend(loc="upper left", frameon=True, framealpha=0.9)
    ax_top.grid(True, axis="y", linestyle=":", alpha=0.4)
    for i, n in enumerate(nodes):
        ax_top.text(x[i], n, f"{n:,}", ha="center", va="bottom", fontsize=7, color=palette["neutral"])

    ax_bot.bar(x, concepts, color=palette["primary"], edgecolor=palette["neutral"], label="OntologyConcept count")
    ax_bot.set_ylabel("OntologyConcept count")
    twin = ax_bot.twinx()
    twin.plot(x, edge_cov, marker="D", color=palette["accent"], label="Edge URI coverage")
    twin.set_ylabel("Edge URI coverage")
    twin.set_ylim(0.99, 1.00)
    ax_bot.set_xticks(x)
    ax_bot.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    ax_bot.set_xlabel("Snapshot")
    ax_bot.grid(True, axis="y", linestyle=":", alpha=0.4)

    # Combined legend on the bottom panel.
    bars, bar_labels = ax_bot.get_legend_handles_labels()
    lines, line_labels = twin.get_legend_handles_labels()
    ax_bot.legend(bars + lines, bar_labels + line_labels, loc="upper left", frameon=True, framealpha=0.9)

    fig.suptitle(title)
    fig.tight_layout()
    return fig, (ax_top, ax_bot)


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
    p = argparse.ArgumentParser(prog="python -m figures.f10_step_deltas")
    p.add_argument("--input", default="outputs/metrics/per_step_audit.json")
    p.add_argument("--output", default="paper_outputs/f10_step_deltas.svg")
    p.add_argument("--palette", choices=("thesis", "paper"), default="thesis")
    p.add_argument("--title", default="Cumulative deltas across enrichment passes")
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
    snapshots = _dedup_adjusted(_ordered_snapshots(payload))
    if not snapshots:
        logger.error("No per-step snapshots in %s", inp)
        return 2

    fig, _ = render(snapshots, palette_name=args.palette, title=args.title)
    out = Path(args.output)
    if not out.is_absolute():
        out = repo_root / out
    for p in save_outputs(fig, out):
        logger.info("Wrote %s", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
