"""Render Q1 thesis-editor / reviewer prompts against the canonical metrics JSONs.

The audit prompts under ``outputs/audit/`` are Jinja2 templates (``*.md.j2``).
This module loads every JSON under ``outputs/metrics/`` plus the freshest
``outputs/validity_reports/kg_validity_*.json`` into a single context dict and
renders each template to the same directory, atomically replacing the previous
``*.md`` output.

Typical use::

    python -m metrics --all                  # renders prompts as the final step
    python -m metrics --render-prompts       # standalone re-render

Failure modes are loud: a missing JSON or a missing template key raises with a
clear path; we never silently substitute empty strings.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jinja2

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


REQUIRED_METRICS_FILES = {
    "snapshot":  "canonical_snapshot.json",
    "fair":      "fair_score.json",
    "alzkb":     "alzkb_alignment.json",
    "audit":     "per_step_audit.json",
    "mapping":   "mapping_rules.json",
    "topology":  "graph_topology.json",
    "density":   "semantic_density.json",
    "tbox_abox": "tbox_abox.json",
    "contrib":   "source_ontology_contribution.json",
    "duplicity": "duplicity_check.json",
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required metrics JSON missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_validity_report(validity_dir: Path) -> tuple[Path, dict[str, Any]]:
    if not validity_dir.exists():
        raise FileNotFoundError(f"Validity report directory missing: {validity_dir}")
    candidates = sorted(validity_dir.glob("kg_validity_*.json"))
    if not candidates:
        raise FileNotFoundError(
            f"No kg_validity_*.json found under {validity_dir} — run `python -m metrics --validity` first"
        )
    latest = candidates[-1]
    return latest, json.loads(latest.read_text(encoding="utf-8"))


def build_context(metrics_dir: Path, validity_dir: Path) -> dict[str, Any]:
    """Load every canonical JSON into a single Jinja2 context dict.

    Raises ``FileNotFoundError`` naming the missing file if any required JSON
    is absent.
    """
    ctx: dict[str, Any] = {}
    for key, fname in REQUIRED_METRICS_FILES.items():
        ctx[key] = _load_json(metrics_dir / fname)

    validity_path, validity_doc = _latest_validity_report(validity_dir)
    ctx["validity"] = validity_doc
    ctx["meta"] = {
        "rendered_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "snapshot_source": str((metrics_dir / "canonical_snapshot.json").as_posix()),
        "validity_report": str(validity_path.as_posix()),
    }
    return ctx


def _filter_comma(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return str(value)


def _filter_pct(value: Any, decimals: int = 2) -> str:
    """Convert a fraction (0.9968) to a percentage string ("99.68%").

    Accepts already-percent values >= 1 unchanged (rare in our JSONs but
    keeps the filter forgiving of stale upstream data).
    """
    if value is None:
        return ""
    n = float(value)
    if n <= 1.0:
        n *= 100.0
    return f"{n:.{decimals}f}%"


def _filter_fixed(value: Any, decimals: int = 4) -> str:
    if value is None:
        return ""
    return f"{float(value):.{decimals}f}"


def _build_env(audit_dir: Path) -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(audit_dir)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    env.filters["comma"] = _filter_comma
    env.filters["pct"] = _filter_pct
    env.filters["fixed"] = _filter_fixed
    return env


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def render_prompts(
    metrics_dir: Path,
    audit_dir: Path,
    validity_dir: Path,
) -> list[Path]:
    """Render every ``*.md.j2`` in ``audit_dir`` to ``*.md`` atomically.

    Returns the list of rendered output paths.
    """
    if not audit_dir.exists():
        raise FileNotFoundError(f"Audit prompt directory missing: {audit_dir}")

    templates = sorted(audit_dir.glob("*.md.j2"))
    if not templates:
        logger.warning("No *.md.j2 templates found under %s", audit_dir)
        return []

    ctx = build_context(metrics_dir, validity_dir)
    env = _build_env(audit_dir)

    written: list[Path] = []
    for template_path in templates:
        out_path = template_path.with_suffix("")  # strip .j2 → leaves .md
        template = env.get_template(template_path.name)
        rendered = template.render(**ctx)
        _atomic_write(out_path, rendered)
        written.append(out_path)
        logger.info("Rendered %s (%d chars)", out_path, len(rendered))
    return written
