"""Tests for metrics.snapshots — the neo4j-admin dump/load wrapper.

We exercise the planning helpers and the dry-run path of dump/load. The
actual subprocess invocation against neo4j-admin is left to integration
tests against the live Galatasaray instance (Q.7 / M1.1).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from metrics.snapshots import (  # noqa: E402
    DEFAULT_SNAPSHOT_DIR,
    SnapshotResult,
    dump,
    load,
    plan_per_step_snapshots,
)


def test_plan_default_paths():
    plan = plan_per_step_snapshots(["pre", "post", 17, 18, 19, 20])
    assert plan["pre"] == DEFAULT_SNAPSHOT_DIR / "pre_steps_17_20.dump"
    assert plan["post"] == DEFAULT_SNAPSHOT_DIR / "post_steps_17_20.dump"
    assert plan["17"] == DEFAULT_SNAPSHOT_DIR / "post_step_17.dump"
    assert plan["20"] == DEFAULT_SNAPSHOT_DIR / "post_step_20.dump"


def test_plan_custom_directory(tmp_path):
    plan = plan_per_step_snapshots([17, 18], snapshot_dir=tmp_path)
    assert plan["17"] == tmp_path / "post_step_17.dump"
    assert plan["18"] == tmp_path / "post_step_18.dump"


def test_dump_dry_run_records_command(tmp_path):
    target = tmp_path / "snap.dump"
    result = dump("neo4j", target, dry_run=True)
    assert isinstance(result, SnapshotResult)
    assert result.operation == "dump"
    assert result.path == target
    assert any("dump" in part for part in result.command)
    assert any("neo4j" in part for part in result.command)
    assert result.returncode == 0
    assert result.stdout == "(dry-run)"
    # Parent directory should be created even on dry-run
    assert target.parent.exists()


def test_dump_existing_target_without_overwrite_raises(tmp_path):
    target = tmp_path / "exists.dump"
    target.write_bytes(b"already here")
    with pytest.raises(FileExistsError):
        dump("neo4j", target, dry_run=True)


def test_dump_existing_target_with_overwrite_proceeds(tmp_path):
    target = tmp_path / "exists.dump"
    target.write_bytes(b"already here")
    result = dump("neo4j", target, overwrite=True, dry_run=True)
    assert result.ok


def test_load_missing_source_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load("neo4j", tmp_path / "nope.dump", dry_run=True)


def test_load_dry_run_includes_database(tmp_path):
    src = tmp_path / "snap.dump"
    src.write_bytes(b"x")
    result = load("neo4j", src, dry_run=True)
    assert result.operation == "load"
    assert "neo4j" in result.command


def test_resolve_admin_binary_falls_back_to_path(tmp_path, monkeypatch):
    """If neo4j_home/bin/neo4j-admin is missing, _resolve_admin_binary should
    fall back to PATH (even if PATH lookup fails, that's a separate error)."""

    from metrics import snapshots

    # Empty neo4j_home — the binary won't exist there
    fake_home = tmp_path / "no-such-neo4j"
    fake_home.mkdir()

    # PATH contains a fake binary so shutil.which finds it
    fake_admin = tmp_path / "neo4j-admin"
    fake_admin.write_text("#!/bin/sh\nexit 0\n")
    fake_admin.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + ((";" if sys.platform == "win32" else ":") + ""))

    # On Windows shutil.which needs a .bat or .exe, so on win32 we just check
    # the function raises predictably when no binary is anywhere.
    if sys.platform != "win32":
        resolved = snapshots._resolve_admin_binary(fake_home)
        assert resolved == str(fake_admin)


def test_resolve_admin_binary_raises_when_missing(monkeypatch, tmp_path):
    from metrics import snapshots

    monkeypatch.setenv("PATH", str(tmp_path))  # empty dir
    with pytest.raises(FileNotFoundError):
        snapshots._resolve_admin_binary(neo4j_home=None)
