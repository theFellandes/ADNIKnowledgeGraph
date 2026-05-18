"""F9 — Mapping-rule density per source CSV.

Reads ``outputs/metrics/mapping_rules.json`` (produced by
``metrics.mapping_rules``) and renders a horizontal bar chart, one bar per
source catalogue, sorted by rule count. The 12 per-source CSVs plus the
deduplicated ``index.csv`` populate the registry that the FAIR R1.2
provenance score reads.

CLI::

    python -m figures.f9_mapping_rules
    python -m figures.f9_mapping_rules --input outputs/metrics/mapping_rules.json --output paper_outputs/f9_mapping_rules.svg
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


_DOMAIN_BY_FILE = {
    "adsxlist_to_hpo.csv": "Symptom → HPO",
    "biolink_categories.csv": "Biolink metadata",
    "biolink_predicates.csv": "Biolink metadata",
    "biomarker_to_loinc.csv": "Biomarker → LOINC",
    "brain_region_to_uberon.csv": "Anatomy → UBERON",
    "cognitive_to_loinc.csv": "Cognitive → LOINC",
    "diagnosis_to_doid.csv": "Disease → DOID",
    "diagnosis_to_mondo.csv": "Disease → MONDO",
    "diagnosis_to_snomed_icd10.csv": "Disease → SNOMED/ICD-10",
    "gene_to_go.csv": "Gene → GO",
    "gene_to_ncbi.csv": "Gene → NCBI",
    "relationship_to_ro_uri.csv": "Relation → RO",
    "index.csv": "Master index (deduplicated)",
}


def render(rows: list[dict], *, palette_name: str = "thesis", title: str = "Mapping-rule density per source catalogue"):
    import matplotlib.pyplot as plt
    import numpy as np

    from figures._style import apply_style

    palette = apply_style(palette_name)

    # Sort all rows by rule count descending; mark index.csv separately
    rows = [r for r in rows if r.get("rule_count", 0) > 0]
    rows = sorted(rows, key=lambda r: r["rule_count"], reverse=True)

    names = [r["source_csv"] for r in rows]
    counts = np.array([r["rule_count"] for r in rows])
    domains = [_DOMAIN_BY_FILE.get(n, "Other") for n in names]

    # Colour: index.csv in accent, others in primary
    colors = [palette["accent"] if n == "index.csv" else palette["primary"] for n in names]

    fig, ax = plt.subplots(figsize=(9.5, max(4.0, 0.45 * len(names) + 1.0)))
    y = np.arange(len(names))
    bars = ax.barh(y, counts, color=colors, edgecolor=palette["neutral"])

    # Annotate each bar with the count
    for i, c in enumerate(counts):
        ax.text(c + max(counts) * 0.01, i, f"{c}", va="center", fontsize=9, color=palette["neutral"])

    ax.set_yticks(y)
    ax.set_yticklabels([f"{n}" for n in names])
    ax.invert_yaxis()
    ax.set_xlabel("Mapping-rule count (data rows, header excluded)")
    ax.set_title(title)
    ax.set_xlim(0, max(counts) * 1.15)

    # Right margin for domain annotation
    secax = ax.secondary_yaxis("right")
    secax.set_yticks(y)
    secax.set_yticklabels(domains, fontsize=8, color=palette["neutral"])
    secax.set_ylabel("Domain", color=palette["neutral"])

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
    p = argparse.ArgumentParser(prog="python -m figures.f9_mapping_rules")
    p.add_argument("--input", default="outputs/metrics/mapping_rules.json")
    p.add_argument("--output", default="paper_outputs/f9_mapping_rules.svg")
    p.add_argument("--palette", choices=("thesis", "paper"), default="thesis")
    p.add_argument("--title", default="Mapping-rule density per source catalogue")
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
        logger.error("Input not found: %s — run `python -m metrics.mapping_rules` first.", inp)
        return 2

    with open(inp, "r", encoding="utf-8") as f:
        payload = json.load(f)
    rows = payload.get("files", [])
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
