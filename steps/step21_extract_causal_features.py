"""
Step 21 – Extract Causal Feature Matrix
========================================
Queries the Neo4j knowledge graph to build a patient-level baseline feature
matrix for causal discovery (Phase 2).

Output
------
- causal/causal_features.csv          (imputed, encoded, z-scored)
- causal/causal_features_raw.csv      (before imputation)
- causal/completeness_report.json     (% missing per variable)
- causal/correlation_matrix.png       (heatmap)

Feature groups
--------------
Demographics   : age, gender, education, apoe_e4_count
Cognitive      : MMSE, CDR, ADAS-Cog-13, MoCA, FAQ
CSF Biomarkers : CSF_AB42, CSF_TAU, CSF_PTAU
Volumetric     : Hippocampus, Entorhinal, Ventricles, WholeBrain, ICV
PET            : AV45_SUVR (amyloid), FDG_SUVR (metabolism)
ATN            : A_status, T_status, N_status
Diagnosis      : DX_bl (CN=0, MCI=1, AD=2)
"""

import logging
import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# CYPHER QUERIES
# ────────────────────────────────────────────────────────────────

# One row per patient at baseline visit
QUERY_DEMOGRAPHICS = """
MATCH (p:Patient)
OPTIONAL MATCH (p)-[:HAS_VISIT]->(v:Visit)
  WHERE v.viscode IN ['bl', 'sc']
RETURN DISTINCT
    p.ptid           AS ptid,
    p.age_at_baseline AS age,
    p.gender          AS gender,
    p.education_years AS education,
    p.apoe_genotype   AS apoe_genotype
"""

QUERY_COGNITIVE = """
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(cog:CognitiveAssessment)
WHERE v.viscode IN ['bl', 'sc']
RETURN
    p.ptid         AS ptid,
    cog.test_name  AS test_name,
    cog.total_score AS score
"""

QUERY_BIOMARKERS = """
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_BIOMARKER]->(bio:Biomarker)
WHERE v.viscode IN ['bl', 'sc']
RETURN
    p.ptid       AS ptid,
    bio.analyte  AS analyte,
    bio.value    AS value
"""

QUERY_VOLUMETRIC = """
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_VOLUMETRIC_MEASURE]->(vol:VolumetricMeasure)
WHERE v.viscode IN ['bl', 'sc']
RETURN
    p.ptid       AS ptid,
    vol.region   AS region,
    vol.volume   AS volume,
    vol.hemisphere AS hemisphere
"""

QUERY_PET = """
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_PET_BINDING]->(pet:PETBinding)
WHERE v.viscode IN ['bl', 'sc']
RETURN
    p.ptid       AS ptid,
    pet.tracer   AS tracer,
    pet.region   AS region,
    pet.suvr     AS suvr
"""

QUERY_ATN = """
MATCH (p:Patient)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
RETURN
    p.ptid       AS ptid,
    atn.a_status AS a_status,
    atn.t_status AS t_status,
    atn.n_status AS n_status
"""

QUERY_DIAGNOSIS = """
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_DIAGNOSIS]->(dx:Diagnosis)
WHERE v.viscode IN ['bl', 'sc']
RETURN
    p.ptid           AS ptid,
    dx.diagnosis_code AS diagnosis_code
"""


# ────────────────────────────────────────────────────────────────
# FEATURE EXTRACTOR CLASS
# ────────────────────────────────────────────────────────────────

class CausalFeatureExtractor:
    """Extract and preprocess features for causal discovery from Neo4j."""

    # Cognitive tests we care about (stable across ADNI phases)
    COG_TESTS = ['MMSE', 'CDR', 'ADAS-Cog-13', 'ADAS-Cog', 'MoCA', 'FAQ',
                 'Logical Memory']
    # Biomarker analytes
    BIO_ANALYTES = ['ABETA', 'TAU', 'PTAU', 'Abeta42', 'Tau', 'pTau',
                    'AB42', 'AB40', 'ABETA42', 'TAU_TOTAL', 'PTAU181']
    # Brain regions for volumetric
    VOL_REGIONS = ['Hippocampus', 'Entorhinal', 'Ventricles', 'WholeBrain',
                   'ICV', 'MidTemp', 'Fusiform']
    # PET tracers
    PET_TRACERS = ['AV45', 'FDG', 'AV1451', 'FBB', 'FBP']

    # Diagnosis encoding
    DX_MAP = {'CN': 0, 'SMC': 0, 'EMCI': 1, 'MCI': 1, 'LMCI': 1, 'AD': 2}

    def __init__(self, connector, config: Dict[str, Any]):
        self.connector = connector
        self.config = config.get('causal', {})
        self.output_dir = Path(config.get('output_dir', 'causal'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.min_samples = self.config.get('min_samples', 50)

    def execute(self) -> Dict[str, Any]:
        """Main entry point — extract, pivot, preprocess, save."""
        logger.info("=" * 60)
        logger.info("STEP 21 — Extract Causal Feature Matrix")
        logger.info("=" * 60)

        results = {
            'step': 21,
            'status': 'started',
            'timestamp': datetime.now().isoformat(),
        }

        try:
            # 1. Query each feature group
            logger.info("Querying Neo4j for baseline features...")
            demographics = self._query_demographics()
            cognitive = self._query_cognitive()
            biomarkers = self._query_biomarkers()
            volumetric = self._query_volumetric()
            pet = self._query_pet()
            atn = self._query_atn()
            diagnosis = self._query_diagnosis()

            # 2. Merge into single patient-level DataFrame
            logger.info("Merging feature groups into patient matrix...")
            df = self._merge_features(
                demographics, cognitive, biomarkers,
                volumetric, pet, atn, diagnosis
            )
            logger.info(f"  Raw matrix shape: {df.shape}")

            # 2b. Exclude flagged PTIDs (ADNI data quality advisory — 381_S_ site)
            if 'ptid' in df.columns:
                excluded_mask = df['ptid'].str.startswith('381_S_', na=False)
                n_excluded = excluded_mask.sum()
                if n_excluded > 0:
                    df = df[~excluded_mask].reset_index(drop=True)
                    logger.warning(
                        f"  Excluded {n_excluded} patients from site 381_S_ "
                        f"(ADNI data quality advisory). New shape: {df.shape}"
                    )

            if len(df) < self.min_samples:
                logger.warning(
                    f"Only {len(df)} patients with baseline data "
                    f"(minimum: {self.min_samples}). Results may be unreliable."
                )

            # 3. Save raw version
            raw_path = self.output_dir / 'causal_features_raw.csv'
            df.to_csv(raw_path, index=False)
            logger.info(f"  Saved raw features: {raw_path}")

            # 4. Completeness report
            completeness = self._completeness_report(df)
            comp_path = self.output_dir / 'completeness_report.json'
            with open(comp_path, 'w') as f:
                json.dump(completeness, f, indent=2)
            logger.info(f"  Saved completeness report: {comp_path}")

            # 5. Preprocess (drop sparse, impute, encode, standardize)
            df_clean = self._preprocess(df)
            logger.info(f"  Preprocessed matrix shape: {df_clean.shape}")

            # 6. Save final
            final_path = self.output_dir / 'causal_features.csv'
            df_clean.to_csv(final_path, index=False)
            logger.info(f"  Saved final features: {final_path}")

            # 7. Correlation matrix
            self._plot_correlation(df_clean)

            results.update({
                'status': 'completed',
                'patients': len(df_clean),
                'features': len(df_clean.columns) - 1,  # exclude ptid
                'raw_path': str(raw_path),
                'final_path': str(final_path),
                'completeness': completeness['summary'],
            })
            logger.info(f"✅ Step 21 complete — {results['patients']} patients, "
                        f"{results['features']} features")

        except Exception as e:
            logger.error(f"Step 21 failed: {e}", exc_info=True)
            results['status'] = 'failed'
            results['error'] = str(e)

        return results

    # ── Query helpers ─────────────────────────────────────────

    def _run_query(self, query: str) -> List[Dict]:
        """Run a Cypher query and return list of dicts."""
        return self.connector.run_query(query)

    def _query_demographics(self) -> pd.DataFrame:
        """Demographics: one row per patient."""
        records = self._run_query(QUERY_DEMOGRAPHICS)
        df = pd.DataFrame(records)
        if df.empty:
            logger.warning("No demographic data found")
            return pd.DataFrame(columns=['ptid', 'age', 'gender', 'education', 'apoe_e4_count'])

        # Encode APOE genotype → e4 allele count
        df['apoe_e4_count'] = df['apoe_genotype'].apply(self._count_apoe_e4)
        df.drop(columns=['apoe_genotype'], inplace=True, errors='ignore')
        df.drop_duplicates(subset=['ptid'], keep='first', inplace=True)

        logger.info(f"  Demographics: {len(df)} patients")
        return df

    def _query_cognitive(self) -> pd.DataFrame:
        """Cognitive tests pivoted: one column per test."""
        records = self._run_query(QUERY_COGNITIVE)
        if not records:
            logger.warning("No cognitive data found")
            return pd.DataFrame(columns=['ptid'])

        df = pd.DataFrame(records)
        # Normalize test names
        df['test_name'] = df['test_name'].str.upper().str.strip()
        df['score'] = pd.to_numeric(df['score'], errors='coerce')

        # Pivot: one column per test, take first (baseline) score
        pivot = df.pivot_table(
            index='ptid', columns='test_name', values='score',
            aggfunc='first'
        ).reset_index()

        # Rename to clean column names
        pivot.columns = [f'COG_{c}' if c != 'ptid' else c for c in pivot.columns]
        logger.info(f"  Cognitive: {len(pivot)} patients, "
                    f"{len(pivot.columns)-1} tests")
        return pivot

    def _query_biomarkers(self) -> pd.DataFrame:
        """CSF biomarkers pivoted: one column per analyte."""
        records = self._run_query(QUERY_BIOMARKERS)
        if not records:
            logger.warning("No biomarker data found")
            return pd.DataFrame(columns=['ptid'])

        df = pd.DataFrame(records)
        df['analyte'] = df['analyte'].str.upper().str.strip()
        df['value'] = pd.to_numeric(df['value'], errors='coerce')

        pivot = df.pivot_table(
            index='ptid', columns='analyte', values='value',
            aggfunc='first'
        ).reset_index()
        pivot.columns = [f'BIO_{c}' if c != 'ptid' else c for c in pivot.columns]

        logger.info(f"  Biomarkers: {len(pivot)} patients, "
                    f"{len(pivot.columns)-1} analytes")
        return pivot

    def _query_volumetric(self) -> pd.DataFrame:
        """Volumetric measures pivoted: one column per region."""
        records = self._run_query(QUERY_VOLUMETRIC)
        if not records:
            logger.warning("No volumetric data found")
            return pd.DataFrame(columns=['ptid'])

        df = pd.DataFrame(records)
        # For bilateral structures, average L/R; otherwise use as-is
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')

        # Create region-hemisphere key, then average if duplicates
        df['region_key'] = df.apply(
            lambda r: f"{r['region']}_{r['hemisphere']}"
                      if pd.notna(r.get('hemisphere')) and r.get('hemisphere') not in ['bilateral', '']
                      else r['region'],
            axis=1
        )

        pivot = df.pivot_table(
            index='ptid', columns='region_key', values='volume',
            aggfunc='mean'
        ).reset_index()
        pivot.columns = [f'VOL_{c}' if c != 'ptid' else c for c in pivot.columns]

        logger.info(f"  Volumetric: {len(pivot)} patients, "
                    f"{len(pivot.columns)-1} regions")
        return pivot

    def _query_pet(self) -> pd.DataFrame:
        """PET binding pivoted: one column per tracer."""
        records = self._run_query(QUERY_PET)
        if not records:
            logger.warning("No PET data found")
            return pd.DataFrame(columns=['ptid'])

        df = pd.DataFrame(records)
        df['suvr'] = pd.to_numeric(df['suvr'], errors='coerce')
        df['tracer_key'] = df['tracer'].str.upper().str.strip()

        # Average SUVR across regions per tracer per patient
        pivot = df.pivot_table(
            index='ptid', columns='tracer_key', values='suvr',
            aggfunc='mean'
        ).reset_index()
        pivot.columns = [f'PET_{c}' if c != 'ptid' else c for c in pivot.columns]

        logger.info(f"  PET: {len(pivot)} patients, "
                    f"{len(pivot.columns)-1} tracers")
        return pivot

    def _query_atn(self) -> pd.DataFrame:
        """ATN profile: binary A/T/N status."""
        records = self._run_query(QUERY_ATN)
        if not records:
            logger.warning("No ATN data found")
            return pd.DataFrame(columns=['ptid'])

        df = pd.DataFrame(records)
        # Convert +/- to 1/0
        for col in ['a_status', 't_status', 'n_status']:
            if col in df.columns:
                df[col] = df[col].map({'+': 1, '-': 0}).astype('Int64')

        df.rename(columns={
            'a_status': 'ATN_A', 't_status': 'ATN_T', 'n_status': 'ATN_N'
        }, inplace=True)
        df.drop_duplicates(subset=['ptid'], keep='first', inplace=True)

        logger.info(f"  ATN: {len(df)} patients")
        return df

    def _query_diagnosis(self) -> pd.DataFrame:
        """Baseline diagnosis encoded as ordinal: CN=0, MCI=1, AD=2."""
        records = self._run_query(QUERY_DIAGNOSIS)
        if not records:
            logger.warning("No diagnosis data found")
            return pd.DataFrame(columns=['ptid', 'DX_bl'])

        df = pd.DataFrame(records)
        df['DX_bl'] = df['diagnosis_code'].map(self.DX_MAP)
        df.drop(columns=['diagnosis_code'], inplace=True, errors='ignore')
        df.drop_duplicates(subset=['ptid'], keep='first', inplace=True)

        logger.info(f"  Diagnosis: {len(df)} patients")
        return df

    # ── Merge ────────────────────────────────────────────────

    def _merge_features(self, demographics, cognitive, biomarkers,
                        volumetric, pet, atn, diagnosis) -> pd.DataFrame:
        """Left-join all feature groups on ptid."""
        df = demographics.copy()
        for other in [cognitive, biomarkers, volumetric, pet, atn, diagnosis]:
            if len(other) > 0 and 'ptid' in other.columns:
                df = df.merge(other, on='ptid', how='left')
        return df

    # ── Preprocessing ────────────────────────────────────────

    def _completeness_report(self, df: pd.DataFrame) -> Dict:
        """Report % missing per column."""
        total = len(df)
        per_col = {}
        for col in df.columns:
            if col == 'ptid':
                continue
            n_missing = df[col].isna().sum()
            pct = round(n_missing / total * 100, 1) if total > 0 else 0
            per_col[col] = {
                'missing': int(n_missing),
                'total': total,
                'pct_missing': pct,
            }

        avg_missing = round(np.mean([v['pct_missing'] for v in per_col.values()]), 1)
        cols_gt_50 = [k for k, v in per_col.items() if v['pct_missing'] > 50]

        summary = {
            'total_patients': total,
            'total_features': len(per_col),
            'avg_missing_pct': avg_missing,
            'columns_gt_50pct_missing': cols_gt_50,
        }

        return {'summary': summary, 'per_column': per_col}

    def _preprocess(self, df: pd.DataFrame) -> pd.DataFrame:
        """Impute, encode, standardize."""
        df = df.copy()
        drop_threshold = self.config.get('drop_threshold', 0.5)

        # 1. Encode gender → binary
        if 'gender' in df.columns:
            df['gender'] = df['gender'].map({'M': 0, 'F': 1, 'Male': 0, 'Female': 1})

        # 2. Drop columns with >{threshold}% missing
        n = len(df)
        cols_to_drop = []
        for col in df.columns:
            if col == 'ptid':
                continue
            pct_missing = df[col].isna().sum() / n if n > 0 else 0
            if pct_missing > drop_threshold:
                cols_to_drop.append(col)

        if cols_to_drop:
            logger.info(f"  Dropping {len(cols_to_drop)} columns with >{drop_threshold*100:.0f}% "
                        f"missing: {cols_to_drop[:5]}{'...' if len(cols_to_drop) > 5 else ''}")
            df.drop(columns=cols_to_drop, inplace=True)

        # 3. Separate numeric and categorical for imputation
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        categorical_cols = [c for c in df.columns
                          if c not in numeric_cols and c != 'ptid']

        # 4. Impute numeric with median
        for col in numeric_cols:
            if df[col].isna().any():
                median_val = df[col].median()
                df[col].fillna(median_val, inplace=True)

        # 5. Impute categorical with mode
        for col in categorical_cols:
            if df[col].isna().any():
                mode_val = df[col].mode()
                if len(mode_val) > 0:
                    df[col].fillna(mode_val.iloc[0], inplace=True)

        # 6. Z-score standardization for continuous variables
        # Exclude binary/ordinal columns from standardization
        binary_cols = {'gender', 'ATN_A', 'ATN_T', 'ATN_N', 'DX_bl', 'apoe_e4_count'}
        standardize_cols = [c for c in numeric_cols
                          if c not in binary_cols and c != 'ptid']

        for col in standardize_cols:
            std = df[col].std()
            if std > 0:
                df[col] = (df[col] - df[col].mean()) / std
            else:
                df[col] = 0.0

        logger.info(f"  Final columns: {list(df.columns)}")
        return df

    # ── Visualization ────────────────────────────────────────

    def _plot_correlation(self, df: pd.DataFrame) -> None:
        """Generate and save correlation matrix heatmap."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import matplotlib.colors as mcolors

            numeric_df = df.select_dtypes(include=[np.number])
            if numeric_df.shape[1] < 2:
                logger.warning("Not enough numeric columns for correlation matrix")
                return

            corr = numeric_df.corr()
            n = len(corr)
            fig_size = max(8, n * 0.5)

            fig, ax = plt.subplots(figsize=(fig_size, fig_size))

            # Professional diverging colormap
            cmap = plt.cm.RdBu_r
            im = ax.imshow(corr.values, cmap=cmap, vmin=-1, vmax=1, aspect='auto')

            # Labels
            ax.set_xticks(range(n))
            ax.set_yticks(range(n))
            ax.set_xticklabels(corr.columns, rotation=45, ha='right', fontsize=8)
            ax.set_yticklabels(corr.columns, fontsize=8)

            # Colorbar
            plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label='Pearson r')

            # Annotate cells if not too many
            if n <= 20:
                for i in range(n):
                    for j in range(n):
                        val = corr.values[i, j]
                        color = 'white' if abs(val) > 0.5 else 'black'
                        ax.text(j, i, f'{val:.2f}', ha='center', va='center',
                                fontsize=6, color=color)

            ax.set_title('Baseline Feature Correlation Matrix', fontsize=14, pad=15)
            plt.tight_layout()

            out_path = self.output_dir / 'correlation_matrix.png'
            fig.savefig(out_path, dpi=150, bbox_inches='tight')
            plt.close(fig)
            logger.info(f"  Saved correlation matrix: {out_path}")

        except ImportError:
            logger.warning("matplotlib not available — skipping correlation plot")

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _count_apoe_e4(genotype) -> Optional[int]:
        """Count APOE e4 alleles from genotype string like '3/4' or '4/4'."""
        if pd.isna(genotype) or not genotype:
            return None
        try:
            parts = str(genotype).replace(' ', '').split('/')
            return sum(1 for p in parts if p.strip() == '4')
        except Exception:
            return None


# ────────────────────────────────────────────────────────────────
# CLI + pipeline integration
# ────────────────────────────────────────────────────────────────

def execute_causal_features(config: Dict[str, Any],
                            connector=None) -> Dict[str, Any]:
    """Pipeline entry-point for Step 21."""
    if connector is None:
        from utils.neo4j_connector import Neo4jConnector
        connector = Neo4jConnector(
            config['neo4j']['uri'],
            config['neo4j']['user'],
            config['neo4j']['password']
        )

    extractor = CausalFeatureExtractor(connector, config)
    return extractor.execute()


if __name__ == '__main__':
    import yaml
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
    )

    # Load config
    config_path = Path(__file__).parent.parent / 'config.yaml'
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
    else:
        config = {}

    # Ensure output dir
    config.setdefault('output_dir', 'causal')

    result = execute_causal_features(config)
    print(json.dumps(result, indent=2, default=str))
