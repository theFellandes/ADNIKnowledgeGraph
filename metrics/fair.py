"""FAIR principle scorer.

Reads ``metrics/fair_principles.yaml``, runs each principle's check against
the graph (Cypher), the filesystem (file presence), or a manual default,
and produces a JSON score.

Three-level scale per principle::

    yes      = 1.0
    partial  = 0.5
    no       = 0.0

For Cypher checks the result must yield a column ``coverage`` (0.0–1.0) or
a single integer-like column above the configured ``partial_threshold`` /
``full_threshold``. For file checks: presence of any listed path → partial,
all listed paths present → full. Manual checks read the ``default`` field
of the rubric.

CLI::

    python -m metrics.fair                 # scores live graph, writes metrics/output/fair_score.json
    python -m metrics.fair --rubric ...
    python -m metrics.fair --output ...
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


YES = "yes"
PARTIAL = "partial"
NO = "no"

LEVEL_TO_SCORE = {YES: 1.0, PARTIAL: 0.5, NO: 0.0}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PrincipleResult:
    id: str
    name: str
    level: str
    score: float
    measured: dict[str, Any] = field(default_factory=dict)
    threshold: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class FairReport:
    schema_version: int
    timestamp: str
    graph_uri: str
    rubric_version: int
    overall_score: float
    by_dimension: dict[str, float]
    principles: dict[str, PrincipleResult]
    duration_seconds: float
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "graph_uri": self.graph_uri,
            "rubric_version": self.rubric_version,
            "overall_score": round(self.overall_score, 4),
            "by_dimension": {k: round(v, 4) for k, v in self.by_dimension.items()},
            "principles": {k: asdict(v) for k, v in self.principles.items()},
            "duration_seconds": round(self.duration_seconds, 3),
            "config": self.config,
        }


# ---------------------------------------------------------------------------
# Connector protocol
# ---------------------------------------------------------------------------


class Connector:
    def run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Per-check evaluators
# ---------------------------------------------------------------------------


def _eval_cypher(
    connector: Connector | None,
    check: dict[str, Any],
    defaults: dict[str, float],
) -> tuple[str, dict[str, Any], dict[str, Any], list[str]]:
    """Run a Cypher check and reduce it to (level, measured, threshold, notes)."""

    if connector is None:
        return NO, {"error": "no connector"}, {}, ["Cypher check requires a connector"]

    query = check["query"]
    rows = connector.run_query(query)
    if not rows:
        return NO, {"rows": 0}, {}, ["Cypher returned no rows"]

    row = rows[0]
    # Pick the first numeric column
    measured_value: float | None = None
    measured_col: str | None = None
    for k, v in row.items():
        if isinstance(v, (int, float)):
            measured_value = float(v)
            measured_col = k
            break
    if measured_value is None:
        return NO, {"row": dict(row)}, {}, ["No numeric column in Cypher result"]

    # Threshold semantics: if 0 <= measured <= 1, treat as a coverage ratio.
    # Otherwise use partial_threshold / full_threshold from the check.
    if 0.0 <= measured_value <= 1.0 and "partial_threshold" not in check:
        partial = float(defaults.get("partial_threshold", 0.5))
        full = float(defaults.get("full_threshold", 0.95))
    else:
        partial = float(check.get("partial_threshold", defaults.get("partial_threshold", 0.5)))
        full = float(check.get("full_threshold", defaults.get("full_threshold", 0.95)))

    if measured_value >= full:
        level = YES
    elif measured_value >= partial:
        level = PARTIAL
    else:
        level = NO

    return (
        level,
        {"value": round(measured_value, 4), "column": measured_col},
        {"partial_threshold": partial, "full_threshold": full},
        [],
    )


def _eval_file(
    check: dict[str, Any],
    project_root: Path,
) -> tuple[str, dict[str, Any], dict[str, Any], list[str]]:
    paths = [project_root / p for p in check.get("paths", [])]
    present = [str(p.relative_to(project_root)) for p in paths if p.exists()]
    missing = [str(p.relative_to(project_root)) for p in paths if not p.exists()]

    full_if_all = bool(check.get("full_if_all", True))
    partial_if_any = bool(check.get("partial_if_any", True))

    if missing == [] and present:
        level = YES if full_if_all else PARTIAL
    elif present:
        level = PARTIAL if partial_if_any else NO
    else:
        level = NO

    return (
        level,
        {"present": present, "missing": missing},
        {"full_if_all": full_if_all, "partial_if_any": partial_if_any},
        [],
    )


def _eval_manual(
    check: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any], list[str]]:
    raw = check.get("default", NO)
    # Accept either yes/no/partial keywords or a numeric default.
    if isinstance(raw, bool):
        level = YES if raw else NO
    elif isinstance(raw, (int, float)):
        if raw >= 1.0:
            level = YES
        elif raw >= 0.5:
            level = PARTIAL
        else:
            level = NO
    else:
        token = str(raw).strip().lower()
        if token in {"yes", "y", "true", "full"}:
            level = YES
        elif token in {"partial", "p", "half"}:
            level = PARTIAL
        else:
            level = NO

    return level, {"default": raw}, {}, ["Manual review — default applied"]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


_DIMENSION_PREFIX = {
    "F": "Findable",
    "A": "Accessible",
    "I": "Interoperable",
    "R": "Reusable",
}


def _dimension_for(principle_id: str) -> str:
    first = principle_id[:1].upper()
    return _DIMENSION_PREFIX.get(first, "Other")


def load_rubric(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"FAIR rubric not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        rubric = yaml.safe_load(f)
    if not isinstance(rubric, dict) or "principles" not in rubric:
        raise ValueError(f"Malformed FAIR rubric at {path}: missing 'principles'")
    return rubric


def score_fair(
    connector: Connector | None,
    rubric: dict[str, Any],
    *,
    graph_uri: str = "(unknown)",
    project_root: Path | None = None,
) -> FairReport:
    """Score every principle in the rubric. ``connector`` may be ``None`` if
    no Cypher checks need to run (manual / file only)."""

    project_root = project_root or PROJECT_ROOT
    defaults = rubric.get("defaults", {}) or {}
    principles_spec: dict[str, dict[str, Any]] = rubric.get("principles", {})

    started = time.time()

    results: dict[str, PrincipleResult] = {}
    for pid, spec in principles_spec.items():
        check = spec.get("check", {})
        check_type = check.get("type", "manual")
        try:
            if check_type == "cypher":
                level, measured, threshold, notes = _eval_cypher(connector, check, defaults)
            elif check_type == "file":
                level, measured, threshold, notes = _eval_file(check, project_root)
            elif check_type == "manual":
                level, measured, threshold, notes = _eval_manual(check)
            else:
                level, measured, threshold, notes = NO, {}, {}, [f"Unknown check type: {check_type}"]
        except Exception as exc:
            logger.exception("Principle %s check failed", pid)
            level, measured, threshold, notes = NO, {"error": str(exc)}, {}, [f"check raised {type(exc).__name__}"]

        results[pid] = PrincipleResult(
            id=pid,
            name=str(spec.get("name", pid)),
            level=level,
            score=LEVEL_TO_SCORE[level],
            measured=measured,
            threshold=threshold,
            notes=notes,
        )

    if results:
        overall = sum(r.score for r in results.values()) / len(results)
    else:
        overall = 0.0

    by_dim_totals: dict[str, list[float]] = {}
    for r in results.values():
        by_dim_totals.setdefault(_dimension_for(r.id), []).append(r.score)
    by_dimension = {dim: sum(s) / len(s) for dim, s in by_dim_totals.items() if s}

    return FairReport(
        schema_version=1,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        graph_uri=graph_uri,
        rubric_version=int(rubric.get("version", 1)),
        overall_score=overall,
        by_dimension=by_dimension,
        principles=results,
        duration_seconds=time.time() - started,
        config={"defaults": defaults, "project_root": str(project_root)},
    )


def write_json(report: FairReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)


def diff(baseline: FairReport, post: FairReport) -> dict[str, Any]:
    """Per-principle / per-dimension delta (post − baseline)."""

    keys = sorted(set(baseline.principles) | set(post.principles))
    per_principle = []
    for k in keys:
        b = baseline.principles.get(k)
        p = post.principles.get(k)
        per_principle.append(
            {
                "id": k,
                "baseline": {"level": b.level, "score": b.score} if b else None,
                "post": {"level": p.level, "score": p.score} if p else None,
                "delta": round(((p.score if p else 0.0) - (b.score if b else 0.0)), 4),
            }
        )

    dim_keys = sorted(set(baseline.by_dimension) | set(post.by_dimension))
    by_dim = {
        d: round(post.by_dimension.get(d, 0.0) - baseline.by_dimension.get(d, 0.0), 4)
        for d in dim_keys
    }

    return {
        "schema_version": 1,
        "baseline_timestamp": baseline.timestamp,
        "post_timestamp": post.timestamp,
        "overall_delta": round(post.overall_score - baseline.overall_score, 4),
        "by_dimension_delta": by_dim,
        "per_principle": per_principle,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics.fair",
        description="Score the graph against the FAIR principles rubric.",
    )
    p.add_argument(
        "--rubric",
        default=str(PROJECT_ROOT / "metrics" / "fair_principles.yaml"),
    )
    p.add_argument("--output", default="outputs/metrics/fair_score.json")
    p.add_argument("--neo4j-uri", default=None)
    p.add_argument("--user", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--no-cypher", action="store_true",
                   help="Skip the live graph queries (manual/file checks only).")
    return p


def _resolve_credentials(args: argparse.Namespace) -> tuple[str, str, str]:
    uri, user, pw = args.neo4j_uri, args.user, args.password
    if not (uri and user and pw):
        from utils.env_loader import load_config

        cfg = load_config()
        uri = uri or cfg.get("neo4j_uri")
        user = user or cfg.get("neo4j_user", "neo4j")
        pw = pw or cfg.get("neo4j_password")
    if not (uri and user and pw):
        raise RuntimeError("Neo4j credentials missing")
    return uri, user, pw


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        rubric = load_rubric(args.rubric)
    except Exception as exc:
        logger.error("Failed to load rubric: %s", exc)
        return 2

    connector = None
    graph_uri = "(no-cypher)"
    if not args.no_cypher:
        try:
            uri, user, pw = _resolve_credentials(args)
            from utils.neo4j_connector import Neo4jConnector

            connector = Neo4jConnector(uri=uri, user=user, password=pw)
            graph_uri = uri
        except Exception as exc:
            logger.error("Cannot connect to Neo4j: %s — pass --no-cypher to skip", exc)
            return 2

    try:
        report = score_fair(connector, rubric, graph_uri=graph_uri)
    finally:
        if connector is not None:
            connector.close()

    out = Path(args.output)
    if not out.is_absolute():
        out = PROJECT_ROOT / out
    write_json(report, out)
    logger.info("Wrote %s", out)
    print(json.dumps(
        {
            "overall_score": round(report.overall_score, 4),
            "by_dimension": {k: round(v, 4) for k, v in report.by_dimension.items()},
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
