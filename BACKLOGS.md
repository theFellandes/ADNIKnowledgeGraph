# Backlogs — MAKO Metrics + Figures Pipeline

> Tracks known issues, defects, and follow-up work for the metric / figure
> infrastructure. Items are roughly priority-ordered. Created 2026-05-09.
>
> Companion to `docs/final_report/c7_plan_v2/TASKS.md` (the forward plan)
> and `docs/final_report/c7_plan_v2/STATUS.md` (status ledger).

---

## P0 — Blocking Sultan / paper deliverables

### B-01. Step 24's `ALZKB_RELATES_TO` edges fail A5

**Symptom.** Validity gate fails with one rel-type below per-type threshold:
`ALZKB_RELATES_TO` (18 edges, 0% URI). Created by step 24 between
`:AlzKBConcept` nodes; never in step 18's `RELATIONSHIP_URIS` dict.

**Evidence.** `outputs/validity_reports/kg_validity_20260509T164241Z.md` line 10:
> `1 rel-types below per-type threshold (top offenders: [{'rel_type': 'ALZKB_RELATES_TO', 'coverage': 0.0}])`

**Fix options (pick one).**
- **Option A — extend step 18's `RELATIONSHIP_URIS`.** Add
  `"ALZKB_RELATES_TO": "ro:RO_0002610"` (correlated_with) — most general
  fit since the AlzKB CYPHERL types vary (GENEASSOCIATESWITHDISEASE,
  DISEASELOCALIZESTOANATOMY, DRUGTREATSDISEASE, etc.). Re-run step 18 once.
- **Option B — allowlist it.** Add `ALZKB_RELATES_TO` to
  `metrics/validity_rubric.yaml::A5.allowlist_unannotated`. Cleaner because
  step 24's edges already carry a `type` property holding the specific
  AlzKB predicate; layering `r.uri` on top is double-bookkeeping.
- **Option C — step 24 sets r.uri at write time.** Modify
  `MERGE_ALZKB_RELATIONSHIP` template at
  [steps/step24_alzkb_bridge.py:237](steps/step24_alzkb_bridge.py:237) to
  also set `r.uri` based on `rel.type`. Most semantically faithful.

**Recommendation.** B for now (one-line YAML edit), then C as part of a
proper Step D / relation-normalisation pass once the paper's methodology
section is finalised.

---

### B-02. Stale metric JSONs after a failed validity gate

**Symptom.** When validity fails, the runner correctly short-circuits, but
`main.py` still proceeds to figure rendering. The figure scripts read from
`outputs/metrics/*.json` — which carry **pre-step24 results from the
previous successful run**. F3, F5 SVG/PDF therefore show stale numbers.

**Evidence.** At 19:42:
- Validity FAIL
- alignment, density, fair, step_audit not executed
- `outputs/metrics/alzkb_alignment.json` shows `alzkb_concept_total: 0`,
  `same_as_edge_total: 0`, all categories 0/N
- Direct `MATCH (a:AlzKBConcept) RETURN count(a)` returns **46**
- The graph is healthy; the JSON is just old

**Fix options.**
- Either timestamp + version each JSON output (so figures pick the *latest
  successful* run), or have figures refuse to render if their input JSON
  is older than the most recent validity report.
- Simpler: have the runner write a `runner_summary.json` that figures
  consult to know whether the upstream metrics actually ran in the current
  invocation.

**Recommendation.** Add a `current_run_id` to `runner_summary.json` and have
each metric JSON carry the same id. Figures verify the id matches before
trusting the JSON.

---

### B-03. A5 strictness — type_coverage above threshold but result FAIL

**Symptom.** A5 fails even though type_coverage = 0.9804 ≥ 0.95 threshold,
because the validity logic appends a note for *any* type below per-type
threshold and `result = FAIL if notes else PASS`.

**Evidence.** `outputs/validity_reports/kg_validity_20260509T164241Z.json`
A5 measured: `total_types=56, annotated_types=50, type_coverage=0.9804,
types_below_threshold=[ALZKB_RELATES_TO @ 0.0]`. Should be PASS under the
intent of `type_coverage_threshold: 0.95`.

**Fix.** In [metrics/validity.py](metrics/validity.py) `check_a5()`:
separate hard-fail notes (type_coverage < threshold) from informational
notes (specific types below per-type). Make `types_below` informational
only; FAIL only if `type_coverage < type_coverage_threshold`.

**Recommendation.** Fix in the same change as B-01 — these tend to surface
together every time step 24 runs.

---

## P1 — Architectural / recurring issues

### B-04. Step 18 needs to run *after* every edge-creating step

**Symptom.** Each pipeline run creates new edges of types like HAS_VISIT,
PRECEDES, FOLLOWED_BY etc. via steps 9, 12, 15, 22, 24. None of those
steps set `r.uri` — that's step 18's job. But step 18 sits at position 18
in `pipeline.py`, before steps 19, 20, 22, 23, 24 that add more edges. So
each pipeline run leaves a fresh layer of unannotated edges. Operator has
to re-run step 18 manually after every full pipeline run to keep A5 PASS.

**Evidence.** Three separate validity reports between 18:46 and 19:42 show
the same family-rel and edge-type regressions on every run.

**Fix options.**
- Move step 18 invocation in `pipeline.py` from line 207 to *after* the
  last edge-creating step (currently step 29 area).
- Or add a "step 18 finalize" call at the end of every pipeline run that
  re-applies URIs.
- Or have each edge-creating step set `r.uri` itself at creation time.

**Recommendation.** Move step 18 to run last in `pipeline.py`. Smallest
change; preserves idempotency; eliminates the manual re-run.

---

### B-05. `is_hierarchy_root` property missing from graph

**Symptom.** Validity A6 query references `o.is_hierarchy_root`, which Neo4j
warns is unknown:
> `the missing property name is: is_hierarchy_root`

The current A6 logic uses the rubric's `hierarchy_roots` URI list as the
exempt set, which works — but the `coalesce(o.is_hierarchy_root, false)`
fallback in the query produces noise.

**Fix options.**
- Have step 19 / step 20 set `is_hierarchy_root: true` on the explicit
  hierarchy-root concepts at creation time, so the property exists.
- Or remove the `is_hierarchy_root` fallback from the validity Cypher and
  rely solely on the rubric YAML list.

**Recommendation.** Drop the `is_hierarchy_root` Cypher fallback. The YAML
list is the source of truth; doubling up just adds warning noise.

---

### B-06. Validity-report retention policy

**Symptom.** Six validity reports already accumulated in
`outputs/validity_reports/` from one afternoon. Pre-deliverable cleanup
is going to be tedious.

**Fix.** Either (a) keep only the most recent 5 plus any with `RESULT: PASS`,
or (b) write to a date-stamped subdir per run and delete older sibling
dirs older than N days.

**Recommendation.** (a). Keep last 5 + every PASS, delete the rest at the
end of `main.py`.

---

## P2 — Functional gaps documented in the plan

### B-07. F4 (semantic density progression) needs snapshots

Per [docs/final_report/c7_plan_v2/TASKS.md](docs/final_report/c7_plan_v2/TASKS.md)
M1.* — neo4j-admin offline dumps + per-step snapshots. Without those,
`outputs/metrics/semantic_density_per_step.json` stays empty and F4 keeps
skipping.

**Owner.** Q.7 schedule downtime with Özgün, then implement the snapshot
loop in `metrics/snapshots.py` wrapper (already authored).

---

### B-08. AlzKB Phenotype alignment is 0/5

**Symptom.** Per the standalone-run alignment from 19:31 — Disease 2/17,
Anatomy 2/14, **Phenotype 0/5**. Step 24's `SAME_AS_RULES` at
[steps/step24_alzkb_bridge.py:124](steps/step24_alzkb_bridge.py:124) has
no HPO ↔ AlzKB Symptom/BiologicalProcess mappings. The C7 paper claim of
"3 of 4 in-scope" needs Phenotype to light up.

**Fix.** Extend `SAME_AS_RULES` with HPO concept mappings:
- `hpo:HP:0000726` (Dementia) → `alzkb:disease_dementia` (cross-type same-as)
- `hpo:HP:0001268` (Mental deterioration) → ... etc.

**Owner.** Step 24 maintainer.

---

### B-09. R1.2 provenance coverage stuck at 55%

**Symptom.** FAIR R1.2 returns 0.5536 (partial) because the Cypher checks
for `BATCH_INGESTED_BY|LOADED_FROM` rel types (warned as unknown) and
`batch_id`/`source_table` properties on Patient/Visit/Diagnosis/etc. About
55% of clinical nodes have one of those.

**Fix.** Either (a) add provenance edges from data ingestion steps (1-7)
to a `:BatchIngestion` node, or (b) set `source_table` on every node in
the loader.

**Owner.** Data-ingestion steps; needs Özgün's input on which approach.

---

### B-10. R1.1 licence clarity is a manual review

**Symptom.** R1.1 defaults to "partial" because the rubric is honest about
licence clarity needing a human assessor. Will stay partial until:
- A LICENSE file exists in the repo root, AND
- The ADNI DUA is referenced in a CITATION / DATA_USAGE doc, AND
- Hajer signs off.

**Owner.** Oğuzhan + Hajer; not a code task.

---

## P2 — Tooling improvements

### B-11. mmdc not installed; mermaid.ink fallback in use

**Symptom.** F1, F2 render via the public `mermaid.ink` HTTPS service.
Works fine but means: (a) needs network, (b) image quality depends on a
third-party renderer, (c) reproducibility hash will differ between runs
if mermaid.ink upgrades its SVG output.

**Fix options.**
- Install mmdc once: `npm i -g @mermaid-js/mermaid-cli`. Offline +
  deterministic.
- Pin mermaid version explicitly via the `MAKO_MERMAID_BACKEND=mmdc` env
  var when offline rendering matters (e.g. paper submission).
- For the thesis defense / submission, re-render with a pinned mmdc and
  commit the SVGs.

**Recommendation.** Install mmdc on the machine that produces the
publication artefacts. Keep mermaid.ink fallback for daily dev use.

---

### B-12. step 24's pipeline integration uses nested config keys

**Symptom.** `execute_alzkb_bridge` originally indexed `config['neo4j']['uri']`
but `env_loader.load_config()` produces flat `config['neo4j_uri']`. We
patched it to accept both shapes; `pipeline.py` may still pass the wrong
shape on a full pipeline run.

**Fix.** Verify `pipeline.py::_execute_alzkb_bridge` (around line 600)
constructs a config dict step 24 understands. Add a unit test that runs
`execute_alzkb_bridge` against a fake connector with the env_loader-shape
config.

**Owner.** Pipeline maintainer.

---

## P3 — Future / nice-to-have

### B-13. **Comprehensive thesis report generator (USER REQUEST)**

**Goal.** A single command that consumes every metric output and the
existing step-29 EDA figures, and produces a thesis-ready report (Markdown
+ PDF) the user can fold into their thesis chapter.

**Inputs.**
- `outputs/validity_reports/kg_validity_<latest>.{json,md}` — Sultan's gate result
- `outputs/metrics/semantic_density.json` — node + edge URI coverage, per-label, per-edge-type breakdown
- `outputs/metrics/fair_score.json` — 13 FAIR principles + by-dimension averages
- `outputs/metrics/alzkb_alignment.json` — per-category strong-match counts
- `outputs/metrics/step_audit.csv` — per-step nodes_touched / edges_added / runtime / fair_delta / density_delta (currently empty rows; populate after snapshots)
- `outputs/metrics/runner_summary.json` — last run timestamp + overall status
- `outputs/eda_figures/01_node_distribution.{svg,png}` through `15_relationship_schema.{svg,png}` — step 29's 15 EDA figures
- `outputs/eda_figures/eda_statistics.json` — step 29's raw stats
- `outputs/eda_figures/mermaid_*.mmd` — KG schema, data flow, ontology layer
- `paper_outputs/f1_dependency.svg` through `f5_alignment.svg` — the 5 paper figures (where rendered)

**Output.**
- `outputs/thesis_report/thesis_report.md` — long-form Markdown with embedded SVG/PNG references and full metric tables
- `outputs/thesis_report/thesis_report.pdf` — same content rendered for read-only sharing
- `outputs/thesis_report/sections/<section>.md` — per-chapter slices the user can copy-paste into the thesis LaTeX

**Suggested sections** (mirroring the thesis evaluation chapter):
1. **Executive summary** — overall validity result, headline FAIR score, headline AlzKB alignment (3 numbers, 1 paragraph each).
2. **KG state at a glance** — node + edge counts, schema diagram, the step-29 KG summary dashboard (`14_kg_summary_dashboard`).
3. **Sultan's validity gate** — full assertion-by-assertion table from the validity Markdown report; flag any FAIL with a recommended fix from BACKLOGS.md.
4. **Semantic density** — aggregate + per-label + per-edge-type, with the most density-bearing labels (Diagnosis, CognitiveAssessment, Visit, BrainRegion) highlighted; reference step-29's `10_ontology_coverage` for the heatmap view.
5. **FAIR scoring** — 13 principles in a table, per-dimension averages, F3 SVG embedded; commentary on the partial principles (R1.1, R1.2) with cross-refs to BACKLOGS items B-09, B-10.
6. **AlzKB alignment** — 4×2 matrix (with N/A treatment for Gene), F5 SVG embedded; explicit mention of B-08 (Phenotype gap).
7. **Methodology — column-to-concept mapping** — load `ontology/mappings/index.csv`, render as a paginated supplementary table.
8. **Step audit** — per-step migration table; flag empty rows and link to B-07 (snapshots).
9. **EDA panels** — embed every step-29 figure with a one-paragraph caption derived from its filename.
10. **Methodology — paper figures** — F1-F5 with captions explaining each.
11. **Limitations & future work** — every P2/P3 item from this BACKLOGS.md as bullet points.

**Implementation sketch.**
- New file `metrics/thesis_report.py` (or `figures/thesis_report.py`).
- Parses the JSON / CSV / SVG inputs.
- Uses Jinja2 (or a hand-rolled f-string template) to produce the Markdown.
- Optional: render to PDF via `pandoc` (already used elsewhere in the
  project? — verify) or `reportlab` + `svglib` (already in
  `requirements.txt` per the project context, used by step 28's thesis
  figures).
- Hooks into `main.py` as a new phase (after figures): `python main.py
  --thesis-report` or `python main.py --report`.

**Acceptance criteria.**
- Single command produces a self-contained Markdown that opens cleanly in
  GitHub / VS Code / Obsidian.
- Every claim in the report has a JSON / CSV / SVG citation (footnote style).
- PDF version preserves all images.
- Re-running on a fresh metric-pipeline output produces an updated report
  in <30s.

**Owner.** Oğuzhan, with Claude assistance. Defer until the BACKLOGS P0
items (B-01, B-02, B-03) are resolved so the report doesn't reflect stale
or misleading data.

---

### B-14. Compare with step 28's thesis figures

`steps/step28_thesis_figures.py` already exists and produces thesis
figures. The new `figures/` package may overlap. Audit step 28 and either:
- merge step 28's outputs into the new figure pipeline, or
- explicitly document what step 28 produces vs what F1-F5 produce, in
  the c7_plan_v2 docs.

---

### B-15. Step audit — populate after snapshots arrive

`outputs/metrics/step_audit.csv` is currently empty (header only). Once
B-07 lands and `semantic_density_per_step.json` + `fair_score_per_step.json`
exist, the audit will auto-populate from `metrics/step_audit.py`. Verify
the column-by-column shape matches what T2 in the C7 paper expects.

---

## P0 — Publication blocker

### B-16. Numerical reconciliation across snapshots — the report cites multiple stale sources at once

**Severity.** P0 — every figure and table in the evaluation report needs
to cite the same graph-state snapshot before the C7 paper can be
submitted. Currently it does not, and several measured values disagree
with each other and with PHASE1 ground truth.

**Symptom.** A cross-check of the generated PDF against
`docs/infrastructure/history/PHASE1_SCHEMA_MIGRATION.md`,
`docs/infrastructure/IMPLEMENTATION_PLAN.md`, the IEEE Big Data 2025
manuscript, and the C7 contribution table found six concrete
discrepancies:

| ID | Issue | Locations | Magnitude |
|---|---|---|---|
| B-16a | **Biomarker LOINC coverage** mismatch | PHASE1 says 100% (9,467/9,467); Figure 4.1 heatmap shows 79%; per-label table reports 9,467/12,008 = 78.84%. PHASE1 was true at migration time but is now stale because the Biomarker pool has grown beyond the originally-mapped LOINC subset (CSF only). | High — direct claim in C7 contribution table. |
| B-16b | **OntologyConcept count** disagreement across the same report | Dashboard (Figure 2.1): 51; Figure 9.1 bar chart: ~22; A3 validity row: 51 (17 SNOMED + 10 LOINC + 14 UBERON + 5 HPO + 5 ICD-10); PHASE1: 47 + 5 = 52. The Figure 9.1 chart and the dashboard cannot both be right. | High — figure rendered from a different snapshot than the metric tables. |
| B-16c | **Visit count drift** between PHASE1 and live | PHASE1 (Feb 2026): 30,267 Visit nodes; live dashboard (May 2026): 33,800. Plausibly real ingestion since Feb, but the snapshot date is not documented anywhere in the report. | Medium — fixable by stamping the canonical snapshot date. |
| B-16d | **IS_A edge count drift** | PHASE1: 25 IS_A edges (9 SNOMED + 13 UBERON + 3 HPO); live A4 row: 27. Probably real growth from step 19/20 incremental runs; needs documentation. | Low — small absolute difference. |
| B-16e | **Edge-coverage denominator inconsistency** | Section 4.1's URI-coverage denominator: 1,509,297. Dashboard total relationships: 1,430,527. PHASE1: ~1,235,651. Three different totals across one report. Root cause: `eda_statistics.json` (used by Figure 2.1) and `semantic_density.json` (used by Section 4) are produced by different commands at different times and the report renders both side-by-side. | High — every density / FAIR / coverage number needs a consistent denominator. |
| B-16f | **AlzKBConcept vs OntologyConcept conflation in headlines** | Section 6 says "46 AlzKBConcept nodes materialised". Some readers will compare this to the 51 in the dashboard and conclude the OntologyConcept layer shrunk. They are different labels — the report should state this explicitly in §6. | Medium — copy edit. |

**Root cause.** The report is composed from three independently-produced
JSON snapshots:
- `outputs/eda_figures/eda_statistics.json` (from `steps/step29_kg_eda.py`)
- `outputs/metrics/semantic_density.json` (from `metrics/semantic_density`)
- `outputs/metrics/fair_score.json`, `outputs/metrics/alzkb_alignment.json`,
  validity JSONs (from `metrics/runner`)

Each is produced by a different invocation, possibly minutes or hours
apart, against a graph that may have changed between runs. There is no
mechanism guaranteeing the snapshots are temporally aligned.

**Fix proposal.**
- **Step 1.** Implement `metrics/reconcile.py` — a single-transaction
  Cypher batch that runs every canonical query the report needs, writes
  one ``outputs/metrics/canonical_snapshot.json`` with a wall-clock
  timestamp, and reports the **canonical** numbers for every quantity
  cited in the evaluation report.
- **Step 2.** Update `metrics/thesis_pdf.py` and `metrics/thesis_report.py`
  to prefer ``canonical_snapshot.json`` as the source of truth when
  present, and to display the snapshot timestamp prominently in the
  report header.
- **Step 3.** Add a per-section footer line ("All numerical values in
  this section are taken from canonical snapshot &lt;timestamp&gt;").
- **Step 4.** For the C7 paper specifically, run `metrics/reconcile.py`
  once, freeze the resulting JSON, and have the paper's `\input{...}`
  numbers reference that frozen snapshot. Subsequent re-runs of the
  metric pipeline produce a *new* snapshot but do not invalidate the
  paper's cited numbers.

**Specific reconciliation Cypher (to live in `metrics/reconcile.py`).**

```cypher
// Aggregate counts
MATCH (n) RETURN count(n) AS node_total;
MATCH ()-[r]->() RETURN count(r) AS edge_total;

// Per-label clinical entities
MATCH (p:Patient)            RETURN count(p) AS patients;
MATCH (v:Visit)              RETURN count(v) AS visits;
MATCH (d:Diagnosis)          RETURN count(d) AS diagnoses;
MATCH (c:CognitiveAssessment) RETURN count(c) AS cog_assessments;
MATCH (b:Biomarker)          RETURN count(b) AS biomarkers_total;
MATCH (b:Biomarker)
  WHERE toUpper(coalesce(b.biomarker_type,'')) CONTAINS 'CSF'
  RETURN count(b) AS biomarkers_csf;
MATCH (b:Biomarker)          WHERE b.loinc_code IS NOT NULL
  RETURN count(b) AS biomarkers_loinc;
MATCH (br:BrainRegion)       RETURN count(br) AS brain_regions;

// Ontology layer
MATCH (o:OntologyConcept)
  RETURN o.source_ontology AS source, count(o) AS n
  ORDER BY source;

// AlzKB layer
MATCH (a:AlzKBConcept)       RETURN count(a) AS alzkb_total;
MATCH ()-[r:SAME_AS]->()     RETURN count(r) AS same_as_total;

// Edge type breakdown
MATCH ()-[r:MAPS_TO]->()        RETURN count(r) AS maps_to;
MATCH ()-[r:IS_A]->()           RETURN count(r) AS is_a;
MATCH ()-[r:CLASSIFIED_AS]->()  RETURN count(r) AS classified_as;

// URI coverage (the denominator-consistency fix)
MATCH ()-[r]->()
  WITH count(r) AS total, count(CASE WHEN r.uri IS NOT NULL THEN 1 END) AS with_uri
  RETURN total, with_uri, toFloat(with_uri) / total AS coverage;
```

**Acceptance.**
- `outputs/metrics/canonical_snapshot.json` exists, contains a single
  timestamp, and lists every canonical count.
- The report header displays the snapshot timestamp.
- Every per-section table number matches the canonical snapshot
  (verified by a CI check that diffs section-rendered numbers against
  the snapshot JSON).
- The Biomarker discrepancy is resolved by separating two distinct
  numbers in the report: total Biomarker count (~12k) and
  LOINC-annotated CSF Biomarker subset (~9.5k). The 100% claim in PHASE1
  / contribution table is updated to reflect that it applies to the CSF
  subset only.
- The PHASE1 history doc is annotated with a "superseded as of
  &lt;date&gt;" footer for the count claims that have drifted.

**Owner.** Oğuzhan, with Claude assistance. Block on this before
submitting the C7 paper.

**Related backlog items.**
- B-02 (stale-JSON guard) — partial fix; B-16 supersedes by addressing
  the source rather than guarding the consumer.
- B-07 (per-step snapshots) — orthogonal; B-16 captures the *current*
  state consistently, B-07 captures *intermediate* states.

---

## P1 — Open gaps against the Hajer Contribution Table (2026-05-09 cross-check)

Each row below is an item from Hajer's `Contribution_Table_updated HB.pdf`
marked "in progress" or "ADD" that is **not yet present in the live graph**.
Identified via cross-check of the contribution-table claims against the
canonical snapshot from `metrics/reconcile.py`. Effort estimates are from
Hajer's own column.

### B-17. Contribution 3 — HPO expansion 5 → 30 concepts

**Source.** HB Contribution Table, Contribution 3, "In progress" status;
HB Ontology Assessment Summary, HPO row: "EXPAND (top priority). 5 → 30
concepts. Link to ADSXLIST + FamilyMember. 1-2 days."

**Current state.** Live graph has 5 HPO `:OntologyConcept` nodes. ADSXLIST
binary symptom columns (anxiety, depression, agitation, wandering,
insomnia, hallucinations, etc.) are not linked to HPO terms. FamilyMember
nodes carry no HPO annotation.

**Fix.**
1. Author `ontology/mappings/adsxlist_to_hpo.csv` with ~15 rules
   (AXANXIET → HP:0000739 Anxiety; AXDEPRES → HP:0000716 Depression;
   AXAGITAT → HP:0000713 Agitation; AXWANDER → HP:0030214 Wandering;
   AXINSOMN → HP:0100785 Insomnia; AXHALLUC → HP:0000738 Hallucinations;
   etc.)
2. Author a new step (e.g. `steps/step30_hpo_expansion.py`) that creates
   `:OntologyConcept` nodes for the new HPO terms and `MAPS_TO` edges
   from the corresponding `ClinicalFinding` or `Visit` nodes.
3. Update `metrics/validity_rubric.yaml` A3 to expect the higher HPO count.

**Required for.** Contribution 7's Phenotype category match rate to rise
above the current 20% (1/5) ceiling. Without HPO expansion the AlzKB
Phenotype alignment will remain at its current weak position.

---

### B-18. Contribution 3 — LOINC vital-sign vocabulary 10 → 16 codes

**Source.** HB Contribution Table, Contribution 3, LOINC row: "Add 6
vital sign codes. Half a day."

**Current state.** Live graph has 10 LOINC `:OntologyConcept` nodes (all
cognitive-assessment / CSF-biomarker codes). VITALS source-table columns
exist but no LOINC vocabulary covers them.

**Fix.** Add the six codes from HB's spec:
- systolic BP — LOINC 8480-6
- diastolic BP — LOINC 8462-4
- weight — LOINC 29463-7
- height — LOINC 8302-2
- heart rate — LOINC 8867-4
- BMI — LOINC 39156-5

Author `ontology/mappings/vitals_to_loinc.csv`; extend
`steps/step20_ontology_layer.py` (or new step) to materialise these
`:OntologyConcept` nodes and link `:Biomarker`-or-VITALS nodes via
`MAPS_TO`.

**Effort.** Half a day per HB.

---

### B-19. Contribution 3 — Comorbidity extraction from MEDHIST

**Source.** HB Contribution Table, Contribution 3, "Comorbidity
extraction" sub-bullet.

**Current state.** No `:Comorbidity` label exists in the graph. MEDHIST
category-level flags (cardiovascular, psychiatric, neurological,
endocrine) are not lifted into structured nodes.

**Fix.** Author a new step that scans MEDHIST rows, creates
`:Comorbidity` nodes keyed by the SNOMED-CT category code, and connects
them to `:Patient` via `HAS_COMORBIDITY` edges. SNOMED-CT mappings stay
at category granularity per HB's scope note.

**Effort.** Estimated 1 day.

---

### B-20. Contribution 5 — Biolink Model predicate alignment

**Source.** HB Contribution 5, "In progress" status; HB Ontology
Assessment Summary, Biolink Model row: "ADD. biolink_category on all 17
node types via batch Cypher. Half a day."

**Current state.** Relationships carry RO URIs (`r.uri = 'ro:RO_...'`)
but no `r.biolink_predicate`. Node labels carry no `biolink_category`
property. The semantic-density `edge_uri_properties` array includes
`biolink_predicate` in anticipation; the property is simply never set.

**Fix.** Author a one-off batch Cypher that sets:
- `r.biolink_predicate` per relationship type using the
  Biolink-Model 4.x predicate map (e.g. HAS_DIAGNOSIS → `biolink:has_phenotype`,
  HAS_BIOMARKER → `biolink:has_biological_role`).
- `n.biolink_category` per node label (e.g. Patient → `biolink:Patient`,
  Diagnosis → `biolink:Disease`).

Update `ontology/mappings/relationship_to_ro_uri.csv` with a new
column or sibling file documenting the Biolink predicate per rel type.

**Effort.** Half a day per HB.

---

### B-21. Contribution 7 — MONDO + DOID wiring

**Source.** HB Ontology Assessment Summary, MONDO and DOID rows: "ADD.
Wire up existing codes. 2-3 hours" and "ADD. 3 mappings. Half a day".

**Current state.** Diagnosis nodes have `mondo_code` properties set
(e.g. MONDO:0004975 for AD), but no `:OntologyConcept` nodes for MONDO
exist and no `MAPS_TO` edges link Diagnosis to MONDO. DOID is not
integrated at all.

**Fix.**
1. Materialise MONDO `:OntologyConcept` nodes from the existing
   `mondo_code` property values (zero-cost — Cypher batch).
2. Add MAPS_TO edges Diagnosis → MONDO OntologyConcept.
3. Add 3 DOID OntologyConcept nodes (AD = DOID:10652, dementia =
   DOID:1307, MCI) with MAPS_TO edges from the corresponding
   Diagnosis nodes.

**Required for.** Contribution 7's "Source ontologies: 5 → 10" target
and the OntologyConcept count target (52 → 90-110). Currently we are at
5 source ontologies and 51 OntologyConcept nodes.

**Effort.** Estimated half a day total.

---

### B-22. Contribution 6 — Patient ontology trade-off matrix

**Source.** HB Contribution 6, "Patient ontology design: 3 options
compared (custom OWL 2 vs composite reuse vs lightweight hybrid)".

**Current state.** No formal trade-off matrix written. The current
graph uses a lightweight hybrid (`:Patient` label with `rdf_type =
'ncit:C16960'`), but the comparison against the other two design
options is not documented anywhere.

**Fix.** Author a section in `docs/final_report/c7_plan_v2/` (suggest
`PATIENT_ONTOLOGY_DESIGN.md`) with a 3×4 matrix: option × (rigour,
effort weeks, adoption, FAIR-score-projection) plus a one-paragraph
rationale per choice. Reference the chosen option in the methodology
section of the C7 paper.

**Effort.** A few hours.

---

### B-23. Contribution 7 expansion targets — OntologyConcept and IS_A

**Source.** HB Contribution 7 metrics:
- "OntologyConcept nodes: 52 → 90-110 (target)"
- "IS_A edges: 27 → 50-60 (target)"
- "Source ontologies: 5 → 10 (+100%)"
- "Node types with ontology property: 6/17 → 10/17"

**Current state.**
- OntologyConcept: 51 (against 90-110 target — short by ~50%)
- IS_A: 27 (against 50-60 target — short)
- Source ontologies: 5 (against 10 target — short by 50%)
- Node types with ontology property: 6 (against 10/17 target — short)

**Fix.** The expansion targets are met *as a consequence of* completing
B-17 (HPO), B-18 (LOINC vitals), B-20 (Biolink), B-21 (MONDO+DOID). No
separate work item — the targets are emergent.

---

### B-24. OntoQA → FAIR scope decision documentation

**Source.** HB Contribution Table is built around OntoQA (CR, RR, AR,
IR). HB's "Open Questions for Friday Meeting" question 1 asks whether
OntoQA is the right framework; the meeting decided to use FAIR +
semantic density instead (recorded in
`docs/final_report/c7_plan_v2/meeting_notes.md`).

**Current state.** The Contribution Table PDF in the user's downloads
still presents OntoQA as the headline framework. The c7_plan_v2 docs
(IMPLEMENTATION_PLAN.md) reflect the FAIR-only decision. The two
documents are inconsistent.

**Fix.** Either (a) update the Contribution Table to reflect the
post-Friday-meeting decision (replace OntoQA section with FAIR and
semantic density), or (b) annotate the Contribution Table with a header
note pointing readers to c7_plan_v2/IMPLEMENTATION_PLAN.md for the
current methodology.

**Note.** This is purely a documentation reconciliation, not a code
gap. No measured values are affected.

---

## Resolved

| ID | Title | Resolution |
|---|---|---|
| **B-01** | ALZKB_RELATES_TO no URI | Step 24 now sets `r.uri` from a `CASE rel.type WHEN ...` map at MERGE time + back-fill query for legacy edges. `relationship_to_ro_uri.csv` synced. |
| **B-02** | Stale metric JSONs after failed validity | `phase_figures` now reads `runner_summary.json` and skips F3/F5 when the upstream metric isn't `status=ok` in the most recent run. `--ignore-validity` opts out of staleness gating. |
| **B-03** | A5 strictness — types_below caused FAIL even when type_coverage ≥ threshold | `check_a5` now treats `types_below` as informational; only `type_coverage < type_coverage_threshold` is blocking. |
| **B-04** | Step 18 needs to run after every edge-creating step | `pipeline.py` now invokes step 18 *twice*: once at its original position, again as a finalization pass after step 29. Idempotent — only sets `r.uri` where IS NULL. |
| **B-05** | `is_hierarchy_root` Cypher warning | Dropped the property fallback from `check_a6`. Source of truth is the rubric YAML's `hierarchy_roots` URI list. |
| **B-06** | Validity report retention | `main.py` now prunes old reports at end of every run: keeps last 5 + every PASS, deletes the rest. |
| **B-08** | AlzKB Phenotype 0/5 | Extended `SAME_AS_RULES` in step 24 with HPO mappings (Dementia, Memory impairment, Mental deterioration, Behavioural abnormality, neurodegeneration / neuroinflammation proxies). Re-run step 24 to populate. |
| **B-12** | step 24 config shape | `_resolve_neo4j_creds` accepts both flat (env_loader shape) and nested (`config['neo4j']`) shapes. New regression test in `tests/test_step24_creds.py`. |
| **B-13** | Thesis report generator (the user's main ask) | `metrics/thesis_report.py` + `main.py --report`. 11 sections, embeds every metric JSON + step-29 EDA figure + paper figure + column-to-concept index. Per-section .md slices for direct LaTeX paste. Optional pandoc PDF. 11 tests covering full / missing / partial input scenarios. |
