# C7 Plan v3 — MAKO Finishing Plan

> **Status.** Planning complete; approved 2026-05-16. Implementation begins after Sultan / Özgün / Hajer sign-off on the open coordination items (see [IMPLEMENTATION_PLAN.md §8](IMPLEMENTATION_PLAN.md)).
>
> **Supersedes.** [c7_plan_v2/](../c7_plan_v2/). v2 documents are preserved as the historical record. Cross-references in v3 may point back into v2 where the spec is unchanged (e.g. VALIDITY_CHECK_SPEC.md's seven-assertion Cypher remains authoritative; v3 only adds the progress-report rendering layer).
>
> **One-line summary.** Close the five contribution-table gaps (B-17 to B-21), capture per-step snapshots, render F4 + Sultan progress report, then patch the thesis to match.

---

## Why v3 exists

Two things changed since v2 was written:

1. **The `metrics/` and `figures/` packages were implemented.** v2's "❌ Missing" bucket is now mostly ✅ (FAIR scorer, semantic density, validity gate, AlzKB alignment, F1/F2/F3/F5 all exist). What v2 framed as 14 work items has reduced to a handful of finishing tasks plus the gap-closure work.
2. **The user committed to closing the contribution-table gaps.** The five items from [Contribution_Table_updated HB.pdf](file:///C:/Users/Fellandes/Downloads/Contribution_Table_updated%20HB.pdf) that v2 deferred — HPO expansion, LOINC vital signs, MEDHIST comorbidity nodes, Biolink Model, MONDO/DOID wiring — are now in scope. v3 owns their implementation, validation, and thesis patches.

If you read only one document, read [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) first, then [TASKS.md](TASKS.md).

---

## Folder map

| File | When to read |
|---|---|
| [README.md](README.md) | Now — entry point |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | First — the six-phase plan with rationale, deliverables, risks |
| [TASKS.md](TASKS.md) | When picking up work — granular task list with verification commands |
| [STATUS.md](STATUS.md) | Quick state check — ledger of ✅/❌/⚠️/⏸️ per artifact |
| [VALIDITY_PROGRESS_REPORT_SPEC.md](VALIDITY_PROGRESS_REPORT_SPEC.md) | Building Sultan's deliverable (Phase 1) |
| [GAP_CLOSURE_SPEC.md](GAP_CLOSURE_SPEC.md) | Implementing B-17 to B-21 (Phase 3) — Cypher, mappings, edge counts, tests |
| [THESIS_PATCH_PLAN.md](THESIS_PATCH_PLAN.md) | Editing the LaTeX thesis (Phase 5) — chapter-by-chapter |

External cross-references:

- [c7_unified_contribution.md](../c7_unified_contribution.md) — the paper's contribution doc (treat as authoritative for scope)
- [meeting_notes.md](../meeting_notes.md) — Friday meeting source of truth (OntoQA dropped, MAKO rename, FAIR + semantic density)
- [c7_plan_v2/VALIDITY_CHECK_SPEC.md](../c7_plan_v2/VALIDITY_CHECK_SPEC.md) — seven-assertion validity-gate spec; v3 references this without modification
- [c7_plan_v2/CAUSALITY_NOTE.md](../c7_plan_v2/CAUSALITY_NOTE.md) — paused-but-retained causal code; v3 honors
- [c7_plan_v2/CONTRIBUTION_TABLE_GAP_ANALYSIS.md](../c7_plan_v2/CONTRIBUTION_TABLE_GAP_ANALYSIS.md) — the gap analysis to be flipped to ✅ during v3 execution

---

## The three parallel tracks

Per user decision (2026-05-16): all three deliverables advance in parallel, sharing the canonical snapshot as single source of truth.

| Track | Earliest deliverable | Where it lands |
|---|---|---|
| **T-Sultan** | `outputs/validity_reports/kg_validity_progress_report.md` + PDF | Next progress report to Sultan |
| **T-Paper** | `paper_outputs/{f1..f5}.{svg,pdf}` + `t{1..4}.tex` + methods text | C7 paper submission |
| **T-Thesis** | Updated `Thesis/OğuzhanGüngör_Tez (1)/*.tex` | Defense May 2026 |

Numbers in all three deliverables trace back to `metrics/output/canonical_snapshot.json`.

---

## Hard exclusions (do not implement)

Per user instruction and prior decisions:

- ❌ **OntoQA** — Tartir 2005 is not cited; OntoQA metrics are not computed. FAIR + semantic density only.
- ⏸️ **Causal discovery** — steps 21–26 paused; `causal/` directory untouched; config toggles `false`.
- ❌ **Gene Ontology integration** — C4 from the original contribution table; left as documented future work in the thesis.
- ❌ **C6 comparative benchmark** — post-June 2026; out of scope.
- ❌ **UMLS, ICD-11, FOAM, BioPortal Annotator, HL7 FHIR, OpenEHR** — excluded with rationale in the contribution-table summary.

---

## What changed from v2 to v3

| v2 item | v3 disposition |
|---|---|
| ❌ "Missing: metrics/fair.py, semantic_density.py, validity.py, ..." | ✅ Now implemented. v3 extends, does not rewrite. |
| ❌ "Missing: F1–F5 figures" | ✅ F1, F2, F3, F5 rendered. F4 still needs SVG/PDF (P2.9 in v3). |
| ❌ "Missing: ontology/mappings/ CSVs" | ❌ Still missing. v3 owns (P3.3). |
| ❌ "Missing: per-step snapshots" | ❌ Still missing. v3 owns (P2.2–P2.5). |
| 🆕 V1–V6 (validity gate impl + tests) | ✅ Implemented. Add `render_progress_report()` helper for Sultan (Phase 1 S1.2). |
| ❌ "Deferred: HPO 5→30, LOINC vitals, MEDHIST comorbidity, Biolink, MONDO/DOID" | 🚧 **Now in scope.** v3 Phase 3 (B-17 to B-21). |
| (not covered) | 🚧 **Thesis patches.** v3 Phase 5. |
| (not covered) | 🚧 **Canonical numerical reconciliation.** v3 Phase 0. |

---

## Next-session entry point

1. Read [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) top to bottom (~15 minutes).
2. Read [STATUS.md](STATUS.md) — find the next task with status `[ ]` and matching phase.
3. Check [IMPLEMENTATION_PLAN.md §8](IMPLEMENTATION_PLAN.md) — confirm the open coordination items (Q.6, Q.7, FAIR rubric, AlzKB pin, Biolink ambiguity) are resolved in `meeting_notes.md`.
4. Execute Phase 0 (audit) before any other phase.
5. Honor the "DO NOT change" list in [IMPLEMENTATION_PLAN.md §6](IMPLEMENTATION_PLAN.md).

If you need a 30-second briefing for a stakeholder: paste the "one-line summary" from the top of this file plus the "three parallel tracks" table above.
