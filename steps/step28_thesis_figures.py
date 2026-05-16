"""
Step 28 – Thesis Figures
========================
Generates publication-quality figures for thesis defense using
graphviz, matplotlib, and networkx.

Output
------
All figures in thesis_output/ as SVG + PNG:
  - kg_schema.{svg,png}        — KG schema diagram
  - causal_overlay.{svg,png}   — Causal graph on schema
  - lpg_vs_kg_query.{svg,png}  — Before/after query comparison
  - atn_cascade.{svg,png}      — ATN biomarker cascade
  - icd10_tree.{svg,png}       — ICD-10 hierarchy tree
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

import graphviz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# THEME
# ────────────────────────────────────────────────────────────────

# Color palette — AD-research inspired
COLORS = {
    'Patient':            '#4A90D9',
    'Visit':              '#6CB4EE',
    'Diagnosis':          '#E74C3C',
    'CognitiveAssessment':'#27AE60',
    'Biomarker':          '#F39C12',
    'ImagingStudy':       '#9B59B6',
    'VolumetricMeasure':  '#1ABC9C',
    'PETBinding':         '#E67E22',
    'GeneticProfile':     '#3498DB',
    'ATNProfile':         '#2C3E50',
    'DiseaseStage':       '#C0392B',
    'ClinicalFinding':    '#16A085',
    'OntologyConcept':    '#8E44AD',
    'AlzKBConcept':       '#D35400',
    'CausalVariable':     '#2980B9',
    'default':            '#95A5A6',
}

REL_COLORS = {
    'HAS_VISIT':       '#7F8C8D',
    'HAS_DIAGNOSIS':   '#E74C3C',
    'MAPS_TO':         '#8E44AD',
    'CAUSES':          '#C0392B',
    'SAME_AS':         '#D35400',
    'HAS_CHILD':       '#2C3E50',
    'default':         '#BDC3C7',
}

FONT_NAME = 'Helvetica'


# ────────────────────────────────────────────────────────────────
# FIGURE 1: KG Schema Diagram
# ────────────────────────────────────────────────────────────────

def _create_schema_diagram(output_dir: Path) -> None:
    """Generate the complete KG schema diagram."""
    g = graphviz.Digraph('ADNI_KG_Schema', format='svg',
                         graph_attr={
                             'rankdir': 'TB',
                             'fontname': FONT_NAME,
                             'fontsize': '14',
                             'bgcolor': '#FAFAFA',
                             'pad': '0.5',
                             'nodesep': '0.8',
                             'ranksep': '1.0',
                             'label': 'ADNI Knowledge Graph Schema',
                             'labelloc': 't',
                             'fontsize': '18',
                         })

    # Node definitions
    nodes = {
        'Patient':             {'shape': 'box', 'style': 'filled,rounded'},
        'Visit':               {'shape': 'box', 'style': 'filled,rounded'},
        'Diagnosis':           {'shape': 'box', 'style': 'filled,rounded'},
        'CognitiveAssessment': {'shape': 'box', 'style': 'filled,rounded'},
        'Biomarker':           {'shape': 'box', 'style': 'filled,rounded'},
        'ImagingStudy':        {'shape': 'box', 'style': 'filled,rounded'},
        'VolumetricMeasure':   {'shape': 'box', 'style': 'filled,rounded'},
        'PETBinding':          {'shape': 'box', 'style': 'filled,rounded'},
        'GeneticProfile':      {'shape': 'box', 'style': 'filled,rounded'},
        'ATNProfile':          {'shape': 'box', 'style': 'filled,rounded'},
        'DiseaseStage':        {'shape': 'box', 'style': 'filled,rounded'},
        'ClinicalFinding':     {'shape': 'box', 'style': 'filled,rounded'},
        'OntologyConcept':     {'shape': 'hexagon', 'style': 'filled'},
        'AlzKBConcept':        {'shape': 'hexagon', 'style': 'filled'},
        'CausalVariable':      {'shape': 'diamond', 'style': 'filled'},
    }

    for name, attrs in nodes.items():
        color = COLORS.get(name, COLORS['default'])
        g.node(name, label=name,
               fillcolor=color, fontcolor='white',
               fontname=FONT_NAME, fontsize='11',
               **attrs)

    # Clinical layer relationships
    edges = [
        ('Patient', 'Visit',               'HAS_VISIT'),
        ('Visit',   'Diagnosis',           'HAS_DIAGNOSIS'),
        ('Visit',   'CognitiveAssessment', 'HAS_COGNITIVE_ASSESSMENT'),
        ('Visit',   'Biomarker',           'HAS_BIOMARKER'),
        ('Visit',   'ImagingStudy',        'HAS_IMAGING_STUDY'),
        ('Visit',   'VolumetricMeasure',   'HAS_VOLUMETRIC_MEASURE'),
        ('Visit',   'PETBinding',          'HAS_PET_BINDING'),
        ('Patient', 'GeneticProfile',      'HAS_GENETIC_PROFILE'),
        ('Patient', 'ATNProfile',          'HAS_ATN_PROFILE'),
        ('Patient', 'DiseaseStage',        'HAS_DISEASE_STAGE'),
        ('Visit',   'ClinicalFinding',     'HAS_CLINICAL_FINDING'),
        # Semantic layer
        ('Diagnosis',          'OntologyConcept', 'MAPS_TO'),
        ('CognitiveAssessment','OntologyConcept', 'MAPS_TO'),
        ('Biomarker',          'OntologyConcept', 'MAPS_TO'),
        ('VolumetricMeasure',  'OntologyConcept', 'MAPS_TO'),
        ('PETBinding',         'OntologyConcept', 'MAPS_TO'),
        ('OntologyConcept',    'OntologyConcept', 'HAS_CHILD'),
        # Integration layer
        ('AlzKBConcept',       'OntologyConcept', 'SAME_AS'),
        ('CausalVariable',     'OntologyConcept', 'MAPS_TO'),
        ('CausalVariable',     'CausalVariable',  'CAUSES'),
    ]

    for src, tgt, label in edges:
        color = REL_COLORS.get(label, REL_COLORS['default'])
        style = 'bold' if label in ('CAUSES', 'MAPS_TO', 'SAME_AS') else 'solid'
        g.edge(src, tgt, label=label, fontsize='9', fontname=FONT_NAME,
               color=color, fontcolor=color, style=style)

    # Render both SVG and PNG
    svg_path = str(output_dir / 'kg_schema')
    g.render(svg_path, cleanup=True)

    g.format = 'png'
    g.render(svg_path, cleanup=True)

    logger.info(f"  Created: kg_schema.svg + kg_schema.png")


# ────────────────────────────────────────────────────────────────
# FIGURE 2: Causal Graph Overlay
# ────────────────────────────────────────────────────────────────

def _create_causal_overlay(output_dir: Path, causal_dir: Path) -> None:
    """Generate a causal graph overlaid on the schema."""
    consensus_path = causal_dir / 'consensus_edges.json'
    if not consensus_path.exists():
        logger.info("  Skipping causal overlay — no consensus_edges.json")
        return

    with open(consensus_path) as f:
        edges = json.load(f)

    if not edges:
        logger.info("  Skipping causal overlay — empty consensus")
        return

    # Build networkx graph
    G = nx.DiGraph()
    for e in edges:
        src = e.get('source', '')
        tgt = e.get('target', '')
        conf = e.get('confidence', 0.5)
        algos = e.get('algorithms', [])
        G.add_edge(src, tgt, confidence=conf,
                   algorithms=', '.join(algos) if isinstance(algos, list) else str(algos))

    fig, ax = plt.subplots(1, 1, figsize=(14, 10))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#1a1a2e')

    # Layout
    pos = nx.spring_layout(G, seed=42, k=2.0)

    # Node colors by prefix
    node_colors = []
    for node in G.nodes():
        if node.startswith('BIO_'):
            node_colors.append('#F39C12')
        elif node.startswith('COG_'):
            node_colors.append('#27AE60')
        elif node.startswith('VOL_'):
            node_colors.append('#1ABC9C')
        elif node.startswith('PET_'):
            node_colors.append('#E67E22')
        elif node.startswith('DX'):
            node_colors.append('#E74C3C')
        elif node in ('age', 'education', 'gender', 'apoe_e4_count'):
            node_colors.append('#4A90D9')
        elif node.startswith('ATN_'):
            node_colors.append('#2C3E50')
        else:
            node_colors.append('#95A5A6')

    # Draw
    nx.draw_networkx_nodes(G, pos, ax=ax, node_size=1200,
                           node_color=node_colors, alpha=0.9,
                           edgecolors='white', linewidths=1.5)
    nx.draw_networkx_labels(G, pos, ax=ax, font_size=7,
                            font_color='white', font_weight='bold')

    # Edge widths by confidence
    widths = [G[u][v].get('confidence', 0.5) * 3 + 0.5
              for u, v in G.edges()]
    nx.draw_networkx_edges(G, pos, ax=ax, width=widths,
                           edge_color='#E74C3C', alpha=0.7,
                           arrows=True, arrowsize=15,
                           connectionstyle='arc3,rad=0.1')

    # Legend
    legend_items = [
        mpatches.Patch(color='#4A90D9', label='Demographics'),
        mpatches.Patch(color='#F39C12', label='CSF Biomarkers'),
        mpatches.Patch(color='#27AE60', label='Cognitive'),
        mpatches.Patch(color='#1ABC9C', label='Volumetric'),
        mpatches.Patch(color='#E67E22', label='PET'),
        mpatches.Patch(color='#E74C3C', label='Diagnosis'),
        mpatches.Patch(color='#2C3E50', label='ATN'),
    ]
    ax.legend(handles=legend_items, loc='upper left',
              fontsize=8, facecolor='#16213e', edgecolor='white',
              labelcolor='white', framealpha=0.8)

    ax.set_title('Causal Discovery — Consensus Graph',
                 color='white', fontsize=16, fontweight='bold', pad=15)
    ax.axis('off')

    plt.tight_layout()
    fig.savefig(output_dir / 'causal_overlay.svg', format='svg',
                facecolor=fig.get_facecolor(), dpi=150)
    fig.savefig(output_dir / 'causal_overlay.png', format='png',
                facecolor=fig.get_facecolor(), dpi=150)
    plt.close(fig)
    logger.info("  Created: causal_overlay.svg + causal_overlay.png")


# ────────────────────────────────────────────────────────────────
# FIGURE 3: LPG vs KG Query Comparison
# ────────────────────────────────────────────────────────────────

def _draw_node(ax, x, y, label, color, width=1.6, height=0.55):
    """Draw a rounded-rectangle node with centred label."""
    from matplotlib.patches import FancyBboxPatch
    box = FancyBboxPatch(
        (x - width / 2, y - height / 2), width, height,
        boxstyle="round,pad=0.12",
        facecolor=color, edgecolor='#333333', linewidth=1.4,
        zorder=3,
    )
    ax.add_patch(box)
    ax.text(x, y, label, ha='center', va='center',
            fontsize=9, fontweight='bold', color='white', zorder=4)
    return (x, y)


def _draw_edge(ax, start, end, label, style='solid', color='#555555',
               connectionstyle='arc3,rad=0.0'):
    """Draw a labelled arrow between two (x, y) positions."""
    ax.annotate(
        '', xy=end, xytext=start,
        arrowprops=dict(
            arrowstyle='-|>',
            color=color,
            lw=1.5,
            linestyle=style,
            connectionstyle=connectionstyle,
            shrinkA=12, shrinkB=12,
        ),
        zorder=2,
    )
    mid_x = (start[0] + end[0]) / 2
    mid_y = (start[1] + end[1]) / 2
    ax.text(mid_x, mid_y + 0.18, label, ha='center', va='bottom',
            fontsize=7, fontstyle='italic', color=color,
            bbox=dict(boxstyle='round,pad=0.15', facecolor='white',
                      edgecolor='none', alpha=0.85),
            zorder=5)


def _create_lpg_vs_kg(output_dir: Path) -> None:
    """Generate before/after visual graph comparison diagram."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    fig.patch.set_facecolor('white')

    # ── Colour palette ──
    C_PATIENT   = '#2980B9'   # blue
    C_VISIT     = '#7F8C8D'   # gray
    C_DIAGNOSIS = '#C0392B'   # red
    C_ONTOLOGY  = '#8E44AD'   # purple
    C_ALZKB     = '#E67E22'   # orange
    C_CAUSAL    = '#27AE60'   # green

    # ================================================================
    # LEFT PANEL — LPG (Before)
    # ================================================================
    ax1.set_xlim(-1, 7)
    ax1.set_ylim(-1.5, 5.5)
    ax1.set_aspect('equal')
    ax1.axis('off')
    ax1.set_facecolor('white')

    ax1.set_title('Property Graph (LPG)', fontsize=14,
                  fontweight='bold', color='#333333', pad=12)

    # Nodes — simple linear chain
    p1 = _draw_node(ax1, 1.0, 3.5, 'Patient',   C_PATIENT)
    v1 = _draw_node(ax1, 3.0, 3.5, 'Visit',     C_VISIT)
    d1 = _draw_node(ax1, 5.0, 3.5, 'Diagnosis', C_DIAGNOSIS)

    # Edges
    _draw_edge(ax1, p1, v1, 'HAS_VISIT')
    _draw_edge(ax1, v1, d1, 'HAS_DIAGNOSIS')

    # Faded "dead-end" indicator
    ax1.text(5.0, 2.6, '(no further links)',
             ha='center', va='top', fontsize=8,
             color='#AAAAAA', fontstyle='italic')

    # Limitation bullets
    limitations = [
        'Text-matching only (no coded semantics)',
        'No ontology or cross-graph traversal',
        'No causal reasoning capability',
    ]
    for i, txt in enumerate(limitations):
        ax1.text(0.5, 0.7 - i * 0.45, f'\u2716  {txt}',
                 ha='center', va='center', fontsize=9.5, color='#C0392B',
                 transform=ax1.transAxes)

    # ================================================================
    # RIGHT PANEL — KG (After)
    # ================================================================
    ax2.set_xlim(-1.5, 8.5)
    ax2.set_ylim(-2.0, 6.0)
    ax2.set_aspect('equal')
    ax2.axis('off')
    ax2.set_facecolor('white')

    ax2.set_title('Knowledge Graph (KG)', fontsize=14,
                  fontweight='bold', color='#333333', pad=12)

    # Core chain (same as LPG)
    p2 = _draw_node(ax2, 0.5, 4.0, 'Patient',   C_PATIENT)
    v2 = _draw_node(ax2, 2.8, 4.0, 'Visit',     C_VISIT)
    d2 = _draw_node(ax2, 5.1, 4.0, 'Diagnosis', C_DIAGNOSIS)

    _draw_edge(ax2, p2, v2, 'HAS_VISIT')
    _draw_edge(ax2, v2, d2, 'HAS_DIAGNOSIS')

    # Ontology layer
    o2 = _draw_node(ax2, 5.1, 2.2, 'OntologyConcept', C_ONTOLOGY,
                    width=2.0)
    _draw_edge(ax2, d2, o2, 'MAPS_TO', color=C_ONTOLOGY)

    # AlzKB bridge
    a2 = _draw_node(ax2, 2.2, 2.2, 'AlzKBConcept', C_ALZKB,
                    width=1.9)
    _draw_edge(ax2, o2, a2, 'SAME_AS', color=C_ALZKB,
               connectionstyle='arc3,rad=0.0')

    # Causal variables
    cv1 = _draw_node(ax2, 1.5, 0.3, 'CausalVar\n(Abeta)', C_CAUSAL,
                     width=1.7, height=0.65)
    cv2 = _draw_node(ax2, 5.1, 0.3, 'CausalVar\n(Tau)', C_CAUSAL,
                     width=1.7, height=0.65)
    _draw_edge(ax2, cv1, cv2, 'CAUSES', style='dashed', color=C_CAUSAL)

    # Capability bullets
    capabilities = [
        'SNOMED / LOINC coded semantics',
        'Cross-graph AlzKB integration',
        'Discovered causal edges (DoWhy)',
    ]
    for i, txt in enumerate(capabilities):
        ax2.text(0.5, 0.78 - i * 0.06, f'\u2714  {txt}',
                 ha='center', va='center', fontsize=9.5, color=C_CAUSAL,
                 transform=ax2.transAxes)

    # ── Global title ──
    fig.suptitle(
        u'Property Graph \u2192 Knowledge Graph: Query Evolution',
        fontsize=18, fontweight='bold', y=0.97, color='#222222',
    )
    plt.tight_layout(rect=[0, 0, 1, 0.93])

    fig.savefig(output_dir / 'lpg_vs_kg_query.svg', format='svg', dpi=150)
    fig.savefig(output_dir / 'lpg_vs_kg_query.png', format='png', dpi=150)
    plt.close(fig)
    logger.info("  Created: lpg_vs_kg_query.svg + lpg_vs_kg_query.png")


# ────────────────────────────────────────────────────────────────
# FIGURE 4: ATN Biomarker Cascade
# ────────────────────────────────────────────────────────────────

def _create_atn_cascade(output_dir: Path) -> None:
    """ATN framework with causal annotations."""
    g = graphviz.Digraph('ATN_Cascade', format='svg',
                         graph_attr={
                             'rankdir': 'LR',
                             'fontname': FONT_NAME,
                             'bgcolor': '#1a1a2e',
                             'pad': '0.5',
                             'nodesep': '1.2',
                             'ranksep': '1.5',
                             'label': 'ATN Biomarker Cascade with Causal Annotations',
                             'labelloc': 't',
                             'fontsize': '16',
                             'fontcolor': 'white',
                         })

    # A — Amyloid
    with g.subgraph(name='cluster_A') as c:
        c.attr(label='A (Amyloid)', style='dashed', color='#F39C12',
               fontcolor='#F39C12', fontsize='14')
        c.node('APOE4', 'APOE ε4', shape='ellipse', style='filled',
               fillcolor='#4A90D9', fontcolor='white', fontname=FONT_NAME)
        c.node('CSF_AB42', 'CSF Aβ42', shape='box', style='filled,rounded',
               fillcolor='#F39C12', fontcolor='white', fontname=FONT_NAME)
        c.node('AV45', 'Amyloid PET\n(AV45 SUVR)', shape='box', style='filled,rounded',
               fillcolor='#E67E22', fontcolor='white', fontname=FONT_NAME)

    # T — Tau
    with g.subgraph(name='cluster_T') as c:
        c.attr(label='T (Tau)', style='dashed', color='#E74C3C',
               fontcolor='#E74C3C', fontsize='14')
        c.node('CSF_TAU', 'CSF Total Tau', shape='box', style='filled,rounded',
               fillcolor='#E74C3C', fontcolor='white', fontname=FONT_NAME)
        c.node('CSF_PTAU', 'CSF p-Tau', shape='box', style='filled,rounded',
               fillcolor='#C0392B', fontcolor='white', fontname=FONT_NAME)

    # N — Neurodegeneration
    with g.subgraph(name='cluster_N') as c:
        c.attr(label='N (Neurodegeneration)', style='dashed', color='#1ABC9C',
               fontcolor='#1ABC9C', fontsize='14')
        c.node('Hippocampus', 'Hippocampal\nVolume', shape='box', style='filled,rounded',
               fillcolor='#1ABC9C', fontcolor='white', fontname=FONT_NAME)
        c.node('Entorhinal', 'Entorhinal\nCortex', shape='box', style='filled,rounded',
               fillcolor='#16A085', fontcolor='white', fontname=FONT_NAME)
        c.node('FDG', 'FDG PET\n(Metabolism)', shape='box', style='filled,rounded',
               fillcolor='#E67E22', fontcolor='white', fontname=FONT_NAME)

    # Outcome
    with g.subgraph(name='cluster_outcome') as c:
        c.attr(label='Clinical Outcome', style='dashed', color='#27AE60',
               fontcolor='#27AE60', fontsize='14')
        c.node('MMSE', 'MMSE', shape='box', style='filled,rounded',
               fillcolor='#27AE60', fontcolor='white', fontname=FONT_NAME)
        c.node('ADAS13', 'ADAS-Cog 13', shape='box', style='filled,rounded',
               fillcolor='#2ECC71', fontcolor='white', fontname=FONT_NAME)
        c.node('DX', 'Diagnosis\n(CN→MCI→AD)', shape='box', style='filled,rounded',
               fillcolor='#9B59B6', fontcolor='white', fontname=FONT_NAME)

    # Causal edges (bold red = discovered, dashed gray = hypothesized)
    causal_edges = [
        ('APOE4',      'CSF_AB42',    'CAUSES', 'bold', '#E74C3C'),
        ('CSF_AB42',   'CSF_TAU',     'CAUSES', 'bold', '#E74C3C'),
        ('CSF_AB42',   'CSF_PTAU',    'CAUSES', 'bold', '#E74C3C'),
        ('CSF_TAU',    'Hippocampus', 'CAUSES', 'bold', '#E74C3C'),
        ('CSF_PTAU',   'Hippocampus', 'CAUSES', 'bold', '#E74C3C'),
        ('Hippocampus','MMSE',        'CAUSES', 'bold', '#E74C3C'),
        ('Hippocampus','ADAS13',      'CAUSES', 'dashed', '#7F8C8D'),
        ('AV45',       'CSF_AB42',    'reflects', 'dotted', '#95A5A6'),
        ('MMSE',       'DX',          'defines', 'dotted', '#95A5A6'),
    ]

    for src, tgt, label, style, color in causal_edges:
        g.edge(src, tgt, label=label, style=style, color=color,
               fontcolor=color, fontsize='9', fontname=FONT_NAME,
               penwidth='2.0' if style == 'bold' else '1.0')

    svg_path = str(output_dir / 'atn_cascade')
    g.render(svg_path, cleanup=True)
    g.format = 'png'
    g.render(svg_path, cleanup=True)
    logger.info("  Created: atn_cascade.svg + atn_cascade.png")


# ────────────────────────────────────────────────────────────────
# FIGURE 5: ICD-10 Hierarchy Tree
# ────────────────────────────────────────────────────────────────

def _create_icd10_tree(output_dir: Path) -> None:
    """Generate ICD-10 hierarchy tree (AD-relevant subset)."""
    g = graphviz.Digraph('ICD10_Tree', format='svg',
                         graph_attr={
                             'rankdir': 'TB',
                             'fontname': FONT_NAME,
                             'bgcolor': '#FAFAFA',
                             'nodesep': '0.5',
                             'ranksep': '0.8',
                             'label': 'ICD-10 Hierarchy — Alzheimer Disease Codes',
                             'labelloc': 't',
                             'fontsize': '16',
                         })

    # ICD-10 AD codes hierarchy
    icd_nodes = [
        ('G', 'G\nDiseases of the\nnervous system', '#2C3E50'),
        ('G30', 'G30\nAlzheimer disease', '#E74C3C'),
        ('G30.0', 'G30.0\nEarly onset', '#C0392B'),
        ('G30.1', 'G30.1\nLate onset', '#E74C3C'),
        ('G30.8', 'G30.8\nOther Alzheimer', '#D35400'),
        ('G30.9', 'G30.9\nUnspecified', '#BDC3C7'),
        ('F', 'F\nMental and behavioural\ndisorders', '#2C3E50'),
        ('F00', 'F00\nDementia in\nAlzheimer disease', '#9B59B6'),
        ('F00.0', 'F00.0\nEarly onset\n(type 2)', '#8E44AD'),
        ('F00.1', 'F00.1\nLate onset\n(type 1)', '#9B59B6'),
        ('F00.2', 'F00.2\nAtypical/mixed', '#7D3C98'),
        ('F00.9', 'F00.9\nUnspecified', '#BDC3C7'),
    ]

    for node_id, label, color in icd_nodes:
        g.node(node_id, label=label, shape='box', style='filled,rounded',
               fillcolor=color, fontcolor='white',
               fontname=FONT_NAME, fontsize='9')

    edges = [
        ('G', 'G30'),
        ('G30', 'G30.0'), ('G30', 'G30.1'),
        ('G30', 'G30.8'), ('G30', 'G30.9'),
        ('F', 'F00'),
        ('F00', 'F00.0'), ('F00', 'F00.1'),
        ('F00', 'F00.2'), ('F00', 'F00.9'),
    ]

    for src, tgt in edges:
        g.edge(src, tgt, color='#2C3E50', penwidth='1.5')

    # Cross-reference dotted line
    g.edge('G30', 'F00', style='dashed', color='#95A5A6',
           label='ICD cross-ref', fontsize='8', fontcolor='#95A5A6')

    svg_path = str(output_dir / 'icd10_tree')
    g.render(svg_path, cleanup=True)
    g.format = 'png'
    g.render(svg_path, cleanup=True)
    logger.info("  Created: icd10_tree.svg + icd10_tree.png")


# ────────────────────────────────────────────────────────────────
# Figure generator class
# ────────────────────────────────────────────────────────────────

class ThesisFigures:
    """Generates all thesis figures."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.thesis_dir = Path('thesis_output')
        self.thesis_dir.mkdir(parents=True, exist_ok=True)
        self.causal_dir = Path(config.get('causal', {}).get('output_dir', 'causal'))

    def execute(self) -> Dict[str, Any]:
        """Main entry-point."""
        logger.info("=" * 60)
        logger.info("STEP 28 — Thesis Figures")
        logger.info("=" * 60)

        results = {
            'step': 28,
            'status': 'started',
            'timestamp': __import__('datetime').datetime.now().isoformat(),
            'figures': [],
            'warnings': [],
        }

        figure_tasks = [
            ("kg_schema",      "[1/5] KG Schema Diagram",
             lambda: _create_schema_diagram(self.thesis_dir)),
            ("causal_overlay", "[2/5] Causal Graph Overlay",
             lambda: _create_causal_overlay(self.thesis_dir, self.causal_dir)),
            ("lpg_vs_kg_query","[3/5] LPG vs KG Query Comparison",
             lambda: _create_lpg_vs_kg(self.thesis_dir)),
            ("atn_cascade",    "[4/5] ATN Biomarker Cascade",
             lambda: _create_atn_cascade(self.thesis_dir)),
            ("icd10_tree",     "[5/5] ICD-10 Hierarchy Tree",
             lambda: _create_icd10_tree(self.thesis_dir)),
        ]

        for name, label, task_fn in figure_tasks:
            try:
                logger.info(f"  {label}...")
                task_fn()
                results['figures'].append(name)
            except Exception as e:
                msg = f"{label} failed: {e}"
                logger.warning(f"  ⚠ {msg}")
                results['warnings'].append(msg)
                # For graphviz figures, save the DOT source as fallback
                if 'ExecutableNotFound' in type(e).__name__ or 'dot' in str(e):
                    logger.info(f"    → Graphviz 'dot' not found. "
                                "Install Graphviz system package to render SVG/PNG.")

        if results['figures']:
            results['status'] = 'completed'
            results['output_dir'] = str(self.thesis_dir)
            logger.info(f"✅ Step 28 complete — {len(results['figures'])}/"
                        f"{len(figure_tasks)} figures generated in thesis_output/")
            if results['warnings']:
                logger.info(f"   ({len(results['warnings'])} figures skipped, "
                            "see warnings)")
        else:
            results['status'] = 'failed'
            results['error'] = "No figures could be generated"
            logger.error("Step 28 failed — no figures generated")

        return results



# ────────────────────────────────────────────────────────────────
# CLI + pipeline
# ────────────────────────────────────────────────────────────────

def execute_thesis_figures(config: Dict[str, Any]) -> Dict[str, Any]:
    """Pipeline entry-point for Step 28."""
    generator = ThesisFigures(config)
    return generator.execute()


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

    result = execute_thesis_figures(config)
    print(json.dumps(result, indent=2, default=str))
