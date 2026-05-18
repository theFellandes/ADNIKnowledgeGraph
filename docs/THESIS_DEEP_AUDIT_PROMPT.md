# MAKO Thesis Deep Audit — Agent Brief

> **Target tool.** Claude Code (not Cowork). Paste this as the first user message in a fresh Claude Code session opened at the repository root `D:\Programming\Python\ADNIKnowledgeGraph`. Claude Code's bash + Task subagent + skill loader + extended-thinking combination is what this audit needs.
>
> **Audit window.** This is a read-and-flag pass, not an edit pass. You are the examiner, not the author. Do not rewrite paragraphs. Do not modify any `.tex` or `.bib` file. Your output is a single markdown report plus a follow-up conversation if I have questions about specific findings.
>
> **Defense date.** May 22, 2026 (six days from today, 2026-05-16). Treat anything that could embarrass the author in front of the jury as P0; anything an external journal reviewer would catch as P1; anything that hurts readability or polish as P2; anything cosmetic as P3.

---

## 1. Use extended thinking on every non-trivial check

Use the maximum thinking budget your tool gives you (`xthink`, `think hard`, interleaved thinking, or the equivalent flag for your runtime). Specifically:

- **Before** spawning a subagent — think through what the agent should look for, what it should ignore, what success looks like.
- **Before** writing each finding into the report — think through whether it is a real defect or whether you have misunderstood the surrounding context.
- **Before** declaring the audit complete — think through every category and confirm you have actually examined it, not just glanced.

Do not collapse reasoning into the first plausible answer. The whole point of this pass is to find the things the writing agent missed.

---

## 2. Use the right skills proactively

Load these skills via the Skill tool the moment you need them. Do not paraphrase from memory — read the SKILL.md first.

| When you encounter | Load skill |
|---|---|
| Any prose paragraph | `humanizer2` (sweep for AI patterns), `scientific-writing` (IMRAD + flow), `anti-ai` |
| Any claim of evidence | `scientific-critical-thinking` (rate evidence quality) |
| Any methodological section | `peer-review` (manuscript-style critique) |
| Quantitative claim about the graph | `knowledge-graph-patterns` (sanity-check KG semantics) |
| Cited external paper (Romano 2024, Spassov 2024, Yang 2025, Jack 2010, Bilgel 2022, Wilkinson 2016, etc.) | `literature-review` and `research-lookup` to verify the cited figure exists in the cited paper |
| Aggregate scoring of the thesis | `scholar-evaluation` (quantitative rubric) |

If a skill is not installed, log that as a separate "missing skill" finding and proceed without it.

---

## 3. Project context

You are auditing the MSc thesis of Oğuzhan Güngör, defending at Galatasaray University on **May 22, 2026**. The thesis is titled "Ontology-Driven Construction of a Knowledge Graph from Multimodal Medical Data". The project name is **MAKO** (Multimodal Alzheimer's Knowledge graph with Ontology grounding); the earlier working name was **CauAD** and appears only in Acknowledgments.

The thesis builds on the IEEE Big Data 2025 paper (`@gungor2025multitier`) which validated the multi-tier image-storage architecture. The thesis itself adds the ontology-grounding methodology that takes the labeled property graph from that paper to a true knowledge graph with cross-vocabulary alignment to AlzKB.

The thesis was last edited on 2026-05-16 by a writing agent against the May-16 canonical snapshot. That writing agent's brief is at `docs/final_report/c7_plan_v3/THESIS_EDIT_BRIEF_2026-05-16.md`. Read this brief first so you know what the writing agent was supposed to do.

### Files under audit

| Path | What it is | Read fully |
|---|---|---|
| `Thesis/OğuzhanGüngör_Tez (1)/thesis.tex` | The thesis (1,730 lines, ~223 kB) | YES |
| `Thesis/Article/article.tex` | Journal-paper mirror (~880 lines) | YES |
| `Thesis/OğuzhanGüngör_Tez (1)/thesis_references.bib` | Bibliography (138 entries) | scan + targeted reads |
| `Thesis/OğuzhanGüngör_Tez (1)/abbreviations.tex` | List of abbreviations | YES |
| `Thesis/OğuzhanGüngör_Tez (1)/Figures/*` | All figures referenced by the .tex | inventory + spot-check |

### Files that are the source of truth

| Path | What it is |
|---|---|
| `outputs/metrics/canonical_snapshot.json` | **Every number in the thesis must trace here.** Single source of truth. Timestamp 2026-05-16T11:26:42+00:00. |
| `outputs/metrics/fair_score.json` | Per-principle FAIR breakdown |
| `outputs/metrics/alzkb_alignment.json` | Per-category AlzKB match rates |
| `outputs/metrics/per_step_audit.json` | Pre-Step-30 → post-Step-34 deltas |
| `outputs/metrics/semantic_density.json` | Per-label and per-edge-type URI coverage |
| `outputs/metrics/semantic_density_per_step.json` | Per-step density deltas |
| `outputs/metrics/runner_summary.json` | Run-time summary |
| `outputs/validity_reports/kg_validity_progress_report.md` | Sultan-facing validity report |
| `ontology/mappings/index.csv` | Consolidated 264-row mapping inventory |
| `ontology/mappings/*.csv` | Per-source mapping files (12 of them) |
| `docs/final_report/c7_plan_v3/THESIS_EDIT_BRIEF_2026-05-16.md` | What the writing agent was told to do |
| `docs/final_report/c7_plan_v3/COMPARATOR_KGS.md` | Comparator-table source content |
| `docs/final_report/c7_plan_v3/CYPHER_QUERIES.md` | Cypher exemplar for §4.6 |
| `docs/final_report/c7_plan_v3/HAJER_RESPONSE.md` | Collaborator feedback on contributions |
| `docs/final_report/c7_plan_v3/STATUS.md` | What's complete / partial / missing |
| `steps/step17_apply_constraints.py` through `steps/step35_*.py` | Implementation that the thesis describes |

### Files that are deliberately stale or paused

| Path | Status — do not flag as missing |
|---|---|
| `steps/step21_extract_causal_features.py` through `steps/step26_dowhy_inference.py` | Causal-discovery workstream is paused; thesis explicitly says so in §5.4 |
| `Thesis/OğuzhanGüngör_Tez (1)/thesis.tex.backup1` | Older backup, ignore |
| `Thesis/OğuzhanGüngör_Tez (1)/Figures/f5_alignment.pdf` (dated May 9) | Known stale — see findings hint below |

---

## 4. Eight categories you must audit (and how)

For each category, run at least the checks listed. Add your own checks when something looks off. **Where the check has a programmatic component, run it; do not eyeball.**

### C1. Numeric consistency against `canonical_snapshot.json`

The thesis cites roughly 60 distinct numerical values. Every one must trace to a JSON in `outputs/metrics/`. Build a number-by-number trace:

1. `grep -nE '[0-9]{3,}' Thesis/OğuzhanGüngör_Tez\ \(1\)/thesis.tex` to find candidates.
2. For each number, identify its claimed referent (total nodes, MAPS_TO count, FAIR aggregate, per-category match rate, etc.).
3. Look the referent up in `canonical_snapshot.json` / `fair_score.json` / `alzkb_alignment.json` / `per_step_audit.json`.
4. Flag every mismatch as **P0** (numeric over-claim or stale figure).
5. Pay particular attention to:
   - `443,170` / `1,657,679` (totals)
   - `30.98%` / `99.61%` (density)
   - `0.9231` (FAIR aggregate)
   - Per-category AlzKB rates (`11.76%` Disease, `14.29%` Anatomy, `4.17%` Phenotype, `100%` Gene)
   - Step counts (5 Gene nodes, 10 GO concepts, 2,426 ENCODES, 5 SAME_AS Gene, 24 HPO, 121,082 FamilyMember mapping, 12,420 MONDO/DOID each)
   - Validity report numbers (59 constraints, 153 indexes, threshold 0.95)
   - Per-step audit numbers (the table at §4.4.1)
   - Mapping rule counts (264 total across 12 CSVs; the per-file breakdown in §3.5 must sum to 264)

The writing agent kept ONE deliberate use of the May-9 numbers (443,131 / 1,509,297 / 51 concepts / 5 sources) inside §4.2 as a historical-comparison reference, and again inside the per-step audit table as the pre-Step-30 baseline row. Both are intentional. Do NOT flag those two specific occurrences. Anywhere else those numbers appear, flag.

### C2. Internal consistency across chapters

The thesis is a single .tex file but reads as five chapters. Cross-check:

1. **Abstract vs body** — every claim in the EN/FR/TR abstracts must be backed by a paragraph in the body. Conversely, body claims that change the conclusion should be reflected in the abstract.
2. **Intro § Contributions vs §5.1 Restatement** — the contribution list in §1.4 must match the restatement in §5.1.
3. **§3 Methodology vs §4 Experiments** — every step described in §3 must produce a measurement in §4 (or be explicitly flagged in §5.3 Limitations as deferred / data-blocked).
4. **§4 Claims vs §5.3 Limitations and §5.4 Future Work** — every claim that lands a "partial" or "not yet validated" verdict in §4 must reappear in §5.3 (as a limitation) or §5.4 (as future work).
5. **Comparator table §5.2 vs body** — the MAKO row in the comparator table must agree with the headline numbers in the abstract.
6. **Article.tex vs thesis.tex** — substantive numeric claims must agree between the two files. Article is condensed; expect the thesis to have more detail but not contradictory numbers.

### C3. Promised vs delivered

This is the highest-yield category for an examiner attack. For every sentence of the form "we report X" / "Section Y reports X" / "Table Z shows X" / "Figure W illustrates X":

1. Find the referenced location.
2. Verify the referenced location actually delivers what was promised.
3. Flag every mismatch as **P0** or **P1** depending on visibility.

Specific landmines to walk:
- The thesis claims Cypher exemplar in §4.6. Is the listing label cited from §4.6 prose? Does the listing actually run against the graph?
- The thesis claims four claims, each with a verdict. Are all four verdicts present and consistent with the measurements?
- The thesis claims "validity gate passes 7/7". Does Table 4.4 actually show seven PASS rows?
- The thesis claims an OntologyConcept count of 85 across 8 sources. Does the per-source breakdown in §4.3 Table 4.4 sum to 85? Does it list 8 sources?
- The §5.4 Future Work says five items. Are there actually five?
- §3.5 promises a 264-rule mapping inventory across 12 files; the per-file breakdown is listed inline. Does it sum to 264?

### C4. Knowledge-graph correctness

Use the `knowledge-graph-patterns` skill before doing this category. Then check:

1. **Ontology code accuracy.** Every cited code must be valid:
   - SNOMED-CT 116154003 (person), 308335008 (clinical encounter), 26929004 (Alzheimer disease)
   - LOINC 57973-5 (CSF Aβ42), 53817-7 (pTau), 48543-0 (total tau), 99521-7 (plasma Aβ40), 8480-6 (systolic BP), 8462-4 (diastolic), 29463-7 (weight), 8302-2 (height), 8867-4 (heart rate), 39156-5 (BMI)
   - UBERON 0001954 (hippocampus), 0002728 (entorhinal cortex)
   - HPO 0000726 (Dementia), 0100785 (Insomnia), 0000708 (Behavioral abnormality), 0100543 (Cognitive impairment)
   - GO 0001540 (amyloid-beta binding), 0006869 (lipid transport), 0042632 (cholesterol homeostasis), 0005576 (extracellular region)
   - DOID 10652 (Alzheimer), 1307 (dementia), 0050169 (MCI)
   - RO 0000051 (has part), 0000050 (part of), 0000056 (participates in), 0000059 (correlated with condition), 0002404 (causally upstream of)
   - For each one, use research-lookup or web search to confirm the code resolves to the claimed concept. Flag any mismatch.

2. **Relation semantics.** The thesis describes specific relationship types:
   - `MAPS_TO`, `IS_A`, `CLASSIFIED_AS`, `SAME_AS`, `ENCODES`, `PARTICIPATES_IN`, `HAS_VISIT`, `INDICATES`, `HAS_PART`, `PART_OF`, etc.
   - Verify the thesis's semantic claim about each matches the standard interpretation (Biolink, RO).

3. **Cypher syntax.** The §4.6 Cypher exemplar must be syntactically valid for Neo4j 5.x. Mentally execute it against the schema described in §3 and confirm it would return rows.

4. **AlzKB schema accuracy.** The thesis names six AlzKB entity categories (Disease, Gene, Drug, Pathway, Anatomy, Phenotype). Cross-check this against AlzKB documentation. Cross-check that the source ontologies of each category are correctly named (DOID for Disease, GO for Gene, ChEBI for Drug, etc.).

5. **FAIR rubric correctness.** The thesis uses Wilkinson 2016 with 13 principles in 4 dimensions, three-level scoring. Cross-check the principle names and the dimension assignments. The dimension averages must roll up to 0.9231 (F=1.0, A=1.0, I=1.0, R=0.667 → mean = 0.917, not 0.9231). Investigate whether the thesis uses simple mean across dimensions or weighted mean over principles. If the thesis's described aggregation rule does not produce 0.9231 from the stated dimension scores, flag.

6. **OWL/RDF/SKOS terminology.** Where the thesis says `owl:sameAs`, `skos:exactMatch`, or similar, confirm the usage is semantically defensible.

### C5. Writing quality (humanizer2 + anti-ai sweep)

Load `humanizer2` and `anti-ai` and apply their full checklists to:

1. **Abstract (EN/FR/TR)** — verify no AI-pattern tells.
2. **Every new paragraph added on 2026-05-16** — these are the highest-risk for AI patterns because they were written by an editing agent. Locate them with `git log -p` if available, or compare against the May 15 backup at `Thesis/OğuzhanGüngör_Tez (1)/thesis.tex.backup1`.
3. **The five Future Work paragraphs in §5.4** — particularly likely to fall into the "rule of three" / "vague attributions" / "AI vocabulary" patterns.
4. **The four-rates discussion in §4.6** — recently rewritten, watch for AI symptoms.
5. **The Limitations paragraphs in §5.3** — recently rewritten.

Quantify your findings. Report the per-section AI-pattern score and list the top 10 worst sentences.

Specifically flag:
- Em-dash overuse (the writer was told to avoid these; verify compliance)
- "rule of three" lists where two or four items would be more natural
- AI-vocabulary tells: "robust", "comprehensive", "novel", "intricate", "delve", "underscore", "leverage", "facilitate", "moreover", "furthermore"
- "It is important to note that" / "It should be emphasized" / "Notably" filler
- Vague attributions: "studies have shown", "researchers have found" (without citation)
- Negative parallelism: "not just A but B also"
- Inflated symbolism / hedging
- Run-on sentences over 60 words

Where you find an AI pattern, quote the offending sentence and propose a 1-line rewrite (not a full rewrite — just enough to show the alternative).

### C6. Citation and bibliography hygiene

1. **Every `\cite{key}` resolves** — should already be true; verify.
2. **Every bib entry is used at least once** — flag unused entries. (138 entries, 89 used per last audit — that's 49 unused. Flag the 49 as P3 for the user to decide whether to prune.)
3. **Every claim that needs a citation has one** — in particular:
   - Any claim about a comparator KG (AlzKB, AD-DPC, ADKG) must cite the paper.
   - Any methodological claim (FAIR, Biolink, OBO Relation Ontology, MONDO, DOID, GO, HPO, SNOMED-CT, LOINC, UBERON, ICD-10) must cite the source ontology paper or specification.
   - Any factual claim about AD biology (Jack cascade, ATN framework, APOE, biomarker temporal ordering) must cite a paper.
4. **Cited numbers in the comparator table** — the [V] markers in §5.2 Table 5.1 indicate "verify against the source paper". Actually verify them using `research-lookup` or `WebSearch` against the named papers. Flag any [V] cell that turns out wrong.

### C7. LaTeX / build hygiene

1. **All `\ref{}` resolve to a `\label{}`** — recheck.
2. **All environments balance** (comment-aware) — recheck.
3. **All `\includegraphics{}` references resolve to a file in `Thesis/OğuzhanGüngör_Tez (1)/Figures/`** — recheck.
4. **Run `pdflatex` end-to-end**:
   ```
   cd "Thesis/OğuzhanGüngör_Tez (1)"
   pdflatex -interaction=nonstopmode thesis.tex
   bibtex thesis
   pdflatex -interaction=nonstopmode thesis.tex
   pdflatex -interaction=nonstopmode thesis.tex
   ```
   Capture every warning and every overfull/underfull box ≥ 5pt. Report them grouped by severity.
5. **Visual check on the rendered PDF** — open the resulting `thesis.pdf` (use the Read tool with pages argument for spot-checks of figures, tables, layout). Check at minimum:
   - Table 4.5 split actually fits the page
   - Figure 4.x (per-step density) renders correctly
   - Figure 4.alzkb (f5_alignment.pdf) shows what the caption claims
   - Abstract pages render cleanly
   - TOC, LoF, LoT are populated
   - No orphan figure floating to wrong page

### C8. Defensibility (jury attack surface)

For a thesis defense, examiners typically pick on:

1. **Definitions that hide a circularity.** Example: the thesis defines "strong match" as a `SAME_AS` edge between an `OntologyConcept` and an `AlzKBConcept`. But the `SAME_AS` edges are themselves added by the alignment routine in Step 24. Examiner question: "Isn't this measuring what you built?" Locate every such circular definition and flag.

2. **Cherry-picked baselines.** Example: the per-step audit's "pre-Step-30 baseline" is the post-Steps-17–20 state. Why not the IEEE-paper LPG baseline? Locate every place a baseline is chosen and verify the choice is justified.

3. **"Intersection-based metric" disclosures.** The Gene 5/5 100% number is intersection-based. The thesis discloses this. Verify the disclosure is in EVERY place the 100% number appears (abstract, intro, §4.6, §5 conclusion). If any place mentions 5/5 without the intersection caveat, flag.

4. **Causal-discovery scoping.** The thesis says the causal work is paused. Verify NO results from the causal work are quoted anywhere. Verify the causal-discovery prose is confined to literature review (Ch.2) and Future Work (§5.4).

5. **Reproducibility claims that can't be verified.** The thesis says the pipeline is reproducible. Spot-check: pick three claims (e.g., "the 264 mapping rules are version-controlled", "the validity rubric is in `metrics/validity_rubric.yaml`", "the AlzKB cypherl ingestion is in `steps/step24_alzkb_bridge.py`") and verify the files actually exist with the expected content.

6. **Generalisability claim (Claim 4).** The thesis claims the methodology generalises to other clinical cohorts but Claim 4 is "deferred by design". Verify the wording does not over-promise. Verify there is no place where the thesis implicitly claims to have validated Claim 4.

---

## 5. Specific things the writing agent might have missed

Use these as priors. Do not stop at this list, but use it to know what classes of issue are plausible.

1. **`f5_alignment.pdf` is dated 2026-05-09.** Before the Gene category went from N/A to 5/5. The file caption in the thesis says it shows the four in-scope categories. The rendered figure may still show only three (Disease, Anatomy, Phenotype) with Gene row hatched as "out of scope". Confirm. If true, this is a P0 because the figure contradicts the text.

2. **The per-step audit table baseline row.** The pre-Step-30 row uses May-9 numbers (443,131 / 1,509,297 / 51 / 100,770 / 0.9957). Verify these numbers are actually correct for the post-Steps-17–20 state by reading `outputs/metrics/per_step_audit.json` if it has a pre_step_30 entry. If the file's `pre_step_30` block disagrees with the table row, flag.

3. **OntoQA footnote in §5.4.** The footnote is the only allowed mention. Verify it does not also leak OntoQA terminology into the abstract, into §4.1 indicator definitions, or anywhere else outside that single footnote.

4. **Mapping count summation.** The thesis says 264 rules across 12 files and lists the per-file counts inline in §3.5. Sum the per-file counts and confirm they equal 264. The per-file counts also appear in the Publications appendix; the two listings must agree. Sum both and confirm equality.

5. **`12.25 avg properties` vs `13.34 measured`.** The thesis cites F2 at 12.25 avg properties. `fair_score.json` actually shows `13.3368`. The writing agent followed the brief's quoted number. If `canonical_snapshot.json` also has `12.2479` (let me check…) — confirm the source. If the canonical disagrees with fair_score, that's a metric-pipeline bug to flag separately.

6. **Article.tex section labels.** The thesis was reconstructed in pieces; verify the article.tex `\label{sec:eval-density}` and similar still match their `\ref{}` callers.

7. **Bibliography sort order / DOI accuracy.** Spot-check 5 random bib entries for correct DOIs.

8. **Embedded code-style snippets.** The thesis has `\begin{verbatim}` blocks for Cypher and Python-style migration code. Confirm each is syntactically valid for the language it claims to be.

9. **Turkish ş, ğ, ü, ç, ı characters in the abstract.** Verify they render correctly under pdflatex (the writing agent used LaTeX escape sequences `\c{s}`, `\u{g}`, `\"{u}`, `\c{c}`, `\i`). Spot-check the rendered PDF.

10. **The closing remark in §5.5.** Should mention "four in-scope categories" now, not three. Verify.

---

## 6. Process — execute in this order

Stage your work so subagents can parallelise where appropriate.

### Stage 1 — set up (do not parallelise)
1. Read `THESIS_EDIT_BRIEF_2026-05-16.md` end to end.
2. Read `canonical_snapshot.json`, `fair_score.json`, `alzkb_alignment.json`, `per_step_audit.json`.
3. Read `thesis.tex` end to end. Note section line ranges.
4. Read `article.tex` end to end.
5. Build an internal table of every numeric claim in the thesis with its location and its canonical source.

### Stage 2 — spawn subagents (parallelise)
Spawn three to five parallel subagents via the `Task` tool, each with a tight scope and a short report (~250 words max each):

- **Subagent A** — Numeric audit (C1) against canonical JSONs. Output: table of every number, location, claimed vs canonical, mismatch flag.
- **Subagent B** — Writing quality (C5). Output: top 20 worst sentences for AI patterns, with proposed rewrites.
- **Subagent C** — KG correctness (C4). Output: every ontology code or schema claim with a verdict.
- **Subagent D** — Citation / external-paper verification (C6). Use research-lookup. Output: bib hygiene + verification of [V] cells in §5.2.
- **Subagent E** — LaTeX build + figure rendering (C7). Output: pdflatex log warnings, figure-vs-caption mismatches found in the PDF.

While the subagents run, you handle C2 (internal consistency), C3 (promised vs delivered), and C8 (defensibility) yourself — these need cross-chapter reasoning that subagents would have to re-read everything to do.

### Stage 3 — consolidate
Merge subagent outputs into a single report at `outputs/audit/THESIS_AUDIT_REPORT_<YYYYMMDD>.md`. Group findings by severity (P0/P1/P2/P3), then by category. Each finding follows the format below.

### Stage 4 — present
Hand the report back as a single concise summary message (one paragraph per category, plus the top 10 P0/P1 findings inline). Reference the full report file for the rest. Ask the user which findings they want fixed; do not fix anything without explicit instruction.

---

## 7. Finding format (required schema)

Every finding in the report uses this format. Do not deviate.

```markdown
### F-NNN — [Category] One-line summary

- **Severity:** P0 / P1 / P2 / P3
- **Location:** thesis.tex line(s) X–Y (or article.tex / bib / Figures/)
- **Issue:** What is wrong, in one or two sentences.
- **Evidence:**
  - Quoted thesis text (verbatim).
  - Canonical source contradicting it (file path + line / JSON key + value).
- **Suggested fix:** One-line sketch of how to fix. Not a full rewrite.
- **Confidence:** High / Medium / Low — how sure you are this is a defect.
```

**Numbering.** Number findings F-001 through F-NNN in the order you discover them.

**Severity calibration.**
- **P0** — Embarrasses the author in front of the jury. Examples: numeric over-claim, figure contradicts caption, undefined reference rendering as "??", mathematical aggregation that doesn't work out, a stated method that the code doesn't implement.
- **P1** — A journal reviewer would request revision. Examples: missing citation for a non-trivial claim, internal inconsistency between chapters, AI-pattern sentence in the abstract, ambiguous definition of a key metric.
- **P2** — Polish defect that hurts readability or professional impression. Examples: AI-pattern sentence in the body, awkward sentence flow, em-dash overuse in body prose, redundant table column, suboptimal figure placement.
- **P3** — Cosmetic. Examples: trailing whitespace, inconsistent capitalisation of "Knowledge Graph" vs "knowledge graph", unused bib entry.

**Confidence calibration.**
- **High** — Verified against canonical source or rendered PDF.
- **Medium** — Pattern-matched but not verified against canonical source.
- **Low** — Hunch / smell; needs human judgement.

Report ALL low-confidence findings even if you are unsure; mark them honestly. Better to flag and let the human dismiss than to silently skip.

---

## 8. Things you must NOT do

- Do not edit any `.tex` or `.bib` file. This is read-only audit.
- Do not regenerate figures. If a figure is stale, flag it, do not re-render.
- Do not rewrite paragraphs in your report. Quote the offending sentence, sketch a fix in one line, move on.
- Do not invent canonical numbers. If a number is not in `outputs/metrics/`, say so and mark the finding low-confidence.
- Do not parrot the writing agent's brief. Your job is to find what the writing agent missed, not to confirm what the brief said.
- Do not collapse multiple distinct issues into a single finding. One finding per defect.
- Do not skip categories. If a category yields zero findings, write "No findings — checks performed: …" so the reader knows the category was examined.
- Do not refer to "we" or "our" — you are the auditor, not a co-author.

---

## 9. Deliverable checklist

When you say "done", confirm all of the following are true:

- [ ] `outputs/audit/THESIS_AUDIT_REPORT_<YYYYMMDD>.md` exists.
- [ ] Report has a top-level summary table: total findings by (severity × category).
- [ ] Every numeric claim in the thesis has a row in the report's numeric-audit appendix, with a claimed-vs-canonical column.
- [ ] Every figure referenced by the thesis has a row in the report's figure-audit appendix, with a freshness verdict.
- [ ] `pdflatex` build log is captured at `outputs/audit/build.log` and the count of warnings / errors is in the summary table.
- [ ] At least three subagents were used in parallel for Stage 2.
- [ ] The report ends with a "Top 10 — fix these first" section ordered by (severity, defense-visibility).
- [ ] No findings have severity "Critical" or "Blocker" or other custom severities — only P0–P3.
- [ ] The report's "Top 10" section is no longer than 600 words.

---

## 10. Tone of the report

Write the report as an external examiner would. Direct, specific, calm. Do not soften findings with "this is a minor issue but". Do not pad with "overall the thesis is in good shape" disclaimers — the user knows. Quote what is wrong, point at where it lives, suggest the fix, move on.

Use British English (the thesis is in British English).

Do not use emoji.

Do not use the words "robust", "comprehensive", "novel", "intricate", "delve", "leverage", "facilitate", "moreover", "furthermore" in the report itself.

---

## 11. One escape hatch

If at any point you discover that the canonical metrics files themselves are inconsistent (e.g., `canonical_snapshot.json` and `fair_score.json` disagree on F2 average properties), stop the per-thesis audit and write a finding about the metric-pipeline inconsistency first. The thesis cannot be audited against an inconsistent source of truth. Flag this as a meta-P0 and ask the user how to proceed.

---

End of brief. Start with Stage 1.
