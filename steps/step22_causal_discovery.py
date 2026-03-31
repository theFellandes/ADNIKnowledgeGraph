"""
Step 22 – Causal Discovery Algorithms
======================================
Runs constraint-based (PC, FCI) and score-based (GES) causal discovery
algorithms on the feature matrix produced by Step 21.

Output
------
- causal/PC_adjacency.json
- causal/PC_graph.png
- causal/FCI_adjacency.json
- causal/FCI_graph.png
- causal/GES_adjacency.json
- causal/GES_graph.png
- causal/consensus_edges.json   (edges found by ≥ threshold algorithms)

Dependencies
------------
    pip install causal-learn
"""

import logging
import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
from collections import defaultdict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# Causal Discovery Runner
# ────────────────────────────────────────────────────────────────

class CausalDiscoveryRunner:
    """
    Runs PC, FCI, and GES algorithms on the causal feature matrix
    and produces consensus edges.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('causal', {})
        self.output_dir = Path(config.get('output_dir', 'causal'))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Algorithm parameters
        self.alpha = self.config.get('alpha', 0.05)
        self.ci_test = self.config.get('ci_test', 'fisherz')
        self.algorithms = self.config.get('algorithms', ['PC', 'FCI', 'GES'])
        self.consensus_threshold = self.config.get('consensus_threshold', 2)
        self.min_samples = self.config.get('min_samples', 50)

    def execute(self) -> Dict[str, Any]:
        """Main entry point."""
        logger.info("=" * 60)
        logger.info("STEP 22 — Causal Discovery Algorithms")
        logger.info("=" * 60)

        results = {
            'step': 22,
            'status': 'started',
            'timestamp': datetime.now().isoformat(),
            'algorithm_results': {},
        }

        try:
            # 1. Load feature matrix
            csv_path = self.output_dir / 'causal_features.csv'
            if not csv_path.exists():
                raise FileNotFoundError(
                    f"Feature matrix not found at {csv_path}. "
                    "Run Step 21 first."
                )

            df = pd.read_csv(csv_path)
            logger.info(f"  Loaded feature matrix: {df.shape}")

            # Drop ptid — not a feature
            feature_cols = [c for c in df.columns if c != 'ptid']
            data = df[feature_cols].values.astype(float)
            labels = feature_cols

            if len(df) < self.min_samples:
                logger.warning(
                    f"Only {len(df)} samples (min: {self.min_samples}). "
                    "Results may be unreliable."
                )

            # 2. Import causal-learn
            try:
                from causallearn.search.ConstraintBased.PC import pc
                from causallearn.search.ConstraintBased.FCI import fci
                from causallearn.search.ScoreBased.GES import ges
                logger.info("  causal-learn imported successfully")
            except ImportError as e:
                raise ImportError(
                    "causal-learn not installed. Run: pip install causal-learn"
                ) from e

            # 3. Run each algorithm
            all_edges = {}

            if 'PC' in self.algorithms:
                logger.info("  Running PC algorithm...")
                pc_edges = self._run_pc(data, labels)
                all_edges['PC'] = pc_edges
                results['algorithm_results']['PC'] = {
                    'edges': len(pc_edges),
                    'status': 'completed'
                }

            if 'FCI' in self.algorithms:
                logger.info("  Running FCI algorithm...")
                fci_edges = self._run_fci(data, labels)
                all_edges['FCI'] = fci_edges
                results['algorithm_results']['FCI'] = {
                    'edges': len(fci_edges),
                    'status': 'completed'
                }

            if 'GES' in self.algorithms:
                logger.info("  Running GES algorithm...")
                ges_edges = self._run_ges(data, labels)
                all_edges['GES'] = ges_edges
                results['algorithm_results']['GES'] = {
                    'edges': len(ges_edges),
                    'status': 'completed'
                }

            # 4. Save per-algorithm results
            for algo, edges in all_edges.items():
                self._save_algorithm_result(algo, edges, labels)

            # 5. Consensus
            logger.info(f"  Computing consensus (threshold = {self.consensus_threshold})...")
            consensus = self._compute_consensus(all_edges)
            consensus_path = self.output_dir / 'consensus_edges.json'
            with open(consensus_path, 'w') as f:
                json.dump(consensus, f, indent=2)
            logger.info(f"  Consensus edges: {len(consensus)}")
            logger.info(f"  Saved: {consensus_path}")

            # 6. Visualize consensus
            self._plot_consensus_graph(consensus, labels)

            results.update({
                'status': 'completed',
                'total_consensus_edges': len(consensus),
                'consensus_path': str(consensus_path),
            })
            logger.info(f"✅ Step 22 complete — {len(consensus)} consensus edges")

        except Exception as e:
            logger.error(f"Step 22 failed: {e}", exc_info=True)
            results['status'] = 'failed'
            results['error'] = str(e)

        return results

    # ── Algorithm implementations ────────────────────────────

    def _run_pc(self, data: np.ndarray, labels: List[str]) -> List[Dict]:
        """Run PC algorithm and extract edges."""
        from causallearn.search.ConstraintBased.PC import pc

        cg = pc(data, alpha=self.alpha, indep_test=self.ci_test,
                node_names=labels, show_progress=False)

        return self._extract_edges_from_graph(cg.G, labels, 'PC')

    def _run_fci(self, data: np.ndarray, labels: List[str]) -> List[Dict]:
        """Run FCI algorithm (handles latent confounders)."""
        from causallearn.search.ConstraintBased.FCI import fci

        G, edges = fci(data, alpha=self.alpha, independence_test_method=self.ci_test,
                       node_names=labels, show_progress=False)

        return self._extract_edges_from_graph(G, labels, 'FCI')

    def _run_ges(self, data: np.ndarray, labels: List[str]) -> List[Dict]:
        """Run GES (Greedy Equivalence Search) algorithm."""
        from causallearn.search.ScoreBased.GES import ges

        record = ges(data, score_func='local_score_BIC',
                     node_names=labels)

        return self._extract_edges_from_graph(record['G'], labels, 'GES')

    def _extract_edges_from_graph(self, G, labels: List[str],
                                   algo: str) -> List[Dict]:
        """Extract edge list from a causal-learn GeneralGraph object."""
        edges = []
        n = len(labels)
        graph_matrix = G.graph  # adjacency matrix

        for i in range(n):
            for j in range(i + 1, n):
                # causal-learn uses:
                #  graph[i,j] = -1, graph[j,i] = 1  → i --> j (directed)
                #  graph[i,j] = -1, graph[j,i] = -1 → i --- j (undirected)
                #  graph[i,j] = 1, graph[j,i] = -1  → j --> i
                #  graph[i,j] = 2, graph[j,i] = -1  → i o-> j (FCI: possible)
                #  graph[i,j] = 0, graph[j,i] = 0   → no edge

                val_ij = graph_matrix[i, j]
                val_ji = graph_matrix[j, i]

                if val_ij == 0 and val_ji == 0:
                    continue  # No edge

                source = labels[i]
                target = labels[j]

                # Determine edge type
                if val_ij == -1 and val_ji == 1:
                    # i --> j
                    edge_type = '-->'
                    direction = 'directed'
                elif val_ij == 1 and val_ji == -1:
                    # j --> i (swap)
                    source, target = labels[j], labels[i]
                    edge_type = '-->'
                    direction = 'directed'
                elif val_ij == -1 and val_ji == -1:
                    # i --- j (undirected)
                    edge_type = '---'
                    direction = 'undirected'
                elif val_ij == 2 or val_ji == 2:
                    # Circle endpoint (FCI)
                    edge_type = 'o->' if val_ij == 2 else '<-o'
                    direction = 'partially_directed'
                else:
                    edge_type = '???'
                    direction = 'unknown'

                edges.append({
                    'source': source,
                    'target': target,
                    'direction': direction,
                    'edge_type': edge_type,
                    'algorithm': algo,
                })

        logger.info(f"    {algo}: {len(edges)} edges found")
        return edges

    # ── Consensus ────────────────────────────────────────────

    def _compute_consensus(self, all_edges: Dict[str, List[Dict]]) -> List[Dict]:
        """
        Build consensus: include edges found by ≥ threshold algorithms.
        Treats undirected edges as compatible with directed edges between
        the same pair.
        """
        # Key: frozenset({source, target}) for undirected comparison
        edge_counts = defaultdict(lambda: {
            'algorithms': [],
            'directions': [],
            'edge_types': [],
        })

        for algo, edges in all_edges.items():
            for e in edges:
                key = frozenset([e['source'], e['target']])
                info = edge_counts[key]
                info['algorithms'].append(algo)
                info['directions'].append(e['direction'])
                info['edge_types'].append(e['edge_type'])
                # Store source-target for directed consensus
                if 'sources' not in info:
                    info['sources'] = []
                    info['targets'] = []
                info['sources'].append(e['source'])
                info['targets'].append(e['target'])

        consensus = []
        for key, info in edge_counts.items():
            if len(info['algorithms']) >= self.consensus_threshold:
                # Determine consensus direction
                directed_count = sum(1 for d in info['directions'] if d == 'directed')
                if directed_count > 0:
                    # Use majority direction
                    source_counts = defaultdict(int)
                    for s in info['sources']:
                        source_counts[s] += 1
                    consensus_source = max(source_counts, key=source_counts.get)
                    nodes = list(key)
                    consensus_target = nodes[0] if nodes[1] == consensus_source else nodes[1]
                    direction = 'directed'
                    edge_type = '-->'
                else:
                    nodes = sorted(list(key))
                    consensus_source = nodes[0]
                    consensus_target = nodes[1]
                    direction = 'undirected'
                    edge_type = '---'

                confidence = round(len(info['algorithms']) / len(all_edges), 2)

                consensus.append({
                    'source': consensus_source,
                    'target': consensus_target,
                    'direction': direction,
                    'edge_type': edge_type,
                    'algorithms': sorted(set(info['algorithms'])),
                    'confidence': confidence,
                    'n_algorithms': len(set(info['algorithms'])),
                })

        # Sort by confidence descending
        consensus.sort(key=lambda e: (-e['confidence'], e['source']))
        return consensus

    # ── Saving & Visualization ───────────────────────────────

    def _save_algorithm_result(self, algo: str, edges: List[Dict],
                                labels: List[str]) -> None:
        """Save adjacency JSON and graph PNG for one algorithm."""
        # Save edges JSON
        json_path = self.output_dir / f'{algo}_adjacency.json'
        with open(json_path, 'w') as f:
            json.dump(edges, f, indent=2)
        logger.info(f"    Saved: {json_path}")

        # Plot
        self._plot_graph(edges, labels, algo)

    def _plot_graph(self, edges: List[Dict], labels: List[str],
                    algo: str) -> None:
        """Visualize a causal graph using matplotlib/networkx."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            try:
                import networkx as nx
                self._plot_with_networkx(edges, labels, algo, plt)
            except ImportError:
                self._plot_adjacency_matrix(edges, labels, algo, plt)

        except ImportError:
            logger.warning("matplotlib not available — skipping graph plot")

    def _plot_with_networkx(self, edges: List[Dict], labels: List[str],
                            algo: str, plt) -> None:
        """Plot using networkx for proper graph layout."""
        import networkx as nx

        G = nx.DiGraph()
        G.add_nodes_from(labels)

        directed_edges = []
        undirected_edges = []

        for e in edges:
            if e['direction'] == 'directed':
                directed_edges.append((e['source'], e['target']))
            else:
                undirected_edges.append((e['source'], e['target']))

        G.add_edges_from(directed_edges)

        fig, ax = plt.subplots(figsize=(12, 10))
        pos = nx.spring_layout(G, k=2.5, iterations=50, seed=42)

        # Draw nodes
        nx.draw_networkx_nodes(G, pos, ax=ax, node_size=800,
                              node_color='#4FC3F7', alpha=0.9,
                              edgecolors='#01579B', linewidths=2)
        # Directed edges
        nx.draw_networkx_edges(G, pos, edgelist=directed_edges, ax=ax,
                              edge_color='#E53935', width=2,
                              arrows=True, arrowsize=20,
                              connectionstyle='arc3,rad=0.1')
        # Undirected edges
        if undirected_edges:
            UG = nx.Graph()
            UG.add_edges_from(undirected_edges)
            nx.draw_networkx_edges(UG, pos, ax=ax,
                                  edge_color='#78909C', width=1.5,
                                  style='dashed')

        nx.draw_networkx_labels(G, pos, ax=ax, font_size=8,
                               font_weight='bold')

        ax.set_title(f'{algo} Causal Graph ({len(edges)} edges)',
                    fontsize=14, fontweight='bold')
        ax.axis('off')
        plt.tight_layout()

        out_path = self.output_dir / f'{algo}_graph.png'
        fig.savefig(out_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        logger.info(f"    Saved: {out_path}")

    def _plot_adjacency_matrix(self, edges: List[Dict], labels: List[str],
                                algo: str, plt) -> None:
        """Fallback: plot adjacency as heatmap if networkx unavailable."""
        n = len(labels)
        label_idx = {l: i for i, l in enumerate(labels)}
        adj = np.zeros((n, n))

        for e in edges:
            i = label_idx.get(e['source'])
            j = label_idx.get(e['target'])
            if i is not None and j is not None:
                adj[i, j] = 1
                if e['direction'] != 'directed':
                    adj[j, i] = 1

        fig, ax = plt.subplots(figsize=(10, 10))
        ax.imshow(adj, cmap='Blues', aspect='auto')
        ax.set_xticks(range(n))
        ax.set_yticks(range(n))
        ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=7)
        ax.set_yticklabels(labels, fontsize=7)
        ax.set_title(f'{algo} Adjacency ({len(edges)} edges)')
        plt.tight_layout()

        out_path = self.output_dir / f'{algo}_graph.png'
        fig.savefig(out_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        logger.info(f"    Saved: {out_path}")

    def _plot_consensus_graph(self, consensus: List[Dict],
                               labels: List[str]) -> None:
        """Plot the consensus graph."""
        if not consensus:
            logger.warning("No consensus edges to plot")
            return
        self._plot_graph(consensus, labels, 'consensus')


# ────────────────────────────────────────────────────────────────
# CLI + pipeline integration
# ────────────────────────────────────────────────────────────────

def execute_causal_discovery(config: Dict[str, Any]) -> Dict[str, Any]:
    """Pipeline entry-point for Step 22."""
    runner = CausalDiscoveryRunner(config)
    return runner.execute()


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

    result = execute_causal_discovery(config)
    print(json.dumps(result, indent=2, default=str))
