"""F1 — Functional dependency diagram (revised).

Generates ``paper_outputs/f1_dependency.mmd`` (Mermaid source) and, if the
``mmdc`` CLI is on PATH, an ``f1_dependency.svg``. The diagram puts C7 at
the centre, Steps A–D as feeders, C6 as future work on the right, and the
removed C4 box rendered faded.

CLI::

    python -m figures.f1_dependency
    python -m figures.f1_dependency --output paper_outputs/f1_dependency.svg
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


MERMAID_SOURCE = """%% F1 — MAKO functional dependency diagram (post-Step-35)
%% C7 (cross-vocabulary AlzKB alignment) sits at the centre.
%% Steps A–D feed into C7. C4 (Gene Ontology) landed at Step 35 and now also
%% feeds C7, taking the AlzKB Gene-category alignment to 5/5. C6 is future
%% work.
flowchart LR
    subgraph Steps["Methodological Steps"]
        A["Step A<br/>Three-axis ontology selection<br/>(was C1)"]
        B["Step B<br/>In-place semantic migration<br/>(was C2)"]
        C["Step C<br/>Column-to-concept mapping<br/>(was C3, renamed)"]
        D["Step D<br/>Relation normalisation<br/>(was C5)"]
    end

    C7[["C7 — Cross-Vocabulary Alignment<br/>(MAKO ↔ AlzKB)"]]
    C6(["C6 — Comparative Benchmark<br/>(future work)"])
    C4(["C4 — Gene Ontology integration<br/>(added at Step 35)"]):::added

    A --> C7
    B --> C7
    C --> C7
    D --> C7
    C4 --> C7
    C7 --> C6

    classDef added fill:#dcfce7,stroke:#16a34a,color:#14532d;
    classDef future fill:#fef3c7,stroke:#b8b90c,color:#3f3f00;
    classDef hub fill:#184a7c,stroke:#0f1d3a,color:#ffffff;
    class C7 hub
    class C6 future
"""


def write_mermaid(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(MERMAID_SOURCE, encoding="utf-8")
    return path


def render_svg(mmd_path: Path, svg_path: Path) -> bool:
    """Render via mmdc if available, else fall back to mermaid.ink (HTTPS)."""

    from figures._mermaid import render_mmd_to_svg

    return render_mmd_to_svg(mmd_path, svg_path)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m figures.f1_dependency",
        description="Render the F1 functional dependency diagram.",
    )
    p.add_argument("--mmd", default="paper_outputs/f1_dependency.mmd")
    p.add_argument("--svg", default="paper_outputs/f1_dependency.svg")
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
    # Also emit a PNG sibling — the reportlab-based thesis PDF generator
    # prefers PNG (svglib chokes on certain mermaid stroke-dasharray values).
    png_path = svg_path.with_suffix(".png")
    if render_svg(mmd, png_path):
        logger.info("Wrote %s", png_path)
    return 0  # not having a backend isn't a hard fail — SVG/PNG are optional


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
