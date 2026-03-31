"""
Step 26 – DoWhy Causal Inference
=================================
Uses the DoWhy library to estimate causal effects for key
treatment–outcome pairs identified by the causal discovery step.

For each pair:
1. Builds a CausalModel from the FCI/consensus DAG + feature data
2. Identifies the estimand via backdoor criterion
3. Estimates causal effect (linear regression)
4. Runs 3 refutation tests: placebo, data subset, random common cause

Output
------
- causal/dowhy_results.json  (per-pair effect, CI, refutation p-values)
"""

import logging
import json
import warnings
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Suppress DoWhy / EconML verbosity
warnings.filterwarnings('ignore', category=FutureWarning)

# ────────────────────────────────────────────────────────────────
# TREATMENT–OUTCOME PAIRS
# ────────────────────────────────────────────────────────────────
# These are the key causal hypotheses from AD literature that we
# attempt to estimate using the observational data.

DEFAULT_TREATMENT_OUTCOME_PAIRS = [
    {
        'treatment': 'BIO_ABETA',
        'outcome':   'BIO_TAU',
        'hypothesis': 'Amyloid accelerates tau accumulation',
    },
    {
        'treatment': 'BIO_TAU',
        'outcome':   'VOL_Hippocampus',
        'hypothesis': 'Tau drives hippocampal atrophy',
    },
    {
        'treatment': 'apoe_e4_count',
        'outcome':   'BIO_ABETA',
        'hypothesis': 'APOE4 increases amyloid burden',
    },
    {
        'treatment': 'age',
        'outcome':   'VOL_Hippocampus',
        'hypothesis': 'Age drives hippocampal atrophy',
    },
    {
        'treatment': 'education',
        'outcome':   'COG_MMSE',
        'hypothesis': 'Education provides cognitive reserve',
    },
]


# ────────────────────────────────────────────────────────────────
# DAG builder
# ────────────────────────────────────────────────────────────────

def _build_gml_from_edges(edges: List[Dict], columns: List[str]) -> str:
    """Convert consensus edges to GML format for DoWhy."""
    lines = ['graph[directed 1']

    # Add all feature columns as nodes
    for col in columns:
        safe = col.replace('"', '\\"')
        lines.append(f'  node[id "{safe}" label "{safe}"]')

    # Add directed edges
    for e in edges:
        src = e.get('source', '')
        tgt = e.get('target', '')
        if src in columns and tgt in columns:
            safe_src = src.replace('"', '\\"')
            safe_tgt = tgt.replace('"', '\\"')
            lines.append(f'  edge[source "{safe_src}" target "{safe_tgt}"]')

    lines.append(']')
    return '\n'.join(lines)


# ────────────────────────────────────────────────────────────────
# Inference class
# ────────────────────────────────────────────────────────────────

class DoWhyInference:
    """Estimates causal effects using DoWhy."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('causal', {})
        self.output_dir = Path(config.get('output_dir', 'causal'))

    def execute(self) -> Dict[str, Any]:
        """Main entry-point."""
        logger.info("=" * 60)
        logger.info("STEP 26 — DoWhy Causal Inference")
        logger.info("=" * 60)

        results = {
            'step': 26,
            'status': 'started',
            'timestamp': datetime.now().isoformat(),
        }

        try:
            # Check DoWhy availability
            try:
                import dowhy
                from dowhy import CausalModel
                logger.info(f"  DoWhy version: {dowhy.__version__}")
            except ImportError:
                raise ImportError(
                    "DoWhy not installed. Run: pip install dowhy"
                )

            # 1. Load feature data
            features_path = self.output_dir / 'causal_features.csv'
            if not features_path.exists():
                raise FileNotFoundError(
                    f"Feature matrix not found at {features_path}. "
                    "Run Step 21 first."
                )
            data = pd.read_csv(features_path)
            logger.info(f"  Loaded feature matrix: {data.shape}")

            # 2. Load consensus edges
            consensus_path = self.output_dir / 'consensus_edges.json'
            if consensus_path.exists():
                with open(consensus_path) as f:
                    edges = json.load(f)
                logger.info(f"  Loaded {len(edges)} consensus edges")
            else:
                edges = []
                logger.warning("  No consensus edges found — using empty DAG")

            # 3. Build GML graph
            columns = list(data.columns)
            gml_str = _build_gml_from_edges(edges, columns)

            # 4. Run inference for each treatment–outcome pair
            pair_results = []
            pairs = self.config.get('dowhy_pairs',
                                    DEFAULT_TREATMENT_OUTCOME_PAIRS)

            for pair in pairs:
                treatment = pair['treatment']
                outcome = pair['outcome']
                hypothesis = pair.get('hypothesis', '')

                if treatment not in columns or outcome not in columns:
                    logger.warning(f"  Skipping {treatment} → {outcome}: "
                                   "variable(s) not in data")
                    pair_results.append({
                        'treatment': treatment,
                        'outcome': outcome,
                        'hypothesis': hypothesis,
                        'status': 'skipped',
                        'reason': 'variable not in feature matrix',
                    })
                    continue

                result = self._run_pair(
                    data, gml_str, treatment, outcome, hypothesis
                )
                pair_results.append(result)

            # 5. Save results
            output = {
                'timestamp': datetime.now().isoformat(),
                'n_pairs': len(pair_results),
                'n_completed': sum(1 for r in pair_results
                                   if r.get('status') == 'completed'),
                'pairs': pair_results,
            }

            output_path = self.output_dir / 'dowhy_results.json'
            with open(output_path, 'w') as f:
                json.dump(output, f, indent=2, default=str)
            logger.info(f"  Saved results: {output_path}")

            results.update({
                'status': 'completed',
                'pairs_analysed': output['n_completed'],
                'results_path': str(output_path),
            })

            logger.info(f"✅ Step 26 complete — {output['n_completed']}/"
                        f"{len(pair_results)} pairs analysed")

        except ImportError as e:
            logger.error(str(e))
            results['status'] = 'skipped'
            results['error'] = str(e)
        except Exception as e:
            logger.error(f"Step 26 failed: {e}", exc_info=True)
            results['status'] = 'failed'
            results['error'] = str(e)

        return results

    def _run_pair(self, data: pd.DataFrame, gml_str: str,
                  treatment: str, outcome: str,
                  hypothesis: str) -> Dict[str, Any]:
        """Run DoWhy for a single treatment–outcome pair."""
        from dowhy import CausalModel

        logger.info(f"  Analysing: {treatment} → {outcome}")
        result = {
            'treatment': treatment,
            'outcome': outcome,
            'hypothesis': hypothesis,
            'status': 'started',
        }

        try:
            # Build causal model
            model = CausalModel(
                data=data,
                treatment=treatment,
                outcome=outcome,
                graph=gml_str,
            )

            # Identify estimand
            estimand = model.identify_effect(
                proceed_when_unidentifiable=True
            )
            result['estimand'] = str(estimand)

            if estimand is None:
                result['status'] = 'unidentifiable'
                return result

            # Estimate effect
            estimate = model.estimate_effect(
                estimand,
                method_name="backdoor.linear_regression",
            )
            result['effect_value'] = float(estimate.value)
            result['estimate_str'] = str(estimate)
            logger.info(f"    Effect: {estimate.value:.4f}")

            # Refutation tests
            refutations = {}

            # 1. Placebo treatment
            try:
                ref_placebo = model.refute_estimate(
                    estimand, estimate,
                    method_name="placebo_treatment_refuter",
                    placebo_type="permute",
                    num_simulations=50,
                )
                refutations['placebo'] = {
                    'new_effect': float(ref_placebo.new_effect),
                    'p_value': float(ref_placebo.refutation_result.get(
                        'p_value', -1)) if hasattr(ref_placebo, 'refutation_result')
                        and isinstance(ref_placebo.refutation_result, dict)
                        else None,
                    'passed': abs(float(ref_placebo.new_effect)) < abs(
                        float(estimate.value)) * 0.5,
                }
                logger.info(f"    Placebo: new_effect={ref_placebo.new_effect:.4f}")
            except Exception as e:
                refutations['placebo'] = {'error': str(e)}

            # 2. Data subset
            try:
                ref_subset = model.refute_estimate(
                    estimand, estimate,
                    method_name="data_subset_refuter",
                    subset_fraction=0.8,
                    num_simulations=50,
                )
                refutations['data_subset'] = {
                    'new_effect': float(ref_subset.new_effect),
                    'passed': abs(float(ref_subset.new_effect) -
                                  float(estimate.value)) < abs(
                                      float(estimate.value)) * 0.5,
                }
                logger.info(f"    Subset: new_effect={ref_subset.new_effect:.4f}")
            except Exception as e:
                refutations['data_subset'] = {'error': str(e)}

            # 3. Random common cause
            try:
                ref_random = model.refute_estimate(
                    estimand, estimate,
                    method_name="random_common_cause",
                    num_simulations=50,
                )
                refutations['random_common_cause'] = {
                    'new_effect': float(ref_random.new_effect),
                    'passed': abs(float(ref_random.new_effect) -
                                  float(estimate.value)) < abs(
                                      float(estimate.value)) * 0.3,
                }
                logger.info(f"    Random CC: new_effect={ref_random.new_effect:.4f}")
            except Exception as e:
                refutations['random_common_cause'] = {'error': str(e)}

            result['refutations'] = refutations
            result['status'] = 'completed'

        except Exception as e:
            logger.warning(f"    Failed: {e}")
            result['status'] = 'failed'
            result['error'] = str(e)

        return result


# ────────────────────────────────────────────────────────────────
# CLI + pipeline integration
# ────────────────────────────────────────────────────────────────

def execute_dowhy_inference(config: Dict[str, Any]) -> Dict[str, Any]:
    """Pipeline entry-point for Step 26."""
    inferrer = DoWhyInference(config)
    return inferrer.execute()


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

    result = execute_dowhy_inference(config)
    print(json.dumps(result, indent=2, default=str))
