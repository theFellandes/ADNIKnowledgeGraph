"""
Direct Neo4j ADNI Knowledge Graph Explorer
Streamlit app that connects directly to Neo4j without FastAPI backend

Run with:
    streamlit run direct_neo4j_streamlit.py
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_agraph import agraph, Node, Edge, Config
from neo4j import GraphDatabase, basic_auth
import os
from typing import List, Dict, Any, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════ CONFIGURATION ═══════════════════════════
# Neo4j Configuration - Update these with your credentials
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "your_password")  # CHANGE THIS!

CACHE_TTL = 300  # 5 minutes cache

# Enhanced color palette for different node types
COLORS = {
    "patient": "#FF6B6B",      # Red for patient
    "mri": "#4ECDC4",          # Teal for MRI
    "pet": "#45B7D1",          # Blue for PET
    "clinical": "#96CEB4",     # Green for clinical findings
    "family": "#FFEAA7",       # Yellow for family
    "genetic": "#DDA0DD",      # Purple for genetic
    "pathway": "#FFB347",      # Orange for pathways
    "temporal": "#B0C4DE",     # Light blue for temporal
    "assessment": "#F0E68C",   # Khaki for assessments
    "default": "#D3D3D3"       # Gray for others
}

# ═══════════════════════════ NEO4J CONNECTION ═══════════════════════════
@st.cache_resource
def get_neo4j_driver():
    """Initialize and cache Neo4j driver"""
    try:
        driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_lifetime=300
        )
        # Test connection
        with driver.session() as session:
            session.run("RETURN 1").single()
        return driver
    except Exception as e:
        st.error(f"❌ Failed to connect to Neo4j: {e}")
        st.info("Please check your Neo4j credentials in the script configuration.")
        return None

def run_neo4j_query(query: str, **params):
    """Execute Neo4j query with error handling"""
    driver = get_neo4j_driver()
    if driver is None:
        return []

    try:
        with driver.session() as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]
    except Exception as e:
        st.error(f"Query error: {e}")
        logger.error(f"Neo4j query failed: {e}")
        return []

# ═══════════════════════════ CYPHER QUERIES ═══════════════════════════
# Database statistics
QUERY_STATS = """
MATCH (p:Patient) WITH count(p) AS patients
MATCH (img:ImageNode) 
WITH patients, count(img) AS total_images,
     sum(CASE WHEN img.modality_type = 'MRI' THEN 1 ELSE 0 END) AS mri_images,
     sum(CASE WHEN img.modality_type = 'PET' THEN 1 ELSE 0 END) AS pet_images
MATCH (cf:ClinicalFinding) WITH patients, total_images, mri_images, pet_images, count(cf) AS findings
MATCH (fm:FamilyMember) WITH patients, total_images, mri_images, pet_images, findings, count(fm) AS family_members
OPTIONAL MATCH (t:PETTracer) WITH patients, total_images, mri_images, pet_images, findings, family_members, count(t) AS tracers
OPTIONAL MATCH (bp:BiologicalPathway) 
RETURN 
    patients,
    total_images,
    mri_images, 
    pet_images,
    findings,
    family_members,
    tracers,
    count(bp) AS pathways
"""

# Patient list
QUERY_PATIENT_LIST = """
MATCH (p:Patient)
WHERE $search_term IS NULL OR p.ptid CONTAINS $search_term
RETURN p.ptid AS ptid
ORDER BY p.ptid
LIMIT $limit
"""

# Comprehensive patient overview
QUERY_PATIENT_OVERVIEW = """
MATCH (p:Patient {ptid: $ptid})

// Get ParticipantFile and Constitutional data
OPTIONAL MATCH (p)-[:hasGenericDependent]->(pf:ParticipantFile)
OPTIONAL MATCH (pf)-[:hasMemberPartAtAllTimes]->(const:Constitutional)

// Get all image nodes
OPTIONAL MATCH (p)<-[:belongsToPatient]-(img:ImageNode)

// Get imaging hierarchy
OPTIONAL MATCH (p)-[:hasImagingStudy]->(study:ImagingStudy)
OPTIONAL MATCH (study)-[:containsImagingSeries]->(series:ImagingSeries)

// Get diagnoses
OPTIONAL MATCH (p)-[:hasDiagnosis]->(d:Diagnosis)

// Get clinical findings by type
OPTIONAL MATCH (p)<-[:belongsToPatient]-(cf:ClinicalFinding)
OPTIONAL MATCH (p)<-[:belongsToPatient]-(psy:PsychometricFinding)
OPTIONAL MATCH (p)<-[:belongsToPatient]-(bio:BiomarkerFinding)
OPTIONAL MATCH (p)<-[:belongsToPatient]-(gen:GeneticFinding)
OPTIONAL MATCH (p)<-[:belongsToPatient]-(beh:BehavioralFinding)
OPTIONAL MATCH (p)<-[:belongsToPatient]-(imgf:ImageFinding)

// Get family members
OPTIONAL MATCH (p)-[:hasRelative]->(fm:FamilyMember)
OPTIONAL MATCH (p)-[:hasRelative]->(affected_fm:FamilyMember {has_dementia: true})

// Get genetic risk profile
OPTIONAL MATCH (p)-[:hasGeneticRiskProfile]->(grp:GeneticRiskProfile)

// Get temporal regions
OPTIONAL MATCH (p)<-[:belongsToPatient]-(any_finding:ClinicalFinding)-[:existsAt]->(t:ZeroDimensionalTemporalRegion)

// Get assessments
OPTIONAL MATCH (p)-[:undergoesAssessment]->(a:Assessment)

// Get PET tracers and pathways
OPTIONAL MATCH (p)<-[:belongsToPatient]-(pet_img:ImageNode)-[:usesTracer]->(tracer:PETTracer)
WHERE pet_img.modality_type = 'PET'
OPTIONAL MATCH (p)<-[:belongsToPatient]-(path_img:ImageNode)-[:revealsPathwayActivity]->(pathway:BiologicalPathway)

// Get multimodal sessions
OPTIONAL MATCH (p)-[:hasMultimodalSession]->(mms:MultimodalSession)

RETURN 
    p.ptid AS ptid,
    p.rid AS rid,
    p.display_label AS display_label,
    
    // Demographics - try multiple sources
    coalesce(const.age_at_baseline, p.age_at_baseline) AS age_at_baseline,
    coalesce(const.gender, p.gender) AS gender,
    coalesce(const.education_years, p.education_years) AS education_years,
    coalesce(const.race, p.race) AS race,
    
    // Clinical
    collect(DISTINCT d.severity) AS diagnoses,
    collect(DISTINCT cf.clinical_significance) AS clinical_significance_levels,
    
    // Imaging counts
    count(DISTINCT img) AS total_images,
    sum(CASE WHEN img.modality_type = 'MRI' THEN 1 ELSE 0 END) AS mri_images,
    sum(CASE WHEN img.modality_type = 'PET' THEN 1 ELSE 0 END) AS pet_images,
    count(DISTINCT study) AS imaging_studies,
    count(DISTINCT series) AS imaging_series,
    
    // PET specific
    collect(DISTINCT tracer.tracer_name) AS pet_tracers,
    collect(DISTINCT pathway.pathway_name) AS biological_pathways,
    count(DISTINCT mms) AS multimodal_sessions,
    
    // Findings counts
    count(DISTINCT cf) AS total_findings,
    count(DISTINCT psy) AS psychometric_findings,
    count(DISTINCT bio) AS biomarker_findings,
    count(DISTINCT gen) AS genetic_findings,
    count(DISTINCT beh) AS behavioral_findings,
    count(DISTINCT imgf) AS imaging_findings,
    
    // Family & genetic
    count(DISTINCT fm) AS family_members,
    count(DISTINCT affected_fm) AS affected_family_members,
    grp.risk_level AS genetic_risk_level,
    grp.apoe_genotype AS apoe_genotype,
    
    // Temporal & assessments
    count(DISTINCT t) AS temporal_regions,
    count(DISTINCT a) AS assessment_count
"""

# Patient relationships for graph visualization
QUERY_PATIENT_RELATIONS = """
MATCH (p:Patient {ptid: $ptid})

// Get outgoing relationships
OPTIONAL MATCH (p)-[r_out]->(n_out)
WITH p, collect({
    rel: type(r_out), 
    direction: 'OUT', 
    target: n_out,
    target_labels: labels(n_out),
    target_id: coalesce(
        n_out.ptid, n_out.study_id, n_out.series_id, n_out.image_id,
        n_out.finding_id, n_out.member_id, n_out.temporal_id, 
        n_out.assessment_id, n_out.diagnosis_id, n_out.pathway_id,
        n_out.tracer_id, n_out.session_id, toString(id(n_out))
    ),
    target_display: coalesce(
        n_out.display_label, n_out.assessment_name, n_out.pathway_name,
        n_out.tracer_name, n_out.relationship_type, n_out.modality_type,
        n_out.finding_type, labels(n_out)[0]
    ),
    modality_type: n_out.modality_type,
    finding_type: n_out.finding_type,
    relationship_type: n_out.relationship_type
}) AS out_rels

// Get incoming relationships  
OPTIONAL MATCH (n_in)-[r_in]->(p)
WITH p, out_rels, collect({
    rel: type(r_in),
    direction: 'IN',
    target: n_in,
    target_labels: labels(n_in),
    target_id: coalesce(
        n_in.ptid, n_in.study_id, n_in.series_id, n_in.image_id,
        n_in.finding_id, n_in.member_id, n_in.temporal_id,
        n_in.assessment_id, n_in.diagnosis_id, n_in.pathway_id,
        n_in.tracer_id, n_in.session_id, toString(id(n_in))
    ),
    target_display: coalesce(
        n_in.display_label, n_in.assessment_name, n_in.pathway_name,
        n_in.tracer_name, n_in.relationship_type, n_in.modality_type,
        n_in.finding_type, labels(n_in)[0]
    ),
    modality_type: n_in.modality_type,
    finding_type: n_in.finding_type,
    relationship_type: n_in.relationship_type
}) AS in_rels

// Combine and return
UNWIND (out_rels + in_rels) AS rel_info
WHERE rel_info.target IS NOT NULL

RETURN 
    rel_info.rel AS rel,
    rel_info.direction AS direction,
    rel_info.target_labels AS target_labels,
    rel_info.target_id AS target_id,
    rel_info.target_display AS target_display,
    rel_info.modality_type AS modality_type,
    rel_info.finding_type AS finding_type,
    rel_info.relationship_type AS relationship_type

LIMIT $limit
"""

# Imaging details
QUERY_IMAGING_DETAILS = """
MATCH (p:Patient {ptid: $ptid})<-[:belongsToPatient]-(img:ImageNode)
RETURN 
    img.image_id AS image_id,
    img.modality_type AS modality_type,
    img.modality AS modality,
    img.study_date AS study_date,
    img.series_description AS series_description,
    img.anatomical_region AS anatomical_region,
    img.pet_tracer AS pet_tracer,
    coalesce(img.has_blob, false) AS has_blob,
    img.slice_thickness AS slice_thickness
ORDER BY img.study_date DESC
LIMIT $limit
"""

# Family details
QUERY_FAMILY_DETAILS = """
MATCH (p:Patient {ptid: $ptid})-[:hasRelative]->(fm:FamilyMember)
RETURN 
    fm.member_id AS member_id,
    fm.relationship_type AS relationship_type,
    fm.gender AS gender,
    fm.has_dementia AS has_dementia,
    fm.age_at_onset AS age_at_onset
ORDER BY fm.relationship_type, fm.member_id
"""

# Clinical findings
QUERY_FINDINGS_DETAILS = """
MATCH (p:Patient {ptid: $ptid})<-[:belongsToPatient]-(cf:ClinicalFinding)
RETURN 
    cf.finding_id AS finding_id,
    cf.finding_type AS finding_type,
    cf.finding_subtype AS finding_subtype,
    cf.months AS months,
    cf.viscode AS viscode,
    cf.clinical_significance AS clinical_significance,
    cf.confidence_score AS confidence_score,
    cf.assessment_name AS assessment_name,
    cf.table_source AS table_source,
    labels(cf) AS finding_labels
ORDER BY cf.months, cf.finding_type
LIMIT $limit
"""

# ═══════════════════════════ CACHED DATA FUNCTIONS ═══════════════════════════
@st.cache_data(ttl=CACHE_TTL)
def get_database_stats():
    """Get overall database statistics"""
    results = run_neo4j_query(QUERY_STATS)
    return results[0] if results else {}

@st.cache_data(ttl=CACHE_TTL)
def get_patient_list(search_term: str = None, limit: int = 1000):
    """Get list of patient IDs"""
    results = run_neo4j_query(QUERY_PATIENT_LIST, search_term=search_term, limit=limit)
    return [r['ptid'] for r in results]

@st.cache_data(ttl=CACHE_TTL)
def get_patient_overview(ptid: str):
    """Get comprehensive patient overview"""
    results = run_neo4j_query(QUERY_PATIENT_OVERVIEW, ptid=ptid)
    if results:
        data = results[0]
        # Clean up list fields
        for field in ['diagnoses', 'clinical_significance_levels', 'pet_tracers', 'biological_pathways']:
            if field in data and data[field]:
                data[field] = [x for x in data[field] if x is not None and x != '']
            else:
                data[field] = []
        return data
    return None

@st.cache_data(ttl=CACHE_TTL)
def get_patient_relations(ptid: str, limit: int = 100):
    """Get patient relationships for graph visualization"""
    return run_neo4j_query(QUERY_PATIENT_RELATIONS, ptid=ptid, limit=limit)

@st.cache_data(ttl=CACHE_TTL)
def get_patient_imaging(ptid: str, limit: int = 100):
    """Get patient imaging details"""
    return run_neo4j_query(QUERY_IMAGING_DETAILS, ptid=ptid, limit=limit)

@st.cache_data(ttl=CACHE_TTL)
def get_patient_family(ptid: str):
    """Get patient family members"""
    return run_neo4j_query(QUERY_FAMILY_DETAILS, ptid=ptid)

@st.cache_data(ttl=CACHE_TTL)
def get_patient_findings(ptid: str, limit: int = 100):
    """Get patient clinical findings"""
    return run_neo4j_query(QUERY_FINDINGS_DETAILS, ptid=ptid, limit=limit)

# ═══════════════════════════ VISUALIZATION FUNCTIONS ═══════════════════════════
def get_node_color_and_shape(labels: List[str], modality_type: str = None,
                            finding_type: str = None, relationship_type: str = None):
    """Determine node color and shape based on type"""
    if "Patient" in labels:
        return COLORS["patient"], "dot"
    elif "ImageNode" in labels:
        if modality_type == "MRI":
            return COLORS["mri"], "triangle"
        elif modality_type == "PET":
            return COLORS["pet"], "diamond"
        else:
            return COLORS["default"], "triangle"
    elif any(x in labels for x in ["ClinicalFinding", "PsychometricFinding", "BiomarkerFinding"]):
        return COLORS["clinical"], "circle"
    elif "FamilyMember" in labels:
        return COLORS["family"], "square"
    elif any(x in labels for x in ["GeneticRiskProfile", "GeneticFinding"]):
        return COLORS["genetic"], "star"
    elif "BiologicalPathway" in labels:
        return COLORS["pathway"], "hexagon"
    elif "ZeroDimensionalTemporalRegion" in labels:
        return COLORS["temporal"], "dot"
    elif "Assessment" in labels:
        return COLORS["assessment"], "triangle"
    else:
        return COLORS["default"], "dot"

def build_knowledge_graph(ptid: str, relations: List[Dict]):
    """Build interactive knowledge graph"""
    nodes = [Node(id=ptid, label=f"Patient\n{ptid}", size=40, shape="dot", color=COLORS["patient"])]
    edges = []
    seen_nodes = {ptid}

    for rel in relations:
        target_id = str(rel["target_id"])
        if target_id not in seen_nodes:
            color, shape = get_node_color_and_shape(
                rel["target_labels"],
                rel.get("modality_type"),
                rel.get("finding_type"),
                rel.get("relationship_type")
            )

            display_name = rel["target_display"] or rel["target_labels"][0]
            if len(display_name) > 20:
                display_name = display_name[:17] + "..."

            nodes.append(Node(id=target_id, label=display_name, size=20, shape=shape, color=color))
            seen_nodes.add(target_id)

        # Edge styling
        edge_color = COLORS["default"]
        rel_type = rel["rel"].lower()
        if "imaging" in rel_type or "image" in rel_type:
            edge_color = COLORS["mri"]
        elif "family" in rel_type or "relative" in rel_type:
            edge_color = COLORS["family"]
        elif "genetic" in rel_type:
            edge_color = COLORS["genetic"]
        elif "pathway" in rel_type:
            edge_color = COLORS["pathway"]

        # Direction indicator
        edge_label = f"← {rel['rel']}" if rel["direction"] == "IN" else rel["rel"]

        edges.append(Edge(source=ptid, target=target_id, label=edge_label, color=edge_color, width=2))

    return nodes, edges

def create_imaging_timeline(imaging_data: List[Dict]):
    """Create timeline visualization for imaging studies"""
    if not imaging_data:
        return None

    df = pd.DataFrame(imaging_data)
    df['study_date'] = pd.to_datetime(df['study_date'], errors='coerce')
    df = df.dropna(subset=['study_date'])

    if df.empty:
        return None

    fig = px.scatter(df, x='study_date', y='modality_type',
                     color='modality_type', symbol='pet_tracer',
                     hover_data=['series_description', 'anatomical_region'],
                     title="Imaging Studies Timeline")

    fig.update_layout(height=400, xaxis_title="Study Date", yaxis_title="Modality")
    return fig

def create_findings_distribution(findings_data: List[Dict]):
    """Create distribution chart for clinical findings"""
    if not findings_data:
        return None

    df = pd.DataFrame(findings_data)
    type_counts = df['finding_type'].value_counts()
    fig = px.pie(values=type_counts.values, names=type_counts.index, title="Clinical Findings Distribution")
    return fig

def create_temporal_progression(findings_data: List[Dict]):
    """Create temporal progression chart"""
    if not findings_data:
        return None

    df = pd.DataFrame(findings_data)
    df = df.sort_values('months')

    temporal_df = df.groupby(['months', 'clinical_significance']).size().reset_index(name='count')
    fig = px.bar(temporal_df, x='months', y='count', color='clinical_significance',
                 title="Clinical Findings Over Time")
    fig.update_layout(height=400, xaxis_title="Months from Baseline", yaxis_title="Number of Findings")
    return fig

# ═══════════════════════════ STREAMLIT UI ═══════════════════════════
def main():
    st.set_page_config("ADNI Knowledge Graph Explorer", layout="wide",
                       page_icon="🧠", initial_sidebar_state="expanded")

    # Header
    st.title("🧠 ADNI Knowledge Graph Explorer")
    st.markdown("*Direct Neo4j Connection - Enhanced Pipeline Data*")

    # Test Neo4j connection
    driver = get_neo4j_driver()
    if driver is None:
        st.stop()

    # Get and display statistics
    stats = get_database_stats()
    if stats:
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Patients", stats.get("patients", 0))
        with col2:
            st.metric("MRI Images", stats.get("mri_images", 0))
        with col3:
            st.metric("PET Images", stats.get("pet_images", 0))
        with col4:
            st.metric("Findings", stats.get("findings", 0))
        with col5:
            st.metric("Family Members", stats.get("family_members", 0))

    st.divider()

    # ═══════════════════════════ SIDEBAR ═══════════════════════════
    st.sidebar.title("🔍 Patient Selection")
    st.sidebar.info(f"Connected to: `{NEO4J_URI}`")

    # Get patient list
    patient_ids = get_patient_list(limit=5000)

    if not patient_ids:
        st.sidebar.error("No patients found in database")
        st.error("No patient data found. Please ensure your pipeline has completed successfully.")
        st.stop()

    # Selection mode
    selection_mode = st.sidebar.radio(
        "Selection Mode",
        ["Dropdown", "Search"],
        horizontal=True
    )

    # Patient selection
    if selection_mode == "Dropdown":
        selected_ptid = st.sidebar.selectbox(
            "Select Patient ID",
            patient_ids,
            help="Choose from available patients"
        )
    else:
        search_term = st.sidebar.text_input(
            "Search Patient ID",
            placeholder="Type patient ID...",
            help="Enter partial or complete patient ID"
        )

        if search_term and len(search_term) >= 3:
            filtered_patients = [p for p in patient_ids if search_term.upper() in p.upper()]
            if filtered_patients:
                selected_ptid = st.sidebar.selectbox("Matching Patients", filtered_patients)
            else:
                st.sidebar.warning("No matching patients found")
                selected_ptid = None
        else:
            selected_ptid = None

    # Display options
    st.sidebar.divider()
    st.sidebar.subheader("⚙️ Display Options")
    max_relations = st.sidebar.slider("Max Relations", 10, 200, 100)
    show_advanced = st.sidebar.checkbox("Show Advanced Analytics", False)

    # Color legend
    st.sidebar.divider()
    st.sidebar.subheader("🎨 Node Colors")
    st.sidebar.markdown(f"""
    <div style="font-size: 11px;">
    🔴 Patient<br>
    🟢 MRI Images<br>
    🔵 PET Images<br>
    🟡 Family Members<br>
    🟣 Genetic Data<br>
    🟠 Pathways<br>
    🟤 Clinical Findings
    </div>
    """, unsafe_allow_html=True)

    # ═══════════════════════════ MAIN CONTENT ═══════════════════════════
    if not selected_ptid:
        st.info("👆 Please select a patient to explore their data")

        # Show some sample patients
        if patient_ids:
            st.subheader("📋 Available Patients (Sample)")
            sample_patients = patient_ids[:20]  # Show first 20
            cols = st.columns(4)
            for i, ptid in enumerate(sample_patients):
                with cols[i % 4]:
                    if st.button(ptid, key=f"sample_{i}"):
                        st.rerun()
        st.stop()

    # Load patient data
    with st.spinner("Loading patient data..."):
        patient = get_patient_overview(selected_ptid)

        if not patient:
            st.error(f"Patient {selected_ptid} not found or has no data")
            st.stop()

        relations = get_patient_relations(selected_ptid, max_relations)
        imaging_data = get_patient_imaging(selected_ptid)
        family_data = get_patient_family(selected_ptid)
        findings_data = get_patient_findings(selected_ptid)

    # ═══════════════════════════ PATIENT OVERVIEW ═══════════════════════════
    st.header(f"👤 Patient: {selected_ptid}")

    # Basic demographics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        age = patient.get('age_at_baseline')
        st.metric("Age at Baseline", f"{age} years" if age else "N/A")
    with col2:
        st.metric("Gender", patient.get('gender', 'N/A'))
    with col3:
        edu = patient.get('education_years')
        st.metric("Education", f"{edu} years" if edu else "N/A")
    with col4:
        st.metric("RID", patient.get('rid', 'N/A'))

    # Clinical overview
    st.subheader("🏥 Clinical Overview")
    col1, col2, col3 = st.columns(3)
    with col1:
        diagnoses = patient.get('diagnoses', [])
        st.write("**Diagnoses:**", ", ".join(diagnoses) if diagnoses else "None")
    with col2:
        significance = patient.get('clinical_significance_levels', [])
        st.write("**Clinical Significance:**", ", ".join(set(significance)) if significance else "N/A")
    with col3:
        st.write("**Temporal Regions:**", f"{patient.get('temporal_regions', 0)} timepoints")

    # ═══════════════════════════ TABBED INTERFACE ═══════════════════════════
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🖼️ Imaging", "👨‍👩‍👧‍👦 Family & Genetic", "📋 Clinical Findings",
        "🕸️ Knowledge Graph", "📊 Analytics"
    ])

    # ─── TAB 1: IMAGING ───
    with tab1:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Images", patient.get('total_images', 0))
        with col2:
            st.metric("MRI Images", patient.get('mri_images', 0))
        with col3:
            st.metric("PET Images", patient.get('pet_images', 0))
        with col4:
            st.metric("Imaging Studies", patient.get('imaging_studies', 0))

        # PET-specific info
        if patient.get('pet_images', 0) > 0:
            st.subheader("🧠 PET Information")
            col1, col2 = st.columns(2)
            with col1:
                tracers = patient.get('pet_tracers', [])
                st.write("**Tracers:**", ", ".join(tracers) if tracers else "None")
            with col2:
                pathways = patient.get('biological_pathways', [])
                st.write("**Pathways:**", ", ".join(pathways) if pathways else "None")

        # Imaging timeline
        if imaging_data:
            timeline_fig = create_imaging_timeline(imaging_data)
            if timeline_fig:
                st.plotly_chart(timeline_fig, use_container_width=True)

            st.subheader("📋 Imaging Details")
            imaging_df = pd.DataFrame(imaging_data)
            st.dataframe(imaging_df, use_container_width=True, height=300)
        else:
            st.info("No imaging data available")

    # ─── TAB 2: FAMILY & GENETIC ───
    with tab2:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("🧬 Genetic Information")
            st.metric("Genetic Risk", patient.get('genetic_risk_level', 'N/A'))
            st.metric("APOE Genotype", patient.get('apoe_genotype', 'N/A'))
            st.metric("Genetic Findings", patient.get('genetic_findings', 0))

        with col2:
            st.subheader("👨‍👩‍👧‍👦 Family Information")
            st.metric("Family Members", patient.get('family_members', 0))
            st.metric("Affected Members", patient.get('affected_family_members', 0))

        if family_data:
            st.subheader("👥 Family Details")
            family_df = pd.DataFrame(family_data)
            family_df['dementia_status'] = family_df['has_dementia'].map({
                True: "🔴 Affected", False: "🟢 Unaffected", None: "❓ Unknown"
            })
            st.dataframe(family_df, use_container_width=True)
        else:
            st.info("No family data available")

    # ─── TAB 3: CLINICAL FINDINGS ───
    with tab3:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Findings", patient.get('total_findings', 0))
        with col2:
            st.metric("Psychometric", patient.get('psychometric_findings', 0))
        with col3:
            st.metric("Biomarker", patient.get('biomarker_findings', 0))
        with col4:
            st.metric("Imaging Findings", patient.get('imaging_findings', 0))

        if findings_data:
            col1, col2 = st.columns(2)
            with col1:
                dist_fig = create_findings_distribution(findings_data)
                if dist_fig:
                    st.plotly_chart(dist_fig, use_container_width=True)

            with col2:
                temporal_fig = create_temporal_progression(findings_data)
                if temporal_fig:
                    st.plotly_chart(temporal_fig, use_container_width=True)

            st.subheader("📋 Clinical Findings Details")
            findings_df = pd.DataFrame(findings_data)

            # Filters
            col1, col2, col3 = st.columns(3)
            with col1:
                finding_types = st.multiselect(
                    "Finding Type",
                    options=findings_df['finding_type'].unique(),
                    default=findings_df['finding_type'].unique()
                )
            with col2:
                significance_levels = st.multiselect(
                    "Clinical Significance",
                    options=findings_df['clinical_significance'].unique(),
                    default=findings_df['clinical_significance'].unique()
                )

            # Apply filters
            filtered_df = findings_df[
                (findings_df['finding_type'].isin(finding_types)) &
                (findings_df['clinical_significance'].isin(significance_levels))
            ]

            st.dataframe(filtered_df, use_container_width=True, height=400)
        else:
            st.info("No clinical findings available")

    # ─── TAB 4: KNOWLEDGE GRAPH ───
    with tab4:
        st.subheader("🕸️ Patient Knowledge Graph")

        if relations:
            col1, col2 = st.columns([3, 1])

            with col2:
                st.write("**Graph Settings**")
                physics = st.checkbox("Physics", True)
                highlight = st.checkbox("Highlighting", True)
                height = st.slider("Height", 400, 800, 600)

            with col1:
                nodes, edges = build_knowledge_graph(selected_ptid, relations)
                config = Config(
                    height=height,
                    physics=physics,
                    nodeHighlightBehavior=highlight,
                    directed=True
                )
                agraph(nodes, edges, config)

            # Relationship summary
            st.subheader("📊 Relationships Summary")
            rel_df = pd.DataFrame(relations)
            if not rel_df.empty:
                rel_summary = rel_df.groupby(['rel', 'direction']).size().reset_index(name='count')
                rel_summary['relationship'] = rel_summary['direction'] + ': ' + rel_summary['rel']

                fig = px.bar(rel_summary, x='relationship', y='count',
                           title="Relationship Distribution")
                fig.update_xaxis(tickangle=45)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No relationships found for this patient")

    # ─── TAB 5: ANALYTICS ───
    with tab5:
        st.subheader("📈 Patient Analytics")

        # Risk Assessment
        st.subheader("⚠️ Risk Assessment")
        risk_factors = []

        if patient.get('affected_family_members', 0) > 0:
            risk_factors.append(f"Family History: {patient.get('affected_family_members')} affected relatives")

        genetic_risk = patient.get('genetic_risk_level')
        if genetic_risk and genetic_risk != 'normal':
            risk_factors.append(f"Genetic Risk: {genetic_risk}")

        apoe = patient.get('apoe_genotype')
        if apoe and '4' in str(apoe):
            risk_factors.append(f"APOE4 Carrier: {apoe}")

        if risk_factors:
            for factor in risk_factors:
                st.warning(factor)
        else:
            st.success("No major risk factors identified")

        # Data completeness
        st.subheader("📊 Data Completeness")
        has_imaging = 1 if patient.get('total_images', 0) > 0 else 0
        has_findings = 1 if patient.get('total_findings', 0) > 0 else 0
        has_family = 1 if patient.get('family_members', 0) > 0 else 0
        has_genetic = 1 if patient.get('genetic_findings', 0) > 0 else 0

        completeness = (has_imaging + has_findings + has_family + has_genetic) / 4 * 100
        st.metric("Data Completeness", f"{completeness:.1f}%")

        # Advanced analytics
        if show_advanced:
            st.subheader("🔬 Advanced Analytics")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Assessments", patient.get('assessment_count', 0))
                st.metric("Temporal Coverage", f"{patient.get('temporal_regions', 0)} timepoints")
            with col2:
                st.metric("Multimodal Sessions", patient.get('multimodal_sessions', 0))
                st.metric("Imaging Series", patient.get('imaging_series', 0))

if __name__ == "__main__":
    main()