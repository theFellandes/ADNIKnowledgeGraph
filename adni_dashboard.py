"""
Main application file for ADNI Knowledge Graph Explorer
"""

import streamlit as st
import logging
from pathlib import Path

# Import UI components
from ui import (
    apply_custom_styles,
    render_dashboard,
    render_patient_explorer,
    render_imaging_explorer,
    render_atn_framework,
    render_disease_progression,
    render_biomarker_analysis,
    render_cognitive_patterns,
    render_family_risk_network,
    render_multimodal_profiles,
    render_relationship_explorer,
    render_network_visualization,
    render_progression_tracking,
    render_biomarker_correlations,
    render_advanced_query
)

# Import utilities
from utils.neo4j_connector import Neo4jConnector
from utils.elasticsearch_indexer import SearchIndexer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="ADNI Knowledge Graph Explorer",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply custom styles
apply_custom_styles()

# Initialize session state
if 'connector' not in st.session_state:
    st.session_state.connector = None
if 'es_indexer' not in st.session_state:
    st.session_state.es_indexer = None
if 'selected_patient' not in st.session_state:
    st.session_state.selected_patient = None
if 'graph_depth' not in st.session_state:
    st.session_state.graph_depth = 2
if 'selected_image' not in st.session_state:
    st.session_state.selected_image = None
if 'show_image_modal' not in st.session_state:
    st.session_state.show_image_modal = False
if 'selected_page' not in st.session_state:
    st.session_state.selected_page = "Dashboard"


# Database connection functions
@st.cache_resource
def get_connector():
    """Initialize Neo4j connection"""
    try:
        neo4j_uri = st.secrets.get("neo4j_uri", "bolt://localhost:7687")
        neo4j_user = st.secrets.get("neo4j_user", "neo4j")
        neo4j_password = st.secrets.get("neo4j_password", "your_password")

        connector = Neo4jConnector(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)

        if connector.verify_connection():
            return connector
        return None
    except Exception as e:
        st.error(f"Connection failed: {e}")
        return None


@st.cache_resource
def get_es_indexer():
    """Initialize Elasticsearch connection"""
    try:
        es_host = st.secrets.get("es_host", "localhost")
        es_port = st.secrets.get("es_port", 9200)

        indexer = SearchIndexer(host=es_host, port=es_port)

        if indexer.es and indexer.es.ping():
            return indexer
        return None
    except Exception as e:
        logger.warning(f"Elasticsearch connection failed: {e}")
        return None


# Define page categories
page_categories = {
    "Core Analysis": ["Dashboard", "Patient Explorer", "Imaging Explorer"],
    "Biomarkers": ["Biomarker Analysis", "ATN Framework", "Biomarker Correlations"],
    "Disease Insights": ["Disease Progression", "Cognitive Patterns", "Progression Tracking"],
    "Relationships": ["Family Risk Network", "Relationship Explorer", "Network Visualization"],
    "Advanced": ["Multimodal Profiles", "Advanced Query"]
}

# Flatten pages for easy lookup
all_pages = []
page_to_category = {}
for category, pages in page_categories.items():
    all_pages.extend(pages)
    for page in pages:
        page_to_category[page] = category

# SIDEBAR WITH FIXED CATEGORY NAVIGATION
with st.sidebar:
    st.title("🧠 ADNI Knowledge Graph")
    st.markdown("---")

    # Category selector
    selected_category = st.selectbox("Select Category", list(page_categories.keys()))

    # Page selector - filtered by category
    available_pages = page_categories[selected_category]
    selected_page = st.selectbox("Select Analysis", available_pages, key="page_selector")

    # Update session state
    st.session_state.selected_page = selected_page

    st.markdown("---")

    # Connection status
    connector = get_connector()
    es_indexer = get_es_indexer()

    if connector:
        st.success("✅ Connected to Neo4j")

        # Quick stats
        st.markdown("### Quick Stats")

        patients = connector.get_node_count("Patient")
        st.metric("Total Patients", f"{patients:,}")

        biomarkers = connector.get_node_count("Biomarker")
        st.metric("Biomarkers", f"{biomarkers:,}")

        images = connector.get_node_count("ImageNode")
        st.metric("Images", f"{images:,}")

        # ATN profiles
        query = "MATCH (p:Patient)-[:HAS_ATN_PROFILE]->() RETURN COUNT(DISTINCT p) as count"
        result = connector.run_query(query)
        atn_count = result[0]['count'] if result else 0
        st.metric("ATN Profiles", f"{atn_count:,}")
    else:
        st.error("❌ Neo4j not connected")
        st.stop()

    if es_indexer:
        st.success("✅ Connected to Elasticsearch")
    else:
        st.warning("⚠️ Elasticsearch not connected")

# MAIN APPLICATION ROUTING
selected_page = st.session_state.selected_page

# Route to appropriate page based on selection
page_renderers = {
    "Dashboard": lambda: render_dashboard(connector),
    "Patient Explorer": lambda: render_patient_explorer(connector),
    "Imaging Explorer": lambda: render_imaging_explorer(connector, es_indexer),
    "ATN Framework": lambda: render_atn_framework(connector),
    "Disease Progression": lambda: render_disease_progression(connector),
    "Biomarker Analysis": lambda: render_biomarker_analysis(connector),
    "Cognitive Patterns": lambda: render_cognitive_patterns(connector),
    "Family Risk Network": lambda: render_family_risk_network(connector),
    "Multimodal Profiles": lambda: render_multimodal_profiles(connector),
    "Relationship Explorer": lambda: render_relationship_explorer(connector),
    "Network Visualization": lambda: render_network_visualization(connector),
    "Progression Tracking": lambda: render_progression_tracking(connector),
    "Biomarker Correlations": lambda: render_biomarker_correlations(connector),
    "Advanced Query": lambda: render_advanced_query(connector)
}

# Execute the selected page renderer
if selected_page in page_renderers:
    page_renderers[selected_page]()
else:
    st.error(f"Page '{selected_page}' not found")

# Image viewer modal
if st.session_state.show_image_modal and st.session_state.selected_image:
    from ui.components import render_image_viewer_modal

    render_image_viewer_modal()

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; padding: 20px;'>
        <p>ADNI Knowledge Graph Explorer | Enhanced Edition</p>
        <p style='font-size: 0.9em;'>Powered by Neo4j, Elasticsearch & Advanced AD Research</p>
    </div>
    """,
    unsafe_allow_html=True
)