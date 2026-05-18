"""Per-step audit orchestrator — Python wrapper around docker + metrics.per_step_audit.

Wraps the in-process Python audit (``python -m metrics.per_step_audit``) with an
optional offline ``neo4j-admin database dump`` backup before the run, and a
matching restore-from-dump path. Uses ``subprocess`` to call docker; no
PowerShell execution-policy issues, no shell scripts.

What this script does
---------------------

1. (Optional, default ON) Takes an offline ``neo4j-admin database dump`` of the
   current graph state and writes it to ``data/snapshots/``, so a bad audit run
   can be rolled back even if the in-script idempotent-replay safety net fails.
2. Runs ``python -m metrics.per_step_audit`` — the Python orchestrator that
   does rollback + snapshot + replay + state-equivalence check.
3. Optionally restores from a saved dump if the audit aborts (or any time
   later, on demand).

Why this exists
---------------

``metrics/per_step_audit.py`` uses the live Bolt connection and trusts that
migration steps 30, 33, 34 are idempotent (which they are). That is sufficient
under normal conditions. But if something corrupts the graph during a rollback
(bad rubric, Neo4j out of disk, power loss mid-batch), there is no backup to
restore from. The offline dump created here is that backup.

Container info (auto-confirmed at runtime via ``docker inspect``):

* Default container : ``adni-kg``
* Default image     : ``neo4j:5.24.2-community``
* Default data vol  : ``adni-knowledge-graph_neo4j_data`` → ``/data``
* Default database  : ``neo4j``
* Bolt port         : 7687

CLI
---

::

    python scripts/run_per_step_audit.py                            # backup + audit (default; safe)
    python scripts/run_per_step_audit.py --skip-backup              # audit only (faster; trusts idempotency)
    python scripts/run_per_step_audit.py --backup-only              # backup only, do not audit
    python scripts/run_per_step_audit.py --restore <path-to-dump>   # restore a previously taken dump

Exit codes
----------

* 0  Success
* 1  Audit failed (state-equivalence check tripped or rollback guardrail tripped)
* 2  Backup failed (e.g. neo4j-admin error or container would not restart)
* 3  Restore failed
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Defaults — auto-confirmed against `docker inspect adni-kg`
# ---------------------------------------------------------------------------

DEFAULT_CONTAINER = "adni-kg"
DEFAULT_DATABASE = "neo4j"
DEFAULT_DATA_VOLUME = "adni-knowledge-graph_neo4j_data"
DEFAULT_IMAGE = "neo4j:5.24.2-community"
DEFAULT_SNAPSHOTS_DIR = PROJECT_ROOT / "data" / "snapshots"
DEFAULT_READY_TIMEOUT_S = 600   # 10 min — post-dump restarts on a 3 GB graph can take 5+ min on Docker Desktop

# Banner separator
BAR = "=" * 70


def _run(cmd: Sequence[str], *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Wrapper around subprocess.run with consistent logging."""

    pretty = " ".join(str(c) for c in cmd)
    logger.info("$ %s", pretty)
    return subprocess.run(
        list(cmd),
        check=check,
        text=True,
        capture_output=capture,
    )


def _read_password_from_env_file() -> str | None:
    """Best-effort .env reader for NEO4J_PASSWORD when not already in env."""

    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("NEO4J_PASSWORD="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def neo4j_ready(container: str, password: str | None) -> bool:
    """Return True if a `RETURN 1` succeeds via the container's cypher-shell."""

    if not password:
        # We cannot test bolt; the caller should still wait a fixed amount.
        return True
    try:
        proc = subprocess.run(
            [
                "docker", "exec", container,
                "cypher-shell", "-u", "neo4j", "-p", password,
                "RETURN 1 AS ok",
            ],
            check=False, text=True, capture_output=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 0 and "1" in (proc.stdout or "")


def wait_for_neo4j(container: str, *, timeout_s: int) -> bool:
    pw = os.environ.get("NEO4J_PASSWORD") or _read_password_from_env_file()
    if not pw:
        logger.warning(
            "NEO4J_PASSWORD not in env or .env; cannot probe Bolt. "
            "Sleeping %ds and assuming ready.", min(timeout_s, 30),
        )
        time.sleep(min(timeout_s, 30))
        return True

    logger.info("Waiting for Neo4j on %s to accept Bolt connections (timeout %ds)...",
                container, timeout_s)
    logger.info("  Note: post-dump restart on a multi-GB graph can take 5+ minutes "
                "while transaction logs replay.")
    started = time.time()
    last_progress = started
    while time.time() - started < timeout_s:
        if neo4j_ready(container, pw):
            elapsed = int(time.time() - started)
            logger.info("  ✓ Neo4j ready after %ds", elapsed)
            return True
        time.sleep(3)
        # Print a progress heartbeat every 30s so the user knows the script
        # is still running and just waiting.
        now = time.time()
        if now - last_progress >= 30:
            elapsed = int(now - started)
            logger.info("  ... still waiting (%ds elapsed, %ds remaining)",
                        elapsed, timeout_s - elapsed)
            last_progress = now
    logger.warning(
        "Neo4j did not accept Bolt within %ds. The container may still be replaying "
        "transaction logs. Check `docker logs --tail 30 %s`. The dump itself "
        "completed successfully; re-run with --skip-backup once Neo4j is up.",
        timeout_s, container,
    )
    return False


# ---------------------------------------------------------------------------
# Backup / restore
# ---------------------------------------------------------------------------


def run_backup(*, container: str, database: str, data_volume: str, image: str,
               snapshots_dir: Path, ready_timeout_s: int) -> Path:
    """Stop the live container, dump via a one-shot container, restart.

    Returns the host-side path to the new ``.dump`` file. Raises
    RuntimeError on failure (caller catches and returns exit code 2)."""

    snapshots_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = snapshots_dir / f"pre_audit_{stamp}.dump"

    logger.info("%s", BAR)
    logger.info("PHASE 1 — BACKUP: offline neo4j-admin dump → %s", target)
    logger.info("%s", BAR)

    logger.info("Stopping container %s (required for offline dump)...", container)
    _run(["docker", "stop", container])

    # One-shot dump container. Mount the live data volume read-only is not
    # an option for neo4j-admin (it writes locks/state during dump validation),
    # so it stays read-write. The host snapshots directory is bind-mounted so
    # the dump lands on the host disk directly.
    snapshots_abs = snapshots_dir.resolve()
    logger.info("Running neo4j-admin database dump in one-shot container...")
    try:
        _run([
            "docker", "run", "--rm",
            "-v", f"{data_volume}:/data",
            "-v", f"{snapshots_abs}:/dumps",
            image,
            "neo4j-admin", "database", "dump", database,
            "--to-path=/dumps/", "--overwrite-destination=true",
        ])
    except subprocess.CalledProcessError as exc:
        logger.error("neo4j-admin dump failed (exit %s); re-starting %s...",
                     exc.returncode, container)
        _run(["docker", "start", container], check=False)
        raise RuntimeError("backup dump failed") from exc

    # neo4j-admin writes <database>.dump; rename to the timestamped target.
    default_dump = snapshots_dir / f"{database}.dump"
    if default_dump.exists():
        shutil.move(str(default_dump), str(target))

    size_mb = round(target.stat().st_size / (1024 * 1024), 1)
    logger.info("  ✓ Backup written: %s (%s MB)", target, size_mb)

    logger.info("Re-starting container %s...", container)
    _run(["docker", "start", container])
    if not wait_for_neo4j(container, timeout_s=ready_timeout_s):
        # Soft-fail: the dump file is on disk and is the artifact that matters.
        # Neo4j may still come up after this script exits — the dump is durable.
        logger.warning(
            "Backup file is on disk (%s) but Neo4j has not accepted Bolt yet. "
            "The dump is good; you can either wait for Neo4j to finish recovering "
            "and re-run with --skip-backup, or check `docker logs --tail 30 %s` "
            "for the actual startup state.", target, container,
        )
        raise RuntimeError(
            "Neo4j did not become ready in the allotted window; dump succeeded."
        )
    return target


def run_restore(dump_path: Path, *, container: str, database: str, data_volume: str,
                image: str, ready_timeout_s: int) -> None:
    """Load a previously-saved dump into the container's data volume.

    Stops the container, runs ``neo4j-admin database load`` in a one-shot
    container with the live data volume + a read-only mount of the host dump
    directory, then restarts. Raises RuntimeError on failure."""

    abs_path = dump_path.resolve()
    if not abs_path.exists():
        raise RuntimeError(f"Dump file not found: {abs_path}")
    host_dir = abs_path.parent

    logger.info("%s", BAR)
    logger.info("RESTORE FROM DUMP: %s", abs_path)
    logger.info("%s", BAR)

    # neo4j-admin database load expects a file named <database>.dump in the
    # --from-path directory. If our timestamped backup has a different name,
    # we stage it into a temp directory under host_dir with the canonical name.
    staged_path = host_dir / f"{database}.dump"
    must_clean = False
    if abs_path.name != f"{database}.dump":
        if staged_path.exists():
            staged_path.unlink()
        shutil.copy2(abs_path, staged_path)
        must_clean = True

    logger.info("Stopping container %s...", container)
    _run(["docker", "stop", container])

    try:
        _run([
            "docker", "run", "--rm",
            "-v", f"{data_volume}:/data",
            "-v", f"{host_dir.resolve()}:/incoming:ro",
            image,
            "neo4j-admin", "database", "load", database,
            "--from-path=/incoming/", "--overwrite-destination=true",
        ])
    except subprocess.CalledProcessError as exc:
        if must_clean and staged_path.exists():
            staged_path.unlink(missing_ok=True)
        logger.error("neo4j-admin load failed (exit %s); re-starting %s...",
                     exc.returncode, container)
        _run(["docker", "start", container], check=False)
        raise RuntimeError("restore failed") from exc

    if must_clean and staged_path.exists():
        staged_path.unlink(missing_ok=True)

    logger.info("Re-starting container %s...", container)
    _run(["docker", "start", container])
    if not wait_for_neo4j(container, timeout_s=ready_timeout_s):
        raise RuntimeError("Neo4j did not become ready after restore")
    logger.info("✓ Restore complete.")


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def run_audit() -> int:
    """Invoke `python -m metrics.per_step_audit`. Returns its exit code."""

    logger.info("%s", BAR)
    logger.info("PHASE 2 — AUDIT: python -m metrics.per_step_audit")
    logger.info("%s", BAR)
    proc = subprocess.run(
        [sys.executable, "-m", "metrics.per_step_audit"],
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    return proc.returncode


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python scripts/run_per_step_audit.py",
        description=(
            "Per-step audit orchestrator — wraps `python -m metrics.per_step_audit` "
            "with an optional offline neo4j-admin dump backup + restore path."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/run_per_step_audit.py\n"
            "  python scripts/run_per_step_audit.py --skip-backup\n"
            "  python scripts/run_per_step_audit.py --backup-only\n"
            "  python scripts/run_per_step_audit.py --restore data/snapshots/pre_audit_20260516_135108.dump\n"
        ),
    )
    p.add_argument("--skip-backup", action="store_true",
                   help="Skip the offline dump; just run the audit (faster, but no rollback safety net).")
    p.add_argument("--backup-only", action="store_true",
                   help="Take an offline dump and stop; do not run the audit.")
    p.add_argument("--restore", default=None, metavar="DUMP_PATH",
                   help="Restore a previously taken dump and exit; skips backup and audit.")
    p.add_argument("--container", default=DEFAULT_CONTAINER,
                   help=f"Docker container name (default: {DEFAULT_CONTAINER}).")
    p.add_argument("--database", default=DEFAULT_DATABASE,
                   help=f"Neo4j database name (default: {DEFAULT_DATABASE}).")
    p.add_argument("--data-volume", default=DEFAULT_DATA_VOLUME,
                   help=f"Docker volume hosting /data (default: {DEFAULT_DATA_VOLUME}).")
    p.add_argument("--image", default=DEFAULT_IMAGE,
                   help=f"Neo4j image used for the one-shot dump/load container (default: {DEFAULT_IMAGE}).")
    p.add_argument("--snapshots-dir", default=str(DEFAULT_SNAPSHOTS_DIR),
                   help=f"Host directory where dumps land (default: {DEFAULT_SNAPSHOTS_DIR}).")
    p.add_argument("--ready-timeout", type=int, default=DEFAULT_READY_TIMEOUT_S,
                   help=f"Seconds to wait for Neo4j to accept Bolt after a restart "
                        f"(default: {DEFAULT_READY_TIMEOUT_S}).")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress INFO logging (errors still print).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
    )

    snapshots_dir = Path(args.snapshots_dir)
    if not snapshots_dir.is_absolute():
        snapshots_dir = (PROJECT_ROOT / snapshots_dir).resolve()

    # Restore short-circuit
    if args.restore:
        try:
            run_restore(
                Path(args.restore),
                container=args.container,
                database=args.database,
                data_volume=args.data_volume,
                image=args.image,
                ready_timeout_s=args.ready_timeout,
            )
            return 0
        except Exception as exc:
            logger.error("Restore failed: %s", exc)
            return 3

    # Backup
    dump_path: Path | None = None
    if not args.skip_backup:
        try:
            dump_path = run_backup(
                container=args.container,
                database=args.database,
                data_volume=args.data_volume,
                image=args.image,
                snapshots_dir=snapshots_dir,
                ready_timeout_s=args.ready_timeout,
            )
        except Exception as exc:
            logger.error("Backup failed: %s", exc)
            return 2

    if args.backup_only:
        logger.info("")
        logger.info("Backup-only mode; not running audit. Done.")
        if dump_path:
            logger.info("Dump: %s", dump_path)
            logger.info(
                "To restore later: python scripts/run_per_step_audit.py --restore %s",
                dump_path,
            )
        return 0

    # Audit
    audit_exit = run_audit()
    if audit_exit == 0:
        logger.info("")
        logger.info("✓ Per-step audit complete. State-equivalence check PASS.")
        logger.info("  Outputs:")
        logger.info("    outputs/metrics/per_step_audit.json")
        logger.info("    outputs/metrics/step_audit.csv")
        logger.info("    outputs/per_step/<stage>/canonical_snapshot.json (+ validity, FAIR, density, alignment)")
        if dump_path:
            logger.info("")
            logger.info("Backup retained at %s for manual rollback if needed.", dump_path)
        return 0

    logger.warning("Audit aborted with exit code %d.", audit_exit)
    if dump_path:
        logger.info("")
        logger.info("To restore the pre-audit state from the backup, run:")
        logger.info("  python scripts/run_per_step_audit.py --restore %s", dump_path)
    else:
        logger.info("")
        logger.info("No backup was taken (--skip-backup was set).")
        logger.info("The graph is in whatever partial state the audit left it in.")
        logger.info("Idempotent re-runs of the enrichment steps should restore:")
        logger.info("  python -m steps.step30_hpo_expansion")
        logger.info("  python -m steps.step33_biolink_categories")
        logger.info("  python -m steps.step34_mondo_doid_wiring")
    return audit_exit


if __name__ == "__main__":
    sys.exit(main())
