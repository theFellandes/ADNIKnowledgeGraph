"""Neo4j snapshot helpers for the metrics pipeline.

Wraps the offline ``neo4j-admin database dump`` / ``database load`` workflow.
The decision to use the offline path (DB stopped during dump) is recorded in
``docs/final_report/c7_plan_v2/IMPLEMENTATION_PLAN.md`` §10.

The functions here shell out to ``neo4j-admin`` via ``subprocess``. Stop /
start of the Neo4j service is left to the operator (Q.7 schedules downtime
windows) — this module only generates the commands and verifies the dump
file exists afterwards.

Typical usage::

    from metrics.snapshots import dump, load, plan_per_step_snapshots

    dump(
        database="neo4j",
        target=Path("data/snapshots/post_steps_17_20.dump"),
        neo4j_home=Path("/opt/neo4j"),
    )

    plan = plan_per_step_snapshots(["pre", 17, 18, 19, 20])
    for step, target in plan.items():
        print(step, "→", target)

CLI::

    python -m metrics.snapshots dump  --database neo4j --target data/snapshots/post.dump
    python -m metrics.snapshots load  --database neo4j --source data/snapshots/post.dump
    python -m metrics.snapshots plan  --steps pre,17,18,19,20
"""

from __future__ import annotations

import argparse
import logging
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


DEFAULT_SNAPSHOT_DIR = Path("data/snapshots")


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------


@dataclass
class SnapshotResult:
    operation: str          # "dump" | "load"
    database: str
    path: Path
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    bytes_written: int = 0

    @property
    def ok(self) -> bool:
        return self.returncode == 0


# ---------------------------------------------------------------------------
# Command resolution
# ---------------------------------------------------------------------------


def _resolve_admin_binary(neo4j_home: Path | None) -> str:
    """Find the neo4j-admin executable.

    Priority:
        1. ``$NEO4J_HOME/bin/neo4j-admin`` if neo4j_home given
        2. ``neo4j-admin`` on PATH
    """

    if neo4j_home:
        candidate = neo4j_home / "bin" / ("neo4j-admin.bat" if sys.platform == "win32" else "neo4j-admin")
        if candidate.exists():
            return str(candidate)
        logger.warning("neo4j-admin not found under %s; falling back to PATH", neo4j_home)

    on_path = shutil.which("neo4j-admin")
    if on_path:
        return on_path

    raise FileNotFoundError(
        "neo4j-admin not found. Set --neo4j-home or ensure neo4j-admin is on PATH."
    )


# ---------------------------------------------------------------------------
# Dump / load
# ---------------------------------------------------------------------------


def dump(
    database: str,
    target: Path | str,
    *,
    neo4j_home: Path | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> SnapshotResult:
    """Run ``neo4j-admin database dump`` to the given target file.

    The target's parent directory is created if missing. Caller is responsible
    for stopping the Neo4j service before calling this on a live deployment.
    """

    target = Path(target)
    if target.exists() and not overwrite:
        raise FileExistsError(f"{target} already exists (pass overwrite=True to replace)")

    target.parent.mkdir(parents=True, exist_ok=True)

    admin = _resolve_admin_binary(neo4j_home) if not dry_run else "neo4j-admin"
    cmd = [
        admin,
        "database",
        "dump",
        database,
        f"--to-path={target.parent}",
    ]

    logger.info("Dumping %s → %s", database, target)
    logger.info("Command: %s", " ".join(shlex.quote(c) for c in cmd))

    if dry_run:
        return SnapshotResult(
            operation="dump",
            database=database,
            path=target,
            command=cmd,
            returncode=0,
            stdout="(dry-run)",
            stderr="",
        )

    proc = subprocess.run(cmd, capture_output=True, text=True)
    # neo4j-admin writes the dump as <db>.dump in --to-path; rename to target if needed
    produced = target.parent / f"{database}.dump"
    bytes_written = 0
    if proc.returncode == 0 and produced.exists():
        if produced != target:
            produced.replace(target)
        bytes_written = target.stat().st_size

    return SnapshotResult(
        operation="dump",
        database=database,
        path=target,
        command=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        bytes_written=bytes_written,
    )


def load(
    database: str,
    source: Path | str,
    *,
    neo4j_home: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> SnapshotResult:
    """Run ``neo4j-admin database load`` from a dump file."""

    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(f"Snapshot not found: {source}")

    admin = _resolve_admin_binary(neo4j_home) if not dry_run else "neo4j-admin"
    cmd = [
        admin,
        "database",
        "load",
        database,
        f"--from-path={source.parent}",
    ]
    if force:
        cmd.append("--overwrite-destination")

    logger.info("Loading %s ← %s", database, source)
    logger.info("Command: %s", " ".join(shlex.quote(c) for c in cmd))

    if dry_run:
        return SnapshotResult(
            operation="load",
            database=database,
            path=source,
            command=cmd,
            returncode=0,
            stdout="(dry-run)",
            stderr="",
        )

    # neo4j-admin expects the dump filename to be <database>.dump in --from-path.
    # If `source` has a different name, copy it into a temp file beside it.
    expected = source.parent / f"{database}.dump"
    cleanup = False
    if source != expected:
        if expected.exists():
            raise FileExistsError(
                f"{expected} already exists; remove it before loading {source}"
            )
        shutil.copy2(source, expected)
        cleanup = True

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        if cleanup and expected.exists():
            expected.unlink()

    return SnapshotResult(
        operation="load",
        database=database,
        path=source,
        command=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


# ---------------------------------------------------------------------------
# Per-step snapshot planning
# ---------------------------------------------------------------------------


def plan_per_step_snapshots(
    steps: Sequence[str | int],
    *,
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
) -> dict[str, Path]:
    """Generate the canonical {step → snapshot_path} mapping.

    >>> plan_per_step_snapshots(["pre", 17, 18, 19, 20])
    {'pre': PosixPath('data/snapshots/pre_steps_17_20.dump'),
     '17': PosixPath('data/snapshots/post_step_17.dump'),
     '18': PosixPath('data/snapshots/post_step_18.dump'),
     '19': PosixPath('data/snapshots/post_step_19.dump'),
     '20': PosixPath('data/snapshots/post_step_20.dump')}
    """

    plan: dict[str, Path] = {}
    snapshot_dir = Path(snapshot_dir)
    for step in steps:
        s = str(step)
        if s == "pre":
            plan[s] = snapshot_dir / "pre_steps_17_20.dump"
        elif s == "post":
            plan[s] = snapshot_dir / "post_steps_17_20.dump"
        else:
            plan[s] = snapshot_dir / f"post_step_{s}.dump"
    return plan


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m metrics.snapshots",
        description="Wrap neo4j-admin database dump/load for the metrics pipeline.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pd = sub.add_parser("dump", help="Dump a database to a snapshot file")
    pd.add_argument("--database", default="neo4j")
    pd.add_argument("--target", required=True, help="Path to the .dump file")
    pd.add_argument("--neo4j-home", default=None)
    pd.add_argument("--overwrite", action="store_true")
    pd.add_argument("--dry-run", action="store_true")

    pl = sub.add_parser("load", help="Load a snapshot into a database")
    pl.add_argument("--database", default="neo4j")
    pl.add_argument("--source", required=True, help="Path to the .dump file")
    pl.add_argument("--neo4j-home", default=None)
    pl.add_argument("--force", action="store_true", help="Pass --overwrite-destination to neo4j-admin")
    pl.add_argument("--dry-run", action="store_true")

    pp = sub.add_parser("plan", help="Print the canonical {step → path} mapping")
    pp.add_argument("--steps", default="pre,17,18,19,20", help="Comma-separated step list")
    pp.add_argument("--snapshot-dir", default=str(DEFAULT_SNAPSHOT_DIR))

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    if args.command == "plan":
        plan = plan_per_step_snapshots(
            args.steps.split(","),
            snapshot_dir=Path(args.snapshot_dir),
        )
        for step, path in plan.items():
            print(f"{step}\t{path}")
        return 0

    if args.command == "dump":
        result = dump(
            args.database,
            args.target,
            neo4j_home=Path(args.neo4j_home) if args.neo4j_home else None,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
    elif args.command == "load":
        result = load(
            args.database,
            args.source,
            neo4j_home=Path(args.neo4j_home) if args.neo4j_home else None,
            force=args.force,
            dry_run=args.dry_run,
        )
    else:  # pragma: no cover
        raise ValueError(args.command)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
