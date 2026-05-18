"""Cross-check thesis numeric claims against the canonical metric JSONs.

Reads every numeric token from ``Thesis/OğuzhanGüngör_Tez (1)/thesis.tex`` and
classifies each as one of:

    backed:       a JSON value matches the literal at this offset
    suspect:      a literal that looks like a metric but no JSON match was found
    prose:        a literal that does not look like a metric (years, page nos)

A small set of token regexes (percentages, comma-separated integers, decimal
ratios) drives the classification. The output is a Markdown report plus a
machine-readable JSON.

This is a one-shot reading script; it does not write back to the thesis.

CLI::

    python -m metrics.cross_check
    python -m metrics.cross_check --thesis path/to/thesis.tex
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Patterns we treat as candidate metric tokens.
TOKEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("comma_int", re.compile(r"\b\d{1,3}(?:[,{]?\,?[}]?\d{3})+\b")),
    ("percent", re.compile(r"\d+\.\d+\s*\\?,?\s*\\?%")),
    ("decimal", re.compile(r"\b0\.\d{3,4}\b")),
    ("ratio", re.compile(r"\b\d+/\d+\b")),
]


def _collect_json_values(payload: Any, out: dict[str, Any], prefix: str = "") -> None:
    """Flatten a JSON tree into {dotted-key: value}."""
    if isinstance(payload, dict):
        for k, v in payload.items():
            _collect_json_values(v, out, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(payload, list):
        for i, v in enumerate(payload):
            _collect_json_values(v, out, f"{prefix}[{i}]")
    else:
        out[prefix] = payload


def _normalize_thesis_token(tok: str) -> str:
    """Strip LaTeX `{,}` kerning marks and percent / texttt wrappers."""
    s = tok.replace("{,}", ",").replace("\\,", "").replace("\\%", "%")
    return s.strip()


def _matches_value(thesis_tok: str, json_val: Any) -> bool:
    s = _normalize_thesis_token(thesis_tok)
    # Comma integers.
    try:
        s_int = int(s.replace(",", ""))
        if isinstance(json_val, (int, float)) and float(json_val).is_integer():
            return int(json_val) == s_int
    except ValueError:
        pass
    # Percent literals (e.g., 99.68 %).
    if "%" in s:
        try:
            pct = float(s.replace("%", "").strip())
            if isinstance(json_val, float):
                return abs(json_val * 100 - pct) < 0.05
        except ValueError:
            pass
    # Decimal literals.
    try:
        d = float(s)
        if isinstance(json_val, float):
            return abs(json_val - d) < 1e-3
    except ValueError:
        pass
    # Ratios like 5/5.
    if "/" in s:
        try:
            num, den = s.split("/")
            num_i, den_i = int(num), int(den)
            if isinstance(json_val, dict):
                strong = json_val.get("strong_matches")
                total = json_val.get("total")
                if strong == num_i and total == den_i:
                    return True
        except ValueError:
            pass
    return False


def cross_check(thesis_path: Path, json_paths: list[Path]) -> dict[str, Any]:
    if not thesis_path.exists():
        raise FileNotFoundError(thesis_path)

    text = thesis_path.read_text(encoding="utf-8")

    json_values: dict[str, dict[str, Any]] = {}
    for jp in json_paths:
        if not jp.exists():
            logger.warning("Missing JSON source: %s", jp)
            continue
        with open(jp, "r", encoding="utf-8") as f:
            data = json.load(f)
        flat: dict[str, Any] = {}
        _collect_json_values(data, flat)
        json_values[jp.name] = flat

    seen: set[tuple[str, int]] = set()
    findings: list[dict[str, Any]] = []
    for kind, pat in TOKEN_PATTERNS:
        for m in pat.finditer(text):
            key = (m.group(0), m.start())
            if key in seen:
                continue
            seen.add(key)
            tok = m.group(0)
            line_no = text.count("\n", 0, m.start()) + 1

            matched_in: list[str] = []
            for src, flat in json_values.items():
                for json_key, val in flat.items():
                    if _matches_value(tok, val):
                        matched_in.append(f"{src}:{json_key}")
                        break

            findings.append(
                {
                    "token": tok,
                    "kind": kind,
                    "line": line_no,
                    "matched_in": matched_in,
                    "status": "backed" if matched_in else "suspect",
                }
            )

    summary = {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "thesis_path": str(thesis_path),
        "json_sources": [str(p) for p in json_paths],
        "total_tokens": len(findings),
        "backed": sum(1 for f in findings if f["status"] == "backed"),
        "suspect": sum(1 for f in findings if f["status"] == "suspect"),
        "findings": findings,
    }
    return summary


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics.cross_check",
        description="Fact-check thesis numeric claims against canonical JSON outputs.",
    )
    p.add_argument(
        "--thesis",
        default="Thesis/OğuzhanGüngör_Tez (1)/thesis.tex",
        help="Path to the thesis .tex file.",
    )
    p.add_argument(
        "--output",
        default="outputs/metrics/cross_check.json",
        help="Path for the JSON output.",
    )
    p.add_argument(
        "--metrics-dir",
        default="outputs/metrics",
        help="Directory containing canonical metric JSONs.",
    )
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    repo_root = Path(__file__).resolve().parents[1]
    thesis = Path(args.thesis)
    if not thesis.is_absolute():
        thesis = repo_root / thesis

    metrics_dir = Path(args.metrics_dir)
    if not metrics_dir.is_absolute():
        metrics_dir = repo_root / metrics_dir

    json_paths = sorted(metrics_dir.glob("*.json"))
    if not json_paths:
        logger.error("No metric JSONs found under %s", metrics_dir)
        return 2

    summary = cross_check(thesis, json_paths)

    out = Path(args.output)
    if not out.is_absolute():
        out = repo_root / out
    write_json(summary, out)
    logger.info(
        "Wrote %s — %d tokens, %d backed, %d suspect",
        out,
        summary["total_tokens"],
        summary["backed"],
        summary["suspect"],
    )
    print(
        json.dumps(
            {
                "total": summary["total_tokens"],
                "backed": summary["backed"],
                "suspect": summary["suspect"],
                "rate": round(summary["backed"] / summary["total_tokens"], 4)
                if summary["total_tokens"]
                else 0.0,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
