"""
Step 29: Knowledge Graph Exploratory Data Analysis
Generates publication-quality figures for thesis and presentations.
Queries Neo4j for graph statistics and produces figures + mermaid diagrams.
Output: SVG + 300 DPI PNG in outputs/eda_figures/
"""

import logging
import json
import textwrap
from pathlib import Path
from typing import Dict, List, Any, Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import seaborn as sns
from matplotlib.gridspec import GridSpec

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)

# ── Publication style ────────────────────────────────────────────────
STYLE = {
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
}

# Diagnosis colour palette (clinical convention)
DX_PALETTE = {
    "CN": "#2ecc71", "SMC": "#a8d08d", "EMCI": "#f1c40f",
    "LMCI": "#e67e22", "MCI": "#e67e22", "AD": "#e74c3c",
    "Dementia": "#c0392b",
}
DX_ORDER = ["CN", "SMC", "EMCI", "LMCI", "MCI", "AD", "Dementia"]

# Node categories for grouping and colouring
NODE_CATEGORIES = {
    "Clinical Core": {
        "nodes": ["Patient", "Visit", "Diagnosis", "DiseaseStage", "DiagnosisStage"],
        "color": "#3498db", "desc": "Participants, longitudinal visits, and diagnostic labels"
    },
    "Assessments": {
        "nodes": ["CognitiveAssessment", "MultimodalAssessment", "CognitiveTrajectory",
                   "CognitiveTest", "TestType"],
        "color": "#9b59b6", "desc": "MMSE, CDR, ADAS-Cog scores and trajectories"
    },
    "Biomarkers": {
        "nodes": ["Biomarker", "BiomarkerProfile", "ATNProfile", "ATNCategory",
                   "BiomarkerCategory", "BiomarkerPattern", "PETTracer"],
        "color": "#e74c3c", "desc": "CSF (Abeta, Tau, pTau), PET SUVR, ATN framework"
    },
    "Imaging": {
        "nodes": ["ImageNode", "SmoothRendering", "PyramidFormat", "WebViewerReady"],
        "color": "#1abc9c", "desc": "MRI/PET images with multi-format renderings"
    },
    "Demographics & Family": {
        "nodes": ["FamilyMember", "FamilyRisk", "Demographics", "ClinicalPhenotype",
                   "PatientSummary"],
        "color": "#27ae60", "desc": "Family history, risk factors, patient summaries"
    },
    "Ontology & Semantics": {
        "nodes": ["OntologyConcept", "BrainRegion", "RiskFactor", "BiologicalPathway",
                   "Domain", "Ontology", "EventOntology"],
        "color": "#2980b9", "desc": "SNOMED-CT, LOINC, UBERON, ICD-10 concepts"
    },
    "Temporal & Events": {
        "nodes": ["ProgressionEvent", "ProgressionPattern", "Timeline",
                   "EventType", "ClinicalFinding"],
        "color": "#f39c12", "desc": "Disease progression events and temporal chains"
    },
    "Infrastructure": {
        "nodes": ["ResearchCohort", "Cohort", "BatchIngestion"],
        "color": "#95a5a6", "desc": "ADNI cohort metadata and data ingestion tracking"
    },
}

# Relationship semantic categories
REL_CATEGORIES = {
    "Clinical": {
        "rels": ["HAS_VISIT", "HAS_DIAGNOSIS", "SUPPORTS_DIAGNOSIS", "HAS_CLINICAL_FINDING",
                 "IS_CLINICAL_FINDING", "RESULTED_IN"],
        "color": "#3498db",
    },
    "Assessment": {
        "rels": ["HAS_COGNITIVE_ASSESSMENT", "UNDERWENT_ASSESSMENT", "INCLUDES_ASSESSMENT",
                 "IS_TYPE", "HAS_MULTIMODAL_ASSESSMENT", "HAS_COGNITIVE_TRAJECTORY"],
        "color": "#9b59b6",
    },
    "Biomarker": {
        "rels": ["HAS_BIOMARKER", "BELONGS_TO_CATEGORY", "HAS_BIOMARKER_PROFILE"],
        "color": "#e74c3c",
    },
    "Imaging": {
        "rels": ["HAS_IMAGE", "HAS_SMOOTH_RENDERING", "HAS_PYRAMID", "HAS_WEB_VIEWER"],
        "color": "#1abc9c",
    },
    "Family": {
        "rels": ["HAS_FAMILY_MEMBER", "HAS_SIBLING", "HAS_PARENT"],
        "color": "#27ae60",
    },
    "Temporal": {
        "rels": ["PROGRESSED_TO", "PRECEDES", "FOLLOWED_BY", "ASSOCIATED_WITH_STAGE"],
        "color": "#f39c12",
    },
    "Ontology": {
        "rels": ["MAPS_TO", "CLASSIFIED_AS", "IS_A", "INDICATES_PATHWAY"],
        "color": "#2980b9",
    },
}


def _get_node_color(label: str) -> str:
    for cat in NODE_CATEGORIES.values():
        if label in cat["nodes"]:
            return cat["color"]
    return "#bdc3c7"


def _get_node_category(label: str) -> str:
    for cat_name, cat in NODE_CATEGORIES.items():
        if label in cat["nodes"]:
            return cat_name
    return "Other"


class KnowledgeGraphEDA:
    """Generates publication-quality EDA figures from the ADNI Knowledge Graph."""

    def __init__(self, connector: Neo4jConnector, output_dir: str = "outputs/eda_figures"):
        self.connector = connector
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stats: Dict[str, Any] = {}

    def _query(self, cypher: str, params: dict = None) -> List[Dict]:
        try:
            return self.connector.run_query(cypher, params or {})
        except Exception as e:
            logger.warning(f"Query failed: {e}")
            return []

    def _save(self, fig: plt.Figure, name: str):
        for ext in ("svg", "png"):
            path = self.output_dir / f"{name}.{ext}"
            fig.savefig(str(path), format=ext, bbox_inches="tight",
                        dpi=300 if ext == "png" else None)
        plt.close(fig)
        logger.info(f"  Saved: {name}.svg / .png")

    def _save_mermaid(self, mermaid_code: str, name: str):
        path = self.output_dir / f"{name}.mmd"
        path.write_text(mermaid_code, encoding="utf-8")
        logger.info(f"  Saved: {name}.mmd")

    def _fmt(self, n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return str(n)

    # ── Main entry ────────────────────────────────────────────────────

    def execute(self) -> Dict[str, Any]:
        logger.info("\n" + "=" * 70)
        logger.info("KNOWLEDGE GRAPH — EXPLORATORY DATA ANALYSIS (v2)")
        logger.info("=" * 70)

        with plt.rc_context(STYLE):
            self._fig01_node_distribution()
            self._fig02_relationship_distribution()
            self._fig03_patient_demographics()
            self._fig04_diagnosis_distribution()
            self._fig05_disease_progression()
            self._fig06_csf_biomarkers()
            self._fig07_cognitive_scores()
            self._fig08_temporal_visits()
            self._fig09_brain_volumetrics()
            self._fig10_ontology_coverage()
            self._fig11_missing_data()
            self._fig12_graph_connectivity()
            self._fig13_correlation_matrix()
            self._fig14_kg_summary_dashboard()
            self._fig15_relationship_schema()

        # Mermaid diagrams
        self._mermaid_kg_schema()
        self._mermaid_data_flow()
        self._mermaid_ontology_layer()

        # Save statistics
        stats_path = self.output_dir / "eda_statistics.json"
        with open(stats_path, "w") as f:
            json.dump(self.stats, f, indent=2, default=str)
        logger.info(f"\nStatistics saved: {stats_path}")
        return self.stats

    # ── 1. Node Distribution (filtered, categorised) ──────────────────

    def _fig01_node_distribution(self):
        logger.info("\n[1/15] Node type distribution...")
        rows = self._query("""
            CALL db.labels() YIELD label
            CALL (label) { MATCH (n) WHERE label IN labels(n) RETURN count(n) AS cnt }
            RETURN label, cnt ORDER BY cnt DESC
        """)
        if not rows:
            return

        # Filter out empty labels
        rows = [r for r in rows if r["cnt"] > 0]
        labels = [r["label"] for r in rows]
        counts = [r["cnt"] for r in rows]
        colors = [_get_node_color(l) for l in labels]
        self.stats["node_counts"] = dict(zip(labels, counts))
        # Use a direct count to avoid inflating total due to multi-labeled nodes
        total = self._query("MATCH (n) RETURN count(n) AS cnt")
        self.stats["total_nodes"] = total[0]["cnt"] if total else sum(counts)

        fig, ax = plt.subplots(figsize=(12, max(6, len(labels) * 0.35)))
        bars = ax.barh(range(len(labels)), counts, color=colors, edgecolor="white", linewidth=0.5)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlabel("Number of Nodes")
        ax.set_title(f"Knowledge Graph — Node Type Distribution ({self._fmt(sum(counts))} total nodes)")
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: self._fmt(int(x))))

        for bar, cnt in zip(bars, counts):
            ax.text(bar.get_width() + max(counts) * 0.01, bar.get_y() + bar.get_height() / 2,
                    self._fmt(cnt), va="center", fontsize=8)

        # Category legend
        legend_patches = [mpatches.Patch(color=c["color"], label=name)
                          for name, c in NODE_CATEGORIES.items()]
        ax.legend(handles=legend_patches, loc="lower right", fontsize=8,
                  title="Category", title_fontsize=9, framealpha=0.9)

        fig.tight_layout()
        self._save(fig, "01_node_distribution")

    # ── 2. Relationship Distribution (categorised) ────────────────────

    def _fig02_relationship_distribution(self):
        logger.info("[2/15] Relationship type distribution...")
        rows = self._query("""
            CALL db.relationshipTypes() YIELD relationshipType AS type
            CALL (type) { MATCH ()-[r]->() WHERE type(r) = type RETURN count(r) AS cnt }
            RETURN type, cnt ORDER BY cnt DESC LIMIT 25
        """)
        if not rows:
            return

        types = [r["type"] for r in rows]
        counts = [r["cnt"] for r in rows]
        self.stats["relationship_counts"] = dict(zip(types, counts))
        self.stats["total_relationships"] = sum(r["cnt"] for r in rows)

        # Colour by category
        def get_rel_color(rtype):
            for cat in REL_CATEGORIES.values():
                if rtype in cat["rels"]:
                    return cat["color"]
            return "#bdc3c7"

        colors = [get_rel_color(t) for t in types]

        fig, ax = plt.subplots(figsize=(13, max(6, len(types) * 0.35)))
        ax.barh(range(len(types)), counts, color=colors, edgecolor="white", linewidth=0.5)
        ax.set_yticks(range(len(types)))
        ax.set_yticklabels(types, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlabel("Number of Relationships")
        ax.set_title("Knowledge Graph — Relationship Type Distribution (Top 25)")
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: self._fmt(int(x))))

        for i, cnt in enumerate(counts):
            ax.text(cnt + max(counts) * 0.01, i, self._fmt(cnt), va="center", fontsize=8)

        legend_patches = [mpatches.Patch(color=c["color"], label=name)
                          for name, c in REL_CATEGORIES.items()]
        ax.legend(handles=legend_patches, loc="lower right", fontsize=8,
                  title="Category", title_fontsize=9, framealpha=0.9)

        fig.tight_layout()
        self._save(fig, "02_relationship_distribution")

    # ── 3. Patient Demographics ───────────────────────────────────────

    def _fig03_patient_demographics(self):
        logger.info("[3/15] Patient demographics...")
        fig = plt.figure(figsize=(14, 10))
        gs = GridSpec(2, 2, hspace=0.35, wspace=0.3)

        # 3a. Age — try multiple property names
        rows = self._query("""
            MATCH (p:Patient)
            WITH p, COALESCE(p.age_at_baseline, p.age, p.baseline_age) AS age
            WHERE age IS NOT NULL
            RETURN age
        """)
        if not rows:
            # Fallback: check Demographics nodes
            rows = self._query("""
                MATCH (d:Demographics)
                WHERE d.age IS NOT NULL OR d.AGE IS NOT NULL
                RETURN COALESCE(d.age, d.AGE) AS age
            """)

        ax1 = fig.add_subplot(gs[0, 0])
        if rows:
            ages = [r["age"] for r in rows if r["age"] is not None]
            if ages:
                ax1.hist(ages, bins=30, color="#3498db", edgecolor="white", alpha=0.85)
                ax1.axvline(np.median(ages), color="#e74c3c", ls="--", lw=1.5,
                            label=f"Median: {np.median(ages):.0f}")
                ax1.set_xlabel("Age at Baseline")
                ax1.set_ylabel("Count")
                ax1.set_title(f"Age Distribution (N={len(ages):,})")
                ax1.legend()
                self.stats["age_median"] = float(np.median(ages))
                self.stats["age_mean"] = float(np.mean(ages))
            else:
                ax1.text(0.5, 0.5, "No age data found\n(age_at_baseline is NULL for all patients)",
                         ha="center", va="center", transform=ax1.transAxes, fontsize=10, color="gray")
                ax1.set_title("Age Distribution")
        else:
            ax1.text(0.5, 0.5, "No age data found", ha="center", va="center",
                     transform=ax1.transAxes, fontsize=10, color="gray")
            ax1.set_title("Age Distribution")

        # 3b. Gender
        rows = self._query("""
            MATCH (p:Patient)
            WHERE p.gender IS NOT NULL
            RETURN p.gender AS gender, count(p) AS cnt
        """)
        ax2 = fig.add_subplot(gs[0, 1])
        if rows:
            genders = [r["gender"] for r in rows]
            counts = [r["cnt"] for r in rows]
            # Normalise labels
            label_map = {"M": "Male", "F": "Female", "1": "Male", "2": "Female"}
            display_labels = [label_map.get(g, g) for g in genders]
            colors = ["#3498db" if "Male" in dl or dl == "M" else "#e91e63" for dl in display_labels]
            ax2.pie(counts, labels=[f"{l}\n(n={c:,})" for l, c in zip(display_labels, counts)],
                    autopct="%1.1f%%", colors=colors, startangle=90, textprops={"fontsize": 10})
            ax2.set_title("Gender Distribution")
            self.stats["gender_distribution"] = dict(zip(display_labels, counts))

        # 3c. Education
        rows = self._query("""
            MATCH (p:Patient)
            WITH p, COALESCE(p.education_years, p.education, p.PTEDUCAT) AS edu
            WHERE edu IS NOT NULL
            RETURN edu
        """)
        ax3 = fig.add_subplot(gs[1, 0])
        if rows:
            edu = [r["edu"] for r in rows if r["edu"] is not None]
            if edu:
                ax3.hist(edu, bins=20, color="#2ecc71", edgecolor="white", alpha=0.85)
                ax3.axvline(np.median(edu), color="#e74c3c", ls="--", lw=1.5,
                            label=f"Median: {np.median(edu):.0f} yrs")
                ax3.set_xlabel("Years of Education")
                ax3.set_ylabel("Count")
                ax3.set_title(f"Education Distribution (N={len(edu):,})")
                ax3.legend()
            else:
                ax3.text(0.5, 0.5, "No education data found", ha="center", va="center",
                         transform=ax3.transAxes, fontsize=10, color="gray")
                ax3.set_title("Education Distribution")
        else:
            ax3.text(0.5, 0.5, "No education data found", ha="center", va="center",
                     transform=ax3.transAxes, fontsize=10, color="gray")
            ax3.set_title("Education Distribution")

        # 3d. APOE
        rows = self._query("""
            MATCH (p:Patient)
            WHERE p.apoe_genotype IS NOT NULL
            RETURN p.apoe_genotype AS allele, count(p) AS cnt
            ORDER BY cnt DESC
        """)
        ax4 = fig.add_subplot(gs[1, 1])
        if rows:
            alleles = [str(r["allele"]) for r in rows]
            counts = [r["cnt"] for r in rows]
            ax4.bar(alleles, counts, color="#9b59b6", edgecolor="white")
            ax4.set_xlabel("APOE Genotype")
            ax4.set_ylabel("Count")
            ax4.set_title(f"APOE Genotype (N={sum(counts):,})")
            for i, cnt in enumerate(counts):
                ax4.text(i, cnt + max(counts) * 0.02, str(cnt), ha="center", fontsize=9)
        else:
            ax4.text(0.5, 0.5, "No APOE data found", ha="center", va="center",
                     transform=ax4.transAxes, fontsize=10, color="gray")
            ax4.set_title("APOE Genotype")

        n_patients = self.stats.get("node_counts", {}).get("Patient", "?")
        fig.suptitle(f"Patient Demographics (N={n_patients:,} ADNI Participants)", fontsize=14, y=1.01)
        self._save(fig, "03_patient_demographics")

    # ── 4. Diagnosis Distribution ─────────────────────────────────────

    def _fig04_diagnosis_distribution(self):
        logger.info("[4/15] Diagnosis distribution...")
        rows = self._query("""
            MATCH (d:Diagnosis)
            WITH COALESCE(d.dx_label, d.diagnosis_code, d.name) AS dx
            WHERE dx IS NOT NULL
            RETURN dx, count(*) AS cnt
            ORDER BY cnt DESC
        """)
        if not rows:
            return

        dx_labels = [r["dx"] for r in rows]
        counts = [r["cnt"] for r in rows]
        colors = [DX_PALETTE.get(dx, "#95a5a6") for dx in dx_labels]
        self.stats["diagnosis_distribution"] = dict(zip(dx_labels, counts))

        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(dx_labels, counts, color=colors, edgecolor="white", linewidth=0.5)
        ax.set_xlabel("Diagnosis Group")
        ax.set_ylabel("Number of Diagnosis Nodes")
        ax.set_title("Diagnosis Distribution Across ADNI Cohort")
        plt.xticks(rotation=45, ha="right")

        for bar, cnt in zip(bars, counts):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(counts) * 0.01,
                    self._fmt(cnt), ha="center", fontsize=9)

        # Add clinical explanation
        ax.annotate("CN = Cognitively Normal\nMCI = Mild Cognitive Impairment\nAD = Alzheimer's Disease",
                    xy=(0.98, 0.95), xycoords="axes fraction", ha="right", va="top",
                    fontsize=9, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.8))

        fig.tight_layout()
        self._save(fig, "04_diagnosis_distribution")

    # ── 5. Disease Stage Progression ──────────────────────────────────

    def _fig05_disease_progression(self):
        logger.info("[5/15] Disease stage progression...")
        rows = self._query("""
            MATCH (d1:DiseaseStage)-[r:PROGRESSES_TO]->(d2:DiseaseStage)
            RETURN d1.name AS from_stage, d2.name AS to_stage,
                   COALESCE(r.patient_count, r.count, 1) AS weight
        """)
        if not rows:
            rows = self._query("""
                MATCH (p:Patient)-[:HAS_VISIT]->(v1:Visit)-[:HAS_DIAGNOSIS]->(d1:Diagnosis),
                      (p)-[:HAS_VISIT]->(v2:Visit)-[:HAS_DIAGNOSIS]->(d2:Diagnosis)
                WHERE v1.months_from_baseline < v2.months_from_baseline
                  AND COALESCE(d1.dx_label, d1.diagnosis_code) <> COALESCE(d2.dx_label, d2.diagnosis_code)
                WITH COALESCE(d1.dx_label, d1.diagnosis_code) AS from_dx,
                     COALESCE(d2.dx_label, d2.diagnosis_code) AS to_dx, p
                RETURN from_dx AS from_stage, to_dx AS to_stage, count(DISTINCT p) AS weight
                ORDER BY weight DESC LIMIT 15
            """)
        if not rows:
            logger.warning("  No disease progression data found.")
            return

        self.stats["disease_transitions"] = [
            {"from": r["from_stage"], "to": r["to_stage"], "count": r["weight"]} for r in rows
        ]

        stages_set = sorted(set([r["from_stage"] for r in rows] + [r["to_stage"] for r in rows]),
                            key=lambda s: DX_ORDER.index(s) if s in DX_ORDER else 99)
        matrix = pd.DataFrame(0, index=stages_set, columns=stages_set)
        for r in rows:
            if r["from_stage"] in stages_set and r["to_stage"] in stages_set:
                matrix.loc[r["from_stage"], r["to_stage"]] = r["weight"]

        fig, ax = plt.subplots(figsize=(9, 7))
        sns.heatmap(matrix, annot=True, fmt="g", cmap="YlOrRd", ax=ax,
                    linewidths=0.5, linecolor="white", cbar_kws={"label": "Patient Count"})
        ax.set_title("Disease Stage Transition Matrix")
        ax.set_xlabel("To Stage")
        ax.set_ylabel("From Stage")
        fig.tight_layout()
        self._save(fig, "05_disease_progression")

    # ── 6. CSF Biomarkers ─────────────────────────────────────────────

    def _fig06_csf_biomarkers(self):
        logger.info("[6/15] CSF biomarker distributions...")
        rows = self._query("""
            MATCH (v:Visit)-[:HAS_DIAGNOSIS]->(dx:Diagnosis),
                  (v)-[:HAS_BIOMARKER]->(b:Biomarker)
            WHERE b.value IS NOT NULL
              AND (dx.dx_label IS NOT NULL OR dx.diagnosis_code IS NOT NULL)
            RETURN COALESCE(dx.dx_label, dx.diagnosis_code) AS diagnosis,
                   COALESCE(b.analyte, b.name, b.biomarker_type) AS analyte,
                   toFloat(b.value) AS value
            LIMIT 100000
        """)
        if not rows:
            logger.warning("  No biomarker data found.")
            return

        df = pd.DataFrame(rows)
        if "analyte" not in df.columns or df["analyte"].isna().all():
            return

        # Top analytes by count
        top_analytes = df["analyte"].value_counts().head(6).index.tolist()
        df = df[df["analyte"].isin(top_analytes)]
        n_analytes = len(top_analytes)

        fig, axes = plt.subplots(2, 3, figsize=(16, 10), sharey=False)
        axes_flat = axes.flatten()

        for i, analyte in enumerate(top_analytes[:6]):
            ax = axes_flat[i]
            sub = df[df["analyte"] == analyte]
            dx_present = [d for d in DX_ORDER if d in sub["diagnosis"].values]
            palette = {d: DX_PALETTE.get(d, "#95a5a6") for d in dx_present}
            if len(sub) > 0 and len(dx_present) > 0:
                sns.violinplot(data=sub, x="diagnosis", y="value", order=dx_present,
                               palette=palette, ax=ax, inner="box", cut=0, linewidth=0.8)
            ax.set_title(analyte, fontsize=11)
            ax.set_xlabel("")
            ax.set_ylabel("Value" if i % 3 == 0 else "")
            plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

        for j in range(len(top_analytes), 6):
            axes_flat[j].set_visible(False)

        fig.suptitle("Biomarker Distributions by Diagnosis Group", fontsize=14, y=1.02)
        fig.tight_layout()
        self._save(fig, "06_biomarker_distributions")

    # ── 7. Cognitive Scores ───────────────────────────────────────────

    def _fig07_cognitive_scores(self):
        logger.info("[7/15] Cognitive score distributions...")
        rows = self._query("""
            MATCH (v:Visit)-[:HAS_DIAGNOSIS]->(dx:Diagnosis),
                  (v)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
            WHERE ca.total_score IS NOT NULL
              AND ca.test_name IS NOT NULL
              AND (dx.dx_label IS NOT NULL OR dx.diagnosis_code IS NOT NULL)
            RETURN COALESCE(dx.dx_label, dx.diagnosis_code) AS diagnosis,
                   ca.test_name AS test, toFloat(ca.total_score) AS score
            LIMIT 100000
        """)
        if not rows:
            logger.warning("  No cognitive score data found.")
            return

        df = pd.DataFrame(rows)
        tests = df["test"].value_counts().head(5).index.tolist()
        n_tests = len(tests)

        fig, axes = plt.subplots(1, min(n_tests, 5), figsize=(4.5 * min(n_tests, 5), 6), sharey=False)
        if n_tests == 1:
            axes = [axes]

        for ax, test in zip(axes, tests[:5]):
            sub = df[df["test"] == test]
            dx_present = [d for d in DX_ORDER if d in sub["diagnosis"].values]
            palette = {d: DX_PALETTE.get(d, "#95a5a6") for d in dx_present}
            if len(sub) > 0 and len(dx_present) > 0:
                sns.boxplot(data=sub, x="diagnosis", y="score", order=dx_present,
                            palette=palette, ax=ax, linewidth=0.8, fliersize=2)
            ax.set_title(test)
            ax.set_xlabel("")
            ax.set_ylabel("Score" if ax == axes[0] else "")
            plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

        fig.suptitle("Cognitive Assessment Scores by Diagnosis", fontsize=14, y=1.02)
        fig.tight_layout()
        self._save(fig, "07_cognitive_scores")

    # ── 8. Temporal Visits ────────────────────────────────────────────

    def _fig08_temporal_visits(self):
        logger.info("[8/15] Temporal visit patterns...")
        rows = self._query("""
            MATCH (v:Visit)
            WHERE v.viscode IS NOT NULL
            RETURN v.viscode AS viscode, count(v) AS cnt
            ORDER BY cnt DESC
        """)
        if not rows:
            return

        def viscode_sort_key(vc):
            vc = str(vc).lower().strip()
            if vc in ("bl", "baseline"): return 0
            if vc in ("sc", "screening"): return -1
            if vc.startswith("m"):
                try: return float(vc[1:])
                except ValueError: return 9999
            if vc.startswith("y"):
                try: return float(vc[1:]) * 12
                except ValueError: return 9999
            return 9999

        # Filter to standard ADNI viscodes
        standard = [r for r in rows if viscode_sort_key(r["viscode"]) < 200]
        standard.sort(key=lambda x: viscode_sort_key(x["viscode"]))
        if not standard:
            standard = sorted(rows, key=lambda x: -x["cnt"])[:30]

        viscodes = [d["viscode"] for d in standard]
        counts = [d["cnt"] for d in standard]
        self.stats["visit_distribution"] = dict(zip(viscodes, counts))

        fig, ax = plt.subplots(figsize=(14, 5))
        bars = ax.bar(range(len(viscodes)), counts, color="#3498db", edgecolor="white")
        ax.set_xticks(range(len(viscodes)))
        ax.set_xticklabels(viscodes, rotation=60, ha="right", fontsize=8)
        ax.set_xlabel("Visit Code (bl=baseline, mXX=month XX, yX=year X)")
        ax.set_ylabel("Number of Visits")
        ax.set_title("Temporal Visit Distribution — Standard ADNI Visit Codes")

        for bar, cnt in zip(bars, counts):
            if cnt > max(counts) * 0.05:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(counts) * 0.01,
                        str(cnt), ha="center", fontsize=7)

        fig.tight_layout()
        self._save(fig, "08_temporal_visits")

    # ── 9. Brain Volumetrics ──────────────────────────────────────────

    def _fig09_brain_volumetrics(self):
        logger.info("[9/15] Brain region volumetrics...")
        rows = self._query("""
            MATCH (v:Visit)-[:HAS_DIAGNOSIS]->(dx:Diagnosis),
                  (v)-[r]->(vol)
            WHERE vol.volume IS NOT NULL AND vol.region_name IS NOT NULL
              AND (dx.dx_label IS NOT NULL OR dx.diagnosis_code IS NOT NULL)
            RETURN COALESCE(dx.dx_label, dx.diagnosis_code) AS diagnosis,
                   vol.region_name AS region, toFloat(vol.volume) AS volume
            LIMIT 50000
        """)
        if not rows:
            logger.warning("  No volumetric data found.")
            return

        df = pd.DataFrame(rows)
        top_regions = df["region"].value_counts().head(6).index.tolist()
        df = df[df["region"].isin(top_regions)]
        dx_present = [d for d in DX_ORDER if d in df["diagnosis"].values]
        palette = {d: DX_PALETTE.get(d, "#95a5a6") for d in dx_present}

        n = min(len(top_regions), 6)
        ncols = 3
        nrows = (n + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(16, 5 * nrows), sharey=False)
        axes_flat = axes.flatten() if hasattr(axes, 'flatten') else [axes]

        for i, region in enumerate(top_regions[:6]):
            ax = axes_flat[i]
            sub = df[df["region"] == region]
            if len(sub) > 0 and len(dx_present) > 0:
                sns.boxplot(data=sub, x="diagnosis", y="volume", order=dx_present,
                            palette=palette, ax=ax, linewidth=0.8, fliersize=2)
            ax.set_title(region, fontsize=11)
            ax.set_xlabel("")
            ax.set_ylabel("Volume (mm\u00b3)" if i % ncols == 0 else "")
            plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

        for j in range(n, len(axes_flat)):
            axes_flat[j].set_visible(False)

        fig.suptitle("Brain Region Volumes by Diagnosis", fontsize=14, y=1.01)
        fig.tight_layout()
        self._save(fig, "09_brain_volumetrics")

    # ── 10. Ontology Coverage ─────────────────────────────────────────

    def _fig10_ontology_coverage(self):
        logger.info("[10/15] Ontology coverage...")
        ontology_checks = {
            "SNOMED": "snomed_code", "LOINC": "loinc_code", "UBERON": "uberon_id",
            "ICD-10": "icd10_code", "RDF Type": "rdf_type", "Ontology URI": "ontology_uri",
        }
        node_labels = ["Patient", "Diagnosis", "CognitiveAssessment", "Biomarker",
                        "BrainRegion", "Visit", "DiseaseStage"]

        matrix = pd.DataFrame(0.0, index=node_labels, columns=list(ontology_checks.keys()))

        for label in node_labels:
            total_res = self._query(f"MATCH (n:{label}) RETURN count(n) AS total")
            total = total_res[0]["total"] if total_res else 0
            if total == 0:
                continue
            for ont_name, prop in ontology_checks.items():
                has_res = self._query(f"MATCH (n:{label}) WHERE n.{prop} IS NOT NULL RETURN count(n) AS cnt")
                cnt = has_res[0]["cnt"] if has_res else 0
                matrix.loc[label, ont_name] = round(100 * cnt / total, 1)

        self.stats["ontology_coverage"] = matrix.to_dict()

        fig, ax = plt.subplots(figsize=(10, 6))
        sns.heatmap(matrix, annot=True, fmt=".0f", cmap="YlGn", ax=ax,
                    linewidths=0.5, linecolor="white", vmin=0, vmax=100,
                    cbar_kws={"label": "Coverage (%)"})
        ax.set_title("Ontology Property Coverage by Node Type (%)\nShows which ontology codes are assigned to each node type")
        ax.set_ylabel("")
        fig.tight_layout()
        self._save(fig, "10_ontology_coverage")

    # ── 11. Missing Data ──────────────────────────────────────────────

    def _fig11_missing_data(self):
        logger.info("[11/15] Missing data heatmap...")
        checks = {
            "Patient": ["gender", "education_years", "apoe_genotype", "age_at_baseline"],
            "Diagnosis": ["diagnosis_code", "snomed_code", "icd10_code"],
            "CognitiveAssessment": ["total_score", "test_name"],
            "Visit": ["viscode", "visit_date", "months_from_baseline"],
        }

        rows_data = []
        for label, props in checks.items():
            total_res = self._query(f"MATCH (n:{label}) RETURN count(n) AS total")
            total = total_res[0]["total"] if total_res else 0
            if total == 0:
                continue
            for prop in props:
                null_res = self._query(f"MATCH (n:{label}) WHERE n.{prop} IS NULL RETURN count(n) AS cnt")
                null_cnt = null_res[0]["cnt"] if null_res else 0
                pct = round(100 * null_cnt / total, 1)
                rows_data.append({"Node": label, "Property": prop, "Missing %": pct})

        if not rows_data:
            return

        df = pd.DataFrame(rows_data)
        pivot = df.pivot(index="Node", columns="Property", values="Missing %").fillna(0)
        self.stats["missing_data"] = pivot.to_dict()

        fig, ax = plt.subplots(figsize=(12, 5))
        sns.heatmap(pivot, annot=True, fmt=".1f", cmap="YlOrRd", ax=ax,
                    linewidths=0.5, linecolor="white", vmin=0, vmax=100,
                    cbar_kws={"label": "Missing (%)"})
        ax.set_title("Data Completeness — Missing Properties by Node Type (%)\n"
                     "100% = property not populated during ETL; 0% = fully complete")
        ax.set_ylabel("")
        fig.tight_layout()
        self._save(fig, "11_missing_data")

    # ── 12. Graph Connectivity ────────────────────────────────────────

    def _fig12_graph_connectivity(self):
        logger.info("[12/15] Graph connectivity...")
        rows = self._query("""
            MATCH (n)
            WITH n, size([(n)-[]-() | 1]) AS degree
            WHERE degree > 0
            RETURN labels(n)[0] AS label, degree
            ORDER BY degree DESC
            LIMIT 5000
        """)
        if not rows:
            return

        degrees = [r["degree"] for r in rows]
        self.stats["max_degree"] = max(degrees)
        self.stats["avg_degree"] = float(np.mean(degrees))
        self.stats["median_degree"] = float(np.median(degrees))

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

        ax1.hist(degrees, bins=50, color="#3498db", edgecolor="white", alpha=0.85)
        ax1.set_xlabel("Node Degree (number of connections)")
        ax1.set_ylabel("Frequency (log scale)")
        ax1.set_title("Degree Distribution (Top 5000 Nodes)")
        ax1.set_yscale("log")
        ax1.annotate(f"Max degree: {max(degrees):,}\nMedian: {np.median(degrees):.0f}\nMean: {np.mean(degrees):.0f}",
                     xy=(0.95, 0.95), xycoords="axes fraction", ha="right", va="top", fontsize=9,
                     bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

        # Degree by node type
        from collections import defaultdict
        type_degrees = defaultdict(list)
        for r in rows[:500]:
            type_degrees[r["label"]].append(r["degree"])

        type_stats = [(lbl, np.mean(ds), max(ds)) for lbl, ds in type_degrees.items()]
        type_stats.sort(key=lambda x: -x[2])
        top_types = type_stats[:10]

        labels_t = [t[0] for t in top_types]
        max_degs = [t[2] for t in top_types]
        colors = [_get_node_color(l) for l in labels_t]

        ax2.barh(labels_t, max_degs, color=colors, edgecolor="white")
        ax2.set_xlabel("Maximum Degree")
        ax2.set_title("Hub Nodes — Top 10 by Max Degree")
        ax2.invert_yaxis()
        for i, (_, _, md) in enumerate(top_types):
            ax2.text(md + max(max_degs) * 0.01, i, self._fmt(md), va="center", fontsize=8)

        fig.tight_layout()
        self._save(fig, "12_graph_connectivity")

    # ── 13. Correlation Matrix ────────────────────────────────────────

    def _fig13_correlation_matrix(self):
        logger.info("[13/15] Biomarker-cognitive correlation matrix...")
        rows = self._query("""
            MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)
            WHERE v.viscode IN ['bl', 'sc']
            OPTIONAL MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(mmse:CognitiveAssessment {test_name: 'MMSE'})
            OPTIONAL MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(cdr:CognitiveAssessment {test_name: 'CDR'})
            OPTIONAL MATCH (v)-[:HAS_BIOMARKER]->(ab:Biomarker)
                WHERE ab.analyte IN ['ABETA42', 'Abeta42']
            OPTIONAL MATCH (v)-[:HAS_BIOMARKER]->(tau:Biomarker)
                WHERE tau.analyte IN ['TAU', 'Tau']
            OPTIONAL MATCH (v)-[:HAS_BIOMARKER]->(ptau:Biomarker)
                WHERE ptau.analyte IN ['PTAU', 'pTau']
            WITH p, v,
                 COALESCE(p.age_at_baseline, p.age) AS age,
                 p.education_years AS education,
                 toFloat(mmse.total_score) AS mmse,
                 toFloat(cdr.total_score) AS cdr,
                 toFloat(ab.value) AS abeta42,
                 toFloat(tau.value) AS tau,
                 toFloat(ptau.value) AS ptau
            WHERE age IS NOT NULL OR mmse IS NOT NULL OR abeta42 IS NOT NULL
            RETURN age, education, mmse, cdr, abeta42, tau, ptau
            LIMIT 5000
        """)
        if not rows:
            logger.warning("  No data for correlation matrix.")
            return

        df = pd.DataFrame(rows)
        df = df.dropna(axis=1, thresh=int(len(df) * 0.1))
        if df.shape[1] < 2:
            return

        corr = df.corr(numeric_only=True)
        self.stats["correlation_matrix"] = corr.to_dict()

        fig, ax = plt.subplots(figsize=(9, 7))
        mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
        sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", cmap="RdBu_r",
                    center=0, ax=ax, linewidths=0.5, linecolor="white",
                    vmin=-1, vmax=1, square=True)
        ax.set_title("Baseline Biomarker-Cognitive Correlation Matrix\n"
                     "Positive = increase together | Negative = inverse relationship")
        fig.tight_layout()
        self._save(fig, "13_correlation_matrix")

    # ── 14. KG Summary Dashboard ──────────────────────────────────────

    def _fig14_kg_summary_dashboard(self):
        logger.info("[14/15] KG summary dashboard...")

        total_nodes = self.stats.get("total_nodes", 0)
        total_rels = self.stats.get("total_relationships", 0)
        n_patients = self.stats.get("node_counts", {}).get("Patient", 0)
        n_visits = self.stats.get("node_counts", {}).get("Visit", 0)
        n_images = self.stats.get("node_counts", {}).get("ImageNode", 0)
        n_diagnoses = self.stats.get("node_counts", {}).get("Diagnosis", 0)
        n_ontology = self.stats.get("node_counts", {}).get("OntologyConcept", 0)
        n_labels = len([v for v in self.stats.get("node_counts", {}).values() if v > 0])
        n_rel_types = len(self.stats.get("relationship_counts", {}))

        fig, ax = plt.subplots(figsize=(16, 9))
        ax.set_xlim(0, 16)
        ax.set_ylim(0, 9)
        ax.axis("off")

        # Title
        ax.text(8, 8.3, "ADNI Knowledge Graph — Summary Dashboard", fontsize=20,
                ha="center", va="center", fontweight="bold")

        # Key metrics boxes
        metrics = [
            (2, 6.8, self._fmt(total_nodes), "Total Nodes", "#3498db"),
            (5.5, 6.8, self._fmt(total_rels), "Total Relationships", "#2ecc71"),
            (9, 6.8, str(n_labels), "Node Types", "#e74c3c"),
            (12.5, 6.8, str(n_rel_types), "Relationship Types", "#9b59b6"),
        ]
        for x, y, val, label, color in metrics:
            ax.add_patch(plt.Rectangle((x - 1.3, y - 0.6), 2.6, 1.2,
                                       facecolor=color, alpha=0.15, edgecolor=color, linewidth=2,
                                       transform=ax.transData, zorder=2))
            ax.text(x, y + 0.15, val, fontsize=22, ha="center", va="center",
                    fontweight="bold", color=color)
            ax.text(x, y - 0.3, label, fontsize=10, ha="center", va="center", color="#555")

        # Clinical data summary
        clinical = [
            ("Patients", n_patients, "ADNI participants across 5 cohorts"),
            ("Visits", n_visits, "Longitudinal timepoints (bl to m96)"),
            ("Diagnoses", n_diagnoses, "CN, MCI, AD classifications"),
            ("Medical Images", n_images, "MRI + PET scans (lossless)"),
            ("Ontology Concepts", n_ontology, "SNOMED, LOINC, UBERON, ICD-10, HPO"),
        ]

        y_start = 5.0
        ax.text(1, y_start + 0.3, "Clinical Data", fontsize=13, fontweight="bold", color="#2c3e50")
        for i, (name, count, desc) in enumerate(clinical):
            y = y_start - i * 0.55
            ax.text(1.5, y, f"{name}:", fontsize=11, fontweight="bold", color="#333")
            ax.text(4.5, y, f"{count:,}", fontsize=11, color="#3498db")
            ax.text(6, y, desc, fontsize=9, color="#777")

        # Node category breakdown
        ax.text(1, 2.0, "Node Categories", fontsize=13, fontweight="bold", color="#2c3e50")
        for i, (cat_name, cat_info) in enumerate(NODE_CATEGORIES.items()):
            y = 1.5 - i * 0.4
            if y < -1.5:
                break
            cat_count = sum(self.stats.get("node_counts", {}).get(n, 0) for n in cat_info["nodes"])
            if cat_count > 0:
                ax.add_patch(plt.Rectangle((1.2, y - 0.12), 0.3, 0.24,
                                           facecolor=cat_info["color"], edgecolor="none"))
                ax.text(1.8, y, f"{cat_name}: {self._fmt(cat_count)}", fontsize=9, va="center")
                ax.text(6, y, cat_info["desc"], fontsize=8, va="center", color="#777")

        self._save(fig, "14_kg_summary_dashboard")

    # ── 15. Relationship Schema ───────────────────────────────────────

    def _fig15_relationship_schema(self):
        logger.info("[15/15] Relationship schema explanation...")
        rows = self._query("""
            MATCH (a)-[r]->(b)
            WITH labels(a)[0] AS src, type(r) AS rel, labels(b)[0] AS tgt, count(*) AS cnt
            WHERE cnt > 100
            RETURN src, rel, tgt, cnt
            ORDER BY cnt DESC
            LIMIT 30
        """)
        if not rows:
            return

        self.stats["relationship_schema"] = [
            {"source": r["src"], "relationship": r["rel"], "target": r["tgt"], "count": r["cnt"]}
            for r in rows
        ]

        fig, ax = plt.subplots(figsize=(16, max(8, len(rows) * 0.4)))
        ax.set_xlim(0, 10)
        ax.set_ylim(-len(rows), 1)
        ax.axis("off")

        ax.text(5, 0.5, "Knowledge Graph — Relationship Schema (Top 30 by Count)",
                fontsize=14, ha="center", va="center", fontweight="bold")

        # Headers
        ax.text(0.3, -0.2, "Source Node", fontsize=10, fontweight="bold", color="#555")
        ax.text(3.3, -0.2, "Relationship", fontsize=10, fontweight="bold", color="#555")
        ax.text(6.3, -0.2, "Target Node", fontsize=10, fontweight="bold", color="#555")
        ax.text(9.0, -0.2, "Count", fontsize=10, fontweight="bold", color="#555")

        for i, r in enumerate(rows):
            y = -(i + 1)
            bg = "#f8f9fa" if i % 2 == 0 else "white"
            ax.add_patch(plt.Rectangle((0.1, y - 0.35), 9.8, 0.7,
                                       facecolor=bg, edgecolor="none"))

            src_color = _get_node_color(r["src"])
            tgt_color = _get_node_color(r["tgt"])

            ax.add_patch(plt.Rectangle((0.1, y - 0.15), 0.15, 0.3,
                                       facecolor=src_color, edgecolor="none"))
            ax.text(0.4, y, r["src"], fontsize=9, va="center")

            # Arrow
            ax.annotate("", xy=(5.8, y), xytext=(3, y),
                        arrowprops=dict(arrowstyle="->", color="#888", lw=1.2))
            ax.text(4.4, y + 0.15, r["rel"], fontsize=8, ha="center", va="center",
                    color="#555", fontstyle="italic")

            ax.add_patch(plt.Rectangle((6.1, y - 0.15), 0.15, 0.3,
                                       facecolor=tgt_color, edgecolor="none"))
            ax.text(6.4, y, r["tgt"], fontsize=9, va="center")

            ax.text(9.2, y, self._fmt(r["cnt"]), fontsize=9, va="center", color="#3498db")

        self._save(fig, "15_relationship_schema")

    # ══════════════════════════════════════════════════════════════════
    # Mermaid Diagrams
    # ══════════════════════════════════════════════════════════════════

    def _mermaid_kg_schema(self):
        logger.info("\n[Mermaid] KG Schema diagram...")
        rows = self._query("""
            MATCH (a)-[r]->(b)
            WITH labels(a)[0] AS src, type(r) AS rel, labels(b)[0] AS tgt, count(*) AS cnt
            WHERE cnt > 500
            RETURN src, rel, tgt, cnt
            ORDER BY cnt DESC
            LIMIT 40
        """)
        if not rows:
            return

        lines = ["graph LR"]
        seen_nodes = set()
        seen_edges = set()

        for r in rows:
            src, rel, tgt = r["src"], r["rel"], r["tgt"]
            edge_key = f"{src}-{rel}-{tgt}"
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            # Style nodes by category
            if src not in seen_nodes:
                cat = _get_node_category(src)
                lines.append(f"    {src}[{src}]")
                seen_nodes.add(src)
            if tgt not in seen_nodes:
                cat = _get_node_category(tgt)
                lines.append(f"    {tgt}[{tgt}]")
                seen_nodes.add(tgt)

            cnt_str = self._fmt(r["cnt"])
            lines.append(f"    {src} -->|{rel}<br/>{cnt_str}| {tgt}")

        # Add style classes
        lines.append("")
        for cat_name, cat_info in NODE_CATEGORIES.items():
            class_name = cat_name.replace(" ", "").replace("&", "")
            for node in cat_info["nodes"]:
                if node in seen_nodes:
                    lines.append(f"    style {node} fill:{cat_info['color']},color:white,stroke:{cat_info['color']}")

        mermaid = "\n".join(lines)
        self._save_mermaid(mermaid, "mermaid_kg_schema")

    def _mermaid_data_flow(self):
        logger.info("[Mermaid] Data flow diagram...")
        mermaid = textwrap.dedent("""\
        graph TD
            subgraph "Data Sources"
                ADNI["ADNI IDA Portal<br/>180+ CSV Tables"]
                MRI["MRI DICOM Files"]
                PET["PET DICOM Files"]
            end

            subgraph "ETL Pipeline (29 Steps)"
                S1["Step 1: Database Setup<br/>(Neo4j + Elasticsearch)"]
                S2["Step 2: Load 108 CSV Tables"]
                S3["Step 3: Create Patient Nodes<br/>(2,638 participants)"]
                S4["Step 4: Family Extraction"]
                S5["Step 5: Image Processing<br/>(Lossless TIFF/PNG/J2K)"]
                S6["Step 6-8: Clinical Findings<br/>& Relationships"]
                S9["Step 9-16: Enhancement<br/>(EDA, Metrics, Queries)"]
                S17["Step 17-20: Ontology Migration<br/>(SNOMED, LOINC, UBERON, ICD-10)"]
                S21["Step 21-23: Causal Discovery<br/>(PC, FCI, GES algorithms)"]
                S24["Step 24-28: Validation<br/>(AlzKB, DoWhy, Figures)"]
                S29["Step 29: KG EDA<br/>(Publication Figures)"]
            end

            subgraph "Storage Layer"
                NEO4J[("Neo4j 5.24<br/>Knowledge Graph<br/>407K+ nodes")]
                ES[("Elasticsearch<br/>Metadata Search<br/>5 indices")]
                FS[("File System<br/>Lossless Images<br/>TIFF/PNG/J2K")]
            end

            ADNI --> S1
            MRI --> S5
            PET --> S5
            S1 --> S2 --> S3 --> S4
            S4 --> S5 --> S6 --> S9
            S9 --> S17 --> S21 --> S24 --> S29
            S3 --> NEO4J
            S5 --> ES
            S5 --> FS
            S6 --> NEO4J
            S17 --> NEO4J
            S21 --> NEO4J

            style ADNI fill:#3498db,color:white
            style MRI fill:#1abc9c,color:white
            style PET fill:#1abc9c,color:white
            style NEO4J fill:#2ecc71,color:white
            style ES fill:#e67e22,color:white
            style FS fill:#95a5a6,color:white
        """)
        self._save_mermaid(mermaid, "mermaid_data_flow")

    def _mermaid_ontology_layer(self):
        logger.info("[Mermaid] Ontology layer diagram...")
        mermaid = textwrap.dedent("""\
        graph TD
            subgraph "Data Nodes (ADNI)"
                P["Patient<br/>(2,638)"]
                V["Visit<br/>(30,267)"]
                DX["Diagnosis<br/>(25,946)"]
                CA["CognitiveAssessment<br/>(65,345)"]
                BIO["Biomarker<br/>(12,008)"]
                BR["BrainRegion<br/>(12)"]
            end

            subgraph "Ontology Layer (OntologyConcept)"
                SNOMED["SNOMED-CT<br/>(18 concepts)<br/>Disease hierarchy"]
                LOINC["LOINC<br/>(10 concepts)<br/>Lab test codes"]
                UBERON["UBERON<br/>(14 concepts)<br/>Brain anatomy"]
                ICD10["ICD-10<br/>(5 concepts)<br/>WHO classification"]
                HPO["HPO<br/>(5 concepts)<br/>Phenotype terms"]
            end

            subgraph "Semantic Relationships"
                DX -->|"MAPS_TO<br/>25,946"| SNOMED
                DX -->|"CLASSIFIED_AS<br/>25,946"| ICD10
                CA -->|"MAPS_TO<br/>65,345"| LOINC
                BIO -->|"MAPS_TO<br/>9,467"| LOINC
                BR -->|"MAPS_TO<br/>12"| UBERON
                SNOMED -->|"IS_A"| SNOMED
                UBERON -->|"IS_A"| UBERON
                HPO -->|"IS_A"| HPO
            end

            P -->|"HAS_VISIT"| V
            V -->|"HAS_DIAGNOSIS"| DX
            V -->|"HAS_COGNITIVE_ASSESSMENT"| CA
            V -->|"HAS_BIOMARKER"| BIO

            style P fill:#3498db,color:white
            style V fill:#2ecc71,color:white
            style DX fill:#e74c3c,color:white
            style CA fill:#9b59b6,color:white
            style BIO fill:#e74c3c,color:white
            style BR fill:#f39c12,color:white
            style SNOMED fill:#2980b9,color:white
            style LOINC fill:#2980b9,color:white
            style UBERON fill:#2980b9,color:white
            style ICD10 fill:#2980b9,color:white
            style HPO fill:#2980b9,color:white
        """)
        self._save_mermaid(mermaid, "mermaid_ontology_layer")


# ── Pipeline entry point ──────────────────────────────────────────────

def execute_kg_eda(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                   output_dir: str = "outputs/eda_figures") -> Dict[str, Any]:
    """Execute Knowledge Graph EDA and generate publication-quality figures."""
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)
    try:
        eda = KnowledgeGraphEDA(connector, output_dir=output_dir)
        return eda.execute()
    finally:
        connector.close()
