# Causality — Paused, Code Retained

> **TL;DR.** Causal discovery work is **paused** for the C7 paper and the May 2026 master's thesis defense. The code is **intentionally retained** — do not delete, refactor, or move it during cleanup passes. Resumes after the thesis defense.

---

## Why this note exists

The original CauAD project framing put causal discovery (PC / FCI / GES / DAG-GNN, then DoWhy refutation) at the centre. Per Hajer's Friday meeting note, that workstream is now scoped out of the C7 paper, and per the user's instruction in the planning session, no causal work is part of the c7_plan_v2 deliverables.

But the code exists. Future contributors (or the user, post-defense) need a clear "this is paused, not abandoned" signal so a routine cleanup or dead-code pass does not strip it out.

---

## Scope of "paused"

The following are paused — code retained, no work scheduled, default-off in `config.yaml`:

| Path | Purpose | Status |
|---|---|---|
| `steps/step21_extract_causal_features.py` | Extract feature matrix for causal discovery from KG | retained, not run |
| `steps/step22_causal_discovery.py` | Run PC / FCI / GES / DAG-GNN | retained, not run |
| `steps/step23_embed_causal_edges.py` | Persist discovered edges back into the KG | retained, not run |
| `steps/step25_validate_causal.py` | Compare against literature-derived ground truth (precision / recall / F1 / SHD) | retained, not run |
| `steps/step26_dowhy_inference.py` | DoWhy refutation tests on the discovered DAG | retained, not run |
| `causal/` directory | Supporting modules (config, helpers, output schemas) | retained |
| Any `run_causal_*` toggle in `config.yaml` | Pipeline gating | default `false`, do not flip |

The phase-history record for this work lives at [../../infrastructure/history/PHASE2_CAUSAL_DISCOVERY.md](../../infrastructure/history/PHASE2_CAUSAL_DISCOVERY.md).

---

## Scope of "not paused" (still active)

`steps/step24_alzkb_bridge.py` is **not** paused. Step 24 creates `:AlzKBConcept` nodes and `:SAME_AS` edges that the C7 alignment metric consumes (see `metrics/alzkb_alignment.py` in [TASKS.md](TASKS.md) M4.*). It happens to live in the same numeric range as the causal steps; that is a historical accident of step ordering, not an indication that step 24 is part of the causality workstream.

---

## Do not delete instruction

When running cleanup passes, dead-code removal, or import audits:

1. **Leave `steps/step21*..step26*.py` alone** (excluding step 24, which is active).
2. **Leave `causal/` alone.**
3. **Leave the `run_causal_*` flags in `config.yaml` alone** — do not delete the keys, do not change the defaults.
4. If a linter or formatter touches these files, prefer the smallest possible change set; do not refactor for "while we're here" cleanups.
5. If a future test sweep reveals these modules don't import (e.g., a dependency was removed), prefer adding the dependency back over deleting the module.

If a cleanup absolutely needs to touch these files for non-causality reasons (security patch, breaking dependency upgrade, etc.), the change goes through a normal review with a note that the causality code itself remains paused.

---

## When this resumes

Two milestones must complete first:

1. C7 paper submitted (current target window per `c7_unified_contribution.md`).
2. Master's thesis defended (May 2026, Galatasaray University).

After both, the causality workstream returns as a separate workstream on top of the now-aligned MAKO graph. At that point, this note can be retired (or updated to "active again").

---

## Cross-references

- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) §2 — out-of-scope statement for causality
- [TASKS.md](TASKS.md) §"Causality (paused)" — the four CAU.* placeholder rows
- [STATUS.md](STATUS.md) — paused bucket
- [../../infrastructure/history/PHASE2_CAUSAL_DISCOVERY.md](../../infrastructure/history/PHASE2_CAUSAL_DISCOVERY.md) — full historical record
- [../meeting_notes.md](../meeting_notes.md) — Hajer's note that scoped causality out of C7
