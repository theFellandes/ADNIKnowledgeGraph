# Gap-Closure Spec — Contribution-Table Items B-17 to B-21 (Phase 3)

> **Owner.** Oğuzhan Güngör (implementation), Dr. Hajer Baazaoui (scope sign-off Q.8 + Q.9).
> **Position in pipeline.** Phase 3 of [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Runs after Phase 2 snapshots so per-step deltas can be reported.
> **Anchor task IDs.** P3.10 (B-17), P3.20 (B-18), P3.30 (B-19), P3.40 (B-20), P3.50 (B-21) — see [TASKS.md §P3](TASKS.md).
> **Source of truth.** [Contribution_Table_updated HB.pdf](file:///C:/Users/Fellandes/Downloads/Contribution_Table_updated%20HB.pdf) §§3, 5; the "Ontology and Tool Assessment Summary" table.

---

## 0. Cross-cutting requirements (apply to every B-17 to B-21 step)

Every new step file under `steps/step{30..34}_*.py` adheres to the existing project conventions:

### 0.1 Function signature

```python
def execute_step_n(neo4j_uri: str, user: str, password: str, *, config: dict | None = None) -> dict:
    """Step <n> — <one-line description>.

    Idempotent: re-running produces the same node/edge counts.
    Returns a result dict for the pipeline runner: {"status": "success"|"failure", "counts": {...}, "duration_s": float}.
    """
```

### 0.2 Idempotency

Every Cypher uses `MERGE` (not `CREATE`) for nodes; every edge `MERGE` is keyed on both endpoints + type. Sample:

```cypher
MERGE (o:OntologyConcept {code: $code, source_ontology: $src})
ON CREATE SET o.label = $label, o.uri = $uri, o.created_at = datetime()
ON MATCH SET o.label = coalesce($label, o.label)
```

### 0.3 Logging

Use `utils/quality_aware_logger.py::QualityAwareLogger` (or `utils/data_quality_logger.py::DataQualityLogger`, whichever the existing steps use). Log:
- Inputs (rows / columns from source table).
- Outputs (nodes created, edges created).
- Failures (REST timeouts, missing columns).
- Idempotency check (counts after re-run).

### 0.4 Pipeline registration

Add a `_execute_step_n(self)` wrapper to `pipeline.py::ADNIPipeline`, and register it in the `run()` method behind a config toggle. Toggle keys (defaulted `false`):
- `run_hpo_expansion`
- `run_loinc_vitals`
- `run_medhist_comorbidity`
- `run_biolink_categories`
- `run_mondo_doid_wiring`

### 0.5 Validation hook

After the step finishes, the runner calls `metrics/validity.py::run_validity()` and aborts the pipeline on FAIL. This ensures the validity gate stays PASS through Phase 3.

### 0.6 Mapping CSV

Each step has a companion CSV at `ontology/mappings/<table>_to_<ontology>.csv` with the schema:

```csv
source_table,source_column,source_value_pattern,target_ontology,target_uri,target_label,mapping_rule,test_fixture_id,last_verified_date
```

`test_fixture_id` is the ID of a row in `tests/fixtures/mini_kg.cypher` that exercises this mapping.

### 0.7 Tests

`tests/test_step{30..34}.py` each contain:
- An idempotency test (run twice → identical counts).
- A coverage test (post-step, verify the expected count of new nodes / edges).
- A validity test (run validity gate after the step → PASS).

`tests/test_column_to_concept.py` is extended with per-step row validation against the mini-KG fixture.

---

## §B-17 — HPO expansion (Step 30)

**Contribution-table commitment.** "(a) HPO expansion: ~5 concepts → ~15. Map the HPO-mappable AX symptoms (anxiety, depression, agitation, wandering, insomnia, hallucinations…) to HPO terms. Link FamilyMember nodes too." Plus the assessment summary's "EXPAND (top priority). 5 → 30 concepts."

The contribution table is a touch ambiguous (15 vs 30 concepts). v3 targets **15 directly-mapped concepts** (one per ADSXLIST symptom) **plus** additional HPO terms for FamilyMember-flag mappings — total ~20–30 depending on how FamilyMember categories resolve. Q.8 confirms with Hajer.

### Source data
**Table.** `ADSXLIST` — 30 binary symptom columns. Approximately 15 map cleanly to HPO. Existing step 4 / 8 / 9 may have already created `:Visit` or `:ClinicalFinding` nodes with these column values as properties.

**Audit task.** During A0.1, query `MATCH (v:Visit) RETURN keys(v) ORDER BY size(keys(v)) DESC LIMIT 5` to verify which `AX...` properties exist on `:Visit` vs which are on a separate `:ClinicalFinding` label.

### HPO target list

The 15 HPO terms most cleanly mapped from ADSXLIST columns:

| ADSXLIST column | HPO ID | HPO label |
|---|---|---|
| `AXANXIET` | HP:0000739 | Anxiety |
| `AXDEPRES` | HP:0000716 | Depression |
| `AXAGITAT` | HP:0000713 | Agitation |
| `AXWANDER` | HP:0030223 | Wandering |
| `AXINSOMN` | HP:0100785 | Insomnia |
| `AXHALL` | HP:0000738 | Hallucinations |
| `AXDELU` | HP:0000746 | Delusions |
| `AXAPATHY` | HP:0000741 | Apathy |
| `AXIRRITAB` | HP:0000737 | Irritability |
| `AXELATED` | HP:0100024 | Elation (or HP:0000749 Euphoria — confirm in Q.8) |
| `AXAPETIT` | HP:0004324 | Abnormality of appetite |
| `AXNIGHT` | HP:0002360 | Sleep disturbance |
| `AXMOTOR` | HP:0001332 | Dystonia (proxy for aberrant motor) |
| `AXDISINH` | HP:0000758 | Disinhibition |
| `AXEUPHOR` | HP:0000749 | Euphoria |

(Final list confirmed by reading the actual ADSXLIST CSV header during A0.1; the IDs above are the high-confidence mappings.)

### Cypher (template)

```cypher
// Create HPO OntologyConcept nodes (idempotent)
UNWIND $hpo_concepts AS row
MERGE (o:OntologyConcept {code: row.code, source_ontology: 'HPO'})
ON CREATE SET o.label = row.label,
              o.uri = 'http://purl.obolibrary.org/obo/HP_' + replace(row.code, ':', '_'),
              o.created_by = 'step30_hpo_expansion',
              o.created_at = datetime();

// Link Visit (or ClinicalFinding) → HPO via MAPS_TO
MATCH (v:Visit), (o:OntologyConcept {source_ontology: 'HPO'})
WHERE v[$column_name] = 1
MERGE (v)-[r:MAPS_TO]->(o)
ON CREATE SET r.uri = o.uri,
              r.source_column = $column_name,
              r.created_at = datetime();
```

Repeated per row in `ontology/mappings/adsxlist_to_hpo.csv`.

### FamilyMember mappings

Also map family-history flags (e.g., `FHFAM_*`) where they correspond to HPO phenotypes. Edge:

```cypher
MATCH (f:FamilyMember), (o:OntologyConcept {code: 'HP:0002511', source_ontology: 'HPO'})
WHERE f.FHQAD = 1  // family history of Alzheimer's
MERGE (f)-[:MAPS_TO {uri: o.uri}]->(o);
```

### REST handling

For label lookups, follow the [steps/step19_icd10_integration.py](../../../steps/step19_icd10_integration.py) pattern:
1. Try EBI OLS REST endpoint (`https://www.ebi.ac.uk/ols/api/ontologies/hp/terms?iri=...`).
2. On 5xx / timeout, retry with exponential backoff (1s, 2s, 4s).
3. On final failure, fall back to `ontology/hpo_concepts_cache.json` (committed to repo).
4. Log fail-loud to the quality logger.

`ontology/hpo_concepts_cache.json` is pre-populated once during P3.11 from a known-good lookup.

### Verification

After step 30 runs:
- `MATCH (o:OntologyConcept {source_ontology:'HPO'}) RETURN count(o)` ≥ 15.
- `MATCH ()-[r:MAPS_TO]->(:OntologyConcept {source_ontology:'HPO'}) RETURN count(r)` ≥ 3,000 (≈15 symptoms × ≥200 patients reporting any symptom).
- Validity A3 reports HPO present; A2 unchanged (HPO is not on the per-label-coverage list); A6 reports HPO concepts reachable.
- Audit log: every ADSXLIST column either has a mapping rule + count, or an explicit "no HPO match, skipped" entry.

### Effort
~1.5 days including mapping CSV + cache + tests + ambiguity-resolution iterations.

---

## §B-18 — LOINC vital signs (Step 31)

**Contribution-table commitment.** "(c) LOINC vital signs: systolic BP (8480-6), diastolic (8462-4), weight (29463-7), height (8302-2), heart rate (8867-4), BMI (39156-5). LOINC vocabulary goes from 10 to 16 codes."

Six concepts, exact codes specified — no ambiguity here.

### Source data
**Table.** `VITALS` — has columns `VSBPSYS`, `VSBPDIA`, `VSWEIGHT`, `VSHEIGHT`, `VSPULSE`, `VSBMI` (or whatever the actual column names are — confirm during A0.1).

**Audit task.** During A0.1, inspect headers.json for VITALS column names. If the table doesn't exist or has different columns, the mapping CSV's `source_column` is the resolution.

### LOINC target list

| Source column (audit) | LOINC code | LOINC label |
|---|---|---|
| `VSBPSYS` | 8480-6 | Systolic blood pressure |
| `VSBPDIA` | 8462-4 | Diastolic blood pressure |
| `VSWEIGHT` | 29463-7 | Body weight |
| `VSHEIGHT` | 8302-2 | Body height |
| `VSPULSE` | 8867-4 | Heart rate |
| `VSBMI` | 39156-5 | Body mass index (BMI) |

### Where the values live

Two options to check during A0.1:
- (a) `:Biomarker` nodes already carry vital-sign values with `biomarker_type='vital_sign'`. → Step 31 just adds MAPS_TO edges to LOINC concepts.
- (b) `:Visit` nodes carry vital-sign values as properties. → Step 31 creates `:Biomarker(biomarker_type='vital_sign')` nodes per visit per measurement, then MAPS_TO.

The contribution table is silent on this; the existing step 18 partially handles it. Inspect during audit and document the decision in `ontology/mappings/vitals_to_loinc.csv`'s `mapping_rule` column.

### Cypher (option a — biomarker already exists)

```cypher
// Create 6 new LOINC OntologyConcept nodes
UNWIND $loinc_vital_signs AS row
MERGE (o:OntologyConcept {code: row.code, source_ontology: 'LOINC'})
ON CREATE SET o.label = row.label,
              o.uri = 'http://loinc.org/' + row.code,
              o.created_by = 'step31_loinc_vital_signs',
              o.created_at = datetime();

// MAPS_TO edges from existing vital-sign biomarkers
MATCH (b:Biomarker), (o:OntologyConcept {source_ontology: 'LOINC'})
WHERE b.biomarker_type = 'vital_sign' AND b.measurement_name = o.label
MERGE (b)-[r:MAPS_TO]->(o)
ON CREATE SET r.uri = o.uri, r.created_at = datetime();
```

### Verification

- `MATCH (o:OntologyConcept {source_ontology:'LOINC'}) RETURN count(o)` = 16 (10 baseline + 6 new).
- `MATCH (b:Biomarker)-[:MAPS_TO]->(:OntologyConcept {source_ontology:'LOINC'}) WHERE b.biomarker_type='vital_sign' RETURN count(b)` ≈ (VITALS row count) × 6 − nulls.
- Validity A3 reports LOINC count band 10–16 still in range.

### Effort
~0.5 day.

---

## §B-19 — MEDHIST → Comorbidity nodes (Step 32)

**Contribution-table commitment.** "(b) Comorbidity extraction: create Comorbidity nodes from MEDHIST. MEDHIST provides category-level flags (e.g. cardiovascular, psychiatric, neurological, endocrine) rather than specific diagnoses, so SNOMED-CT mappings stay at category granularity."

### Source data
**Table.** `MEDHIST` — confirm exact column names during A0.1. Likely includes `MHPSYCH`, `MHNEURL`, `MHCARDIO`, `MHENDO`, `MHGASTRO`, `MHRENAL`, `MHHEPAT`, `MHMUSCL`, `MHRESPI`, `MHSKIN`, `MHHEMAT`, `MHOPHTH`, `MHOTHER`, `MHALLERG`, ... (per ADNI's standard MEDHIST schema).

**Categories targeted (minimum 5; expand if MEDHIST has more).**

| MEDHIST column | Category | SNOMED-CT category code | SNOMED label |
|---|---|---|---|
| `MHPSYCH` | psychiatric | 74732009 | Mental disorder |
| `MHNEURL` | neurological | 118940003 | Disorder of nervous system |
| `MHCARDIO` | cardiovascular | 49601007 | Disorder of cardiovascular system |
| `MHENDO` | endocrine | 362969004 | Disorder of endocrine system |
| `MHGASTRO` | gastrointestinal | 53619000 | Disorder of digestive system |

Additional categories as MEDHIST exposes them (renal, hepatic, etc.).

### Schema

New node label `:Comorbidity`. Properties:
- `category` — short slug (e.g., `cardiovascular`)
- `snomed_code` — SNOMED-CT category code
- `source_column` — `MHCARDIO` etc.
- `description` — human-readable label

New relationship type `:HAS_COMORBIDITY` between `:Patient` and `:Comorbidity`, properties:
- `snomed_code` — duplicated for traversal queries
- `uri` — SKOS exact-match URI
- `source_table` — `MEDHIST`

### Cypher (template)

```cypher
// Create Comorbidity nodes (one per category)
UNWIND $categories AS cat
MERGE (c:Comorbidity {category: cat.slug})
ON CREATE SET c.snomed_code = cat.snomed_code,
              c.source_column = cat.column,
              c.description = cat.description,
              c.created_by = 'step32_medhist_comorbidity',
              c.created_at = datetime();

// Also create the corresponding SNOMED OntologyConcept (idempotent)
UNWIND $categories AS cat
MERGE (o:OntologyConcept {code: cat.snomed_code, source_ontology: 'SNOMED-CT'})
ON CREATE SET o.label = cat.description,
              o.uri = 'http://snomed.info/id/' + cat.snomed_code,
              o.created_at = datetime();

// Link Comorbidity → SNOMED OntologyConcept
MATCH (c:Comorbidity), (o:OntologyConcept {source_ontology:'SNOMED-CT'})
WHERE c.snomed_code = o.code
MERGE (c)-[:MAPS_TO {uri: o.uri}]->(o);

// Link Patient → Comorbidity from MEDHIST flags
MATCH (p:Patient)
WITH p
UNWIND $categories AS cat
WITH p, cat
WHERE p[cat.column] = 1
MATCH (c:Comorbidity {category: cat.slug})
MERGE (p)-[r:HAS_COMORBIDITY]->(c)
ON CREATE SET r.snomed_code = cat.snomed_code,
              r.uri = 'http://snomed.info/id/' + cat.snomed_code,
              r.source_table = 'MEDHIST',
              r.created_at = datetime();
```

The MEDHIST flag may live on `:Patient` (per-patient single record) or on `:MedicalHistory` (per-visit record). Confirm during A0.1.

### Validity gate impact

A2 — `:Comorbidity` is a new label with no existing coverage threshold. v3 adds a new A2 sub-rule: `{Comorbidity: {property: snomed_code, threshold: 1.0}}` — must be 100 % because new label.

A5 — `HAS_COMORBIDITY` is a new relationship type. By default, A5 requires `uri` populated; we set it. No allowlist needed.

### Verification

- `MATCH (c:Comorbidity) RETURN count(c)` ≥ 5.
- `MATCH (c:Comorbidity) WHERE c.snomed_code IS NULL RETURN count(c)` = 0.
- `MATCH ()-[r:HAS_COMORBIDITY]->() WHERE r.uri IS NULL RETURN count(r)` = 0.
- HAS_COMORBIDITY count matches MEDHIST flag count.

### Effort
~1 day including the category-resolution work.

---

## §B-20 — Biolink Model (Step 33)

**Contribution-table commitment.** "Biolink Model — Schema standard for biomedical KGs. Node categories + predicate types. ADD. biolink_category on all 17 node types via batch Cypher. Half a day."

Plus the relation-normalization section: "Biolink Model predicate alignment added on top (biolink:causes, biolink:associated_with, etc.)" with "Biolink-aligned node types: 0/17 → 12/17".

### Approach

Two Cypher batches:

1. **Node categorization.** For each of the 17 node labels in the graph, set `n.biolink_category` to the Biolink Model class string.
2. **Predicate alignment.** For each of the 30 relationship types, set `r.biolink_predicate` (already partial — some are set by step 18, see `INDICATES`, `HAS_VISIT` examples).

### Node-label → Biolink mapping (draft — confirm with Hajer in Q.9)

| Node label | Biolink category | Confidence |
|---|---|---|
| `:Patient` | `biolink:Case` | high (Biolink 4.x) |
| `:Visit` | `biolink:ClinicalAttribute` | medium — alternative `biolink:Procedure` |
| `:Diagnosis` | `biolink:DiseaseOrPhenotypicFeature` | high |
| `:CognitiveAssessment` | `biolink:DiagnosticAid` | medium — alternative `biolink:ClinicalMeasurement` |
| `:Biomarker` | `biolink:ChemicalEntity` (CSF proteins) / `biolink:ClinicalMeasurement` (vital signs) | **ambiguous — Q.9** |
| `:BrainRegion` | `biolink:GrossAnatomicalStructure` | high |
| `:OntologyConcept` | `biolink:OntologyClass` | high |
| `:Image` | `biolink:Image` | high (if Biolink 4.x supports it) — otherwise `biolink:NamedThing` |
| `:FamilyMember` | `biolink:Case` (related-party) | medium |
| `:ClinicalFinding` | `biolink:PhenotypicFeature` | medium |
| `:Comorbidity` | `biolink:DiseaseOrPhenotypicFeature` | high (NEW label from B-19) |
| `:Medication` | `biolink:Drug` or `biolink:ChemicalEntity` | medium |
| `:GeneticProfile` | `biolink:Genotype` | medium |
| `:MedicalHistory` | `biolink:ClinicalAttribute` | low — Q.9 |
| `:AlzKBConcept` | `biolink:OntologyClass` (it represents external concepts) | medium |
| `:BatchIngestion` | `biolink:NamedThing` (provenance node) | low |
| `:Study` | `biolink:Study` | high |

(17 rows here; actual labels in the graph may differ. A0.1 audit confirms.)

### Predicate-type → Biolink mapping (draft)

| Relationship type | Biolink predicate | Confidence |
|---|---|---|
| `HAS_VISIT` | `biolink:has_attribute` | medium |
| `HAS_DIAGNOSIS` | `biolink:has_phenotype` | high |
| `INDICATES` | `biolink:correlated_with` | high |
| `MAPS_TO` | `biolink:exact_match` (skos:exactMatch wrapper) | high |
| `IS_A` | `biolink:subclass_of` | high |
| `CLASSIFIED_AS` | `biolink:category` | medium |
| `SAME_AS` | `biolink:same_as` | high |
| `HAS_PART` | `biolink:has_part` | high |
| `PART_OF` | `biolink:part_of` | high |
| `HAS_BIOMARKER` | `biolink:has_biomarker_for` | medium |
| `HAS_FAMILY_MEMBER` | `biolink:related_to` | medium |
| `HAS_COMORBIDITY` | `biolink:has_phenotype` | medium (NEW from B-19) |
| ... | ... | ... |

(30 rows total. Generate during execution from the canonical relationship-type list in step 18.)

### Cypher (template)

```cypher
// Batch 1 — node categorization
UNWIND $node_categories AS row
MATCH (n)
WHERE labels(n)[0] = row.label
SET n.biolink_category = row.category;

// Batch 2 — predicate alignment
UNWIND $predicate_map AS row
MATCH ()-[r]->()
WHERE type(r) = row.rel_type
SET r.biolink_predicate = row.biolink_predicate;
```

For very large relationship types (e.g., `:MAPS_TO` with 100 K+ edges), batch via `apoc.periodic.iterate` if available, or run a `CALL { ... } IN TRANSACTIONS` for Neo4j 5.x.

### Verification

- `MATCH (n) WHERE n.biolink_category IS NOT NULL RETURN labels(n)[0] AS label, count(n) ORDER BY label` shows ≥ 12 / 17 node types annotated.
- `MATCH ()-[r]->() WHERE r.biolink_predicate IS NOT NULL RETURN type(r), count(r) ORDER BY type(r)` shows ≥ 12 / 30 relationship types annotated.
- Validity A5 (relationship-type URI coverage) unchanged (Biolink is additive on top of existing `uri`).
- FAIR I2 (interoperable vocabularies) expected to rise.

### Effort
~0.5–1 day. Mostly authoring + Q.9 confirmation on the ambiguous mappings.

---

## §B-21 — MONDO/DOID concept wiring (Step 34)

**Contribution-table commitment.**
- "MONDO — Cross-reference disease hub. Links OMIM, Orphanet, DOID. mondo_code properties exist on Diagnosis nodes. No OntologyConcept nodes or MAPS_TO edges. ADD. Wire up existing codes. 2-3 hours."
- "DOID — Disease Ontology. Used by AlzKB and Yang et al. for disease entities. Not integrated. Phase 3 would need SNOMED → DOID mapping without it. ADD. 3 mappings (AD, dementia, MCI). Half a day."

### Approach

Two sub-steps within step 34:

#### Sub-step 34a — MONDO wiring

```cypher
// Find unique MONDO codes on :Diagnosis nodes
MATCH (d:Diagnosis)
WHERE d.mondo_code IS NOT NULL
WITH DISTINCT d.mondo_code AS code, d.diagnosis_label AS label
// Create OntologyConcept nodes
MERGE (o:OntologyConcept {code: code, source_ontology: 'MONDO'})
ON CREATE SET o.label = label,
              o.uri = 'http://purl.obolibrary.org/obo/MONDO_' + replace(code, ':', '_'),
              o.created_by = 'step34_mondo_doid_wiring',
              o.created_at = datetime();

// Wire MAPS_TO from Diagnosis to MONDO OntologyConcept
MATCH (d:Diagnosis), (o:OntologyConcept {source_ontology:'MONDO'})
WHERE d.mondo_code = o.code
MERGE (d)-[r:MAPS_TO]->(o)
ON CREATE SET r.uri = o.uri, r.created_at = datetime();
```

#### Sub-step 34b — DOID wiring (3 explicit nodes)

```cypher
// Create 3 DOID OntologyConcept nodes
WITH [
  {code: 'DOID:10652', label: "Alzheimer's disease", diagnosis_label: 'AD'},
  {code: 'DOID:1307', label: 'dementia', diagnosis_label: 'Dementia'},
  {code: 'DOID:0050169', label: 'mild cognitive impairment', diagnosis_label: 'MCI'}
] AS rows
UNWIND rows AS r
MERGE (o:OntologyConcept {code: r.code, source_ontology: 'DOID'})
ON CREATE SET o.label = r.label,
              o.uri = 'http://purl.obolibrary.org/obo/' + replace(r.code, ':', '_'),
              o.created_by = 'step34_mondo_doid_wiring',
              o.created_at = datetime();

// Wire MAPS_TO from Diagnosis to DOID
UNWIND [
  {doid: 'DOID:10652', dx: 'AD'},
  {doid: 'DOID:1307', dx: 'Dementia'},
  {doid: 'DOID:0050169', dx: 'MCI'}
] AS m
MATCH (d:Diagnosis {diagnosis_label: m.dx}), (o:OntologyConcept {code: m.doid, source_ontology:'DOID'})
MERGE (d)-[:MAPS_TO {uri: o.uri}]->(o);
```

### Validity gate update

- A3 `required_sources` extended to `[SNOMED-CT, LOINC, UBERON, HPO, ICD-10, MONDO, DOID]`.
- A3 count band for MONDO: ≥ 1 (whatever the unique mondo_code count on Diagnosis is, plus expectation for at least one).
- A3 count band for DOID: exactly 3.

### Verification

- `MATCH (o:OntologyConcept) RETURN DISTINCT o.source_ontology` returns 7 sources.
- `MATCH (:Diagnosis)-[:MAPS_TO]->(:OntologyConcept {source_ontology:'DOID'}) RETURN count(*)` ≥ 1 per DOID concept × matching Diagnosis count.
- FAIR I1 / I2 rise (more shared identifiers).
- AlzKB alignment: Disease category jumps from "weak" (SNOMED only) to "strong" (now shares DOID with AlzKB).

### Effort
~0.5 day.

---

## Phase 3 close-out

After all five steps land:

1. **Re-run validity gate.** `python -m metrics validity` must PASS. The rubric YAML extension (P3.4) ensures the 7-source requirement is met.
2. **Capture per-enrichment snapshots.** P3.5 — five new dump files in `data/snapshots/`.
3. **Re-run metrics on the post-enrichment graph.** P3.6 — refreshed canonical snapshot.
4. **Trigger Phase 4.** AlzKB re-bridge + F3 / F4 / F5 figure regeneration.

---

## Cross-references

- [IMPLEMENTATION_PLAN.md §4 Phase 3](IMPLEMENTATION_PLAN.md)
- [TASKS.md §P3](TASKS.md)
- [STATUS.md](STATUS.md) — flip ❌ → ✅ as each B-* lands
- [c7_unified_contribution.md Step C](../c7_unified_contribution.md) — paper-side description of column-to-concept mapping
- [Contribution_Table_updated HB.pdf](file:///C:/Users/Fellandes/Downloads/Contribution_Table_updated%20HB.pdf) — the original promise
- [c7_plan_v2/CONTRIBUTION_TABLE_GAP_ANALYSIS.md](../c7_plan_v2/CONTRIBUTION_TABLE_GAP_ANALYSIS.md) — gap analysis to flip to "done"
