# Ontology Selection, Mapping, and Evaluation for a Multimodal Alzheimer's Disease Knowledge Graph

> **Working title.** "Enrichment" removed per Hajer's note; "Evaluation" added to surface the FAIR and semantic density measurement work. Alternative title if a stronger evaluation framing is wanted: *A Metrics-Driven Methodology for Ontology Selection and Cross-KG Alignment in a Multimodal Alzheimer's Disease Knowledge Graph*.

> **Project rename.** The project is renamed from CauAD to **MAKO** (Multimodal Alzheimer's Knowledge graph with Ontology grounding) to reflect the shift away from causal discovery as the immediate focus. See `PROJECT_NAME_ALTERNATIVES.md` for the rationale and runner-up names. The IEEE Big Data 2025 paper remains under the CauAD name; the rename only applies to the ongoing ontology paper and the thesis.

---

## Restructuring summary

Per the Friday meeting with Hajer, the seven-contribution table is consolidated into **a single unified contribution (C7)** with four supporting methodological steps. The status of each original item:

| Original | New role | Reason |
|---|---|---|
| C1 (Three-axis evaluation framework) | **Step inside C7** — methodology for selecting which ontologies enter the graph | Foundational but not a paper-level contribution on its own |
| C2 (In-place semantic migration) | **Step inside C7** — graph substrate preparation | Reproducible engineering, not a stand-alone scientific contribution |
| C3 (Semantic enrichment of patient-level data) | **Step inside C7, renamed *Column-to-Concept Mapping*** | Renamed to highlight reproducibility; original "enrichment" framing was vague |
| C4 (Gene Ontology integration) | **Removed** | Not implemented; presenting it would be a fabricated contribution |
| C5 (Relation normalisation with RO URIs) | **Step inside C7** | Literature review needed to confirm whether RO normalisation is treated as a contribution in comparable papers; current default is to demote to a step |
| C6 (Comparative benchmark) | **Future work, separate paper after June 2026** | Will follow C7 once the unified contribution is published |
| **C7 (Vocabulary mismatch and AlzKB alignment)** | **Main paper contribution** | Has standalone scientific value; bridges clinical and molecular AD KGs |

Diagram: the existing functional-dependency figure should be redrawn so that C7 sits at the centre, the four steps feed into it, and C6 sits to the right as a downstream future-work box.

---

## C7 — Cross-Vocabulary Alignment Between a Clinical Multimodal AD Knowledge Graph and the AlzKB Molecular Knowledge Graph

### The problem

CauAD and AlzKB do not share a common language. CauAD uses clinical terminologies (SNOMED-CT for diagnoses, LOINC for lab tests and cognitive assessments, ICD-10 for classification, UBERON for anatomy). AlzKB uses molecular-biological ontologies (DOID for diseases, GO for gene functions, CHEBI for chemicals, HPO for phenotypes, UBERON for anatomy). Without an explicit cross-vocabulary bridge, edges discovered or asserted in one KG cannot be checked against the other, and any future causal validation pipeline (out of scope for this paper, planned as the next step after the master's thesis) is structurally blocked.

The contribution is a reproducible methodology that produces such a bridge for a real ADNI-derived multimodal KG, evaluated quantitatively against a well-known reference KG.

> **Number to verify before submission.** Graph size must be stated from a live `MATCH (n) RETURN count(n)` / relationship count, not from memory. Three different figures are currently circulating across project documents (~407K nodes / ~1.16M edges in the repo `IMPLEMENTATION_PLAN.md`; ~421K nodes / ~1.4M edges in the contribution PDF; the patient count is consistently 2,638). Do not put a node/edge count in the paper until it is measured on the instance the paper reports on. Tracked in `CONVERSATION_HISTORY.md`.

### Scope

The alignment target is the biomarker cause-effect cascade: **Disease, Gene, Phenotype, Anatomy**. Drug and Pathway are explicitly out of scope because the project does not model pharmacological intervention or reaction networks. Acknowledged but not pursued.

### The four methodological steps

#### Step A — Three-axis ontology selection (was C1)

A reproducible procedure for deciding which biomedical ontologies should enter a multimodal clinical KG and which should not. Each candidate is scored on three axes, with the scores fed into an include / exclude / future-work decision.

**Axes:**

1. **Coverage completeness.** Splits T-Box (ontology classes and properties present as schema in the graph) from A-Box (ontology concepts actually annotating instance data). The distinction matters because a concept that exists only as schema does not contribute to query traversal. Example: pre-enrichment, HPO had 5 schema concepts and zero MAPS_TO edges, so its A-Box coverage was 0%.
2. **Interoperability gain.** Three sub-questions answered for each candidate: Does it add new semantic content? Does it improve FAIR or semantic density scores? Does it help align identifiers with AlzKB?
3. **Feasibility.** Working days, API availability, mapping complexity. A candidate that scores high on coverage and interoperability but low on feasibility is logged as future work, not rejected.

**Scope of the comparison.** Ten ontologies (SNOMED-CT, LOINC, UBERON, ICD-10, HPO, ICD-11, UMLS, GO, MONDO, DOID), three mapping tools (LogMap, FOAM, BioPortal Annotator), two clinical-data standards (HL7 FHIR, OpenEHR). The full assessment table is in the appendix.

**What changes from the previous draft.** Hajer's recommendation is to drop OntoQA and use **FAIR** and **semantic density** as the schema-quality metrics. The earlier draft proposed OntoQA (Tartir et al., 2005) as the headline schema-quality framework with FAIR and semantic density as add-ons; that ordering is reversed in the current draft. FAIR and semantic density are the methods; OntoQA is not used. The baseline reference point for the before/after comparison is the **pre-enrichment CauAD graph** (per Hajer's note in the meeting). The "before" state already carries some ontology codes on a few node types, so it is not a true zero, but it is the cleanest comparison conceptually because every step's contribution becomes visible against a real baseline rather than a synthetic one. The trade-off is documented in the methods section.

#### Step B — In-place semantic migration of an existing labeled property graph (was C2)

A reproducible engineering procedure for upgrading an existing labeled property graph to a knowledge graph **without rebuilding it**. This matters because real clinical KGs accumulate years of ETL work, and a rebuild is rarely an option.

**Pipeline:**

- **Step 17** — Composite uniqueness constraints (12 constraints, 15 indexes) on observation nodes to prevent duplicate observation rows on re-ingest.
- **Step 18** — Ontology property annotation on existing nodes (Diagnosis, CognitiveAssessment, Biomarker, BrainRegion, Patient, Visit) via a curated mapping table. No node deletion or re-creation. Properties added: `ontology_uri`, `loinc_code`, `uberon_id`, `snomed_code`, `mondo_code`, `source_table`, `source_column`.
- **Step 19** — ICD-10 hierarchy construction via the WHO ICD-10 REST API with a static JSON fallback for offline reproducibility.
- **Step 20** — `OntologyConcept` layer with `MAPS_TO` and `IS_A` edges, materialising each ontology concept as a first-class node in the graph.

**Why this matters as part of C7.** Without this step, the graph holds string codes inside node properties and cannot be traversed semantically. After this step, every ontology concept is a node, and AlzKB alignment becomes a graph-to-graph match instead of a string match.

**Reproducibility artefact.** The full set of curated mapping tables is committed to the repo (`ontology/mappings/`) so that the procedure can be reproduced on any other ADNI-derived graph or extended to a different clinical dataset.

#### Step C — Column-to-concept mapping for raw clinical observations (was C3, renamed)

The graph holds large amounts of clinical data as raw column values that no ontology can reason over. A binary flag like `AXINSOMN = 1` in `ADSXLIST` means the patient reports insomnia, but the graph does not know that. Column-to-concept mapping turns each such column value into an ontology-grounded entity, connected to the corresponding HPO or SNOMED-CT term via a `MAPS_TO` edge.

**Why "column-to-concept mapping" rather than "semantic enrichment".** The new name says exactly what the procedure does: it takes a column name, applies a curated mapping rule, and produces a concept node attached to the right ontology. The previous name (*semantic enrichment*) hid that this is a deterministic, reproducible transformation rather than an open-ended add-on.

**Sources and targets:**

- `ADSXLIST` — 30 binary symptom columns, of which approximately 15 map cleanly to HPO terms (anxiety, depression, agitation, wandering, insomnia, hallucinations and so on). Map to HPO; link `FamilyMember` nodes with the same flags.
- `MEDHIST` — category-level medical history flags (cardiovascular, psychiatric, neurological, endocrine). SNOMED-CT mappings stay at category granularity. Specific disease codes below the category level are not recoverable from MEDHIST alone and are out of scope for this step. Out-of-scope status is documented in the paper so that reviewers do not expect specific-diagnosis comorbidity nodes.
- `VITALS` — systolic BP (LOINC 8480-6), diastolic BP (8462-4), weight (29463-7), height (8302-2), heart rate (8867-4), BMI (39156-5). LOINC vocabulary breadth grows from 10 to 16 codes.

**Reproducibility focus per meeting note.** The paper publishes the full column-to-concept mapping as an explicit table (one row per source column, one row per target concept, with the mapping rule and the test fixture used to verify it). This is what Hajer asked for under "reproducibility mapping to show originality".

**REST error handling.** Lookups against BioPortal and EBI OLS are network-dependent and occasionally fail. The pipeline uses retry with exponential backoff on 5xx and timeout responses, a local JSON fallback for the ~15 HPO concepts used (cached from a known-good snapshot), and fail-loud logging when a lookup falls through all retries. Status and failure counts are written into the step log and checked by the quality-check phase.

#### Step D — Relation normalisation (was C5, demoted)

Every relationship type in the graph receives a formal URI from the OBO Relation Ontology, and Biolink Model predicate alignment is layered on top.

**Examples.**
`HAS_VISIT` → `RO:0000056` (participates in).
`INDICATES` → `RO:0000059` (correlated with condition).
`HAS_PART` → `RO:0000051`, `PART_OF` → `RO:0000050`.

**Why this is a step rather than a contribution.** Standard practice for OBO-conformant KGs. The paper presents it as a quality-of-service step that makes the graph interoperable with Biolink-aligned tooling, rather than as a novel methodological contribution. **Action item:** check the literature before final submission to confirm that recent papers (Lyu et al. 2025, Romano et al. 2024, Yang et al. 2025) treat RO normalisation as a step rather than a contribution; if any of them treat it as a contribution, restore it.

### Cross-vocabulary alignment with AlzKB (the contribution proper)

This is the part that is not in any of the steps above. With Steps A–D in place, the graph is now ontology-grounded; the next move is to align it identifier-for-identifier with AlzKB so that any node in CauAD has a `owl:sameAs` or `skos:exactMatch` link to the corresponding AlzKB entity where one exists.

**Method.**

- Walk AlzKB's six entity categories (Disease, Gene, Drug, Pathway, Anatomy, Phenotype). Drug and Pathway are out of scope.
- For each in-scope category, run identifier overlap analysis against the corresponding ontology in CauAD: SNOMED-CT and DOID for Disease (via MONDO as a cross-reference hub); UBERON for Anatomy (already shared); HPO for Phenotype; and an explicit not-applicable note for Gene since Gene Ontology integration was not implemented (this is the consequence of removing C4).
- Materialise alignment edges in the graph: `(:Disease)-[:SAME_AS_ALZKB]->(:AlzKBEntity {doid: ...})` etc.
- Report the entity-type strong-match count before and after Steps A–D.

**Expected results.**

| AlzKB category | Pre-Steps A–D | Post-Steps A–D (achieved) | Method |
|---|---|---|---|
| Anatomy | strong (UBERON shared) | strong | direct UBERON match |
| Disease | weak (SNOMED only) | strong | SNOMED → MONDO → DOID via curated map |
| Phenotype | none | strong | HPO column-to-concept mapping (Step C) |
| Gene | none | not applicable | not implemented; documented as known limitation |
| Drug | n/a | n/a | out of scope |
| Pathway | n/a | n/a | out of scope |

So the strong-match count goes from **1 of 4 in-scope categories** to **3 of 4**, with Gene flagged as a known limitation tied to the C4 decision. The Gene gap is the natural follow-up paper.

### Why this is the main contribution

1. The clinical-to-molecular vocabulary mismatch is a real, named obstacle in AD KG work (Romano et al. 2024 acknowledge it; Yang et al. 2025 sidestep it by building from literature only). No prior paper publishes a reproducible alignment procedure on a real patient-derived KG.
2. The four steps are necessary preconditions but not sufficient on their own; the alignment is what makes the rest worth doing.
3. The procedure generalises. The same Steps A–D plus alignment can be applied to any ADNI-derived graph or, with adjustments, any clinical multimodal KG.

---

## Evaluation

### What the paper measures

| Metric family | What it captures | Reported as |
|---|---|---|
| **FAIR** | Findability, Accessibility, Interoperability, Reusability | Per principle, scored against the FAIR maturity model, before / after |
| **Semantic density** | How much of the graph carries ontology grounding | Fraction of nodes / edges with at least one URI, before / after, per step |
| **AlzKB alignment** | Cross-KG matchability | Strong-match count per in-scope entity category |
| **Pipeline reproducibility** | Can someone else run this? | Pass/fail on a fresh container with the JSON fallback |

### Baseline choice

Per Hajer's meeting note: the **pre-enrichment CauAD graph** is the baseline. Each step's contribution to FAIR and semantic density is measured as a delta against the immediately prior state, so the before/after numbers are reported per step, not only at the endpoints. The fact that the baseline is not a true zero (some ontology codes already exist on a few node types) is documented in the methods section as a known property of measuring on a real, evolving graph rather than on a synthetic substrate.

### Open questions for the meeting

1. FAIR scoring methodology: should the FAIR maturity model checklist be applied as binary per principle, or with a three-level scale (no / partial / yes)? The latter is more informative but harder to defend without an external assessor.
2. Semantic density granularity: report aggregate only, or also per node label and per edge type? Per-label adds detail at the cost of a more crowded figure.
3. How should we handle the Gene category limitation? Disclose openly in the limitations section, or as a labelled gap in the alignment table?

---

## Experimental section: presentation plan

### What the results section will show

1. **Selection table** — the ten ontologies, three tools, two standards from Step A, scored on the three axes, with include / exclude / future-work decisions and a one-line rationale per row. The existing assessment summary table fits here with light edits.
2. **Migration step audit** — for each of Steps 17–20 (Step B), a row reporting nodes touched, properties added, edges added, runtime, and the FAIR and semantic density deltas attributable to that single step. This is what makes the migration reproducible: the reader can see what each step does on its own.
3. **Column-to-concept mapping table** (Step C) — one row per source column, with target ontology, target concept URI, mapping rule, and a test-fixture identifier. Published as a supplementary CSV alongside the paper.
4. **FAIR scorecard before / after** — per-principle bar chart or heatmap, showing each FAIR principle's score at baseline and after Steps A–D. One of the two headline visuals.
5. **Semantic density progression** — node-URI and edge-URI coverage growing per step, as a stacked area or waterfall chart. The other headline visual; complements the FAIR scorecard by showing how the FAIR gains are realised in graph-level coverage.
6. **AlzKB alignment matrix** — a 4×2 table, four in-scope AlzKB categories on rows, pre and post on columns, with cell shading for none / weak / strong match.
7. **Functional dependency diagram (revised)** — C7 at the centre, Steps A–D as feeders, C6 (future work) on the right. Replaces the current seven-node diagram.

### Reproducibility artefacts published with the paper

- `ontology/mappings/` — every column-to-concept mapping rule, one CSV per source table.
- `metrics/fair.py` — FAIR maturity scoring against the FAIR principles checklist.
- `metrics/semantic_density.py` — node-level and edge-level URI coverage on the live graph.
- `metrics/alzkb_alignment.py` — the alignment query set against the AlzKB RDF dump.
- `tests/` — fixtures so each step is verifiable on a synthetic miniature graph.

---

## Future work (deferred from the paper)

- **C6 — comparative benchmark.** After June 2026, once the C7 paper is submitted. Will run the same four-step methodology on a second clinical multimodal source (candidate: PPMI Parkinson's data, or UK Biobank if access permits) and report whether the procedure transfers.
- **C4-equivalent — molecular layer.** Gene Ontology integration was removed from the current paper because it was not implemented. The natural follow-up adds Gene nodes, GO terms, and the missing AlzKB Gene-category alignment.
- **Causal layer.** The original CauAD scope. Once the ontology paper is published and the master's thesis is defended (mid-2026), causal discovery resumes as a separate workstream on top of the now-aligned MAKO graph.

---

## Authorship and signature order

Per project convention:
1. Asst. Prof. Özgün Pınarer (PI / coordinator, Galatasaray University)
2. Dr. Sultan Nezihe Turhan (Co-Investigator, Galatasaray University)
3. Oğuzhan Güngör (MSc Candidate, Galatasaray University)
4. Dr. Hajer Baazaoui (CY Cergy Paris Université, ETIS Lab)

Order subject to the paper's specific contribution mapping; co-corresponding arrangement to be confirmed.
