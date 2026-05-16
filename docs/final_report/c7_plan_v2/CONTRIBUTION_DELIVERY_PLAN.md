# Contribution Delivery Plan — Closing the Gap to Hajer's Contribution Table

> **Companion to.** [CONTRIBUTION_TABLE_GAP_ANALYSIS.md](CONTRIBUTION_TABLE_GAP_ANALYSIS.md)
> (the gap inventory) and [CONTRIBUTION_DELIVERY_TASKS.md](CONTRIBUTION_DELIVERY_TASKS.md)
> (the granular checklist).
>
> **Goal.** Bring the evaluation report (`outputs/thesis_report/MAKO_evaluation.pdf`)
> and the underlying measurement pipeline into full alignment with Hajer's
> `Contribution_Table_updated HB.pdf`, so that every metric the contribution
> table promises is either measured-with-value or marked as deliberately
> deferred with a documented reason.

---

## 1. Scope and non-goals

**In scope.**

- Close all ten enumerated gaps (G1–G10) from the gap-analysis document.
- Close the implementation backlog items required for the measurable gaps
  (B-07, B-17, B-18, B-19, B-20, B-21, B-22).
- Update the evaluation PDF and Markdown report to include every metric
  promised by the contribution table.
- Maintain a single canonical-snapshot mechanism
  (`metrics/reconcile.py` + `canonical_snapshot.json`) as the
  authoritative source for numerical values.

**Out of scope.**

- Contribution 4 (Gene Ontology integration). Remains in "Proposed" status
  per Hajer's contribution table.
- Drug and Pathway AlzKB categories. Explicitly out of scope per
  Contribution 7's scope note.
- Causal-discovery work (Phase 2 / `steps/step21..step26*.py`). Paused
  per [CAUSALITY_NOTE.md](CAUSALITY_NOTE.md).

---

## 2. Workstream organisation

The work splits into four workstreams. Each can be tackled independently
once its dependencies are satisfied.

### 2.1 Workstream A — Documentation-only gap closures (no graph changes)

Fastest set of items; closes documentation gaps without touching the
graph. Total effort estimate: **half a day**.

| Gap | Action | Effort |
|---|---|---|
| G1 | Port the Ontology & Tool Assessment Summary table from Hajer's PDF into the evaluation report (new appendix) | 1 hour |
| G2 | Build the three-axis (coverage / interop / feasibility) score table for each candidate ontology | 2 hours |
| G3 | Add T-Box / A-Box coverage subsection — computed from the canonical snapshot, no new measurement infrastructure needed | 1 hour |
| G7 | Add a constraint-violation-count assertion to the validity rubric (separate from A1's presence check) | 1 hour |
| G8 | Cite ADKG (Yang et al. 2025) + AD-DPC (Spassov et al. 2024) in §6 of the evaluation report | 30 min |
| G9 | Add a "node-types with ontology property" count to the evaluation report (6/17 vs 10/17 target) | 1 hour |
| G10 | Audit the UBERON URI-prefix mismatch flagged in Hajer's PDF; document the resolution | 1 hour |

Acceptance: re-running `python -m metrics.thesis_pdf` produces a PDF
that contains every Workstream-A artefact.

### 2.2 Workstream B — Patient-level semantic enrichment (Contribution 3 finish)

Closes Contribution 3 and unlocks G5. Total effort: **2.5 days**.

| Backlog | Action | Effort |
|---|---|---|
| B-17 | HPO expansion 5 → 30 + ADSXLIST → HPO MAPS_TO | 1-2 days |
| B-18 | LOINC vital signs 10 → 16 codes | half a day |
| B-19 | Comorbidity nodes from MEDHIST + HAS_COMORBIDITY edges | 1 day |
| G6 | Lookup reliability stats surfaced via the step logs / new metric | 2 hours |

Acceptance:
- `ontology/mappings/adsxlist_to_hpo.csv`, `vitals_to_loinc.csv`, and
  `medhist_to_snomed.csv` exist with curated rules.
- Steps that materialise the new concepts and edges are implemented
  and idempotent.
- Validity rubric A3 expects ≥ 30 HPO concepts; A2 covers Comorbidity
  if introduced.
- Canonical snapshot reports updated HPO / LOINC counts and Comorbidity
  cardinality.
- Evaluation report's §4 per-label coverage table shows non-zero HPO and
  Comorbidity coverage.

### 2.3 Workstream C — Relation normalisation finish + ontology expansion (Contributions 5, 7)

Closes Biolink alignment and the source-ontology expansion targets.
Total effort: **1 day**.

| Backlog | Action | Effort |
|---|---|---|
| B-20 | Biolink Model predicate alignment (`biolink_predicate` on rel types, `biolink_category` on node labels) | half a day |
| B-21 | MONDO + DOID OntologyConcept materialisation + MAPS_TO edges | half a day |

Acceptance:
- Every relationship type carries `r.biolink_predicate` in addition to
  `r.uri`.
- Every node label carries `biolink_category` as a class-level annotation.
- MONDO and DOID `:OntologyConcept` nodes materialised with MAPS_TO from
  Diagnosis.
- Canonical snapshot reports 8+ source ontologies (5 + MONDO + DOID +
  potentially Biolink at schema level).
- Evaluation report's §6 alignment table reports MONDO/DOID concepts.

### 2.4 Workstream D — Per-step baseline snapshots (B-07)

Closes G4 and the before-vs-after framing for FAIR + density + AlzKB
alignment. Requires coordination with Özgün for scheduled downtime on
the Galatasaray Neo4j instance.

| Backlog | Action | Effort |
|---|---|---|
| B-07 | Schedule one downtime window; capture baseline + per-step snapshots; populate step audit CSV | 1 day operational + 0.5 day code |

Acceptance:
- `data/snapshots/post_steps_17_20.dump`, `pre_steps_17_20.dump`, and
  `post_step_{17,18,19,20}.dump` exist.
- `metrics/step_audit.py` produces a populated `step_audit.csv`.
- Evaluation report §8 renders a non-empty table.
- §6 AlzKB alignment table shows before-vs-after columns.

---

## 3. Sequencing and dependencies

```
Workstream A (docs only)
   ├─ no dependencies → start immediately
   ├─ closes G1, G2, G3, G7, G8, G9, G10
   └─ unblocks: nothing (independent)

Workstream B (Contribution 3)
   ├─ no graph dependencies → can start in parallel with A
   ├─ closes G5, G6 (via B-17, B-18, B-19)
   └─ unblocks: Contribution 7 expansion targets indirectly

Workstream C (Biolink + MONDO/DOID)
   ├─ no hard dependencies → can start in parallel with A and B
   ├─ closes Contribution 5 finish + source-ontology growth
   └─ unblocks: AlzKB Disease match-rate improvement

Workstream D (B-07 snapshots)
   ├─ depends on Q.7 (scheduled downtime with Özgün)
   ├─ closes G4 + before-vs-after framing
   └─ should run AFTER Workstreams B and C land so the snapshot captures
      the *final* enrichment state, not an intermediate one
```

**Recommended order.**

1. Start Workstream A today (half-day, no graph changes, immediately
   visible in PDF).
2. Start Workstream C in parallel with A (half-day implementation, then
   re-run `metrics.reconcile` + `metrics.thesis_pdf` to see updated
   numbers).
3. Start Workstream B once A + C land (2-3 days of implementation work).
4. Workstream D last (operational; needs Özgün) — captures the
   final-state baseline once B and C are in.

Total elapsed time at 1 person-day per day: **~5 working days**.

---

## 4. Acceptance criteria for the whole programme

When all four workstreams are complete:

1. **Every row in the contribution-table delivery matrix
   ([CONTRIBUTION_TABLE_GAP_ANALYSIS.md §2](CONTRIBUTION_TABLE_GAP_ANALYSIS.md))
   is ✅, 🗂️, or has a documented backlog reference.** No row is left
   silently incomplete.
2. **Evaluation PDF renders every metric Hajer's contribution table
   promises.** Either with a measured value or with a clearly-marked
   "scope-deferred per Contribution N" placeholder.
3. **Canonical snapshot remains the single source of truth.** No section
   of the report contradicts the canonical snapshot's numbers.
4. **Hajer's paper structure 4.1–4.6 can be drafted using only numbers
   sourced from the evaluation report.** No paper section is left
   without a measured value to cite.
5. **All 167 tests in `tests/` still pass** plus any new tests added by
   the workstream implementations.
6. **A process-checklist (PROCESS_CHECKLIST.md) is in place** documenting
   the source-of-truth reconciliation requirement for future
   workstreams.

---

## 5. Risks and mitigations

| Risk | Mitigation |
|---|---|
| HPO expansion mapping rules require domain knowledge | Use the curated mapping in HB's contribution table (anxiety, depression, agitation, wandering, insomnia, hallucinations are explicitly listed) and the HPO Browser for the rest. |
| Comorbidity category-level granularity is coarser than HB's "Comorbidity" framing suggests | Already acknowledged in HB's scope note ("specific disease codes below the category level are not recoverable from MEDHIST"). No mitigation needed. |
| Biolink Model predicate map for our relationship types may have ambiguities | Use the Biolink Model 4.x reference (`biolink:has_phenotype`, `biolink:has_biological_role`, etc.). Where ambiguous, fall back to `biolink:related_to`. |
| Özgün's downtime window may not align with thesis-defence schedule | Workstream D can be deprioritised: the evaluation report can ship without per-step snapshots, with §8 retaining the "future work" framing it already has. The before-vs-after AlzKB framing can also be deferred. |
| The OntoQA / FAIR question with Hajer is still open | Workstream A's framing remains FAIR-primary; if Hajer reinstates OntoQA, add it as a secondary cross-check in a follow-up workstream (estimated half a day). |
| Time pressure before thesis defence (May 2026) | Workstreams A and C alone (≈1 day total) close the most visible documentation gaps. Workstream B is the largest investment but is also the most important for the paper's headline. If forced to choose, do A + C + B-21 (MONDO/DOID) and defer B-17 + B-19 to post-defence. |

---

## 6. What this plan does not do

- It does not change the evaluation methodology. FAIR, semantic density,
  AlzKB alignment, structural validity remain the four pillars.
- It does not reintroduce OntoQA. That decision stands pending Hajer's
  confirmation of her email's section 4.2 framing.
- It does not implement Contribution 4 (Gene Ontology). Remains
  "Proposed".
- It does not change the paper's scope. The methodology paper still
  targets the seven-contribution framework with C7 as the headline.

---

## 7. Tracking

Progress against this plan is tracked in
[CONTRIBUTION_DELIVERY_TASKS.md](CONTRIBUTION_DELIVERY_TASKS.md). The
gap-analysis document
([CONTRIBUTION_TABLE_GAP_ANALYSIS.md](CONTRIBUTION_TABLE_GAP_ANALYSIS.md))
is updated as gaps close (rows move from ❌ to ✅ in the delivery matrix).

Updates to this plan require a corresponding update to the gap analysis
and the task list. The three documents are version-locked.
