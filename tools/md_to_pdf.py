"""Markdown → PDF converter with backend auto-detection.

Tries multiple backends in priority order; the first one that's available
wins. If none are available, writes a styled HTML file instead and returns
that path so the caller still has a deliverable.

Backends (in default order)::

    1. pandoc           — external binary; best output quality, supports LaTeX maths
    2. weasyprint       — pure-Python on Linux/macOS; on Windows needs GTK
    3. xhtml2pdf        — pure Python, cross-platform, no binaries
    4. html_only        — last-ditch fallback: writes an HTML file instead

Pick / restrict via the ``backend`` argument or the ``MD_TO_PDF_BACKEND``
environment variable.

Usage (Python)::

    from tools.md_to_pdf import md_to_pdf
    written_path = md_to_pdf("report.md", "report.pdf")
    if written_path.suffix == ".html":
        print("(PDF backends unavailable — wrote HTML instead)")

Usage (CLI)::

    python -m tools.md_to_pdf input.md output.pdf
    python -m tools.md_to_pdf input.md output.pdf --backend pandoc
    python -m tools.md_to_pdf --list-backends

Image handling:
    All backends resolve relative `<img>` paths against the **input
    Markdown's directory** (not the working directory). SVG embedding works
    in pandoc and weasyprint natively; xhtml2pdf renders SVG via svglib if
    installed, else skips with a warning.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

logger = logging.getLogger(__name__)


Backend = Literal["pandoc", "weasyprint", "xhtml2pdf", "html_only", "auto"]


# ---------------------------------------------------------------------------
# Capability probes
# ---------------------------------------------------------------------------


def _have_pandoc() -> str | None:
    return shutil.which("pandoc")


def _have_weasyprint() -> bool:
    try:
        import weasyprint  # noqa: F401
    except Exception:
        return False
    return True


def _have_xhtml2pdf() -> bool:
    try:
        import xhtml2pdf  # noqa: F401
        import xhtml2pdf.pisa  # noqa: F401
    except Exception:
        return False
    return True


def _have_markdown_lib() -> bool:
    try:
        import markdown  # noqa: F401
    except Exception:
        return False
    return True


@dataclass
class BackendStatus:
    name: str
    available: bool
    detail: str = ""


def list_backends() -> list[BackendStatus]:
    """Inventory of which backends this environment can use."""
    pandoc = _have_pandoc()
    return [
        BackendStatus(
            "pandoc",
            available=bool(pandoc),
            detail=pandoc or "not on PATH; install from https://pandoc.org",
        ),
        BackendStatus(
            "weasyprint",
            available=_have_weasyprint(),
            detail="pip install weasyprint (Linux/macOS easy; Windows needs GTK)",
        ),
        BackendStatus(
            "xhtml2pdf",
            available=_have_xhtml2pdf(),
            detail=(
                "pip install xhtml2pdf  (also `markdown`; optional `svglib` "
                "+ `reportlab` for SVG embed)"
            ),
        ),
        BackendStatus(
            "html_only",
            available=_have_markdown_lib(),
            detail="pip install markdown — fallback that writes styled HTML",
        ),
    ]


# ---------------------------------------------------------------------------
# Pandoc backend
# ---------------------------------------------------------------------------


def _render_with_pandoc(md_path: Path, pdf_path: Path) -> bool:
    binary = _have_pandoc()
    if not binary:
        return False
    cmd = [
        binary,
        str(md_path),
        "-o", str(pdf_path),
        "--standalone",
        "--toc",
        "--metadata", f"title={md_path.stem}",
        "--resource-path", str(md_path.parent),
    ]
    logger.info("pandoc: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.warning("pandoc failed (rc=%d): %s", proc.returncode, proc.stderr.strip()[:300])
        return False
    return pdf_path.exists() and pdf_path.stat().st_size > 0


# ---------------------------------------------------------------------------
# HTML helpers (used by weasyprint, xhtml2pdf, html_only)
# ---------------------------------------------------------------------------


_DEFAULT_CSS = """
@page { size: A4; margin: 2cm 1.8cm; }
body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 11pt; line-height: 1.5; color: #1f2937; }
h1 { color: #184A7C; border-bottom: 2px solid #184A7C; padding-bottom: 4px; }
h2 { color: #184A7C; margin-top: 1.4em; }
h3 { color: #4A4A4A; }
code, pre { font-family: 'DejaVu Sans Mono', Consolas, monospace; background: #f3f4f6;
            padding: 2px 4px; border-radius: 3px; }
pre { padding: 8px 10px; overflow-x: auto; }
table { border-collapse: collapse; margin: 0.6em 0; }
table th, table td { border: 1px solid #d1d5db; padding: 4px 8px; text-align: left; }
table th { background: #f3f4f6; }
blockquote { border-left: 4px solid #B5397D; margin: 0.6em 0; padding: 0.4em 0.8em;
             color: #4A4A4A; background: #fef3c7; }
img { max-width: 100%; }
a { color: #184A7C; }
hr { border: none; border-top: 1px solid #d1d5db; margin: 1.2em 0; }
"""


def _md_to_html(md_path: Path) -> str:
    """Convert Markdown to HTML body (extensions: tables, fenced_code, toc, attr_list)."""
    try:
        import markdown
    except ImportError:
        # Fallback: minimal hand-rolled wrapper so we at least have *some* HTML
        text = md_path.read_text(encoding="utf-8")
        body = (
            "<pre style='white-space: pre-wrap; font-family: monospace;'>"
            + (text
               .replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;"))
            + "</pre>"
        )
        return body

    text = md_path.read_text(encoding="utf-8")
    return markdown.markdown(
        text,
        extensions=[
            "tables",
            "fenced_code",
            "toc",
            "attr_list",
            "sane_lists",
        ],
    )


def _wrap_html(body: str, *, title: str, base_href: str | None = None) -> str:
    base_tag = f'<base href="{base_href}/">\n' if base_href else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
{base_tag}<style>{_DEFAULT_CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""


def _resolve_image_paths(html: str, md_dir: Path) -> str:
    """Rewrite <img src="relative"> to absolute file:/// URIs.

    Both weasyprint and xhtml2pdf can struggle with relative paths when the
    input HTML lives in a different directory than the source Markdown. We
    emit absolute URIs anchored at the Markdown's directory so callers can
    pass an arbitrary output path without breaking image embedding.
    """
    md_dir_uri = md_dir.resolve().as_uri().rstrip("/") + "/"

    def _fix(m: re.Match) -> str:
        src = m.group(2)
        if src.startswith(("http://", "https://", "data:", "file://", "/")):
            return m.group(0)
        if Path(src).is_absolute():
            return m.group(0)
        # Relative path — rewrite to absolute file URI
        return f'{m.group(1)}"{md_dir_uri}{src}"'

    return re.sub(r'(<img[^>]+src=)"([^"]+)"', _fix, html)


# ---------------------------------------------------------------------------
# weasyprint backend
# ---------------------------------------------------------------------------


def _render_with_weasyprint(md_path: Path, pdf_path: Path) -> bool:
    if not _have_weasyprint():
        return False
    try:
        import weasyprint
    except Exception as exc:
        logger.warning("weasyprint import failed: %s", exc)
        return False

    body = _md_to_html(md_path)
    html = _wrap_html(body, title=md_path.stem)
    html = _resolve_image_paths(html, md_path.parent)

    try:
        weasyprint.HTML(string=html, base_url=str(md_path.parent)).write_pdf(str(pdf_path))
    except Exception as exc:
        logger.warning("weasyprint render failed: %s", exc)
        return False
    return pdf_path.exists() and pdf_path.stat().st_size > 0


# ---------------------------------------------------------------------------
# xhtml2pdf backend
# ---------------------------------------------------------------------------


def _render_with_xhtml2pdf(md_path: Path, pdf_path: Path) -> bool:
    if not _have_xhtml2pdf():
        return False
    try:
        from xhtml2pdf import pisa
    except Exception as exc:
        logger.warning("xhtml2pdf import failed: %s", exc)
        return False

    body = _md_to_html(md_path)
    html = _wrap_html(body, title=md_path.stem)
    html = _resolve_image_paths(html, md_path.parent)

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with open(pdf_path, "wb") as out:
        result = pisa.CreatePDF(html, dest=out, encoding="utf-8")
    if result.err:
        logger.warning("xhtml2pdf reported %d error(s)", result.err)
        return pdf_path.exists() and pdf_path.stat().st_size > 0
    return pdf_path.exists() and pdf_path.stat().st_size > 0


# ---------------------------------------------------------------------------
# html-only fallback
# ---------------------------------------------------------------------------


def _render_html_only(md_path: Path, pdf_path: Path) -> Path:
    """Last-resort fallback: write a styled HTML alongside the requested PDF
    path and return the HTML path so the caller can detect the fallback.

    Returns the actual output path (with .html suffix). Never raises.
    """
    body = _md_to_html(md_path)
    html = _wrap_html(body, title=md_path.stem)
    html = _resolve_image_paths(html, md_path.parent)

    html_path = pdf_path.with_suffix(".html")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")
    logger.warning(
        "No PDF backend available — wrote HTML to %s instead. "
        "Install a backend: `choco install pandoc` (Windows), or "
        "`pip install xhtml2pdf` (cross-platform).",
        html_path,
    )
    return html_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_BACKENDS: dict[str, Callable[[Path, Path], bool]] = {
    "pandoc": _render_with_pandoc,
    "weasyprint": _render_with_weasyprint,
    "xhtml2pdf": _render_with_xhtml2pdf,
}


def md_to_pdf(
    md_path: Path | str,
    pdf_path: Path | str,
    *,
    backend: Backend | str | None = None,
) -> Path:
    """Convert Markdown to PDF using the first available backend.

    Returns the actual output path. Normally this equals ``pdf_path``; if
    every PDF backend is unavailable, the function writes an HTML file
    instead and returns that path with a `.html` suffix. The caller can
    inspect ``returned.suffix`` to detect the fallback.

    Raises ``FileNotFoundError`` only if ``md_path`` doesn't exist.
    """

    md_path = Path(md_path)
    pdf_path = Path(pdf_path)
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown source not found: {md_path}")

    requested = (
        backend
        or os.environ.get("MD_TO_PDF_BACKEND")
        or "auto"
    ).lower()

    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    if requested == "html_only":
        return _render_html_only(md_path, pdf_path)

    order: list[str]
    if requested == "auto":
        order = ["pandoc", "weasyprint", "xhtml2pdf"]
    elif requested in _BACKENDS:
        order = [requested]
    else:
        raise ValueError(
            f"Unknown backend {requested!r}. "
            f"Pick one of: pandoc, weasyprint, xhtml2pdf, html_only, auto."
        )

    for name in order:
        fn = _BACKENDS[name]
        try:
            ok = fn(md_path, pdf_path)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Backend %s raised: %s", name, exc)
            ok = False
        if ok:
            logger.info("md_to_pdf: wrote %s via %s", pdf_path, name)
            return pdf_path

    # Last resort
    return _render_html_only(md_path, pdf_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.md_to_pdf",
        description="Convert Markdown to PDF with auto-detected backend.",
    )
    p.add_argument("source", nargs="?", help="Path to .md source")
    p.add_argument("output", nargs="?", help="Output .pdf path")
    p.add_argument(
        "--backend",
        choices=("auto", "pandoc", "weasyprint", "xhtml2pdf", "html_only"),
        default="auto",
        help="Force a specific backend (default: auto — try in priority order).",
    )
    p.add_argument(
        "--list-backends",
        action="store_true",
        help="Print backend availability and exit.",
    )
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.list_backends:
        rows = list_backends()
        print(f"{'Backend':<14} {'Available':<10} Detail")
        print("-" * 78)
        for r in rows:
            mark = "yes" if r.available else "no"
            print(f"{r.name:<14} {mark:<10} {r.detail}")
        return 0

    if not args.source or not args.output:
        print("Error: source and output paths required (or pass --list-backends).",
              file=sys.stderr)
        return 2

    out = md_to_pdf(args.source, args.output, backend=args.backend)
    if out.suffix == ".html":
        print(f"Wrote HTML fallback: {out}", file=sys.stderr)
        return 1
    print(f"Wrote: {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
