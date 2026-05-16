"""Tests for metrics.runner.

We exercise the orchestration layer by injecting a FakeConnector and
verifying:
  - selection logic (--all vs individual flags)
  - validity-gate short-circuit
  - --ignore-validity override
  - per-step JSON / Markdown / CSV outputs land in the expected paths
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Re-use the passing handler shapes from each metric's test module.
from tests.test_validity import _passing_handlers as _validity_passing  # noqa: E402
from tests.test_validity import FakeConnector as ValidityFake  # noqa: E402
from tests.test_semantic_density import _density_handlers  # noqa: E402
from tests.test_alzkb_alignment import FakeConnector as AlignmentFake  # noqa: E402

import metrics.runner as runner  # noqa: E402


# ---------------------------------------------------------------------------
# Composite fake — joins the per-metric handlers behind a single connector
# ---------------------------------------------------------------------------


class CompositeFake:
    """Returns rows for any query the runner fires.

    We hand-roll the dispatch instead of layering FakeConnector on top of
    FakeConnector because the runner asks each metric module for *different*
    queries; there's no overlap risk.
    """

    def __init__(self, *, validity_pass: bool = True, alignment_full: bool = True):
        self.uri = "test://composite"
        self.calls: list[tuple[str, dict | None]] = []

        # ---------------------------- validity
        if validity_pass:
            self._validity = ValidityFake(_validity_passing())
        else:
            handlers = _validity_passing()
            handlers = [(p, [{"n": 0}] if p == "SHOW CONSTRAINTS" else r) for p, r in handlers]
            self._validity = ValidityFake(handlers)

        # ---------------------------- density
        from tests.test_semantic_density import FakeConnector as DensityFake

        self._density = DensityFake(_density_handlers())

        # ---------------------------- alzkb alignment
        if alignment_full:
            self._alignment = AlignmentFake(
                alzkb_total=20, same_as_total=15,
                per_ontology={
                    "SNOMED-CT": (5, 5), "UBERON": (4, 4), "HPO": (3, 3)
                },
            )
        else:
            self._alignment = AlignmentFake(
                alzkb_total=0, same_as_total=0, per_ontology={},
            )

    def run_query(self, query: str, parameters=None):
        self.calls.append((query, parameters))

        # ---------------------------- Density (must come before FAIR — its
        # per-label query includes "n.snomed_code IS NOT NULL" which would
        # otherwise be claimed by FAIR's F1 fallback below)
        if "UNWIND labels(n) AS label" in query:
            return self._density.run_query(query, parameters)
        if "WITH type(r) AS rel_type, r" in query:
            return self._density.run_query(query, parameters)
        if query.startswith("MATCH (n) WITH n"):
            return self._density.run_query(query, parameters)
        if query.startswith("MATCH ()-[r]->() RETURN"):
            return self._density.run_query(query, parameters)

        # ---------------------------- Validity
        if any(s in query for s in (
            "SHOW CONSTRAINTS", "SHOW INDEXES",
            "MATCH (n:Diagnosis)", "MATCH (n:CognitiveAssessment)",
            "MATCH (n:Biomarker)", "MATCH (n:BrainRegion)",
        )):
            return self._validity.run_query(query, parameters)
        if "RETURN coalesce(o.source_ontology" in query:
            return self._validity.run_query(query, parameters)
        if any(s in query for s in ("[r:MAPS_TO]", "[r:IS_A]", "[r:CLASSIFIED_AS]")):
            return self._validity.run_query(query, parameters)
        if "WITH type(r) AS rel_type, count(r) AS n," in query:
            return self._validity.run_query(query, parameters)
        if "MATCH (o:OntologyConcept) OPTIONAL MATCH" in query:
            return self._validity.run_query(query, parameters)
        if "MATCH (p:Patient) WHERE p.ptid STARTS WITH" in query:
            return self._validity.run_query(query, parameters)

        # ---------------------------- Alignment
        if "MATCH (a:AlzKBConcept) RETURN count(a)" in query:
            return self._alignment.run_query(query, parameters)
        if "MATCH ()-[r:SAME_AS]->() RETURN count(r)" in query:
            return self._alignment.run_query(query, parameters)
        if "RETURN count(DISTINCT o) AS total" in query:
            return self._alignment.run_query(query, parameters)
        if "RETURN count(DISTINCT o) AS strong" in query:
            return self._alignment.run_query(query, parameters)

        # ---------------------------- FAIR (catch-all for high-coverage answers)
        if "RETURN avg(size(keys(n)))" in query:
            return [{"avg_properties": 9.0}]
        if "SHOW INDEXES" in query:
            return [{"index_count": 20}]
        if any(s in query for s in (
            "n.snomed_code IS NOT NULL", "o.code IS NOT NULL AND o.uri IS NOT NULL",
            "WITH ['SNOMED-CT'", "['MAPS_TO','IS_A','CLASSIFIED_AS','SAME_AS']",
            "BATCH_INGESTED_BY", "n.batch_id IS NOT NULL",
        )):
            return [{"coverage": 1.0}]

        return []


# ---------------------------------------------------------------------------
# Helpers — patch the runner's connector resolution so tests don't hit Neo4j
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_connector(monkeypatch):
    """Patch out _resolve_credentials and Neo4jConnector so no DB is needed."""

    fake = CompositeFake()
    monkeypatch.setattr(runner, "_resolve_credentials", lambda args: ("test://composite", "u", "p"))

    # Replace Neo4jConnector(uri=…, user=…, password=…) with a factory returning our fake.
    import utils.neo4j_connector as nc

    monkeypatch.setattr(nc, "Neo4jConnector", lambda **kwargs: fake)
    return fake


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_selected_all_returns_all_steps():
    args = runner._build_arg_parser().parse_args(["--all"])
    assert runner._selected(args) == ["validity", "density", "fair", "alignment", "step_audit"]


def test_selected_subset():
    args = runner._build_arg_parser().parse_args(["--validity", "--density"])
    assert runner._selected(args) == ["validity", "density"]


def test_no_selection_returns_exit_code_2(tmp_path, capsys):
    code = runner.main(["--output-dir", str(tmp_path)])
    assert code == 2


def test_validity_only_writes_reports(tmp_path, patched_connector):
    code = runner.main(["--validity", "--output-dir", str(tmp_path), "--quiet"])
    assert code == 0
    json_files = list((tmp_path / "validity_reports").glob("kg_validity_*.json"))
    md_files = list((tmp_path / "validity_reports").glob("kg_validity_*.md"))
    assert json_files and md_files


def test_all_selected_writes_each_metric(tmp_path, patched_connector):
    code = runner.main(["--all", "--output-dir", str(tmp_path), "--quiet"])
    assert code == 0
    metrics_dir = tmp_path / "metrics"
    assert (metrics_dir / "semantic_density.json").exists()
    assert (metrics_dir / "fair_score.json").exists()
    assert (metrics_dir / "alzkb_alignment.json").exists()
    assert (metrics_dir / "step_audit.csv").exists()
    assert (metrics_dir / "runner_summary.json").exists()


def test_validity_failure_short_circuits(tmp_path, monkeypatch):
    fake = CompositeFake(validity_pass=False)
    monkeypatch.setattr(runner, "_resolve_credentials", lambda args: ("test://composite", "u", "p"))
    import utils.neo4j_connector as nc

    monkeypatch.setattr(nc, "Neo4jConnector", lambda **kwargs: fake)

    code = runner.main(["--all", "--output-dir", str(tmp_path), "--quiet"])
    assert code == 1
    # Density / FAIR should NOT have run
    assert not (tmp_path / "metrics" / "semantic_density.json").exists()
    assert not (tmp_path / "metrics" / "fair_score.json").exists()


def test_ignore_validity_continues_after_failure(tmp_path, monkeypatch):
    fake = CompositeFake(validity_pass=False)
    monkeypatch.setattr(runner, "_resolve_credentials", lambda args: ("test://composite", "u", "p"))
    import utils.neo4j_connector as nc

    monkeypatch.setattr(nc, "Neo4jConnector", lambda **kwargs: fake)

    code = runner.main(["--all", "--ignore-validity", "--output-dir", str(tmp_path), "--quiet"])
    # Overall status still 1 (validity failed), but other steps ran
    assert code == 1
    assert (tmp_path / "metrics" / "semantic_density.json").exists()


def test_runner_summary_records_outcomes(tmp_path, patched_connector):
    runner.main(["--all", "--output-dir", str(tmp_path), "--quiet"])
    summary = json.loads((tmp_path / "metrics" / "runner_summary.json").read_text(encoding="utf-8"))
    names = [o["name"] for o in summary["outcomes"]]
    assert names == ["validity", "density", "fair", "alignment", "step_audit"]
    assert summary["overall_status"] == 0
