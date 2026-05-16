"""Mermaid → SVG / PNG renderer.

Two backends, tried in this order:

1. **mmdc** (Mermaid CLI from npm) — offline, deterministic. Used if
   ``mmdc`` is on PATH.
2. **mermaid.ink** — public HTTPS renderer. No npm needed; just stdlib
   ``urllib`` + base64. Used as fallback. Requires network access.

Override the order via the ``backend`` argument or the
``MAKO_MERMAID_BACKEND`` environment variable (``mmdc`` | ``mermaid_ink`` | ``auto``).

Public API::

    from figures._mermaid import render_mmd_to_svg

    render_mmd_to_svg(mmd_path, svg_path)        # auto
    render_mmd_to_svg(mmd_path, svg_path, backend="mermaid_ink")
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


Backend = Literal["mmdc", "mermaid_ink", "auto"]


# ---------------------------------------------------------------------------
# Backend 1: mmdc (offline)
# ---------------------------------------------------------------------------


def _have_mmdc() -> str | None:
    return shutil.which("mmdc") or shutil.which("mmdc.cmd")


def _render_with_mmdc(mmd_path: Path, out_path: Path) -> bool:
    binary = _have_mmdc()
    if not binary:
        return False
    cmd = [binary, "-i", str(mmd_path), "-o", str(out_path)]
    logger.info("Rendering via mmdc: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.warning("mmdc failed (rc=%d): %s", proc.returncode, proc.stderr.strip())
        return False
    return out_path.exists() and out_path.stat().st_size > 0


# ---------------------------------------------------------------------------
# Backend 2: mermaid.ink (online, no npm)
# ---------------------------------------------------------------------------


def _mermaid_ink_url(mmd_text: str, fmt: str) -> str:
    """Construct a mermaid.ink URL for the given source.

    mermaid.ink accepts URL-safe base64 of the mermaid source on the
    /svg/ or /img/ paths.
    """
    encoded = base64.urlsafe_b64encode(mmd_text.encode("utf-8")).decode("ascii").rstrip("=")
    if fmt == "svg":
        return f"https://mermaid.ink/svg/{encoded}"
    if fmt in ("png", "img"):
        return f"https://mermaid.ink/img/{encoded}"
    raise ValueError(f"Unsupported mermaid.ink format: {fmt}")


def _render_with_mermaid_ink(mmd_path: Path, out_path: Path, *, timeout: int = 30) -> bool:
    fmt = out_path.suffix.lstrip(".").lower()
    if fmt not in ("svg", "png"):
        logger.warning("mermaid.ink supports svg/png; got %s", out_path.suffix)
        return False

    mmd_text = mmd_path.read_text(encoding="utf-8")
    url = _mermaid_ink_url(mmd_text, "svg" if fmt == "svg" else "img")

    req = Request(url, headers={"User-Agent": "MAKO-figures/0.1"})
    logger.info("Rendering via mermaid.ink: %s", url[:80] + ("..." if len(url) > 80 else ""))
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        logger.warning("mermaid.ink failed: %s", exc)
        return False

    if not data:
        logger.warning("mermaid.ink returned empty body")
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    return True


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------


def render_mmd_to_svg(
    mmd_path: Path | str,
    out_path: Path | str,
    *,
    backend: Backend | None = None,
) -> bool:
    """Render a .mmd file to SVG (or PNG, based on out_path extension).

    Returns True on success, False on failure (logs the reason).
    """

    mmd_path = Path(mmd_path)
    out_path = Path(out_path)
    if not mmd_path.exists():
        logger.error("Source not found: %s", mmd_path)
        return False

    backend = (
        backend
        or os.environ.get("MAKO_MERMAID_BACKEND")
        or "auto"
    ).lower()

    order: list[str]
    if backend == "mmdc":
        order = ["mmdc"]
    elif backend == "mermaid_ink":
        order = ["mermaid_ink"]
    else:  # auto
        order = ["mmdc", "mermaid_ink"]

    for name in order:
        ok = (
            _render_with_mmdc(mmd_path, out_path)
            if name == "mmdc"
            else _render_with_mermaid_ink(mmd_path, out_path)
        )
        if ok:
            logger.info("Wrote %s (backend=%s)", out_path, name)
            return True

    logger.warning(
        "Could not render %s — neither mmdc nor mermaid.ink worked. "
        "Install `npm i -g @mermaid-js/mermaid-cli` for offline rendering, "
        "or check network access for the mermaid.ink fallback.",
        mmd_path,
    )
    return False


# ---------------------------------------------------------------------------
# CLI for ad-hoc use: python -m figures._mermaid input.mmd output.svg
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m figures._mermaid")
    parser.add_argument("source", help="Path to .mmd source")
    parser.add_argument("output", help="Output path (.svg or .png)")
    parser.add_argument("--backend", choices=("mmdc", "mermaid_ink", "auto"), default="auto")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ok = render_mmd_to_svg(args.source, args.output, backend=args.backend)
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
