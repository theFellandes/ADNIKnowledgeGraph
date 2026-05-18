"""Mapping-rule registry — counts rules per source CSV plus the consolidated index.

Reads every ``*.csv`` in ``ontology/mappings/`` and reports per-file row counts
plus a global summary. Independent of Neo4j: this metric reads files only.

CLI::

    python -m metrics.mapping_rules
    python -m metrics.mapping_rules --output outputs/metrics/mapping_rules.json
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _count_rows(csv_path: Path) -> tuple[int, list[str], str | None, str | None]:
    """Return (data_row_count, header_columns, min_last_verified, max_last_verified)."""
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return 0, [], None, None
        rows = list(reader)

    last_verified_col = None
    for i, col in enumerate(header):
        if col.strip().lower() == "last_verified_date":
            last_verified_col = i
            break

    dates: list[str] = []
    if last_verified_col is not None:
        for row in rows:
            if last_verified_col < len(row):
                d = row[last_verified_col].strip()
                if d:
                    dates.append(d)

    return len(rows), header, (min(dates) if dates else None), (max(dates) if dates else None)


def compute(mappings_dir: Path) -> dict[str, Any]:
    if not mappings_dir.is_dir():
        raise FileNotFoundError(f"Mappings directory not found: {mappings_dir}")

    rows_out: list[dict[str, Any]] = []
    total = 0
    for csv_path in sorted(mappings_dir.glob("*.csv")):
        count, header, mn, mx = _count_rows(csv_path)
        rows_out.append(
            {
                "source_csv": csv_path.name,
                "rule_count": count,
                "columns": header,
                "last_verified_min": mn,
                "last_verified_max": mx,
            }
        )
        if csv_path.name != "index.csv":
            total += count

    index_row = next((r for r in rows_out if r["source_csv"] == "index.csv"), None)
    index_total = index_row["rule_count"] if index_row else None

    return {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mappings_dir": str(mappings_dir),
        "files": rows_out,
        "per_file_sum": total,
        "index_total": index_total,
    }


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics.mapping_rules",
        description="Count mapping rules per source CSV under ontology/mappings/.",
    )
    p.add_argument(
        "--mappings-dir",
        default="ontology/mappings",
        help="Directory containing the rule CSVs.",
    )
    p.add_argument(
        "--output",
        default="outputs/metrics/mapping_rules.json",
        help="Path for the JSON output.",
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
    mappings_dir = Path(args.mappings_dir)
    if not mappings_dir.is_absolute():
        mappings_dir = repo_root / mappings_dir

    try:
        payload = compute(mappings_dir)
    except Exception as exc:
        logger.error("%s", exc)
        return 2

    out = Path(args.output)
    if not out.is_absolute():
        out = repo_root / out
    write_json(payload, out)
    logger.info("Wrote %s", out)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
