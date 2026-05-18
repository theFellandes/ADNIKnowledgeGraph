"""Tests for metrics.alzkb_alignment."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from metrics.alzkb_alignment import (  # noqa: E402
    IN_SCOPE_CATEGORIES,
    OUT_OF_SCOPE_CATEGORIES,
    AlignmentReport,
    CategoryResult,
    CategorySpec,
    compute_alignment,
    diff,
    write_json,
)


# ---------------------------------------------------------------------------
# Fake connector that maps (source_ontology, query-kind) → canned rows
# ---------------------------------------------------------------------------


class FakeConnector:
    def __init__(
        self,
        *,
        alzkb_total=10,
        same_as_total=8,
        per_ontology=None,    # {source_ontology: (total, strong)} for OntologyConcept-routed categories
        gene_total=0,         # Step 35 — number of :Gene nodes on the MAKO side
        gene_strong=0,        # Step 35 — AlzKBConcept(Gene)→:Gene SAME_AS count
    ):
        self.alzkb_total = alzkb_total
        self.same_as_total = same_as_total
        self.per_ontology = per_ontology or {}
        self.gene_total = gene_total
        self.gene_strong = gene_strong
        self.calls = []

    def run_query(self, query, parameters=None):
        parameters = parameters or {}
        self.calls.append((query, parameters))
        if "MATCH (a:AlzKBConcept) RETURN count(a)" in query:
            return [{"n": self.alzkb_total}]
        if "MATCH ()-[r:SAME_AS]->() RETURN count(r)" in query:
            return [{"n": self.same_as_total}]
        # Gene-specific queries (Step 35)
        if "MATCH (g:Gene) RETURN count(DISTINCT g) AS total" in query:
            return [{"total": self.gene_total}]
        if "MATCH (a:AlzKBConcept)-[:SAME_AS]->(g:Gene)" in query:
            return [{"strong": self.gene_strong}]
        # Ontology-concept-routed queries (Disease, Anatomy, Phenotype)
        if "RETURN count(DISTINCT o) AS total" in query:
            ont = parameters.get("source_ontology", "")
            total, _ = self.per_ontology.get(ont, (0, 0))
            return [{"total": total}]
        if "RETURN count(DISTINCT o) AS strong" in query:
            ont = parameters.get("source_ontology", "")
            _, strong = self.per_ontology.get(ont, (0, 0))
            return [{"strong": strong}]
        raise AssertionError(f"Unhandled query: {query!r}")


# ---------------------------------------------------------------------------
# Smoke tests on the dataclasses
# ---------------------------------------------------------------------------


def test_category_result_to_dict():
    c = CategoryResult(name="Disease", total=10, strong_matches=8, match_rate=0.8)
    d = c.to_dict()
    assert d["name"] == "Disease"
    assert d["match_rate"] == 0.8
    assert d["not_implemented"] is False


def test_in_scope_categories_have_alzkb_source_types():
    # Every in-scope category must declare at least one AlzKB source_type
    # to match against. The cauad_source_ontology may be None for entities
    # routed via a dedicated node label (e.g. Gene → :Gene).
    for spec in IN_SCOPE_CATEGORIES:
        assert spec.alzkb_source_types, f"{spec.name} has no alzkb_source_types"


def test_gene_moved_in_scope_via_step35():
    # Step 35 (Gene Ontology integration) moved Gene from OUT_OF_SCOPE to
    # IN_SCOPE. The category uses :Gene as the MAKO-side anchor, not an
    # OntologyConcept, so cauad_source_ontology is None for Gene.
    by_name = {c.name: c for c in IN_SCOPE_CATEGORIES}
    assert "Gene" in by_name
    assert by_name["Gene"].cauad_source_ontology is None
    assert "Gene" in by_name["Gene"].alzkb_source_types
    # And the OUT_OF_SCOPE bucket should now be empty (or at least not
    # contain Gene).
    assert "Gene" not in {c.name for c in OUT_OF_SCOPE_CATEGORIES}


# ---------------------------------------------------------------------------
# compute_alignment
# ---------------------------------------------------------------------------


def test_alignment_full_match():
    # Default fake has no :Gene nodes (gene_total=0), so the Gene category
    # falls back to not_implemented=True — mirroring the pre-Step-35 state.
    fake = FakeConnector(
        alzkb_total=20,
        same_as_total=15,
        per_ontology={
            "SNOMED-CT": (5, 5),  # all 5 diseases matched
            "UBERON": (4, 4),     # all 4 anatomy matched
            "HPO": (3, 3),        # all 3 phenotypes matched
        },
    )
    report = compute_alignment(fake, graph_uri="test://mini")
    by = {c.name: c for c in report.categories}

    assert by["Disease"].match_rate == pytest.approx(1.0)
    assert by["Anatomy"].match_rate == pytest.approx(1.0)
    assert by["Phenotype"].match_rate == pytest.approx(1.0)
    # Gene falls back to not_implemented because gene_total=0 (no Step 35
    # data yet in this fake).
    assert by["Gene"].not_implemented is True
    assert by["Gene"].strong_matches == 0
    # 3 of 4 in-scope categories have strong matches; Gene is N/A in the fake.
    assert report.in_scope_strong_count == 3
    assert report.in_scope_total_count == 3  # only the implemented ones


def test_alignment_with_gene_via_step35():
    """When Step 35 has run, :Gene nodes exist and the Gene category
    reports a real match rate instead of not_implemented."""

    fake = FakeConnector(
        alzkb_total=20,
        same_as_total=15,
        per_ontology={
            "SNOMED-CT": (5, 5),
            "UBERON": (4, 4),
            "HPO": (3, 3),
        },
        gene_total=5,    # Step 35 created 5 Gene nodes
        gene_strong=5,   # All 5 matched to AlzKB Gene entries
    )
    report = compute_alignment(fake)
    by = {c.name: c for c in report.categories}
    assert by["Gene"].not_implemented is False
    assert by["Gene"].total == 5
    assert by["Gene"].strong_matches == 5
    assert by["Gene"].match_rate == pytest.approx(1.0)
    # All 4 in-scope categories now have strong matches.
    assert report.in_scope_strong_count == 4
    assert report.in_scope_total_count == 4


def test_alignment_partial_match():
    fake = FakeConnector(
        per_ontology={
            "SNOMED-CT": (10, 6),
            "UBERON": (10, 10),
            "HPO": (10, 0),
        }
    )
    report = compute_alignment(fake)
    by = {c.name: c for c in report.categories}
    assert by["Disease"].match_rate == pytest.approx(0.6)
    assert by["Anatomy"].match_rate == pytest.approx(1.0)
    assert by["Phenotype"].match_rate == pytest.approx(0.0)
    assert by["Phenotype"].strong_matches == 0


def test_alignment_no_concepts_yields_zero_rates():
    fake = FakeConnector(per_ontology={})
    report = compute_alignment(fake)
    by = {c.name: c for c in report.categories}
    assert all(by[name].total == 0 for name in ("Disease", "Anatomy", "Phenotype"))
    assert all(by[name].match_rate == 0.0 for name in ("Disease", "Anatomy", "Phenotype"))
    assert by["Gene"].not_implemented is True


def test_alignment_report_includes_global_counts():
    fake = FakeConnector(alzkb_total=42, same_as_total=37)
    report = compute_alignment(fake)
    assert report.alzkb_concept_total == 42
    assert report.same_as_edge_total == 37


def test_to_dict_shape():
    fake = FakeConnector(per_ontology={"SNOMED-CT": (5, 5), "UBERON": (4, 4), "HPO": (3, 2)})
    report = compute_alignment(fake)
    d = report.to_dict()
    assert d["schema_version"] == 1
    assert isinstance(d["categories"], list)
    names = [c["name"] for c in d["categories"]]
    assert names == ["Disease", "Anatomy", "Phenotype", "Gene"]


def test_write_json_round_trip(tmp_path):
    fake = FakeConnector(per_ontology={"SNOMED-CT": (5, 5)})
    report = compute_alignment(fake)
    path = tmp_path / "alignment.json"
    write_json(report, path)
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["categories"][0]["name"] == "Disease"


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


def test_diff_post_better_than_baseline():
    baseline = compute_alignment(
        FakeConnector(per_ontology={"SNOMED-CT": (10, 0), "UBERON": (4, 4), "HPO": (3, 0)})
    )
    post = compute_alignment(
        FakeConnector(per_ontology={"SNOMED-CT": (10, 9), "UBERON": (4, 4), "HPO": (3, 3)})
    )
    d = diff(baseline, post)
    by = {row["name"]: row for row in d["per_category"]}
    assert by["Disease"]["delta_strong_matches"] == 9
    assert by["Phenotype"]["delta_strong_matches"] == 3
    assert by["Anatomy"]["delta_strong_matches"] == 0
    assert d["in_scope_strong_count_baseline"] == 1   # only Anatomy strong before
    assert d["in_scope_strong_count_post"] == 3       # all three strong after


def test_diff_handles_missing_categories_in_one_side():
    """A baseline / post mismatch (e.g., new category added later) shouldn't crash."""

    base = AlignmentReport(
        schema_version=1, timestamp="t1", graph_uri="x",
        alzkb_concept_total=0, same_as_edge_total=0,
        categories=[CategoryResult("Disease", 5, 0, 0.0)],
    )
    post = AlignmentReport(
        schema_version=1, timestamp="t2", graph_uri="x",
        alzkb_concept_total=10, same_as_edge_total=8,
        categories=[
            CategoryResult("Disease", 5, 5, 1.0),
            CategoryResult("Anatomy", 4, 4, 1.0),
        ],
    )
    d = diff(base, post)
    by = {row["name"]: row for row in d["per_category"]}
    assert by["Anatomy"]["baseline"] is None
    assert by["Disease"]["delta_match_rate"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Custom category specs (extension hook)
# ---------------------------------------------------------------------------


def test_compute_alignment_accepts_custom_specs():
    custom = (
        CategorySpec(name="Drug", cauad_source_ontology="ATC",
                     alzkb_source_types=("Drug",), note="custom"),
    )
    fake = FakeConnector(per_ontology={"ATC": (2, 1)})
    report = compute_alignment(fake, in_scope=custom, out_of_scope=())
    assert [c.name for c in report.categories] == ["Drug"]
    assert report.categories[0].match_rate == pytest.approx(0.5)
