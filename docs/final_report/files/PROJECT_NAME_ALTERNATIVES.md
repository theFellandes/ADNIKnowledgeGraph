# Project Name Alternatives

The current acronym **CauAD** stands for *Causal Alzheimer's Disease* and was chosen when causal discovery sat at the centre of the thesis. The scope has since shifted to ontology selection, mapping, and evaluation for a multimodal AD knowledge graph, with cross-KG alignment as the primary contribution. The name no longer reflects what the project does, so it needs to change.

## Selection criteria

A new name should:

1. Drop the causality reference (no `Cau-` prefix).
2. Capture the three pillars now in scope: **multimodal**, **ontology-grounded**, **Alzheimer's KG**.
3. Be short enough to use as a code repo name and a paper acronym.
4. Be pronounceable in English and not collide with existing AD KG names (AlzKB, ADKG, AD-DPC).
5. Leave room for the causal extension to return later as a follow-up work without a second rename.

## Recommended candidates

Ranked by how well they fit the criteria above.

### 1. **MAKO** — *Multimodal Alzheimer's Knowledge graph with Ontology grounding*

Short, easy to say, easy to type. The "K" carries both *Knowledge* and *Knowledge graph*, the "O" carries both *Ontology* and *Ontology-grounded*. Reads naturally in figure captions ("the MAKO graph contains..."). No collision with AlzKB, ADKG, or AlzPath. Strong first choice.

### 2. **OMAK** — *Ontology-grounded Multimodal Alzheimer's Knowledge graph*

Same letters as MAKO, reordered to put *Ontology* first, which matches the paper's framing (ontology selection comes before everything else in the methodology). Pronounces "oh-mack". A bit harder than MAKO to read fluently in prose.

### 3. **MAKER** — *Multimodal Alzheimer's Knowledge graph with Evaluation and Reconciliation*

The "E" gives space to talk about OntoQA / FAIR / semantic density evaluation, and the "R" gives space to talk about cross-vocabulary reconciliation with AlzKB. Pronounces as a real English word. Slightly long but fits the paper's contribution map exactly.

### 4. **OntoAD-KG** — *Ontology-grounded Alzheimer's Disease Knowledge Graph*

Most descriptive. No invented acronym, so no learning curve for the reader. Loses the *multimodal* qualifier, which has to be added in prose every time.

### 5. **BrAID-KG** — *Bridging Alzheimer's Information Domains – Knowledge Graph*

Centres the cross-vocabulary alignment story (clinical SNOMED/LOINC/ICD on one side, molecular GO/DOID/CHEBI on the other) which is the core of the unified C7 contribution. Pronounces as "braid", which fits the bridging metaphor. A bit on-the-nose.

### 6. **AlignAD** — *Alignment-driven Alzheimer's Disease Knowledge Graph*

Foregrounds cross-KG alignment as the project's identity. Risks reading as an alignment-only tool and underselling the upstream ontology selection and migration work.

### 7. **MOAK** — *Multimodal Ontology-grounded Alzheimer's Knowledge graph*

Variant of MAKO. Clean, but "moak" reads more awkwardly than "mako" in English.

### 8. **PAMAK** — *Patient-level Aligned Multimodal Alzheimer's Knowledge graph*

Highlights that the KG is patient-centric (every node ultimately attaches to a Patient hub), which differentiates it from literature-derived KGs like ADKG. Long and harder to remember.

## Names considered and rejected

- **SemMAD / OntoMAD** — the "MAD" suffix has the obvious unwanted connotation in a clinical context.
- **MultiAD-KG** — descriptive but flat, no acronym character.
- **CauAD-2 / CauAD-Onto** — preserves brand continuity with the IEEE Big Data 2025 paper but keeps the causality reference, which is exactly what we are trying to drop.

## Suggestion

Go with **MAKO** for the rename. Short, distinctive, says all three pillars in four letters, and works equally well as a thesis title acronym, repo name, and paper short title. If the reviewers later prefer something more self-explanatory, **OntoAD-KG** is the safe fallback. Keep **CauAD** alive only as a historical reference to the published IEEE Big Data 2025 paper, since renaming that retroactively is not possible.

## Continuity note

The IEEE Big Data 2025 paper (DOI: 10.1109/BigData66926.2025.11402185) is published under CauAD and that reference is now permanent. The thesis and the new ontology paper can introduce MAKO as the project name with a sentence such as: "This work was previously published as part of the CauAD project (Güngör et al., 2025); the project has since been renamed MAKO to reflect the shift in scope from causal discovery to ontology selection and cross-KG alignment."
