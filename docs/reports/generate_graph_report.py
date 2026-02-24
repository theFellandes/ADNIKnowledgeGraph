"""
ADNI Knowledge Graph — LPG to KG Transformation Report Generator
=================================================================
Generates a PDF report with embedded SVG diagrams illustrating the
transformation from a Labeled Property Graph (LPG) to a Knowledge Graph (KG)
completed during Phase 1 (Steps 17-20) on February 24, 2026.

Usage:
    python docs/reports/generate_graph_report.py

Output:
    docs/reports/ADNI_KG_Graph_Classification_Report.pdf
    docs/reports/images/*.svg
"""

import os
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

# ── Paths ────────────────────────────────────────────────────────────
REPORT_DIR = Path(__file__).parent
IMAGES_DIR = REPORT_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════
#  SVG DIAGRAM GENERATION
# ══════════════════════════════════════════════════════════════════════


def _svg_header(width, height, viewbox=None):
    vb = viewbox or f"0 0 {width} {height}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="{vb}">\n'
        f'<defs>\n'
        f'  <style>\n'
        f'    text {{ font-family: "Segoe UI", Arial, sans-serif; }}\n'
        f'    .title {{ font-size: 18px; font-weight: bold; fill: #1a1a2e; }}\n'
        f'    .subtitle {{ font-size: 13px; fill: #555; }}\n'
        f'    .label {{ font-size: 11px; fill: #333; font-weight: 600; }}\n'
        f'    .small {{ font-size: 9px; fill: #666; }}\n'
        f'    .tiny {{ font-size: 8px; fill: #888; }}\n'
        f'    .count {{ font-size: 10px; fill: #0d47a1; font-weight: bold; }}\n'
        f'    .edge-label {{ font-size: 9px; fill: #c62828; font-weight: 600; }}\n'
        f'  </style>\n'
        f'  <marker id="arrowhead" markerWidth="10" markerHeight="7" '
        f'refX="9" refY="3.5" orient="auto">\n'
        f'    <polygon points="0 0, 10 3.5, 0 7" fill="#555"/>\n'
        f'  </marker>\n'
        f'  <marker id="arrowhead-red" markerWidth="10" markerHeight="7" '
        f'refX="9" refY="3.5" orient="auto">\n'
        f'    <polygon points="0 0, 10 3.5, 0 7" fill="#c62828"/>\n'
        f'  </marker>\n'
        f'  <marker id="arrowhead-blue" markerWidth="10" markerHeight="7" '
        f'refX="9" refY="3.5" orient="auto">\n'
        f'    <polygon points="0 0, 10 3.5, 0 7" fill="#1565c0"/>\n'
        f'  </marker>\n'
        f'  <marker id="arrowhead-green" markerWidth="10" markerHeight="7" '
        f'refX="9" refY="3.5" orient="auto">\n'
        f'    <polygon points="0 0, 10 3.5, 0 7" fill="#2e7d32"/>\n'
        f'  </marker>\n'
        f'</defs>\n'
    )


def _rounded_rect(x, y, w, h, fill, stroke="#333", rx=8, opacity=1.0):
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1.5" opacity="{opacity}"/>\n'
    )


def _circle(cx, cy, r, fill, stroke="#333"):
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="1.5"/>\n'
    )


def _text(x, y, content, cls="label", anchor="middle"):
    return f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{content}</text>\n'


def _line(x1, y1, x2, y2, color="#555", width=1.5, marker_end="arrowhead", dashed=False):
    dash = ' stroke-dasharray="5,3"' if dashed else ""
    me = f' marker-end="url(#{marker_end})"' if marker_end else ""
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{color}" stroke-width="{width}"{dash}{me}/>\n'
    )


def _path(d, color="#555", width=1.5, marker_end="arrowhead", dashed=False):
    dash = ' stroke-dasharray="5,3"' if dashed else ""
    me = f' marker-end="url(#{marker_end})"' if marker_end else ""
    return (
        f'<path d="{d}" fill="none" stroke="{color}" '
        f'stroke-width="{width}"{dash}{me}/>\n'
    )


# ────────────────────────────────────────────────────────────────────
# DIAGRAM 1: LPG Before State
# ────────────────────────────────────────────────────────────────────
def generate_lpg_before_svg():
    """Generate SVG showing the ADNI graph BEFORE semantic migration (LPG state)."""
    w, h = 780, 520
    svg = _svg_header(w, h)

    # Title
    svg += _text(390, 30, "ADNI Labeled Property Graph (LPG) — Before Phase 1", "title")
    svg += _text(390, 50, "~407K nodes, ~1.16M relationships | No ontology grounding", "subtitle")

    # ── Patient hub ──
    svg += _circle(390, 180, 42, "#bbdefb", "#1565c0")
    svg += _text(390, 176, "Patient", "label")
    svg += _text(390, 191, "2,638", "count")

    # ── Visit ──
    svg += _circle(180, 300, 36, "#c8e6c9", "#2e7d32")
    svg += _text(180, 296, "Visit", "label")
    svg += _text(180, 311, "30,267", "count")

    # ── Diagnosis ──
    svg += _circle(390, 400, 36, "#ffcdd2", "#c62828")
    svg += _text(390, 396, "Diagnosis", "label")
    svg += _text(390, 411, "25,946", "count")

    # ── CognitiveAssessment ──
    svg += _circle(600, 300, 36, "#fff9c4", "#f9a825")
    svg += _text(600, 296, "CogAssess", "label")
    svg += _text(600, 311, "65,345", "count")

    # ── Biomarker ──
    svg += _circle(100, 180, 34, "#e1bee7", "#7b1fa2")
    svg += _text(100, 176, "Biomarker", "label")
    svg += _text(100, 191, "9,467", "count")

    # ── BrainRegion ──
    svg += _circle(680, 180, 30, "#b2dfdb", "#00695c")
    svg += _text(680, 176, "BrainReg", "label")
    svg += _text(680, 191, "12", "count")

    # ── DiseaseStage ──
    svg += _circle(600, 440, 30, "#ffe0b2", "#e65100")
    svg += _text(600, 436, "DxStage", "label")
    svg += _text(600, 451, "5", "count")

    # ── GeneticProfile ──
    svg += _circle(180, 120, 30, "#d1c4e9", "#4527a0")
    svg += _text(180, 116, "Genetic", "label")
    svg += _text(180, 131, "~2.6K", "count")

    # ── Edges ──
    svg += _line(360, 210, 210, 275, "#1565c0")
    svg += _text(270, 235, "HAS_VISIT", "edge-label")

    svg += _line(195, 330, 360, 385, "#2e7d32")
    svg += _text(260, 365, "HAS_DIAGNOSIS", "edge-label")

    svg += _line(420, 210, 575, 275, "#f9a825")
    svg += _text(520, 235, "HAS_COGNITIVE", "edge-label")

    svg += _line(145, 195, 155, 275, "#7b1fa2")
    svg += _text(115, 245, "HAS_BIO", "edge-label")

    svg += _line(420, 430, 575, 435, "#e65100")
    svg += _text(500, 425, "IN_STAGE", "edge-label")

    svg += _line(340, 155, 210, 130, "#4527a0")
    svg += _text(265, 130, "HAS_GENETIC", "edge-label")

    # ── Properties callout (LPG properties, NO ontology codes) ──
    svg += _rounded_rect(20, 460, 740, 50, "#fff3e0", "#e65100", rx=6)
    svg += _text(390, 480, "LPG Properties: ptid, viscode, diagnosis_code='AD', test_name='MMSE', "
                 "total_score=28", "small")
    svg += _text(390, 496,
                 "NO snomed_code | NO loinc_code | NO uberon_code | NO rdf_type | NO URI on relationships",
                 "tiny")

    svg += '</svg>'
    path = IMAGES_DIR / "01_lpg_before.svg"
    path.write_text(svg, encoding="utf-8")
    return path


# ────────────────────────────────────────────────────────────────────
# DIAGRAM 2: KG After State
# ────────────────────────────────────────────────────────────────────
def generate_kg_after_svg():
    """Generate SVG showing the ADNI graph AFTER semantic migration (KG state)."""
    w, h = 820, 620
    svg = _svg_header(w, h)

    # Title
    svg += _text(410, 28, "ADNI Knowledge Graph (KG) — After Phase 1", "title")
    svg += _text(410, 48, "Ontology-grounded | 52 OntologyConcept nodes | ~127K new semantic edges", "subtitle")

    # ── Patient hub ──
    svg += _circle(410, 160, 42, "#bbdefb", "#1565c0")
    svg += _text(410, 152, "Patient", "label")
    svg += _text(410, 167, "2,638", "count")
    svg += _text(410, 180, "rdf_type: ncit:C16960", "tiny")

    # ── Visit ──
    svg += _circle(190, 280, 36, "#c8e6c9", "#2e7d32")
    svg += _text(190, 272, "Visit", "label")
    svg += _text(190, 287, "30,267", "count")
    svg += _text(190, 300, "rdf_type: ncit:C159705", "tiny")

    # ── Diagnosis ──
    svg += _circle(410, 390, 38, "#ffcdd2", "#c62828")
    svg += _text(410, 378, "Diagnosis", "label")
    svg += _text(410, 393, "25,946", "count")
    svg += _text(410, 406, "snomed: 26929004", "tiny")
    svg += _text(410, 416, "icd10: G30.9", "tiny")

    # ── CognitiveAssessment ──
    svg += _circle(630, 280, 38, "#fff9c4", "#f9a825")
    svg += _text(630, 268, "CogAssess", "label")
    svg += _text(630, 283, "65,345", "count")
    svg += _text(630, 298, "loinc: 72106-8", "tiny")

    # ── Biomarker ──
    svg += _circle(100, 160, 34, "#e1bee7", "#7b1fa2")
    svg += _text(100, 152, "Biomarker", "label")
    svg += _text(100, 167, "9,467", "count")
    svg += _text(100, 180, "loinc: 13967-5", "tiny")

    # ── BrainRegion ──
    svg += _circle(720, 160, 30, "#b2dfdb", "#00695c")
    svg += _text(720, 152, "BrainReg", "label")
    svg += _text(720, 167, "12", "count")
    svg += _text(720, 180, "uberon: 0002421", "tiny")

    # ── OntologyConcept (NEW) ──
    svg += _rounded_rect(270, 500, 280, 60, "#e8eaf6", "#283593", rx=12)
    svg += _text(410, 522, "OntologyConcept", "label")
    svg += _text(410, 538, "52 nodes (SNOMED + LOINC + UBERON + HPO + ICD-10)", "small")
    svg += _text(410, 552, "uri | code | label | source_ontology", "tiny")

    # ── ICD-10 subgroup ──
    svg += _rounded_rect(600, 465, 190, 50, "#fce4ec", "#880e4f", rx=8)
    svg += _text(695, 485, "ICD-10 Hierarchy", "label")
    svg += _text(695, 500, "G30.9 IS_A G30 IS_A ...", "tiny")

    # ── Original edges ──
    svg += _line(375, 190, 220, 255, "#1565c0")
    svg += _text(280, 215, "HAS_VISIT", "edge-label")

    svg += _line(210, 310, 375, 370, "#2e7d32")
    svg += _text(275, 350, "HAS_DIAGNOSIS", "edge-label")

    svg += _line(445, 190, 600, 255, "#f9a825")
    svg += _text(535, 215, "HAS_COGNITIVE", "edge-label")

    svg += _line(150, 175, 165, 255, "#7b1fa2")

    # ── NEW semantic edges (dashed, colored) ──
    # Diagnosis → OntologyConcept (MAPS_TO SNOMED)
    svg += _path("M 410 428 C 410 465 350 500 350 500", "#283593", 2, "arrowhead-blue", dashed=True)
    svg += _text(345, 467, "MAPS_TO", "edge-label")
    svg += _text(345, 480, "25,946", "tiny")

    # CogAssess → OntologyConcept (MAPS_TO LOINC)
    svg += _path("M 610 315 C 560 400 460 500 460 500", "#283593", 2, "arrowhead-blue", dashed=True)
    svg += _text(545, 405, "MAPS_TO", "edge-label")
    svg += _text(545, 418, "65,345", "tiny")

    # Biomarker → OntologyConcept (MAPS_TO LOINC)
    svg += _path("M 115 192 C 150 350 300 500 300 500", "#283593", 2, "arrowhead-blue", dashed=True)
    svg += _text(170, 360, "MAPS_TO", "edge-label")
    svg += _text(170, 373, "9,467", "tiny")

    # Diagnosis → ICD-10 (CLASSIFIED_AS)
    svg += _path("M 445 410 C 550 440 600 465 600 465", "#880e4f", 2, "arrowhead-red", dashed=True)
    svg += _text(545, 435, "CLASSIFIED_AS", "edge-label")
    svg += _text(545, 448, "25,946", "tiny")

    # IS_A within OntologyConcept
    svg += _path("M 550 530 C 580 510 600 495 600 495", "#283593", 1.5, "arrowhead-blue")
    svg += _text(590, 518, "IS_A (27)", "tiny")

    # ── Legend ──
    svg += _rounded_rect(15, 570, 790, 42, "#fafafa", "#ccc", rx=4)
    svg += _text(50, 588, "Legend:", "label", "start")
    svg += _line(110, 585, 150, 585, "#555", 1.5, "arrowhead")
    svg += _text(165, 589, "Original LPG edge", "tiny", "start")
    svg += _line(305, 585, 345, 585, "#283593", 2, "arrowhead-blue", dashed=True)
    svg += _text(360, 589, "New semantic edge (MAPS_TO/IS_A)", "tiny", "start")
    svg += _line(560, 585, 600, 585, "#880e4f", 2, "arrowhead-red", dashed=True)
    svg += _text(615, 589, "CLASSIFIED_AS (ICD-10)", "tiny", "start")

    svg += '</svg>'
    path = IMAGES_DIR / "02_kg_after.svg"
    path.write_text(svg, encoding="utf-8")
    return path


# ────────────────────────────────────────────────────────────────────
# DIAGRAM 3: Transformation Steps (Phase 1 pipeline)
# ────────────────────────────────────────────────────────────────────
def generate_transformation_pipeline_svg():
    """Generate SVG showing the 4-step LPG→KG transformation pipeline."""
    w, h = 780, 400
    svg = _svg_header(w, h)

    svg += _text(390, 28, "Phase 1: Schema Migration Pipeline (Steps 17-20)", "title")
    svg += _text(390, 48, "In-place semantic upgrade without graph rebuild", "subtitle")

    # Step boxes
    steps = [
        ("Step 17", "Apply Constraints", "12 constraints\n15 indexes", "#e3f2fd", "#1565c0"),
        ("Step 18", "Ontology Properties", "SNOMED, LOINC\nUBERON, rdf_type", "#e8f5e9", "#2e7d32"),
        ("Step 19", "ICD-10 Integration", "5 OntConcepts\n25,946 CLASSIFIED_AS", "#fce4ec", "#c62828"),
        ("Step 20", "Ontology Layer", "47 OntConcepts\n100,770 MAPS_TO", "#ede7f6", "#4527a0"),
    ]

    bx, by = 30, 90
    bw, bh = 160, 130
    gap = 35

    for i, (step, title, desc, fill, stroke) in enumerate(steps):
        x = bx + i * (bw + gap)
        svg += _rounded_rect(x, by, bw, bh, fill, stroke, rx=10)
        svg += _text(x + bw / 2, by + 25, step, "label")
        svg += _text(x + bw / 2, by + 45, title, "small")
        # Multi-line description
        lines = desc.split("\n")
        for j, line in enumerate(lines):
            svg += _text(x + bw / 2, by + 70 + j * 16, line, "tiny")

        # Arrow between steps
        if i < 3:
            ax = x + bw + 2
            svg += _line(ax, by + bh / 2, ax + gap - 4, by + bh / 2, stroke, 2, "arrowhead")

    # Before/After comparison
    y_comp = 260
    svg += _rounded_rect(30, y_comp, 340, 120, "#fff3e0", "#e65100", rx=8)
    svg += _text(200, y_comp + 22, "BEFORE (LPG)", "label")
    before_items = [
        "Nodes: ~407K (17 labels)",
        "Relationships: ~1.16M (20+ types)",
        "Ontology codes: NONE",
        "Relationship URIs: NONE",
        "OntologyConcept nodes: 0",
    ]
    for i, item in enumerate(before_items):
        svg += _text(200, y_comp + 42 + i * 16, item, "small")

    svg += _rounded_rect(410, y_comp, 340, 120, "#e8f5e9", "#2e7d32", rx=8)
    svg += _text(580, y_comp + 22, "AFTER (KG)", "label")
    after_items = [
        "Nodes: ~407K + 52 OntologyConcept",
        "Relationships: ~1.16M + 126,743 semantic",
        "Ontology codes: 100% coverage",
        "Relationship URIs: 30 types (1.2M rels)",
        "OntologyConcept nodes: 52 (4 ontologies)",
    ]
    for i, item in enumerate(after_items):
        svg += _text(580, y_comp + 42 + i * 16, item, "small")

    # Arrow between before/after
    svg += _line(370, y_comp + 60, 410, y_comp + 60, "#333", 3, "arrowhead")

    svg += '</svg>'
    path = IMAGES_DIR / "03_transformation_pipeline.svg"
    path.write_text(svg, encoding="utf-8")
    return path


# ────────────────────────────────────────────────────────────────────
# DIAGRAM 4: Ontology Concept Layer detail
# ────────────────────────────────────────────────────────────────────
def generate_ontology_layer_svg():
    """Generate SVG showing the OntologyConcept layer and IS_A hierarchies."""
    w, h = 780, 480
    svg = _svg_header(w, h)

    svg += _text(390, 28, "OntologyConcept Layer — IS_A Hierarchies & MAPS_TO", "title")
    svg += _text(390, 48, "52 concept nodes across 4 ontologies + ICD-10", "subtitle")

    # ── SNOMED-CT hierarchy ──
    sx = 50
    svg += _rounded_rect(sx, 75, 200, 220, "#e3f2fd", "#1565c0", rx=8)
    svg += _text(sx + 100, 95, "SNOMED-CT (18)", "label")

    snomed_tree = [
        (100, 115, "Disease"),
        (110, 135, "Disorder of NS"),
        (120, 155, "Neurodegenerative"),
        (130, 175, "Dementia"),
        (140, 195, "Alzheimer's (26929004)"),
        (130, 215, "MCI (386806002)"),
        (100, 240, "Cognitive finding"),
        (100, 260, "CSF analysis"),
    ]
    for x_off, y, label in snomed_tree:
        svg += _text(x_off, y, label, "tiny", "start")
        if y > 115 and x_off > 100:
            svg += _line(x_off - 12, y - 8, x_off - 4, y - 4, "#1565c0", 1, None)

    # ── LOINC ──
    lx = 270
    svg += _rounded_rect(lx, 75, 170, 160, "#e8f5e9", "#2e7d32", rx=8)
    svg += _text(lx + 85, 95, "LOINC (10)", "label")

    loinc_items = [
        "72106-8  MMSE",
        "72172-0  CDR",
        "72194-4  ADAS-Cog",
        "72133-2  MoCA",
        "13967-5  Abeta42",
        "15201-7  Tau",
        "62731-6  pTau181",
    ]
    for i, item in enumerate(loinc_items):
        svg += _text(lx + 10, 115 + i * 16, item, "tiny", "start")

    # ── UBERON ──
    ux = 460
    svg += _rounded_rect(ux, 75, 170, 220, "#b2dfdb", "#00695c", rx=8)
    svg += _text(ux + 85, 95, "UBERON (14)", "label")

    uberon_tree = [
        (470, 115, "Brain"),
        (480, 135, "Cerebral cortex"),
        (490, 155, "Hippocampus"),
        (490, 175, "Entorhinal cortex"),
        (490, 195, "Frontal lobe"),
        (490, 215, "Temporal lobe"),
        (480, 235, "Amygdala"),
        (480, 255, "Thalamus"),
        (480, 275, "Cerebellum"),
    ]
    for x_off, y, label in uberon_tree:
        svg += _text(x_off, y, label, "tiny", "start")

    # ── HPO ──
    hx = 650
    svg += _rounded_rect(hx, 75, 120, 120, "#f3e5f5", "#7b1fa2", rx=8)
    svg += _text(hx + 60, 95, "HPO (5)", "label")

    hpo_items = ["Cognitive imp.", "Dementia", "Memory imp.", "Mental deter.", "Behavioral abn."]
    for i, item in enumerate(hpo_items):
        svg += _text(hx + 10, 115 + i * 16, item, "tiny", "start")

    # ── ICD-10 ──
    svg += _rounded_rect(650, 210, 120, 85, "#fce4ec", "#880e4f", rx=8)
    svg += _text(710, 230, "ICD-10 (5)", "label")
    icd_items = ["G30.9 AD", "G30 parent", "F06.7 MCI", "F06 parent", "Z03.89 CN"]
    for i, item in enumerate(icd_items):
        svg += _text(660, 250 + i * 13, item, "tiny", "start")

    # ── MAPS_TO summary below ──
    y_maps = 330
    svg += _rounded_rect(30, y_maps, 720, 130, "#fafafa", "#bbb", rx=8)
    svg += _text(390, y_maps + 22, "MAPS_TO Edge Distribution", "label")

    maps_data = [
        ("Diagnosis", "SNOMED-CT", "25,946", "#c62828"),
        ("CognitiveAssessment", "LOINC", "65,345", "#f9a825"),
        ("Biomarker (CSF)", "LOINC", "9,467", "#7b1fa2"),
        ("BrainRegion", "UBERON", "12", "#00695c"),
        ("Diagnosis", "ICD-10 (CLASSIFIED_AS)", "25,946", "#880e4f"),
    ]

    bar_x = 60
    bar_y = y_maps + 42
    max_val = 65345
    bar_max_w = 400

    for i, (source, target, count_str, color) in enumerate(maps_data):
        y = bar_y + i * 20
        count_val = int(count_str.replace(",", ""))
        bar_w = max(4, int(count_val / max_val * bar_max_w))
        svg += _text(bar_x - 5, y + 5, f"{source} -> {target}", "tiny", "end")
        # Move label left of bar
        svg += f'<text x="{bar_x - 5}" y="{y + 5}" class="tiny" text-anchor="end">{source}</text>\n'
        svg += f'<rect x="{bar_x + 170}" y="{y - 7}" width="{bar_w}" height="14" fill="{color}" rx="3" opacity="0.8"/>\n'
        svg += _text(bar_x + 175 + bar_w, y + 5, count_str, "count", "start")

    svg += '</svg>'
    path = IMAGES_DIR / "04_ontology_layer.svg"
    path.write_text(svg, encoding="utf-8")
    return path


# ────────────────────────────────────────────────────────────────────
# DIAGRAM 5: LPG vs KG Comparison
# ────────────────────────────────────────────────────────────────────
def generate_lpg_vs_kg_comparison_svg():
    """Generate SVG with a side-by-side comparison table of LPG vs KG characteristics."""
    w, h = 780, 520
    svg = _svg_header(w, h)

    svg += _text(390, 28, "Labeled Property Graph vs Knowledge Graph", "title")
    svg += _text(390, 48, "Key distinctions applied to the ADNI dataset", "subtitle")

    # Table structure
    col1_x, col2_x, col3_x = 40, 300, 540
    header_y = 80
    row_h = 36

    # Header row
    svg += f'<rect x="30" y="{header_y - 15}" width="720" height="32" fill="#263238" rx="4"/>\n'
    svg += f'<text x="{col1_x}" y="{header_y + 4}" class="label" text-anchor="start" fill="white">Characteristic</text>\n'
    svg += f'<text x="{col2_x}" y="{header_y + 4}" class="label" text-anchor="start" fill="white">LPG (Before)</text>\n'
    svg += f'<text x="{col3_x}" y="{header_y + 4}" class="label" text-anchor="start" fill="white">KG (After Phase 1)</text>\n'

    rows = [
        ("Data Model", "Nodes + Edges + Properties", "Nodes + Edges + Properties\n+ Ontology Concepts"),
        ("Node Semantics", "Application-specific labels\n(Patient, Visit, Diagnosis)", "Ontology-grounded labels\nrdf_type = ncit:C16960"),
        ("Relationship Semantics", "String-typed edges\n(HAS_VISIT, HAS_DIAGNOSIS)", "URI-annotated edges\nuri = ro:RO_0000056"),
        ("Disease Coding", "diagnosis_code = 'AD'\n(local string)", "snomed: 26929004\nicd10: G30.9, mondo: 0004975"),
        ("Assessment Coding", "test_name = 'MMSE'\n(local string)", "loinc_code: 72106-8\n(global standard)"),
        ("Brain Region Coding", "name = 'Hippocampus'\n(local string)", "uberon_code: UBERON:0002421\n(global standard)"),
        ("Concept Taxonomy", "NONE\n(flat namespace)", "IS_A hierarchies: SNOMED,\nUBERON, HPO, ICD-10 (27 edges)"),
        ("Cross-Ontology Links", "NONE", "100,770 MAPS_TO +\n25,946 CLASSIFIED_AS"),
        ("External Interoperability", "Requires custom mappings\nfor each integration", "Standard URIs enable\ndirect AlzKB, FHIR linking"),
        ("Machine Reasoning", "Pattern matching only\n(Cypher queries)", "Ontology traversal +\nIS_A inference + reasoning"),
    ]

    for i, (char, lpg_val, kg_val) in enumerate(rows):
        y = header_y + 32 + i * row_h
        bg = "#f5f5f5" if i % 2 == 0 else "#ffffff"
        svg += f'<rect x="30" y="{y - 10}" width="720" height="{row_h}" fill="{bg}"/>\n'
        svg += _text(col1_x, y + 8, char, "small", "start")

        # Handle multiline
        lpg_lines = lpg_val.split("\n")
        for j, line in enumerate(lpg_lines):
            svg += _text(col2_x, y + 4 + j * 13, line, "tiny", "start")

        kg_lines = kg_val.split("\n")
        for j, line in enumerate(kg_lines):
            svg += _text(col3_x, y + 4 + j * 13, line, "tiny", "start")

    # Bottom verdict
    vy = header_y + 32 + len(rows) * row_h + 15
    svg += _rounded_rect(30, vy, 720, 40, "#e8f5e9", "#2e7d32", rx=6)
    svg += _text(390, vy + 18, "Verdict: After Phase 1, the ADNI graph is a Knowledge Graph", "label")
    svg += _text(390, vy + 33, "100% ontology coverage | Formal hierarchies | Standard URIs | Cross-ontology linkage", "tiny")

    svg += '</svg>'
    path = IMAGES_DIR / "05_lpg_vs_kg_comparison.svg"
    path.write_text(svg, encoding="utf-8")
    return path


# ══════════════════════════════════════════════════════════════════════
#  PDF GENERATION
# ══════════════════════════════════════════════════════════════════════

def generate_pdf(svg_paths: list):
    """Generate a professional PDF report with embedded SVG diagrams."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm, cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image, PageBreak, KeepTogether
    )
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPDF

    pdf_path = REPORT_DIR / "ADNI_KG_Graph_Classification_Report.pdf"

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    styles.add(ParagraphStyle(
        "ReportTitle", parent=styles["Title"],
        fontSize=22, spaceAfter=6, textColor=HexColor("#1a1a2e"),
        fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "ReportSubtitle", parent=styles["Normal"],
        fontSize=12, spaceAfter=16, textColor=HexColor("#555"),
        alignment=TA_CENTER, fontName="Helvetica",
    ))
    styles.add(ParagraphStyle(
        "SectionHead", parent=styles["Heading1"],
        fontSize=16, spaceBefore=18, spaceAfter=8,
        textColor=HexColor("#0d47a1"), fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "SubSectionHead", parent=styles["Heading2"],
        fontSize=13, spaceBefore=12, spaceAfter=6,
        textColor=HexColor("#283593"), fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "BodyText2", parent=styles["Normal"],
        fontSize=10, spaceAfter=8, alignment=TA_JUSTIFY,
        fontName="Helvetica", leading=14,
    ))
    styles.add(ParagraphStyle(
        "Caption", parent=styles["Normal"],
        fontSize=9, alignment=TA_CENTER, textColor=HexColor("#666"),
        fontName="Helvetica-Oblique", spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        "BulletItem", parent=styles["Normal"],
        fontSize=10, leftIndent=20, bulletIndent=10,
        spaceAfter=4, fontName="Helvetica", leading=13,
    ))

    story = []

    # ── Title Page ──
    story.append(Spacer(1, 40 * mm))
    story.append(Paragraph(
        "ADNI Knowledge Graph<br/>Graph Classification Report",
        styles["ReportTitle"]
    ))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        "From Labeled Property Graph to Knowledge Graph:<br/>"
        "Phase 1 Schema Migration Results",
        styles["ReportSubtitle"]
    ))
    story.append(Spacer(1, 15 * mm))
    story.append(Paragraph(
        "<b>Project:</b> ADNI Knowledge Graph for Alzheimer's Disease Research<br/>"
        "<b>Author:</b> Oguzhan Gungor<br/>"
        "<b>Supervisor:</b> Dr. Sultan Turhan &amp; Asst. Prof. Ozgun Pinarer<br/>"
        "<b>Institution:</b> Galatasaray University<br/>"
        "<b>Date:</b> February 24, 2026<br/>"
        "<b>Phase:</b> 1 (Schema Migration) &mdash; Steps 17&ndash;20 Complete",
        styles["BodyText2"]
    ))
    story.append(PageBreak())

    # ── Table of Contents (inline) ──
    story.append(Paragraph("Table of Contents", styles["SectionHead"]))
    toc_items = [
        "1. Executive Summary",
        "2. Definitions: LPG vs Knowledge Graph",
        "3. ADNI Graph Before Phase 1 (LPG State)",
        "4. Phase 1 Transformation Pipeline",
        "5. ADNI Graph After Phase 1 (KG State)",
        "6. Ontology Layer Detail",
        "7. Side-by-Side Comparison: LPG vs KG",
        "8. Classification Verdict",
        "9. What This Enables for Phases 2-4",
    ]
    for item in toc_items:
        story.append(Paragraph(item, styles["BulletItem"]))
    story.append(PageBreak())

    # ── 1. Executive Summary ──
    story.append(Paragraph("1. Executive Summary", styles["SectionHead"]))
    story.append(Paragraph(
        "On February 24, 2026, Phase 1 of the ADNI Knowledge Graph project was completed. "
        "This phase transformed the existing Neo4j Labeled Property Graph (LPG) &mdash; containing "
        "~407,000 nodes and ~1.16 million relationships ingested from 108 ADNI clinical tables &mdash; "
        "into a semantically grounded <b>Knowledge Graph (KG)</b>.",
        styles["BodyText2"]
    ))
    story.append(Paragraph(
        "The transformation was achieved <b>in-place</b>, without rebuilding the database, through "
        "four pipeline steps (17&ndash;20) that added:",
        styles["BodyText2"]
    ))
    summary_items = [
        "<b>12 uniqueness constraints</b> and <b>15 performance indexes</b> (Step 17)",
        "<b>Ontology codes</b> on all observation nodes: SNOMED-CT, LOINC, UBERON, ICD-10, MONDO, NCI Thesaurus (Step 18)",
        "<b>URI properties</b> on 30 relationship types covering ~1.2M relationships (Step 18)",
        "<b>52 OntologyConcept nodes</b> with IS_A hierarchies across 4 ontologies + ICD-10 (Steps 19-20)",
        "<b>126,743 new semantic edges</b>: 100,770 MAPS_TO + 25,946 CLASSIFIED_AS + 27 IS_A (Steps 19-20)",
    ]
    for item in summary_items:
        story.append(Paragraph(f"&bull; {item}", styles["BulletItem"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "The graph now carries formal semantic meaning through ontology grounding, enabling machine "
        "reasoning, cross-ontology queries, and interoperability with external biomedical knowledge "
        "bases such as AlzKB. <b>By every standard definition, the graph is now a Knowledge Graph.</b>",
        styles["BodyText2"]
    ))
    story.append(PageBreak())

    # ── 2. Definitions ──
    story.append(Paragraph("2. Definitions: Labeled Property Graph vs Knowledge Graph", styles["SectionHead"]))

    story.append(Paragraph("2.1 Labeled Property Graph (LPG)", styles["SubSectionHead"]))
    story.append(Paragraph(
        "A Labeled Property Graph is formally defined as a tuple G = (V, E, &rho;, &lambda;, &sigma;) where "
        "V is a set of vertices (nodes), E is a set of directed edges (relationships), &rho; is a property "
        "function mapping nodes/edges to key-value pairs, &lambda; is a labeling function assigning type "
        "identifiers, and &sigma; represents optional schema constraints.",
        styles["BodyText2"]
    ))
    story.append(Paragraph(
        "LPGs are a <b>database model</b> designed for efficient storage and traversal. They emphasize "
        "flexible schema evolution, fast multi-hop queries via index-free adjacency, and rich property "
        "storage on both nodes and edges. Critically, LPGs do <b>not</b> require global identifiers "
        "(URIs/IRIs) and have <b>no inherent semantic grounding</b> to external ontologies or formal "
        "type systems. Node labels and relationship types are application-specific strings.",
        styles["BodyText2"]
    ))

    story.append(Paragraph("2.2 Knowledge Graph (KG)", styles["SubSectionHead"]))
    story.append(Paragraph(
        "A Knowledge Graph is a knowledge base that uses a graph-structured data model to formally "
        "represent semantics by describing entities and their interrelationships. The critical distinction "
        "from an LPG is that a KG encodes <b>meaning</b> for programmatic use through ontologies, which "
        "describe entity types, characteristics, and relationships using standards such as:",
        styles["BodyText2"]
    ))
    kg_standards = [
        "<b>OWL</b> (Web Ontology Language) &mdash; for logical inference and class hierarchies",
        "<b>RDFS</b> (RDF Schema) &mdash; for vocabulary definition (rdfs:subClassOf = IS_A)",
        "<b>SKOS</b> (Simple Knowledge Organization System) &mdash; for concept mapping (skos:exactMatch = MAPS_TO)",
        "<b>RO</b> (Relation Ontology) &mdash; for standardized biological relationship predicates",
        "<b>SNOMED-CT, LOINC, UBERON, ICD-10</b> &mdash; domain-specific ontology standards",
    ]
    for item in kg_standards:
        story.append(Paragraph(f"&bull; {item}", styles["BulletItem"]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "A graph becomes a KG when its nodes and edges are grounded in formal ontologies, carry "
        "globally unique identifiers (URIs), participate in IS_A taxonomic hierarchies, and support "
        "machine reasoning through these formal semantics. The key phrase is: <i>a KG carries meaning "
        "that machines can interpret without application-specific knowledge</i>.",
        styles["BodyText2"]
    ))

    story.append(Paragraph("2.3 Can a Neo4j Graph Be Both?", styles["SubSectionHead"]))
    story.append(Paragraph(
        "<b>Yes.</b> Neo4j remains an LPG database at the infrastructure level (using its native "
        "property graph storage engine and Cypher query language), but by adding semantic properties "
        "(ontology codes, URIs, rdf_type annotations, OntologyConcept nodes, IS_A/MAPS_TO relationships), "
        "it is upgraded to a Knowledge Graph at the semantic layer. Recent literature describes this as a "
        "<b>Semantic Property Graph (SPG)</b> or <b>LPG-based Knowledge Graph</b>, combining RDF reasoning "
        "capabilities with property graph performance.",
        styles["BodyText2"]
    ))
    story.append(PageBreak())

    # ── 3. Before State ──
    story.append(Paragraph("3. ADNI Graph Before Phase 1 (LPG State)", styles["SectionHead"]))
    story.append(Paragraph(
        "Before Phase 1, the ADNI graph was a pure Labeled Property Graph constructed through pipeline "
        "steps 1&ndash;16. It contained ~407,000 nodes across 17 label types and ~1.16 million "
        "relationships across 20+ types. All data from 108 ADNI CSV tables (~5,800 columns) was "
        "ingested, including patient demographics, cognitive assessments, biomarkers, imaging metadata, "
        "genetic profiles, and family history.",
        styles["BodyText2"]
    ))
    story.append(Paragraph(
        "While comprehensive in coverage, the graph lacked any formal semantic grounding. Node labels "
        "like 'Diagnosis' and relationship types like 'HAS_VISIT' were application-specific strings "
        "with no connection to external ontologies. A 'diagnosis_code' of 'AD' was meaningful to humans "
        "but opaque to machines without custom application logic.",
        styles["BodyText2"]
    ))

    # Embed SVG diagram 1
    drawing1 = svg2rlg(str(svg_paths[0]))
    if drawing1:
        scale = min(170 * mm / drawing1.width, 130 * mm / drawing1.height)
        drawing1.width *= scale
        drawing1.height *= scale
        drawing1.scale(scale, scale)
        story.append(drawing1)
        story.append(Paragraph(
            "Figure 1: ADNI Labeled Property Graph before Phase 1. No ontology codes, "
            "no URI properties, no OntologyConcept nodes.",
            styles["Caption"]
        ))
    story.append(PageBreak())

    # ── 4. Transformation Pipeline ──
    story.append(Paragraph("4. Phase 1 Transformation Pipeline", styles["SectionHead"]))
    story.append(Paragraph(
        "The transformation was executed through four sequential steps, each building on the previous:",
        styles["BodyText2"]
    ))

    step_details = [
        ("<b>Step 17: Apply Composite Unique Constraints</b> &mdash; "
         "Created 12 uniqueness constraints (5 core + 7 composite for observation nodes) and "
         "15 performance indexes. All use IF NOT EXISTS for idempotency. Verified Neo4j 5.24.2 "
         "supports composite constraints."),
        ("<b>Step 18: Add Ontology Properties (In-Place Upgrade)</b> &mdash; "
         "Enriched existing nodes with ontology codes without creating new nodes: "
         "Diagnosis nodes received snomed_code, icd10_code, and mondo_code; "
         "CognitiveAssessment nodes received loinc_code; Biomarker nodes received loinc_code; "
         "BrainRegion nodes received uberon_code; Patient and Visit nodes received rdf_type. "
         "30 relationship types received URI properties. 100% coverage achieved."),
        ("<b>Step 19: ICD-10 Integration</b> &mdash; "
         "Created 5 OntologyConcept nodes for ICD-10 codes (G30.9, G30, F06.7, F06, Z03.89), "
         "built 2 IS_A hierarchy edges, and linked all 25,946 Diagnosis nodes via CLASSIFIED_AS "
         "edges. WHO ICD REST API client implemented with static JSON fallback."),
        ("<b>Step 20: Ontology Layer + MAPS_TO</b> &mdash; "
         "Created 47 OntologyConcept nodes across 4 ontologies (18 SNOMED-CT, 10 LOINC, "
         "14 UBERON, 5 HPO). Built 25 IS_A hierarchy edges. Created 100,770 MAPS_TO edges "
         "linking data nodes to their ontology concepts."),
    ]
    for detail in step_details:
        story.append(Paragraph(f"&bull; {detail}", styles["BulletItem"]))
    story.append(Spacer(1, 4 * mm))

    # Embed SVG diagram 3
    drawing3 = svg2rlg(str(svg_paths[2]))
    if drawing3:
        scale = min(170 * mm / drawing3.width, 105 * mm / drawing3.height)
        drawing3.width *= scale
        drawing3.height *= scale
        drawing3.scale(scale, scale)
        story.append(drawing3)
        story.append(Paragraph(
            "Figure 2: Phase 1 transformation pipeline showing the four sequential steps "
            "and before/after comparison.",
            styles["Caption"]
        ))
    story.append(PageBreak())

    # ── 5. After State ──
    story.append(Paragraph("5. ADNI Graph After Phase 1 (KG State)", styles["SectionHead"]))
    story.append(Paragraph(
        "After Phase 1, the graph carries full semantic meaning. Every Diagnosis node is grounded "
        "in SNOMED-CT (e.g., Alzheimer's disease = 26929004) and classified under ICD-10 (G30.9). "
        "Every CognitiveAssessment is linked to its LOINC code (e.g., MMSE = 72106-8). Every "
        "BrainRegion carries its UBERON identifier (e.g., Hippocampus = UBERON:0002421). "
        "All relationships carry URI properties from the Relation Ontology (e.g., HAS_VISIT = "
        "ro:RO_0000056).",
        styles["BodyText2"]
    ))
    story.append(Paragraph(
        "The OntologyConcept layer provides formal IS_A taxonomies. A machine can now traverse "
        "from a specific Diagnosis node through MAPS_TO to a SNOMED-CT concept, then up the IS_A "
        "hierarchy: Alzheimer's disease IS_A Dementia IS_A Neurodegenerative disorder IS_A "
        "Disorder of nervous system IS_A Disease. This was impossible in the LPG state.",
        styles["BodyText2"]
    ))

    # Embed SVG diagram 2
    drawing2 = svg2rlg(str(svg_paths[1]))
    if drawing2:
        scale = min(170 * mm / drawing2.width, 140 * mm / drawing2.height)
        drawing2.width *= scale
        drawing2.height *= scale
        drawing2.scale(scale, scale)
        story.append(drawing2)
        story.append(Paragraph(
            "Figure 3: ADNI Knowledge Graph after Phase 1. Dashed lines show new semantic edges "
            "(MAPS_TO, CLASSIFIED_AS, IS_A). OntologyConcept nodes provide the semantic backbone.",
            styles["Caption"]
        ))
    story.append(PageBreak())

    # ── 6. Ontology Layer Detail ──
    story.append(Paragraph("6. Ontology Layer Detail", styles["SectionHead"]))
    story.append(Paragraph(
        "The ontology layer consists of 52 OntologyConcept nodes distributed across five ontology "
        "systems. Each concept has a globally unique URI (e.g., snomed:26929004), a human-readable "
        "label, a source_ontology identifier, and an optional code property.",
        styles["BodyText2"]
    ))

    # Ontology breakdown table
    ont_data = [
        ["Ontology", "Concepts", "IS_A Edges", "MAPS_TO Source", "MAPS_TO Count"],
        ["SNOMED-CT", "18", "9", "Diagnosis", "25,946"],
        ["LOINC", "10", "0", "CogAssess + Biomarker", "74,812"],
        ["UBERON", "14", "13", "BrainRegion", "12"],
        ["HPO", "5", "3", "(future use)", "0"],
        ["ICD-10", "5", "2", "Diagnosis (CLASSIFIED_AS)", "25,946"],
        ["TOTAL", "52", "27", "", "126,716"],
    ]
    t = Table(ont_data, colWidths=[75, 55, 55, 120, 75])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor("#263238")),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor("#FFFFFF")),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
        ('BACKGROUND', (0, -1), (-1, -1), HexColor("#E8F5E9")),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [HexColor("#FFFFFF"), HexColor("#F5F5F5")]),
    ]))
    story.append(t)
    story.append(Paragraph(
        "Table 1: OntologyConcept distribution across ontology systems.",
        styles["Caption"]
    ))

    # Embed SVG diagram 4
    drawing4 = svg2rlg(str(svg_paths[3]))
    if drawing4:
        scale = min(170 * mm / drawing4.width, 120 * mm / drawing4.height)
        drawing4.width *= scale
        drawing4.height *= scale
        drawing4.scale(scale, scale)
        story.append(drawing4)
        story.append(Paragraph(
            "Figure 4: OntologyConcept layer showing IS_A hierarchies within each ontology "
            "and MAPS_TO edge distribution.",
            styles["Caption"]
        ))
    story.append(PageBreak())

    # ── 7. Comparison ──
    story.append(Paragraph("7. Side-by-Side Comparison: LPG vs KG", styles["SectionHead"]))
    story.append(Paragraph(
        "The following table summarizes the key differences between the graph's LPG state "
        "(before Phase 1) and its KG state (after Phase 1):",
        styles["BodyText2"]
    ))

    comp_data = [
        ["Characteristic", "LPG (Before)", "KG (After Phase 1)"],
        ["Data Model", "Nodes + Edges + Properties", "Nodes + Edges + Properties\n+ OntologyConcepts"],
        ["Node Semantics", "App-specific labels\n(Patient, Visit, Diagnosis)", "Ontology-grounded\nrdf_type = ncit:C16960"],
        ["Relationship Semantics", "String-typed edges", "URI-annotated edges\nro:RO_0000056"],
        ["Disease Coding", "diagnosis_code = 'AD'", "snomed: 26929004\nicd10: G30.9"],
        ["Assessment Coding", "test_name = 'MMSE'", "loinc_code: 72106-8"],
        ["Brain Region Coding", "name = 'Hippocampus'", "uberon: UBERON:0002421"],
        ["Concept Taxonomy", "NONE (flat)", "IS_A hierarchies (27 edges)"],
        ["Cross-Ontology Links", "NONE", "100,770 MAPS_TO\n25,946 CLASSIFIED_AS"],
        ["Machine Reasoning", "Pattern matching", "Ontology traversal + IS_A"],
        ["External Interop.", "Custom mappings req.", "Standard URIs (AlzKB, FHIR)"],
    ]
    t2 = Table(comp_data, colWidths=[100, 130, 140])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor("#263238")),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor("#FFFFFF")),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor("#FFFFFF"), HexColor("#F5F5F5")]),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t2)
    story.append(Paragraph(
        "Table 2: Feature-by-feature comparison of the LPG and KG states.",
        styles["Caption"]
    ))
    story.append(Spacer(1, 4 * mm))

    # Embed SVG diagram 5
    drawing5 = svg2rlg(str(svg_paths[4]))
    if drawing5:
        scale = min(170 * mm / drawing5.width, 120 * mm / drawing5.height)
        drawing5.width *= scale
        drawing5.height *= scale
        drawing5.scale(scale, scale)
        story.append(drawing5)
        story.append(Paragraph(
            "Figure 5: Visual comparison table of LPG vs KG characteristics.",
            styles["Caption"]
        ))
    story.append(PageBreak())

    # ── 8. Classification Verdict ──
    story.append(Paragraph("8. Classification Verdict", styles["SectionHead"]))
    story.append(Paragraph(
        "Based on the established definitions of Labeled Property Graphs and Knowledge Graphs, "
        "we classify the ADNI graph as follows:",
        styles["BodyText2"]
    ))

    verdict_data = [
        ["KG Criterion", "Status", "Evidence"],
        ["Ontology grounding on nodes", "PASS", "100% of Diagnosis, CogAssess,\nBiomarker, BrainRegion nodes"],
        ["Formal relationship URIs", "PASS", "30 types, 1.2M rels with\nRO/SKOS/RDFS URIs"],
        ["OntologyConcept layer", "PASS", "52 nodes across\nSNOMED/LOINC/UBERON/HPO/ICD-10"],
        ["IS_A taxonomic hierarchies", "PASS", "27 IS_A edges in\n4 ontology systems"],
        ["MAPS_TO / CLASSIFIED_AS links", "PASS", "126,716 semantic edges\nlinking data to concepts"],
        ["rdf_type on nodes", "PASS", "Patient (ncit:C16960)\nVisit (ncit:C159705)"],
        ["Global unique identifiers", "PASS", "URI property on all\nOntologyConcept nodes"],
        ["Cross-ontology queryability", "PASS", "SNOMED-CT <-> ICD-10\nvia MAPS_TO + CLASSIFIED_AS"],
    ]
    t3 = Table(verdict_data, colWidths=[130, 50, 170])
    t3.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor("#263238")),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor("#FFFFFF")),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
        ('BACKGROUND', (1, 1), (1, -1), HexColor("#C8E6C9")),
        ('FONTNAME', (1, 1), (1, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (0, -1), [HexColor("#FFFFFF"), HexColor("#F5F5F5")]),
        ('ROWBACKGROUNDS', (2, 1), (2, -1), [HexColor("#FFFFFF"), HexColor("#F5F5F5")]),
    ]))
    story.append(t3)
    story.append(Paragraph(
        "Table 3: Knowledge Graph criteria checklist &mdash; all criteria pass.",
        styles["Caption"]
    ))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "<b>Conclusion:</b> The ADNI Neo4j graph, after the completion of Phase 1 (Steps 17&ndash;20), "
        "satisfies <b>all standard criteria</b> for classification as a Knowledge Graph. It retains "
        "all LPG capabilities (fast traversal, property storage, Cypher queries) while adding the "
        "semantic layer that distinguishes a KG: ontology grounding, formal hierarchies, standard URIs, "
        "and cross-ontology linkage.",
        styles["BodyText2"]
    ))
    story.append(Paragraph(
        "The graph is best described as an <b>LPG-based Knowledge Graph</b> or "
        "<b>Semantic Property Graph</b> &mdash; a hybrid architecture that combines the performance "
        "of Neo4j's LPG engine with the semantic richness of formal ontology systems.",
        styles["BodyText2"]
    ))
    story.append(PageBreak())

    # ── 9. Future Phases ──
    story.append(Paragraph("9. What This Enables for Phases 2-4", styles["SectionHead"]))
    story.append(Paragraph(
        "The semantic upgrade completed in Phase 1 is not merely a classification exercise. It "
        "directly enables the subsequent research phases:",
        styles["BodyText2"]
    ))
    future_items = [
        ("<b>Phase 2 (Causal Discovery):</b> The ontology-grounded feature matrix (Step 21) can now "
         "use LOINC/SNOMED codes to standardize variable selection. Causal discovery algorithms (PC, "
         "FCI, GES) will produce edges that can be mapped back to OntologyConcept nodes via their "
         "standardized URIs, making discovered causal relationships interoperable."),
        ("<b>Phase 3 (Validation):</b> The MAPS_TO and CLASSIFIED_AS edges enable direct alignment "
         "with AlzKB (118,902 entities). SAME_AS edges can be created between our OntologyConcept "
         "nodes and AlzKB entities using their shared SNOMED-CT/LOINC codes as join keys. This "
         "was impossible with application-specific strings."),
        ("<b>Phase 4 (Defense Prep):</b> The IS_A hierarchies provide ready-made thesis figures. "
         "The semantic layer demonstrates the knowledge engineering contribution &mdash; the systematic "
         "methodology for transforming a clinical LPG into a semantically interoperable KG."),
    ]
    for item in future_items:
        story.append(Paragraph(f"&bull; {item}", styles["BulletItem"]))
    story.append(Spacer(1, 6 * mm))

    # ── Graph Statistics Summary ──
    story.append(Paragraph("Graph Statistics After Phase 1", styles["SubSectionHead"]))
    stats_data = [
        ["Metric", "Count"],
        ["Total nodes (original)", "~407,000"],
        ["OntologyConcept nodes (ICD-10)", "5"],
        ["OntologyConcept nodes (SNOMED/LOINC/UBERON/HPO)", "47"],
        ["Total OntologyConcept nodes", "52"],
        ["Original relationships", "~1,160,000"],
        ["CLASSIFIED_AS edges (Diagnosis -> ICD-10)", "25,946"],
        ["MAPS_TO edges (data -> ontology)", "100,770"],
        ["IS_A edges (hierarchy)", "27"],
        ["Total new semantic edges", "126,743"],
        ["Relationship types with URI property", "30"],
        ["Relationships with URI property", "~1,200,000"],
        ["Uniqueness constraints", "12"],
        ["Performance indexes", "15"],
    ]
    t4 = Table(stats_data, colWidths=[220, 100])
    t4.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor("#0D47A1")),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor("#FFFFFF")),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor("#FFFFFF"), HexColor("#F5F5F5")]),
    ]))
    story.append(t4)
    story.append(Paragraph(
        "Table 4: Complete graph statistics after Phase 1 completion.",
        styles["Caption"]
    ))
    story.append(Spacer(1, 10 * mm))

    story.append(Paragraph(
        "<i>Report generated on February 24, 2026. Phase 1 (Steps 17&ndash;20) complete. "
        "Next: Phase 2 &mdash; Causal Discovery (Steps 21&ndash;23).</i>",
        styles["Caption"]
    ))

    # Build PDF
    doc.build(story)
    return pdf_path


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("ADNI KG Graph Classification Report Generator")
    print("=" * 60)

    # Generate SVG diagrams
    print("\nGenerating SVG diagrams...")
    svg_paths = []

    svg_paths.append(generate_lpg_before_svg())
    print(f"  1/5  {svg_paths[-1].name}")

    svg_paths.append(generate_kg_after_svg())
    print(f"  2/5  {svg_paths[-1].name}")

    svg_paths.append(generate_transformation_pipeline_svg())
    print(f"  3/5  {svg_paths[-1].name}")

    svg_paths.append(generate_ontology_layer_svg())
    print(f"  4/5  {svg_paths[-1].name}")

    svg_paths.append(generate_lpg_vs_kg_comparison_svg())
    print(f"  5/5  {svg_paths[-1].name}")

    # Generate PDF
    print("\nGenerating PDF report...")
    pdf_path = generate_pdf(svg_paths)
    print(f"\n  PDF: {pdf_path}")
    print(f"  SVGs: {IMAGES_DIR}")
    print("\nDone.")


if __name__ == "__main__":
    main()
