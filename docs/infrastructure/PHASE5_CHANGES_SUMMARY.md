# Phase 5: Exploration, Analysis & Idempotency Fixes

**Date:** 2026-03-31
**Author:** Oguzhan Gungor (assisted by Claude Code)
**Scope:** Pipeline robustness, EDA, thesis figure generation, Cypher query library

---

## 1. Problem: Node Count Inconsistency

### Observation
The step29 EDA dashboard reported **542.2K total nodes**, but a direct Neo4j query returned **421,396 nodes**.

### Root Cause
The EDA code (`step29_kg_eda.py:235`) used `CALL db.labels()` to count nodes per label, then summed the results. Nodes with **multiple labels** (e.g., a node labeled both `:Event` and `:ClinicalEvent`) were counted once per label, inflating the total by ~29%.

### Fix
Added a separate query `MATCH (n) RETURN count(n) AS cnt` for the true node count, used for the dashboard metric. The per-label breakdown remains unchanged for the bar chart (where showing per-label counts is correct).

**File:** `steps/step29_kg_eda.py` (line 235)

---

## 2. Problem: Pipeline Idempotency — Duplicate Nodes on Re-run

### Observation
Running the pipeline twice without adding new data increased counts:
- Nodes: 421,396 -> 426,054 (**+4,658**)
- Relationships: 1,413,130 -> 1,420,236 (**+7,106**)

### Root Causes Identified

Three files contained non-idempotent patterns:

#### 2a. `step15_event_based_model.py` — CREATE Instead of MERGE

**Problem:** 11 Cypher `CREATE` statements used for Event, EventChain, PatientTimeline, EventPattern, and ProgressionPattern nodes. Despite having deterministic IDs (e.g., `event_id: ptid + '_dx_change_' + months`), `CREATE` always generates new nodes regardless of existing data.

**Impact:** ~4,658 duplicate nodes per pipeline re-run.

**Fix:** Changed all 11 `CREATE` to `MERGE` on the deterministic ID field, with `ON CREATE SET` for initial timestamps and `SET` for updateable properties.

| # | Node Type | Merge Key | ID Expression |
|---|-----------|-----------|---------------|
| 1 | Event:ClinicalEvent | event_id | `ptid + '_dx_change_' + months_from + '_to_' + months_to` |
| 2 | Event:ClinicalEvent | event_id | `ptid + '_symptom_onset_' + test_name` |
| 3 | Event:BiomarkerEvent | event_id | `ptid + '_bio_change_' + analyte + '_' + viscode` |
| 4 | Event:BiomarkerEvent | event_id | `ptid + '_atn_transition_' + atn_stage` |
| 5 | Event:CognitiveEvent | event_id | `ptid + '_cog_decline_' + test + '_' + months` |
| 6 | Event:ImagingEvent | event_id | `ptid + '_pet_scan_' + image_hash` |
| 7 | Event:ImagingEvent | event_id | `ptid + '_hippocampal_atrophy_' + months` |
| 8 | EventChain | chain_id | `ptid + '_event_chain'` |
| 9 | PatientTimeline | timeline_id | `ptid + '_timeline'` |
| 10 | EventPattern | pattern_id | `replace(pattern, '->', '_')` |
| 11 | ProgressionPattern | pattern_id | `'rapid_progression_' + ptid` |

**Cypher pattern applied:**
```cypher
-- Before (non-idempotent):
CREATE (e:Event:ClinicalEvent {
    event_id: p.ptid + '_dx_change_' + ...,
    event_type: 'DIAGNOSIS_CHANGE',
    patient_id: p.ptid,
    ...,
    created_at: datetime()
})

-- After (idempotent):
MERGE (e:Event:ClinicalEvent {event_id: p.ptid + '_dx_change_' + ...})
ON CREATE SET e.created_at = datetime()
SET e.event_type = 'DIAGNOSIS_CHANGE',
    e.patient_id = p.ptid,
    ...,
    e.updated_at = datetime()
```

**File:** `steps/step15_event_based_model.py` (11 locations)

#### 2b. `step4_extract_family.py` — Non-Deterministic UUID in MERGE Key

**Problem:** FamilyMember node IDs were generated using `uuid.uuid4()`:
```python
member_id = f"fm_{uuid.uuid4().hex[:8]}"
```
Although the Cypher used `MERGE (fm:FamilyMember {member_id: ...})`, the random UUID meant MERGE never matched existing nodes — effectively behaving as CREATE.

**Fix:** Replaced with a deterministic hash derived from source data:
```python
deterministic_key = f"{ptid}_{relationship_type}_{column}"
member_id = f"fm_{hashlib.md5(deterministic_key.encode()).hexdigest()[:12]}"
```

This ensures the same patient + relationship type + source column always produces the same `member_id`, allowing MERGE to correctly match existing nodes.

**Changes:**
- Added `import hashlib`
- Added `ptid` parameter to `_extract_family_member_from_column()`
- Updated both caller sites to pass `ptid`

**File:** `steps/step4_extract_family.py` (line 213 + method signature + callers)

#### 2c. `step7_batch_insert.py` — Non-Deterministic Batch ID

**Problem:** Batch metadata IDs combined timestamp + UUID:
```python
self.batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
```
Each run created new BatchIngestion metadata nodes.

**Fix:** Changed to date-only deterministic ID:
```python
self.batch_id = f"batch_{datetime.now().strftime('%Y%m%d')}"
```

**File:** `steps/step7_batch_insert.py` (line 62)

### Idempotency Design Principle

The ADNI KG pipeline follows a **MERGE-based idempotency pattern**:

```
For each entity type:
  1. Derive a deterministic unique identifier from source data
     (ptid, visit_id, image_hash, diagnosis_id, etc.)
  2. Use MERGE on that identifier as the match key
  3. Use ON CREATE SET for immutable properties (created_at)
  4. Use SET for mutable properties (updated_at, computed fields)
```

This ensures:
- **New data:** MERGE finds no match -> creates new node
- **Existing data:** MERGE finds match -> updates properties in place
- **Re-runs:** Identical to existing data case -> no duplicates

---

## 3. Image Processing Checkpoint System

### Verified Behavior
Step 5 uses an **LMDB checkpoint database** to track processed files by SHA256 hash. On re-runs:

1. All 40,266 image files are scanned and their hashes checked against LMDB
2. Files already in the checkpoint are skipped entirely ("All files already processed!")
3. Neo4j insert runs for ALL metadata files on disk, but uses `MERGE (i:ImageNode {image_hash: ...})` — safe and idempotent
4. No duplicate ImageNode creation occurs

### JPEG2000 Status
- **glymur 0.14.7 + OpenJPEG 2.5.3** are installed and functional
- The `diagnostic_j2k/` directory is empty because images were first processed before glymur was configured
- The checkpoint system is **format-agnostic** — it marks files as "processed" without tracking which output formats were generated
- To generate J2K files for existing images, the LMDB checkpoint would need to be cleared or a format-aware reprocessing mechanism added
- A diagnostic log was added to warn when J2K is enabled but no files exist

---

## 4. Cypher Explorer Enhancements

### Graph Bubble Rendering Fix
Changed queries 10.5 and 10.6 from `RETURN path` to `RETURN p, r, n`. Neo4j Browser renders graph bubbles (node visualizations) when nodes and relationships are returned as separate columns, not wrapped in a path object.

### Patient Neighborhood Query (New: 10.6)
Added bidirectional query for full patient context:
```cypher
MATCH (p:Patient {ptid: 'PLACEHOLDER'})-[r]-(n)
RETURN p, r, n
LIMIT 50;
```

### ICD-10 Queries (New: 8.6-8.9)
Added 4 deep ICD-10 queries to the Ontology & Semantic Layer section:

| Query | Description |
|-------|-------------|
| 8.6 | CLASSIFIED_AS -> OntologyConcept mapping counts |
| 8.7 | IS_A hierarchy traversal (depth 1-3) |
| 8.8 | Diagnosis coverage gap (unmapped to ICD-10) |
| 8.9 | Full semantic chain: Patient -> Diagnosis -> CLASSIFIED_AS -> OntologyConcept |

**File:** `docs/cypher_explorer.cypher`

---

## 5. Thesis Figure Improvements

### lpg_vs_kg_query Redesign
Replaced plain-text Cypher code boxes with a proper visual graph diagram:
- **Left panel (LPG):** Three colored nodes (Patient -> Visit -> Diagnosis) in a linear chain with limitation annotations
- **Right panel (KG):** Same core chain plus OntologyConcept (MAPS_TO), AlzKBConcept (SAME_AS), and CausalVariable (CAUSES) edges
- Uses `FancyBboxPatch` for nodes and `annotate` with `arrowprops` for edges
- Publication-quality styling for thesis defense

**File:** `steps/step28_thesis_figures.py`

### Mermaid Diagrams for Overleaf

Created 5 Overleaf-compatible Mermaid (.mmd) diagrams:

| File | Content |
|------|---------|
| `kg_schema.mmd` | Full KG schema — 17 node types, 6 color-coded categories, all relationship types |
| `lpg_vs_kg.mmd` | Side-by-side LPG vs KG comparison with semantic/causal layer |
| `atn_cascade.mmd` | ATN biomarker cascade (A/T/N subgroups with CAUSES edges) |
| `icd10_tree.mmd` | ICD-10 hierarchy (G30 + F00 branches with cross-reference) |
| `causal_overlay.mmd` | Consensus causal discovery graph (20 nodes, 22 edges, 7 categories) |

**Location:** `thesis_output/mermaid/`

These can be rendered in Overleaf using the `mermaid` LaTeX package or in any Mermaid-compatible tool.

---

## 6. Phase Documentation

Created `PHASE5_EXPLORATION_ANALYSIS.md` documenting all Phase 5 work:
- Step 29 EDA (15 publication-quality figures)
- Cypher explorer (12 sections, 50+ queries)
- Pipeline idempotency fixes
- Thesis figure improvements
- Mermaid diagram generation

Updated `PHASE1_SCHEMA_MIGRATION.md` cross-references to reflect Phase 2-5 completion status.

---

## Files Modified

| File | Changes |
|------|---------|
| `steps/step15_event_based_model.py` | 11 CREATE -> MERGE for idempotency |
| `steps/step4_extract_family.py` | Deterministic member_id (hashlib MD5) |
| `steps/step7_batch_insert.py` | Deterministic batch_id (date-only) |
| `steps/step29_kg_eda.py` | True node count query |
| `steps/step28_thesis_figures.py` | Redesigned lpg_vs_kg figure |
| `steps/step5_improved_process_images.py` | J2K diagnostic check |
| `docs/cypher_explorer.cypher` | ICD-10 queries, patient neighborhood, graph bubble fix |
| `docs/infrastructure/history/PHASE5_EXPLORATION_ANALYSIS.md` | Phase 5 documentation |
| `docs/infrastructure/history/PHASE1_SCHEMA_MIGRATION.md` | Cross-reference updates |

## Files Created

| File | Purpose |
|------|---------|
| `thesis_output/mermaid/kg_schema.mmd` | KG schema for Overleaf |
| `thesis_output/mermaid/lpg_vs_kg.mmd` | LPG vs KG comparison for Overleaf |
| `thesis_output/mermaid/atn_cascade.mmd` | ATN cascade for Overleaf |
| `thesis_output/mermaid/icd10_tree.mmd` | ICD-10 hierarchy for Overleaf |
| `thesis_output/mermaid/causal_overlay.mmd` | Causal graph for Overleaf |

---

## Cleanup Required

To remove existing duplicate nodes created before the fixes:
```cypher
// Remove duplicate Event nodes (keep oldest per event_id)
MATCH (e:Event)
WITH e.event_id AS eid, collect(e) AS dupes
WHERE size(dupes) > 1
WITH dupes[1..] AS extras
UNWIND extras AS extra
DETACH DELETE extra;

// Repeat for EventChain, PatientTimeline, EventPattern, ProgressionPattern
// using chain_id, timeline_id, pattern_id respectively
```

## Verification Queries
```cypher
// Confirm no duplicates remain
MATCH (e:Event) WITH e.event_id AS eid, count(*) AS c WHERE c > 1 RETURN eid, c;
MATCH (ec:EventChain) WITH ec.chain_id AS cid, count(*) AS c WHERE c > 1 RETURN cid, c;

// Confirm total counts match
MATCH (n) RETURN count(n) AS total_nodes;
MATCH ()-[r]->() RETURN count(r) AS total_relationships;
```
