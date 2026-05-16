# Conversation History & Repository Discrepancy Log

> **Purpose.** Running record of decisions made in the ontology-paper restructuring session, plus a verified list of where the planning documents diverge from the actual repository state. This file exists because the instruction document, the contribution PDF, and the repo do not agree on several concrete facts. Decisions are only safe if everyone is working from the same numbers.
>
> **Last updated:** this session. **Verification basis:** files under `/mnt/project/` inspected directly (headers.json parsed, step scripts listed, IMPLEMENTATION_PLAN.md read).

---

## Part 1 — Decisions made this session

### D1. Project rename
- **From:** CauAD (Causal Alzheimer's Disease)
- **To (recommended):** **MAKO** — Multimodal Alzheimer's Knowledge graph with Ontology grounding
- **Fallback:** OntoAD-KG
- **Constraint:** the IEEE Big Data 2025 paper stays under CauAD permanently; rename applies only to the ongoing ontology paper and the thesis.
- **Artefact:** `PROJECT_NAME_ALTERNATIVES.md`

### D2. Seven contributions collapsed into one
| Original | New role |
|---|---|
| C1 three-axis evaluation | Step A inside C7 |
| C2 in-place semantic migration | Step B inside C7 |
| C3 semantic enrichment | Step C inside C7, **renamed "column-to-concept mapping"** |
| C4 Gene Ontology integration | **Removed** (never implemented) |
| C5 relation normalisation | Step D inside C7 (demoted; literature check pending) |
| C6 comparative benchmark | **Future work**, separate paper after June 2026 |
| **C7 vocabulary mismatch + AlzKB alignment** | **Main paper contribution** |
- **Artefact:** `C7_UNIFIED_CONTRIBUTION.md`

### D3. Evaluation metrics — OntoQA dropped
- **First draft (wrong):** I read Hajer's note as "add FAIR + semantic density alongside OntoQA". Produced docs with OntoQA as the headline metric.
- **Correction (this session):** Hajer wants FAIR and semantic density to **replace** OntoQA. OntoQA is **not used at all**.
- **Baseline:** the pre-enrichment CauAD graph (rollback of Steps 17–20 on a copy), deltas reported per step.
- **Impact:** OntoQA tables, the OntoQA figure (old F3), and the OntoQA computation tasks were removed from all three working documents. Figure count went 6 → 5.
- **Artefacts:** `C7_UNIFIED_CONTRIBUTION.md`, `IMPLEMENTATION_PLAN_METRICS.md`, `TASKS_METRICS.md`

### D4. Title
- **Proposed:** *Ontology Selection, Mapping, and Evaluation for a Multimodal Alzheimer's Disease Knowledge Graph* ("enrichment" removed, "evaluation" added, per Hajer).

### D5. Self-corrected hallucination
- I had written "~542K nodes, ~1.3M relationships" in the C7 problem statement. **This number has no source** — it is not in the repo, the contribution PDF, or the instruction document. Removed and replaced with a flagged "measure before submission" note.

---

## Part 2 — Verified discrepancies between documents and the repository

These were checked directly against `/mnt/project/` this session. Each row says what the source-of-truth is and what needs reconciling.

### DISC-1 — Table count: documents say "180+", repo has 108

| Source | Claim |
|---|---|
| Instruction document | "headers.json documents 180+ ADNI tables across 5,800+ columns" |
| Project memory note | "headers.json (180+ ADNI tables, authoritative schema reference)" |
| **Repo `headers.json` (parsed this session)** | **108 tables, 5,608 columns** |
| Repo `IMPLEMENTATION_PLAN.md` | "108 ADNI tables ingested" ✅ correct |

**Resolution:** The repo's own IMPLEMENTATION_PLAN.md is right. The instruction document and the memory note overstate the table count. Any paper or thesis text that says "180+ tables" is wrong — use **108 tables / 5,608 columns**, or whatever the final ingest set is, measured from headers.json.

### DISC-2 — Graph size: three different node/edge figures in circulation

| Source | Nodes | Relationships |
|---|---|---|
| Repo `IMPLEMENTATION_PLAN.md` | ~407K | ~1.16M |
| Contribution PDF (Hajer's copy) | ~421K | ~1.4M |
| Instruction document | ≈407,000 | ≈1.16M |
| C7 doc, first draft (mine, **wrong**) | ~542K | ~1.3M |
| Patient count (all sources agree) | 2,638 patients | — |

**Resolution:** No node/edge count goes into the paper or thesis until it is measured live (`MATCH (n) RETURN count(n)` and a relationship count) on the exact Neo4j instance the paper reports on. The ~542K figure I introduced is deleted. The 407K vs 421K gap is probably a snapshot-date difference (the graph grew between the repo doc and the contribution PDF) — confirm which snapshot the paper uses and state that one.

### DISC-3 — Steps 17–20 are documented as "Done" but no scripts exist in the repo

| Source | Claim |
|---|---|
| Contribution PDF | C2 status **"Done"** — "Steps 17–20 run on the live graph: constraints, ontology property annotation, ICD-10 hierarchy, OntologyConcept layer" |
| C7 doc (Step B) | describes Steps 17–20 as the migration pipeline |
| **Repo (step files listed this session)** | **only `step1`–`step16` exist. No `step17`–`step20` scripts.** |

**Resolution — this is the biggest discrepancy.** The documents assert implemented, completed work (12 constraints, 100,770 MAPS_TO edges, 25,946 CLASSIFIED_AS edges, the OntologyConcept layer) but the scripts that would have produced it are not in the repository snapshot. Three possibilities, must be resolved before the paper claims this work as done:
1. Steps 17–20 exist on a branch / machine not in this snapshot → bring them into the repo, tag them.
2. The work was done ad-hoc in Cypher and never scripted → the numbers are real but not reproducible; the paper's reproducibility claim is unsupported until the Cypher is committed.
3. The numbers in the contribution PDF are projected/targeted, not measured → they must be relabelled "target", not "Done".

**Action owner: Oğuzhan.** Until this is settled, every "Done" status on C2 and every concrete edge count (100,770 / 25,946 / 52 OntologyConcept nodes / 27 IS_A) is **unverified** and should be treated as a target, not a result.

### DISC-4 — Repo documentation is still causality-centric; current scope is causality-free

| Source | State |
|---|---|
| Repo `IMPLEMENTATION_PLAN.md` | target state lists "Causal discovery overlay (PC, FCI, GES algorithms)"; "Target Thesis Defense: May 2026" |
| Repo `PHASE2_CAUSAL_DISCOVERY.md`, `PHASE3_VALIDATION_INTEGRATION.md` | full causal-discovery plan |
| Instruction document | three-phase plan centred on causal discovery |
| **Current scope (Hajer's notes + project direction)** | causality is **out of scope** for all formal documents; defended contributions are ontology selection / mapping / evaluation; defence target **~July 2026** |

**Resolution:** The repo's phase docs and IMPLEMENTATION_PLAN.md are stale relative to the current scope. They are not wrong as a record of the old plan, but no formal document (paper, thesis, contribution table) should inherit their framing. The new `C7_UNIFIED_CONTRIBUTION.md` and `IMPLEMENTATION_PLAN_METRICS.md` are the current-scope documents. Causality returns only as post-thesis future work.

### DISC-5 — Collaborator / institution drift in the instruction document

| Source | Claim |
|---|---|
| Instruction document | active collaborators "Dr. Souhila Arib, Dr. Hajer Baazaoui, Dr. Redouane Bouhamoum (CY Cergy Paris University)"; "Target Thesis Defense: May 2026" |
| Current project direction | CY Cergy Paris dropped from the consortium for administrative-approval reasons; Hajer Baazaoui remains a co-author on the ontology paper (P2); defence target ~July 2026 |

**Resolution:** Lower-stakes than DISC-1–4 because it only affects acknowledgements / author lists, but the instruction document's collaborator block and defence date are out of date. Use the current author convention (Pınarer, Turhan, Güngör, Baazaoui) from `C7_UNIFIED_CONTRIBUTION.md`, confirmed with the supervisors.

### DISC-6 — Contribution PDF still contains OntoQA throughout

The uploaded `Contribution_Table_updated_HB.pdf` has OntoQA as the schema-quality framework on every page, plus the OntoQA baseline table on page 9. Per D3 this is now superseded. The PDF is a prior artefact; the live working documents (`C7_UNIFIED_CONTRIBUTION.md`) are the corrected version. When Hajer's next round of feedback comes, it should be applied to the markdown, not the PDF.

---

## Part 3 — Consistent facts (verified, safe to use)

These agree across sources and were spot-checked:
- **2,638 patients** — instruction doc, contribution PDF, project memory all agree.
- **C4 Gene Ontology integration = not implemented** — instruction doc, contribution PDF (page 3 "STATUS: Proposed — no pipeline implementation yet"), and memory all agree. Safe to present as "Proposed".
- **MEDHIST is category-level only** — contribution PDF and memory agree; no specific SNOMED disease codes claimable.
- **HPO-mappable AX symptoms ≈ 15, not 30** — contribution PDF page 3 and memory agree.
- **IEEE Big Data 2025 published** — DOI 10.1109/BigData66926.2025.11402185, under the CauAD name. Permanent.
- **Repo step scripts step1–step16 exist** — verified by listing.

---

## Part 4 — Open items requiring a decision (carried forward)

1. **DISC-3 resolution** — where are Steps 17–20? Until answered, C2 "Done" claims and all ontology edge counts are unverified targets. *Highest priority.*
2. **DISC-2 resolution** — which Neo4j snapshot does the paper report on, and what is its measured node/edge count?
3. FAIR scoring rubric — binary vs three-level — to confirm with Hajer (TASKS_METRICS Q.5).
4. Relation normalisation (Step D / old C5) — literature check on whether comparable papers treat it as a step or a contribution.
5. AlzKB RDF dump version pin (TASKS_METRICS Q.4).
6. Gene-category gap presentation — limitations section vs labelled gap in the alignment table.

---

## Part 5 — Artefacts produced this session

| File | Purpose | Status |
|---|---|---|
| `PROJECT_NAME_ALTERNATIVES.md` | Rename options, MAKO recommended | Final draft |
| `C7_UNIFIED_CONTRIBUTION.md` | Unified C7 contribution, OntoQA-free, ~542K figure removed | Working draft, pending DISC-3 |
| `IMPLEMENTATION_PLAN_METRICS.md` | FAIR + semantic density + AlzKB metrics plan, no scripts | Working draft, pending approvals |
| `TASKS_METRICS.md` | Granular task list, renumbered after OntoQA removal | Working draft, pending approvals |
| `CONVERSATION_HISTORY.md` | This file | Living document |

**Reminder:** none of the metrics scripts are written yet — `IMPLEMENTATION_PLAN_METRICS.md` and `TASKS_METRICS.md` are plans only, gated on supervisor and Hajer approval and on resolving DISC-3.
