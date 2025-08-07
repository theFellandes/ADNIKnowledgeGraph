"""
ADNI Knowledge Graph Streamlit UI
Interactive dashboard for exploring Alzheimer's Disease data
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
from typing import Dict, List, Any, Optional
from pathlib import Path

# Import Neo4j connector
from utils.neo4j_connector import Neo4jConnector

# Page configuration
st.set_page_config(
    page_title="ADNI Knowledge Graph Explorer",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main {
        padding-top: 1rem;
    }
    .stMetric {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        margin: 5px;
    }
    .patient-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    .diagnosis-badge {
        padding: 5px 10px;
        border-radius: 15px;
        font-weight: bold;
        margin: 2px;
        display: inline-block;
    }
    .cn { background-color: #28a745; color: white; }
    .mci { background-color: #ffc107; color: black; }
    .ad { background-color: #dc3545; color: white; }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'connector' not in st.session_state:
    st.session_state.connector = None
if 'selected_patient' not in st.session_state:
    st.session_state.selected_patient = None


# Database connection
@st.cache_resource
def get_connector():
    """Initialize Neo4j connection"""
    try:
        connector = Neo4jConnector(
            uri=st.secrets.get("neo4j_uri", "bolt://localhost:7687"),
            user=st.secrets.get("neo4j_user", "neo4j"),
            password=st.secrets.get("neo4j_password", "your_password")
        )
        if connector.verify_connection():
            return connector
        else:
            return None
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        return None


# Sidebar for navigation
with st.sidebar:
    st.title("🧠 ADNI Knowledge Graph")
    st.markdown("---")

    # Navigation menu
    page = st.selectbox(
        "Navigation",
        ["Dashboard", "Patient Explorer", "Cognitive Assessments",
         "Biomarkers", "Imaging", "Family Relationships",
         "Advanced Query", "Data Export"]
    )

    st.markdown("---")

    # Database connection status
    connector = get_connector()
    if connector:
        st.success("✅ Connected to Neo4j")
        st.session_state.connector = connector
    else:
        st.error("❌ Not connected to database")
        st.stop()

# Main content area
if page == "Dashboard":
    st.title("ADNI Knowledge Graph Dashboard")
    st.markdown("### Overview of the Alzheimer's Disease Neuroimaging Initiative Data")

    # Get summary statistics
    col1, col2, col3, col4 = st.columns(4)

    # Total patients
    patient_count = connector.run_query("MATCH (p:Patient) RETURN count(p) as count")[0]['count']
    col1.metric("Total Patients", f"{patient_count:,}")

    # Total visits
    visit_count = connector.run_query("MATCH (v:Visit) RETURN count(v) as count")[0]['count']
    col2.metric("Total Visits", f"{visit_count:,}")

    # Total images
    image_count = connector.run_query("MATCH (i:ImageNode) RETURN count(i) as count")[0]['count']
    col3.metric("Total Images", f"{image_count:,}")

    # Total assessments
    assessment_count = connector.run_query("MATCH (a:CognitiveAssessment) RETURN count(a) as count")[0]['count']
    col4.metric("Cognitive Assessments", f"{assessment_count:,}")

    st.markdown("---")

    # Diagnosis distribution
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Diagnosis Distribution")
        diagnosis_query = """
        MATCH (d:Diagnosis)
        RETURN d.diagnosis_code as diagnosis, count(d) as count
        ORDER BY count DESC
        """
        diagnosis_data = pd.DataFrame(connector.run_query(diagnosis_query))

        if not diagnosis_data.empty:
            fig = px.pie(diagnosis_data, values='count', names='diagnosis',
                         title="Distribution of Diagnoses",
                         color_discrete_map={'CN': '#28a745', 'MCI': '#ffc107', 'AD': '#dc3545'})
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("APOE Genotype Distribution")
        apoe_query = """
        MATCH (p:Patient)
        WHERE p.apoe_genotype IS NOT NULL
        RETURN p.apoe_genotype as genotype, count(p) as count
        ORDER BY count DESC
        """
        apoe_data = pd.DataFrame(connector.run_query(apoe_query))

        if not apoe_data.empty:
            fig = px.bar(apoe_data, x='genotype', y='count',
                         title="APOE Genotype Distribution")
            st.plotly_chart(fig, use_container_width=True)

    # Recent activity
    st.subheader("Recent Data Additions")
    recent_query = """
    MATCH (n)
    WHERE n.created_at IS NOT NULL
    RETURN labels(n)[0] as type, n.created_at as created_at
    ORDER BY n.created_at DESC
    LIMIT 100
    """
    recent_data = pd.DataFrame(connector.run_query(recent_query))

    if not recent_data.empty:
        recent_data['created_at'] = pd.to_datetime(recent_data['created_at'])
        recent_data['date'] = recent_data['created_at'].dt.date
        activity_summary = recent_data.groupby(['date', 'type']).size().reset_index(name='count')

        fig = px.bar(activity_summary, x='date', y='count', color='type',
                     title="Recent Activity by Entity Type")
        st.plotly_chart(fig, use_container_width=True)

elif page == "Patient Explorer":
    st.title("Patient Explorer")

    # Patient search
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        search_term = st.text_input("Search Patient ID", placeholder="e.g., 002_S_0295")

    with col2:
        diagnosis_filter = st.selectbox("Filter by Diagnosis", ["All", "CN", "MCI", "AD"])

    with col3:
        gender_filter = st.selectbox("Filter by Gender", ["All", "M", "F"])

    # Build query
    where_clauses = []
    params = {}

    if search_term:
        where_clauses.append("p.ptid CONTAINS $search_term")
        params['search_term'] = search_term

    if diagnosis_filter != "All":
        where_clauses.append("""
        EXISTS {
            MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
            WHERE d.diagnosis_code = $diagnosis
        }
        """)
        params['diagnosis'] = diagnosis_filter

    if gender_filter != "All":
        where_clauses.append("p.gender = $gender")
        params['gender'] = gender_filter

    where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Get patients
    patient_query = f"""
    MATCH (p:Patient)
    WHERE {where_clause}
    RETURN p
    ORDER BY p.ptid
    LIMIT 50
    """

    patients = connector.run_query(patient_query, params)

    if patients:
        # Display patients
        st.subheader(f"Found {len(patients)} patients")

        # Patient selection
        patient_ids = [p['p']['ptid'] for p in patients]
        selected_id = st.selectbox("Select a patient to view details:", patient_ids)

        if selected_id:
            st.session_state.selected_patient = selected_id

            # Get patient details
            detail_query = """
            MATCH (p:Patient {ptid: $ptid})
            OPTIONAL MATCH (p)-[:HAS_VISIT]->(v:Visit)
            OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
            OPTIONAL MATCH (p)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember)
            RETURN p, 
                   count(DISTINCT v) as visit_count,
                   collect(DISTINCT d.diagnosis_code) as diagnoses,
                   count(DISTINCT fm) as family_count
            """

            details = connector.run_query(detail_query, {'ptid': selected_id})[0]
            patient = details['p']

            # Patient card
            st.markdown(f"""
            <div class="patient-card">
                <h3>Patient: {patient['ptid']}</h3>
                <p><strong>Gender:</strong> {patient.get('gender', 'Unknown')}</p>
                <p><strong>Age at Baseline:</strong> {patient.get('age_at_baseline', 'Unknown')}</p>
                <p><strong>Education Years:</strong> {patient.get('education_years', 'Unknown')}</p>
                <p><strong>APOE Genotype:</strong> {patient.get('apoe_genotype', 'Unknown')}</p>
                <p><strong>Total Visits:</strong> {details['visit_count']}</p>
                <p><strong>Family Members with Dementia:</strong> {details['family_count']}</p>
            </div>
            """, unsafe_allow_html=True)

            # Diagnosis badges
            if details['diagnoses']:
                st.markdown("**Diagnoses:**")
                diagnosis_html = ""
                for dx in details['diagnoses']:
                    css_class = dx.lower()
                    diagnosis_html += f'<span class="diagnosis-badge {css_class}">{dx}</span>'
                st.markdown(diagnosis_html, unsafe_allow_html=True)

            # Patient timeline
            st.subheader("Patient Timeline")

            timeline_query = """
            MATCH (p:Patient {ptid: $ptid})-[:HAS_VISIT]->(v:Visit)
            OPTIONAL MATCH (v)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
            OPTIONAL MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
            OPTIONAL MATCH (v)-[:HAS_IMAGING]->(i:ImagingStudy)
            RETURN v.months_from_baseline as months,
                   v.visit_id as visit_id,
                   d.diagnosis_code as diagnosis,
                   count(DISTINCT ca) as cognitive_count,
                   count(DISTINCT i) as imaging_count
            ORDER BY v.months_from_baseline
            """

            timeline_data = pd.DataFrame(connector.run_query(timeline_query, {'ptid': selected_id}))

            if not timeline_data.empty:
                fig = go.Figure()

                # Add timeline markers
                for _, row in timeline_data.iterrows():
                    hover_text = f"Visit: {row['visit_id']}<br>"
                    hover_text += f"Diagnosis: {row['diagnosis'] or 'None'}<br>"
                    hover_text += f"Cognitive Assessments: {row['cognitive_count']}<br>"
                    hover_text += f"Imaging Studies: {row['imaging_count']}"

                    color = '#28a745' if row['diagnosis'] == 'CN' else '#ffc107' if row[
                                                                                        'diagnosis'] == 'MCI' else '#dc3545' if \
                    row['diagnosis'] == 'AD' else '#6c757d'

                    fig.add_trace(go.Scatter(
                        x=[row['months']],
                        y=[1],
                        mode='markers+text',
                        marker=dict(size=15, color=color),
                        text=row['diagnosis'] or '',
                        textposition='top center',
                        hovertext=hover_text,
                        hoverinfo='text',
                        showlegend=False
                    ))

                fig.update_layout(
                    title="Patient Visit Timeline",
                    xaxis_title="Months from Baseline",
                    yaxis=dict(visible=False),
                    height=200
                )

                st.plotly_chart(fig, use_container_width=True)

elif page == "Cognitive Assessments":
    st.title("Cognitive Assessments Analysis")

    # Select patient
    if st.session_state.selected_patient:
        patient_id = st.session_state.selected_patient
        st.info(f"Viewing data for patient: {patient_id}")
    else:
        # Patient selection
        patients = connector.run_query("MATCH (p:Patient) RETURN p.ptid as ptid ORDER BY p.ptid LIMIT 100")
        patient_ids = [p['ptid'] for p in patients]
        patient_id = st.selectbox("Select a patient:", patient_ids)

    if patient_id:
        # Get cognitive assessments
        assessment_query = """
        MATCH (p:Patient {ptid: $ptid})-[:HAS_VISIT]->(v:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        RETURN v.months_from_baseline as months,
               ca.test_name as test,
               ca.total_score as score,
               ca.clinical_significance as significance
        ORDER BY v.months_from_baseline, ca.test_name
        """

        assessments = pd.DataFrame(connector.run_query(assessment_query, {'ptid': patient_id}))

        if not assessments.empty:
            # Group by test type
            tests = assessments['test'].unique()

            # Create tabs for different tests
            tabs = st.tabs(tests.tolist())

            for i, test in enumerate(tests):
                with tabs[i]:
                    test_data = assessments[assessments['test'] == test]

                    # Line chart
                    fig = px.line(test_data, x='months', y='score',
                                  title=f"{test} Scores Over Time",
                                  markers=True)

                    # Add clinical significance as color
                    if 'significance' in test_data.columns:
                        fig.add_trace(go.Scatter(
                            x=test_data['months'],
                            y=test_data['score'],
                            mode='markers',
                            marker=dict(
                                size=12,
                                color=test_data['significance'].map({
                                    'normal': 'green',
                                    'mild': 'yellow',
                                    'moderate': 'orange',
                                    'severe': 'red'
                                }).fillna('gray')
                            ),
                            showlegend=False
                        ))

                    st.plotly_chart(fig, use_container_width=True)

                    # Data table
                    st.dataframe(test_data[['months', 'score', 'significance']])
        else:
            st.warning("No cognitive assessments found for this patient")

    # Population comparison
    st.subheader("Population Comparison")

    pop_query = """
    MATCH (ca:CognitiveAssessment)
    MATCH (ca)<-[:HAS_COGNITIVE_ASSESSMENT]-(v:Visit)<-[:HAS_VISIT]-(p:Patient)
    MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
    WHERE ca.test_name IN ['MMSE', 'CDR', 'ADAS-Cog']
    RETURN ca.test_name as test,
           d.diagnosis_code as diagnosis,
           avg(ca.total_score) as avg_score,
           count(ca) as count
    """

    pop_data = pd.DataFrame(connector.run_query(pop_query))

    if not pop_data.empty:
        fig = px.bar(pop_data, x='test', y='avg_score', color='diagnosis',
                     title="Average Cognitive Scores by Diagnosis",
                     barmode='group')
        st.plotly_chart(fig, use_container_width=True)

elif page == "Biomarkers":
    st.title("Biomarker Analysis")

    # Biomarker overview
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("CSF Biomarkers")
        csf_query = """
        MATCH (b:Biomarker)
        WHERE b.biomarker_type = 'CSF'
        RETURN b.analyte as analyte,
               count(b) as measurements,
               avg(b.value) as avg_value,
               sum(CASE WHEN b.abnormal_flag = true THEN 1 ELSE 0 END) as abnormal_count
        ORDER BY measurements DESC
        """
        csf_data = pd.DataFrame(connector.run_query(csf_query))

        if not csf_data.empty:
            st.dataframe(csf_data)

    with col2:
        st.subheader("Plasma Biomarkers")
        plasma_query = """
        MATCH (b:Biomarker)
        WHERE b.biomarker_type = 'PLASMA'
        RETURN b.analyte as analyte,
               count(b) as measurements,
               avg(b.value) as avg_value,
               sum(CASE WHEN b.abnormal_flag = true THEN 1 ELSE 0 END) as abnormal_count
        ORDER BY measurements DESC
        """
        plasma_data = pd.DataFrame(connector.run_query(plasma_query))

        if not plasma_data.empty:
            st.dataframe(plasma_data)

    st.markdown("---")

    # Biomarker trends
    st.subheader("Biomarker Trends by Diagnosis")

    # Select biomarker
    biomarkers = connector.run_query("MATCH (b:Biomarker) RETURN DISTINCT b.analyte as analyte ORDER BY analyte")
    analyte = st.selectbox("Select Biomarker:", [b['analyte'] for b in biomarkers])

    if analyte:
        trend_query = """
        MATCH (b:Biomarker {analyte: $analyte})
        MATCH (b)<-[:HAS_BIOMARKER]-(v:Visit)<-[:HAS_VISIT]-(p:Patient)
        MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WHERE v.months_from_baseline >= 0
        RETURN d.diagnosis_code as diagnosis,
               v.months_from_baseline as months,
               avg(b.value) as avg_value,
               count(b) as count
        ORDER BY months
        """

        trend_data = pd.DataFrame(connector.run_query(trend_query, {'analyte': analyte}))

        if not trend_data.empty:
            fig = px.line(trend_data, x='months', y='avg_value', color='diagnosis',
                          title=f"{analyte} Levels Over Time by Diagnosis",
                          labels={'avg_value': f'Average {analyte} Value', 'months': 'Months from Baseline'})
            st.plotly_chart(fig, use_container_width=True)

    # Biomarker correlations
    st.subheader("Biomarker Correlations")

    corr_query = """
    MATCH (v:Visit)-[:HAS_BIOMARKER]->(b1:Biomarker {analyte: 'ABETA42'})
    MATCH (v)-[:HAS_BIOMARKER]->(b2:Biomarker {analyte: 'TAU'})
    MATCH (v)<-[:HAS_VISIT]-(p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
    RETURN b1.value as abeta42,
           b2.value as tau,
           d.diagnosis_code as diagnosis
    """

    corr_data = pd.DataFrame(connector.run_query(corr_query))

    if not corr_data.empty:
        fig = px.scatter(corr_data, x='abeta42', y='tau', color='diagnosis',
                         title="Amyloid-β42 vs Tau Correlation",
                         labels={'abeta42': 'Aβ42 (pg/mL)', 'tau': 'Tau (pg/mL)'})
        st.plotly_chart(fig, use_container_width=True)

elif page == "Imaging":
    import streamlit as st
    import pandas as pd
    import plotly.graph_objects as go
    from PIL import Image
    import base64
    from io import BytesIO
    from pathlib import Path
    import logging

    # Import cache and search managers
    try:
        from utils.redis_cacher import CacheManager

        cache_available = True
    except ImportError:
        cache_available = False
        logging.warning("Redis cache not available")

    try:
        from utils.elasticsearch_indexer import SearchIndexer

        search_available = True
    except ImportError:
        search_available = False
        logging.warning("Elasticsearch not available")


    # Initialize cache and search managers (cached for session)
    @st.cache_resource
    def get_cache_manager():
        """Initialize Redis cache manager"""
        if cache_available:
            try:
                return CacheManager(host='localhost', port=6379)
            except Exception as e:
                st.warning(f"Could not connect to Redis: {e}")
        return None


    @st.cache_resource
    def get_search_indexer():
        """Initialize Elasticsearch indexer"""
        if search_available:
            try:
                return SearchIndexer(host='localhost', port=9200)
            except Exception as e:
                st.warning(f"Could not connect to Elasticsearch: {e}")
        return None


    def render_imaging_page(connector):
        """
        Render the enhanced imaging page with Redis and Elasticsearch integration

        Args:
            connector: Neo4j connector instance
        """
        st.title("Medical Imaging Explorer")

        # Initialize cache and search
        cache_manager = get_cache_manager()
        search_indexer = get_search_indexer()

        # Show status indicators
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            mri_count = connector.run_query("MATCH (i:ImagingStudy {modality: 'MRI'}) RETURN count(i) as count")[0][
                'count']
            st.metric("MRI Studies", f"{mri_count:,}")

        with col2:
            pet_count = connector.run_query("MATCH (i:ImagingStudy {modality: 'PET'}) RETURN count(i) as count")[0][
                'count']
            st.metric("PET Studies", f"{pet_count:,}")

        with col3:
            total_images = connector.run_query("MATCH (n:ImageNode) RETURN count(n) as count")[0]['count']
            st.metric("Total Images", f"{total_images:,}")

        with col4:
            # Show cache/search status
            status_text = "🟢 " if cache_manager else "🔴 "
            status_text += "Cache | "
            status_text += "🟢 " if search_indexer else "🔴 "
            status_text += "Search"
            st.metric("Services", status_text)

        st.markdown("---")

        # Image Search Section
        if search_indexer:
            st.subheader("🔍 Image Search")

            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                search_query = st.text_input(
                    "Search images",
                    placeholder="e.g., hippocampus, FDG, temporal lobe",
                    help="Search across series descriptions, anatomical regions, and notes"
                )

            with col2:
                modality_filter = st.selectbox("Modality", ["All", "MRI", "PET"])

            with col3:
                max_results = st.number_input("Max Results", min_value=1, max_value=100, value=10)

            if search_query or modality_filter != "All":
                # Build filters
                filters = {}
                if modality_filter != "All":
                    filters['modality'] = modality_filter

                # Execute search
                with st.spinner("Searching..."):
                    search_results = search_indexer.search_images(
                        query=search_query,
                        filters=filters,
                        size=max_results
                    )

                if search_results['total'] > 0:
                    st.success(f"Found {search_results['total']} matching images")

                    # Display results
                    for hit in search_results['hits']:
                        with st.expander(f"📷 {hit['source']['image_id']} - Score: {hit['score']:.2f}"):
                            col1, col2 = st.columns([1, 2])

                            with col1:
                                # Try to load thumbnail from cache or file
                                thumbnail_path = None

                                # Try cache first
                                if cache_manager:
                                    thumbnail_path = cache_manager.get_image_path(
                                        hit['source']['image_id'],
                                        'thumbnail'
                                    )

                                # Fall back to search index
                                if not thumbnail_path:
                                    thumbnail_path = hit['source'].get('thumbnail_path')

                                if thumbnail_path and Path(thumbnail_path).exists():
                                    try:
                                        img = Image.open(thumbnail_path)
                                        st.image(img, use_column_width=True)
                                    except Exception as e:
                                        st.info("Thumbnail not available")
                                else:
                                    st.info("No thumbnail")

                            with col2:
                                st.write(f"**Patient:** {hit['source']['patient_id']}")
                                st.write(f"**Modality:** {hit['source']['modality']}")
                                st.write(f"**Series:** {hit['source']['series_description']}")

                                if 'anatomical_region' in hit['source']:
                                    st.write(f"**Region:** {hit['source']['anatomical_region']}")

                                if 'quality_metrics' in hit['source'] and hit['source']['quality_metrics']:
                                    metrics = hit['source']['quality_metrics']
                                    if 'snr' in metrics:
                                        st.write(f"**SNR:** {metrics['snr']:.2f}")
                                    if 'entropy' in metrics:
                                        st.write(f"**Entropy:** {metrics['entropy']:.2f}")

                                # Highlight matches
                                if 'highlight' in hit and hit['highlight']:
                                    st.write("**Matched in:**")
                                    for field, highlights in hit['highlight'].items():
                                        for highlight in highlights:
                                            st.markdown(f"- {highlight}")
                else:
                    st.info("No images found matching your search")

        st.markdown("---")

        # Patient Image Viewer
        st.subheader("📂 Patient Image Viewer")

        # Select patient
        if st.session_state.get('selected_patient'):
            patient_id = st.session_state.selected_patient
        else:
            patients = connector.run_query(
                "MATCH (p:Patient)-[:HAS_IMAGING_STUDY]->() RETURN DISTINCT p.ptid as ptid ORDER BY p.ptid LIMIT 100"
            )
            patient_id = st.selectbox("Select Patient:", [p['ptid'] for p in patients])

        if patient_id:
            # Check cache for patient images
            cached_studies = []
            if cache_manager:
                # Try to get cached patient data
                cache_key = f"patient:studies:{patient_id}"
                cached_data = cache_manager.get(cache_key)
                if cached_data:
                    st.info("📦 Loading from cache...")
                    cached_studies = cached_data

            if not cached_studies:
                # Get imaging studies from Neo4j
                studies_query = """
                MATCH (p:Patient {ptid: $ptid})-[:HAS_IMAGING_STUDY]->(s:ImagingStudy)
                RETURN s.study_id as study_id,
                       s.modality as modality,
                       s.study_date as date,
                       s.study_description as description
                ORDER BY s.study_date DESC
                """

                studies = pd.DataFrame(connector.run_query(studies_query, {'ptid': patient_id}))

                if not studies.empty:
                    # Cache the studies data
                    if cache_manager:
                        cache_manager.set(
                            f"patient:studies:{patient_id}",
                            studies.to_dict('records'),
                            expire=3600  # Cache for 1 hour
                        )
            else:
                studies = pd.DataFrame(cached_studies)

            if not studies.empty:
                # Study selection
                study_options = studies.apply(
                    lambda x: f"{x['modality']} - {x['date']} - {x['description']}",
                    axis=1
                ).tolist()

                selected_idx = st.selectbox(
                    "Select Study:",
                    range(len(study_options)),
                    format_func=lambda x: study_options[x]
                )

                if selected_idx is not None:
                    study_id = studies.iloc[selected_idx]['study_id']

                    # Try cache first for images
                    cached_images = None
                    if cache_manager:
                        cache_key = f"study:images:{study_id}"
                        cached_images = cache_manager.get(cache_key)

                    if cached_images:
                        st.info("📦 Loading images from cache...")
                        images = pd.DataFrame(cached_images)
                    else:
                        # Get images from Neo4j
                        images_query = """
                        MATCH (s:ImagingStudy {study_id: $study_id})-[:HAS_IMAGE]->(i:ImageNode)
                        RETURN i.image_id as image_id,
                               i.series_description as series,
                               i.anatomical_region as region,
                               i.pet_tracer as tracer,
                               i.diagnostic_path as diagnostic_path,
                               i.preview_path as preview_path,
                               i.thumbnail_path as thumbnail_path,
                               i.file_path as file_path,
                               i.snr as snr,
                               i.entropy as entropy
                        ORDER BY i.slice_number
                        LIMIT 20
                        """

                        images = pd.DataFrame(connector.run_query(images_query, {'study_id': study_id}))

                        # Cache the images data
                        if cache_manager and not images.empty:
                            cache_manager.set(
                                f"study:images:{study_id}",
                                images.to_dict('records'),
                                expire=3600
                            )

                    if not images.empty:
                        st.write(f"Found {len(images)} images in this study")

                        # Image display settings
                        col1, col2 = st.columns([1, 3])
                        with col1:
                            display_mode = st.radio(
                                "Display Mode",
                                ["Thumbnails", "Preview", "Details"]
                            )

                        if display_mode == "Thumbnails":
                            # Display in grid
                            cols = st.columns(4)
                            for idx, (_, img) in enumerate(images.iterrows()):
                                col_idx = idx % 4

                                with cols[col_idx]:
                                    # Try to load image
                                    image_loaded = False

                                    # Check cache for path
                                    if cache_manager:
                                        cached_path = cache_manager.get_image_path(
                                            img['image_id'],
                                            'thumbnail'
                                        )
                                        if cached_path:
                                            img['thumbnail_path'] = cached_path

                                    # Try thumbnail path
                                    if img['thumbnail_path'] and Path(img['thumbnail_path']).exists():
                                        try:
                                            image = Image.open(img['thumbnail_path'])
                                            st.image(image, caption=img['series'], use_column_width=True)
                                            image_loaded = True
                                        except Exception as e:
                                            pass

                                    # Fall back to file_path
                                    if not image_loaded and img['file_path'] and Path(img['file_path']).exists():
                                        try:
                                            image = Image.open(img['file_path'])
                                            st.image(image, caption=img['series'], use_column_width=True)
                                            image_loaded = True
                                        except Exception as e:
                                            pass

                                    if not image_loaded:
                                        st.info(f"Image {idx + 1}")

                        elif display_mode == "Preview":
                            # Display larger previews
                            for _, img in images.iterrows():
                                with st.expander(f"Image: {img['series']}", expanded=False):
                                    col1, col2 = st.columns([2, 1])

                                    with col1:
                                        # Try preview or diagnostic path
                                        image_loaded = False

                                        for path_field in ['preview_path', 'diagnostic_path', 'file_path']:
                                            if img[path_field] and Path(img[path_field]).exists():
                                                try:
                                                    image = Image.open(img[path_field])
                                                    st.image(image, use_column_width=True)
                                                    image_loaded = True
                                                    break
                                                except Exception as e:
                                                    continue

                                        if not image_loaded:
                                            st.info("Preview not available")

                                    with col2:
                                        st.write(f"**ID:** {img['image_id']}")
                                        if img['region']:
                                            st.write(f"**Region:** {img['region']}")
                                        if img['tracer']:
                                            st.write(f"**Tracer:** {img['tracer']}")
                                        if img['snr']:
                                            st.write(f"**SNR:** {img['snr']:.2f}")
                                        if img['entropy']:
                                            st.write(f"**Entropy:** {img['entropy']:.2f}")

                        else:  # Details mode
                            # Display as table with quality metrics
                            display_df = images[['image_id', 'series', 'region', 'snr', 'entropy']].copy()
                            st.dataframe(display_df, use_container_width=True)

                            # Download option
                            csv = display_df.to_csv(index=False)
                            st.download_button(
                                label="Download Image Details",
                                data=csv,
                                file_name=f"study_{study_id}_images.csv",
                                mime="text/csv"
                            )
                    else:
                        st.warning("No images found for this study")
            else:
                st.info("No imaging studies found for this patient")

        # Volumetric analysis section remains the same
        st.markdown("---")
        st.subheader("Brain Volumetric Analysis")

        vol_query = """
        MATCH (vm:VolumetricMeasure)
        MATCH (vm)<-[:HAS_VOLUMETRIC_MEASURE]-(v:Visit)<-[:HAS_VISIT]-(p:Patient)
        MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WHERE vm.region IN ['hippocampus', 'ventricles', 'cortex']
        RETURN vm.region as region,
               d.diagnosis_code as diagnosis,
               avg(vm.volume) as avg_volume,
               count(vm) as count
        ORDER BY region, diagnosis
        """

        vol_data = pd.DataFrame(connector.run_query(vol_query))

        if not vol_data.empty:
            fig = px.bar(vol_data, x='region', y='avg_volume', color='diagnosis',
                         title="Average Brain Volumes by Region and Diagnosis",
                         barmode='group',
                         labels={'avg_volume': 'Average Volume (mm³)'})
            st.plotly_chart(fig, use_container_width=True)


    # Export for use in main UI
    __all__ = ['render_imaging_page', 'get_cache_manager', 'get_search_indexer']

    # Volumetric analysis
    st.subheader("Brain Volumetric Analysis")

    vol_query = """
    MATCH (vm:VolumetricMeasure)
    MATCH (vm)<-[:HAS_VOLUMETRIC_MEASURE]-(v:Visit)<-[:HAS_VISIT]-(p:Patient)
    MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
    WHERE vm.region IN ['hippocampus', 'ventricles', 'cortex']
    RETURN vm.region as region,
           d.diagnosis_code as diagnosis,
           avg(vm.volume) as avg_volume,
           count(vm) as count
    ORDER BY region, diagnosis
    """

    vol_data = pd.DataFrame(connector.run_query(vol_query))

    if not vol_data.empty:
        fig = px.bar(vol_data, x='region', y='avg_volume', color='diagnosis',
                     title="Average Brain Volumes by Region and Diagnosis",
                     barmode='group',
                     labels={'avg_volume': 'Average Volume (mm³)'})
        st.plotly_chart(fig, use_container_width=True)

elif page == "Family Relationships":
    st.title("Family History Analysis")

    # Family statistics
    col1, col2, col3 = st.columns(3)

    family_count = connector.run_query("MATCH (fm:FamilyMember) RETURN count(fm) as count")[0]['count']
    with_dementia = connector.run_query("MATCH (fm:FamilyMember {has_dementia: true}) RETURN count(fm) as count")[0][
        'count']
    patients_with_family = connector.run_query("""
        MATCH (p:Patient)-[:HAS_FAMILY_MEMBER]->()
        RETURN count(DISTINCT p) as count
    """)[0]['count']

    col1.metric("Total Family Members", f"{family_count:,}")
    col2.metric("With Dementia", f"{with_dementia:,}")
    col3.metric("Patients with Family History", f"{patients_with_family:,}")

    st.markdown("---")

    # Family network visualization
    st.subheader("Family Network Visualization")

    # Select patient
    patients_with_family = connector.run_query("""
        MATCH (p:Patient)-[:HAS_FAMILY_MEMBER]->()
        RETURN DISTINCT p.ptid as ptid
        ORDER BY p.ptid
        LIMIT 50
    """)

    if patients_with_family:
        patient_id = st.selectbox("Select Patient:", [p['ptid'] for p in patients_with_family])

        if patient_id:
            # Get family network
            family_query = """
            MATCH (p:Patient {ptid: $ptid})-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember)
            RETURN p.ptid as patient_id,
                   fm.member_id as member_id,
                   fm.relationship_type as relationship,
                   fm.has_dementia as has_dementia,
                   fm.age_at_onset as age_onset
            """

            family_data = pd.DataFrame(connector.run_query(family_query, {'ptid': patient_id}))

            if not family_data.empty:
                # Create network graph
                G = nx.Graph()

                # Add patient node
                G.add_node(patient_id, node_type='patient', label=patient_id)

                # Add family member nodes
                for _, member in family_data.iterrows():
                    label = f"{member['relationship']}\n"
                    if member['has_dementia']:
                        label += "Dementia"
                        if member['age_onset']:
                            label += f" (age {member['age_onset']})"

                    G.add_node(member['member_id'],
                               node_type='family',
                               label=label,
                               has_dementia=member['has_dementia'])

                    G.add_edge(patient_id, member['member_id'])

                # Create plotly figure
                pos = nx.spring_layout(G)

                # Edge trace
                edge_trace = []
                for edge in G.edges():
                    x0, y0 = pos[edge[0]]
                    x1, y1 = pos[edge[1]]
                    edge_trace.append(go.Scatter(x=[x0, x1, None], y=[y0, y1, None],
                                                 mode='lines',
                                                 line=dict(width=1, color='#888'),
                                                 showlegend=False))

                # Node trace
                node_x = []
                node_y = []
                node_color = []
                node_text = []

                for node in G.nodes():
                    x, y = pos[node]
                    node_x.append(x)
                    node_y.append(y)

                    node_data = G.nodes[node]
                    if node_data['node_type'] == 'patient':
                        node_color.append('#1f77b4')
                    elif node_data.get('has_dementia'):
                        node_color.append('#d62728')
                    else:
                        node_color.append('#2ca02c')

                    node_text.append(node_data['label'])

                node_trace = go.Scatter(
                    x=node_x, y=node_y,
                    mode='markers+text',
                    text=node_text,
                    textposition="top center",
                    marker=dict(
                        size=20,
                        color=node_color,
                        line_width=2
                    )
                )

                # Create figure
                fig = go.Figure(data=edge_trace + [node_trace])
                fig.update_layout(
                    title=f"Family Network for Patient {patient_id}",
                    showlegend=False,
                    hovermode='closest',
                    margin=dict(b=0, l=0, r=0, t=40),
                    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                    height=500
                )

                st.plotly_chart(fig, use_container_width=True)

    # Family history impact
    st.subheader("Family History Impact on Diagnosis")

    impact_query = """
    MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
    OPTIONAL MATCH (p)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember {has_dementia: true})
    WITH p, d.diagnosis_code as diagnosis, count(fm) as family_with_dementia
    RETURN diagnosis,
           CASE WHEN family_with_dementia > 0 THEN 'With Family History' ELSE 'No Family History' END as family_history,
           count(p) as patient_count
    ORDER BY diagnosis, family_history
    """

    impact_data = pd.DataFrame(connector.run_query(impact_query))

    if not impact_data.empty:
        fig = px.bar(impact_data, x='diagnosis', y='patient_count', color='family_history',
                     title="Diagnosis Distribution by Family History",
                     barmode='group')
        st.plotly_chart(fig, use_container_width=True)

elif page == "Advanced Query":
    st.title("Advanced Query Interface")
    st.markdown("Execute custom Cypher queries on the knowledge graph")

    # Query templates
    st.subheader("Query Templates")

    templates = {
        "Find patients with specific biomarker pattern": """
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_BIOMARKER]->(b:Biomarker)
WHERE b.analyte = 'ABETA42' AND b.abnormal_flag = true
RETURN DISTINCT p.ptid as patient_id, 
       count(DISTINCT v) as visits_with_abnormal_abeta
ORDER BY visits_with_abnormal_abeta DESC
LIMIT 20
        """,
        "Disease progression patterns": """
MATCH (p:Patient)-[:HAS_VISIT]->(v1:Visit)-[:HAS_DIAGNOSIS]->(d1:Diagnosis)
MATCH (p)-[:HAS_VISIT]->(v2:Visit)-[:HAS_DIAGNOSIS]->(d2:Diagnosis)
WHERE v1.months_from_baseline < v2.months_from_baseline
  AND d1.diagnosis_code <> d2.diagnosis_code
RETURN p.ptid as patient_id,
       d1.diagnosis_code + ' -> ' + d2.diagnosis_code as progression,
       v2.months_from_baseline - v1.months_from_baseline as months_to_progression
ORDER BY months_to_progression
LIMIT 50
        """,
        "Multi-modal data for patients": """
MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)
WHERE v.viscode = 'bl'
OPTIONAL MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
OPTIONAL MATCH (v)-[:HAS_BIOMARKER]->(b:Biomarker)
OPTIONAL MATCH (v)-[:HAS_IMAGING]->(i:ImagingStudy)
RETURN p.ptid as patient_id,
       count(DISTINCT ca) as cognitive_tests,
       count(DISTINCT b) as biomarkers,
       count(DISTINCT i) as imaging_studies
ORDER BY patient_id
LIMIT 100
        """
    }

    selected_template = st.selectbox("Select a query template:", ["Custom Query"] + list(templates.keys()))

    if selected_template == "Custom Query":
        query = st.text_area("Enter Cypher Query:", height=200, placeholder="MATCH (n) RETURN n LIMIT 10")
    else:
        query = st.text_area("Enter Cypher Query:", value=templates[selected_template], height=200)

    # Execute query
    if st.button("Execute Query", type="primary"):
        if query:
            try:
                with st.spinner("Executing query..."):
                    start_time = datetime.now()
                    results = connector.run_query(query)
                    execution_time = (datetime.now() - start_time).total_seconds()

                st.success(f"Query executed successfully in {execution_time:.2f} seconds")

                if results:
                    # Convert to DataFrame
                    df = pd.DataFrame(results)

                    # Display results
                    st.subheader(f"Results ({len(df)} rows)")

                    # Show data
                    st.dataframe(df, use_container_width=True)

                    # Download option
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Download results as CSV",
                        data=csv,
                        file_name=f"query_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("Query returned no results")

            except Exception as e:
                st.error(f"Query execution failed: {str(e)}")

elif page == "Data Export":
    st.title("Data Export")
    st.markdown("Export data from the knowledge graph for external analysis")

    # Export options
    export_type = st.selectbox(
        "Select Export Type:",
        ["Patient Summary", "Cognitive Assessments", "Biomarker Data",
         "Imaging Metadata", "Complete Patient Records"]
    )

    # Configuration
    col1, col2 = st.columns(2)

    with col1:
        limit = st.number_input("Maximum records:", min_value=1, max_value=10000, value=1000)

    with col2:
        format_type = st.selectbox("Export Format:", ["CSV", "JSON"])

    # Build export query based on type
    export_queries = {
        "Patient Summary": """
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[:HAS_VISIT]->(v:Visit)
        OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        RETURN p.ptid as patient_id,
               p.gender as gender,
               p.age_at_baseline as age_baseline,
               p.education_years as education,
               p.apoe_genotype as apoe,
               count(DISTINCT v) as total_visits,
               collect(DISTINCT d.diagnosis_code) as diagnoses
        ORDER BY p.ptid
        LIMIT $limit
        """,
        "Cognitive Assessments": """
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        RETURN p.ptid as patient_id,
               v.visit_id as visit_id,
               v.months_from_baseline as months,
               ca.test_name as test,
               ca.total_score as score,
               ca.clinical_significance as significance
        ORDER BY p.ptid, v.months_from_baseline
        LIMIT $limit
        """,
        "Biomarker Data": """
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_BIOMARKER]->(b:Biomarker)
        RETURN p.ptid as patient_id,
               v.visit_id as visit_id,
               v.months_from_baseline as months,
               b.biomarker_type as type,
               b.analyte as analyte,
               b.value as value,
               b.unit as unit,
               b.abnormal_flag as abnormal
        ORDER BY p.ptid, v.months_from_baseline
        LIMIT $limit
        """,
        "Imaging Metadata": """
        MATCH (p:Patient)-[:HAS_IMAGING_STUDY]->(s:ImagingStudy)
        OPTIONAL MATCH (s)-[:HAS_IMAGE]->(i:ImageNode)
        RETURN p.ptid as patient_id,
               s.study_id as study_id,
               s.modality as modality,
               s.study_date as date,
               count(i) as image_count
        ORDER BY p.ptid, s.study_date
        LIMIT $limit
        """,
        "Complete Patient Records": """
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[:HAS_VISIT]->(v:Visit)
        OPTIONAL MATCH (v)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        OPTIONAL MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        OPTIONAL MATCH (v)-[:HAS_BIOMARKER]->(b:Biomarker)
        RETURN p.ptid as patient_id,
               p as patient_data,
               collect(DISTINCT v) as visits,
               collect(DISTINCT d) as diagnoses,
               collect(DISTINCT ca) as cognitive_assessments,
               collect(DISTINCT b) as biomarkers
        ORDER BY p.ptid
        LIMIT $limit
        """
    }

    # Export button
    if st.button("Generate Export", type="primary"):
        query = export_queries[export_type]

        with st.spinner(f"Exporting {export_type}..."):
            try:
                results = connector.run_query(query, {'limit': limit})

                if results:
                    if format_type == "CSV":
                        # Flatten nested data for CSV
                        df = pd.DataFrame(results)

                        # Handle lists in cells
                        for col in df.columns:
                            if df[col].apply(lambda x: isinstance(x, list)).any():
                                df[col] = df[col].apply(lambda x: ', '.join(map(str, x)) if isinstance(x, list) else x)

                        csv_data = df.to_csv(index=False)

                        st.download_button(
                            label=f"Download {export_type} as CSV",
                            data=csv_data,
                            file_name=f"{export_type.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                    else:  # JSON
                        json_data = json.dumps(results, indent=2, default=str)

                        st.download_button(
                            label=f"Download {export_type} as JSON",
                            data=json_data,
                            file_name=f"{export_type.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                            mime="application/json"
                        )

                    st.success(f"Export ready! Found {len(results)} records.")
                else:
                    st.warning("No data found for export")

            except Exception as e:
                st.error(f"Export failed: {str(e)}")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
        ADNI Knowledge Graph Explorer | Built with Streamlit & Neo4j
    </div>
    """,
    unsafe_allow_html=True
)