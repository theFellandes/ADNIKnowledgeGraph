// remap_doid_mci.cypher
// =====================
// One-shot remap: DOID:0050169 → DOID:0080832 for "Mild cognitive impairment".
//
// Background
// ----------
// Step 34 (steps/step34_mondo_doid_wiring.py) originally hardcoded the
// MCI concept as DOID:0050169. The Disease Ontology actually records
//   DOID:0050169  =  cutaneous lupus erythematosus
//   DOID:0080832  =  mild cognitive impairment  ← canonical
// This script rewrites the OntologyConcept node, the MAPS_TO edges that
// point at it, and the Diagnosis.doid_code property in one transaction.
//
// Run from cypher-shell (Windows PowerShell, project root):
//
//     cypher-shell -u neo4j -p <YOUR_PASSWORD> -d neo4j -f scripts/remap_doid_mci.cypher
//
// Or paste into Neo4j Browser block by block.
// All operations are idempotent (the WHERE filters short-circuit on a
// second run).

// 1. Rewrite the OntologyConcept node ----------------------------------
MATCH (o:OntologyConcept {source_ontology: 'DOID'})
WHERE o.code IN ['0050169', 'DOID:0050169', 'doid:0050169']
SET o.code  = '0080832',
    o.label = 'Mild cognitive impairment',
    o.uri   = 'http://purl.obolibrary.org/obo/DOID_0080832'
RETURN count(o) AS ontology_concept_updated;

// 2. Rewrite every MAPS_TO edge that still carries the old URI --------
MATCH ()-[r:MAPS_TO]->()
WHERE r.uri IN [
        'DOID:0050169',
        'doid:0050169',
        'http://purl.obolibrary.org/obo/DOID_0050169'
      ]
SET r.uri = 'http://purl.obolibrary.org/obo/DOID_0080832'
RETURN count(r) AS maps_to_edges_updated;

// 3. Rewrite Diagnosis.doid_code wherever it still holds the old value
MATCH (d:Diagnosis)
WHERE d.doid_code IN ['0050169', 'DOID:0050169', 'doid:0050169']
SET d.doid_code = 'DOID:0080832'
RETURN count(d) AS diagnosis_doid_code_updated;

// 4. Verification — print the three DOID concepts in the graph -------
// Expect:
//   DOID:0080832 — Mild cognitive impairment
//   DOID:10652   — Alzheimer's disease
//   DOID:1307    — Dementia
MATCH (o:OntologyConcept {source_ontology: 'DOID'})
RETURN o.code AS code, o.label AS label, o.uri AS uri
ORDER BY o.code;
