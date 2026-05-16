"""Per-step migration audit.

Combines two information sources:

1. **Diff-based Cypher counts** between snapshot pairs (e.g. pre-step-17 vs
   post-step-17). Reports nodes touched, edges added, properties added.
   The actual snapshot loading lives in ``metrics/snapshots.py``; this
   module assumes the operator has already loaded each snapshot into a
   Neo4j instance and provides a connector for it.

2. **FAIR + density deltas** loaded from the JSON outputs of ``metrics/fair.py``
   and ``metrics/semantic_density.py``.

Output: ``metrics/output/step_audit.csv`` with one row per step::

    step, nodes_touched, edges_added, properties_added,
    runtime_s, fair_delta_overall, density_delta_node, density_delta_edge

Runtime per step is read from ``logs/`` if present (the existing pipeline
writes timing information into the step logs); otherwise blank.

CLI::

    python -m metrics.step_audit --pairs pre,17 17,18 18,19 19,20 \\
        --fair-per-step metrics/output/fair_score_per_step.json \\
        --density-per-step metrics/output/semantic_density_per_step.json \\
        --output metrics/output/step_audit.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class StepDiff:
    step: str
    nodes_before: int = 0
    nodes_after: int = 0
    edges_before: int = 0
    edges_after: int = 0
    distinct_labels_after: int = 0
    distinct_rel_types_after: int = 0

    @property
    def nodes_added(self) -> int:
        return max(0, self.nodes_after - self.nodes_before)

    @property
    def edges_added(self) -> int:
        return max(0, self.edges_after - self.edges_before)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["nodes_added"] = self.nodes_added
        d["edges_added"] = self.edges_added
        return d


@dataclass
class AuditRow:
    step: str
    nodes_touched: int = 0
    edges_added: int = 0
    properties_added: int = 0
    runtime_s: float | None = None
    fair_delta_overall: float | None = None
    density_delta_node: float | None = None
    density_delta_edge: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Connector protocol
# ---------------------------------------------------------------------------


class Connector:
    def run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Cypher snapshots
# ---------------------------------------------------------------------------


_NODE_COUNT_QUERY = "MATCH (n) RETURN count(n) AS n"
_EDGE_COUNT_QUERY = "MATCH ()-[r]->() RETURN count(r) AS n"
_DISTINCT_LABELS_QUERY = (
    "MATCH (n) UNWIND labels(n) AS lbl WITH DISTINCT lbl RETURN count(lbl) AS n"
)
_DISTINCT_REL_TYPES_QUERY = (
    "MATCH ()-[r]->() WITH DISTINCT type(r) AS t RETURN count(t) AS n"
)


def snapshot_counts(connector: Connector, label: str = "snapshot") -> dict[str, int]:
    """Read node/edge/label/rel-type counts from the connected graph."""

    def _scalar(q: str) -> int:
        rows = connector.run_query(q)
        return int(rows[0]["n"]) if rows else 0

    return {
        "label": label,
        "nodes": _scalar(_NODE_COUNT_QUERY),
        "edges": _scalar(_EDGE_COUNT_QUERY),
        "distinct_labels": _scalar(_DISTINCT_LABELS_QUERY),
        "distinct_rel_types": _scalar(_DISTINCT_REL_TYPES_QUERY),
    }


def diff_snapshots(before: dict[str, int], after: dict[str, int], step: str) -> StepDiff:
    return StepDiff(
        step=step,
        nodes_before=before.get("nodes", 0),
        nodes_after=after.get("nodes", 0),
        edges_before=before.get("edges", 0),
        edges_after=after.get("edges", 0),
        distinct_labels_after=after.get("distinct_labels", 0),
        distinct_rel_types_after=after.get("distinct_rel_types", 0),
    )


# ---------------------------------------------------------------------------
# Loading per-step deltas
# ---------------------------------------------------------------------------


def load_fair_per_step(path: Path | str) -> dict[str, float]:
    """Read a JSON like::

        {
          "per_step": {
            "17": {"overall_score": 0.61},
            "18": {"overall_score": 0.74},
            ...
          }
        }

    Returns ``{step → overall_score}``. Returns an empty dict if the file
    does not exist (FAIR per-step may not have been computed yet).
    """

    p = Path(path)
    if not p.exists():
        logger.warning("FAIR per-step file %s missing", p)
        return {}
    with open(p, "r", encoding="utf-8") as f:
        payload = json.load(f)
    per_step = payload.get("per_step", {}) or payload
    out: dict[str, float] = {}
    for k, v in per_step.items():
        if isinstance(v, dict) and "overall_score" in v:
            out[str(k)] = float(v["overall_score"])
        elif isinstance(v, (int, float)):
            out[str(k)] = float(v)
    return out


def load_density_per_step(path: Path | str) -> dict[str, dict[str, float]]:
    """Read a JSON like::

        {
          "per_step": {
            "17": {"node_density": 0.42, "edge_density": 0.10},
            ...
          }
        }

    Returns ``{step → {node_density, edge_density}}``.
    """

    p = Path(path)
    if not p.exists():
        logger.warning("Density per-step file %s missing", p)
        return {}
    with open(p, "r", encoding="utf-8") as f:
        payload = json.load(f)
    per_step = payload.get("per_step", {}) or payload
    out: dict[str, dict[str, float]] = {}
    for k, v in per_step.items():
        if isinstance(v, dict):
            entry = {}
            if "node_density" in v:
                entry["node_density"] = float(v["node_density"])
            if "edge_density" in v:
                entry["edge_density"] = float(v["edge_density"])
            if "aggregate" in v and isinstance(v["aggregate"], dict):
                entry.setdefault("node_density", float(v["aggregate"].get("node_density", 0.0)))
                entry.setdefault("edge_density", float(v["aggregate"].get("edge_density", 0.0)))
            if entry:
                out[str(k)] = entry
    return out


# ---------------------------------------------------------------------------
# Runtime parsing
# ---------------------------------------------------------------------------


_RUNTIME_RE = re.compile(
    r"step\s*(?P<step>\d+).*?(?P<duration>\d+(?:\.\d+)?)\s*(?P<unit>s|sec|seconds|ms|min|m)\b",
    re.IGNORECASE,
)


def parse_runtime_log(path: Path | str) -> dict[str, float]:
    """Best-effort extraction of ``{step → seconds}`` from a free-form log file.

    Recognises lines like::

        Step 17 completed in 12.3s
        step18 done in 4.5 sec
        Step 19 took 2 min

    Anything it can't parse is ignored. Returns empty dict if the file is
    missing.
    """

    p = Path(path)
    if not p.exists():
        return {}

    out: dict[str, float] = {}
    text = p.read_text(encoding="utf-8", errors="ignore")
    for match in _RUNTIME_RE.finditer(text):
        step = match.group("step")
        duration = float(match.group("duration"))
        unit = match.group("unit").lower()
        if unit in ("ms",):
            seconds = duration / 1000.0
        elif unit in ("min", "m"):
            seconds = duration * 60.0
        else:
            seconds = duration
        out[step] = seconds
    return out


# ---------------------------------------------------------------------------
# Audit assembly
# ---------------------------------------------------------------------------


def build_audit_rows(
    diffs: list[StepDiff],
    *,
    fair_per_step: dict[str, float] | None = None,
    density_per_step: dict[str, dict[str, float]] | None = None,
    runtimes: dict[str, float] | None = None,
) -> list[AuditRow]:
    """Assemble final audit rows.

    The FAIR / density inputs are *cumulative* per-step scores; this
    function converts them to deltas relative to the prior row (in input
    order). If ``fair_per_step`` is missing for a step, ``fair_delta_overall``
    is left as None.
    """

    fair_per_step = fair_per_step or {}
    density_per_step = density_per_step or {}
    runtimes = runtimes or {}

    rows: list[AuditRow] = []
    prior_fair: float | None = None
    prior_node_d: float | None = None
    prior_edge_d: float | None = None

    for d in diffs:
        # FAIR delta
        cur_fair = fair_per_step.get(d.step)
        fair_delta = None
        if cur_fair is not None and prior_fair is not None:
            fair_delta = round(cur_fair - prior_fair, 4)
        if cur_fair is not None:
            prior_fair = cur_fair

        # Density deltas
        cur_density = density_per_step.get(d.step, {})
        cur_node = cur_density.get("node_density")
        cur_edge = cur_density.get("edge_density")
        node_delta = (
            round(cur_node - prior_node_d, 4)
            if cur_node is not None and prior_node_d is not None
            else None
        )
        edge_delta = (
            round(cur_edge - prior_edge_d, 4)
            if cur_edge is not None and prior_edge_d is not None
            else None
        )
        if cur_node is not None:
            prior_node_d = cur_node
        if cur_edge is not None:
            prior_edge_d = cur_edge

        rows.append(
            AuditRow(
                step=d.step,
                nodes_touched=d.nodes_added,
                edges_added=d.edges_added,
                properties_added=0,  # populated by an optional Cypher pass; left 0 in M5.1
                runtime_s=runtimes.get(d.step),
                fair_delta_overall=fair_delta,
                density_delta_node=node_delta,
                density_delta_edge=edge_delta,
            )
        )

    return rows


def write_csv(rows: list[AuditRow], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "step",
        "nodes_touched",
        "edges_added",
        "properties_added",
        "runtime_s",
        "fair_delta_overall",
        "density_delta_node",
        "density_delta_edge",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_dict())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics.step_audit",
        description="Assemble per-step migration audit CSV.",
    )
    p.add_argument(
        "--pairs",
        nargs="+",
        required=False,
        help='Snapshot pairs as "before,after" tokens (e.g. "pre,17 17,18 18,19 19,20"). '
             "If omitted, no diff calls are run and the audit row counts are zero.",
    )
    p.add_argument("--fair-per-step", default="outputs/metrics/fair_score_per_step.json")
    p.add_argument("--density-per-step", default="outputs/metrics/semantic_density_per_step.json")
    p.add_argument("--runtime-log", default=None)
    p.add_argument("--output", default="outputs/metrics/step_audit.csv")
    p.add_argument("--neo4j-uri", default=None)
    p.add_argument("--user", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    fair_per_step = load_fair_per_step(args.fair_per_step)
    density_per_step = load_density_per_step(args.density_per_step)
    runtimes = parse_runtime_log(args.runtime_log) if args.runtime_log else {}

    diffs: list[StepDiff] = []
    if args.pairs:
        # Live diff path requires re-loading each snapshot. The actual
        # neo4j-admin load lives in metrics/snapshots.py; here we assume
        # the operator restored each snapshot into the connected DB and
        # passed the pair labels for bookkeeping. The simpler default
        # below skips the live diffs and emits zero counts, leaving the
        # FAIR/density columns to carry the per-step story.
        logger.warning(
            "Live snapshot diffing not yet automated — pass empty diffs (zeros). "
            "Use metrics.snapshots.load() between pairs and call build_audit_rows "
            "from a wrapper script."
        )
        for pair in args.pairs:
            before, after = pair.split(",")
            diffs.append(StepDiff(step=after))

    rows = build_audit_rows(
        diffs,
        fair_per_step=fair_per_step,
        density_per_step=density_per_step,
        runtimes=runtimes,
    )
    write_csv(rows, Path(args.output))
    logger.info("Wrote %s (%d rows)", args.output, len(rows))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
