# `causal/` — Retained, out of thesis scope

> **Status (2026-05-17):** Causal discovery is **explicitly out of scope** for the May 2026 master's thesis and for the thesis's successor paper. The code is retained in the repository as an artefact of project history, not as a queued workstream.

This package was the home of the original CauAD causal-discovery workstream (PC / FCI / GES / DAG-GNN, with DoWhy refutation tests). Per the user-confirmed scope decision on 2026-05-17 — and consistent with the policy already recorded in [`docs/final_report/c7_plan_v2/CAUSALITY_NOTE.md`](../docs/final_report/c7_plan_v2/CAUSALITY_NOTE.md) — no causal-discovery result is part of the present thesis, and causal discovery is not on the future-work list of this research line. The Python modules survive in the repository because deleting working code is destructive; do not treat the presence of these modules as an implicit roadmap.

## What lives here

The package is intentionally light because the actual step entrypoints sit under `steps/` for orchestration parity with the rest of the pipeline:

| Path | Purpose | Status |
|---|---|---|
| [`steps/step21_extract_causal_features.py`](../steps/step21_extract_causal_features.py) | Extract feature matrix from the KG for causal discovery | retained, not run |
| [`steps/step22_causal_discovery.py`](../steps/step22_causal_discovery.py) | Run PC / FCI / GES / DAG-GNN over the feature matrix | retained, not run |
| [`steps/step23_embed_causal_edges.py`](../steps/step23_embed_causal_edges.py) | Persist the discovered DAG back into the KG as `CAUSALLY_PRECEDES` edges | retained, not run |
| [`steps/step25_validate_causal.py`](../steps/step25_validate_causal.py) | Compare the discovered edges against literature-derived ground truth | retained, not run |
| [`steps/step26_dowhy_inference.py`](../steps/step26_dowhy_inference.py) | DoWhy refutation suite on the discovered DAG | retained, not run |
| `causal/` (this package) | Shared helpers, config schemas, output adapters | retained, awaiting resumption |

The `config.yaml` toggles `run_causal_*` are all set to `false` and should stay that way until the post-defense work resumes.

## Why an empty package directory was a problem

The thesis text in §5.3 (Limitations) and §5.4 (Future Work) names this directory alongside the `steps/step21..step26` files when describing the retained-but-paused workstream. A reviewer who checks the citation by running `ls causal/` should see something — a `README.md` and an `__init__.py` are enough to make the package visible without committing to any active code.

## What to do after the defense

Nothing within this thesis's research line. Causal discovery is out of scope, and the thesis Future Work section does not queue it. The modules in this directory exist for historical reasons; any future causal-discovery work would be initiated as a separate project rather than as a continuation of this one. The legacy plan in [`docs/final_report/c7_plan_v2/CAUSALITY_NOTE.md`](../docs/final_report/c7_plan_v2/CAUSALITY_NOTE.md) is retained for reference, but it is superseded by the 2026-05-17 scope decision.

Nothing in the present thesis depends on these modules.
