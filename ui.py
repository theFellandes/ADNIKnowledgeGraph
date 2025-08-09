"""
Complete ADNI Knowledge Graph UI with All Features Fixed
Includes all original tabs and fixes duplicate key error
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import networkx as nx
from PIL import Image
import base64
from io import BytesIO
from datetime import datetime
import json
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import logging
import uuid

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

# Custom CSS with enhanced styles
st.markdown("""
<style>
    .main { padding-top: 1rem; }
    .stMetric {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 15px;
        margin: 10px 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stMetric label { color: rgba(255,255,255,0.8) !important; }
    .stMetric [data-testid="metric-value"] { color: white !important; font-size: 2rem !important; }
    
    .patient-card {
        background: white;
        padding: 25px;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 20px;
        border-left: 4px solid #667eea;
    }
    
    .diagnosis-badge {
        padding: 8px 16px;
        border-radius: 20px;
        font-weight: bold;
        margin: 5px;
        display: inline-block;
        text-transform: uppercase;
        font-size: 0.85rem;
    }
    .cn { background: linear-gradient(135deg, #667eea, #764ba2); color: white; }
    .mci { background: linear-gradient(135deg, #f093fb, #f5576c); color: white; }
    .ad { background: linear-gradient(135deg, #fa709a, #fee140); color: white; }
    
    .relationship-explorer {
        background: #f8f9fa;
        border-radius: 15px;
        padding: 20px;
        margin: 20px 0;
    }
    
    .image-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 15px;
        margin: 20px 0;
    }
    
    .image-card {
        background: white;
        border-radius: 10px;
        padding: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: transform 0.2s;
    }
    .image-card:hover { transform: scale(1.05); }
</style>
""", unsafe_allow_html=True)

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

# Database connection
@st.cache_resource
def get_connector():
    """Initialize Neo4j connection"""
    try:
        from utils.neo4j_connector import Neo4jConnector

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

# Elasticsearch connection
@st.cache_resource
def get_es_indexer():
    """Initialize Elasticsearch connection"""
    try:
        from utils.elasticsearch_indexer import SearchIndexer

        es_host = st.secrets.get("es_host", "localhost")
        es_port = st.secrets.get("es_port", 9200)

        indexer = SearchIndexer(host=es_host, port=es_port)

        # Test connection
        if indexer.es and indexer.es.ping():
            return indexer
        return None
    except Exception as e:
        logger.warning(f"Elasticsearch connection failed: {e}")
        return None

# ============================================================================
# ENHANCED COMPONENTS
# ============================================================================

def render_dashboard_overview(connector):
    """Render enhanced dashboard with key metrics"""
    st.title("🧠 ADNI Knowledge Graph Dashboard")

    # Key metrics in colored cards
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        patient_count = connector.get_node_count("Patient")
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    color: white; padding: 20px; border-radius: 15px; text-align: center;">
            <h2 style="color: white; margin: 0;">{patient_count:,}</h2>
            <p style="color: rgba(255,255,255,0.9); margin: 0;">Patients</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        visit_count = connector.get_node_count("Visit")
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); 
                    color: white; padding: 20px; border-radius: 15px; text-align: center;">
            <h2 style="color: white; margin: 0;">{visit_count:,}</h2>
            <p style="color: rgba(255,255,255,0.9); margin: 0;">Visits</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        image_count = connector.get_node_count("ImageNode")
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); 
                    color: white; padding: 20px; border-radius: 15px; text-align: center;">
            <h2 style="color: white; margin: 0;">{image_count:,}</h2>
            <p style="color: rgba(255,255,255,0.9); margin: 0;">Images</p>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        # Get relationship count
        query = "MATCH ()-[r]->() RETURN count(r) as count"
        result = connector.run_query(query)
        rel_count = result[0]['count'] if result else 0
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); 
                    color: white; padding: 20px; border-radius: 15px; text-align: center;">
            <h2 style="color: white; margin: 0;">{rel_count:,}</h2>
            <p style="color: rgba(255,255,255,0.9); margin: 0;">Relationships</p>
        </div>
        """, unsafe_allow_html=True)

    # Progression Analysis
    st.markdown("### 📈 Disease Progression Analysis")

    query = """
    MATCH (p:ProgressionPattern)
    RETURN p.from_diagnosis + ' → ' + p.to_diagnosis as progression,
           COUNT(p) as count,
           AVG(p.duration_months) as avg_months
    ORDER BY count DESC
    LIMIT 10
    """

    progressions = connector.run_query(query)
    if progressions:
        df = pd.DataFrame(progressions)

        fig = px.bar(df, x='progression', y='count',
                     hover_data=['avg_months'],
                     title="Common Progression Patterns",
                     labels={'count': 'Number of Patients', 'progression': 'Progression Path'})
        fig.update_traces(marker_color='#667eea')
        st.plotly_chart(fig, use_container_width=True)

    # Relationship Distribution
    st.markdown("### 🕸️ Relationship Network Statistics")

    query = """
    MATCH ()-[r]->()
    RETURN type(r) as relationship, count(r) as count
    ORDER BY count DESC
    LIMIT 15
    """

    relationships = connector.run_query(query)
    if relationships:
        df = pd.DataFrame(relationships)

        fig = px.treemap(df, path=['relationship'], values='count',
                        title="Relationship Distribution in Knowledge Graph")
        st.plotly_chart(fig, use_container_width=True)

def render_enhanced_imaging_explorer(connector, es_indexer=None):
    """Enhanced imaging explorer with Elasticsearch/Neo4j fallback"""
    st.title("🏥 Medical Imaging Explorer")

    # Check data sources
    data_sources = []
    if es_indexer and es_indexer.es and es_indexer.es.ping():
        data_sources.append("Elasticsearch")
    if connector:
        data_sources.append("Neo4j")

    if not data_sources:
        st.error("No data sources available for imaging data")
        return

    st.info(f"Using data sources: {', '.join(data_sources)}")

    # Statistics
    col1, col2, col3, col4 = st.columns(4)

    # Get counts from available source
    if "Elasticsearch" in data_sources:
        try:
            stats = es_indexer.get_index_stats()
            total_images = stats.get('total_images', 0)
        except:
            total_images = connector.get_node_count("ImageNode") if "Neo4j" in data_sources else 0
    else:
        total_images = connector.get_node_count("ImageNode") if "Neo4j" in data_sources else 0

    col1.metric("Total Images", f"{total_images:,}")

    # Get modality counts from Neo4j
    if "Neo4j" in data_sources:
        query = "MATCH (i:ImageNode {modality: 'MRI'}) RETURN count(i) as count"
        mri_count = connector.run_query(query)
        col2.metric("MRI Scans", mri_count[0]['count'] if mri_count else 0)

        query = "MATCH (i:ImageNode {modality: 'PET'}) RETURN count(i) as count"
        pet_count = connector.run_query(query)
        col3.metric("PET Scans", pet_count[0]['count'] if pet_count else 0)

        query = "MATCH (p:Patient)-[:HAS_IMAGE]->() RETURN count(DISTINCT p) as count"
        img_patients = connector.run_query(query)
        col4.metric("Patients with Imaging", img_patients[0]['count'] if img_patients else 0)

    st.markdown("---")

    # Image Browser
    tab1, tab2, tab3, tab4 = st.tabs(["Search Images", "Browse by Patient", "Browse by Study", "Image Analysis"])

    with tab1:
        st.subheader("Search Medical Images")

        # Search interface
        col1, col2 = st.columns([3, 1])
        with col1:
            search_query = st.text_input("Search (Patient ID, Description, etc.)",
                                        placeholder="e.g., 002_S_0295 or T1 or MRI")
        with col2:
            modality_filter = st.selectbox("Modality", ["All", "MRI", "PET", "CT"])

        if st.button("Search", type="primary"):
            images = search_images_with_fallback(search_query, modality_filter,
                                                es_indexer, connector, data_sources)

            if images:
                st.success(f"Found {len(images)} images")
                display_image_results(images)
            else:
                st.info("No images found matching your search")

    with tab2:
        # Patient selector
        patient_id = st.text_input("Enter Patient ID", placeholder="e.g., 002_S_0295")

        if patient_id:
            images = get_patient_images_with_fallback(patient_id, es_indexer,
                                                     connector, data_sources)

            if images:
                st.subheader(f"Images for Patient {patient_id} ({len(images)} found)")

                # Group by modality
                mri_images = [img for img in images if img.get('modality') == 'MRI']
                pet_images = [img for img in images if img.get('modality') == 'PET']

                if mri_images:
                    st.markdown("#### MRI Images")
                    display_image_grid(mri_images, context=f"patient_{patient_id}_mri")

                if pet_images:
                    st.markdown("#### PET Images")
                    display_image_grid(pet_images, context=f"patient_{patient_id}_pet")
            else:
                st.info(f"No images found for patient {patient_id}")

    with tab3:
        # Browse by study date
        st.subheader("Browse Images by Study Date")

        if "Neo4j" in data_sources:
            # Get available study dates
            query = """
            MATCH (i:ImageNode)
            WHERE i.study_date IS NOT NULL
            RETURN DISTINCT i.study_date as date
            ORDER BY date DESC
            LIMIT 30
            """

            dates = connector.run_query(query)

            if dates:
                selected_date = st.selectbox("Select Study Date",
                                            [d['date'] for d in dates])

                if selected_date:
                    images = get_images_by_date_with_fallback(selected_date,
                                                             es_indexer, connector, data_sources)

                    if images:
                        st.info(f"Found {len(images)} images from {selected_date}")
                        display_image_results_by_date(images)

    with tab4:
        # Image Analysis
        st.subheader("Image Analysis and Correlations")

        # Volumetric analysis
        query = """
        MATCH (v:VolumetricMeasure)
        RETURN v.region as region,
               AVG(v.volume) as avg_volume,
               MIN(v.volume) as min_volume,
               MAX(v.volume) as max_volume,
               COUNT(v) as count
        ORDER BY count DESC
        LIMIT 10
        """

        volumes = connector.run_query(query)

        if volumes:
            df = pd.DataFrame(volumes)

            fig = go.Figure()
            for _, row in df.iterrows():
                fig.add_trace(go.Box(
                    y=[row['min_volume'], row['avg_volume'], row['max_volume']],
                    name=row['region'],
                    boxmean=True
                ))

            fig.update_layout(title="Brain Region Volumes",
                            yaxis_title="Volume (mm³)")
            st.plotly_chart(fig, use_container_width=True)

def search_images_with_fallback(query: str, modality: str, es_indexer, connector, data_sources) -> List[Dict]:
    """Search images with fallback between Elasticsearch and Neo4j"""
    images = []

    # Try Elasticsearch first if available
    if "Elasticsearch" in data_sources and es_indexer:
        try:
            filters = {}
            if modality != "All":
                filters["modality"] = modality

            results = es_indexer.search_images(query, filters=filters, size=100)
            images = [hit["source"] for hit in results["hits"]]

            if images:
                logger.info(f"Retrieved {len(images)} images from Elasticsearch")
                return images
        except Exception as e:
            logger.warning(f"Elasticsearch search failed: {e}, falling back to Neo4j")

    # Fallback to Neo4j
    if "Neo4j" in data_sources and connector:
        try:
            # Build Neo4j query
            where_clauses = []
            if query:
                where_clauses.append(f"(i.patient_id CONTAINS '{query}' OR i.series_description CONTAINS '{query}')")
            if modality != "All":
                where_clauses.append(f"i.modality = '{modality}'")

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            neo4j_query = f"""
            MATCH (i:ImageNode)
            WHERE {where_clause}
            RETURN i.image_id as image_id,
                   i.patient_id as patient_id,
                   i.modality as modality,
                   i.series_description as series_description,
                   i.study_date as study_date,
                   i.png_path as png_path,
                   i.thumbnail_path as thumbnail_path,
                   i.dcm_path as dcm_path
            LIMIT 100
            """

            images = connector.run_query(neo4j_query)
            logger.info(f"Retrieved {len(images)} images from Neo4j")
        except Exception as e:
            logger.error(f"Neo4j search failed: {e}")

    return images

def get_patient_images_with_fallback(patient_id: str, es_indexer, connector, data_sources) -> List[Dict]:
    """Get patient images with fallback between Elasticsearch and Neo4j"""
    images = []

    # Try Elasticsearch first
    if "Elasticsearch" in data_sources and es_indexer:
        try:
            images = es_indexer.get_patient_images(patient_id)
            if images:
                logger.info(f"Retrieved {len(images)} images from Elasticsearch for patient {patient_id}")
                return images
        except Exception as e:
            logger.warning(f"Elasticsearch failed: {e}, falling back to Neo4j")

    # Fallback to Neo4j
    if "Neo4j" in data_sources and connector:
        try:
            query = """
            MATCH (p:Patient {ptid: $patient_id})-[:HAS_IMAGE]->(i:ImageNode)
            RETURN i.image_id as image_id,
                   i.patient_id as patient_id,
                   i.modality as modality,
                   i.series_description as series_description,
                   i.study_date as study_date,
                   i.png_path as png_path,
                   i.thumbnail_path as thumbnail_path,
                   i.dcm_path as dcm_path
            ORDER BY i.study_date DESC, i.modality
            """

            images = connector.run_query(query, {'patient_id': patient_id})
            logger.info(f"Retrieved {len(images)} images from Neo4j for patient {patient_id}")
        except Exception as e:
            logger.error(f"Neo4j query failed: {e}")

    return images

def get_images_by_date_with_fallback(study_date: str, es_indexer, connector, data_sources) -> List[Dict]:
    """Get images by date with fallback"""
    images = []

    # Try Elasticsearch first
    if "Elasticsearch" in data_sources and es_indexer:
        try:
            filters = {"study_date": study_date}
            results = es_indexer.search_images("", filters=filters, size=200)
            images = [hit["source"] for hit in results["hits"]]

            if images:
                logger.info(f"Retrieved {len(images)} images from Elasticsearch for date {study_date}")
                return images
        except Exception as e:
            logger.warning(f"Elasticsearch failed: {e}, falling back to Neo4j")

    # Fallback to Neo4j
    if "Neo4j" in data_sources and connector:
        try:
            query = """
            MATCH (i:ImageNode {study_date: $date})
            RETURN i.image_id as image_id,
                   i.patient_id as patient_id,
                   i.modality as modality,
                   i.series_description as series_description,
                   i.png_path as png_path,
                   i.thumbnail_path as thumbnail_path
            LIMIT 200
            """

            images = connector.run_query(query, {'date': study_date})
            logger.info(f"Retrieved {len(images)} images from Neo4j for date {study_date}")
        except Exception as e:
            logger.error(f"Neo4j query failed: {e}")

    return images

def display_image_results(images: List[Dict]):
    """Display image search results"""
    # Group by patient
    patients = {}
    for img in images:
        pid = img.get('patient_id', 'unknown')
        if pid not in patients:
            patients[pid] = []
        patients[pid].append(img)

    # Display first 10 patients
    for idx, (pid, patient_images) in enumerate(list(patients.items())[:10]):
        with st.expander(f"Patient {pid} ({len(patient_images)} images)"):
            display_image_grid(patient_images[:12], context=f"search_patient_{pid}_{idx}")

def display_image_results_by_date(images: List[Dict]):
    """Display images grouped by patient for a specific date"""
    # Group by patient
    patients = {}
    for img in images:
        pid = img.get('patient_id', 'unknown')
        if pid not in patients:
            patients[pid] = []
        patients[pid].append(img)

    # Display first 10 patients
    for idx, (pid, patient_images) in enumerate(list(patients.items())[:10]):
        with st.expander(f"Patient {pid} ({len(patient_images)} images)"):
            display_image_grid(patient_images[:12], context=f"date_patient_{pid}_{idx}")

def display_image_grid(images: List[Dict], context: str = ""):
    """Display images in a grid with proper handling and unique keys"""
    cols = st.columns(4)

    # Generate unique context if not provided
    if not context:
        context = str(uuid.uuid4())[:8]

    for idx, img in enumerate(images[:12]):  # Limit to 12 images
        col_idx = idx % 4

        with cols[col_idx]:
            # Try to display the image
            image_displayed = False

            # Try thumbnail first
            if img.get('thumbnail_path'):
                path = Path(img['thumbnail_path'])
                if path.exists():
                    try:
                        pil_img = load_and_convert_image(path)
                        if pil_img:
                            st.image(pil_img, caption=img.get('series_description', 'Image')[:20],
                                   use_container_width=True)
                            image_displayed = True
                    except Exception as e:
                        logger.error(f"Error loading thumbnail: {e}")

            # Try PNG if thumbnail failed
            if not image_displayed and img.get('png_path'):
                path = Path(img['png_path'])
                if path.exists():
                    try:
                        pil_img = load_and_convert_image(path)
                        if pil_img:
                            # Resize for display
                            pil_img.thumbnail((200, 200))
                            st.image(pil_img, caption=img.get('series_description', 'Image')[:20],
                                   use_container_width=True)
                            image_displayed = True
                    except Exception as e:
                        logger.error(f"Error loading PNG: {e}")

            # Show placeholder if no image could be displayed
            if not image_displayed:
                st.markdown(f"""
                <div style="background: #f0f0f0; padding: 40px; 
                           border-radius: 10px; text-align: center;">
                    <p>📷</p>
                    <small>{img.get('modality', 'Image')}</small>
                </div>
                """, unsafe_allow_html=True)

            # Add view button with unique key
            button_key = f"view_{context}_{idx}_{img.get('image_id', '')[:8]}_{str(uuid.uuid4())[:8]}"
            if st.button(f"View", key=button_key):
                st.session_state.selected_image = img

def load_and_convert_image(path: Path) -> Optional[Image.Image]:
    """Load and convert image to displayable format"""
    try:
        img = Image.open(path)

        # Convert problematic modes
        if img.mode == 'I;16':
            # Convert 16-bit to 8-bit
            img_array = np.array(img)
            img_array = ((img_array - img_array.min()) /
                        (img_array.max() - img_array.min()) * 255).astype(np.uint8)
            img = Image.fromarray(img_array, mode='L')

        # Convert to RGB for display
        if img.mode not in ['RGB', 'RGBA']:
            img = img.convert('RGB')

        return img
    except Exception as e:
        logger.error(f"Error converting image: {e}")
        return None

def render_relationship_explorer(connector):
    """Interactive relationship explorer"""
    st.title("🔗 Relationship Explorer")

    # Relationship type selector
    rel_types = [
        "Clinical Progression",
        "Biomarker Correlations",
        "Family Relationships",
        "Temporal Sequences",
        "Genetic Risk",
        "Multimodal Connections"
    ]

    selected_type = st.selectbox("Select Relationship Type", rel_types)

    if selected_type == "Clinical Progression":
        # Show progression patterns
        query = """
        MATCH (d1:Diagnosis)-[r:PROGRESSED_TO]->(d2:Diagnosis)
        RETURN d1.diagnosis_code as from_dx,
               d2.diagnosis_code as to_dx,
               COUNT(r) as count,
               AVG(r.months_delta) as avg_months
        ORDER BY count DESC
        LIMIT 25
        """

        results = connector.run_query(query)

        if results:
            df = pd.DataFrame(results)

            # Sankey diagram
            unique_labels = list(set(df['from_dx'].tolist() + df['to_dx'].tolist()))

            fig = go.Figure(data=[go.Sankey(
                node=dict(
                    pad=15,
                    thickness=20,
                    line=dict(color="black", width=0.5),
                    label=unique_labels
                ),
                link=dict(
                    source=[unique_labels.index(x) for x in df['from_dx']],
                    target=[unique_labels.index(x) for x in df['to_dx']],
                    value=df['count'].tolist()
                )
            )])

            fig.update_layout(title="Disease Progression Flow")
            st.plotly_chart(fig, use_container_width=True)

            # Table
            st.dataframe(df, use_container_width=True)

    elif selected_type == "Biomarker Correlations":
        # Show biomarker correlations
        query = """
        MATCH (b1:Biomarker)-[r:CORRELATES_WITH]->(b2:Biomarker)
        RETURN b1.analyte as biomarker1,
               b2.analyte as biomarker2,
               COUNT(r) as correlation_count
        ORDER BY correlation_count DESC
        LIMIT 25
        """

        results = connector.run_query(query)

        if results:
            df = pd.DataFrame(results)

            # Create correlation matrix
            pivot = df.pivot_table(values='correlation_count',
                                  index='biomarker1',
                                  columns='biomarker2',
                                  fill_value=0)

            fig = px.imshow(pivot,
                          title="Biomarker Correlation Matrix",
                          labels=dict(x="Biomarker", y="Biomarker", color="Correlations"))
            st.plotly_chart(fig, use_container_width=True)

    elif selected_type == "Family Relationships":
        # Show family network
        query = """
        MATCH (p:Patient)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember)
        RETURN fm.relationship_type as relationship,
               SUM(CASE WHEN fm.has_dementia THEN 1 ELSE 0 END) as with_dementia,
               COUNT(fm) as total,
               100.0 * SUM(CASE WHEN fm.has_dementia THEN 1 ELSE 0 END) / COUNT(fm) as percentage
        ORDER BY total DESC
        """

        results = connector.run_query(query)

        if results:
            df = pd.DataFrame(results)

            # Stacked bar chart
            fig = go.Figure()
            fig.add_trace(go.Bar(name='With Dementia',
                                x=df['relationship'],
                                y=df['with_dementia']))
            fig.add_trace(go.Bar(name='Without Dementia',
                                x=df['relationship'],
                                y=df['total'] - df['with_dementia']))

            fig.update_layout(barmode='stack',
                            title="Family Members by Relationship Type")
            st.plotly_chart(fig, use_container_width=True)

def render_progression_tracking(connector):
    """Disease progression tracking"""
    st.title("📊 Disease Progression Tracking")

    # Individual progression paths
    st.subheader("Patient Progression Paths")

    patient_id = st.text_input("Enter Patient ID for Progression Analysis", key="prog_patient_id")

    if patient_id:
        query = """
        MATCH (p:Patient {ptid: $patient_id})-[:HAS_VISIT]->(v:Visit)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        OPTIONAL MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        WHERE ca.test_name = 'MMSE'
        RETURN v.months_from_baseline as months,
               d.diagnosis_code as diagnosis,
               ca.total_score as mmse_score
        ORDER BY v.months_from_baseline
        """

        progression = connector.run_query(query, {'patient_id': patient_id})

        if progression:
            df = pd.DataFrame(progression)

            # Create dual-axis plot
            fig = make_subplots(specs=[[{"secondary_y": True}]])

            # Add MMSE scores
            if 'mmse_score' in df.columns and not df['mmse_score'].isna().all():
                fig.add_trace(
                    go.Scatter(x=df['months'], y=df['mmse_score'],
                             name='MMSE Score', mode='lines+markers'),
                    secondary_y=False
                )

            # Add diagnosis markers
            diagnosis_map = {'CN': 0, 'MCI': 1, 'AD': 2}
            df['dx_numeric'] = df['diagnosis'].map(diagnosis_map)

            fig.add_trace(
                go.Scatter(x=df['months'], y=df['dx_numeric'],
                         name='Diagnosis Stage', mode='lines+markers',
                         line=dict(dash='dash')),
                secondary_y=True
            )

            fig.update_xaxes(title_text="Months from Baseline")
            fig.update_yaxes(title_text="MMSE Score", secondary_y=False)
            fig.update_yaxes(title_text="Diagnosis Stage", secondary_y=True,
                           ticktext=['CN', 'MCI', 'AD'], tickvals=[0, 1, 2])

            fig.update_layout(title=f"Progression Timeline for {patient_id}")
            st.plotly_chart(fig, use_container_width=True)

            # Show raw data
            st.dataframe(df, use_container_width=True)
        else:
            st.info(f"No progression data found for patient {patient_id}")

def render_network_visualization_fixed(connector):
    """Fixed network visualization with proper path handling"""
    st.title("🕸️ Network Visualization")

    # Network depth control
    depth = st.slider("Relationship Depth", 1, 4, 2)

    patient_id = st.text_input("Enter Patient ID for Network", placeholder="e.g., 002_S_0295", key="network_patient_id")

    if patient_id:
        with st.spinner("Building network..."):
            # Modified query to return individual nodes and relationships
            query = f"""
            MATCH (p:Patient {{ptid: $patient_id}})
            OPTIONAL MATCH path = (p)-[*1..{depth}]-(connected)
            WITH p, relationships(path) as rels, nodes(path) as nodes
            RETURN p as center_node, 
                   COLLECT(DISTINCT nodes) as all_nodes,
                   COLLECT(DISTINCT rels) as all_relationships
            LIMIT 1
            """

            result = connector.run_query(query, {'patient_id': patient_id})

            if result and len(result) > 0:
                # Build network graph
                G = nx.Graph()

                # Process the result
                record = result[0]
                center_node = record.get('center_node', {})
                all_nodes_nested = record.get('all_nodes', [])
                all_relationships_nested = record.get('all_relationships', [])

                # Flatten nested lists
                all_nodes = []
                for node_list in all_nodes_nested:
                    if isinstance(node_list, list):
                        all_nodes.extend(node_list)
                    else:
                        all_nodes.append(node_list)

                all_relationships = []
                for rel_list in all_relationships_nested:
                    if isinstance(rel_list, list):
                        all_relationships.extend(rel_list)
                    else:
                        all_relationships.append(rel_list)

                # Add center node
                if center_node:
                    G.add_node(patient_id, type='Patient', label=patient_id)

                # Process nodes - now we have a flat list of node dictionaries
                node_mapping = {patient_id: patient_id}  # Map original IDs to display IDs

                for node in all_nodes:
                    if node and isinstance(node, dict):
                        # Determine node ID and type based on available properties
                        node_id = None
                        node_type = 'Unknown'

                        # Try different ID fields
                        if 'ptid' in node:
                            node_id = node['ptid']
                            node_type = 'Patient'
                        elif 'visit_id' in node:
                            node_id = node['visit_id']
                            node_type = 'Visit'
                        elif 'image_id' in node:
                            node_id = node['image_id']
                            node_type = 'ImageNode'
                        elif 'biomarker_id' in node:
                            node_id = node['biomarker_id']
                            node_type = 'Biomarker'
                        elif 'diagnosis_id' in node:
                            node_id = node['diagnosis_id']
                            node_type = 'Diagnosis'
                        elif 'assessment_id' in node:
                            node_id = node['assessment_id']
                            node_type = 'CognitiveAssessment'
                        elif 'member_id' in node:
                            node_id = node['member_id']
                            node_type = 'FamilyMember'
                        else:
                            # Try to find any ID field
                            for key in node.keys():
                                if 'id' in key.lower():
                                    node_id = str(node[key])
                                    break

                        if node_id and node_id not in G:
                            display_id = f"{node_type}_{node_id[:8]}" if len(str(node_id)) > 8 else str(node_id)
                            G.add_node(display_id, type=node_type, original_id=node_id)
                            node_mapping[node_id] = display_id

                # Alternative approach: Get relationships with a simpler query
                rel_query = f"""
                MATCH (p:Patient {{ptid: $patient_id}})-[r*1..{depth}]-(connected)
                RETURN DISTINCT type(r[0]) as rel_type, 
                       id(startNode(r[0])) as start_id, 
                       id(endNode(r[0])) as end_id,
                       labels(startNode(r[0]))[0] as start_type,
                       labels(endNode(r[0]))[0] as end_type
                LIMIT 200
                """

                rel_results = connector.run_query(rel_query, {'patient_id': patient_id})

                # Add edges based on the relationship results
                for rel in rel_results:
                    if rel:
                        # Create simplified node IDs for the graph
                        start_node = f"{rel.get('start_type', 'Unknown')}_{rel.get('start_id', '')}"[:20]
                        end_node = f"{rel.get('end_type', 'Unknown')}_{rel.get('end_id', '')}"[:20]

                        # Ensure nodes exist
                        if start_node not in G:
                            G.add_node(start_node, type=rel.get('start_type', 'Unknown'))
                        if end_node not in G:
                            G.add_node(end_node, type=rel.get('end_type', 'Unknown'))

                        # Add edge
                        G.add_edge(start_node, end_node, type=rel.get('rel_type', 'RELATED'))

                # If we have nodes, create visualization
                if G.number_of_nodes() > 0:
                    # Create layout
                    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)

                    # Create edge traces
                    edge_traces = []
                    for edge in G.edges():
                        x0, y0 = pos[edge[0]]
                        x1, y1 = pos[edge[1]]
                        edge_trace = go.Scatter(
                            x=[x0, x1, None],
                            y=[y0, y1, None],
                            mode='lines',
                            line=dict(width=0.5, color='#888'),
                            hoverinfo='none'
                        )
                        edge_traces.append(edge_trace)

                    # Create node trace
                    node_x = []
                    node_y = []
                    node_text = []
                    node_colors = []

                    # Color mapping for node types
                    color_map = {
                        'Patient': '#667eea',
                        'Visit': '#f093fb',
                        'ImageNode': '#4facfe',
                        'Diagnosis': '#fa709a',
                        'Biomarker': '#fee140',
                        'CognitiveAssessment': '#30cfd0',
                        'FamilyMember': '#a8edea',
                        'Unknown': '#888888'
                    }

                    for node in G.nodes():
                        x, y = pos[node]
                        node_x.append(x)
                        node_y.append(y)
                        node_type = G.nodes[node].get('type', 'Unknown')
                        node_text.append(f"{node_type}: {node}")
                        node_colors.append(color_map.get(node_type, '#888888'))

                    node_trace = go.Scatter(
                        x=node_x,
                        y=node_y,
                        mode='markers+text',
                        hoverinfo='text',
                        marker=dict(
                            size=10,
                            color=node_colors,
                            line_width=2
                        ),
                        text=[n.split('_')[0] if '_' in n else n for n in G.nodes()],
                        textposition="top center",
                        hovertext=node_text
                    )

                    # Create figure
                    fig = go.Figure(
                        data=edge_traces + [node_trace],
                        layout=go.Layout(
                            title=f'Network for {patient_id} (depth={depth})',
                            showlegend=False,
                            hovermode='closest',
                            margin=dict(b=20, l=5, r=5, t=40),
                            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                            height=600
                        )
                    )

                    st.plotly_chart(fig, use_container_width=True)

                    # Network statistics
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Nodes", G.number_of_nodes())
                    col2.metric("Edges", G.number_of_edges())
                    if G.number_of_nodes() > 0:
                        col3.metric("Density", f"{nx.density(G):.3f}")
                else:
                    st.warning(f"No network data found for patient {patient_id}")
            else:
                st.warning(f"Patient {patient_id} not found in the database")

# ============================================================================
# MAIN APPLICATION
# ============================================================================

# Sidebar
with st.sidebar:
    st.title("🧠 ADNI Knowledge Graph")
    st.markdown("---")

    # Navigation
    pages = [
        "Dashboard",
        "Patient Explorer",
        "Imaging Explorer",
        "Relationship Explorer",
        "Progression Tracking",
        "Network Visualization",
        "Biomarker Analysis",
        "Advanced Query"
    ]

    selected_page = st.selectbox("Select Page", pages)

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

        visits = connector.get_node_count("Visit")
        st.metric("Total Visits", f"{visits:,}")

        images = connector.get_node_count("ImageNode")
        st.metric("Total Images", f"{images:,}")
    else:
        st.error("❌ Neo4j not connected")
        st.stop()

    if es_indexer:
        st.success("✅ Connected to Elasticsearch")
    else:
        st.warning("⚠️ Elasticsearch not connected")
        st.caption("Using Neo4j for image search")

# Main content area
if selected_page == "Dashboard":
    render_dashboard_overview(connector)

elif selected_page == "Patient Explorer":
    st.title("🔍 Patient Explorer")

    # Search
    search_term = st.text_input("Search Patient ID", placeholder="e.g., 002_S_0295", key="patient_search")

    if search_term:
        query = """
        MATCH (p:Patient)
        WHERE p.ptid CONTAINS $search
        OPTIONAL MATCH (p)-[:HAS_GENETIC_RISK_PROFILE]->(gr:GeneticRiskProfile)
        OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        RETURN p.ptid as id,
               p.gender as gender,
               p.age_at_baseline as age,
               p.apoe_genotype as apoe,
               gr.risk_category as genetic_risk,
               COLLECT(DISTINCT d.diagnosis_code) as diagnoses
        LIMIT 20
        """

        patients = connector.run_query(query, {'search': search_term})

        if patients:
            for patient in patients:
                with st.expander(f"Patient {patient['id']}"):
                    col1, col2, col3, col4 = st.columns(4)

                    col1.metric("Gender", patient['gender'] or 'Unknown')
                    col2.metric("Age", f"{patient['age']:.0f}" if patient['age'] else 'N/A')
                    col3.metric("APOE", patient['apoe'] or 'Unknown')
                    col4.metric("Risk", patient['genetic_risk'] or 'Unknown')

                    if patient['diagnoses']:
                        st.markdown("**Diagnoses:**")
                        for dx in patient['diagnoses']:
                            if dx:
                                st.markdown(f'<span class="diagnosis-badge {dx.lower()}">{dx}</span>',
                                          unsafe_allow_html=True)
        else:
            st.info("No patients found matching your search")

elif selected_page == "Imaging Explorer":
    render_enhanced_imaging_explorer(connector, es_indexer)

elif selected_page == "Relationship Explorer":
    render_relationship_explorer(connector)

elif selected_page == "Progression Tracking":
    render_progression_tracking(connector)

elif selected_page == "Network Visualization":
    render_network_visualization_fixed(connector)

elif selected_page == "Biomarker Analysis":
    st.title("🧪 Biomarker Analysis")

    # Biomarker overview
    query = """
    MATCH (b:Biomarker)
    RETURN b.analyte as biomarker,
           b.specimen_type as specimen,
           AVG(b.value) as avg_value,
           MIN(b.value) as min_value,
           MAX(b.value) as max_value,
           STDEV(b.value) as std_dev,
           COUNT(b) as count
    ORDER BY count DESC
    LIMIT 20
    """

    biomarkers = connector.run_query(query)

    if biomarkers:
        df = pd.DataFrame(biomarkers)

        # Distribution plot
        fig = go.Figure()
        for _, row in df.iterrows():
            fig.add_trace(go.Box(
                y=[row['min_value'], row['avg_value'] - row.get('std_dev', 0),
                   row['avg_value'], row['avg_value'] + row.get('std_dev', 0),
                   row['max_value']],
                name=f"{row['biomarker']} ({row['specimen']})",
                boxmean=True
            ))

        fig.update_layout(title="Biomarker Value Distributions",
                        yaxis_title="Value (pg/mL)")
        st.plotly_chart(fig, use_container_width=True)

        # Correlation with diagnosis
        st.subheader("Biomarker-Diagnosis Associations")

        query = """
        MATCH (b:Biomarker)-[:ASSOCIATED_WITH_DIAGNOSIS]->(d:Diagnosis)
        RETURN b.analyte as biomarker,
               d.diagnosis_code as diagnosis,
               COUNT(*) as associations
        ORDER BY associations DESC
        LIMIT 30
        """

        associations = connector.run_query(query)

        if associations:
            df = pd.DataFrame(associations)
            pivot = df.pivot_table(values='associations',
                                  index='biomarker',
                                  columns='diagnosis',
                                  fill_value=0)

            fig = px.imshow(pivot,
                          title="Biomarker-Diagnosis Association Heatmap",
                          labels=dict(x="Diagnosis", y="Biomarker", color="Associations"))
            st.plotly_chart(fig, use_container_width=True)

elif selected_page == "Advanced Query":
    st.title("🔧 Advanced Query Interface")

    # Query templates
    templates = {
        "Custom Query": "",
        "Find Converters (CN→AD)": """
MATCH (p:Patient)-[:HAS_VISIT]->(v1:Visit)-[:HAS_DIAGNOSIS]->(d1:Diagnosis {diagnosis_code: 'CN'})
MATCH (p)-[:HAS_VISIT]->(v2:Visit)-[:HAS_DIAGNOSIS]->(d2:Diagnosis {diagnosis_code: 'AD'})
WHERE v2.months_from_baseline > v1.months_from_baseline
RETURN p.ptid as patient, 
       v2.months_from_baseline - v1.months_from_baseline as months_to_conversion
ORDER BY months_to_conversion
LIMIT 25
        """,
        "Images with Biomarkers": """
MATCH (p:Patient)-[:HAS_IMAGE]->(i:ImageNode)
MATCH (p)-[:HAS_VISIT]->(v:Visit)-[:HAS_BIOMARKER]->(b:Biomarker)
WHERE i.modality = 'MRI'
RETURN p.ptid as patient,
       COUNT(DISTINCT i) as image_count,
       COUNT(DISTINCT b) as biomarker_count,
       COLLECT(DISTINCT b.analyte)[0..5] as biomarkers
LIMIT 25
        """,
        "Multimodal Patients": """
MATCH (p:Patient)
WHERE EXISTS((p)-[:HAS_IMAGE]->())
  AND EXISTS((p)-[:HAS_VISIT]->()-[:HAS_BIOMARKER]->())
  AND EXISTS((p)-[:HAS_VISIT]->()-[:HAS_COGNITIVE_ASSESSMENT]->())
  AND EXISTS((p)-[:HAS_GENETIC_RISK_PROFILE]->())
RETURN p.ptid as patient,
       p.apoe_genotype as apoe,
       COUNT(DISTINCT (p)-[:HAS_IMAGE]->()) as image_count
LIMIT 25
        """
    }

    selected_template = st.selectbox("Select Query Template", list(templates.keys()))

    query = st.text_area("Cypher Query",
                        value=templates[selected_template],
                        height=200)

    if st.button("Execute Query", type="primary"):
        if query:
            try:
                with st.spinner("Executing query..."):
                    results = connector.run_query(query)

                if results:
                    df = pd.DataFrame(results)
                    st.success(f"Found {len(df)} results")

                    # Display results
                    st.dataframe(df, use_container_width=True)

                    # Download option
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Download as CSV",
                        data=csv,
                        file_name=f"query_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("Query returned no results")

            except Exception as e:
                st.error(f"Query execution failed: {e}")

# Display selected image in modal-like view
if st.session_state.selected_image:
    st.markdown("---")
    st.subheader("Image Viewer")

    img = st.session_state.selected_image
    col1, col2 = st.columns([3, 1])

    with col1:
        # Try to display full resolution image
        if img.get('png_path'):
            path = Path(img['png_path'])
            if path.exists():
                try:
                    pil_img = load_and_convert_image(path)
                    if pil_img:
                        st.image(pil_img, caption=img.get('series_description', 'Medical Image'))
                except:
                    st.error("Could not load image")
        else:
            st.info("No image file available")

    with col2:
        st.markdown("**Image Details**")
        st.text(f"ID: {img.get('image_id', 'N/A')[:10]}")
        st.text(f"Patient: {img.get('patient_id', 'N/A')}")
        st.text(f"Modality: {img.get('modality', 'N/A')}")
        st.text(f"Date: {img.get('study_date', 'N/A')}")

        if st.button("Close"):
            st.session_state.selected_image = None
            st.rerun()

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; padding: 20px;'>
        <p>ADNI Knowledge Graph Explorer | Complete Edition</p>
        <p style='font-size: 0.9em;'>Powered by Neo4j & Elasticsearch</p>
    </div>
    """,
    unsafe_allow_html=True
)