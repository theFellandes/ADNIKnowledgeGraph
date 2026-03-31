"""
Step 27 – Final Statistics
==========================
Queries Neo4j for comprehensive graph statistics and generates a
human-readable report for thesis defense.

Output
------
- thesis_output/final_stats.json
- thesis_output/final_stats.md
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# QUERIES
# ────────────────────────────────────────────────────────────────

Q_NODE_COUNTS = """
CALL db.labels() YIELD label
CALL {
    WITH label
    MATCH (n) WHERE label IN labels(n)
    RETURN count(n) AS cnt
}
RETURN label, cnt ORDER BY cnt DESC
"""

Q_REL_COUNTS = """
CALL db.relationshipTypes() YIELD relationshipType AS type
CALL {
    WITH type
    MATCH ()-[r]->() WHERE type(r) = type
    RETURN count(r) AS cnt
}
RETURN type, cnt ORDER BY cnt DESC
"""

Q_ONTOLOGY_COVERAGE = """
MATCH (n)
WHERE NOT n:OntologyConcept AND NOT n:AlzKBConcept AND NOT n:CausalVariable
WITH count(n) AS total_data_nodes
OPTIONAL MATCH (n)-[:MAPS_TO]->(:OntologyConcept)
WHERE NOT n:OntologyConcept AND NOT n:AlzKBConcept AND NOT n:CausalVariable
WITH total_data_nodes, count(DISTINCT n) AS mapped_nodes
RETURN total_data_nodes, mapped_nodes,
       CASE WHEN total_data_nodes > 0
            THEN toFloat(mapped_nodes) / total_data_nodes * 100
            ELSE 0 END AS coverage_pct
"""

Q_ICD10_DEPTH = """
MATCH path = (root:OntologyConcept)-[:HAS_CHILD*]->(leaf:OntologyConcept)
WHERE root.source = 'ICD-10'
RETURN max(length(path)) AS max_depth,
       avg(length(path)) AS avg_depth,
       count(DISTINCT leaf) AS leaf_count
"""

Q_CAUSAL_SUMMARY = """
MATCH ()-[r:CAUSES]->()
WITH count(r) AS total,
     collect(r.algorithms) AS all_algos,
     sum(CASE WHEN r.validated_by_literature = true THEN 1 ELSE 0 END) AS validated
RETURN total, validated,
       CASE WHEN total > 0
            THEN toFloat(validated) / total * 100
            ELSE 0 END AS validation_rate
"""

Q_GRAPH_DENSITY = """
MATCH (n) WITH count(n) AS nodes
MATCH ()-[r]->() WITH nodes, count(r) AS rels
RETURN nodes, rels,
       CASE WHEN nodes > 1
            THEN toFloat(rels) / (toFloat(nodes) * (toFloat(nodes) - 1))
            ELSE 0 END AS density,
       CASE WHEN nodes > 0
            THEN toFloat(rels * 2) / toFloat(nodes)
            ELSE 0 END AS avg_degree
"""

Q_CONNECTED_COMPONENTS = """
MATCH (n)
WHERE NOT (n)--()
RETURN count(n) AS isolated_nodes
"""

Q_ALZKB_STATS = """
MATCH (a:AlzKBConcept) WITH count(a) AS concepts
OPTIONAL MATCH ()-[r:SAME_AS]->() WITH concepts, count(r) AS same_as
OPTIONAL MATCH ()-[r:ALZKB_RELATES_TO]->() WITH concepts, same_as, count(r) AS internal_rels
RETURN concepts, same_as, internal_rels
"""

Q_CAUSAL_ALGO_BREAKDOWN = """
MATCH ()-[r:CAUSES]->()
WHERE r.algorithms IS NOT NULL
UNWIND r.algorithms AS algo
RETURN algo, count(*) AS edge_count
ORDER BY edge_count DESC
"""


# ────────────────────────────────────────────────────────────────
# Statistics collector
# ────────────────────────────────────────────────────────────────

class FinalStatistics:
    """Collects and reports graph statistics."""

    def __init__(self, connector, config: Dict[str, Any]):
        self.connector = connector
        self.config = config
        self.thesis_dir = Path('thesis_output')
        self.thesis_dir.mkdir(parents=True, exist_ok=True)

    def execute(self) -> Dict[str, Any]:
        """Main entry-point."""
        logger.info("=" * 60)
        logger.info("STEP 27 — Final Statistics")
        logger.info("=" * 60)

        results = {
            'step': 27,
            'status': 'started',
            'timestamp': datetime.now().isoformat(),
        }

        try:
            stats = {}

            # 1. Node counts
            stats['node_counts'] = self._query_safe(Q_NODE_COUNTS, 'node counts')
            total_nodes = sum(r.get('cnt', 0) for r in (stats['node_counts'] or []))
            logger.info(f"  Total node labels: {len(stats['node_counts'] or [])}, "
                        f"total count: {total_nodes}")

            # 2. Relationship counts
            stats['rel_counts'] = self._query_safe(Q_REL_COUNTS, 'rel counts')
            total_rels = sum(r.get('cnt', 0) for r in (stats['rel_counts'] or []))
            logger.info(f"  Total rel types: {len(stats['rel_counts'] or [])}, "
                        f"total count: {total_rels}")

            # 3. Ontology coverage
            cov = self._query_safe(Q_ONTOLOGY_COVERAGE, 'ontology coverage')
            stats['ontology_coverage'] = cov[0] if cov else {}
            logger.info(f"  Ontology coverage: {stats['ontology_coverage']}")

            # 4. ICD-10 depth
            icd = self._query_safe(Q_ICD10_DEPTH, 'ICD-10 depth')
            stats['icd10_hierarchy'] = icd[0] if icd else {}
            logger.info(f"  ICD-10 hierarchy: {stats['icd10_hierarchy']}")

            # 5. Causal edge summary
            causal = self._query_safe(Q_CAUSAL_SUMMARY, 'causal summary')
            stats['causal_summary'] = causal[0] if causal else {}
            logger.info(f"  Causal edges: {stats['causal_summary']}")

            # 6. Algorithm breakdown
            algo = self._query_safe(Q_CAUSAL_ALGO_BREAKDOWN, 'algo breakdown')
            stats['causal_algo_breakdown'] = algo or []

            # 7. Graph metrics
            density = self._query_safe(Q_GRAPH_DENSITY, 'graph density')
            stats['graph_metrics'] = density[0] if density else {}
            logger.info(f"  Graph metrics: {stats['graph_metrics']}")

            # 8. Isolated nodes
            isolated = self._query_safe(Q_CONNECTED_COMPONENTS, 'isolated')
            stats['isolated_nodes'] = (isolated[0]['isolated_nodes']
                                       if isolated else 0)

            # 9. AlzKB stats
            alzkb = self._query_safe(Q_ALZKB_STATS, 'AlzKB stats')
            stats['alzkb'] = alzkb[0] if alzkb else {}

            # Save JSON
            json_path = self.thesis_dir / 'final_stats.json'
            with open(json_path, 'w') as f:
                json.dump(stats, f, indent=2, default=str)
            logger.info(f"  Saved: {json_path}")

            # Generate markdown report
            self._generate_report(stats)

            results.update({
                'status': 'completed',
                'total_nodes': total_nodes,
                'total_rels': total_rels,
                'json_path': str(json_path),
            })

            logger.info(f"✅ Step 27 complete — {total_nodes} nodes, "
                        f"{total_rels} relationships")

        except Exception as e:
            logger.error(f"Step 27 failed: {e}", exc_info=True)
            results['status'] = 'failed'
            results['error'] = str(e)

        return results

    def _query_safe(self, query: str, label: str):
        """Run a query with error handling."""
        try:
            return self.connector.run_query(query)
        except Exception as e:
            logger.warning(f"  Query '{label}' failed: {e}")
            return None

    def _generate_report(self, stats: Dict) -> None:
        """Generate final_stats.md."""
        lines = [
            "# ADNI Knowledge Graph — Final Statistics",
            "",
            f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "---",
            "",
            "## 1. Node Counts",
            "",
            "| Label | Count |",
            "|---|---|",
        ]

        for r in (stats.get('node_counts') or []):
            lines.append(f"| {r.get('label', '?')} | {r.get('cnt', 0):,} |")

        lines += ["", "## 2. Relationship Counts", "", "| Type | Count |", "|---|---|"]
        for r in (stats.get('rel_counts') or []):
            lines.append(f"| {r.get('type', '?')} | {r.get('cnt', 0):,} |")

        # Ontology coverage
        cov = stats.get('ontology_coverage', {})
        lines += [
            "", "## 3. Ontology Coverage", "",
            f"- Total data nodes: **{cov.get('total_data_nodes', 0):,}**",
            f"- Mapped to OntologyConcept: **{cov.get('mapped_nodes', 0):,}**",
            f"- Coverage: **{cov.get('coverage_pct', 0):.1f}%**",
        ]

        # ICD-10
        icd = stats.get('icd10_hierarchy', {})
        lines += [
            "", "## 4. ICD-10 Hierarchy", "",
            f"- Max depth: **{icd.get('max_depth', 0)}**",
            f"- Avg depth: **{icd.get('avg_depth', 0):.1f}**" if icd.get('avg_depth') else "- Avg depth: **N/A**",
            f"- Leaf codes: **{icd.get('leaf_count', 0):,}**",
        ]

        # Causal summary
        cs = stats.get('causal_summary', {})
        lines += [
            "", "## 5. Causal Edge Summary", "",
            f"- Total CAUSES edges: **{cs.get('total', 0)}**",
            f"- Validated by literature: **{cs.get('validated', 0)}**",
            f"- Validation rate: **{cs.get('validation_rate', 0):.1f}%**",
        ]

        # Algo breakdown
        algos = stats.get('causal_algo_breakdown', [])
        if algos:
            lines += ["", "### By Algorithm", "", "| Algorithm | Edges |", "|---|---|"]
            for a in algos:
                lines.append(f"| {a.get('algo', '?')} | {a.get('edge_count', 0)} |")

        # Graph metrics
        gm = stats.get('graph_metrics', {})
        lines += [
            "", "## 6. Graph Metrics", "",
            f"- Total nodes: **{gm.get('nodes', 0):,}**",
            f"- Total relationships: **{gm.get('rels', 0):,}**",
            f"- Density: **{gm.get('density', 0):.6f}**",
            f"- Average degree: **{gm.get('avg_degree', 0):.2f}**",
            f"- Isolated nodes: **{stats.get('isolated_nodes', 0):,}**",
        ]

        # AlzKB
        ak = stats.get('alzkb', {})
        if ak:
            lines += [
                "", "## 7. AlzKB Integration", "",
                f"- AlzKBConcept nodes: **{ak.get('concepts', 0)}**",
                f"- SAME_AS edges: **{ak.get('same_as', 0)}**",
                f"- Internal AlzKB rels: **{ak.get('internal_rels', 0)}**",
            ]

        lines.append("")

        path = self.thesis_dir / 'final_stats.md'
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        logger.info(f"  Saved: {path}")


# ────────────────────────────────────────────────────────────────
# CLI + pipeline
# ────────────────────────────────────────────────────────────────

def execute_final_stats(config: Dict[str, Any],
                        connector=None) -> Dict[str, Any]:
    """Pipeline entry-point for Step 27."""
    if connector is None:
        from utils.neo4j_connector import Neo4jConnector
        connector = Neo4jConnector(
            config['neo4j']['uri'],
            config['neo4j']['user'],
            config['neo4j']['password']
        )

    collector = FinalStatistics(connector, config)
    return collector.execute()


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

    result = execute_final_stats(config)
    print(json.dumps(result, indent=2, default=str))
