"""F2 — Schema before / after.

Renders a side-by-side schema comparison: pre-Steps-17–20 (LPG only) vs.
post-Steps-17–20 (with the :OntologyConcept layer + MAPS_TO / IS_A /
CLASSIFIED_AS edges).

**Banned overlap (per IMPLEMENTATION_PLAN.md §7.1).** The output must
visibly differ from ``outputs/eda_figures/15_relationship_schema.svg`` —
F2 is a *delta* (two states side by side), step 29 fig 15 is a single
state. The Mermaid source below uses subgraphs to make that diff visually
obvious.

CLI::

    python -m figures.f2_schema --output paper_outputs/f2_schema.svg
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


MERMAID_TEMPLATE = """%% F2 — Schema before / after Steps 17–20 (c7_plan_v2)
flowchart TB
    subgraph Before["Before Steps 17–20 — LPG"]
        direction LR
        bP[":Patient"]
        bV[":Visit"]
        bD[":Diagnosis<br/>(string codes only)"]
        bC[":CognitiveAssessment"]
        bB[":Biomarker"]
        bR[":BrainRegion"]
        bP --> bV
        bV --> bD
        bV --> bC
        bV --> bB
        bC -. observed at .-> bR
    end

    subgraph After["After Steps 17–20 — KG"]
        direction LR
        aP[":Patient"]
        aV[":Visit"]
        aD[":Diagnosis<br/>+snomed_code +icd10_code"]
        aC[":CognitiveAssessment<br/>+loinc_code"]
        aB[":Biomarker<br/>+loinc_code"]
        aR[":BrainRegion<br/>+uberon_code"]
        aP --> aV
        aV --> aD
        aV --> aC
        aV --> aB
        aC -. observed at .-> aR

        subgraph Layer["Ontology layer (NEW)"]
            direction LR
            oS[":OntologyConcept<br/>SNOMED-CT"]
            oL[":OntologyConcept<br/>LOINC"]
            oU[":OntologyConcept<br/>UBERON"]
            oH[":OntologyConcept<br/>HPO"]
            oI[":OntologyConcept<br/>ICD-10"]
            oS -. IS_A .-> oS
            oL -. IS_A .-> oL
        end

        aD ==>|MAPS_TO| oS
        aC ==>|MAPS_TO| oL
        aB ==>|MAPS_TO| oL
        aR ==>|MAPS_TO| oU
        aD ==>|CLASSIFIED_AS| oI
    end

    classDef ontology fill:#fef3c7,stroke:#b8b90c,color:#3f3f00;
    classDef enriched fill:#dbeafe,stroke:#184a7c,color:#0f1d3a;
    class oS,oL,oU,oH,oI ontology
    class aD,aC,aB,aR enriched
"""


def write_mermaid(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(MERMAID_TEMPLATE, encoding="utf-8")
    return path


def render_svg(mmd_path: Path, svg_path: Path) -> bool:
    """Render via mmdc if available, else fall back to mermaid.ink (HTTPS)."""

    from figures._mermaid import render_mmd_to_svg

    return render_mmd_to_svg(mmd_path, svg_path)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m figures.f2_schema",
        description="Render the F2 before/after schema diagram.",
    )
    p.add_argument("--mmd", default="paper_outputs/f2_schema.mmd")
    p.add_argument("--svg", default="paper_outputs/f2_schema.svg")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )

    mmd = write_mermaid(Path(args.mmd))
    logger.info("Wrote %s", mmd)
    svg_path = Path(args.svg)
    if render_svg(mmd, svg_path):
        logger.info("Wrote %s", svg_path)
    # Also emit a PNG sibling — the reportlab thesis PDF generator prefers PNG.
    png_path = svg_path.with_suffix(".png")
    if render_svg(mmd, png_path):
        logger.info("Wrote %s", png_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
