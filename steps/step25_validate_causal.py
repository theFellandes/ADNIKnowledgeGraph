"""
Step 25 – Validate Causal Edges
================================
Compares CAUSES edges discovered in Step 22 against a curated ground
truth from the amyloid cascade hypothesis and published AD literature.

Computes precision, recall, F1, and SHD (Structural Hamming Distance).
Optionally cross-references with AlzKB relationships (if Step 24 ran).
Marks validated edges in Neo4j: SET r.validated_by_literature = true.

Output
------
- thesis_output/validation_report.md
- thesis_output/validation_metrics.json
- Updated CAUSES edges with validation flags
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# GROUND TRUTH — known AD causal relationships
# ────────────────────────────────────────────────────────────────
# From the amyloid cascade hypothesis, published meta-analyses, and
# the ATN framework. Expanded from the report's expected causal chain:
# Amyloid → Tau → Neurodegeneration → Cognitive decline.

GROUND_TRUTH_EDGES = [
    # Amyloid cascade
    {'source': 'BIO_ABETA',     'target': 'BIO_TAU',           'evidence': 'Amyloid cascade hypothesis (Hardy & Higgins 1992)'},
    {'source': 'BIO_ABETA',     'target': 'BIO_PTAU',          'evidence': 'Aβ triggers tau phosphorylation'},
    {'source': 'BIO_TAU',       'target': 'VOL_Hippocampus',   'evidence': 'Tau-mediated neurodegeneration (Braak staging)'},
    {'source': 'BIO_PTAU',      'target': 'VOL_Hippocampus',   'evidence': 'pTau drives hippocampal atrophy'},

    # Structural → Cognitive
    {'source': 'VOL_Hippocampus','target': 'COG_MMSE',         'evidence': 'Structural-cognitive correlation (Jack et al. 2010)'},
    {'source': 'VOL_Hippocampus','target': 'COG_ADAS-COG-13',  'evidence': 'Hippocampal vol predicts ADAS-Cog'},
    {'source': 'VOL_Entorhinal', 'target': 'COG_MMSE',         'evidence': 'Entorhinal cortex atrophy in early AD'},

    # Genetics
    {'source': 'apoe_e4_count',  'target': 'BIO_ABETA',        'evidence': 'APOE4 accelerates Aβ deposition (Castellano 2011)'},
    {'source': 'apoe_e4_count',  'target': 'DX_bl',            'evidence': 'APOE4 strongest genetic risk for AD'},

    # Age effects
    {'source': 'age',            'target': 'BIO_TAU',           'evidence': 'Age-related tau accumulation'},
    {'source': 'age',            'target': 'VOL_Hippocampus',   'evidence': 'Age-related hippocampal atrophy'},
    {'source': 'age',            'target': 'COG_MMSE',          'evidence': 'Age-related cognitive decline'},

    # Cognitive reserve
    {'source': 'education',      'target': 'COG_MMSE',          'evidence': 'Cognitive reserve hypothesis (Stern 2012)'},

    # PET ↔ CSF correspondence
    {'source': 'PET_AV45',       'target': 'BIO_ABETA',         'evidence': 'Amyloid PET reflects CSF Aβ42 (inverse)'},

    # Diagnosis tracks
    {'source': 'DX_bl',          'target': 'COG_MMSE',          'evidence': 'Diagnosis defined partly by cognitive scores'},

    # ATN framework
    {'source': 'ATN_A',          'target': 'BIO_ABETA',         'evidence': 'ATN amyloid status corresponds to CSF Aβ'},
    {'source': 'ATN_T',          'target': 'BIO_TAU',           'evidence': 'ATN tau status corresponds to CSF tau'},
    {'source': 'ATN_N',          'target': 'VOL_Hippocampus',   'evidence': 'ATN neurodegeneration status'},
]


# ────────────────────────────────────────────────────────────────
# Validator class
# ────────────────────────────────────────────────────────────────

class CausalValidator:
    """Validates discovered CAUSES edges against ground truth."""

    def __init__(self, connector, config: Dict[str, Any]):
        self.connector = connector
        self.config = config.get('causal', {})
        self.output_dir = Path(config.get('output_dir', 'causal'))
        self.thesis_dir = Path('thesis_output')
        self.thesis_dir.mkdir(parents=True, exist_ok=True)

    def execute(self) -> Dict[str, Any]:
        """Main entry-point."""
        logger.info("=" * 60)
        logger.info("STEP 25 — Validate Causal Edges")
        logger.info("=" * 60)

        results = {
            'step': 25,
            'status': 'started',
            'timestamp': datetime.now().isoformat(),
        }

        try:
            # 1. Load discovered edges
            consensus_path = self.output_dir / 'consensus_edges.json'
            if consensus_path.exists():
                with open(consensus_path) as f:
                    discovered = json.load(f)
                logger.info(f"  Loaded {len(discovered)} discovered edges from file")
            else:
                # Try loading from Neo4j
                discovered = self._load_causes_from_neo4j()
                logger.info(f"  Loaded {len(discovered)} discovered edges from Neo4j")

            # 2. Build edge sets
            discovered_set = self._edges_to_set(discovered)
            gt_set = self._gt_to_set()

            # 3. Compute metrics
            metrics = self._compute_metrics(discovered_set, gt_set)

            # 4. Compute SHD
            metrics['shd'] = self._compute_shd(discovered_set, gt_set)

            # 5. Mark validated edges in Neo4j
            validated_count = self._mark_validated_edges(discovered, gt_set)
            metrics['validated_in_neo4j'] = validated_count

            # 6. Cross-reference with AlzKB (if available)
            alzkb_matches = self._cross_reference_alzkb(discovered)
            metrics['alzkb_cross_refs'] = alzkb_matches

            # 7. Generate reports
            self._save_metrics(metrics)
            self._generate_report(metrics, discovered, gt_set)

            results.update({
                'status': 'completed',
                'precision': metrics['precision'],
                'recall': metrics['recall'],
                'f1': metrics['f1'],
                'shd': metrics['shd'],
                'validated_edges': validated_count,
            })

            logger.info(f"✅ Step 25 complete — P={metrics['precision']:.2f}, "
                        f"R={metrics['recall']:.2f}, F1={metrics['f1']:.2f}, "
                        f"SHD={metrics['shd']}")

        except Exception as e:
            logger.error(f"Step 25 failed: {e}", exc_info=True)
            results['status'] = 'failed'
            results['error'] = str(e)

        return results

    # ── Edge set operations ──────────────────────────────────

    def _edges_to_set(self, edges: List[Dict]) -> Set[Tuple[str, str]]:
        """Convert edge list to set of (source, target) tuples."""
        edge_set = set()
        for e in edges:
            src = e.get('source', '')
            tgt = e.get('target', '')
            edge_set.add((src, tgt))
            # Also add undirected match (for '---' edges)
            if e.get('edge_type') == '---':
                edge_set.add((tgt, src))
        return edge_set

    def _gt_to_set(self) -> Set[Tuple[str, str]]:
        """Ground truth as set of (source, target) tuples."""
        return {(e['source'], e['target']) for e in GROUND_TRUTH_EDGES}

    # ── Metrics ──────────────────────────────────────────────

    def _compute_metrics(self, discovered: Set, ground_truth: Set) -> Dict:
        """Compute precision, recall, F1."""
        tp = discovered & ground_truth
        fp = discovered - ground_truth
        fn = ground_truth - discovered

        precision = len(tp) / len(discovered) if discovered else 0.0
        recall = len(tp) / len(ground_truth) if ground_truth else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) > 0 else 0.0)

        return {
            'true_positives': len(tp),
            'false_positives': len(fp),
            'false_negatives': len(fn),
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1': round(f1, 4),
            'tp_edges': sorted([f"{s} → {t}" for s, t in tp]),
            'fp_edges': sorted([f"{s} → {t}" for s, t in fp]),
            'fn_edges': sorted([f"{s} → {t}" for s, t in fn]),
            'total_discovered': len(discovered),
            'total_ground_truth': len(ground_truth),
        }

    def _compute_shd(self, discovered: Set, ground_truth: Set) -> int:
        """Structural Hamming Distance — edit distance between two graphs."""
        # SHD = |missing_edges| + |extra_edges| + |reversed_edges|
        all_vars = set()
        for s, t in discovered | ground_truth:
            all_vars.add(s)
            all_vars.add(t)

        shd = 0
        for s, t in ground_truth:
            if (s, t) not in discovered:
                if (t, s) in discovered:
                    shd += 1  # reversed
                else:
                    shd += 1  # missing
        for s, t in discovered:
            if (s, t) not in ground_truth and (t, s) not in ground_truth:
                shd += 1  # extra

        return shd

    # ── Neo4j operations ─────────────────────────────────────

    def _load_causes_from_neo4j(self) -> List[Dict]:
        """Load CAUSES edges from Neo4j."""
        result = self.connector.run_query("""
            MATCH (src)-[r:CAUSES]->(tgt)
            RETURN src.variable_id AS source, tgt.variable_id AS target,
                   r.algorithms AS algorithms, r.confidence AS confidence,
                   r.edge_type AS edge_type
        """)
        return result if result else []

    def _mark_validated_edges(self, discovered: List[Dict],
                               gt_set: Set[Tuple[str, str]]) -> int:
        """Mark validated CAUSES edges in Neo4j."""
        count = 0
        for edge in discovered:
            src, tgt = edge.get('source', ''), edge.get('target', '')
            is_valid = (src, tgt) in gt_set or (tgt, src) in gt_set

            try:
                self.connector.run_query("""
                    MATCH (s:CausalVariable {variable_id: $src})
                          -[r:CAUSES]->
                          (t:CausalVariable {variable_id: $tgt})
                    SET r.validated_by_literature = $valid
                """, {'src': src, 'tgt': tgt, 'valid': is_valid})
                if is_valid:
                    count += 1
            except Exception:
                pass

        logger.info(f"  Marked {count} edges as validated_by_literature")
        return count

    def _cross_reference_alzkb(self, discovered: List[Dict]) -> int:
        """Cross-reference CAUSES edges with AlzKB relationships."""
        try:
            result = self.connector.run_query("""
                MATCH (s:CausalVariable)-[:CAUSES]->(t:CausalVariable)
                WHERE EXISTS {
                    (s)-[:SAME_AS|MAPS_TO*1..2]-(:AlzKBConcept)
                    -[:ALZKB_RELATES_TO]-
                    (:AlzKBConcept)-[:SAME_AS|MAPS_TO*1..2]-(t)
                }
                RETURN count(*) AS cnt
            """)
            cnt = result[0]['cnt'] if result else 0
            logger.info(f"  AlzKB cross-references found: {cnt}")
            return cnt
        except Exception as e:
            logger.debug(f"  AlzKB cross-reference skipped: {e}")
            return 0

    # ── Reporting ────────────────────────────────────────────

    def _save_metrics(self, metrics: Dict) -> None:
        """Save metrics JSON."""
        path = self.thesis_dir / 'validation_metrics.json'
        with open(path, 'w') as f:
            json.dump(metrics, f, indent=2)
        logger.info(f"  Saved metrics: {path}")

    def _generate_report(self, metrics: Dict, discovered: List,
                          gt_set: Set) -> None:
        """Generate validation_report.md."""
        report_lines = [
            "# Causal Edge Validation Report",
            "",
            f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "---",
            "",
            "## Summary Metrics",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Discovered edges | {metrics['total_discovered']} |",
            f"| Ground truth edges | {metrics['total_ground_truth']} |",
            f"| True positives | {metrics['true_positives']} |",
            f"| False positives | {metrics['false_positives']} |",
            f"| False negatives | {metrics['false_negatives']} |",
            f"| **Precision** | **{metrics['precision']:.4f}** |",
            f"| **Recall** | **{metrics['recall']:.4f}** |",
            f"| **F1 Score** | **{metrics['f1']:.4f}** |",
            f"| **SHD** | **{metrics['shd']}** |",
            f"| Validated in Neo4j | {metrics.get('validated_in_neo4j', 0)} |",
            f"| AlzKB cross-refs | {metrics.get('alzkb_cross_refs', 0)} |",
            "",
            "---",
            "",
            "## True Positives (correctly discovered)",
            "",
        ]

        if metrics['tp_edges']:
            for e in metrics['tp_edges']:
                report_lines.append(f"- ✅ {e}")
        else:
            report_lines.append("- *(none)*")

        report_lines += [
            "",
            "## False Positives (discovered but not in ground truth)",
            "",
        ]
        if metrics['fp_edges']:
            for e in metrics['fp_edges']:
                report_lines.append(f"- ❌ {e}")
        else:
            report_lines.append("- *(none)*")

        report_lines += [
            "",
            "## False Negatives (missed ground truth edges)",
            "",
        ]
        if metrics['fn_edges']:
            for e in metrics['fn_edges']:
                report_lines.append(f"- ⚠️ {e}")
        else:
            report_lines.append("- *(none)*")

        report_lines += [
            "",
            "---",
            "",
            "## Ground Truth Reference",
            "",
            "| Source | Target | Evidence |",
            "|---|---|---|",
        ]
        for gt in GROUND_TRUTH_EDGES:
            report_lines.append(f"| {gt['source']} | {gt['target']} | {gt['evidence']} |")

        report_lines.append("")

        path = self.thesis_dir / 'validation_report.md'
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))
        logger.info(f"  Saved report: {path}")


# ────────────────────────────────────────────────────────────────
# CLI + pipeline integration
# ────────────────────────────────────────────────────────────────

def execute_validate_causal(config: Dict[str, Any],
                            connector=None) -> Dict[str, Any]:
    """Pipeline entry-point for Step 25."""
    if connector is None:
        from utils.neo4j_connector import Neo4jConnector
        connector = Neo4jConnector(
            config['neo4j']['uri'],
            config['neo4j']['user'],
            config['neo4j']['password']
        )

    validator = CausalValidator(connector, config)
    return validator.execute()


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

    result = execute_validate_causal(config)
    print(json.dumps(result, indent=2, default=str))
