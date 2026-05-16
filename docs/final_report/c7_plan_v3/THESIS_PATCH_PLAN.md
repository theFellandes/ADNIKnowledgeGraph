# Thesis Patch Plan — Phase 5

> **Owner.** Oğuzhan Güngör (LaTeX edits), Asst. Prof. Özgün Pınarer (acceptance), Dr. Hajer Baazaoui (paper-side mirror).
> **Position in pipeline.** Phase 5 of [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Runs after Phase 4 produces the post-enrichment canonical snapshot.
> **Target.** [Thesis/OğuzhanGüngör_Tez (1)/](../../../Thesis/OğuzhanGüngör_Tez%20(1)/) (MSc thesis) and [Thesis/Article/article.tex](../../../Thesis/Article/article.tex) (journal mirror).

---

## 0. Ground rules

1. **No causality content added or modified.** The thesis already defers causality to future work (§5.4). Leave Chapter 2's causal-discovery literature review untouched. Do not introduce causal claims, causal-edge tables, or causal-discovery results.
2. **No OntoQA content.** The thesis already drops OntoQA in favour of FAIR + semantic density. Confirm by `grep -i ontoqa Thesis/**/*.tex` — there should be zero hits (or only a footnote in §4.5 acknowledging it as prior art that was deliberately not used).
3. **No project-name regression.** Use **MAKO** throughout. The historical name CauAD appears only in the Acknowledgments and the references to the IEEE Big Data 2025 paper.
4. **All numeric claims trace back to `metrics/output/canonical_snapshot.json`.** Before final build, `grep` the LaTeX for every numeric mention and verify against the JSON. If any number doesn't match, fix the text, not the JSON.
5. **No scope expansion.** B-22 (Gene Ontology) stays in Future Work. Do not document Gene/GO results.

---

## 1. Thesis chapter structure (recap)

From the Explore agent's reading of the LaTeX project:

| Chapter | Title | What changes |
|---|---|---|
| 1 | Introduction | None |
| 2 | Literature Review | None (no causal content modifications) |
| 3 | Proposed Approach | Sections 3.5–3.10 (per-step descriptions + QA) |
| 4 | Experiments | Sections 4.2–4.6 (graph composition, validity, density, FAIR, AlzKB) |
| 5 | Conclusion and Discussion | Sections 5.3 (limitations), 5.4 (future work) |

The article mirror at `Thesis/Article/article.tex` has the same structure in a condensed form.

---

## 2. Task-by-task LaTeX edits

For each TH.* task in [TASKS.md §TH](TASKS.md), this section provides:
- The target .tex file + section.
- A concrete LaTeX snippet (or diff) to insert.
- Verification hint.

### TH.1 — §3.10 (Quality Assurance and Validation)

**Target.** `Thesis/OğuzhanGüngör_Tez (1)/chapter3.tex` (or whichever chapter file contains §3.10 — verify with the chapter file's `\section{Quality Assurance and Validation}`).

**Edit.** Replace the existing "intermediate snapshots not yet captured" caveat paragraph with:

```latex
\subsection{Structural validity gate}

The MAKO pipeline produces a deterministic structural-validity check across seven assertions
(A1–A7) that must all pass before any downstream metric is computed. The assertions verify:
constraint and index presence (A1), per-label ontology-code coverage (A2), OntologyConcept
layer materialization across seven source vocabularies (A3), MAPS\_TO/IS\_A/CLASSIFIED\_AS
edge URI annotation (A4), relationship-type URI coverage (A5), absence of orphan
OntologyConcept nodes (A6), and PTID hygiene (A7). The rubric is configurable in
\texttt{metrics/validity\_rubric.yaml} and the gate runs in
\texttt{metrics/validity.py}. The reproducible artefact is published as
\texttt{outputs/validity\_reports/kg\_validity\_progress\_report.md}; the current run is
included in Appendix~\ref{app:validity}.

\subsection{Per-step snapshot programme}

Across Steps 17--34, intermediate snapshots are captured by
\texttt{metrics/snapshots.py} (offline \texttt{neo4j-admin database dump}), enabling
per-step FAIR and semantic-density delta reporting. The delta progression is
visualised in Figure~\ref{fig:density_progression} and tabulated in
Table~\ref{tab:step_audit}. The previous version of this thesis listed
intermediate-snapshot capture as future work; with the present revision the
programme is complete.
```

**Verify.** `pdflatex` compiles; cross-references `\ref{app:validity}`, `\ref{fig:density_progression}`, `\ref{tab:step_audit}` resolve.

### TH.2 — Steps 30–34 descriptions

**Target.** Same chapter as TH.1, after the existing §3.X covering Step 20.

**Edit.** Add five subsections (one per new step). Template per step:

```latex
\subsection{Step 30 — HPO expansion}\label{sec:step30}

The Human Phenotype Ontology (HPO) anchors symptom-level reasoning in the graph.
Prior to this step, MAKO held five HPO concepts as schema with zero
instance-level connections. Step~30 maps fifteen ADSXLIST binary symptom columns
to HPO terms (Table~\ref{tab:adsxlist_hpo}) and connects ClinicalFinding
(or Visit) nodes to the corresponding OntologyConcept via MAPS\_TO edges.
FamilyMember nodes are linked analogously for family-history flags. The
implementation uses the EBI OLS REST API with retry-with-backoff and a local
JSON fallback at \texttt{ontology/hpo\_concepts\_cache.json} for offline
reproducibility. Post-step measurements: HPO A-Box coverage rises from
\SI{0}{\percent} to \SI{XX.XX}{\percent} of symptom-carrying visits;
HPO OntologyConcept count grows from 5 to YY; new MAPS\_TO edges total ZZ\,ZZZ.
```

(Repeat for Steps 31, 32, 33, 34. The numeric placeholders `XX.XX`, `YY`, `ZZ,ZZZ` are filled from `canonical_snapshot.json` after Phase 4.)

For each step, include a `\input{paper_outputs/tX_*.tex}` or a small inline table referencing the corresponding `ontology/mappings/*.csv` row count.

**Verify.** Each subsection compiles; mapping-table cross-refs (`\ref{tab:adsxlist_hpo}` etc.) resolve via TH.11 Appendix.

### TH.3 — §4.2 (Graph Composition)

**Target.** `Thesis/OğuzhanGüngör_Tez (1)/chapter4.tex` (or wherever §4.2 lives).

**Edit.** Find the existing "Graph composition" table or paragraph and update:

| Item | Old value (2026-05-09 snapshot) | New value (post-Phase-4 snapshot) |
|---|---|---|
| Total nodes | 443,131 | (from canonical_snapshot.json `total_nodes`) |
| Total relationships | 1,509,297 | (from canonical_snapshot.json `total_edges`) |
| Distinct ontology sources | 5 | **7** |
| OntologyConcept nodes | 51 | (from canonical_snapshot.json `ontology_concept_count`) |
| Node labels | 17 | 18 (`+ :Comorbidity`) |
| Relationship types | ~30 | ~31 (`+ :HAS_COMORBIDITY`) |

**LaTeX template:**

```latex
\begin{table}[t]
\centering
\caption{MAKO graph composition after the four-step migration + five-step enrichment pipeline.
All counts taken from the canonical snapshot \texttt{canonical\_snapshot.json}
(timestamp: \texttt{YYYY-MM-DDTHH:MM:SS}).}
\label{tab:graph_composition}
\begin{tabular}{lr}
\toprule
Item & Count \\
\midrule
Patient nodes & \num{2638} \\
Visit nodes & \num{XX,XXX} \\
Total nodes & \num{XXX,XXX} \\
Total relationships & \num{X,XXX,XXX} \\
Distinct node labels & 18 \\
Distinct relationship types & 31 \\
OntologyConcept nodes & XX \\
Distinct ontology sources & 7 \\
\bottomrule
\end{tabular}
\end{table}
```

**Verify.** Numbers match `canonical_snapshot.json`; table compiles.

### TH.4 — §4.3 (Structural Validity)

**Target.** Chapter 4's §4.3.

**Edit.** Insert the validity report excerpt as a table + cross-reference to Appendix.

```latex
\begin{table}[t]
\centering
\caption{Structural-validity assertions (A1--A7) on the post-enrichment MAKO snapshot.
Generated by \texttt{metrics/validity.py}; full report in
Appendix~\ref{app:validity}.}
\label{tab:validity}
\begin{tabular}{lllll}
\toprule
Assertion & What it checks & Measured & Threshold & Result \\
\midrule
A1 & Constraints + indexes complete & 12/15 & $\geq$12/15 & PASS \\
A2 & Ontology-code coverage (per label) & 0.962--0.997 & $\geq$0.95 & PASS \\
A3 & OntologyConcept covers $\geq$5 sources & 7 sources & $\geq$5 & PASS \\
A4 & MAPS\_TO/IS\_A/CLASSIFIED\_AS URI coverage & $\geq$0.99 each & $\geq$0.95 & PASS \\
A5 & Relationship-type URI coverage & 0.97 & $\geq$0.95 & PASS \\
A6 & No orphan OntologyConcept nodes & 1.000 reachable & $\geq$0.95 & PASS \\
A7 & PTID hygiene (no \texttt{381\_S\_*}) & 0 violations & 0 & PASS \\
\bottomrule
\end{tabular}
\end{table}
```

**Verify.** Compiles; values reflect canonical snapshot.

### TH.5 — §4.4 (Semantic Density)

**Target.** Chapter 4's §4.4.

**Edit.** Add the per-step density progression table + reference to F4.

```latex
\begin{table}[t]
\centering
\caption{Semantic-density progression across Steps 17--34. Node-URI coverage is the
share of nodes carrying any ontology URI; edge-URI coverage is the share of
relationships annotated with a URI (\texttt{ro\_uri},
\texttt{biolink\_predicate}, or generic \texttt{uri}). Values taken from
\texttt{semantic\_density\_per\_step.json}.}
\label{tab:density_progression}
\begin{tabular}{lrrrr}
\toprule
Stage & Nodes (URI) & Edges (URI) & Node \% & Edge \% \\
\midrule
Pre-Steps-17--20 (baseline) & 0 & 0 & 0.0 & 0.0 \\
Post-Step-17 (constraints only) & 0 & 0 & 0.0 & 0.0 \\
Post-Step-18 (node ontology codes) & XX,XXX & XX,XXX & XX.X & XX.X \\
Post-Step-19 (ICD-10 hierarchy) & XX,XXX & XX,XXX & XX.X & XX.X \\
Post-Step-20 (OntologyConcept layer) & XX,XXX & X,XXX,XXX & XX.X & XX.X \\
Post-Step-30 (HPO expansion) & XX,XXX & X,XXX,XXX & XX.X & XX.X \\
Post-Step-31 (LOINC vitals) & XX,XXX & X,XXX,XXX & XX.X & XX.X \\
Post-Step-32 (MEDHIST comorbidity) & XX,XXX & X,XXX,XXX & XX.X & XX.X \\
Post-Step-33 (Biolink categories) & XXX,XXX & X,XXX,XXX & XX.X & XX.X \\
Post-Step-34 (MONDO/DOID wiring) & XXX,XXX & X,XXX,XXX & XX.X & XX.X \\
\bottomrule
\end{tabular}
\end{table}

\begin{figure}[t]
\centering
\includegraphics[width=0.85\linewidth]{paper_outputs/f4_density}
\caption{Semantic-density progression across the migration and enrichment pipeline.
Both node-URI and edge-URI coverage shown per step. The pre-Steps-17--20
baseline is a true zero; post-step values rise monotonically as each step
materialises new ontology grounding.}
\label{fig:density_progression}
\end{figure}
```

**Verify.** F4 SVG/PDF compiles into the document; table rows match `semantic_density_per_step.json`.

### TH.6 — §4.5 (FAIR Compliance)

**Target.** Chapter 4's §4.5.

**Edit.** Update the FAIR aggregate score + per-principle breakdown + F3 figure reference.

```latex
The FAIR maturity model assigns one of three levels (no = 0.0, partial = 0.5,
yes = 1.0) to each of 13 principles (Wilkinson et~al., 2016). The post-enrichment
MAKO graph achieves an aggregate FAIR score of \textbf{0.XX} (was 0.92 pre-enrichment).
The per-principle breakdown is in Figure~\ref{fig:fair} and the rubric in
\texttt{metrics/fair\_principles.yaml}. The two principles that remain below
the maximum are R1.1 (license clarity) and R1.2 (provenance), both of which require
external documentation rather than additional graph structure.

\begin{figure}[t]
\centering
\includegraphics[width=0.85\linewidth]{paper_outputs/f3_fair}
\caption{Per-principle FAIR scores before and after the four-step migration plus
five-step enrichment pipeline. Findable (F1--F4) and Accessible (A1.1, A1.2, A2)
reach the maximum; Interoperable (I1, I2, I3) gain substantially from
Biolink-model categorization and MONDO/DOID concept wiring; Reusable (R1.1--R1.3)
remains the bottleneck.}
\label{fig:fair}
\end{figure}
```

**Verify.** Aggregate score and per-principle bar values match `fair_score_post.json`.

### TH.7 — §4.6 (AlzKB Alignment)

**Target.** Chapter 4's §4.6.

**Edit.** Update the alignment matrix.

```latex
\begin{table}[t]
\centering
\caption{AlzKB cross-vocabulary alignment matrix, before and after the four-step
migration plus the five-step enrichment pipeline. ``Strong'' denotes identifier
overlap on the shared OBO/Biolink ontology; ``weak'' denotes string-only or
indirect mapping; ``N/A'' denotes a category whose alignment depends on
contributions left to future work.}
\label{tab:alzkb}
\begin{tabular}{lll}
\toprule
AlzKB category & Pre-pipeline & Post-pipeline \\
\midrule
Anatomy & strong (UBERON shared) & strong \\
Disease & weak (SNOMED only) & strong (via MONDO + DOID) \\
Phenotype & none & strong (HPO expansion) \\
Gene & none & N/A (Gene Ontology integration deferred; \S\ref{sec:future}) \\
Drug & out of scope (CauAD does not model interventions) & out of scope \\
Pathway & out of scope & out of scope \\
\bottomrule
\end{tabular}
\end{table}

\begin{figure}[t]
\centering
\includegraphics[width=0.7\linewidth]{paper_outputs/f5_alignment}
\caption{AlzKB alignment matrix visualised. Three of four in-scope categories
achieve strong identifier overlap with the AlzKB reference knowledge graph after
the enrichment pipeline; the Gene category remains a future-work item.}
\label{fig:alignment}
\end{figure}
```

**Verify.** Matches `alzkb_alignment.json`; F5 figure compiles.

### TH.8 — §5.3 (Threats to Validity / Limitations)

**Target.** Chapter 5's §5.3.

**Edit.** Find the existing paragraph that says "per-step progression deferred" or similar; remove it. Find the existing Gene-Ontology / molecular-layer mention; if it references C4 directly, keep but reframe as "deferred to future work, see §5.4". Add (if not present):

```latex
A current limitation is the absence of a molecular layer aligned to AlzKB's
Gene category. The MAKO graph holds APOE allele information as string properties
on \texttt{:GeneticProfile} nodes, but does not materialise a \texttt{:Gene}
node label or link to Gene Ontology (GO) terms. Consequently, AlzKB's Gene
category remains in the ``N/A'' column of Table~\ref{tab:alzkb}. Integration is
scoped as future work in §\ref{sec:future}.
```

**Verify.** "Per-step progression" caveat removed; Gene-deferral acknowledgment present.

### TH.9 — §5.4 (Future Work)

**Target.** Chapter 5's §5.4.

**Edit.** Trim the Future Work list to three items:

```latex
\section{Future work}\label{sec:future}

Three workstreams follow the present thesis:

\paragraph{Gene Ontology integration.} A \texttt{:Gene} node label, a small set
of GO OntologyConcept terms covering APOE's molecular function and biological
process annotations, and \texttt{ENCODES}/\texttt{PARTICIPATES\_IN} edges. This
closes the Gene-category gap with AlzKB documented in §\ref{sec:limitations}.

\paragraph{Comparative benchmark on a second cohort.} Apply the present
four-step migration plus five-step enrichment methodology to a second clinical
multimodal source (candidate: PPMI Parkinson's data, or UK Biobank if access
permits) and report whether the FAIR + density gains transfer.

\paragraph{Causal-discovery layer.} The original CauAD scope (PC/FCI/GES with
DoWhy refutation) is preserved as paused code under \texttt{steps/step21..26}
and the \texttt{causal/} directory; the data infrastructure required for that
layer is now in place but the analysis is deferred to a post-defence
workstream.
```

The previous Future Work list had five items; this trims to three by absorbing "snapshot programme" (now done) and "validity gate" (now done).

**Verify.** Three paragraphs; references resolve.

### TH.10 — Bibliography updates

**Target.** `Thesis/OğuzhanGüngör_Tez (1)/thesis_references.bib` (or the actual bib file).

**Add** (if not present):

```bibtex
@article{bizon2019biolink,
  title={Implementing biomedical data harmonization with the Biolink Model},
  author={Bizon, Chris and Cox, Steven and Balhoff, James and others},
  journal={Database},
  year={2019}
}

@article{unni2022biolink,
  title={Biolink Model: A universal schema for knowledge graphs in clinical, biomedical, and translational science},
  author={Unni, Deepak R and Moxon, Sierra A T and Bada, Michael and others},
  journal={Clinical and Translational Science},
  volume={15},
  number={8},
  pages={1848--1855},
  year={2022}
}

@article{vasilevsky2022mondo,
  title={Mondo: Unifying diseases for the world, by the world},
  author={Vasilevsky, Nicole A and Matentzoglu, Nicolas A and Toro, Sabrina and others},
  journal={medRxiv},
  year={2022}
}

@article{schriml2022doid,
  title={The Human Disease Ontology 2022 update},
  author={Schriml, Lynn M and Munro, James B and Schor, Mike and others},
  journal={Nucleic Acids Research},
  volume={50},
  number={D1},
  pages={D1255--D1261},
  year={2022}
}
```

**Confirm present** (Explore agent confirmed these are already in the bib):
- Wilkinson 2016 (FAIR)
- Romano 2024 (AlzKB)
- Yang 2025 (ADKG)

**Confirm absent** (must not be added):
- Tartir 2005 (OntoQA) — explicitly excluded

**Verify.** `bibtex` / `biber` runs without errors; all `\cite{...}` references resolve.

### TH.11 — Appendix A: Column-to-concept supplementary

**Target.** Create a new appendix at the end of the thesis.

**Edit.**

```latex
\appendix
\chapter{Column-to-concept mapping supplementary}\label{app:mappings}

This appendix consolidates the reproducibility artefacts produced by Step C
(column-to-concept mapping; see §\ref{sec:step30}--§\ref{sec:step34}). Each
row maps one source-table column to one target ontology concept, with the
mapping rule, the URI, and the test-fixture identifier used to validate the
mapping. The consolidated CSV is published at
\texttt{ontology/mappings/index.csv} alongside the paper.

\begin{table}[h]
\centering
\caption{Excerpt of \texttt{ontology/mappings/index.csv}. Full table in the
supplementary material.}
\label{tab:mappings_excerpt}
\input{paper_outputs/t3_column_to_concept}
\end{table}

\chapter{Validity report}\label{app:validity}

The structural-validity report from the latest canonical snapshot
(\texttt{outputs/validity\_reports/kg\_validity\_progress\_report.md}) is
reproduced verbatim below.

\input{outputs/validity_reports/kg_validity_progress_report_latex}
```

If a Markdown → LaTeX conversion isn't trivial, render the MD as a verbatim block:

```latex
\verbatiminput{outputs/validity_reports/kg_validity_progress_report.md}
```

**Verify.** Appendix renders; mapping table excerpt visible.

### TH.12 — Article mirror

**Target.** `Thesis/Article/article.tex`.

**Edit.** Apply the same numeric updates as TH.3, TH.6, TH.7. The article version is much shorter — the relevant LaTeX is the abstract, results table, and figure references. Use the same source-of-truth numbers (`canonical_snapshot.json`) so the two documents stay consistent.

Specific updates:
- Abstract aggregate FAIR score: 0.92 → new measured value
- Results section: graph composition table → new values
- AlzKB alignment matrix: 3/4 strong (was 1/4)
- F3, F4, F5 figure references identical to thesis
- Bibliography sync — same `\addbibresource{thesis_references.bib}` reference

**Verify.** `pdflatex article.tex` compiles; abstract numbers match.

### TH.13 — End-to-end LaTeX build

**Target.** Both LaTeX projects.

**Commands.**

```powershell
# Thesis
cd "Thesis/OğuzhanGüngör_Tez (1)"
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex

# Article
cd ../../Thesis/Article
pdflatex article.tex
bibtex article
pdflatex article.tex
pdflatex article.tex
```

**Verify.**
- Both PDFs build without unresolved references.
- All `\includegraphics` resolve (figures in `paper_outputs/` exist).
- All `\cite{...}` resolve.
- Visual inspection: F3, F4, F5 render cleanly; tables fit on page; no layout overflow.

---

## 3. Numeric-claim audit (pre-final-build)

Before TH.13, run:

```powershell
# Find every numeric mention in the thesis
Select-String -Path "Thesis/OğuzhanGüngör_Tez (1)/*.tex" -Pattern "\d{2,}" |
  Where-Object { $_.Line -notmatch "^\s*%" } |
  Select-Object Path, LineNumber, Line |
  Out-File numbers_audit.txt
```

Manually cross-check each number against `canonical_snapshot.json`. Any mismatch is a thesis bug; fix the LaTeX, not the JSON.

Pay particular attention to:
- Total node count
- Total edge count
- OntologyConcept count per source
- FAIR aggregate
- Per-label coverage percentages
- AlzKB alignment counts

---

## 4. Project-naming audit

```powershell
# Confirm MAKO is consistent
Select-String -Path "Thesis/**/*.tex" -Pattern "CauAD"
```

Expected hits:
- Acknowledgments (the rename story) ✅ keep
- References to the IEEE Big Data 2025 paper title (\texttt{CauAD}) ✅ keep — historical paper name
- Anywhere else ❌ replace with MAKO

---

## 5. OntoQA bleed-through audit

```powershell
Select-String -Path "Thesis/**/*.tex" -Pattern "OntoQA|Tartir"
```

Expected hits: **zero**, or at most one footnote in §4.5 saying "we considered OntoQA (Tartir et al., 2005) but chose FAIR + semantic density per Hajer's recommendation; see methods §X.Y".

---

## 6. Causality bleed-through audit

```powershell
Select-String -Path "Thesis/**/*.tex" -Pattern "causal" |
  Where-Object { $_.Line -notmatch "future work|deferred|paused" }
```

Expected hits: only in Chapter 2 (literature review) and Chapter 5.4 (Future Work). Anywhere else flag as a stale claim and remove.

---

## 7. Sign-off checklist (before submission)

- [ ] Numbers all match `canonical_snapshot.json` (§3 audit clean)
- [ ] Project name MAKO throughout, CauAD only where historically required (§4 audit clean)
- [ ] OntoQA absent or scoped to one acknowledgement footnote (§5 audit clean)
- [ ] Causality only in Chapter 2 review + §5.4 future work (§6 audit clean)
- [ ] F3, F4, F5 figures embedded and rendered
- [ ] T1, T2, T3, T4 tables `\input`'d or inlined
- [ ] Validity report in Appendix
- [ ] Mapping CSV excerpt in Appendix
- [ ] Bibliography includes Biolink, MONDO, DOID; excludes Tartir
- [ ] `pdflatex → bibtex → pdflatex → pdflatex` builds clean
- [ ] Article mirror has consistent numbers
- [ ] Özgün signs off on the LaTeX changes
- [ ] Hajer signs off on the paper-side mirror

---

## Cross-references

- [IMPLEMENTATION_PLAN.md §4 Phase 5](IMPLEMENTATION_PLAN.md)
- [TASKS.md §TH](TASKS.md)
- [STATUS.md](STATUS.md)
- [VALIDITY_PROGRESS_REPORT_SPEC.md](VALIDITY_PROGRESS_REPORT_SPEC.md) — Appendix B source
- [GAP_CLOSURE_SPEC.md](GAP_CLOSURE_SPEC.md) — Section 3.5–3.9 source
- [c7_unified_contribution.md](../c7_unified_contribution.md) — paper-side narrative authority
