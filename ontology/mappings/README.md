# Column-to-Concept Mappings

> Reproducibility artefact for **Step C** of the C7 paper (column-to-concept
> mapping). Every CSV here is a deterministic mapping rule: given a source
> column value, the rule produces an ontology concept (URI + label) attached
> via `MAPS_TO` / `CLASSIFIED_AS`.
>
> Source of truth in code: `steps/step18_add_ontology_properties.py` and
> `steps/step20_ontology_layer.py`. These CSVs **mirror** the dictionaries in
> those scripts. Drift is caught by `tests/test_column_to_concept.py`.

## Files

| File | Source | Target ontology | Used by |
|---|---|---|---|
| [diagnosis_to_snomed_icd10.csv](diagnosis_to_snomed_icd10.csv) | `:Diagnosis` (DXSUM, ARM) | SNOMED-CT, ICD-10, MONDO | step 18 `_enrich_diagnosis_nodes` |
| [cognitive_to_loinc.csv](cognitive_to_loinc.csv) | `:CognitiveAssessment` | LOINC | step 18 `_enrich_cognitive_assessments` |
| [biomarker_to_loinc.csv](biomarker_to_loinc.csv) | `:Biomarker` (CSF) | LOINC | step 18 `_enrich_biomarkers` |
| [brain_region_to_uberon.csv](brain_region_to_uberon.csv) | `:BrainRegion` | UBERON | step 18 `_enrich_brain_regions` |
| [relationship_to_ro_uri.csv](relationship_to_ro_uri.csv) | every relationship type | OBO Relation Ontology, SKOS, RDFS | step 18 `_enrich_relationships` |
| [index.csv](index.csv) | All of the above, consolidated | mixed | paper supplementary material |

## Schema

Every per-source CSV has these columns:

| Column | Description |
|---|---|
| `source_table` | ADNI raw CSV table name (`DXSUM`, `MEDHIST`, ...) or `_synthetic` for derived nodes |
| `source_column` | Column name in that table, or `_node_property` for derived |
| `source_value_pattern` | Exact value (or regex if rule-based) that triggers the mapping |
| `target_ontology` | One of: `SNOMED-CT`, `LOINC`, `UBERON`, `HPO`, `ICD-10`, `MONDO`, `RO`, `SKOS`, `RDFS`, `OWL`, `NCIt` |
| `target_uri` | Full or prefixed concept URI (e.g. `snomed:26929004`, `loinc:72106-8`) |
| `target_label` | Human-readable concept label |
| `mapping_rule` | `exact_match`, `case_insensitive`, `regex`, `derived_from_property` |
| `test_fixture_id` | Reference to a row in `tests/fixtures/mini_kg.cypher` that exercises this mapping |
| `last_verified_date` | YYYY-MM-DD when the mapping was last cross-checked against the source ontology |

The `index.csv` adds a `source_csv` column pointing back to the per-source file.

## Adding a new mapping

1. Add the row to the appropriate per-source CSV.
2. Add a fixture row to `tests/fixtures/mini_kg.cypher` using the same `target_uri`.
3. Update `tests/test_column_to_concept.py` if the rule type is new (regex, conditional).
4. Re-run `python -m metrics --validity` to confirm the rubric still passes.
5. Re-generate `index.csv` (a small helper script can be authored under R1.4).

## Out of scope (documented in the paper as known limitations)

- `ADSXLIST` (30 binary symptom flags) → HPO. Conceptual mapping exists in the
  paper but is not yet implemented in step 18; the corresponding CSV is not
  present here. Future work post-thesis-defense.
- `MEDHIST` (medical history flags) → SNOMED-CT category-level mappings.
  Same status — paper cites it; CSV not yet authored.
- `VITALS` (BP, weight, etc.) → LOINC. Same status.

When those are implemented, the new CSVs slot into this directory with the
same schema.
