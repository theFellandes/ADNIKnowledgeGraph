# Validity Check Specification — KG Acceptance Gate

> **Owner.** Sultan Nezihe Turhan (acceptance criteria), Oğuzhan Güngör (implementation).
> **Status.** Specification — no code yet. Approval gate Q.6 (rubric thresholds) must pass before implementation.
> **Position in pipeline.** This gate runs **before** any FAIR / semantic density work. On FAIL, downstream tasks short-circuit.

---

## 1. Why this gate exists

Sultan's feedback on the progress report: *"Bu ilerleme raporuna metrikleri koymasan bile hiç olmazsa ontolojileri bitirip graphın KG haline dönüşmüş halini koymak lazım"* — even if the progress report does not include the metrics, the ontologies must be finished and the KG-converted state of the graph must be presented. This spec turns that requirement into a deterministic, reproducible check with seven assertions and machine-readable output.

If the gate passes, two artefacts go into the next progress report:
- `outputs/validity_reports/kg_validity_<timestamp>.md` — the human-readable summary.
- A reference to the underlying `kg_validity_<timestamp>.json` — for reviewers who want the raw counts.

If the gate fails, the offending assertions print at the top of the report and the metric pipeline does not run.

---

## 2. The seven assertions

The full list. Each assertion has a precise Cypher (or runtime) check, a default threshold, and a hard-fail condition. Threshold-based scoring per the user decision; defaults are configurable via `metrics/validity_rubric.yaml` (Q.6 confirms the numbers).

### A1 — Constraints + indexes complete

**Goal.** Every constraint / index from `steps/step17_apply_constraints.py` is present.

**Check.**
```cypher
SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties
RETURN count(*) AS constraint_count;

SHOW INDEXES YIELD name, type, labelsOrTypes, properties
WHERE type IN ['RANGE', 'TEXT', 'LOOKUP']
RETURN count(*) AS index_count;
```

**Threshold.** `constraint_count >= 12` AND `index_count >= 15`.
**Hard fail.** `constraint_count == 0` (graph never had step 17 run).

---

### A2 — Ontology-code coverage on enriched node labels

**Goal.** Per Step 18, the relevant ontology code property is present on most data nodes of each label.

**Checks.**
```cypher
// Diagnosis → SNOMED
MATCH (n:Diagnosis)
WITH count(n) AS total,
     count(CASE WHEN n.snomed_code IS NOT NULL THEN 1 END) AS with_code
RETURN total, with_code, toFloat(with_code) / total AS coverage;

// CognitiveAssessment → LOINC
MATCH (n:CognitiveAssessment)
WITH count(n) AS total,
     count(CASE WHEN n.loinc_code IS NOT NULL THEN 1 END) AS with_code
RETURN total, with_code, toFloat(with_code) / total AS coverage;

// Biomarker (CSF subset) → LOINC
MATCH (n:Biomarker)
WHERE coalesce(n.biomarker_type, n.source_table, '') CONTAINS 'CSF'
WITH count(n) AS total,
     count(CASE WHEN n.loinc_code IS NOT NULL THEN 1 END) AS with_code
RETURN total, with_code, toFloat(with_code) / total AS coverage;

// BrainRegion → UBERON
MATCH (n:BrainRegion)
WITH count(n) AS total,
     count(CASE WHEN n.uberon_code IS NOT NULL THEN 1 END) AS with_code
RETURN total, with_code, toFloat(with_code) / total AS coverage;
```

**Threshold.** Each `coverage >= 0.95` (configurable per label in the rubric YAML).
**Hard fail.** Any of the four labels has `total == 0` (the label never existed) — this means the graph is missing whole categories of clinical data and must be fixed upstream.

---

### A3 — `:OntologyConcept` layer materialised across five sources

**Goal.** Step 19 + Step 20 created `:OntologyConcept` nodes covering SNOMED, LOINC, UBERON, HPO, ICD-10.

**Check.**
```cypher
MATCH (o:OntologyConcept)
RETURN o.source_ontology AS source, count(o) AS n
ORDER BY source;
```

**Threshold.** Result rows include all of: `SNOMED-CT`, `LOINC`, `UBERON`, `HPO`, `ICD-10` (label match, case-insensitive).
**Hard fail.** Total `:OntologyConcept` count `== 0` — step 20 never ran.

Note: the published per-source counts (18 SNOMED, 10 LOINC, 14 UBERON, 5 HPO, 5 ICD-10) are **not** part of the gate by default — only the presence of all five source labels is. If Sultan wants tolerance bands on the counts, set them in the rubric YAML under `A3.expected_counts`.

---

### A4 — Ontology edges present with `uri`

**Goal.** Step 19 / 20 created `MAPS_TO`, `IS_A`, `CLASSIFIED_AS` edges with skos / rdfs URIs.

**Checks.**
```cypher
// MAPS_TO present and most have uri
MATCH ()-[r:MAPS_TO]->()
WITH count(r) AS total,
     count(CASE WHEN r.uri IS NOT NULL THEN 1 END) AS with_uri
RETURN total, with_uri, toFloat(with_uri) / total AS coverage;

// IS_A
MATCH ()-[r:IS_A]->()
WITH count(r) AS total,
     count(CASE WHEN r.uri IS NOT NULL THEN 1 END) AS with_uri
RETURN total, with_uri, toFloat(with_uri) / total AS coverage;

// CLASSIFIED_AS
MATCH ()-[r:CLASSIFIED_AS]->()
WITH count(r) AS total,
     count(CASE WHEN r.uri IS NOT NULL THEN 1 END) AS with_uri
RETURN total, with_uri, toFloat(with_uri) / total AS coverage;
```

**Threshold.** Each edge type: `total > 0` AND `coverage >= 0.95`.
**Hard fail.** `MAPS_TO total == 0` (step 20 never ran).

---

### A5 — Relationship-type URI annotation coverage

**Goal.** Step 18 sets `uri` on every relationship type listed in the schema.

**Check.**
```cypher
// For each relationship type, what fraction of edges have a non-null uri?
MATCH ()-[r]->()
WITH type(r) AS rel_type, count(r) AS n,
     count(CASE WHEN r.uri IS NOT NULL THEN 1 END) AS with_uri
WITH rel_type, n, with_uri, toFloat(with_uri) / n AS coverage
ORDER BY coverage ASC
RETURN rel_type, n, with_uri, coverage;
```

**Threshold.** ≥ 95 % of relationship **types** must have `coverage >= 0.95` on their edges. (i.e., at most 5 % of types may be unannotated.)
**Hard fail.** Zero relationship types have any `uri` populated — step 18 never ran.

The rubric YAML carries a per-type allowlist for relationship types that are intentionally not URI-annotated (e.g., `:BatchIngestion`-related provenance edges).

---

### A6 — No orphan `:OntologyConcept` nodes

**Goal.** Every concept is reachable from a data node via `MAPS_TO` / `IS_A` / `CLASSIFIED_AS` (or is an explicit hierarchy root).

**Check.**
```cypher
MATCH (o:OntologyConcept)
OPTIONAL MATCH (o)<-[r1:MAPS_TO|CLASSIFIED_AS]-(:`*`)
OPTIONAL MATCH (o)<-[r2:IS_A]-(:OntologyConcept)
WITH o, count(r1) + count(r2) AS in_degree
WITH count(o) AS total,
     count(CASE WHEN in_degree > 0 OR o.is_hierarchy_root = true THEN 1 END) AS reachable
RETURN total, reachable, toFloat(reachable) / total AS coverage;
```

**Threshold.** `coverage >= 0.95`.
**Hard fail.** None — orphans are recoverable by re-running step 20 with the missing seeds.

Hierarchy roots (top-level ICD-10 chapters, top-level SNOMED parents) are exempt by setting `is_hierarchy_root = true` on those concepts; the rubric YAML lists the expected roots.

---

### A7 — PTID hygiene

**Goal.** No `:Patient` node has a `ptid` matching the 381_S_ exclusion pattern (ADNI March 2026 advisory).

**Check.** Re-applies `utils/batch_processor.py::DataValidator.validate_ptid` against every Patient node.
```cypher
MATCH (p:Patient)
WHERE p.ptid STARTS WITH '381_S_'
RETURN count(p) AS violation_count, collect(p.ptid)[0..10] AS sample;
```

**Threshold.** `violation_count == 0` (binary).
**Hard fail.** Same as threshold — any 381_S_* present is a fail. The fix is to re-run the cleanup pass that called `DataValidator`.

---

## 3. YAML rubric schema

`metrics/validity_rubric.yaml` shape (Q.6 fills the actual numbers):

```yaml
version: 1
defaults:
  threshold: 0.95
assertions:
  A1:
    description: Constraints + indexes complete
    expected_constraints: 12
    expected_indexes: 15
    hard_fail_if_zero: true
  A2:
    description: Ontology-code coverage on enriched node labels
    per_label:
      Diagnosis: { property: snomed_code, threshold: 0.95 }
      CognitiveAssessment: { property: loinc_code, threshold: 0.95 }
      Biomarker: { property: loinc_code, threshold: 0.95, filter: "csf" }
      BrainRegion: { property: uberon_code, threshold: 0.95 }
  A3:
    description: OntologyConcept layer covers five sources
    required_sources: [SNOMED-CT, LOINC, UBERON, HPO, ICD-10]
    expected_counts:    # optional tolerance bands
      SNOMED-CT: { min: 15, max: 25 }
      LOINC:     { min: 8,  max: 14 }
      UBERON:    { min: 12, max: 18 }
      HPO:       { min: 4,  max: 8 }
      ICD-10:    { min: 4,  max: 8 }
    hard_fail_if_zero: true
  A4:
    description: Ontology edges present with uri
    edges: [MAPS_TO, IS_A, CLASSIFIED_AS]
    threshold: 0.95
    hard_fail_if_maps_to_zero: true
  A5:
    description: Relationship-type URI annotation coverage
    per_type_threshold: 0.95
    type_coverage_threshold: 0.95
    allowlist_unannotated: [BATCH_INGESTED_BY]
  A6:
    description: No orphan OntologyConcept nodes
    threshold: 0.95
    hierarchy_roots: [icd10:G30, icd10:F00, snomed:64572001]
  A7:
    description: PTID hygiene
    forbidden_prefix: "381_S_"
    binary: true
```

---

## 4. Output schemas

### 4.1 JSON (`outputs/validity_reports/kg_validity_<timestamp>.json`)

```json
{
  "schema_version": 1,
  "timestamp": "2026-05-09T14:32:00+03:00",
  "graph_uri": "bolt://localhost:7687",
  "rubric_version": 1,
  "result": "PASS",
  "assertions": {
    "A1": {"result": "PASS", "constraint_count": 12, "index_count": 15},
    "A2": {"result": "PASS", "per_label": {"Diagnosis": 0.997, "CognitiveAssessment": 0.984, "Biomarker": 0.962, "BrainRegion": 0.991}},
    "A3": {"result": "PASS", "sources_present": ["SNOMED-CT","LOINC","UBERON","HPO","ICD-10"], "counts": {"SNOMED-CT": 18, "LOINC": 10, "UBERON": 14, "HPO": 5, "ICD-10": 5}},
    "A4": {"result": "PASS", "MAPS_TO": {"total": 100770, "uri_coverage": 1.0}, "IS_A": {"total": 27, "uri_coverage": 1.0}, "CLASSIFIED_AS": {"total": 25946, "uri_coverage": 1.0}},
    "A5": {"result": "PASS", "type_coverage": 0.97, "types_below_threshold": []},
    "A6": {"result": "PASS", "orphan_rate": 0.0, "reachable_rate": 1.0},
    "A7": {"result": "PASS", "violation_count": 0}
  },
  "warnings": [],
  "duration_seconds": 3.2
}
```

### 4.2 Markdown (`kg_validity_<timestamp>.md`)

Header line: `# KG Validity Report — <timestamp> — RESULT: PASS`.
One section per assertion with the result, the measured number, and the rubric threshold. On FAIL, the offending assertions are listed first with a "what to re-run" hint.

---

## 5. Hard-fail conditions (apply even with threshold scoring)

The threshold scheme allows assertions to pass at 95 %+ even if the whole graph isn't perfect. But certain conditions are still hard fails because they indicate the migration didn't run at all:

- **A1** — `constraint_count == 0`
- **A2** — any of the four labels (Diagnosis, CognitiveAssessment, Biomarker, BrainRegion) has `total == 0`
- **A3** — total `:OntologyConcept` count `== 0`
- **A4** — `MAPS_TO total == 0`
- **A7** — any `381_S_*` Patient (binary, no threshold)

These are listed in `metrics/validity_rubric.yaml` under each assertion's `hard_fail_*` key.

---

## 6. Open questions for Sultan (Q.6)

1. Are the per-label A2 thresholds 0.95 across the board, or label-specific (e.g., 0.99 for Diagnosis, 0.95 for the rest)?
2. Should A3 enforce the per-source count tolerance bands, or only the presence of the five source names?
3. Is the A5 `type_coverage_threshold` of 95 % acceptable, or should it be 100 % minus the explicit allowlist?
4. Should the JSON / Markdown report include the offending node IDs on FAIL (useful for debugging, but bigger files), or only summary counts?

---

## 7. Cross-references

- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) §5 — gate position in pipeline
- [TASKS.md](TASKS.md) §V — implementation tasks
- [STATUS.md](STATUS.md) — current state
- [../../infrastructure/history/PHASE1_SCHEMA_MIGRATION.md](../../infrastructure/history/PHASE1_SCHEMA_MIGRATION.md) — Steps 17–20 background
- `steps/step17_apply_constraints.py` / `step18..step20*.py` — code under test
- `utils/batch_processor.py::DataValidator` — A7 reuses the existing PTID validator
