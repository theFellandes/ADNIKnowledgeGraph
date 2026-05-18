# Thesis Edit Brief — 2026-05-16 (Post Steps 30, 33, 34, 35)

> **Audience.** Cowork session (with the system prompt from [COWORK_THESIS_PROMPT.md](COWORK_THESIS_PROMPT.md)).
> **Scope.** Section-by-section change list for `Thesis/OğuzhanGüngör_Tez (1)/*.tex` reflecting the May-16 enrichment + per-step audit + Step 35 Gene Ontology integration.
> **Total estimated edit time.** 1.5–2 hours.
> **Source of truth for every number.** `outputs/metrics/canonical_snapshot.json` (timestamp 2026-05-16T11:26:42+00:00).

---

## 0. Canonical numbers — copy into thesis verbatim

| Quantity | Value (May 16 snapshot) |
|---|---|
| Total nodes | **443,170** |
| Total relationships | **1,657,679** |
| Patients | 2,638 |
| Visits | 33,800 |
| Diagnoses | 25,946 (100 % SNOMED-CT) |
| CognitiveAssessments | 65,345 (100 % LOINC) |
| Biomarkers (CSF subset) | 9,467 (100 % LOINC) |
| Biomarkers (overall) | 12,008 (78.84 % LOINC) |
| BrainRegions | 12 (100 % UBERON) |
| FamilyMembers | 121,082 |
| Gene nodes | **5** (APOE, APP, PSEN1, PSEN2, MAPT — Step 35) |
| OntologyConcepts | **85 across 8 sources** |
| · SNOMED-CT | 17 |
| · LOINC | 10 |
| · UBERON | 14 |
| · ICD-10 | 5 |
| · HPO | 24 |
| · MONDO | 2 |
| · DOID | 3 |
| · **GO** | **10** |
| AlzKBConcepts | 46 |
| SAME_AS edges | 12 (was 7; +5 from Step 35 Gene SAME_AS) |
| MAPS_TO edges | 246,692 |
| IS_A edges | 46 |
| Edge URI coverage | 99.61 % |
| Node ontology coverage | 30.98 % |
| Validity gate | PASS 7/7 (threshold 0.95) |
| FAIR aggregate | 0.9231 (F 1.000, A 1.000, I 1.000, R 0.667) |
| FAIR F1 coverage | 0.9754 |
| FAIR F2 avg properties | 12.2479 |
| FAIR F4 index count | 153 |
| FAIR I1 edge URI coverage | 0.9957 (pre-enrichment) → 0.9961 (current) |
| FAIR R1.2 provenance | 0.5536 |
| AlzKB Disease alignment | 2 / 17 (11.76 %) strong |
| AlzKB Anatomy alignment | 2 / 14 (14.29 %) strong |
| AlzKB Phenotype alignment | 1 / 24 (4.17 %) strong |
| AlzKB Gene alignment | **5 / 5 (100.00 %) strong** |
| AlzKB in-scope strong | **4 / 4** (was 3/4 before Step 35) |

---

## 1. Section-by-section edits

### Chapter 3 — Proposed Approach

#### §3.5 (or wherever Steps 17–20 are described) — extend with Steps 30, 33, 34, 35

The thesis currently describes Steps 17–20 + Step 24. Add four subsections describing
the post-defense-prep enrichment, modelled on the existing Step-20 paragraph (~120
words each).

**§3.5.5 Step 30 — HPO concept expansion + FamilyMember dementia mapping**

Describe: extension of the HPO concept layer from 5 to 24 concepts, anchoring the 19
new NPI-Q neuropsychiatric symptom phenotypes (anxiety, depression, agitation,
wandering, insomnia, hallucinations, delusions, apathy, irritability, euphoria,
hyperactivity, sleep disturbance, body-weight abnormality, social/occupational
deterioration, childhood-onset behavioural abnormality, echolalia, loss of
consciousness, severe intellectual disability, higher mental function abnormality) as
IS_A children of HP:0000708 (Behavioral abnormality) or HP:0100543 (Cognitive
impairment). At the instance level, the 121,082 FamilyMember nodes with
`has_dementia=true` are mapped to HP:0000726 (Dementia) via MAPS_TO. Note the
ADSXLIST symptom-flag A-Box mapping is data-ingestion-blocked and listed in §5.4
Future Work.

**§3.5.6 Step 33 — Biolink Model annotation**

Pure-metadata pass setting `biolink_category` on 443,150 nodes across 40 node labels
and `biolink_predicate` on 1,640,857 edges across 50 relationship types. Eight
project-internal aggregation relationship types are intentionally unannotated
(BATCH_INGESTED_BY, LOADED_FROM, PROCESSED_BY, HAS_TIMELINE, HAS_SUMMARY, HAS_DOMAIN,
DEFINES_EVENT_TYPE, MATCHES_PATTERN) per the "no semantic over-claim" constraint.

**§3.5.7 Step 34 — MONDO + DOID OntologyConcept layer wiring**

Wires the pre-existing `Diagnosis.mondo_code` properties (set by Step 18) into the
ontology layer as 2 MONDO concepts and adds 3 explicit DOID concepts (DOID:10652
Alzheimer's disease, DOID:1307 dementia, DOID:0050169 mild cognitive impairment).
Materialises 12,420 Diagnosis → MONDO and 12,420 Diagnosis → DOID MAPS_TO edges.
This is what enables DOID-based cross-vocabulary alignment with AlzKB's Disease
entries — the substrate that takes the Disease category from "weak" (SNOMED-CT only)
toward "strong" (shared DOID identifiers).

**§3.5.8 Step 35 — Gene Ontology integration (Contribution 4)**

Materialises 5 `:Gene` nodes (APOE, APP, PSEN1, PSEN2, MAPT) carrying NCBI Gene IDs,
HGNC symbols, and UniProt accessions, and 10 GO `:OntologyConcept` nodes spanning
Molecular Function, Biological Process, and Cellular Component. Bridging edges:
APOE Gene participates in all 10 GO terms (PARTICIPATES_IN); 2,426 GeneticMarker
nodes link to APOE Gene via ENCODES; 5 AlzKBConcept Gene entries link to the
:Gene nodes via SAME_AS. Closes Contribution 4 from the contribution table and
takes the AlzKB Gene-category alignment from N/A to 5/5 (100 %).

#### §3.10 — Quality Assurance and Validation

**Replace** the existing paragraph that says "intermediate snapshots not yet
captured" with:

> The validity gate runs before any metric computation and verifies seven
> structural assertions: constraint and index presence (A1), per-label ontology-code
> coverage (A2), OntologyConcept layer materialisation across the eight source
> ontologies (A3), MAPS_TO / IS_A / CLASSIFIED_AS edge URI annotation (A4),
> relationship-type URI coverage (A5), reachability of every OntologyConcept (A6),
> and PTID hygiene (A7). All seven pass at threshold 0.95 on the May-16 snapshot.
> Intermediate snapshots are captured by `metrics/per_step_audit.py` via a
> rollback-and-replay protocol against the live database, enabling per-step FAIR
> and semantic-density delta reporting in §4.4 (Table 4.X, Figure F4) without
> requiring offline `neo4j-admin database dump` downtime.

### Chapter 4 — Experiments

#### §4.2 — Graph composition

Update the composition table to the post-Step-35 numbers (see §0 above). The
critical changes vs the May-9 baseline thesis: 443,131 → **443,170** nodes;
1,509,297 → **1,657,679** edges; 51 → **85** OntologyConcepts; **5 → 8** distinct
source ontologies; addition of the `:Gene` node label.

#### §4.3 — Structural Validity

Insert the 7-assertion summary table verbatim from
`outputs/validity_reports/kg_validity_progress_report.md` §2. Cite the rubric file
path (`metrics/validity_rubric.yaml`) so a reviewer can audit thresholds. Add a
forward reference to Appendix A (full validity report).

#### §4.4 — Semantic Density

**Add** the per-step progression table using the data from
`outputs/metrics/step_audit.csv`. Format:

| Stage | Nodes | Edges | OntConcepts | MAPS_TO | Edge URI cov | FAIR |
|---|---|---|---|---|---|---|
| pre-Step-30 (baseline) | 443,131 | 1,509,297 | 51 | 100,770 | 0.9957 | 0.9231 |
| post-Step-30 (HPO + FamilyMember) | 443,150 | 1,630,398 | 70 | 221,852 | 0.9960 | 0.9231 |
| post-Step-33 (Biolink) | 443,150 | 1,630,398 | 70 | 221,852 | 0.9960 | 0.9231 |
| post-Step-34 (MONDO + DOID) | 443,155 | 1,655,238 | 75 | 246,692 | 0.9961 | 0.9231 |
| post-Step-35 (Gene + GO) | **443,170** | **1,657,679** | **85** | 246,692 | 0.9961 | 0.9231 |

Embed [paper_outputs/f4_density.svg](../../../paper_outputs/f4_density.svg) as
Figure 4.X with caption: "Semantic-density progression across the five enrichment
steps. Node-URI coverage and edge-URI coverage are reported separately; FAIR
aggregate remains 0.9231 throughout because the metric uses a three-level
(no / partial / yes) rubric that is insensitive to small percentage shifts."

#### §4.5 — FAIR Compliance

Update the per-principle breakdown. FAIR aggregate 0.9231 is unchanged. Replace any
"may be measured" / "pending measurement" language with the actual values from
`outputs/metrics/fair_score.json`:

| Principle | Level | Score |
|---|---|---|
| F1 (Globally unique persistent IDs) | yes | 1.0 (coverage 0.9754) |
| F2 (Rich metadata) | yes | 1.0 (avg 12.25 properties / node) |
| F3 (Metadata explicit IDs) | yes | 1.0 |
| F4 (Indexed) | yes | 1.0 (153 indexes) |
| A1.1 (Open protocol) | yes | 1.0 (Bolt) |
| A1.2 (Auth) | yes | 1.0 (Neo4j RBAC) |
| A2 (Metadata survives) | yes | 1.0 (`ontology/mappings/` committed) |
| I1 (Formal language) | yes | 1.0 (edge URI 0.9961) |
| I2 (FAIR vocabularies) | yes | 1.0 (8 / 8 sources are FAIR-aligned) |
| I3 (Qualified references) | yes | 1.0 (MAPS_TO + IS_A + CLASSIFIED_AS + SAME_AS) |
| R1.1 (Licence) | partial | 0.5 (ADNI DUA + project licence — manual) |
| R1.2 (Provenance) | partial | 0.5 (coverage 0.5536) |
| R1.3 (Community standards) | yes | 1.0 |

Embed [paper_outputs/f3_fair.svg](../../../paper_outputs/f3_fair.svg) as Figure 4.X.

#### §4.6 — AlzKB Alignment

This section is the most substantive update. Replace the existing 3-of-4 / Gene-N/A
matrix with the post-Step-35 4-of-4 matrix:

| Category | MAKO side | AlzKB side | Strong matches | Match rate |
|---|---|---|---|---|
| Disease | SNOMED-CT (17 concepts) | AlzKB Disease (17 entries) | 2 | 11.76 % |
| Anatomy | UBERON (14 concepts) | AlzKB Anatomy (14 entries) | 2 | 14.29 % |
| Phenotype | HPO (24 concepts) | AlzKB Symptom + BiologicalProcess | 1 | 4.17 % |
| **Gene** | **`:Gene` (5 nodes — APOE, APP, PSEN1, PSEN2, MAPT)** | **AlzKB Gene (15 entries)** | **5** | **100.00 %** |

Add the Cypher example from `docs/final_report/c7_plan_v3/CYPHER_QUERIES.md` §6 as a
worked traversal demonstrating cross-KG patient → diagnosis → SNOMED → AlzKB Disease
navigation. Embed [paper_outputs/f5_alignment.svg](../../../paper_outputs/f5_alignment.svg)
(re-render needed against the new numbers before the LaTeX build).

Discuss honestly: per-category match rates for Disease, Anatomy, and Phenotype are
low (11.8 %, 14.3 %, 4.2 %) because AlzKB's identifier-set and MAKO's are
incompletely overlapping. The Gene category reaches 100 % because we deliberately
materialised :Gene nodes only for those genes AlzKB already carries — this is the
correct intersection-based metric, and we report it as such, not as "complete
coverage of AlzKB Genes". A future-work paragraph should note that extending
:Gene to the remaining 10 AlzKB Gene entries (TREM2, CLU, BIN1, ABCA7, CD33, CR1,
SORL1, ADAM10, BACE1, BDNF) is straightforward and would change the match-RATE
denominator interpretation.

### Chapter 5 — Conclusion and Discussion

#### §5.2 — Comparison with Related Work

**Insert the comparator table** from
[COMPARATOR_KGS.md](COMPARATOR_KGS.md). Five rows: AlzKB (Romano 2024), AD-DPC
(Spassov 2024), ADKG (Yang 2025), Dobreva 2025 framework, **MAKO (this thesis)**.

#### §5.3 — Threats to Validity / Limitations

**Remove** these items (now done):
- "Gene Ontology integration is deferred." → DONE (Step 35; §3.5.8, §4.6).
- "Intermediate snapshots not yet captured." → DONE (per-step audit; §4.4, Figure F4).
- "Biolink Model alignment is deferred." → DONE (Step 33).
- "MONDO and DOID OntologyConcept layers are pending." → DONE (Step 34).

**Keep** these limitations (still real):
- ADSXLIST symptom-flag A-Box mapping pending source-data ingestion (the 19 new
  HPO concepts are schema-only in the current graph; A-Box mapping requires
  Visit/ClinicalFinding nodes carrying the binary AX columns, which the current
  graph does not).
- LOINC vital signs (+6 codes) — source VITALS table not loaded as Biomarker nodes.
- MEDHIST Comorbidity nodes — source MEDHIST table not loaded as Patient properties.
- AlzKB alignment per-category rates remain modest (Disease 11.8 %, Anatomy 14.3 %,
  Phenotype 4.2 %) because identifier-set overlap is partial; the binary "strong
  match exists" headline (4/4) hides the rate magnitudes which are reported here.
- ADNI cohort specificity — the methodology generalises in principle to any
  clinical KG, but validation on a second cohort (PPMI / UK Biobank) is post-defense
  paper work.

#### §5.4 — Future Work

**Narrow** the future-work list to:

1. ADNI VITALS + MEDHIST table ingestion → unlocks LOINC vital-sign concepts and
   MEDHIST Comorbidity nodes (~2.5 days; Workstream B in
   `c7_plan_v2/CONTRIBUTION_DELIVERY_PLAN.md`).
2. AlzKB Gene-category expansion — adding :Gene nodes for the remaining 10 AlzKB
   Gene entries (TREM2, CLU, BIN1, ABCA7, CD33, CR1, SORL1, ADAM10, BACE1, BDNF)
   broadens the Gene-category denominator from 5 to 15. Straightforward extension
   of Step 35.
3. Cross-source AlzKB alignment — the current `metrics/alzkb_alignment.py` counts
   matches within the same source_ontology only. A small extension counts
   cross-source matches via shared `purl` (e.g. AlzKB Disease ↔ MAKO MONDO via
   shared MONDO URI), surfacing additional Disease and Phenotype matches that the
   present metric misses.
4. Causal-discovery layer — the original CauAD scope (PC / FCI / GES / DoWhy
   refutation). Prototypes preserved at `steps/step21..26` and `causal/`; resumes
   as a separate workstream post-defense.
5. Comparative benchmark on a second cohort (PPMI / UK Biobank) — the same
   methodology applied to a non-AD dataset; planned for the C7 journal submission
   in mid-2026.

**Remove** any prior text about Gene Ontology being future work, snapshot programme,
Biolink, MONDO, or DOID.

### Acknowledgments

If the rename story is in Acknowledgments, retain it (CauAD → MAKO context is part
of the thesis narrative). If not, no change.

### Bibliography (`thesis_references.bib`)

Confirm presence of (add if missing):

```bibtex
@article{bizon2019biolink,
  title  = {Implementing biomedical data harmonization with the Biolink Model},
  author = {Bizon, Chris and Cox, Steven and Balhoff, James and others},
  journal= {Database},
  year   = {2019}
}

@article{unni2022biolink,
  title  = {Biolink Model: A universal schema for knowledge graphs in clinical, biomedical, and translational science},
  author = {Unni, Deepak R. and Moxon, Sierra A.T. and Bada, Michael and others},
  journal= {Clinical and Translational Science},
  volume = {15},
  number = {8},
  pages  = {1848--1855},
  year   = {2022}
}

@article{vasilevsky2022mondo,
  title  = {Mondo: Unifying diseases for the world, by the world},
  author = {Vasilevsky, Nicole A. and Matentzoglu, Nicolas A. and Toro, Sabrina and others},
  journal= {medRxiv},
  year   = {2022}
}

@article{schriml2022doid,
  title  = {The Human Disease Ontology 2022 update},
  author = {Schriml, Lynn M. and Munro, James B. and Schor, Mike and others},
  journal= {Nucleic Acids Research},
  volume = {50},
  number = {D1},
  pages  = {D1255--D1261},
  year   = {2022}
}

@article{ashburner2000gene,
  title  = {Gene Ontology: tool for the unification of biology},
  author = {Ashburner, Michael and Ball, Catherine A. and Blake, Judith A. and others},
  journal= {Nature Genetics},
  volume = {25},
  number = {1},
  pages  = {25--29},
  year   = {2000}
}

@article{theGOconsortium2023,
  title  = {The Gene Ontology knowledgebase in 2023},
  author = {{The Gene Ontology Consortium}},
  journal= {Genetics},
  volume = {224},
  number = {1},
  pages  = {iyad031},
  year   = {2023}
}
```

Confirm absent (must not appear):
- Tartir 2005 OntoQA.

### Appendix A — Validity Report

`\verbatiminput` or `\input` the contents of
`outputs/validity_reports/kg_validity_progress_report.md` (translate the Turkish
preamble + paragraph headings to whatever LaTeX form the thesis uses).

### Appendix B — Mapping Inventory

Insert the consolidated `ontology/mappings/index.csv` as a multi-page table. 264
rows; the structure is documented in the CSV header.

---

## 2. Article mirror — `Thesis/Article/article.tex`

The journal paper version is shorter. Apply the **numerical** updates from §0 above:

- Abstract: 443,170 nodes, 1,657,679 edges, 85 OntologyConcepts across 8 sources,
  FAIR 0.9231, AlzKB 4/4 in-scope strong.
- Section 4.2 graph composition table — same updates.
- Section 4.6 alignment matrix — same updates.
- Figure references — F3 and F5 will need re-rendering against the May-16 JSONs
  before the LaTeX build.

Do **not** add new sections to the article (§3.5.5–§3.5.8). The article keeps the
methodology compact; describe Steps 30, 33, 34, 35 as a single combined paragraph
("Subsequent enrichments materialised an HPO symptom catalogue, Biolink Model
categorisation, MONDO + DOID concept wiring, and Gene Ontology integration; see
the thesis methodology chapter for per-step detail.").

---

## 3. Verification before declaring done

After all edits:

```powershell
# 1. Confirm no OntoQA bleed-through
Select-String -Path "Thesis/**/*.tex" -Pattern "OntoQA|Tartir"
# Expected: zero hits

# 2. Confirm no stale causality claims outside Chapter 2 + §5.4
Select-String -Path "Thesis/**/*.tex" -Pattern "causal" |
  Where-Object { $_.Line -notmatch "future|literature|prior|paused|defer" }
# Expected: minimal / context-only hits

# 3. Confirm MAKO naming
Select-String -Path "Thesis/**/*.tex" -Pattern "CauAD"
# Expected: only acknowledgments + IEEE-Big-Data-2025 citation

# 4. Build the LaTeX
cd "Thesis/OğuzhanGüngör_Tez (1)"
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
# Expected: no unresolved refs, no missing figures, no overfull boxes >5pt

# 5. Spot-check three numbers in the PDF against canonical_snapshot.json
# - Total nodes:   443,170
# - OntologyConcepts: 85
# - AlzKB Gene match: 5/5 (100.00%)
```

If all five checks pass, the thesis is defense-ready against the May-16 snapshot.

---

## 4. Cross-references

- [COWORK_THESIS_PROMPT.md](COWORK_THESIS_PROMPT.md) — system prompt for the cowork session
- [COMPARATOR_KGS.md](COMPARATOR_KGS.md) — comparator table content for §5.2
- [CYPHER_QUERIES.md](CYPHER_QUERIES.md) §6 — Cypher exemplar for §4.6
- [history/IMPLEMENTATION_HISTORY_2026-05-16.md](history/IMPLEMENTATION_HISTORY_2026-05-16.md) — what changed on the live graph today
- [history/SESSION_LOG_2026-05-16.md](history/SESSION_LOG_2026-05-16.md) — full session forensic log
- `outputs/metrics/canonical_snapshot.json` — source of truth for every number
