"""B-12 — regression tests for step24's _resolve_neo4j_creds.

Locks down the contract that ``execute_alzkb_bridge`` accepts both:
  - flat config (env_loader shape: ``neo4j_uri`` / ``neo4j_user`` / ``neo4j_password``)
  - nested config (legacy shape: ``config['neo4j']['uri']`` etc.)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from steps.step24_alzkb_bridge import _resolve_neo4j_creds  # noqa: E402


def test_flat_config_shape():
    cfg = {
        "neo4j_uri": "bolt://localhost:7687",
        "neo4j_user": "neo4j",
        "neo4j_password": "secret",
    }
    uri, user, password = _resolve_neo4j_creds(cfg)
    assert (uri, user, password) == ("bolt://localhost:7687", "neo4j", "secret")


def test_nested_config_shape():
    cfg = {
        "neo4j": {
            "uri": "bolt://other:7687",
            "user": "admin",
            "password": "shh",
        }
    }
    uri, user, password = _resolve_neo4j_creds(cfg)
    assert (uri, user, password) == ("bolt://other:7687", "admin", "shh")


def test_nested_takes_precedence_over_flat():
    """If both shapes are present (e.g. a CLI overlay) the nested wins —
    that matches what the original buggy code did, so behaviour is stable."""
    cfg = {
        "neo4j": {"uri": "bolt://nested:7687", "user": "admin", "password": "nested"},
        "neo4j_uri": "bolt://flat:7687",
        "neo4j_user": "flat-user",
        "neo4j_password": "flat",
    }
    uri, user, password = _resolve_neo4j_creds(cfg)
    assert uri == "bolt://nested:7687"
    assert user == "admin"
    assert password == "nested"


def test_missing_password_raises():
    cfg = {"neo4j_uri": "bolt://localhost:7687", "neo4j_user": "neo4j"}
    with pytest.raises(RuntimeError, match="password missing"):
        _resolve_neo4j_creds(cfg)


def test_defaults_when_uri_user_missing():
    cfg = {"neo4j_password": "secret"}
    uri, user, password = _resolve_neo4j_creds(cfg)
    assert uri == "bolt://localhost:7687"
    assert user == "neo4j"
    assert password == "secret"
