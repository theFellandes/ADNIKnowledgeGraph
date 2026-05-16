# c7_plan_v2 — Index

> Versioned planning folder. The original `docs/final_report/implementation_plan.md`, `task_metrics.md`, `c7_unified_contribution.md`, `meeting_notes.md`, and `project_name.md` remain as the historical record. This folder holds the evolved plan, dated 2026-05-09.

## Core plan documents

| File | Purpose | Read first if you are… |
|---|---|---|
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Master plan: scope, deliverables, architecture, validity gate, metric definitions, risks, sequencing, decisions | …a supervisor reviewing the approach end-to-end |
| [TASKS.md](TASKS.md) | Granular checklist (Q / V / M / F / T / R / P / TH groupings) with status tags | …an implementer about to start work |
| [VALIDITY_CHECK_SPEC.md](VALIDITY_CHECK_SPEC.md) | Sultan's gate — seven assertions, Cypher queries, YAML rubric, output schemas | …Sultan, or anyone implementing `metrics/validity.py` |
| [STATUS.md](STATUS.md) | At-a-glance ledger: ✅ completed, ❌ missing, 🆕 added, ⏸️ paused | …trying to figure out what is already done |
| [CAUSALITY_NOTE.md](CAUSALITY_NOTE.md) | Paused-but-retained statement for `steps/step21*..step26*.py` (excl. 24) and `causal/` | …about to do a cleanup pass on the repo |

## Contribution-table gap recovery (added 2026-05-09)

After a cross-check of the generated `MAKO_evaluation.pdf` against
Hajer's `Contribution_Table_updated HB.pdf`, several promised metrics
were identified as absent from the evaluation pipeline. The following
documents enumerate the gap, plan the recovery, and put process around
preventing this recurring.

| File | Purpose | Read first if you are… |
|---|---|---|
| [CONTRIBUTION_TABLE_GAP_ANALYSIS.md](CONTRIBUTION_TABLE_GAP_ANALYSIS.md) | Post-mortem, complete promised-metric inventory, delivery matrix, paper-structure crosswalk | …trying to understand what the evaluation report misses and why |
| [CONTRIBUTION_DELIVERY_PLAN.md](CONTRIBUTION_DELIVERY_PLAN.md) | Workstream plan (A / B / C / D), sequencing, acceptance criteria, risks | …deciding what to work on next |
| [CONTRIBUTION_DELIVERY_TASKS.md](CONTRIBUTION_DELIVERY_TASKS.md) | Per-task checklist with effort estimates and acceptance per task | …an implementer about to start one of the workstreams |
| [PROCESS_CHECKLIST.md](PROCESS_CHECKLIST.md) | Pre-flight checklist for any new evaluation workstream to prevent the same class of failure recurring | …kicking off a new workstream |

## Session handoff (added 2026-05-15)

| File | Purpose | Read first if you are… |
|---|---|---|
| **[SESSION_HANDOFF.md](SESSION_HANDOFF.md)** | **Self-contained handoff document** — complete project context, live-graph state, file inventory, session chronology, user constraints, settled decisions, open questions, verification commands. Designed to bring a fresh Claude session (or new collaborator) fully up to speed without re-exploration. | **…starting a new session and need the full picture in one file** |

---

## Approval flow

1. **Sultan** reviews [VALIDITY_CHECK_SPEC.md](VALIDITY_CHECK_SPEC.md) first (Q.6 thresholds), then [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
2. **Özgün** reviews the full plan + [TASKS.md](TASKS.md) (Q.1, Q.3, Q.7).
3. **Hajer** reviews paper-side parts (Q.2, Q.5).
4. Implementation begins only after all three approvals.

## Differences from the originals

- Adds a formal **KG validity gate** in front of every metric task (Sultan's feedback).
- Acknowledges that `steps/step24_alzkb_bridge.py` and `outputs/eda_figures/` already exist; new work **extends** rather than rebuilds.
- Drops the `source_table` / `source_column` claim that step 18 doesn't actually implement.
- Adds explicit **snapshot tooling** (`metrics/snapshots.py`) — the original plan referenced snapshots without owning a tool.
- Adds the **`ontology/mappings/` directory creation** task — the original plan referenced it as if it existed.
- Adds **STATUS.md** and **CAUSALITY_NOTE.md** per user request.
