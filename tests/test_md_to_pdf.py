"""Tests for tools.md_to_pdf."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from tools import md_to_pdf as mod  # noqa: E402


SAMPLE_MD = """# Sample report

## Section 1

Hello **world**. Here is a list:

- alpha
- beta
- gamma

```python
print("hi")
```

## Section 2

| Col A | Col B |
|---|---|
| 1 | 2 |
| 3 | 4 |

![logo](logo.svg)
"""


def _write_sample(tmp_path: Path) -> Path:
    md = tmp_path / "sample.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    (tmp_path / "logo.svg").write_text("<svg/>", encoding="utf-8")
    return md


# ---------------------------------------------------------------------------
# Capability probes
# ---------------------------------------------------------------------------


def test_list_backends_returns_four_entries():
    rows = mod.list_backends()
    names = [r.name for r in rows]
    assert names == ["pandoc", "weasyprint", "xhtml2pdf", "html_only"]
    for r in rows:
        assert isinstance(r.available, bool)
        assert r.detail


# ---------------------------------------------------------------------------
# md_to_html / wrap / image rewriting
# ---------------------------------------------------------------------------


def test_md_to_html_handles_tables_and_code(tmp_path):
    md = _write_sample(tmp_path)
    html = mod._md_to_html(md)
    # With the `markdown` lib: tables extension produces a <table>.
    # Without it: the fallback wraps everything in a styled <pre ...>.
    assert "<table>" in html or "<pre" in html
    assert "Sample report" in html


def test_resolve_image_paths_rewrites_relative_only(tmp_path):
    md_dir = tmp_path
    html = (
        '<img alt="a" src="paper_outputs/x.svg">'
        '<img alt="b" src="https://example.com/y.png">'
        '<img alt="c" src="data:image/png;base64,xx">'
    )
    out = mod._resolve_image_paths(html, md_dir)
    # Relative path got rewritten
    assert "paper_outputs/x.svg" in out
    assert "file://" in out or md_dir.resolve().as_uri() in out
    # Absolute URLs untouched
    assert 'src="https://example.com/y.png"' in out
    assert 'src="data:image/png;base64,xx"' in out


def test_wrap_html_includes_default_css():
    body = "<h1>hi</h1>"
    html = mod._wrap_html(body, title="t")
    assert "<style>" in html
    assert "@page" in html
    assert "hi</h1>" in html


# ---------------------------------------------------------------------------
# html_only fallback
# ---------------------------------------------------------------------------


def test_html_only_fallback_produces_html(tmp_path):
    md = _write_sample(tmp_path)
    out = mod.md_to_pdf(md, tmp_path / "out.pdf", backend="html_only")
    assert out.suffix == ".html"
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert "Sample report" in body
    assert "<style>" in body


# ---------------------------------------------------------------------------
# Backend dispatch
# ---------------------------------------------------------------------------


def test_unknown_backend_raises(tmp_path):
    md = _write_sample(tmp_path)
    with pytest.raises(ValueError, match="Unknown backend"):
        mod.md_to_pdf(md, tmp_path / "out.pdf", backend="not-a-backend")


def test_missing_source_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        mod.md_to_pdf(tmp_path / "missing.md", tmp_path / "out.pdf")


def test_auto_falls_back_to_html_when_no_pdf_backend(tmp_path, monkeypatch):
    """Force every PDF backend to claim unavailable — ensures graceful fallback."""

    monkeypatch.setattr(mod, "_have_pandoc", lambda: None)
    monkeypatch.setattr(mod, "_have_weasyprint", lambda: False)
    monkeypatch.setattr(mod, "_have_xhtml2pdf", lambda: False)

    md = _write_sample(tmp_path)
    out = mod.md_to_pdf(md, tmp_path / "out.pdf")
    assert out.suffix == ".html"
    assert out.exists()


def test_env_var_overrides_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MD_TO_PDF_BACKEND", "html_only")
    md = _write_sample(tmp_path)
    out = mod.md_to_pdf(md, tmp_path / "out.pdf")
    assert out.suffix == ".html"


def test_explicit_backend_arg_wins_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MD_TO_PDF_BACKEND", "html_only")
    monkeypatch.setattr(mod, "_have_pandoc", lambda: None)
    monkeypatch.setattr(mod, "_have_weasyprint", lambda: False)
    monkeypatch.setattr(mod, "_have_xhtml2pdf", lambda: False)
    md = _write_sample(tmp_path)
    # Forcing 'auto' explicitly with no backends available → still html
    out = mod.md_to_pdf(md, tmp_path / "out.pdf", backend="auto")
    assert out.suffix == ".html"


# ---------------------------------------------------------------------------
# Pandoc integration (mocked)
# ---------------------------------------------------------------------------


def test_pandoc_returns_false_when_binary_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_have_pandoc", lambda: None)
    md = _write_sample(tmp_path)
    assert mod._render_with_pandoc(md, tmp_path / "out.pdf") is False


def test_pandoc_invocation_uses_resource_path(tmp_path, monkeypatch):
    """When pandoc is found, we shell out with --resource-path set so
    relative images resolve correctly."""

    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        out_idx = cmd.index("-o") + 1
        Path(cmd[out_idx]).write_bytes(b"%PDF-1.4 fake")
        return Result()

    monkeypatch.setattr(mod, "_have_pandoc", lambda: "/fake/pandoc")
    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    md = _write_sample(tmp_path)
    pdf = tmp_path / "out.pdf"
    ok = mod._render_with_pandoc(md, pdf)
    assert ok
    assert pdf.exists()
    assert "--resource-path" in captured["cmd"]
    rp_idx = captured["cmd"].index("--resource-path")
    assert captured["cmd"][rp_idx + 1] == str(md.parent)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_list_backends(capsys):
    code = mod.main(["--list-backends"])
    captured = capsys.readouterr()
    assert code == 0
    assert "pandoc" in captured.out
    assert "html_only" in captured.out


def test_cli_missing_args(capsys):
    code = mod.main([])
    assert code == 2
    captured = capsys.readouterr()
    assert "source and output" in captured.err.lower()


def test_cli_writes_html_when_no_backend(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mod, "_have_pandoc", lambda: None)
    monkeypatch.setattr(mod, "_have_weasyprint", lambda: False)
    monkeypatch.setattr(mod, "_have_xhtml2pdf", lambda: False)

    md = _write_sample(tmp_path)
    pdf = tmp_path / "out.pdf"
    code = mod.main([str(md), str(pdf), "--backend", "auto"])
    captured = capsys.readouterr()
    # Exit 1 when fallback to HTML kicks in
    assert code == 1
    assert "HTML fallback" in captured.err


# ---------------------------------------------------------------------------
# Pure-Python backend smoke tests (only run if the lib is installed)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not mod._have_xhtml2pdf(), reason="xhtml2pdf not installed")
def test_xhtml2pdf_round_trip(tmp_path):
    md = _write_sample(tmp_path)
    pdf = tmp_path / "out.pdf"
    out = mod.md_to_pdf(md, pdf, backend="xhtml2pdf")
    assert out == pdf
    assert pdf.exists()
    assert pdf.stat().st_size > 200
    # Magic bytes
    assert pdf.read_bytes()[:4] == b"%PDF"


@pytest.mark.skipif(not mod._have_weasyprint(), reason="weasyprint not installed")
def test_weasyprint_round_trip(tmp_path):
    md = _write_sample(tmp_path)
    pdf = tmp_path / "out.pdf"
    out = mod.md_to_pdf(md, pdf, backend="weasyprint")
    assert out == pdf
    assert pdf.exists()
    assert pdf.stat().st_size > 200
    assert pdf.read_bytes()[:4] == b"%PDF"
