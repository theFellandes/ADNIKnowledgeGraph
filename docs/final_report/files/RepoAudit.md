# Repository Audit — Cross-Verification of Thesis Claims vs. Live Repo

**Date:** 2026-05-15
**Audited paths:** `D:\Programming\Python\ADNIKnowledgeGraph\` (main branch HEAD plus uncommitted working tree)
**Audited against:** the contribution table you uploaded (Hajer's HB version)
**Why this exists:** before adding any new content to the thesis, every claim must be verifiable against the code, the validity report, or the metric output JSON. Half the thesis edits I prepared in the previous round were drafted from the contribution table alone; the contribution table includes both *current state* and *planned state*, and I conflated them. This document separates the two.

---

## TL;DR

The thesis numbers I have already committed to are **all accurate** against the live graph as measured on 2026-05-09 at 18:35 UTC. The previous round's edits that I started but did not finish (the ontology-selection rubric I drafted) **were overclaiming**: they listed Gene Ontology, MONDO, DOID, and Biolink Model as integrated when the repo says they are proposed but not yet implemented. I have reverted that table.

The repo confirms the thesis. The contribution table promises more than the repo currently delivers. Two things to add to the thesis are well-supported (the rubric table restricted to *current-state* candidates, and the in-progress Phase 2 enrichment paragraph as future work); two things require user input (a worked Cypher query and an OntoQA computation script that does not exist yet); and one thing requires a git push (multiple metric / ontology / test files exist locally but are untracked, undermining the public-reproducibility claim).

---

## Section 1 — Thesis claims that match the repo exactly

For every assertion below, I verified the source code or the metric JSON. **No edit needed.**

### Steps 17–20

| Thesis claim | Repo verification | Status |
|---|---|---|
| Step 17 adds 12 constraints and 15 indexes | `steps/step17_apply_constraints.py`: 5 core + 7 composite = 12 constraints; 15 `PERFORMANCE_INDEXES` defined | ✅ |
| Step 18 annotates Diagnosis, CognitiveAssessment, Biomarker, BrainRegion, Patient, Visit | `steps/step18_add_ontology_properties.py` line 27–80 enumerates all six labels | ✅ |
| Step 19 hits the WHO ICD REST API with JSON fallback | `steps/step19_icd10_integration.py` lines 31–80 implement OAuth2 + `STATIC_MAPPING_FILE` fallback | ✅ |
| Step 20 materialises the OntologyConcept layer with MAPS_TO and IS_A | `steps/step20_ontology_layer.py` docstring + SNOMED/LOINC/UBERON/HPO concept lists | ✅ |

### Validity rubric (A1–A7)

The May 9, 18:35 run (`outputs/validity_reports/kg_validity_20260509T183539Z.json`) returns `PASS` on every assertion. The measured values match every Chapter 4 number in the thesis:

- A1: 59 constraints, 153 indexes ✅
- A2: per-label coverage 1.0 on Diagnosis, CognitiveAssessment, Biomarker (CSF subset), BrainRegion ✅
- A3: OntologyConcept counts — SNOMED-CT 17, LOINC 10, UBERON 14, HPO 5, ICD-10 5, total 51 ✅
- A4: MAPS_TO, IS_A, CLASSIFIED_AS all populated with URIs ✅
- A5: 56 rel types total, 51 annotated, 5 in allowlist, type_coverage 1.0 ✅
- A6: 0 orphan OntologyConcept (17 hierarchy roots exempt) ✅
- A7: 0 PTID violations of `381_S_*` exclusion across 2,638 patients ✅

### FAIR scores (May 9, 18:35 run, `outputs/metrics/fair_score.json`)

| Principle | Repo measured | Thesis | Status |
|---|---|---|---|
| Overall | 0.9231 | 0.9231 | ✅ |
| Findable | 1.0 | 1.0 | ✅ |
| Accessible | 1.0 | 1.0 | ✅ |
| Interoperable | 1.0 | 1.0 | ✅ |
| Reusable | 0.6667 | 0.6667 | ✅ |
| F1 coverage | 0.9754 | 0.9754 | ✅ |
| F2 avg_properties | 12.2479 | 12.25 | ✅ |
| F4 index_count | 153 | 153 | ✅ |
| I1 coverage | 0.9957 | 0.9957 | ✅ |
| R1.2 coverage | 0.5536 | 0.5536 | ✅ |

### AlzKB alignment (May 9, 18:35 run, `outputs/metrics/alzkb_alignment.json`)

| Quantity | Repo measured | Thesis | Status |
|---|---|---|---|
| AlzKBConcept nodes | 46 | 46 | ✅ |
| SAME_AS edges (total) | 7 | 7 | ✅ |
| Disease strong matches | 2 / 17 (11.76%) | 2 / 17 (11.8%) | ✅ |
| Anatomy strong matches | 2 / 14 (14.29%) | 2 / 14 (14.3%) | ✅ |
| Phenotype strong matches | 1 / 5 (20.0%) | 1 / 5 (20.0%) | ✅ |
| Gene category | not_implemented: true | n/a, out of scope | ✅ |

The earlier May 9, 16:31 run had `Phenotype: 0 strong matches` and `same_as_edge_total: 5`; the later run added one Phenotype match and two additional SAME_AS edges (likely the manually curated AD→DOID and HPO→AlzKB-Symptom links). The thesis uses the later run, which is the right one.

### Mapping rule inventory (`ontology/mappings/`)

| File | Repo line count (excluding header) | Thesis claim | Status |
|---|---|---|---|
| biomarker_to_loinc.csv | 5 | 5 | ✅ |
| brain_region_to_uberon.csv | 12 | 12 | ✅ |
| cognitive_to_loinc.csv | 6 | 6 | ✅ |
| diagnosis_to_snomed_icd10.csv | 25 | 25 | ✅ |
| relationship_to_ro_uri.csv | 52 | 52 | ✅ |
| **Total** | **100** | **100** | ✅ |

There is also an `index.csv` (100 rows) which is a consolidated view; not separately cited in the thesis and that is fine.

### A5 allowlist precision

The rubric YAML allowlist contains 8 entries: `BATCH_INGESTED_BY`, `DEFINES_EVENT_TYPE`, `HAS_DOMAIN`, `HAS_SUMMARY`, `HAS_TIMELINE`, `LOADED_FROM`, `MATCHES_PATTERN`, `PROCESSED_BY`. The thesis lists 5: `HAS_TIMELINE`, `HAS_SUMMARY`, `MATCHES_PATTERN`, `HAS_DOMAIN`, `DEFINES_EVENT_TYPE`. The 3 missing from the thesis (`BATCH_INGESTED_BY`, `LOADED_FROM`, `PROCESSED_BY`) are *provenance* edge types reserved in the rubric but **not currently materialised in the graph** — the May 9 validity report's `per_type` list confirms only the 5 thesis-cited types appear as edges. The thesis is therefore accurate for the present graph snapshot. ✅

---

## Section 2 — Discrepancies between the contribution table and the live repo

The contribution table you uploaded includes content that the repo does **not yet support**. If I had added these to the thesis, I would have overclaimed.

### Discrepancy 1 — OntoQA framework is described but not implemented

The contribution table (page 1–2 and page 9) describes the OntoQA evaluation framework (Tartir et al., 2005) with four metrics: Class Richness, Relationship Richness, Attribute Richness, Inheritance Richness. The "Tentative baseline numbers" on page 9 are explicitly marked as placeholders:

> "These numbers are placeholders based on a structural estimate of the graph; they will be replaced with measured values from the live Neo4j instance once the OntoQA computation script is run end-to-end."

**Repo check.** I searched `metrics/` for an OntoQA implementation. No file matches. The metric scripts that exist are `validity.py`, `fair.py`, `semantic_density.py`, `alzkb_alignment.py`, `step_audit.py`, `reconcile.py`, `snapshots.py`. **There is no `ontoqa.py`.**

**Implication.** If I had added OntoQA as a fifth indicator family in Chapter 4 with the page-9 tentative numbers, I would be reporting unverified placeholder data as if measured. The thesis should mention OntoQA only as a planned framework, with the four formulas defined and the tentative numbers labelled as such, in either the Limitations or Future Work section.

### Discrepancy 2 — Gene Ontology integration is described but not connected

The contribution table page 3–4 describes a Gene node + 8–10 GO OntologyConcepts + ENCODES + PARTICIPATES_IN relationships for APOE. Status on page 8: "Proposed — no pipeline implementation yet."

**Repo check.**
- `steps/step20_ontology_layer.py` does NOT create Gene nodes or GO OntologyConcepts.
- `ontology/alzkb_cache/alzkb_concepts.json` DOES have 15 Gene entries (APOE, APP, PSEN1, PSEN2, MAPT, TREM2, CLU, BIN1, ABCA7, CD33, CR1, SORL1, ADAM10, BACE1, BDNF). These are AlzKBConcept nodes only — they have no SAME_AS edges to anything on the patient-graph side because there is nothing on the patient-graph side to bridge to.
- The `outputs/metrics/alzkb_alignment.json` reports `Gene: not_implemented: true`.

**Implication.** Thesis is correct to treat Gene as out of scope. The 15 AlzKBConcept Gene entries are scaffolding for the next iteration but they are not edges; they do not count for the alignment metric.

### Discrepancy 3 — HPO expansion 5 → 30 is in progress

Contribution table page 3 and page 7: "HPO 5 concepts → target 30, link to ADSXLIST + FamilyMember, 1–2 days work."

**Repo check.** `step20_ontology_layer.py` defines 5 HPO concepts; the validity report A3 reports HPO: 5. The expansion has not run yet.

**Implication.** Thesis is correct to report HPO at 5 concepts. Adding the planned 30 to the thesis would be premature.

### Discrepancy 4 — LOINC vital signs 10 → 16 is in progress

Contribution table page 3 specifies six new LOINC codes (systolic BP 8480-6, diastolic 8462-4, weight 29463-7, height 8302-2, heart rate 8867-4, BMI 39156-5).

**Repo check.** `step20_ontology_layer.py` shows 10 LOINC concepts. Validity report A3 confirms LOINC: 10.

**Implication.** Thesis is correct to report LOINC at 10 codes.

### Discrepancy 5 — MONDO codes exist as properties but no OntologyConcept layer

Contribution table page 7: "mondo_code properties exist on Diagnosis nodes. No OntologyConcept nodes or MAPS_TO edges. Decision: ADD."

**Repo check.** Confirmed in `step18_add_ontology_properties.py` — the DIAGNOSIS_MAPPINGS dict on line 27 includes `"mondo_code"` for every diagnosis. But Step 20 does not create MONDO OntologyConcepts.

**Implication.** Thesis does not currently mention MONDO. Could add a one-line note that mondo_code properties exist on Diagnosis nodes as future-work scaffold, but the OntologyConcept layer entries are pending.

### Discrepancy 6 — DOID, Biolink Model are decided ADD but not implemented

Contribution table page 7: DOID — "ADD. 3 mappings (AD, dementia, MCI). Half a day." Biolink — "ADD. biolink_category on all 17 node types via batch Cypher. Half a day."

**Repo check.** No DOID OntologyConcept entries in step 20. No `biolink_category` property added in step 18. Both are decided but not yet executed.

**Implication.** Thesis is correct to not claim these. They belong in §5.4 Future Work.

### Discrepancy 7 — Causal discovery prototypes exist on disk but are uncommitted

| File | In main branch? | Status |
|---|---|---|
| `steps/step21_extract_causal_features.py` | No (untracked) | Prototype, not run |
| `steps/step22_causal_discovery.py` | No (untracked) | Prototype, not run |
| `steps/step23_embed_causal_edges.py` | No (untracked) | Prototype, not run |
| `steps/step25_validate_causal.py` | No (untracked) | Prototype, not run |
| `steps/step26_dowhy_inference.py` | No (untracked) | Prototype, not run |
| `steps/step27_final_stats.py` | No (untracked) | Prototype |
| `causal/` directory | Yes (committed) | Data-extraction scaffold |

The thesis's §5.4 paragraph "Data-driven refinement of graph edges (including causal discovery)" cites a "prototype data-extraction code retained in the project repository under `causal/`". That is accurate — `causal/` is committed; the actual discovery scripts are not. **The thesis correctly scopes causal discovery to future work.**

### Discrepancy 8 — A bigger AlzKB role for the bridge report than the validity metric counts

`ontology/alzkb_cache/alzkb_bridge_report.json`:
```
concepts_created: 46
same_as_edges: 7        ← matches validity metric
manual_same_as: 19      ← curated candidates
fuzzy_same_as: 2        ← string-similarity candidates
```

The alignment metric's `same_as_edge_total: 7` is the count of `:SAME_AS` edges that exist in Neo4j. The `manual_same_as: 19` and `fuzzy_same_as: 2` are *candidate* counts considered by the bridge routine; only the 7 strong-confidence pairs were committed as actual edges.

**Implication.** The thesis citing "7 SAME_AS edges" is correct. If you want to add the confidence-level breakdown to §4.6 (helpful to defenders), that is a real number from the bridge report. Not required.

---

## Section 3 — Repo state issues you should fix before defence

These are not thesis-text issues; they are *artefact* issues that affect the Claim 3 reproducibility argument.

### Issue 3.1 — Many cited artefacts are untracked in git

`git status` on `main` shows the following directories / files exist locally but are **not committed**:

- `metrics/` (every metric script and YAML the thesis cites)
- `ontology/mappings/` (the 100-rule CSV inventory)
- `ontology/alzkb_cache/` (the bridge output JSON)
- `paper_outputs/` (f1_dependency, f2_schema, f3_fair, f5_alignment — all four figures the thesis embeds)
- `tests/test_alzkb_alignment.py`, `tests/test_column_to_concept.py`, `tests/test_fair.py`, `tests/test_figures.py`, `tests/test_semantic_density.py`
- `main.py`
- `Thesis/` (the thesis source itself)
- `figures/`

**Why this matters.** Thesis §5 Claim 3 (reproducibility) cites:
- "the column-to-concept mapping inventory is version-controlled under `ontology/mappings/`"
- "metrics/validity_rubric.yaml"
- The GitHub URL `https://github.com/theFellandes/Alzheimer's Disease Knowledge Graph`

If a defender clones the public repo and finds none of these files, the reproducibility claim collapses. **Action:** before defence, run `git add metrics/ ontology/mappings/ ontology/alzkb_cache/ paper_outputs/ tests/ main.py && git commit && git push`.

### Issue 3.2 — Modified files not committed

`git status` shows these have local changes not committed:

- `steps/step18_add_ontology_properties.py`
- `steps/step24_alzkb_bridge.py`
- `steps/step28_thesis_figures.py`
- `pipeline.py`
- `docs/thesis_references.bib`
- Five other step files

**Action:** review each diff, commit the genuine improvements, discard or stash any debug edits.

### Issue 3.3 — Outdated thesis.tex copy in outputs/

`outputs/thesis_report/thesis.tex` (1872 lines, May 15 11:59) is a **different, older** thesis that still has "Phase 3: Causal Discovery and Integration" as a real section. The thesis you have been editing is at `Thesis/OğuzhanGüngör_Tez (1)/thesis.tex` (1470 lines) and is the **scoped-down version** (causal discovery moved to future work).

**Action:** decide whether the `outputs/thesis_report/thesis.tex` is still needed. If yes, regenerate it from the current thesis source. If no, delete it to avoid confusion.

### Issue 3.4 — A5 was failing as of the 16:42 run; fixed by 18:35

`BACKLOGS.md` documents a known bug "B-01" where Step 24's `ALZKB_RELATES_TO` edges were below the A5 per-type threshold (0% URI coverage on 18 edges). The 16:42 validity report failed A5; the 18:35 run passes A5 with `ALZKB_RELATES_TO` at 100% URI coverage.

This means **between 16:42 and 18:35 on May 9, you fixed Step 18 to add URIs to `ALZKB_RELATES_TO` edges**, or you allowlisted them, or both. The current state passes. **Confirm before defence:** the fix is committed and is reproducible from a clean clone.

---

## Section 4 — What I will add to the thesis, and where, after this audit

Everything below is now grounded in *what the repo actually contains*, not in what the contribution table promises. I will not add anything not in this list without further verification.

### Tier A — Safe to add now, repo-backed

1. **Ontology-selection rubric table (§3.5).** Rewritten from the previous overclaiming draft. The "Decision" column will now read `KEEP` only for ontologies the repo actually integrates (SNOMED-CT, LOINC, UBERON, ICD-10, HPO, RO). GO, MONDO, DOID, Biolink Model become `ADD (future work)` with a forward reference to §5.4. The `EXCLUDE` rows (ICD-11, UMLS, LogMap, FOAM, BioPortal Annotator, HL7 FHIR, OpenEHR) stay as drafted because the contribution table's rationale matches the standard reasoning.

2. **Comparator table (§5.2).** Five rows: AlzKB (Romano 2024), AD-DPC (Spassov 2024), ADKG (Yang 2025), Dobreva 2025 unified framework, this thesis. Columns from cited papers and from the live validity / FAIR JSONs.

3. **Step 17–20 description sentence in §3.5.** A two-sentence paragraph naming the four steps explicitly (consistent with the contribution table and with what `steps/step17` through `step20` actually do).

4. **Phase 2 enrichment in-progress paragraph in §5.4.** HPO 5→30, LOINC 10→16 vital signs, MONDO OntologyConcept layer, DOID three-mapping bridge, Biolink batch-category — each named with the contribution-table's working-day estimate.

5. **Declaration of originality.** One sentence in the acknowledgements.

### Tier B — Conditional on user verification

6. **OntoQA paragraph in §5.4 (Future Work).** Names the framework, gives the four formulas, references the contribution table's tentative baseline values as targets, and says the OntoQA computation script is scheduled. No measured numbers will be quoted as evidence.

7. **Confidence-level breakdown for SAME_AS in §4.6.** Adds one sentence on the manual_same_as: 19, fuzzy_same_as: 2, strong-confidence: 7 split. This is repo-backed.

### Tier C — Cannot do alone, needs you

8. **Worked cross-graph Cypher query in §4.6.** I will write a syntactically valid query but it should be **executed** by you against the live graph and the actual returned rows pasted in. I will leave a `\begin{verbatim}` block with the query and a placeholder for the rows.

9. **OntoQA computation script.** I can write the script that computes CR, RR, AR, IR from Cypher; you run it; we paste the results into the future-work paragraph as "now measured" instead of "tentative." Out of scope for this turn but I will include it in the script package I deliver.

### Tier D — Will NOT add

10. **GO / MONDO / DOID / Biolink as integrated.** They are not integrated. They are future work. The thesis will say so.

11. **HPO at 30 concepts, LOINC at 16 codes.** They are at 5 and 10 respectively in the current graph. The thesis will say so.

12. **Anything backed only by the contribution table without repo verification.** The contribution table is a forward planning document; the thesis must describe what is built.

---

## Section 5 — What I need from you to proceed

1. **Confirm Tier A items 1–5 are OK to add** (about an hour of editing, all repo-verified).
2. **Confirm Tier B items 6–7 are OK to add** (about thirty minutes).
3. **For Tier C item 8, decide:** do you want me to write a Cypher query you will run, or do you want to write it yourself and paste the result?
4. **For Tier C item 9, decide:** do you want me to write an `ontoqa.py` script for the `metrics/` directory now, or defer to a later session?
5. **Address Issue 3.1** (commit-and-push the untracked artefacts) before defence. This is not a thesis-text change; it is a git operation you do once.

Reply with `OK Tier A and Tier B, defer Tier C` (or whatever subset you want) and I will proceed.