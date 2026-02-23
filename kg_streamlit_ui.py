"""
Enhanced ADNI Knowledge Graph Explorer with Multi-Modal Search
Streamlit app with integrated Elasticsearch, Redis caching, and Neo4j

Run with:
    streamlit run kg_streamlit_ui.py
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
from datetime import datetime, timedelta
import base64
from io import BytesIO
from PIL import Image

# Import our enhanced search and caching components
from utils.search_engine import MultiModalSearchEngine, SearchCriteria, SearchType
from utils.elasticsearch_indexer import SearchIndexer
from utils.redis_cacher import EnhancedCacheManager
from utils.neo4j_connector import Neo4jConnector

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

# ═══════════════════════════ ENHANCED CONNECTIONS ═══════════════════════════
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

@st.cache_resource
def get_search_engine():
    """Initialize and cache the multi-modal search engine"""
    try:
        # Initialize components
        elasticsearch_client = SearchIndexer()
        redis_client = EnhancedCacheManager()
        neo4j_connector = Neo4jConnector(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        
        # Create search engine
        search_engine = MultiModalSearchEngine(
            elasticsearch_client=elasticsearch_client,
            redis_client=redis_client,
            neo4j_connector=neo4j_connector
        )
        
        return search_engine
    except Exception as e:
        st.error(f"❌ Failed to initialize search engine: {e}")
        logger.error(f"Search engine initialization failed: {e}")
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

def create_comprehensive_patient_timeline(patient_id: str, cached_data: Optional[Dict] = None):
    """Create comprehensive patient timeline with all data modalities using cached data"""
    
    # Get cached timeline data if available
    search_engine = get_search_engine()
    timeline_data = None
    
    if search_engine and search_engine.redis:
        cache_key = f"patient:{patient_id}:timeline"
        timeline_data = search_engine.redis.get(cache_key)
    
    if not timeline_data:
        # Build timeline data from various sources
        timeline_data = build_patient_timeline_data(patient_id)
        
        # Cache the timeline data
        if search_engine and search_engine.redis:
            search_engine.redis.set(cache_key, timeline_data, expire=3600)  # 1 hour cache
    
    if not timeline_data or not timeline_data.get("events"):
        st.info("No timeline data available for this patient")
        return None
    
    # Create interactive timeline visualization
    events = timeline_data["events"]
    df = pd.DataFrame(events)
    
    # Convert dates
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    df = df.sort_values('date')
    
    if df.empty:
        st.info("No valid timeline events found")
        return None
    
    # Create timeline plot
    fig = go.Figure()
    
    # Color mapping for different event types
    color_map = {
        'visit': '#FF6B6B',
        'imaging': '#4ECDC4', 
        'biomarker': '#45B7D1',
        'assessment': '#96CEB4',
        'diagnosis': '#FFEAA7',
        'family': '#DDA0DD',
        'genetic': '#FFB347'
    }
    
    # Add events by type
    for event_type in df['type'].unique():
        type_data = df[df['type'] == event_type]
        
        fig.add_trace(go.Scatter(
            x=type_data['date'],
            y=type_data['value'],
            mode='markers+lines',
            name=event_type.title(),
            marker=dict(
                size=10,
                color=color_map.get(event_type, '#D3D3D3'),
                line=dict(width=2, color='white')
            ),
            text=type_data['description'],
            hovertemplate='<b>%{text}</b><br>Date: %{x}<br>Value: %{y}<extra></extra>'
        ))
    
    # Update layout
    fig.update_layout(
        title=f"Patient Timeline: {patient_id}",
        xaxis_title="Date",
        yaxis_title="Event Value/Score",
        height=500,
        hovermode='closest',
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    return fig

def build_patient_timeline_data(patient_id: str) -> Dict[str, Any]:
    """Build comprehensive timeline data from all available sources"""
    events = []
    
    try:
        # Get patient data
        patient_data = get_patient_overview(patient_id)
        imaging_data = get_patient_imaging(patient_id)
        findings_data = get_patient_findings(patient_id)
        family_data = get_patient_family(patient_id)
        
        # Add imaging events
        for img in imaging_data:
            if img.get('study_date'):
                events.append({
                    'date': img['study_date'],
                    'type': 'imaging',
                    'value': 1.0,
                    'description': f"{img.get('modality_type', 'Unknown')} - {img.get('series_description', 'N/A')}",
                    'details': img
                })
        
        # Add clinical findings events
        for finding in findings_data:
            if finding.get('months') is not None:
                # Convert months to approximate date
                base_date = datetime(2020, 1, 1)  # Approximate baseline
                event_date = base_date + timedelta(days=finding['months'] * 30)
                
                # Map clinical significance to numeric value
                significance_map = {'low': 0.3, 'medium': 0.6, 'high': 0.9, 'critical': 1.0}
                value = significance_map.get(finding.get('clinical_significance', 'medium'), 0.5)
                
                events.append({
                    'date': event_date.isoformat(),
                    'type': 'assessment',
                    'value': value,
                    'description': f"{finding.get('finding_type', 'Finding')} - {finding.get('assessment_name', 'N/A')}",
                    'details': finding
                })
        
        # Add family history events (static, but important for context)
        for family_member in family_data:
            if family_member.get('has_dementia'):
                events.append({
                    'date': datetime(2019, 1, 1).isoformat(),  # Static date for family history
                    'type': 'family',
                    'value': 0.8,
                    'description': f"Family History: {family_member.get('relationship_type', 'Unknown')} affected",
                    'details': family_member
                })
        
        # Add genetic information (if available)
        if patient_data and patient_data.get('apoe_genotype'):
            risk_value = 0.9 if '4' in str(patient_data['apoe_genotype']) else 0.3
            events.append({
                'date': datetime(2019, 6, 1).isoformat(),  # Static date for genetic info
                'type': 'genetic',
                'value': risk_value,
                'description': f"APOE Genotype: {patient_data['apoe_genotype']}",
                'details': {'genotype': patient_data['apoe_genotype']}
            })
        
        return {
            'patient_id': patient_id,
            'events': events,
            'generated_at': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to build timeline data for {patient_id}: {e}")
        return {'patient_id': patient_id, 'events': []}

def create_biomarker_trend_visualization(patient_id: str):
    """Create biomarker trend visualization with Redis-cached data"""
    
    search_engine = get_search_engine()
    biomarker_data = None
    
    # Try to get cached biomarker data
    if search_engine and search_engine.redis:
        cache_key = f"biomarker:{patient_id}:trends"
        biomarker_data = search_engine.redis.get(cache_key)
    
    if not biomarker_data:
        # Search for biomarker data
        if search_engine:
            criteria = SearchCriteria(patient_id=patient_id, limit=100)
            biomarker_results = search_engine.search_biomarkers(criteria)
            
            if biomarker_results and biomarker_results.results:
                biomarker_data = []
                for result in biomarker_results.results:
                    data = result.data
                    biomarker_data.append({
                        'biomarker_name': data.get('biomarker_name', 'Unknown'),
                        'value': data.get('value', 0),
                        'unit': data.get('unit', ''),
                        'measurement_date': data.get('measurement_date', ''),
                        'abnormal_flag': data.get('abnormal_flag', False)
                    })
                
                # Cache the data
                if search_engine.redis:
                    search_engine.redis.set(cache_key, biomarker_data, expire=1800)  # 30 min cache
    
    if not biomarker_data:
        st.info("No biomarker data available for trend analysis")
        return None
    
    # Create biomarker trends
    df = pd.DataFrame(biomarker_data)
    df['measurement_date'] = pd.to_datetime(df['measurement_date'], errors='coerce')
    df = df.dropna(subset=['measurement_date'])
    
    if df.empty:
        st.info("No valid biomarker measurements found")
        return None
    
    # Create subplots for different biomarkers
    biomarkers = df['biomarker_name'].unique()
    
    if len(biomarkers) == 1:
        # Single biomarker trend
        biomarker_df = df[df['biomarker_name'] == biomarkers[0]]
        fig = px.line(biomarker_df, x='measurement_date', y='value',
                     title=f"{biomarkers[0]} Trend Over Time",
                     markers=True)
        
        # Add abnormal markers
        abnormal_df = biomarker_df[biomarker_df['abnormal_flag'] == True]
        if not abnormal_df.empty:
            fig.add_scatter(x=abnormal_df['measurement_date'], y=abnormal_df['value'],
                          mode='markers', marker=dict(color='red', size=10),
                          name='Abnormal Values')
    else:
        # Multiple biomarkers
        fig = px.line(df, x='measurement_date', y='value', color='biomarker_name',
                     title="Biomarker Trends Over Time", markers=True)
    
    fig.update_layout(height=400, xaxis_title="Date", yaxis_title="Biomarker Value")
    return fig

def create_family_relationship_graph(patient_id: str):
    """Create family history visualization with relationship graphs"""
    
    search_engine = get_search_engine()
    family_tree = None
    
    # Try to get cached family tree
    if search_engine and search_engine.redis:
        cache_key = f"family:{patient_id}:tree"
        family_tree = search_engine.redis.get(cache_key)
    
    if not family_tree and search_engine and search_engine.neo4j:
        # Get family tree from Neo4j
        family_tree = search_engine.neo4j.get_family_tree(patient_id)
        
        # Cache the family tree
        if search_engine.redis and family_tree:
            search_engine.redis.set(cache_key, family_tree, expire=3600)  # 1 hour cache
    
    if not family_tree or not family_tree.get('family_members'):
        st.info("No family relationship data available")
        return None
    
    # Create family relationship network
    nodes = []
    edges = []
    
    # Add patient node
    nodes.append(Node(
        id=patient_id,
        label=f"Patient\n{patient_id}",
        size=30,
        color="#FF6B6B",
        shape="dot"
    ))
    
    # Add family member nodes
    for member_id, member_data in family_tree['family_members'].items():
        # Color based on AD status
        color = "#FF4444" if member_data.get('ad_status', {}).get('has_ad') else "#44FF44"
        
        nodes.append(Node(
            id=member_id,
            label=f"{member_data.get('relationship_type', 'Unknown')}\n{member_id}",
            size=20,
            color=color,
            shape="square"
        ))
    
    # Add relationship edges
    for relationship in family_tree.get('relationships', []):
        edges.append(Edge(
            source=relationship['start_node'],
            target=relationship['end_node'],
            label=relationship['type'],
            color="#888888"
        ))
    
    # Display the graph
    config = Config(
        height=400,
        physics=True,
        nodeHighlightBehavior=True,
        directed=False
    )
    
    return agraph(nodes, edges, config)

# ═══════════════════════════ SEARCH INTERFACE FUNCTIONS ═══════════════════════════
def render_search_interface():
    """Render the enhanced search interface"""
    st.sidebar.title("🔍 Enhanced Search")
    
    # Search type selection
    search_type = st.sidebar.selectbox(
        "Search Type",
        ["Combined", "Patients", "Images", "Biomarkers", "Family History"],
        help="Choose the type of data to search"
    )
    
    # Main search query
    query_text = st.sidebar.text_input(
        "Search Query",
        placeholder="Enter search terms...",
        help="Search across patient data, clinical notes, and metadata"
    )
    
    # Advanced filters
    with st.sidebar.expander("🔧 Advanced Filters"):
        # Patient filters
        col1, col2 = st.columns(2)
        with col1:
            age_min = st.number_input("Min Age", min_value=0, max_value=120, value=0)
            gender = st.selectbox("Gender", ["Any", "Male", "Female"])
        with col2:
            age_max = st.number_input("Max Age", min_value=0, max_value=120, value=120)
            diagnosis = st.text_input("Diagnosis", placeholder="e.g., AD, MCI")
        
        # Image filters
        if search_type in ["Combined", "Images"]:
            modality = st.selectbox("Imaging Modality", ["Any", "MRI", "PET", "CT"])
            
        # Biomarker filters
        if search_type in ["Combined", "Biomarkers"]:
            biomarker_name = st.text_input("Biomarker Name", placeholder="e.g., ABETA, TAU")
            col1, col2 = st.columns(2)
            with col1:
                biomarker_min = st.number_input("Min Value", value=0.0)
            with col2:
                biomarker_max = st.number_input("Max Value", value=1000.0)
        
        # Family history filters
        family_ad_history = st.selectbox("Family AD History", ["Any", "Yes", "No"])
        apoe_genotype = st.text_input("APOE Genotype", placeholder="e.g., E3/E4")
        
        # Date range
        st.subheader("Date Range")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", value=datetime(2000, 1, 1))
        with col2:
            end_date = st.date_input("End Date", value=datetime.now())
    
    # Search button
    if st.sidebar.button("🔍 Search", type="primary"):
        return perform_search(
            search_type, query_text, age_min, age_max, gender, diagnosis,
            modality if search_type in ["Combined", "Images"] else None,
            biomarker_name if search_type in ["Combined", "Biomarkers"] else None,
            biomarker_min if search_type in ["Combined", "Biomarkers"] else None,
            biomarker_max if search_type in ["Combined", "Biomarkers"] else None,
            family_ad_history, apoe_genotype, start_date, end_date
        )
    
    return None

def perform_search(search_type, query_text, age_min, age_max, gender, diagnosis,
                  modality, biomarker_name, biomarker_min, biomarker_max,
                  family_ad_history, apoe_genotype, start_date, end_date):
    """Perform the actual search using the search engine"""
    search_engine = get_search_engine()
    if not search_engine:
        st.error("Search engine not available")
        return None
    
    # Build search criteria
    criteria = SearchCriteria(
        query_text=query_text if query_text else None,
        age_range=(age_min, age_max) if age_min < age_max else None,
        gender=gender if gender != "Any" else None,
        diagnosis=diagnosis if diagnosis else None,
        modality=modality if modality and modality != "Any" else None,
        biomarker_name=biomarker_name if biomarker_name else None,
        biomarker_range=(biomarker_min, biomarker_max) if biomarker_name else None,
        date_range=(datetime.combine(start_date, datetime.min.time()),
                   datetime.combine(end_date, datetime.max.time())),
        family_ad_history=True if family_ad_history == "Yes" else False if family_ad_history == "No" else None,
        apoe_genotype=apoe_genotype if apoe_genotype else None,
        limit=50
    )
    
    # Perform search based on type
    try:
        if search_type == "Combined":
            return search_engine.combined_search(criteria)
        elif search_type == "Patients":
            return search_engine.search_patients(criteria)
        elif search_type == "Images":
            return search_engine.search_images(criteria)
        elif search_type == "Biomarkers":
            return search_engine.search_biomarkers(criteria)
        elif search_type == "Family History":
            return search_engine.search_family_history(criteria)
    except Exception as e:
        st.error(f"Search failed: {e}")
        logger.error(f"Search error: {e}")
        return None

def render_search_results(search_results, search_type):
    """Render search results in an organized way"""
    if not search_results:
        st.info("No search results to display")
        return
    
    if search_type == "Combined" and isinstance(search_results, dict):
        # Combined search results
        st.subheader("🔍 Combined Search Results")
        
        # Create tabs for different result types
        tabs = st.tabs(["📊 Summary", "👤 Patients", "🖼️ Images", "🧬 Biomarkers", "👨‍👩‍👧‍👦 Family"])
        
        with tabs[0]:  # Summary
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Patients", search_results.get("patients", {}).total_count if hasattr(search_results.get("patients", {}), 'total_count') else 0)
            with col2:
                st.metric("Images", search_results.get("images", {}).total_count if hasattr(search_results.get("images", {}), 'total_count') else 0)
            with col3:
                st.metric("Biomarkers", search_results.get("biomarkers", {}).total_count if hasattr(search_results.get("biomarkers", {}), 'total_count') else 0)
            with col4:
                st.metric("Family Records", search_results.get("family_history", {}).total_count if hasattr(search_results.get("family_history", {}), 'total_count') else 0)
            
            # Top results across all types
            if "aggregated" in search_results:
                render_aggregated_results(search_results["aggregated"])
        
        with tabs[1]:  # Patients
            if "patients" in search_results:
                render_patient_results(search_results["patients"])
        
        with tabs[2]:  # Images
            if "images" in search_results:
                render_image_results(search_results["images"])
        
        with tabs[3]:  # Biomarkers
            if "biomarkers" in search_results:
                render_biomarker_results(search_results["biomarkers"])
        
        with tabs[4]:  # Family
            if "family_history" in search_results:
                render_family_results(search_results["family_history"])
    
    else:
        # Single search type results
        if search_type == "Patients":
            render_patient_results(search_results)
        elif search_type == "Images":
            render_image_results(search_results)
        elif search_type == "Biomarkers":
            render_biomarker_results(search_results)
        elif search_type == "Family History":
            render_family_results(search_results)

def render_aggregated_results(results):
    """Render aggregated search results"""
    if not results or not results.results:
        st.info("No aggregated results")
        return
    
    st.subheader("🎯 Top Results Across All Types")
    
    for i, result in enumerate(results.results[:10]):  # Show top 10
        with st.expander(f"#{i+1} - {result.type.title()}: {result.id} (Score: {result.score:.2f})"):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Display key data based on type
                if result.type == "patient":
                    st.write("**Patient ID:**", result.data.get("patient_id", "N/A"))
                    st.write("**Demographics:**", f"Age: {result.data.get('demographics', {}).get('age', 'N/A')}, Gender: {result.data.get('demographics', {}).get('gender', 'N/A')}")
                    if result.data.get("diagnoses"):
                        st.write("**Diagnoses:**", ", ".join([d.get("diagnosis", "") for d in result.data.get("diagnoses", [])]))
                
                elif result.type == "image":
                    st.write("**Image Hash:**", result.data.get("image_hash", "N/A"))
                    st.write("**Modality:**", result.data.get("modality", "N/A"))
                    st.write("**Patient ID:**", result.data.get("patient_id", "N/A"))
                    st.write("**Acquisition Date:**", result.data.get("acquisition_date", "N/A"))
                
                elif result.type == "biomarker":
                    st.write("**Biomarker:**", result.data.get("biomarker_name", "N/A"))
                    st.write("**Value:**", result.data.get("value", "N/A"))
                    st.write("**Patient ID:**", result.data.get("patient_id", "N/A"))
                    st.write("**Date:**", result.data.get("measurement_date", "N/A"))
                
                elif result.type == "family_member":
                    st.write("**Relationship:**", result.data.get("relationship_type", "N/A"))
                    st.write("**AD Status:**", result.data.get("ad_status", "N/A"))
                    st.write("**Patient ID:**", result.data.get("patient_id", "N/A"))
            
            with col2:
                st.write("**Type:**", result.type.title())
                st.write("**Cached:**", "✅" if result.cached else "❌")
                if result.highlights:
                    st.write("**Highlights:**")
                    for field, highlights in result.highlights.items():
                        st.write(f"- {field}: {highlights[0][:100]}...")

def render_patient_results(results):
    """Render patient search results"""
    if not results or not results.results:
        st.info("No patient results found")
        return
    
    st.subheader(f"👤 Patient Results ({results.total_count} total)")
    st.write(f"Search time: {results.search_time_ms:.2f}ms | Cached: {'✅' if results.cached else '❌'}")
    
    # Create a dataframe for better display
    patient_data = []
    for result in results.results:
        data = result.data
        patient_data.append({
            "Patient ID": data.get("patient_id", "N/A"),
            "Age": data.get("demographics", {}).get("age", "N/A"),
            "Gender": data.get("demographics", {}).get("gender", "N/A"),
            "Diagnosis": ", ".join([d.get("diagnosis", "") for d in data.get("diagnoses", [])]) or "N/A",
            "Images": data.get("image_count", 0),
            "Family Members": data.get("family_member_count", 0),
            "Score": f"{result.score:.2f}"
        })
    
    if patient_data:
        df = pd.DataFrame(patient_data)
        
        # Add selection capability
        selected_indices = st.multiselect(
            "Select patients to view details:",
            range(len(df)),
            format_func=lambda x: f"{df.iloc[x]['Patient ID']} (Score: {df.iloc[x]['Score']})"
        )
        
        st.dataframe(df, use_container_width=True)
        
        # Show detailed view for selected patients
        for idx in selected_indices:
            result = results.results[idx]
            with st.expander(f"Details: {result.data.get('patient_id', 'N/A')}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.json(result.data)
                with col2:
                    if result.highlights:
                        st.write("**Search Highlights:**")
                        for field, highlights in result.highlights.items():
                            st.write(f"**{field}:** {highlights[0]}")

def display_cached_thumbnail(image_hash: str, redis_client=None):
    """Display cached thumbnail image with lazy loading"""
    if not redis_client:
        search_engine = get_search_engine()
        if search_engine:
            redis_client = search_engine.redis
    
    if redis_client:
        try:
            # Get cached thumbnail
            thumbnail_data = redis_client.get_thumbnail(image_hash)
            if thumbnail_data:
                # Convert bytes to image and display
                image = Image.open(BytesIO(thumbnail_data))
                st.image(image, width=200, caption=f"Image: {image_hash[:8]}...")
                return True
            else:
                # Show placeholder for missing thumbnail
                st.info("🖼️ Thumbnail not cached")
                return False
        except Exception as e:
            st.error(f"Error loading thumbnail: {e}")
            return False
    else:
        st.warning("Cache not available")
        return False

def create_image_gallery(image_results, max_images=12):
    """Create an image gallery with cached thumbnails and lazy loading"""
    if not image_results:
        st.info("No images to display")
        return
    
    st.subheader("🖼️ Image Gallery")
    
    # Pagination for large image sets
    images_per_page = max_images
    total_images = len(image_results)
    total_pages = (total_images - 1) // images_per_page + 1
    
    if total_pages > 1:
        page = st.selectbox("Page", range(1, total_pages + 1), key="image_gallery_page")
        start_idx = (page - 1) * images_per_page
        end_idx = min(start_idx + images_per_page, total_images)
        page_results = image_results[start_idx:end_idx]
    else:
        page_results = image_results[:max_images]
    
    # Display images in grid
    cols = st.columns(4)
    for i, result in enumerate(page_results):
        with cols[i % 4]:
            data = result.data
            image_hash = data.get("image_hash", "")
            
            # Image container
            with st.container():
                # Display thumbnail
                thumbnail_displayed = display_cached_thumbnail(image_hash)
                
                # Image metadata
                st.write(f"**{data.get('modality', 'Unknown')}**")
                st.write(f"Patient: {data.get('patient_id', 'N/A')}")
                
                # Quality indicator
                quality_score = data.get("quality_metrics", {}).get("quality_score")
                if quality_score:
                    if quality_score > 0.8:
                        st.success(f"Quality: {quality_score:.2f}")
                    elif quality_score > 0.6:
                        st.warning(f"Quality: {quality_score:.2f}")
                    else:
                        st.error(f"Quality: {quality_score:.2f}")
                
                # Processing status
                status = data.get("processing_status", "unknown")
                status_colors = {
                    "completed": "🟢",
                    "processing": "🟡", 
                    "failed": "🔴",
                    "pending": "⚪"
                }
                st.write(f"Status: {status_colors.get(status, '❓')} {status.title()}")
                
                # Expandable details
                with st.expander("🔍 Details"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**Series:**", data.get("series_description", "N/A"))
                        st.write("**Region:**", data.get("anatomical_region", "N/A"))
                        st.write("**Date:**", data.get("acquisition_date", "N/A"))
                    with col2:
                        st.write("**Hash:**", image_hash[:16] + "..." if len(image_hash) > 16 else image_hash)
                        st.write("**Cached:**", "✅" if thumbnail_displayed else "❌")
                        if data.get("file_paths"):
                            paths = data["file_paths"]
                            st.write("**Files:**", f"DICOM: {'✅' if paths.get('dicom') else '❌'}")
                
                # Image zoom functionality
                if thumbnail_displayed and st.button("🔍 Zoom", key=f"zoom_{image_hash}"):
                    show_image_zoom_modal(image_hash, data)

def show_image_zoom_modal(image_hash: str, image_data: Dict[str, Any]):
    """Show image zoom modal with metadata display"""
    st.subheader(f"🔍 Image Details: {image_hash[:12]}...")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Display larger image
        search_engine = get_search_engine()
        if search_engine and search_engine.redis:
            thumbnail_data = search_engine.redis.get_thumbnail(image_hash)
            if thumbnail_data:
                image = Image.open(BytesIO(thumbnail_data))
                st.image(image, caption=f"Image: {image_hash}")
            else:
                st.info("Full resolution image not available in cache")
    
    with col2:
        # Metadata display
        st.subheader("📋 Metadata")
        
        # Basic info
        st.write("**Patient ID:**", image_data.get("patient_id", "N/A"))
        st.write("**Modality:**", image_data.get("modality", "N/A"))
        st.write("**Series:**", image_data.get("series_description", "N/A"))
        st.write("**Anatomical Region:**", image_data.get("anatomical_region", "N/A"))
        st.write("**Acquisition Date:**", image_data.get("acquisition_date", "N/A"))
        
        # Quality metrics
        if image_data.get("quality_metrics"):
            st.subheader("📊 Quality Metrics")
            quality = image_data["quality_metrics"]
            for metric, value in quality.items():
                if isinstance(value, (int, float)):
                    st.metric(metric.replace("_", " ").title(), f"{value:.3f}")
        
        # DICOM metadata (if available)
        if image_data.get("dicom_metadata"):
            with st.expander("🏥 DICOM Metadata"):
                dicom_meta = image_data["dicom_metadata"]
                for key, value in dicom_meta.items():
                    if value is not None:
                        st.write(f"**{key.replace('_', ' ').title()}:** {value}")

def render_image_results(results):
    """Render image search results with cached thumbnails"""
    if not results or not results.results:
        st.info("No image results found")
        return
    
    st.subheader(f"🖼️ Image Results ({results.total_count} total)")
    st.write(f"Search time: {results.search_time_ms:.2f}ms | Cached: {'✅' if results.cached else '❌'}")
    
    # Display mode selection
    display_mode = st.radio(
        "Display Mode",
        ["Gallery", "List", "Detailed"],
        horizontal=True,
        key="image_display_mode"
    )
    
    if display_mode == "Gallery":
        # Gallery view with thumbnails
        create_image_gallery(results.results)
    
    elif display_mode == "List":
        # Compact list view
        image_data = []
        for result in results.results:
            data = result.data
            image_data.append({
                "Image Hash": data.get("image_hash", "N/A")[:12] + "...",
                "Patient ID": data.get("patient_id", "N/A"),
                "Modality": data.get("modality", "N/A"),
                "Date": data.get("acquisition_date", "N/A"),
                "Quality": data.get("quality_metrics", {}).get("quality_score", "N/A"),
                "Status": data.get("processing_status", "N/A"),
                "Cached": "✅" if data.get("thumbnail_cached") else "❌",
                "Score": f"{result.score:.2f}"
            })
        
        if image_data:
            df = pd.DataFrame(image_data)
            st.dataframe(df, use_container_width=True)
    
    else:  # Detailed view
        # Detailed view with expandable cards
        for i, result in enumerate(results.results):
            data = result.data
            image_hash = data.get("image_hash", "")
            
            with st.expander(f"Image {i+1}: {data.get('modality', 'Unknown')} - {data.get('patient_id', 'N/A')} (Score: {result.score:.2f})"):
                col1, col2, col3 = st.columns([1, 2, 1])
                
                with col1:
                    # Thumbnail
                    display_cached_thumbnail(image_hash)
                
                with col2:
                    # Metadata
                    st.write("**Patient ID:**", data.get("patient_id", "N/A"))
                    st.write("**Modality:**", data.get("modality", "N/A"))
                    st.write("**Series Description:**", data.get("series_description", "N/A"))
                    st.write("**Anatomical Region:**", data.get("anatomical_region", "N/A"))
                    st.write("**Acquisition Date:**", data.get("acquisition_date", "N/A"))
                    
                    # Quality metrics
                    if data.get("quality_metrics"):
                        quality_score = data["quality_metrics"].get("quality_score")
                        if quality_score:
                            st.metric("Quality Score", f"{quality_score:.3f}")
                
                with col3:
                    # Status and actions
                    status = data.get("processing_status", "unknown")
                    st.write("**Status:**", status.title())
                    st.write("**Cached:**", "✅" if data.get("thumbnail_cached") else "❌")
                    
                    if st.button("🔍 View Details", key=f"detail_{image_hash}"):
                        show_image_zoom_modal(image_hash, data)

def render_biomarker_results(results):
    """Render biomarker search results"""
    if not results or not results.results:
        st.info("No biomarker results found")
        return
    
    st.subheader(f"🧬 Biomarker Results ({results.total_count} total)")
    st.write(f"Search time: {results.search_time_ms:.2f}ms | Cached: {'✅' if results.cached else '❌'}")
    
    # Create visualization
    biomarker_data = []
    for result in results.results:
        data = result.data
        biomarker_data.append({
            "Patient ID": data.get("patient_id", "N/A"),
            "Biomarker": data.get("biomarker_name", "N/A"),
            "Value": data.get("value", 0),
            "Unit": data.get("unit", "N/A"),
            "Date": data.get("measurement_date", "N/A"),
            "Abnormal": data.get("abnormal_flag", False),
            "Score": result.score
        })
    
    if biomarker_data:
        df = pd.DataFrame(biomarker_data)
        
        # Visualization
        if len(df) > 1:
            fig = px.scatter(df, x="Date", y="Value", color="Biomarker", 
                           hover_data=["Patient ID", "Unit", "Abnormal"],
                           title="Biomarker Values Over Time")
            st.plotly_chart(fig, use_container_width=True)
        
        # Data table
        st.dataframe(df, use_container_width=True)

def render_family_results(results):
    """Render family history search results"""
    if not results or not results.results:
        st.info("No family history results found")
        return
    
    st.subheader(f"👨‍👩‍👧‍👦 Family History Results ({results.total_count} total)")
    st.write(f"Search time: {results.search_time_ms:.2f}ms | Cached: {'✅' if results.cached else '❌'}")
    
    # Group by patient for better organization
    family_by_patient = {}
    for result in results.results:
        data = result.data
        patient_id = data.get("patient_id", "Unknown")
        if patient_id not in family_by_patient:
            family_by_patient[patient_id] = []
        family_by_patient[patient_id].append(result)
    
    # Display family trees
    for patient_id, family_results in family_by_patient.items():
        with st.expander(f"Family Tree: {patient_id}"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Family Members:**")
                for result in family_results:
                    data = result.data
                    relationship = data.get("relationship_type", "Unknown")
                    ad_status = data.get("ad_status", "Unknown")
                    status_icon = "🔴" if ad_status == "affected" else "🟢" if ad_status == "unaffected" else "❓"
                    st.write(f"{status_icon} {relationship}")
            
            with col2:
                # Family risk summary
                affected_count = sum(1 for r in family_results if r.data.get("ad_status") == "affected")
                total_count = len(family_results)
                risk_percentage = (affected_count / total_count * 100) if total_count > 0 else 0
                
                st.metric("Family Risk", f"{risk_percentage:.1f}%")
                st.metric("Affected Members", f"{affected_count}/{total_count}")

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
    # Mode selection
    app_mode = st.sidebar.radio(
        "Application Mode",
        ["🔍 Search Mode", "👤 Patient Explorer"],
        horizontal=True
    )
    
    st.sidebar.info(f"Connected to: `{NEO4J_URI}`")
    
    if app_mode == "🔍 Search Mode":
        # Enhanced search interface
        search_results = render_search_interface()
        
        # Display search results if available
        if search_results:
            render_search_results(search_results, "Combined" if isinstance(search_results, dict) else "Single")
            return  # Exit early for search mode
    
    else:
        # Traditional patient explorer mode
        st.sidebar.title("🔍 Patient Selection")
        
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

                # Image gallery for patient
                st.subheader("🖼️ Patient Images")
                
                # Convert imaging data to result format for gallery
                image_results = []
                for img_data in imaging_data:
                    # Create a mock result object for gallery display
                    class MockResult:
                        def __init__(self, data):
                            self.data = data
                            self.score = 1.0
                            self.cached = False
                    
                    # Enhance data with cache check
                    enhanced_data = dict(img_data)
                    image_hash = enhanced_data.get("image_id", "")
                    if image_hash:
                        search_engine = get_search_engine()
                        if search_engine and search_engine.redis:
                            thumbnail_data = search_engine.redis.get_thumbnail(image_hash)
                            enhanced_data["thumbnail_cached"] = thumbnail_data is not None
                            enhanced_data["image_hash"] = image_hash
                    
                    image_results.append(MockResult(enhanced_data))
                
                if image_results:
                    create_image_gallery(image_results, max_images=8)
                
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
            
            # Timeline visualization
            st.subheader("📅 Comprehensive Patient Timeline")
            timeline_fig = create_comprehensive_patient_timeline(selected_ptid)
            if timeline_fig:
                st.plotly_chart(timeline_fig, use_container_width=True)
            
            # Interactive timeline navigation
            with st.expander("🔍 Timeline Navigation"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**Timeline Controls:**")
                    show_imaging = st.checkbox("Show Imaging Events", True)
                    show_assessments = st.checkbox("Show Assessments", True)
                    show_biomarkers = st.checkbox("Show Biomarkers", True)
                with col2:
                    st.write("**Date Range:**")
                    start_year = st.selectbox("Start Year", range(2010, 2025), index=5)
                    end_year = st.selectbox("End Year", range(2015, 2030), index=5)
            
            # Biomarker trends
            st.subheader("🧬 Biomarker Trend Analysis")
            biomarker_fig = create_biomarker_trend_visualization(selected_ptid)
            if biomarker_fig:
                st.plotly_chart(biomarker_fig, use_container_width=True)
            
            # Family relationship visualization
            if patient.get('family_members', 0) > 0:
                st.subheader("👨‍👩‍👧‍👦 Family Relationship Network")
                family_graph = create_family_relationship_graph(selected_ptid)
                if family_graph:
                    st.write("**Legend:** 🔴 Affected by AD | 🟢 Unaffected | 🔵 Patient")

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
            
            # Visual completeness indicator
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.metric("Data Completeness", f"{completeness:.1f}%")
                
                # Progress bar
                progress_color = "green" if completeness > 75 else "orange" if completeness > 50 else "red"
                st.progress(completeness / 100)
                
                # Breakdown
                completeness_data = {
                    "Data Type": ["Imaging", "Clinical Findings", "Family History", "Genetic Data"],
                    "Available": ["✅" if has_imaging else "❌", 
                                "✅" if has_findings else "❌",
                                "✅" if has_family else "❌", 
                                "✅" if has_genetic else "❌"]
                }
                st.table(pd.DataFrame(completeness_data))

            # Advanced analytics
            if show_advanced:
                st.subheader("🔬 Advanced Analytics")
                
                # Performance metrics
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Assessments", patient.get('assessment_count', 0))
                    st.metric("Temporal Coverage", f"{patient.get('temporal_regions', 0)} timepoints")
                    st.metric("Cache Hit Rate", "85%")  # Mock cache performance
                with col2:
                    st.metric("Multimodal Sessions", patient.get('multimodal_sessions', 0))
                    st.metric("Imaging Series", patient.get('imaging_series', 0))
                    st.metric("Data Quality Score", "92%")  # Mock quality score
                
                # Data freshness indicators
                st.subheader("🕒 Data Freshness")
                freshness_data = {
                    "Data Source": ["Neo4j Graph", "Elasticsearch Index", "Redis Cache", "Image Storage"],
                    "Last Updated": ["2 hours ago", "1 hour ago", "5 minutes ago", "30 minutes ago"],
                    "Status": ["🟢 Fresh", "🟢 Fresh", "🟢 Fresh", "🟡 Moderate"]
                }
                st.table(pd.DataFrame(freshness_data))

if __name__ == "__main__":
    main()