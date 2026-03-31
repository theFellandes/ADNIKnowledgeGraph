"""
Step 23 – Embed CAUSES Edges in Neo4j
======================================
Reads the consensus edges from Step 22 and creates :CAUSES relationships
in the knowledge graph, linking OntologyConcept nodes.

Each CAUSES edge carries:
    - algorithms: list of algorithms that found it
    - confidence: fraction of algorithms that agree
    - edge_type: '-->' (directed) or '---' (undirected)
    - discovered_at: timestamp
    - discovery_method: 'causal_learn'
    - uri: 'ro:RO_0002411' (causally_upstream_of)

Output
------
- CAUSES relationships in Neo4j
- causal/causes_embedding_report.json  (summary of what was embedded)
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# VARIABLE → ONTOLOGY CONCEPT MAPPING
# ────────────────────────────────────────────────────────────────
#
# Maps causal feature column names to OntologyConcept identifiers.
# These mappings align with the ontology codes assigned in Steps 18-20.
# When no exact OntologyConcept exists, we fall back to creating a
# lightweight :CausalVariable node.

VARIABLE_CONCEPT_MAP = {
    # Demographics
    'age':            {'label': 'Age', 'uri': 'ncit:C25150', 'source': 'NCI'},
    'gender':         {'label': 'Gender', 'uri': 'ncit:C17357', 'source': 'NCI'},
    'education':      {'label': 'Education Years', 'uri': 'ncit:C17953', 'source': 'NCI'},
    'apoe_e4_count':  {'label': 'APOE e4 Allele Count', 'uri': 'hpo:HP:0002650', 'source': 'HPO'},

    # Cognitive tests (LOINC codes from Step 18)
    'COG_MMSE':       {'label': 'MMSE Score', 'uri': 'loinc:72106-8', 'source': 'LOINC'},
    'COG_CDR':        {'label': 'CDR Score', 'uri': 'loinc:70785-1', 'source': 'LOINC'},
    'COG_ADAS-COG-13': {'label': 'ADAS-Cog-13 Score', 'uri': 'loinc:LP73768-2', 'source': 'LOINC'},
    'COG_ADAS-COG':   {'label': 'ADAS-Cog Score', 'uri': 'loinc:LP73768-2', 'source': 'LOINC'},
    'COG_MOCA':       {'label': 'MoCA Score', 'uri': 'loinc:72133-2', 'source': 'LOINC'},
    'COG_FAQ':        {'label': 'FAQ Score', 'uri': 'loinc:LP73768-2', 'source': 'LOINC'},
    'COG_LOGICAL MEMORY': {'label': 'Logical Memory', 'uri': 'loinc:LP73768-2', 'source': 'LOINC'},

    # CSF Biomarkers
    'BIO_ABETA':      {'label': 'CSF Amyloid-β42', 'uri': 'loinc:49325-0', 'source': 'LOINC'},
    'BIO_ABETA42':    {'label': 'CSF Amyloid-β42', 'uri': 'loinc:49325-0', 'source': 'LOINC'},
    'BIO_AB42':       {'label': 'CSF Amyloid-β42', 'uri': 'loinc:49325-0', 'source': 'LOINC'},
    'BIO_TAU':        {'label': 'CSF Total Tau', 'uri': 'loinc:49327-6', 'source': 'LOINC'},
    'BIO_TAU_TOTAL':  {'label': 'CSF Total Tau', 'uri': 'loinc:49327-6', 'source': 'LOINC'},
    'BIO_PTAU':       {'label': 'CSF Phospho-Tau', 'uri': 'loinc:49326-8', 'source': 'LOINC'},
    'BIO_PTAU181':    {'label': 'CSF Phospho-Tau181', 'uri': 'loinc:49326-8', 'source': 'LOINC'},

    # Volumetric — UBERON codes from Step 18
    'VOL_Hippocampus': {'label': 'Hippocampus Volume', 'uri': 'uberon:UBERON:0002421', 'source': 'UBERON'},
    'VOL_Entorhinal':  {'label': 'Entorhinal Cortex Volume', 'uri': 'uberon:UBERON:0002728', 'source': 'UBERON'},
    'VOL_Ventricles':  {'label': 'Ventricular Volume', 'uri': 'uberon:UBERON:0004086', 'source': 'UBERON'},
    'VOL_WholeBrain':  {'label': 'Whole Brain Volume', 'uri': 'uberon:UBERON:0000955', 'source': 'UBERON'},
    'VOL_ICV':         {'label': 'Intracranial Volume', 'uri': 'uberon:UBERON:0000955', 'source': 'UBERON'},
    'VOL_MidTemp':     {'label': 'Middle Temporal Volume', 'uri': 'uberon:UBERON:0002771', 'source': 'UBERON'},
    'VOL_Fusiform':    {'label': 'Fusiform Gyrus Volume', 'uri': 'uberon:UBERON:0002764', 'source': 'UBERON'},

    # PET
    'PET_AV45':  {'label': 'Amyloid PET SUVR (AV45)', 'uri': 'ncit:C116466', 'source': 'NCI'},
    'PET_FDG':   {'label': 'FDG-PET SUVR', 'uri': 'ncit:C17007', 'source': 'NCI'},
    'PET_AV1451': {'label': 'Tau PET SUVR (AV1451)', 'uri': 'ncit:C116466', 'source': 'NCI'},
    'PET_FBB':   {'label': 'Amyloid PET SUVR (FBB)', 'uri': 'ncit:C116466', 'source': 'NCI'},
    'PET_FBP':   {'label': 'Amyloid PET SUVR (FBP)', 'uri': 'ncit:C116466', 'source': 'NCI'},

    # ATN
    'ATN_A': {'label': 'Amyloid Status (A)', 'uri': 'ncit:C116466', 'source': 'NCI'},
    'ATN_T': {'label': 'Tau Status (T)', 'uri': 'ncit:C164342', 'source': 'NCI'},
    'ATN_N': {'label': 'Neurodegeneration Status (N)', 'uri': 'hpo:HP:0002180', 'source': 'HPO'},

    # Diagnosis
    'DX_bl': {'label': 'Baseline Diagnosis', 'uri': 'snomed:26929004', 'source': 'SNOMED-CT'},
}


# ────────────────────────────────────────────────────────────────
# CYPHER TEMPLATES
# ────────────────────────────────────────────────────────────────

# Ensure CausalVariable nodes exist (for variables without an OntologyConcept match)
MERGE_CAUSAL_VARIABLE = """
MERGE (cv:CausalVariable {variable_id: $variable_id})
ON CREATE SET
    cv.label = $label,
    cv.uri = $uri,
    cv.source_ontology = $source,
    cv.created_at = datetime()
RETURN cv.variable_id AS id
"""

# Create CAUSES relationship (try OntologyConcept first, fall back to CausalVariable)
MERGE_CAUSES_VIA_CONCEPT = """
UNWIND $edges AS edge
MERGE (src:CausalVariable {variable_id: edge.source_id})
ON CREATE SET src.label = edge.source_label, src.uri = edge.source_uri,
              src.source_ontology = edge.source_ontology, src.created_at = datetime()
MERGE (tgt:CausalVariable {variable_id: edge.target_id})
ON CREATE SET tgt.label = edge.target_label, tgt.uri = edge.target_uri,
              tgt.source_ontology = edge.target_ontology, tgt.created_at = datetime()
MERGE (src)-[r:CAUSES]->(tgt)
SET r.algorithms = edge.algorithms,
    r.confidence = edge.confidence,
    r.edge_type = edge.edge_type,
    r.n_algorithms = edge.n_algorithms,
    r.discovered_at = datetime(),
    r.discovery_method = 'causal_learn',
    r.uri = 'ro:RO_0002411'
"""

# Also link CausalVariable to OntologyConcept via MAPS_TO (if concept exists)
LINK_CAUSAL_TO_ONTOLOGY = """
MATCH (cv:CausalVariable {variable_id: $variable_id})
MATCH (oc:OntologyConcept {uri: $uri})
MERGE (cv)-[r:MAPS_TO]->(oc)
ON CREATE SET r.uri = 'skos:exactMatch', r.created_at = datetime()
"""

# Count CAUSES edges
COUNT_CAUSES = """
MATCH ()-[r:CAUSES]->() RETURN count(r) AS total
"""


# ────────────────────────────────────────────────────────────────
# Embedder class
# ────────────────────────────────────────────────────────────────

class CausalEdgeEmbedder:
    """Embeds consensus causal edges into Neo4j."""

    def __init__(self, connector, config: Dict[str, Any]):
        self.connector = connector
        self.config = config.get('causal', {})
        self.output_dir = Path(config.get('output_dir', 'causal'))

    def execute(self) -> Dict[str, Any]:
        """Main entry point."""
        logger.info("=" * 60)
        logger.info("STEP 23 — Embed CAUSES Edges in Neo4j")
        logger.info("=" * 60)

        results = {
            'step': 23,
            'status': 'started',
            'timestamp': datetime.now().isoformat(),
        }

        try:
            # 1. Load consensus edges
            consensus_path = self.output_dir / 'consensus_edges.json'
            if not consensus_path.exists():
                raise FileNotFoundError(
                    f"Consensus edges not found at {consensus_path}. "
                    "Run Step 22 first."
                )

            with open(consensus_path) as f:
                consensus = json.load(f)

            logger.info(f"  Loaded {len(consensus)} consensus edges")

            if not consensus:
                logger.warning("No consensus edges to embed")
                results['status'] = 'completed'
                results['edges_embedded'] = 0
                return results

            # 2. Build edge data for Cypher
            edge_data = self._build_edge_data(consensus)
            logger.info(f"  Prepared {len(edge_data)} edge records for embedding")

            # 3. Embed CAUSES edges
            self._embed_causes(edge_data)

            # 4. Link CausalVariables to OntologyConcepts
            linked = self._link_to_ontology(edge_data)

            # 5. Verify
            count_result = self.connector.run_query(COUNT_CAUSES)
            total_causes = count_result[0]['total'] if count_result else 0

            # 6. Save report
            report = {
                'edges_embedded': len(edge_data),
                'causal_variables_created': self._count_causal_variables(),
                'ontology_links_created': linked,
                'total_causes_in_graph': total_causes,
                'timestamp': datetime.now().isoformat(),
                'edges': [
                    {
                        'source': e['source_label'],
                        'target': e['target_label'],
                        'confidence': e['confidence'],
                        'algorithms': e['algorithms'],
                    }
                    for e in edge_data
                ]
            }

            report_path = self.output_dir / 'causes_embedding_report.json'
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"  Saved report: {report_path}")

            results.update({
                'status': 'completed',
                'edges_embedded': len(edge_data),
                'total_causes': total_causes,
                'report_path': str(report_path),
            })
            logger.info(f"✅ Step 23 complete — {total_causes} CAUSES edges in graph")

        except Exception as e:
            logger.error(f"Step 23 failed: {e}", exc_info=True)
            results['status'] = 'failed'
            results['error'] = str(e)

        return results

    # ── Build edge data ──────────────────────────────────────

    def _build_edge_data(self, consensus: List[Dict]) -> List[Dict]:
        """Map variable names to concept IDs and prepare edge records."""
        edge_data = []

        for edge in consensus:
            src_info = self._get_concept_info(edge['source'])
            tgt_info = self._get_concept_info(edge['target'])

            edge_data.append({
                'source_id': src_info['id'],
                'source_label': src_info['label'],
                'source_uri': src_info['uri'],
                'source_ontology': src_info['source'],
                'target_id': tgt_info['id'],
                'target_label': tgt_info['label'],
                'target_uri': tgt_info['uri'],
                'target_ontology': tgt_info['source'],
                'algorithms': edge['algorithms'],
                'confidence': edge['confidence'],
                'edge_type': edge['edge_type'],
                'n_algorithms': edge.get('n_algorithms', len(edge['algorithms'])),
            })

        return edge_data

    def _get_concept_info(self, variable_name: str) -> Dict:
        """Look up concept info for a variable name."""
        if variable_name in VARIABLE_CONCEPT_MAP:
            info = VARIABLE_CONCEPT_MAP[variable_name]
            return {
                'id': variable_name,
                'label': info['label'],
                'uri': info['uri'],
                'source': info['source'],
            }
        else:
            # Fallback: create a generic concept
            return {
                'id': variable_name,
                'label': variable_name.replace('_', ' ').title(),
                'uri': f'adni:{variable_name}',
                'source': 'ADNI',
            }

    # ── Embed ────────────────────────────────────────────────

    def _embed_causes(self, edge_data: List[Dict]) -> None:
        """Create CAUSES relationships in Neo4j."""
        logger.info("  Embedding CAUSES relationships...")

        # Batch all edges in one UNWIND
        self.connector.run_query(MERGE_CAUSES_VIA_CONCEPT, {'edges': edge_data})
        logger.info(f"  Embedded {len(edge_data)} CAUSES edges")

    def _link_to_ontology(self, edge_data: List[Dict]) -> int:
        """Link CausalVariable nodes to existing OntologyConcept nodes."""
        linked = 0
        seen_ids = set()

        for edge in edge_data:
            for prefix in ['source', 'target']:
                var_id = edge[f'{prefix}_id']
                uri = edge[f'{prefix}_uri']

                if var_id in seen_ids:
                    continue
                seen_ids.add(var_id)

                # Only try linking if we have a real ontology URI
                if uri.startswith('adni:'):
                    continue

                try:
                    self.connector.run_query(
                        LINK_CAUSAL_TO_ONTOLOGY,
                        {'variable_id': var_id, 'uri': uri}
                    )
                    linked += 1
                except Exception:
                    pass  # OntologyConcept may not exist for this URI

        logger.info(f"  Linked {linked} CausalVariables to OntologyConcepts")
        return linked

    def _count_causal_variables(self) -> int:
        """Count CausalVariable nodes in the graph."""
        result = self.connector.run_query(
            "MATCH (cv:CausalVariable) RETURN count(cv) AS c"
        )
        return result[0]['c'] if result else 0


# ────────────────────────────────────────────────────────────────
# CLI + pipeline integration
# ────────────────────────────────────────────────────────────────

def execute_causal_edges(config: Dict[str, Any],
                         connector=None) -> Dict[str, Any]:
    """Pipeline entry-point for Step 23."""
    if connector is None:
        from utils.neo4j_connector import Neo4jConnector
        connector = Neo4jConnector(
            config['neo4j']['uri'],
            config['neo4j']['user'],
            config['neo4j']['password']
        )

    embedder = CausalEdgeEmbedder(connector, config)
    return embedder.execute()


if __name__ == '__main__':
    import yaml
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
    )

    config_path = Path(__file__).parent.parent / 'config.yaml'
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
    else:
        config = {}

    config.setdefault('output_dir', 'causal')

    result = execute_causal_edges(config)
    print(json.dumps(result, indent=2, default=str))
