# Contribution Table — Gap Analysis and Recovery Plan

> **Status.** Created 2026-05-09 after the user (Oğuzhan) cross-checked the
> generated `MAKO_evaluation.pdf` against Hajer's
> `Contribution_Table_updated HB.pdf` and identified that several promised
> metrics are absent from the evaluation report.
>
> **Purpose.** Honest enumeration of what was promised, what was delivered,
> what is missing, why it was missing, and a recovery plan. Companion
> documents: [CONTRIBUTION_DELIVERY_PLAN.md](CONTRIBUTION_DELIVERY_PLAN.md)
> and [CONTRIBUTION_DELIVERY_TASKS.md](CONTRIBUTION_DELIVERY_TASKS.md).

---

## 1. Post-mortem — why this gap existed

### 1.1 The failure

The evaluation report (`outputs/thesis_report/MAKO_evaluation.pdf`) and
the planning documents under
[`docs/final_report/c7_plan_v2/`](.) were authored against the
seven-contribution **narrative** in
[`c7_unified_contribution.md`](../c7_unified_contribution.md), the
Friday-meeting note in
[`meeting_notes.md`](../meeting_notes.md), and the original
[`implementation_plan.md`](../implementation_plan.md).

They were **not** authored against the more recent, more granular
`Contribution_Table_updated HB.pdf` produced by Hajer, which enumerates
**per-contribution metric promises** (target values, status flags, and
the Ontology & Tool Assessment Summary table). That document was the
authoritative source for what every metric should look like, and it was
not used as the source of truth during planning.

The consequence is that the evaluation pipeline measures and reports
**what is implemented** (FAIR, semantic density, AlzKB alignment,
validity) but does not measure or report **every metric Hajer's
contribution table promised** — specifically:

- T-Box vs A-Box coverage separation per ontology
- A three-axis (coverage / interoperability / feasibility) score per
  candidate ontology
- HPO A-Box coverage from ADSXLIST symptom flags (Contribution 3)
- LOINC vocabulary breadth increase 10 → 16 (Contribution 3)
- Comorbidity node count from MEDHIST (Contribution 3)
- Biolink-aligned node types 0/17 → 12/17 (Contribution 5)
- Patient ontology trade-off matrix (Contribution 6)
- Mapping-tool suitability matrix (Contribution 6)
- Source ontologies 5 → 10 (Contribution 7 expansion target)
- Node types with ontology property 6/17 → 10/17 (Contribution 7)
- AlzKB strong-match table before-vs-after (Contribution 7)

Some of these are missing because the underlying feature is not yet
implemented (active work per Hajer's own "in progress" markers). Some
are missing because the evaluation report was scoped too tightly to
implemented features and did not include a "promised but pending" frame
for tracking delivery.

### 1.2 Process-level mistakes (root causes)

1. **Single source of truth was incomplete.** The planning documents
   were built from `c7_unified_contribution.md`, which is the seven-
   contribution narrative. The contribution table — with target values,
   per-row metric specs, and the assessment summary — was a more recent
   document and was not surfaced during planning. **Fix:** at the start
   of any new evaluation workstream, explicitly inventory every supervisor-
   authored document in `docs/final_report/` and reconcile their contents
   before drafting the plan.

2. **No promised × delivered matrix.** The plan documents listed
   *deliverables* (FAIR, density, alignment, figures) but did not list
   *every metric the contribution paper would cite*. A delivery matrix
   (promised metric → measured? → status) would have surfaced every gap
   immediately. **Fix:** create such a matrix as a first-class artefact
   from now on; commit it under `c7_plan_v2/` and update on every
   contribution-table revision.

3. **"In progress" status treated as out of scope for the evaluation
   report.** Hajer's contribution table marks Contributions 3 and parts
   of 5 and 6 as "in progress". The evaluation report omitted them
   entirely rather than including them with a status of "active work,
   pending; metric will read X when delivered". **Fix:** the evaluation
   report should be a **delivery tracker** that shows every promised
   metric with its current value (measured or "0 / pending B-17"),
   so the reader can see exactly what is delivered vs what remains.

4. **No explicit cross-reference between Hajer's email-side paper
   structure (4.1–4.6) and the evaluation report sections.** The paper
   structure she proposed in her email maps section-by-section to the
   evaluation report's measured outputs, but no mapping was maintained.
   **Fix:** maintain a paper-structure crosswalk doc that lists which
   evaluation-report section supplies which paper section's numbers.

5. **OntoQA / FAIR scope decision documented in one place, not
   propagated.** The Friday-meeting decision to drop OntoQA and use
   FAIR + semantic density is recorded in `meeting_notes.md`. Hajer's
   subsequent email still references OntoQA in section 4.2 of her
   proposed paper structure, suggesting the decision may not have been
   fully propagated. **Fix:** before referencing the OntoQA-out
   decision as settled, confirm with Hajer that her latest email reflects
   it. If not, the scope question is reopened.

### 1.3 What this is and isn't

This **is** an accountability document. The failure was process-level,
not data-level — the measurements we did make are correct; the issue is
that we did not make every measurement we promised, and the report did
not flag what was unmeasured.

This **is not** a deliverable abandonment. The fixes are scoped, the
work is enumerated, and the recovery plan in
[CONTRIBUTION_DELIVERY_PLAN.md](CONTRIBUTION_DELIVERY_PLAN.md) closes
every concrete gap. Total estimated work to bring the evaluation report
fully in line with Hajer's contribution table is **3–4 working days of
implementation plus a half-day documentation pass**, broken down per
backlog item in
[CONTRIBUTION_DELIVERY_TASKS.md](CONTRIBUTION_DELIVERY_TASKS.md).

---

## 2. Complete promised-metric inventory

Every metric Hajer's contribution table promised, mapped to delivery
status as of 2026-05-09. Status legend: ✅ delivered with value; ⚠️
partial / proxy delivered; ❌ promised but not measured / not implemented;
🗂️ deliberately deferred per scope decision.

### 2.1 Contribution 1 — Three-axis ontology selection framework

| Promised metric | Delivery status | Notes |
|---|---|---|
| Dataset size: 2,638 patients, ~421K nodes, ~1.4M edges | ✅ | Canonical snapshot: 2,638 patients, 443,131 nodes, 1,509,297 edges (graph has grown since the contribution-table draft). |
| 10 ontologies / 3 tools / 2 standards evaluated | ⚠️ | The list is documented in Hajer's PDF page 6-7 but **not ported into the evaluation report**. Gap G1. |
| Three-axis score per candidate (coverage, interop, feasibility) | ❌ | Scoring matrix not present anywhere. Gap G2. |
| Candidates recommended vs excluded (with rationale per exclusion) | ⚠️ | Documented in Hajer's PDF but not in the evaluation report. Gap G1. |
| OntoQA before / after | 🗂️ | Replaced with FAIR + semantic density per Friday meeting. Confirm with Hajer that her email-side OntoQA reference in section 4.2 reflects this. |
| T-Box (schema presence) coverage per ontology | ❌ | Measurable now from the canonical snapshot. Gap G3. |
| A-Box (instance annotation) coverage per ontology | ❌ | Measurable now from the canonical snapshot. Gap G3. |

### 2.2 Contribution 2 — In-place semantic migration

| Promised metric | Delivery status | Notes |
|---|---|---|
| Steps 17, 18, 19, 20 executed | ✅ | All implemented, idempotent. |
| 12 constraints + 15 indexes (step 17) | ✅ | Validity A1 verifies. |
| Ontology property annotation on six node types (step 18) | ✅ | Validity A2 verifies per-label coverage ≥ 95%. |
| ICD-10 hierarchy via WHO REST API + JSON fallback (step 19) | ✅ | Implemented in `steps/step19_icd10_integration.py`. |
| OntologyConcept layer with MAPS_TO and IS_A (step 20) | ✅ | A3 + A4 verify. |
| OntologyConcept count: 52 across 5 ontologies | ⚠️ | Canonical: 51 (off by 1). Documented in canonical snapshot. |
| IS_A hierarchy edges: 27 | ✅ | Canonical: 27 exactly. |
| MAPS_TO edges: 100,770 | ✅ | Canonical: 100,770 exactly. |
| CLASSIFIED_AS edges: 25,946 | ✅ | Canonical: 25,946 exactly. |
| URI-annotated relationships: ~1.2M | ✅ | Canonical: 1,502,793 (99.6%). Exceeds the claim. |
| Mapping completeness: 100% on Biomarker/LOINC | ⚠️ | **100% on CSF subset only (9,467/9,467); broader pool 78.84% (9,467/12,008).** Now disambiguated in PDF §4.5 and B-16a. |
| Mapping completeness: 100% on BrainRegion/UBERON | ✅ | 12 / 12. |
| Mapping completeness: 100% on Diagnosis/SNOMED-CT | ✅ | 25,946 / 25,946. |
| Log + metrics for each step improvement | ❌ | Per-step migration audit (§8 in PDF) currently empty pending B-07. Gap G4. |

### 2.3 Contribution 3 — Semantic enrichment of patient-level data

| Promised metric | Delivery status | Notes |
|---|---|---|
| HPO expansion 5 → 15 concepts | ❌ | Still 5. **B-17 not implemented.** |
| ADSXLIST symptom flags → HPO via MAPS_TO | ❌ | Not done. **B-17 not implemented.** |
| FamilyMember nodes linked to HPO terms | ❌ | Not done. **B-17 not implemented.** |
| Comorbidity nodes from MEDHIST | ❌ | No `:Comorbidity` label in graph. **B-19 not implemented.** |
| LOINC vocabulary breadth 10 → 16 codes (vital signs) | ❌ | Still 10. **B-18 not implemented.** |
| HPO A-Box coverage 0% → > 80% of symptom-carrying visits | ❌ | Cannot measure until B-17 lands. Gap G5. |
| LOINC vocabulary breadth measurement | ❌ | Cannot measure increase until B-18 lands. Gap G5. |
| Comorbidity node count + HAS_COMORBIDITY edge count | ❌ | Cannot measure until B-19 lands. Gap G5. |
| REST error handling: retry + JSON fallback | ✅ | Implemented in step 19. |
| Lookup reliability stats (failure rate, fallback completion) | ❌ | Logic exists; metric never measured / surfaced. Gap G6. |
| Constraint satisfaction: zero-violation target on new node types | ⚠️ | A1 verifies constraint presence; doesn't separately count violations. Gap G7. |

### 2.4 Contribution 4 — Gene Ontology integration

| Promised metric | Delivery status | Notes |
|---|---|---|
| Gene node for APOE + 8-10 GO terms | 🗂️ | Status "Proposed" per Hajer. Correctly deferred. No gap. |
| ENCODES + PARTICIPATES_IN relationships | 🗂️ | Deferred per Hajer. No gap. |
| AlzKB Gene entity-type match: none → strong | 🗂️ | Currently N/A in AlzKB alignment matrix. Correctly flagged. |

### 2.5 Contribution 5 — Relation normalisation (RO URIs + Biolink)

| Promised metric | Delivery status | Notes |
|---|---|---|
| 30/30 relationship types with RO URI | ✅ | Canonical: 51/51 of non-allowlisted types (graph has grown). |
| Total URI-annotated edges ~1.2M | ✅ | Canonical: 1,502,793. |
| Biolink-aligned node types 0/17 → 12/17 | ❌ | **Still 0/17. B-20 not implemented.** |
| OntoQA Relationship Richness before / after | 🗂️ | Replaced with FAIR I1 + edge density. |

### 2.6 Contribution 6 — Comparative benchmark

| Promised metric | Delivery status | Notes |
|---|---|---|
| Three-axis score per candidate | ❌ | Not in evaluation report. Gap G2. |
| Include / exclude decision count with justification | ⚠️ | Lives in Hajer's PDF page 6-7; not ported. Gap G1. |
| Patient ontology trade-off matrix (custom OWL 2 vs composite vs hybrid) | ❌ | **Not written. B-22 not implemented.** |
| Mapping-tool suitability matrix | ❌ | Lives in Hajer's PDF; not ported into evaluation report. Gap G1. |
| Reference AD KGs cited (AlzKB, ADKG, AD-DPC) | ⚠️ | AlzKB cited in §6; ADKG and AD-DPC not. Gap G8. |

### 2.7 Contribution 7 — Cross-vocabulary alignment with AlzKB

| Promised metric | Delivery status | Notes |
|---|---|---|
| AlzKB strong matches per in-scope category | ✅ | 3 of 3 *implemented* in-scope (Disease, Anatomy, Phenotype). |
| Before vs after enrichment | ⚠️ | Only after measured; before requires rolled-back snapshot. B-07. |
| Source ontologies 5 → 10 | ❌ | Still 5. Emergent from B-17 (HPO expansion via ADSXLIST) and B-21 (MONDO + DOID). |
| OntologyConcept 52 → 90–110 | ❌ | At 51. Emergent. |
| IS_A 27 → 50–60 | ❌ | At 27. Emergent. |
| Node types with ontology property 6/17 → 10/17 | ❌ | Not measured at all in evaluation report. Gap G9. |
| Drug + Pathway out of scope | ✅ | Explicitly out of scope, no measurement required. |
| Gene N/A pending Contribution 4 | ✅ | Reported as not-implemented in alignment matrix. |

### 2.8 Ontology & Tool Assessment Summary (Hajer's PDF page 6-7)

| Row | HB decision | Implementation status |
|---|---|---|
| SNOMED-CT | KEEP. Done. | ✅ 100% on Diagnosis. |
| LOINC | KEEP + EXPAND (vital signs). Half a day. | ⚠️ KEEP done; EXPAND pending B-18. |
| UBERON | KEEP. Fix prefix mismatch. | ⚠️ KEEP done; prefix mismatch fix — unclear status. Gap G10. |
| ICD-10 | KEEP. Done. | ✅ Done. |
| HPO | EXPAND (top priority). 5 → 30. 1-2 days. | ❌ Still 5. B-17. |
| Gene Ontology | ADD. Gene + 8-10 GO terms + ENCODES/PARTICIPATES_IN. 1 day. | 🗂️ Deferred per Contribution 4 "Proposed". |
| MONDO | ADD. Wire up existing codes. 2-3 hours. | ❌ Not done. B-21. |
| DOID | ADD. 3 mappings. Half a day. | ❌ Not done. B-21. |
| Biolink Model | ADD. biolink_category on all 17 node types. Half a day. | ❌ Not done. B-20. |
| ICD-11 | EXCLUDE. | ✅ Correctly excluded. |
| UMLS | EXCLUDE. | ✅ Correctly excluded. |
| LogMap | EXCLUDE (cite in Related Work). | ⚠️ Excluded; Related Work citation belongs in paper. |
| FOAM | EXCLUDE. Obsolete. | ✅ Excluded. |
| BioPortal Annotator | EXCLUDE. Infrastructure broken. | ✅ Excluded. |
| HL7 FHIR | EXCLUDE. Architectural mismatch. | ✅ Excluded. |
| OpenEHR | EXCLUDE. Same mismatch. | ✅ Excluded. |

---

## 3. Consolidated gap inventory

| Gap ID | Description | Type | Backlog ref | Effort |
|---|---|---|---|---|
| **G1** | Ontology & Tool Assessment Summary table not ported into evaluation report | Documentation | (new) | 1 hour |
| **G2** | Three-axis score-per-candidate table missing | Documentation | (new) | 2-3 hours |
| **G3** | T-Box / A-Box coverage breakdown per ontology missing | Measurement | (new) | 1 hour |
| **G4** | Per-step migration audit empty rows | Measurement | B-07 | 1 day (depends on Q.7) |
| **G5** | HPO / LOINC-vitals / Comorbidity coverage metrics not measured | Measurement | B-17, B-18, B-19 | 3 days |
| **G6** | Lookup reliability stats not surfaced | Measurement | (new) | 2 hours |
| **G7** | Constraint-violation-count metric not separated | Measurement | (new) | 1 hour |
| **G8** | ADKG + AD-DPC reference KGs not cited in evaluation report | Documentation | (new) | 30 min |
| **G9** | Node-types-with-ontology-property count (6/17 vs 10/17 target) not reported | Measurement | (new) | 1 hour |
| **G10** | UBERON URI-prefix mismatch fix status unclear | Investigation | (new) | 1 hour |

Plus the existing backlog items that contribute to gap closure:

| Backlog | Item | Required for which gap |
|---|---|---|
| B-07 | Per-step snapshots (offline neo4j-admin dump) | G4, before-vs-after AlzKB |
| B-17 | HPO expansion 5 → 30 + ADSXLIST mapping | G5 (HPO), Contribution 7 expansion targets |
| B-18 | LOINC vital signs 10 → 16 | G5 (LOINC), Contribution 7 source-ontology growth (indirect) |
| B-19 | Comorbidity nodes from MEDHIST | G5 (Comorbidity) |
| B-20 | Biolink Model alignment | Contribution 5 closing |
| B-21 | MONDO + DOID wiring | Contribution 7 source ontologies 5 → 10 |
| B-22 | Patient ontology trade-off matrix | Contribution 6 documentation |

---

## 4. Hajer paper-structure crosswalk

Mapping Hajer's proposed paper sections (her email) to where the
evaluation report supplies the numbers.

| Hajer's paper § | Title | Evaluation-report source | Status |
|---|---|---|---|
| 4.1 | Overview — four-step pipeline + dependency diagram | Figure 10.1 (functional dependency) | ✅ Available |
| 4.2 | Three-axis ontology selection framework | **Needs G1, G2, G3** before the paper section can cite numbers | ⚠️ Missing pieces |
| 4.3 | In-place semantic migration | §2, §3, §4, §8 | ✅ Available (per-step empty pending B-07) |
| 4.4 | Patient-level semantic enrichment | **Needs B-17, B-18, B-19** before the paper section has anything to report | ❌ Not measurable yet |
| 4.5 | Relation normalisation (RO + Biolink) | §4 (RO part); **Biolink needs B-20** | ⚠️ RO done, Biolink pending |
| 4.6 | Cross-vocabulary alignment evaluation | §6 + §11.2 | ✅ Available |

**Critical observation.** Sections 4.2 and 4.4 of the paper cannot be
drafted with measured numbers until the corresponding gaps and backlog
items are closed. Hajer's paper structure assumes Contributions 3 and
5 are landed; they are not.

---

## 5. Open question for Hajer

Hajer's email of (date pending — needs confirmation) proposes section
4.2 of the paper with this content:

> "Axis 2 — Interoperability gain: new semantic content, **OntoQA delta**,
> external KG identifier overlap"

The Friday meeting (recorded in
[meeting_notes.md](../meeting_notes.md)) decided OntoQA would be dropped
in favour of FAIR + semantic density. This evaluation pipeline reflects
that decision (FAIR is implemented, OntoQA is not).

**Action.** Reply to Hajer's email asking explicitly: "Is the OntoQA
reference in section 4.2 a hold-over, or should we add OntoQA back?
If we add it back, FAIR stays as the primary framework, and OntoQA is
reported as a secondary cross-check. Please confirm."

Until that is resolved, the evaluation report should retain its
FAIR-primary framing and add a footnote acknowledging the question is
open.

---

## 6. Next steps

See companion documents:

- [CONTRIBUTION_DELIVERY_PLAN.md](CONTRIBUTION_DELIVERY_PLAN.md) — how
  to close every gap, sequenced by leverage and dependency.
- [CONTRIBUTION_DELIVERY_TASKS.md](CONTRIBUTION_DELIVERY_TASKS.md) —
  granular per-task checklist.
- [PROCESS_CHECKLIST.md](PROCESS_CHECKLIST.md) — pre-flight checklist
  to prevent this class of failure from recurring.

---

## 7. Bottom-line accountability statement

The evaluation report covers what was implemented but does not cover
every metric Hajer's contribution table promised. This was a planning-
process omission: the contribution table was not surfaced as the source
of truth at the start of the workstream, and no
promised-metric-inventory artefact was created. The fix is enumerated
above and in the companion documents.

No measured value in the report is wrong; the report is **incomplete
relative to the contribution table's metric promises**, and that
incompleteness is the gap this document closes by inventory and the
companion documents close by sequenced delivery.
