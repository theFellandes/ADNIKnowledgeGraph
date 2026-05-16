# Contribution Delivery Tasks — Granular Checklist

> **Companion to.** [CONTRIBUTION_TABLE_GAP_ANALYSIS.md](CONTRIBUTION_TABLE_GAP_ANALYSIS.md)
> (the gap inventory) and [CONTRIBUTION_DELIVERY_PLAN.md](CONTRIBUTION_DELIVERY_PLAN.md)
> (the workstream organisation).
>
> **Convention.**
> - `[ ]` = open, `[x]` = done, `[~]` = partially done.
> - IDs prefixed `WA`, `WB`, `WC`, `WD` per workstream.
> - Each task lists its dependency, owner, effort estimate, and acceptance.

---

## Workstream A — Documentation-only gap closures

> Closes G1, G2, G3, G7, G8, G9, G10. Half a day total. No graph changes.

### WA.1 — Port the Ontology & Tool Assessment Summary

- **Gap.** G1
- **What.** Add a new appendix to the evaluation PDF that ports Hajer's
  Ontology and Tool Assessment Summary table (the 16-row table on page
  6-7 of her contribution-table PDF). Render with three columns: "What
  it covers", "Current status", "Decision".
- **Where.** New section in `metrics/thesis_pdf.py` between §10
  (Methodological figures) and §11 (Discussion), titled "Appendix A —
  Ontology and Tool Assessment Summary".
- **Acceptance.**
  - [ ] PDF contains the full 16-row table.
  - [ ] Row entries match Hajer's contribution-table PDF exactly.
  - [ ] The "current status" column reflects live-graph values from the
    canonical snapshot (e.g. "100% on Diagnosis — 25,946 nodes").
- **Effort.** 1 hour. **Owner.** Oğuzhan + Claude.

### WA.2 — Three-axis score table per candidate ontology

- **Gap.** G2
- **What.** For each of the 10 candidate ontologies in Hajer's
  contribution table, populate a row with three numeric / qualitative
  scores: Coverage (T-Box presence and A-Box population), Interoperability
  gain (new semantic content, AlzKB identifier overlap, FAIR-dimension
  contribution), Feasibility (effort days, API stability,
  mapping-complexity). The score values are taken from Hajer's contribution
  table where pre-assigned, and computed from the canonical snapshot
  otherwise.
- **Where.** New section in `metrics/thesis_pdf.py` titled "Appendix B —
  Three-axis ontology selection scoring".
- **Acceptance.**
  - [ ] All 10 candidate ontologies listed (SNOMED-CT, LOINC, UBERON,
    ICD-10, HPO, ICD-11, UMLS, GO, MONDO, DOID).
  - [ ] Each candidate scored on all three axes.
  - [ ] Each candidate carries an include / exclude / future-work
    decision with one-line rationale.
- **Effort.** 2 hours. **Owner.** Oğuzhan + Claude.

### WA.3 — T-Box / A-Box coverage subsection

- **Gap.** G3
- **What.** Add a subsection §3.5 (or new §4.5) that separates T-Box
  (schema presence — count of `:OntologyConcept` per `source_ontology`)
  from A-Box (instance annotation rate — count of MAPS_TO or
  CLASSIFIED_AS edges from data nodes to the corresponding
  `OntologyConcept` subset).
- **Where.** `metrics/thesis_pdf.py` `_build_validity_section` or a new
  `_build_tbox_abox_section`. Numbers come from
  `canonical_snapshot.json::ontology_concepts_by_source` (T-Box) and
  `relationship_cardinalities` (A-Box).
- **Acceptance.**
  - [ ] Per-ontology table with columns: Ontology, T-Box concept count,
    A-Box MAPS_TO / CLASSIFIED_AS count, A-Box / T-Box ratio.
  - [ ] Interpretation paragraph explaining the framing.
- **Effort.** 1 hour. **Owner.** Claude.

### WA.4 — Constraint-violation-count assertion (A1 sub-check)

- **Gap.** G7
- **What.** Extend validity assertion A1 in `metrics/validity.py` to
  report not only the count of constraints + indexes but also the count
  of nodes/edges that *violate* any of those constraints (should be
  zero). Surface as a sub-row in the §3.1 table.
- **Where.** `metrics/validity.py::check_a1` + `metrics/validity_rubric.yaml`.
- **Acceptance.**
  - [ ] Validity report shows constraint violation count as a separate
    field.
  - [ ] PDF §3 displays "Constraint violations: 0 (zero-violation target
    satisfied)" or surfaces non-zero with a note.
- **Effort.** 1 hour. **Owner.** Claude.

### WA.5 — Cite ADKG + AD-DPC in §6

- **Gap.** G8
- **What.** Add citations for ADKG (Yang et al. 2025) and AD-DPC
  (Spassov et al. 2024) as reference AD knowledge graphs alongside the
  existing AlzKB reference, in §6 (Cross-vocabulary alignment) and §11.2
  (Discussion).
- **Acceptance.**
  - [ ] Both citations appear in §6 introductory paragraph.
  - [ ] §11.2 mentions that ADKG and AD-DPC are alternative
    cross-validation targets reserved for future work.
- **Effort.** 30 minutes. **Owner.** Claude.

### WA.6 — Node-types-with-ontology-property count (G9)

- **Gap.** G9
- **What.** Add a metric to the canonical snapshot and the evaluation
  PDF: the count of distinct node labels that carry at least one
  ontology-code property (`snomed_code`, `loinc_code`, `uberon_code`,
  `icd10_code`, `mondo_code`, `hpo_code`, `ontology_uri`). Hajer's
  contribution table targets 10 of 17.
- **Where.** Extend `metrics/reconcile.py` with a Cypher batch that
  counts node labels by ontology-property presence. Add a table row to
  §4 of the evaluation PDF.
- **Acceptance.**
  - [ ] Canonical snapshot reports `node_labels_with_ontology` field.
  - [ ] PDF §4 shows the count vs the 10/17 target.
- **Effort.** 1 hour. **Owner.** Claude.

### WA.7 — UBERON URI-prefix audit (G10)

- **Gap.** G10
- **What.** Hajer's contribution table flags "URI prefix bug exists" on
  UBERON. Audit the live graph for UBERON URIs: confirm whether they
  use `uberon:UBERON:0002421` (double-prefix) or `uberon:0002421` (single)
  or something else, and document the resolution.
- **Where.** New short doc `docs/final_report/c7_plan_v2/UBERON_URI_AUDIT.md`
  reporting the audit + the fix decision.
- **Acceptance.**
  - [ ] Audit doc exists and reports the chosen URI convention.
  - [ ] If a fix is required, the appropriate Cypher `SET` is documented
    (not executed without supervisor sign-off).
- **Effort.** 1 hour. **Owner.** Oğuzhan.

---

## Workstream B — Patient-level semantic enrichment (Contribution 3)

> Closes G5, G6. Backlog items B-17, B-18, B-19. 2.5 days total.

### WB.1 — HPO mapping inventory + step

- **Backlog.** B-17 (HPO expansion 5 → 30).
- **What.**
  1. Author `ontology/mappings/adsxlist_to_hpo.csv` with rules for at
     least the 15 HPO-mappable AX columns Hajer cites: AXANXIET →
     HP:0000739 Anxiety, AXDEPRES → HP:0000716 Depression, AXAGITAT →
     HP:0000713 Agitation, AXWANDER → HP:0030214 Wandering, AXINSOMN →
     HP:0100785 Insomnia, AXHALLUC → HP:0000738 Hallucinations,
     plus the rest. Source: Hajer's list + HPO Browser.
  2. Author a new pipeline step `steps/step30_hpo_expansion.py` that
     creates the additional HPO `:OntologyConcept` nodes and `MAPS_TO`
     edges from the corresponding `ClinicalFinding` or `Visit` nodes.
  3. Update `metrics/validity_rubric.yaml` A3 to expect ≥ 30 HPO
     concepts.
  4. Update `metrics/reconcile.py` to count HPO A-Box coverage per
     symptom column.
- **Acceptance.**
  - [ ] `ontology/mappings/adsxlist_to_hpo.csv` exists with ≥ 15 rows.
  - [ ] Step 30 implemented + idempotent.
  - [ ] Canonical snapshot reports HPO count ≥ 30.
  - [ ] PDF §4 per-label table shows HPO coverage > 0 instead of zero.
- **Effort.** 1-2 days. **Owner.** Oğuzhan.

### WB.2 — LOINC vital signs

- **Backlog.** B-18.
- **What.**
  1. Author `ontology/mappings/vitals_to_loinc.csv` with the six codes
     Hajer specifies: systolic BP (8480-6), diastolic BP (8462-4),
     weight (29463-7), height (8302-2), heart rate (8867-4), BMI (39156-5).
  2. Extend `steps/step20_ontology_layer.py` (or new step) to
     materialise these `:OntologyConcept` nodes and link the
     corresponding biomarker / VITALS nodes via `MAPS_TO`.
- **Acceptance.**
  - [ ] `ontology/mappings/vitals_to_loinc.csv` has 6 rows.
  - [ ] Canonical snapshot reports LOINC count = 16.
  - [ ] PDF §4 reports LOINC vocabulary growth 10 → 16.
- **Effort.** Half a day. **Owner.** Oğuzhan.

### WB.3 — Comorbidity nodes from MEDHIST

- **Backlog.** B-19.
- **What.**
  1. Author `ontology/mappings/medhist_to_snomed.csv` with rules at
     category granularity: MEDHIST.MHCARD → cardiovascular (SNOMED
     49601007), MHPSYCH → psychiatric, MHNEURL → neurological, MHENDO
     → endocrine, etc.
  2. Author `steps/step31_comorbidity_extraction.py` that scans MEDHIST
     rows, creates `:Comorbidity` nodes keyed by the SNOMED-CT category
     code, and connects them to `:Patient` via `HAS_COMORBIDITY`.
  3. Update validity rubric A2 to optionally include `:Comorbidity`
     coverage check.
- **Acceptance.**
  - [ ] `:Comorbidity` label exists in graph with ≥ 4 distinct category
    nodes.
  - [ ] `HAS_COMORBIDITY` edges connect Patient → Comorbidity.
  - [ ] Canonical snapshot reports Comorbidity cardinality.
- **Effort.** 1 day. **Owner.** Oğuzhan.

### WB.4 — Lookup reliability stats (G6)

- **What.** Add a metric to the step-19 (ICD-10 via WHO API) logs that
  surfaces: number of API calls attempted, succeeded, failed, fell back
  to JSON. Aggregate into a single field in the canonical snapshot.
  Report in §3 or §8 of the evaluation PDF.
- **Acceptance.**
  - [ ] Canonical snapshot reports `lookup_reliability` block.
  - [ ] PDF mentions the stats and confirms the fallback completed
    enrichment to target coverage.
- **Effort.** 2 hours. **Owner.** Claude.

---

## Workstream C — Relation normalisation finish + ontology expansion

> Closes Contribution 5 finish + source-ontology expansion targets.
> 1 day total.

### WC.1 — Biolink Model predicate alignment

- **Backlog.** B-20.
- **What.**
  1. Author a Biolink predicate map: relationship-type → biolink
     predicate (HAS_DIAGNOSIS → `biolink:has_phenotype`, HAS_BIOMARKER
     → `biolink:has_biological_role`, MAPS_TO → `biolink:has_xref`,
     SAME_AS → `biolink:exact_match`, etc.).
  2. Author a Biolink category map: node label → biolink category
     (Patient → `biolink:Patient`, Diagnosis → `biolink:Disease`,
     Biomarker → `biolink:Biomarker`, etc.).
  3. Implement a one-off Cypher batch that sets `r.biolink_predicate`
     on every relationship and `biolink_category` on every node label
     (idempotent — `SET` where `IS NULL`).
- **Acceptance.**
  - [ ] All 51+ relationship types have `r.biolink_predicate` populated.
  - [ ] All 43 node labels have `biolink_category` populated (or are on
    an allowlist of non-Biolink-bearing internal labels).
  - [ ] PDF §5 (FAIR) reports the Biolink alignment as part of I1 / I3.
- **Effort.** Half a day. **Owner.** Claude.

### WC.2 — MONDO + DOID OntologyConcept materialisation

- **Backlog.** B-21.
- **What.**
  1. Cypher batch: for every `:Diagnosis` node with a `mondo_code`
     property, create a `:OntologyConcept{source_ontology:'MONDO',
     uri:'mondo:'+mondo_code}` node (idempotent merge) and a
     `MAPS_TO` edge from the Diagnosis to it.
  2. Add 3 DOID `:OntologyConcept` nodes (DOID:10652 Alzheimer, DOID:1307
     dementia, DOID:11825 MCI) and link the corresponding Diagnosis
     nodes via MAPS_TO.
  3. Update validity rubric A3 to expect MONDO and DOID in
     `required_sources` (or accept them as additional sources).
- **Acceptance.**
  - [ ] Canonical snapshot reports 7+ source ontologies (5 + MONDO +
    DOID).
  - [ ] PDF §4 per-ontology table shows MONDO + DOID rows.
  - [ ] Contribution 7 expansion target progress visible.
- **Effort.** Half a day. **Owner.** Claude.

---

## Workstream D — Per-step baseline snapshots

> Closes G4 + before-vs-after framing. Backlog item B-07. 1.5 days.

### WD.1 — Schedule downtime with Özgün

- **Backlog.** B-07 / Q.7.
- **What.** Coordinate a 30-minute downtime window on the Galatasaray
  Neo4j instance to capture the baseline + per-step snapshots.
- **Acceptance.**
  - [ ] Window scheduled and confirmed.
- **Effort.** Coordination, not implementation. **Owner.** Oğuzhan.

### WD.2 — Capture baseline + per-step dumps

- **Backlog.** B-07.
- **What.** Use `metrics/snapshots.py` to capture
  `data/snapshots/post_steps_17_20.dump` (current), roll back, capture
  `pre_steps_17_20.dump`, then run each migration step in order with a
  dump between each.
- **Acceptance.**
  - [ ] All 5 dumps present in `data/snapshots/`.
- **Effort.** 1 day operational. **Owner.** Oğuzhan with Claude
  supervision.

### WD.3 — Populate the step-audit CSV

- **Backlog.** B-15.
- **What.** Run `metrics/step_audit.py` against the snapshot series;
  produce the per-step nodes-touched / edges-added / runtime / ΔFAIR /
  Δdensity rows.
- **Acceptance.**
  - [ ] `outputs/metrics/step_audit.csv` populated with one row per
    step.
  - [ ] PDF §8 renders the populated table.
- **Effort.** Half a day. **Owner.** Claude.

### WD.4 — Before-vs-after framing for AlzKB alignment

- **What.** Run `metrics/alzkb_alignment` against both the pre and post
  snapshots; produce a `alzkb_alignment_baseline.json` companion file.
  Re-render F5 to show pre vs post columns properly.
- **Acceptance.**
  - [ ] `outputs/metrics/alzkb_alignment_baseline.json` exists.
  - [ ] F5 figure shows pre-column with measured values instead of all
    zeros.
  - [ ] PDF §6 reports before-vs-after numbers.
- **Effort.** Half a day. **Owner.** Claude.

---

## Cross-workstream tasks

### CW.1 — Add CONTRIBUTION_DELIVERY status row to MAKO_evaluation.pdf

- **What.** Add a new appendix (or sub-section in §11) that shows the
  delivery-matrix table from
  [CONTRIBUTION_TABLE_GAP_ANALYSIS.md §2](CONTRIBUTION_TABLE_GAP_ANALYSIS.md)
  so reviewers can see at a glance which contribution-table promises are
  measured vs deferred vs pending.
- **Acceptance.**
  - [ ] PDF contains a "Methodological delivery status" appendix with
    one row per contribution-table promise.
- **Effort.** 1 hour. **Owner.** Claude.

### CW.2 — Resolve OntoQA / FAIR question with Hajer

- **What.** Send Hajer a brief email asking whether section 4.2 of her
  proposed paper structure ("OntoQA delta") is a hold-over from before
  the Friday meeting or a deliberate revival.
- **Acceptance.**
  - [ ] Email sent.
  - [ ] Response recorded in `meeting_notes.md` (or new file).
  - [ ] Evaluation report either retains FAIR-only (confirmed) or adds
    OntoQA secondary scoring (estimated additional half-day).
- **Effort.** 10 minutes to send + half-day contingency. **Owner.**
  Oğuzhan.

### CW.3 — Process checklist for future workstreams

- **What.** Author
  `docs/final_report/c7_plan_v2/PROCESS_CHECKLIST.md` listing the
  pre-flight steps that should be completed before any new evaluation
  workstream starts, to prevent this class of failure from recurring.
- **Acceptance.**
  - [ ] Checklist exists.
  - [ ] Checklist includes "inventory every supervisor doc",
    "build promised-metric matrix before code", "version-lock the
    matrix to the plan", etc.
- **Effort.** 1 hour. **Owner.** Claude (already produced in this commit).

---

## Status dashboard

| Workstream | Tasks total | Tasks open | Effort remaining |
|---|---:|---:|---:|
| A — Documentation only | 7 | 7 | ~0.5 day |
| B — Patient enrichment | 4 | 4 | ~2.5 days |
| C — Relation finish + ontology expansion | 2 | 2 | ~1 day |
| D — Snapshots + audit | 4 | 4 | ~1.5 days |
| CW — Cross-workstream | 3 | 2 (CW.3 done) | half a day |
| **Total** | **20** | **19** | **~5.5 days** |

If forced to descope: Workstream A + Workstream C alone (≈1.5 days) close
the most visible documentation gaps and bring the evaluation PDF to
"covers everything HB promised that is measurable given the current
pipeline state". The deeper contributions (B, D) can defer to
post-defence if time-pressed.
