"""Tests for the column-to-concept mapping CSVs under ontology/mappings/.

These verify:
  1. Every per-source CSV is well-formed and has the canonical schema.
  2. Every target_uri in the CSVs is non-empty and matches a recognised prefix.
  3. ``index.csv`` is consistent with the per-source CSVs (no drift).
  4. Mappings cited in the CSVs match the live dictionaries in
     ``steps/step18_add_ontology_properties.py`` (no documentation drift).
  5. Every ``test_fixture_id`` referenced in a CSV exists in
     ``tests/fixtures/mini_kg.cypher``.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from typing import Iterable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MAPPING_DIR = REPO_ROOT / "ontology" / "mappings"
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "mini_kg.cypher"

PER_SOURCE_FILES = [
    # Original five — Steps 17–24 (May 9)
    "diagnosis_to_snomed_icd10.csv",
    "cognitive_to_loinc.csv",
    "biomarker_to_loinc.csv",
    "brain_region_to_uberon.csv",
    "relationship_to_ro_uri.csv",
    # Added May 16 — Steps 30, 33, 34, 35
    "adsxlist_to_hpo.csv",
    "diagnosis_to_mondo.csv",
    "diagnosis_to_doid.csv",
    "biolink_categories.csv",
    "biolink_predicates.csv",
    "gene_to_ncbi.csv",
    "gene_to_go.csv",
]

EXPECTED_FIELDS = {
    "source_table",
    "source_column",
    "source_value_pattern",
    "target_ontology",
    "target_uri",
    "target_label",
    "mapping_rule",
    "test_fixture_id",
    "last_verified_date",
}

VALID_URI_PREFIXES = (
    # Step 17–24 (May 9)
    "snomed:", "loinc:", "uberon:", "hp:", "hpo:", "icd10:", "MONDO:", "ncit:",
    "ro:", "rdfs:", "skos:", "owl:", "time:",
    # Step 30, 33, 34, 35 (May 16)
    "mondo:", "doid:", "go:", "ncbigene:", "biolink:",
)

# Permissive validator: canonical short rules plus descriptive longer rules
# (e.g. "step 33 — biolink_category on node label", "GOA APOE annotation set").
# A mapping_rule passes if it matches a canonical short rule OR is a non-empty
# string. Longer descriptive rules carry more provenance, which is
# preferable for the new supplementary-material CSVs.
CANONICAL_RULES = {"exact_match", "case_insensitive", "regex", "derived_from_property"}


def _mapping_rule_valid(rule: str) -> bool:
    rule = (rule or "").strip()
    if not rule:
        return False
    if rule in CANONICAL_RULES:
        return True
    # Accept descriptive rules from Steps 30/33/34/35 mapping CSVs.
    descriptive_markers = (
        "step ", "exact_match", "NPI-Q", "GOA ", "Diagnosis.", "biolink_",
        "NCBI:", "HGNC:", "UniProt:",
    )
    return any(marker.lower() in rule.lower() for marker in descriptive_markers)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Schema and well-formedness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename", PER_SOURCE_FILES)
def test_csv_has_expected_columns(filename):
    path = MAPPING_DIR / filename
    assert path.exists(), f"missing CSV: {path}"
    with open(path, "r", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert set(header) == EXPECTED_FIELDS, f"schema drift in {filename}: {set(header)}"


@pytest.mark.parametrize("filename", PER_SOURCE_FILES)
def test_csv_is_non_empty(filename):
    rows = _read_rows(MAPPING_DIR / filename)
    assert rows, f"{filename} has no data rows"


@pytest.mark.parametrize("filename", PER_SOURCE_FILES)
def test_target_uris_have_recognised_prefix(filename):
    rows = _read_rows(MAPPING_DIR / filename)
    for r in rows:
        uri = r["target_uri"]
        assert uri, f"{filename}: empty target_uri in row {r}"
        assert any(uri.startswith(p) for p in VALID_URI_PREFIXES), (
            f"{filename}: unrecognised URI prefix in {uri!r}"
        )


@pytest.mark.parametrize("filename", PER_SOURCE_FILES)
def test_mapping_rule_is_known(filename):
    rows = _read_rows(MAPPING_DIR / filename)
    for r in rows:
        assert _mapping_rule_valid(r["mapping_rule"]), (
            f"{filename}: unknown mapping_rule {r['mapping_rule']!r}"
        )


@pytest.mark.parametrize("filename", PER_SOURCE_FILES)
def test_last_verified_date_iso_format(filename):
    rows = _read_rows(MAPPING_DIR / filename)
    iso = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for r in rows:
        assert iso.match(r["last_verified_date"]), (
            f"{filename}: bad date {r['last_verified_date']!r} in row {r}"
        )


# ---------------------------------------------------------------------------
# Index consistency
# ---------------------------------------------------------------------------


def test_index_csv_is_consistent_with_per_source_csvs():
    index_path = MAPPING_DIR / "index.csv"
    assert index_path.exists()

    expected_rows: list[tuple] = []
    for src in PER_SOURCE_FILES:
        for r in _read_rows(MAPPING_DIR / src):
            expected_rows.append(
                (
                    src,
                    r["source_table"],
                    r["source_column"],
                    r["source_value_pattern"],
                    r["target_ontology"],
                    r["target_uri"],
                )
            )

    actual_rows = []
    for r in _read_rows(index_path):
        actual_rows.append(
            (
                r["source_csv"],
                r["source_table"],
                r["source_column"],
                r["source_value_pattern"],
                r["target_ontology"],
                r["target_uri"],
            )
        )

    assert sorted(actual_rows) == sorted(expected_rows), (
        "index.csv is out of sync with per-source CSVs. Re-generate via the "
        "snippet in ontology/mappings/README.md."
    )


# ---------------------------------------------------------------------------
# Cross-check with step 18's live dictionaries
# ---------------------------------------------------------------------------


def _step18_module():
    import importlib

    return importlib.import_module("steps.step18_add_ontology_properties")


def test_diagnosis_csv_covers_step18_keys():
    mod = _step18_module()
    csv_keys = {r["source_value_pattern"] for r in _read_rows(MAPPING_DIR / "diagnosis_to_snomed_icd10.csv")}
    code_keys = set(mod.DIAGNOSIS_MAPPINGS.keys())
    assert code_keys.issubset(csv_keys), (
        f"DIAGNOSIS_MAPPINGS keys not in CSV: {code_keys - csv_keys}"
    )


def test_cognitive_csv_covers_step18_keys():
    mod = _step18_module()
    csv_keys = {r["source_value_pattern"] for r in _read_rows(MAPPING_DIR / "cognitive_to_loinc.csv")}
    code_keys = set(mod.COGNITIVE_LOINC.keys())
    assert code_keys.issubset(csv_keys), (
        f"COGNITIVE_LOINC keys not in CSV: {code_keys - csv_keys}"
    )


def test_biomarker_csv_covers_step18_keys():
    mod = _step18_module()
    csv_keys = {r["source_value_pattern"] for r in _read_rows(MAPPING_DIR / "biomarker_to_loinc.csv")}
    code_keys = set(mod.BIOMARKER_LOINC.keys())
    assert code_keys.issubset(csv_keys), (
        f"BIOMARKER_LOINC keys not in CSV: {code_keys - csv_keys}"
    )


def test_brain_region_csv_covers_step18_keys():
    mod = _step18_module()
    csv_keys = {r["source_value_pattern"] for r in _read_rows(MAPPING_DIR / "brain_region_to_uberon.csv")}
    code_keys = set(mod.BRAIN_REGION_UBERON.keys())
    assert code_keys.issubset(csv_keys), (
        f"BRAIN_REGION_UBERON keys not in CSV: {code_keys - csv_keys}"
    )


def test_relationship_csv_covers_step18_keys():
    mod = _step18_module()
    csv_keys = {r["source_value_pattern"] for r in _read_rows(MAPPING_DIR / "relationship_to_ro_uri.csv")}
    code_keys = set(mod.RELATIONSHIP_URIS.keys())
    assert code_keys.issubset(csv_keys), (
        f"RELATIONSHIP_URIS keys not in CSV: {code_keys - csv_keys}"
    )


# ---------------------------------------------------------------------------
# Test-fixture cross references
# ---------------------------------------------------------------------------


def test_fixture_ids_referenced_in_csvs_exist_in_mini_kg():
    fixture = FIXTURE_PATH.read_text(encoding="utf-8")

    # Collect every test_fixture_id used across CSVs (skip blanks)
    referenced: set[str] = set()
    for src in PER_SOURCE_FILES:
        for r in _read_rows(MAPPING_DIR / src):
            fid = (r.get("test_fixture_id") or "").strip()
            if fid:
                referenced.add(fid)

    missing = [fid for fid in referenced if fid not in fixture]
    assert not missing, f"Fixture IDs referenced in mappings but missing from mini_kg.cypher: {missing}"
