# Process Checklist — Prevent Contribution-Table Drift

> **Purpose.** Before any new evaluation workstream, before any new
> deliverable that summarises measured results, complete this checklist
> end to end. It exists because we shipped an evaluation report that
> did not cover every metric Hajer's contribution table promised, and
> the root cause was a missing source-of-truth reconciliation step at
> the planning stage. This checklist forces that reconciliation.
>
> **Owner.** Whoever is leading the new workstream. Sign off before
> writing any code.
>
> **History.** Created 2026-05-09 in response to the
> Contribution-Table gap discovered when cross-checking
> `MAKO_evaluation.pdf` against
> `Contribution_Table_updated HB.pdf`. The recovery is enumerated in
> [CONTRIBUTION_TABLE_GAP_ANALYSIS.md](CONTRIBUTION_TABLE_GAP_ANALYSIS.md)
> and [CONTRIBUTION_DELIVERY_PLAN.md](CONTRIBUTION_DELIVERY_PLAN.md).

---

## Pre-flight checklist

### Phase 1 — Source-of-truth inventory

Before drafting any plan document:

- [ ] Inventory **every supervisor-authored document** in
  `docs/final_report/`. List the title, date, and primary author of each.
- [ ] For each document, classify it as:
  - **Authoritative spec** (what we must measure / build)
  - **Narrative** (what the work is about, no metric promises)
  - **Historical** (superseded; archive only)
- [ ] If any document is dated more recently than the c7_plan_v2 files,
  treat it as authoritative until proven otherwise.
- [ ] If the user mentions a document not in `docs/final_report/` (e.g.
  attached to an email, in `~/Downloads/`), **explicitly read it before
  proceeding**. Ask the user to share it if not accessible.

### Phase 2 — Promised-metric inventory

Before drafting any technical plan:

- [ ] Build a **promised-metric matrix**. Columns: Contribution ID,
  metric name, target value, current status (measured / partial / not
  measured / deferred), backlog reference. List one row per metric
  the authoritative specs promise.
- [ ] Reconcile this matrix against the existing measurement pipeline.
  Every existing measurement should map to one or more rows.
- [ ] **Every metric in the matrix without a measurement plan is a
  visible gap.** Either schedule it in the plan or mark it explicitly
  as out-of-scope with a documented reason.

### Phase 3 — Plan / report scoping

When writing the plan or the report:

- [ ] State the **delivery-tracker framing** explicitly in the
  introduction: the report tracks *every* promised metric, with
  measured-with-value, measured-partial, or
  not-measured-with-reason status for each.
- [ ] Include an appendix or sub-section enumerating every promised
  metric. Reviewers should be able to count rows in the matrix and
  match them to the appendix.
- [ ] For metrics tied to backlog items (e.g. HPO A-Box coverage tied
  to B-17), the entry in the appendix references the backlog item ID
  so the reader can trace.

### Phase 4 — Cross-document version lock

When the plan goes from draft to active:

- [ ] Stamp each related document
  (`CONTRIBUTION_TABLE_GAP_ANALYSIS.md`,
  `CONTRIBUTION_DELIVERY_PLAN.md`,
  `CONTRIBUTION_DELIVERY_TASKS.md`) with the same version date.
- [ ] When any one of them changes, update the others to keep them
  synchronised. Schedule a fortnightly reconciliation if the
  workstream runs more than two weeks.

### Phase 5 — Implementation gates

When writing code:

- [ ] Every new metric script writes its output to a JSON that includes
  a `schema_version`, `timestamp`, and the **canonical snapshot
  run_id** it was computed against.
- [ ] When the report renders, it cites the canonical snapshot's
  timestamp in the header so the reader knows what graph state every
  number is taken from (already implemented via
  `metrics/reconcile.py`).
- [ ] When a metric depends on a backlog item that's not yet
  implemented, the report shows the metric row with a "pending B-XX"
  status — never silently omitted.

### Phase 6 — Final review before sharing

Before any supervisor presentation or paper submission:

- [ ] Re-walk the promised-metric matrix and confirm every row is
  reflected in the report.
- [ ] Re-run `metrics/reconcile.py` to refresh the canonical snapshot.
- [ ] Regenerate the evaluation PDF.
- [ ] Cross-check at least three random numerical claims in the PDF
  against the canonical snapshot JSON — they must match exactly.
- [ ] Sign off in writing (commit message, meeting note) that the
  checklist has been completed.

---

## Anti-patterns to avoid

The following are the specific failure modes that led to the
Contribution-Table gap. Watch for them in future workstreams.

### "We built it from the narrative document"

The narrative document (`c7_unified_contribution.md`) explains *why*
and *what* but doesn't enumerate every numeric promise. Always
cross-reference against the most detailed metric-promise document
available before drafting the plan.

### "It's in progress per the supervisor's status table, so out of
scope for the evaluation report"

The evaluation report is a delivery tracker, not a victory lap.
Every in-progress item should appear with a status row, not be omitted.

### "Two source-of-truth documents disagree, but the older one is
clear so I'll use that"

If the user shares a newer document (even if informally — via email,
download, message), treat it as authoritative until proven otherwise.
Surface the conflict explicitly and ask for resolution.

### "The user said 'we use FAIR not OntoQA' so I dropped OntoQA
entirely and didn't think about it again"

Decisions evolve. If a supervisor's follow-up email mentions the
dropped framework again, that's a signal to reopen the question, not
to dismiss the mention. Confirm explicitly.

### "I'll mention the gap in the limitations section but not list it
as a delivery item"

Limitations is for methodological caveats (sample size, scope,
generalisability). Undelivered metric promises are not limitations,
they are **open delivery items** — they belong in the delivery
matrix with a backlog reference.

### "The user didn't ask about this metric, so I'll skip it"

The user shouldn't have to ask. The supervisor-authored spec is the
ask. If the spec says "metric X with target Y", measure it and report
it, regardless of whether the user prompts.

---

## Quick-reference: what to do at each new workstream kickoff

1. Read every document in `docs/final_report/`. List them.
2. Ask the user for any additional documents (emails, attachments).
   List those too.
3. Build the promised-metric matrix. Commit it.
4. Map every metric to a backlog item if not already implemented.
5. Write the plan with the matrix as Appendix A.
6. Write the deliverable (report, PDF, tool) to render every matrix row.
7. Sign off via the Phase 6 checklist above.

If any step is skipped, the gap will be discovered later by the
supervisor at the worst possible moment. This is non-negotiable.
