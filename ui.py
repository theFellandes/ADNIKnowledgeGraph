"""
Enhanced ADNI Knowledge Graph UI with Advanced Visualizations
Includes ATN framework, disease progression, biomarker correlations, and more
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
import colorsys

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

# Enhanced CSS with better styles
st.markdown("""
<style>
    /* Dark mode compatibility */
    @media (prefers-color-scheme: dark) {
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white !important;
        }

        .atn-profile {
            background: #2d2d2d !important;
            color: white !important;
        }

        .patient-card {
            background: #2d2d2d !important;
            color: white !important;
            border-left: 5px solid #667eea;
        }

        .network-legend {
            background: #2d2d2d !important;
            color: white !important;
        }

        /* Fix text visibility in dark mode */
        .stMarkdown, .stText, p, h1, h2, h3, h4, h5, h6 {
            color: inherit !important;
        }
    }

    .main { padding-top: 1rem; }

    /* Enhanced metric cards */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 15px;
        margin: 10px 0;
        box-shadow: 0 10px 20px rgba(0,0,0,0.1);
        transition: transform 0.3s ease;
    }
    .metric-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 30px rgba(0,0,0,0.15);
    }
    .metric-card h2, .metric-card p {
        color: white !important;
    }

    /* ATN Profile styles */
    .atn-profile {
        background: white;
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        margin: 15px 0;
    }
    .atn-status {
        display: inline-block;
        padding: 8px 16px;
        border-radius: 20px;
        font-weight: bold;
        margin: 5px;
    }
    .atn-positive { 
        background: #ff6b6b; 
        color: white !important;
    }
    .atn-negative { 
        background: #51cf66; 
        color: white !important;
    }

    /* Disease stage badges */
    .stage-badge {
        padding: 10px 20px;
        border-radius: 25px;
        font-weight: bold;
        margin: 5px;
        display: inline-block;
        text-transform: uppercase;
        font-size: 0.9rem;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        color: white !important;
    }
    .stage-cn { background: linear-gradient(135deg, #667eea, #764ba2); }
    .stage-smc { background: linear-gradient(135deg, #f093fb, #f5576c); }
    .stage-emci { background: linear-gradient(135deg, #4facfe, #00f2fe); }
    .stage-lmci { background: linear-gradient(135deg, #43e97b, #38f9d7); }
    .stage-ad { background: linear-gradient(135deg, #fa709a, #fee140); }

    /* Risk level indicators */
    .risk-indicator {
        padding: 12px 24px;
        border-radius: 30px;
        font-weight: bold;
        text-align: center;
        margin: 10px 0;
    }
    .risk-low { 
        background: #d3f9d8; 
        color: #2b8a3e !important;
    }
    .risk-moderate { 
        background: #fff3cd; 
        color: #f08c00 !important;
    }
    .risk-high { 
        background: #ffe0e0; 
        color: #c92a2a !important;
    }
    .risk-very-high { 
        background: #ff6b6b; 
        color: white !important;
    }

    /* Enhanced patient card */
    .patient-card {
        background: white;
        padding: 25px;
        border-radius: 15px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        margin-bottom: 20px;
        border-left: 5px solid #667eea;
        transition: all 0.3s ease;
    }
    .patient-card:hover {
        transform: translateX(5px);
        box-shadow: 0 8px 20px rgba(0,0,0,0.15);
    }

    /* Biomarker trend indicator */
    .biomarker-trend {
        display: inline-flex;
        align-items: center;
        padding: 5px 12px;
        border-radius: 15px;
        font-size: 0.9rem;
    }
    .trend-up { 
        background: #ffe0e0; 
        color: #c92a2a !important;
    }
    .trend-down { 
        background: #d3f9d8; 
        color: #2b8a3e !important;
    }
    .trend-stable { 
        background: #e3fafc; 
        color: #0c8599 !important;
    }

    /* Network legend */
    .network-legend {
        background: white;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        margin-top: 20px;
    }

    /* Enhanced tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
        background: linear-gradient(to right, #f8f9fa, #ffffff);
        padding: 10px;
        border-radius: 10px;
    }

    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding: 0 24px;
        background-color: white;
        border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea, #764ba2);
        color: white !important;
    }

    /* Image viewer modal */
    .image-viewer-modal {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.9);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 9999;
    }

    .image-viewer-content {
        max-width: 90%;
        max-height: 90%;
        background: white;
        border-radius: 10px;
        padding: 20px;
    }
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
if 'show_image_modal' not in st.session_state:
    st.session_state.show_image_modal = False


# Database connection functions
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

@st.cache_resource
def get_es_indexer():
    """Initialize Elasticsearch connection"""
    try:
        from utils.elasticsearch_indexer import SearchIndexer

        es_host = st.secrets.get("es_host", "localhost")
        es_port = st.secrets.get("es_port", 9200)

        indexer = SearchIndexer(host=es_host, port=es_port)

        if indexer.es and indexer.es.ping():
            return indexer
        return None
    except Exception as e:
        logger.warning(f"Elasticsearch connection failed: {e}")
        return None

# ============================================================================
# NEW ENHANCED COMPONENTS
# ============================================================================

def render_atn_framework_visualization(connector):
    """Render ATN (Amyloid-Tau-Neurodegeneration) framework visualization"""
    st.title("🧬 ATN Framework Analysis")
    st.markdown("""
    The ATN framework is a biological classification system for Alzheimer's disease based on:
    - **A**: Amyloid β deposition (Aβ42)
    - **T**: Tau pathology (p-Tau181)
    - **N**: Neurodegeneration (Total Tau, FDG-PET, MRI atrophy)
    """)

    # First check if ATN profiles exist
    query = """
    MATCH (p:Patient)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
    RETURN atn.profile as profile,
           atn.amyloid_status as A,
           atn.tau_status as T,
           atn.neurodegeneration_status as N,
           COUNT(p) as count
    ORDER BY count DESC
    """

    profiles = connector.run_query(query)

    # If no ATN profiles exist, try to compute them from biomarkers
    if not profiles:
        st.info("Computing ATN profiles from biomarker data...")

        query = """
        MATCH (p:Patient)-[:HAS_BIOMARKER]->(b:Biomarker)
        WHERE b.analyte IN ['Aβ42', 'Total Tau', 'p-Tau181']
        WITH p,
             MAX(CASE WHEN b.analyte = 'Aβ42' AND b.value < 600 THEN 1 ELSE 0 END) as a_pos,
             MAX(CASE WHEN b.analyte = 'p-Tau181' AND b.value > 80 THEN 1 ELSE 0 END) as t_pos,
             MAX(CASE WHEN b.analyte = 'Total Tau' AND b.value > 400 THEN 1 ELSE 0 END) as n_pos
        WITH CASE WHEN a_pos = 1 THEN 'A+' ELSE 'A-' END as A,
             CASE WHEN t_pos = 1 THEN 'T+' ELSE 'T-' END as T,
             CASE WHEN n_pos = 1 THEN 'N+' ELSE 'N-' END as N,
             COUNT(p) as count
        WITH A + '/' + T + '/' + N as profile, A, T, N, count
        RETURN profile, A, T, N, count
        ORDER BY count DESC
        """

        profiles = connector.run_query(query)

    if profiles:
        col1, col2 = st.columns([2, 1])

        with col1:
            # Create distribution chart
            df = pd.DataFrame(profiles)

            # Simple bar chart if Sankey would be too complex
            fig = px.bar(df, x='profile', y='count',
                        title="ATN Profile Distribution",
                        labels={'profile': 'ATN Profile', 'count': 'Number of Patients'})

            # Color bars based on profile
            colors = []
            for profile in df['profile']:
                if 'A+' in profile and 'T+' in profile and 'N+' in profile:
                    colors.append('#ff6b6b')  # High risk - red
                elif 'A+' in profile:
                    colors.append('#ffa94d')  # Moderate risk - orange
                else:
                    colors.append('#51cf66')  # Low risk - green

            fig.update_traces(marker_color=colors)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown("### Profile Statistics")

            # Show profile counts
            for profile in profiles[:5]:
                # Determine risk level based on profile
                risk_level = "high" if 'A+' in profile['A'] and 'T+' in profile['T'] else "moderate" if 'A+' in profile['A'] else "low"

                st.markdown(f"""
                <div class="atn-profile">
                    <h4>{profile['profile']}</h4>
                    <span class="atn-status {'atn-positive' if 'A+' in profile['A'] else 'atn-negative'}">{profile['A']}</span>
                    <span class="atn-status {'atn-positive' if 'T+' in profile['T'] else 'atn-negative'}">{profile['T']}</span>
                    <span class="atn-status {'atn-positive' if 'N+' in profile['N'] else 'atn-negative'}">{profile['N']}</span>
                    <p style="margin-top: 10px;">Patients: <strong>{profile['count']}</strong></p>
                    <div class="risk-indicator risk-{risk_level}">Risk: {risk_level.upper()}</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.warning("No biomarker data available to compute ATN profiles")

        # Show what biomarker data is available
        query = """
        MATCH (b:Biomarker)
        RETURN b.analyte as analyte,
               COUNT(b) as count,
               AVG(b.value) as avg_value
        ORDER BY count DESC
        LIMIT 10
        """

        biomarkers = connector.run_query(query)

        if biomarkers:
            st.subheader("Available Biomarker Data")
            df_bio = pd.DataFrame(biomarkers)
            st.dataframe(df_bio, use_container_width=True)

    # ATN correlation with diagnosis (with fallback)
    st.subheader("ATN Profiles and Clinical Diagnosis")

    # First try with existing ATN profiles
    query = """
    MATCH (p:Patient)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
    MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
    WHERE d.diagnosis_code IN ['CN', 'MCI', 'AD']
    WITH atn.profile as atn_profile,
         d.diagnosis_code as diagnosis,
         COUNT(*) as count
    RETURN atn_profile, diagnosis, count
    ORDER BY atn_profile, diagnosis
    """

    correlations = connector.run_query(query)

    # If no ATN profiles, compute from biomarkers
    if not correlations:
        query = """
        MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WHERE d.diagnosis_code IN ['CN', 'MCI', 'AD']
        OPTIONAL MATCH (p)-[:HAS_BIOMARKER]->(b:Biomarker)
        WHERE b.analyte IN ['Aβ42', 'Total Tau', 'p-Tau181']
        WITH p, d.diagnosis_code as diagnosis,
             MAX(CASE WHEN b.analyte = 'Aβ42' AND b.value < 600 THEN 1 ELSE 0 END) as a_pos,
             MAX(CASE WHEN b.analyte = 'p-Tau181' AND b.value > 80 THEN 1 ELSE 0 END) as t_pos,
             MAX(CASE WHEN b.analyte = 'Total Tau' AND b.value > 400 THEN 1 ELSE 0 END) as n_pos
        WHERE a_pos IS NOT NULL OR t_pos IS NOT NULL OR n_pos IS NOT NULL
        WITH diagnosis,
             CASE WHEN a_pos = 1 THEN 'A+' ELSE 'A-' END + '/' +
             CASE WHEN t_pos = 1 THEN 'T+' ELSE 'T-' END + '/' +
             CASE WHEN n_pos = 1 THEN 'N+' ELSE 'N-' END as atn_profile,
             COUNT(*) as count
        RETURN atn_profile, diagnosis, count
        ORDER BY atn_profile, diagnosis
        """

        correlations = connector.run_query(query)

    if correlations:
        df_corr = pd.DataFrame(correlations)

        # Create a pivot table for visualization
        if not df_corr.empty:
            pivot = df_corr.pivot_table(index='atn_profile', columns='diagnosis', values='count', fill_value=0)

            fig = px.imshow(pivot,
                           labels=dict(x="Clinical Diagnosis", y="ATN Profile", color="Count"),
                           title="ATN Profile vs Clinical Diagnosis Correlation",
                           color_continuous_scale='Viridis')
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Insufficient data to show ATN-diagnosis correlations")

def render_disease_progression_pathways(connector):
    """Render comprehensive disease progression pathways"""
    st.title("📈 Disease Progression Pathways")

    tab1, tab2, tab3, tab4 = st.tabs(["Progression Patterns", "Individual Trajectories",
                                       "Risk Factors", "Survival Analysis"])

    with tab1:
        st.subheader("Common Progression Patterns")

        # Get progression patterns
        query = """
        MATCH (d1:Diagnosis)-[r:PROGRESSED_TO]->(d2:Diagnosis)
        WITH d1.diagnosis_code as from_stage, 
             d2.diagnosis_code as to_stage,
             COUNT(r) as transitions,
             AVG(r.duration_months) as avg_duration
        WHERE transitions > 5
        RETURN from_stage, to_stage, transitions, 
               round(avg_duration, 1) as avg_months
        ORDER BY transitions DESC
        """

        progressions = connector.run_query(query)

        if progressions:
            # Create Sankey diagram
            df = pd.DataFrame(progressions)

            # Get unique stages
            all_stages = list(set(df['from_stage'].tolist() + df['to_stage'].tolist()))
            stage_colors = {
                'CN': '#667eea',
                'SMC': '#f093fb',
                'EMCI': '#4facfe',
                'LMCI': '#43e97b',
                'MCI': '#38f9d7',
                'AD': '#fa709a'
            }

            fig = go.Figure(data=[go.Sankey(
                node=dict(
                    pad=15,
                    thickness=30,
                    line=dict(color="black", width=0.5),
                    label=all_stages,
                    color=[stage_colors.get(s, '#888888') for s in all_stages]
                ),
                link=dict(
                    source=[all_stages.index(s) for s in df['from_stage']],
                    target=[all_stages.index(t) for t in df['to_stage']],
                    value=df['transitions'].tolist(),
                    customdata=df['avg_months'].tolist(),
                    hovertemplate='%{source.label} → %{target.label}<br>' +
                                 'Patients: %{value}<br>' +
                                 'Avg Duration: %{customdata} months<extra></extra>'
                )
            )])

            fig.update_layout(
                title="Disease Stage Progression Patterns",
                height=600
            )
            st.plotly_chart(fig, use_container_width=True)

            # Show statistics
            st.markdown("### Progression Statistics")

            col1, col2, col3 = st.columns(3)

            with col1:
                fast_progressors = df[df['avg_months'] < 24]
                if not fast_progressors.empty:
                    st.metric("Fast Progressions (<2 years)",
                             f"{fast_progressors['transitions'].sum()} patients")

            with col2:
                typical_progressors = df[(df['avg_months'] >= 24) & (df['avg_months'] <= 48)]
                if not typical_progressors.empty:
                    st.metric("Typical Progressions (2-4 years)",
                             f"{typical_progressors['transitions'].sum()} patients")

            with col3:
                slow_progressors = df[df['avg_months'] > 48]
                if not slow_progressors.empty:
                    st.metric("Slow Progressions (>4 years)",
                             f"{slow_progressors['transitions'].sum()} patients")

    with tab2:
        st.subheader("Individual Patient Trajectories")

        patient_id = st.text_input("Enter Patient ID", placeholder="e.g., 002_S_0295")

        if patient_id:
            # Get patient's complete trajectory
            query = """
            MATCH (p:Patient {ptid: $patient_id})-[:HAS_VISIT]->(v:Visit)
            OPTIONAL MATCH (v)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
            OPTIONAL MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
            OPTIONAL MATCH (v)-[:HAS_BIOMARKER]->(b:Biomarker)
            WITH v, d, 
                 COLLECT(DISTINCT {test: ca.test_name, score: ca.total_score}) as assessments,
                 COLLECT(DISTINCT {analyte: b.analyte, value: b.value}) as biomarkers
            RETURN v.months_from_baseline as months,
                   d.diagnosis_code as diagnosis,
                   assessments,
                   biomarkers
            ORDER BY months
            """

            trajectory = connector.run_query(query, {'patient_id': patient_id})

            if trajectory:
                # Create multi-axis plot
                fig = make_subplots(
                    rows=3, cols=1,
                    subplot_titles=("Clinical Diagnosis", "Cognitive Scores", "Biomarkers"),
                    vertical_spacing=0.1,
                    specs=[[{"secondary_y": False}],
                          [{"secondary_y": True}],
                          [{"secondary_y": True}]]
                )

                # Process trajectory data
                months = [t['months'] for t in trajectory]
                diagnoses = [t['diagnosis'] for t in trajectory if t['diagnosis']]

                # Add diagnosis progression
                if diagnoses:
                    dx_map = {'CN': 0, 'SMC': 1, 'EMCI': 2, 'LMCI': 3, 'MCI': 3.5, 'AD': 4}
                    dx_values = [dx_map.get(d, 0) for d in diagnoses]

                    fig.add_trace(
                        go.Scatter(x=months[:len(diagnoses)], y=dx_values,
                                  mode='lines+markers',
                                  name='Diagnosis Stage',
                                  line=dict(width=3, color='#667eea')),
                        row=1, col=1
                    )

                # Add cognitive scores
                mmse_scores = []
                cdr_scores = []
                for t in trajectory:
                    for assessment in t['assessments']:
                        if assessment['test'] == 'MMSE':
                            mmse_scores.append((t['months'], assessment['score']))
                        elif assessment['test'] == 'CDR':
                            cdr_scores.append((t['months'], assessment['score']))

                if mmse_scores:
                    fig.add_trace(
                        go.Scatter(x=[s[0] for s in mmse_scores],
                                  y=[s[1] for s in mmse_scores],
                                  mode='lines+markers',
                                  name='MMSE',
                                  line=dict(color='#4facfe')),
                        row=2, col=1
                    )

                if cdr_scores:
                    fig.add_trace(
                        go.Scatter(x=[s[0] for s in cdr_scores],
                                  y=[s[1] for s in cdr_scores],
                                  mode='lines+markers',
                                  name='CDR',
                                  line=dict(color='#f093fb'),
                                  yaxis="y2"),
                        row=2, col=1, secondary_y=True
                    )

                # Add biomarkers
                abeta_values = []
                tau_values = []
                for t in trajectory:
                    for biomarker in t['biomarkers']:
                        if biomarker and biomarker.get('analyte') is not None and biomarker.get('value') is not None:
                            analyte = str(biomarker['analyte'])  # Convert to string to be safe
                            if any(marker in analyte for marker in ['Aβ42', 'Abeta', 'AB42', 'Amyloid']):
                                abeta_values.append((t['months'], biomarker['value']))
                        elif 'Tau' in biomarker['analyte'] and 'p-' not in biomarker['analyte']:
                            tau_values.append((t['months'], biomarker['value']))

                if abeta_values:
                    fig.add_trace(
                        go.Scatter(x=[v[0] for v in abeta_values],
                                  y=[v[1] for v in abeta_values],
                                  mode='lines+markers',
                                  name='Aβ42',
                                  line=dict(color='#fa709a')),
                        row=3, col=1
                    )

                if tau_values:
                    fig.add_trace(
                        go.Scatter(x=[v[0] for v in tau_values],
                                  y=[v[1] for v in tau_values],
                                  mode='lines+markers',
                                  name='Total Tau',
                                  line=dict(color='#fee140'),
                                  yaxis="y3"),
                        row=3, col=1, secondary_y=True
                    )

                fig.update_xaxes(title_text="Months from Baseline", row=3, col=1)
                fig.update_layout(height=900, title=f"Complete Disease Trajectory for {patient_id}")
                st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("Risk Factor Analysis")

        # Genetic risk distribution
        query = """
        MATCH (p:Patient)
        WHERE p.apoe_genotype IS NOT NULL
        WITH p.apoe_genotype as genotype,
             COUNT(*) as count,
             COLLECT(p.ptid)[..5] as sample_patients
        RETURN genotype, count
        ORDER BY count DESC
        """

        apoe_dist = connector.run_query(query)

        if apoe_dist:
            col1, col2 = st.columns(2)

            with col1:
                df_apoe = pd.DataFrame(apoe_dist)

                # Calculate risk levels
                def get_risk_level(genotype):
                    if 'E4/E4' in str(genotype):
                        return 'Very High (10-15x)'
                    elif 'E3/E4' in str(genotype) or 'E2/E4' in str(genotype):
                        return 'High (3-4x)'
                    elif 'E2/E2' in str(genotype) or 'E2/E3' in str(genotype):
                        return 'Protective (0.6x)'
                    else:
                        return 'Normal (1x)'

                df_apoe['risk_level'] = df_apoe['genotype'].apply(get_risk_level)

                fig = px.sunburst(df_apoe,
                                 path=['risk_level', 'genotype'],
                                 values='count',
                                 title="APOE Genotype Risk Distribution")
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.markdown("### Combined Risk Factors")

                # Get patients with multiple risk factors
                query = """
                MATCH (p:Patient)
                WHERE p.apoe_genotype CONTAINS 'E4'
                OPTIONAL MATCH (p)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember {has_dementia: true})
                WITH p, COUNT(fm) as family_risk
                WHERE family_risk > 0
                RETURN p.apoe_genotype as apoe,
                       family_risk,
                       COUNT(p) as patients
                ORDER BY patients DESC
                LIMIT 10
                """

                multi_risk = connector.run_query(query)

                if multi_risk:
                    for risk in multi_risk:
                        risk_score = 3 if 'E3/E4' in risk['apoe'] else 12 if 'E4/E4' in risk['apoe'] else 2
                        risk_score *= (1 + risk['family_risk'] * 0.5)

                        risk_class = 'risk-very-high' if risk_score > 10 else 'risk-high' if risk_score > 5 else 'risk-moderate'

                        st.markdown(f"""
                        <div class="risk-indicator {risk_class}">
                            APOE: {risk['apoe']}<br>
                            Family Members with Dementia: {risk['family_risk']}<br>
                            Patients: {risk['patients']}<br>
                            Combined Risk Score: {risk_score:.1f}x
                        </div>
                        """, unsafe_allow_html=True)

def render_biomarker_correlation_matrix(connector):
    """Render comprehensive biomarker correlation analysis"""
    st.title("🧪 Biomarker Correlation Analysis")

    # Get biomarker correlations
    query = """
    MATCH (v:Visit)-[:HAS_BIOMARKER]->(b1:Biomarker)
    MATCH (v)-[:HAS_BIOMARKER]->(b2:Biomarker)
    WHERE b1.analyte < b2.analyte
    AND b1.analyte IN ['Aβ42', 'Total Tau', 'p-Tau181']
    AND b2.analyte IN ['Aβ42', 'Total Tau', 'p-Tau181']
    WITH b1.analyte as biomarker1,
         b2.analyte as biomarker2,
         COLLECT([b1.value, b2.value]) as pairs
    WHERE SIZE(pairs) > 10
    RETURN biomarker1, biomarker2, pairs
    """

    correlations = connector.run_query(query)

    if correlations:
        # Calculate correlation coefficients
        correlation_matrix = {}

        for corr in correlations:
            pairs = corr['pairs']
            if len(pairs) > 0:
                values1 = [p[0] for p in pairs if p[0] is not None and p[1] is not None]
                values2 = [p[1] for p in pairs if p[0] is not None and p[1] is not None]

                if len(values1) > 1:
                    correlation = np.corrcoef(values1, values2)[0, 1]
                    key = f"{corr['biomarker1']}_{corr['biomarker2']}"
                    correlation_matrix[key] = correlation

        # Create correlation heatmap
        biomarkers = ['Aβ42', 'Total Tau', 'p-Tau181']
        matrix = np.eye(len(biomarkers))

        for i, bio1 in enumerate(biomarkers):
            for j, bio2 in enumerate(biomarkers):
                if i != j:
                    key = f"{bio1}_{bio2}" if bio1 < bio2 else f"{bio2}_{bio1}"
                    if key in correlation_matrix:
                        matrix[i, j] = correlation_matrix[key]
                        matrix[j, i] = correlation_matrix[key]

        fig = go.Figure(data=go.Heatmap(
            z=matrix,
            x=biomarkers,
            y=biomarkers,
            colorscale='RdBu',
            zmid=0,
            text=np.round(matrix, 2),
            texttemplate='%{text}',
            textfont={"size": 14},
            colorbar=dict(title="Correlation")
        ))

        fig.update_layout(
            title="CSF Biomarker Correlation Matrix",
            height=500
        )
        st.plotly_chart(fig, use_container_width=True)

    # Biomarker trajectories by diagnosis
    st.subheader("Biomarker Trajectories by Diagnosis Group")

    query = """
    MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
    MATCH (p)-[:HAS_VISIT]->(v:Visit)-[:HAS_BIOMARKER]->(b:Biomarker)
    WHERE d.diagnosis_code IN ['CN', 'MCI', 'AD']
    AND b.analyte IN ['Aβ42', 'Total Tau', 'p-Tau181']
    RETURN d.diagnosis_code as diagnosis,
           b.analyte as biomarker,
           v.months_from_baseline as months,
           AVG(b.value) as avg_value,
           STDEV(b.value) as std_value,
           COUNT(b) as n
    ORDER BY diagnosis, biomarker, months
    """

    trajectories = connector.run_query(query)

    if trajectories:
        df_traj = pd.DataFrame(trajectories)

        # Create subplot for each biomarker
        biomarkers = df_traj['biomarker'].unique()
        fig = make_subplots(rows=1, cols=len(biomarkers),
                           subplot_titles=biomarkers)

        colors = {'CN': '#667eea', 'MCI': '#4facfe', 'AD': '#fa709a'}

        for idx, biomarker in enumerate(biomarkers):
            bio_data = df_traj[df_traj['biomarker'] == biomarker]

            for diagnosis in ['CN', 'MCI', 'AD']:
                diag_data = bio_data[bio_data['diagnosis'] == diagnosis]

                if not diag_data.empty:
                    fig.add_trace(
                        go.Scatter(
                            x=diag_data['months'],
                            y=diag_data['avg_value'],
                            mode='lines+markers',
                            name=diagnosis,
                            line=dict(color=colors[diagnosis]),
                            showlegend=(idx == 0)
                        ),
                        row=1, col=idx+1
                    )

        fig.update_xaxes(title_text="Months from Baseline")
        fig.update_layout(height=400, title="Biomarker Trajectories by Diagnosis Group")
        st.plotly_chart(fig, use_container_width=True)

def render_family_risk_network(connector):
    """Render family history and genetic risk network"""
    st.title("👨‍👩‍👧‍👦 Family History & Genetic Risk Network")

    col1, col2 = st.columns([2, 1])

    with col1:
        # Get family risk statistics
        query = """
        MATCH (p:Patient)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember)
        WITH p, 
             SUM(CASE WHEN fm.has_dementia THEN 1 ELSE 0 END) as affected,
             COUNT(fm) as total
        WHERE affected > 0
        RETURN affected, COUNT(p) as patients
        ORDER BY affected DESC
        """

        family_stats = connector.run_query(query)

        if family_stats:
            # Create family risk visualization
            fig = go.Figure()

            for stat in family_stats:
                fig.add_trace(go.Bar(
                    x=[f"{stat['affected']} affected"],
                    y=[stat['patients']],
                    name=f"{stat['affected']} affected family members",
                    marker_color='rgba(102, 126, 234, ' + str(0.3 + stat['affected'] * 0.15) + ')'
                ))

            fig.update_layout(
                title="Distribution of Patients by Number of Affected Family Members",
                xaxis_title="Number of Affected Family Members",
                yaxis_title="Number of Patients",
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("### Family Risk Categories")

        # Get family relationship types
        query = """
        MATCH (fm:FamilyMember {has_dementia: true})
        RETURN fm.relationship_type as relationship,
               COUNT(fm) as count
        ORDER BY count DESC
        """

        relationships = connector.run_query(query)

        if relationships:
            for rel in relationships:
                st.markdown(f"""
                <div class="patient-card">
                    <h4>{rel['relationship'].replace('_', ' ').title()}</h4>
                    <p>Affected: <strong>{rel['count']}</strong></p>
                </div>
                """, unsafe_allow_html=True)

    # Combined genetic and family risk
    st.subheader("Combined Genetic & Family Risk Analysis")

    query = """
    MATCH (p:Patient)
    WHERE p.apoe_genotype IS NOT NULL
    OPTIONAL MATCH (p)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember {has_dementia: true})
    WITH p.apoe_genotype as genotype,
         COUNT(DISTINCT fm) as family_affected,
         COUNT(DISTINCT p) as patients
    RETURN genotype, family_affected, patients
    ORDER BY genotype, family_affected
    """

    combined_risk = connector.run_query(query)

    if combined_risk:
        # Create risk matrix
        df_risk = pd.DataFrame(combined_risk)
        pivot = df_risk.pivot_table(values='patients',
                                   index='genotype',
                                   columns='family_affected',
                                   fill_value=0)

        fig = px.imshow(pivot,
                       labels=dict(x="Family Members with Dementia",
                                 y="APOE Genotype",
                                 color="Patients"),
                       title="Combined Genetic and Family Risk Matrix",
                       color_continuous_scale='YlOrRd')
        st.plotly_chart(fig, use_container_width=True)

def render_cognitive_decline_patterns(connector):
    """Render cognitive decline pattern analysis"""
    st.title("🧠 Cognitive Decline Patterns")

    # First try to get cognitive trajectories if they exist
    query = """
    MATCH (p:Patient)-[:HAS_COGNITIVE_TRAJECTORY]->(traj:CognitiveTrajectory)
    WHERE traj.trajectory_type IN ['declining', 'stable', 'improving']
    RETURN traj.test_name as test,
           traj.trajectory_type as trajectory,
           COUNT(p) as patients,
           AVG(traj.change_rate) as avg_change_rate
    ORDER BY test, trajectory
    """

    trajectories = connector.run_query(query)

    if trajectories:
        df = pd.DataFrame(trajectories)

        # Create grouped bar chart
        fig = px.bar(df, x='test', y='patients', color='trajectory',
                    title="Cognitive Trajectory Distribution by Test",
                    color_discrete_map={
                        'declining': '#fa709a',
                        'stable': '#4facfe',
                        'improving': '#43e97b'
                    })
        st.plotly_chart(fig, use_container_width=True)

        # Show decline rates
        st.subheader("Average Decline Rates")

        declining = df[df['trajectory'] == 'declining']
        if not declining.empty:
            cols = st.columns(len(declining))

            for idx, (_, row) in enumerate(declining.iterrows()):
                with cols[idx]:
                    st.metric(
                        row['test'],
                        f"{abs(row['avg_change_rate']):.3f} points/month",
                        f"{row['patients']} patients"
                    )
    else:
        # Fallback: Calculate trajectories from raw data
        st.info("Computing cognitive trajectories from assessment data...")

        # Get cognitive assessment changes over time
        query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        WITH p, ca.test_name as test, 
             v.months_from_baseline as months,
             ca.total_score as score
        ORDER BY p.ptid, test, months
        WITH p.ptid as patient_id, test,
             COLLECT({months: months, score: score}) as scores
        WHERE SIZE(scores) >= 2
        WITH test, patient_id, scores,
             scores[0].score as first_score,
             scores[-1].score as last_score,
             scores[-1].months - scores[0].months as duration
        WHERE duration > 0
        WITH test, patient_id,
             CASE 
                 WHEN test = 'MMSE' THEN
                     CASE 
                         WHEN (first_score - last_score) > 3 THEN 'declining'
                         WHEN (first_score - last_score) < -2 THEN 'improving'
                         ELSE 'stable'
                     END
                 WHEN test IN ['ADAS-Cog', 'ADAS-Cog13'] THEN
                     CASE 
                         WHEN (last_score - first_score) > 4 THEN 'declining'
                         WHEN (last_score - first_score) < -3 THEN 'improving'
                         ELSE 'stable'
                     END
                 WHEN test = 'CDR' THEN
                     CASE 
                         WHEN (last_score - first_score) > 0.5 THEN 'declining'
                         WHEN (last_score - first_score) < -0.5 THEN 'improving'
                         ELSE 'stable'
                     END
                 ELSE
                     CASE 
                         WHEN (first_score - last_score) > 2 THEN 'declining'
                         WHEN (first_score - last_score) < -2 THEN 'improving'
                         ELSE 'stable'
                     END
             END as trajectory,
             (first_score - last_score) / duration as change_rate
        RETURN test, trajectory, 
               COUNT(DISTINCT patient_id) as patients,
               AVG(change_rate) as avg_change_rate
        ORDER BY test, trajectory
        """

        trajectories = connector.run_query(query)

        if trajectories:
            df = pd.DataFrame(trajectories)

            # Create grouped bar chart
            fig = px.bar(df, x='test', y='patients', color='trajectory',
                        title="Cognitive Trajectory Distribution by Test (Computed)",
                        color_discrete_map={
                            'declining': '#fa709a',
                            'stable': '#4facfe',
                            'improving': '#43e97b'
                        })
            st.plotly_chart(fig, use_container_width=True)

            # Show statistics
            st.subheader("Trajectory Statistics")

            col1, col2, col3 = st.columns(3)

            # Calculate totals safely
            total_patients = df['patients'].sum()
            if total_patients > 0:
                declining_patients = df[df['trajectory'] == 'declining']['patients'].sum()
                stable_patients = df[df['trajectory'] == 'stable']['patients'].sum()
                improving_patients = df[df['trajectory'] == 'improving']['patients'].sum()

                col1.metric("Declining", f"{declining_patients} patients",
                           f"{declining_patients/total_patients*100:.1f}%")
                col2.metric("Stable", f"{stable_patients} patients",
                           f"{stable_patients/total_patients*100:.1f}%")
                col3.metric("Improving", f"{improving_patients} patients",
                           f"{improving_patients/total_patients*100:.1f}%")
        else:
            st.warning("No cognitive assessment data available to compute trajectories")

            # Show available cognitive tests
            query = """
            MATCH (ca:CognitiveAssessment)
            RETURN ca.test_name as test,
                   COUNT(ca) as count,
                   AVG(ca.total_score) as avg_score,
                   MIN(ca.total_score) as min_score,
                   MAX(ca.total_score) as max_score
            ORDER BY count DESC
            """

            tests = connector.run_query(query)

            if tests:
                st.subheader("Available Cognitive Assessment Data")
                df_tests = pd.DataFrame(tests)

                fig = px.bar(df_tests, x='test', y='count',
                           title="Cognitive Assessments by Test Type")
                st.plotly_chart(fig, use_container_width=True)

                st.dataframe(df_tests, use_container_width=True)

def render_multimodal_patient_profile(connector):
    """Render comprehensive multimodal patient profiles"""
    st.title("🔬 Multimodal Patient Profiles")

    patient_id = st.text_input("Patient ID for Multimodal Analysis",
                              placeholder="e.g., 002_S_0295")

    if patient_id:
        # Get comprehensive patient data
        col1, col2, col3 = st.columns(3)

        # Basic demographics
        with col1:
            query = """
            MATCH (p:Patient {ptid: $patient_id})
            OPTIONAL MATCH (p)-[:HAS_GENETIC_RISK]->(gr:GeneticRiskProfile)
            RETURN p.gender as gender,
                   p.age_at_baseline as age,
                   p.apoe_genotype as apoe,
                   p.education_years as education,
                   gr.risk_level as genetic_risk
            """

            demo = connector.run_query(query, {'patient_id': patient_id})

            if demo:
                st.markdown("### Demographics")
                data = demo[0]
                st.write(f"**Gender:** {data.get('gender', 'N/A')}")
                st.write(f"**Age at Baseline:** {data.get('age', 'N/A')}")
                st.write(f"**Education:** {data.get('education', 'N/A')} years")
                st.write(f"**APOE:** {data.get('apoe', 'N/A')}")

                risk_level = data.get('genetic_risk', 'unknown')
                if risk_level and risk_level != 'unknown':
                    risk_class = f"risk-{risk_level.lower()}"
                    st.markdown(f'<div class="{risk_class}">Genetic Risk: {risk_level.upper()}</div>',
                              unsafe_allow_html=True)
                else:
                    st.markdown('<div class="risk-indicator risk-moderate">Genetic Risk: Unknown</div>',
                              unsafe_allow_html=True)

        # Current diagnosis
        with col2:
            query = """
            MATCH (p:Patient {ptid: $patient_id})-[:HAS_DIAGNOSIS]->(d:Diagnosis)
            RETURN d.diagnosis_code as diagnosis,
                   d.confidence as confidence
            ORDER BY d.visit_id DESC
            LIMIT 1
            """

            dx = connector.run_query(query, {'patient_id': patient_id})

            if dx:
                st.markdown("### Current Diagnosis")
                diagnosis = dx[0]['diagnosis']
                confidence = dx[0].get('confidence', 0)

                stage_class = f"stage-{diagnosis.lower()}"
                st.markdown(f'<div class="stage-badge {stage_class}">{diagnosis}</div>',
                          unsafe_allow_html=True)
                st.write(f"**Confidence:** {confidence*100:.0f}%")

        # ATN Profile
        with col3:
            query = """
            MATCH (p:Patient {ptid: $patient_id})-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
            RETURN atn.profile as profile,
                   atn.amyloid_status as A,
                   atn.tau_status as T,
                   atn.neurodegeneration_status as N
            """

            atn = connector.run_query(query, {'patient_id': patient_id})

            if atn:
                st.markdown("### ATN Profile")
                profile = atn[0]

                st.markdown(f"""
                <div class="atn-profile">
                    <span class="atn-status {'atn-positive' if '+' in profile['A'] else 'atn-negative'}">{profile['A']}</span>
                    <span class="atn-status {'atn-positive' if '+' in profile['T'] else 'atn-negative'}">{profile['T']}</span>
                    <span class="atn-status {'atn-positive' if '+' in profile['N'] else 'atn-negative'}">{profile['N']}</span>
                </div>
                """, unsafe_allow_html=True)

        # Multimodal data visualization
        st.markdown("---")
        st.subheader("Longitudinal Multimodal Data")

        # Get all modality data
        query = """
        MATCH (p:Patient {ptid: $patient_id})-[:HAS_VISIT]->(v:Visit)
        OPTIONAL MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        OPTIONAL MATCH (v)-[:HAS_BIOMARKER]->(b:Biomarker)
        OPTIONAL MATCH (v)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        OPTIONAL MATCH (v)-[:HAS_VOLUMETRIC_MEASURE]->(vol:VolumetricMeasure)
        WITH v.months_from_baseline as months,
             COUNT(DISTINCT ca) as cognitive_count,
             COUNT(DISTINCT b) as biomarker_count,
             COUNT(DISTINCT d) as diagnosis_count,
             COUNT(DISTINCT vol) as imaging_count
        RETURN months, cognitive_count, biomarker_count, 
               diagnosis_count, imaging_count
        ORDER BY months
        """

        modalities = connector.run_query(query, {'patient_id': patient_id})

        if modalities:
            df_modal = pd.DataFrame(modalities)

            # Create stacked area chart
            fig = go.Figure()

            modality_colors = {
                'cognitive_count': '#667eea',
                'biomarker_count': '#4facfe',
                'diagnosis_count': '#fa709a',
                'imaging_count': '#43e97b'
            }

            for modality, color in modality_colors.items():
                fig.add_trace(go.Scatter(
                    x=df_modal['months'],
                    y=df_modal[modality],
                    mode='lines',
                    name=modality.replace('_count', '').title(),
                    stackgroup='one',
                    fillcolor=color
                ))

            fig.update_layout(
                title=f"Multimodal Data Availability Timeline for {patient_id}",
                xaxis_title="Months from Baseline",
                yaxis_title="Number of Assessments",
                hovermode='x unified'
            )
            st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# ENHANCED EXISTING COMPONENTS (keeping original functionality)
# ============================================================================

def render_enhanced_dashboard(connector):
    """Enhanced dashboard with new visualizations"""
    st.title("🧠 ADNI Knowledge Graph Dashboard")

    # Enhanced metrics with gradients
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        patient_count = connector.get_node_count("Patient")
        st.markdown(f"""
        <div class="metric-card">
            <h2 style="color: white; margin: 0;">{patient_count:,}</h2>
            <p style="color: rgba(255,255,255,0.9); margin: 0;">Total Patients</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        # Get patients with ATN profiles
        query = "MATCH (p:Patient)-[:HAS_ATN_PROFILE]->() RETURN COUNT(DISTINCT p) as count"
        result = connector.run_query(query)
        atn_count = result[0]['count'] if result else 0

        st.markdown(f"""
        <div class="metric-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
            <h2 style="color: white; margin: 0;">{atn_count:,}</h2>
            <p style="color: rgba(255,255,255,0.9); margin: 0;">ATN Profiles</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        # Get biomarker count
        biomarker_count = connector.get_node_count("Biomarker")
        st.markdown(f"""
        <div class="metric-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
            <h2 style="color: white; margin: 0;">{biomarker_count:,}</h2>
            <p style="color: rgba(255,255,255,0.9); margin: 0;">Biomarkers</p>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        # Get progression events
        query = "MATCH ()-[r:PROGRESSED_TO]->() RETURN COUNT(r) as count"
        result = connector.run_query(query)
        prog_count = result[0]['count'] if result else 0

        st.markdown(f"""
        <div class="metric-card" style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);">
            <h2 style="color: white; margin: 0;">{prog_count:,}</h2>
            <p style="color: rgba(255,255,255,0.9); margin: 0;">Progressions</p>
        </div>
        """, unsafe_allow_html=True)

    # Disease stage distribution
    st.markdown("### 📊 Disease Stage Distribution")

    # First try to get disease stages from AT_STAGE relationships
    query = """
    MATCH (p:Patient)-[:AT_STAGE]->(stage:DiseaseStage)
    RETURN stage.name as stage_name,
           stage.stage_id as stage_id,
           stage.order as stage_order,
           COUNT(p) as patient_count
    ORDER BY stage_order
    """

    stages = connector.run_query(query)

    # If no AT_STAGE relationships, fall back to diagnosis distribution
    if not stages:
        query = """
        MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WHERE d.diagnosis_code IN ['CN', 'SMC', 'EMCI', 'LMCI', 'MCI', 'AD']
        WITH d.diagnosis_code as stage_id,
             COUNT(DISTINCT p) as patient_count
        RETURN stage_id,
               CASE stage_id
                   WHEN 'CN' THEN 'Cognitively Normal'
                   WHEN 'SMC' THEN 'Subjective Memory Concern'
                   WHEN 'EMCI' THEN 'Early MCI'
                   WHEN 'LMCI' THEN 'Late MCI'
                   WHEN 'MCI' THEN 'Mild Cognitive Impairment'
                   WHEN 'AD' THEN 'Alzheimer Disease'
                   ELSE stage_id
               END as stage_name,
               CASE stage_id
                   WHEN 'CN' THEN 1
                   WHEN 'SMC' THEN 2
                   WHEN 'EMCI' THEN 3
                   WHEN 'LMCI' THEN 4
                   WHEN 'MCI' THEN 3.5
                   WHEN 'AD' THEN 5
                   ELSE 6
               END as stage_order,
               patient_count
        ORDER BY stage_order
        """

        stages = connector.run_query(query)

    if stages:
        df_stages = pd.DataFrame(stages)

        # Create funnel chart
        fig = go.Figure(go.Funnel(
            y=df_stages['stage_name'],
            x=df_stages['patient_count'],
            textposition="inside",
            textinfo="value+percent total",
            marker=dict(color=['#667eea', '#f093fb', '#4facfe', '#43e97b', '#fa709a'])
        ))

        fig.update_layout(title="Patient Distribution Across Disease Stages")
        st.plotly_chart(fig, use_container_width=True)

    # Cohort comparison
    st.markdown("### 🔬 Research Cohort Comparison")

    # First try with ResearchCohort nodes
    query = """
    MATCH (p:Patient)-[:BELONGS_TO_COHORT]->(c:ResearchCohort)
    OPTIONAL MATCH (p)-[:HAS_BIOMARKER]->(b:Biomarker)
    WHERE b.analyte IN ['Aβ42', 'Total Tau', 'p-Tau181']
    WITH c.cohort_type as cohort,
         b.analyte as biomarker,
         AVG(b.value) as avg_value,
         STDEV(b.value) as std_value
    WHERE biomarker IS NOT NULL
    RETURN cohort, biomarker, avg_value, std_value
    ORDER BY cohort, biomarker
    """

    cohort_bio = connector.run_query(query)

    # If no ResearchCohort nodes, fall back to diagnosis-based cohorts
    if not cohort_bio:
        query = """
        MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WHERE d.diagnosis_code IN ['CN', 'MCI', 'AD']
        OPTIONAL MATCH (p)-[:HAS_BIOMARKER]->(b:Biomarker)
        WHERE b.analyte IN ['Aβ42', 'Total Tau', 'p-Tau181']
        WITH d.diagnosis_code as cohort,
             b.analyte as biomarker,
             AVG(b.value) as avg_value,
             STDEV(b.value) as std_value
        WHERE biomarker IS NOT NULL
        RETURN cohort, biomarker, avg_value, std_value
        ORDER BY cohort, biomarker
        """

        cohort_bio = connector.run_query(query)

    if cohort_bio:
        df_cohort = pd.DataFrame(cohort_bio)

        # Create grouped bar chart
        fig = px.bar(df_cohort, x='cohort', y='avg_value',
                    color='biomarker', barmode='group',
                    error_y='std_value',
                    title="Average Biomarker Levels by Research Cohort",
                    color_discrete_sequence=['#667eea', '#4facfe', '#fa709a'])
        st.plotly_chart(fig, use_container_width=True)


def render_fixed_biomarker_analysis(connector):
    """Fixed biomarker analysis based on Step 11"""
    st.title("🧪 Comprehensive Biomarker Analysis")

    # Check what biomarker data exists
    check_query = """
    MATCH (b:Biomarker)
    RETURN COUNT(b) as count,
           COLLECT(DISTINCT b.biomarker_type)[..5] as types,
           COLLECT(DISTINCT b.analyte)[..10] as analytes
    """

    check_result = connector.run_query(check_query)

    if check_result and check_result[0]['count'] > 0:
        st.success(f"Found {check_result[0]['count']} biomarkers")

        tabs = st.tabs(["Overview", "CSF Biomarkers", "Genetic Markers", "ATN Profiles", "Correlations"])

        with tabs[0]:
            # Biomarker distribution
            dist_query = """
            MATCH (b:Biomarker)
            RETURN b.biomarker_type as type,
                   b.analyte as analyte,
                   COUNT(b) as count,
                   AVG(b.value) as avg_value,
                   MIN(b.value) as min_value,
                   MAX(b.value) as max_value
            ORDER BY count DESC
            LIMIT 20
            """

            dist_results = connector.run_query(dist_query)

            if dist_results:
                df = pd.DataFrame(dist_results)

                # Create distribution chart
                fig = px.bar(df, x='analyte', y='count', color='type',
                             title="Biomarker Distribution by Type",
                             labels={'count': 'Number of Measurements'})
                st.plotly_chart(fig, use_container_width=True)

                # Show statistics table
                st.subheader("Biomarker Statistics")
                st.dataframe(df, use_container_width=True)

        with tabs[1]:
            st.subheader("CSF Biomarker Analysis")

            # CSF biomarkers by diagnosis
            csf_query = """
            MATCH (p:Patient)-[:HAS_BIOMARKER]->(b:Biomarker)
            WHERE b.biomarker_type = 'CSF'
            OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
            WITH b.analyte as biomarker,
                 d.diagnosis_code as diagnosis,
                 AVG(b.value) as avg_value,
                 STDEV(b.value) as std_value,
                 COUNT(b) as count
            WHERE diagnosis IS NOT NULL
            RETURN biomarker, diagnosis, avg_value, std_value, count
            ORDER BY biomarker, diagnosis
            """

            csf_results = connector.run_query(csf_query)

            if csf_results:
                df_csf = pd.DataFrame(csf_results)

                # Create grouped bar chart
                fig = px.bar(df_csf, x='diagnosis', y='avg_value',
                             color='biomarker', barmode='group',
                             error_y='std_value',
                             title="CSF Biomarker Levels by Diagnosis",
                             labels={'avg_value': 'Average Value (pg/mL)'})
                st.plotly_chart(fig, use_container_width=True)

                # Abnormality rates
                abnormal_query = """
                MATCH (b:Biomarker)
                WHERE b.biomarker_type = 'CSF'
                RETURN b.analyte as biomarker,
                       SUM(CASE WHEN b.abnormal_flag = true THEN 1 ELSE 0 END) as abnormal,
                       COUNT(b) as total,
                       100.0 * SUM(CASE WHEN b.abnormal_flag = true THEN 1 ELSE 0 END) / COUNT(b) as abnormal_rate
                ORDER BY abnormal_rate DESC
                """

                abnormal_results = connector.run_query(abnormal_query)

                if abnormal_results:
                    st.subheader("Abnormality Rates")
                    df_abnormal = pd.DataFrame(abnormal_results)

                    fig = px.bar(df_abnormal, x='biomarker', y='abnormal_rate',
                                 title="CSF Biomarker Abnormality Rates",
                                 labels={'abnormal_rate': 'Abnormal Rate (%)'})
                    st.plotly_chart(fig, use_container_width=True)

        with tabs[2]:
            st.subheader("Genetic Markers Analysis")

            # APOE distribution
            apoe_query = """
            MATCH (b:Biomarker)
            WHERE b.biomarker_type = 'Genetic' AND b.analyte = 'APOE'
            RETURN b.genotype as genotype,
                   b.e4_copies as e4_copies,
                   COUNT(b) as count,
                   AVG(b.value) as risk_score
            ORDER BY risk_score DESC
            """

            apoe_results = connector.run_query(apoe_query)

            if apoe_results:
                df_apoe = pd.DataFrame(apoe_results)

                fig = px.sunburst(df_apoe,
                                  path=['e4_copies', 'genotype'],
                                  values='count',
                                  title="APOE Genotype Distribution")
                st.plotly_chart(fig, use_container_width=True)

        with tabs[3]:
            st.subheader("ATN Profile Analysis")

            # Get ATN profiles
            atn_query = """
            MATCH (bp:BiomarkerProfile)
            RETURN bp.atn_status as atn_profile,
                   bp.risk_score as risk_score,
                   COUNT(bp) as count
            ORDER BY count DESC
            """

            atn_results = connector.run_query(atn_query)

            if atn_results:
                df_atn = pd.DataFrame(atn_results)

                fig = px.bar(df_atn, x='atn_profile', y='count',
                             color='risk_score',
                             title="ATN Profile Distribution",
                             color_continuous_scale='RdYlGn_r')
                st.plotly_chart(fig, use_container_width=True)

        with tabs[4]:
            st.subheader("Biomarker Correlations")

            # Get correlations
            corr_query = """
            MATCH (v:Visit)-[:HAS_BIOMARKER]->(b1:Biomarker)
            MATCH (v)-[:HAS_BIOMARKER]->(b2:Biomarker)
            WHERE b1.analyte < b2.analyte
            AND b1.value IS NOT NULL AND b2.value IS NOT NULL
            WITH b1.analyte as biomarker1,
                 b2.analyte as biomarker2,
                 COLLECT([b1.value, b2.value]) as pairs
            WHERE SIZE(pairs) >= 10
            RETURN biomarker1, biomarker2, SIZE(pairs) as count
            """

            corr_results = connector.run_query(corr_query)

            if corr_results:
                st.info(f"Found {len(corr_results)} biomarker pairs with correlations")

                # Create network visualization
                G = nx.Graph()
                for corr in corr_results:
                    G.add_edge(corr['biomarker1'], corr['biomarker2'],
                               weight=corr['count'])

                if G.number_of_nodes() > 0:
                    pos = nx.spring_layout(G)

                    edge_trace = []
                    for edge in G.edges():
                        x0, y0 = pos[edge[0]]
                        x1, y1 = pos[edge[1]]
                        edge_trace.append(go.Scatter(
                            x=[x0, x1, None],
                            y=[y0, y1, None],
                            mode='lines',
                            line=dict(width=0.5, color='#888'),
                            hoverinfo='none'
                        ))

                    node_trace = go.Scatter(
                        x=[pos[node][0] for node in G.nodes()],
                        y=[pos[node][1] for node in G.nodes()],
                        mode='markers+text',
                        text=list(G.nodes()),
                        textposition="top center",
                        marker=dict(size=10, color='#667eea'),
                        hoverinfo='text'
                    )

                    fig = go.Figure(data=edge_trace + [node_trace],
                                    layout=go.Layout(
                                        title='Biomarker Correlation Network',
                                        showlegend=False,
                                        hovermode='closest'
                                    ))
                    st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No biomarker data found in the database")

# ============================================================================
# ORIGINAL FUNCTIONS FROM EXISTING UI (PRESERVED)
# ============================================================================

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

        # First check if VolumetricMeasure nodes exist and have data
        check_query = """
        MATCH (v:VolumetricMeasure)
        RETURN COUNT(v) as count, 
               COLLECT(DISTINCT keys(v))[0] as sample_keys
        LIMIT 1
        """

        check_result = connector.run_query(check_query)

        if check_result and check_result[0]['count'] > 0:
            # Check available properties
            available_keys = check_result[0].get('sample_keys', [])

            # Try different property names that might exist
            volume_prop = 'volume' if 'volume' in available_keys else 'value' if 'value' in available_keys else None
            region_prop = 'region' if 'region' in available_keys else 'brain_region' if 'brain_region' in available_keys else 'anatomical_region' if 'anatomical_region' in available_keys else None

            if volume_prop and region_prop:
                query = f"""
                MATCH (v:VolumetricMeasure)
                WHERE v.{region_prop} IS NOT NULL AND v.{volume_prop} IS NOT NULL
                RETURN v.{region_prop} as region,
                       AVG(v.{volume_prop}) as avg_volume,
                       MIN(v.{volume_prop}) as min_volume,
                       MAX(v.{volume_prop}) as max_volume,
                       COUNT(v) as count
                ORDER BY count DESC
                LIMIT 10
                """

                volumes = connector.run_query(query)
            else:
                # Fallback: just show what properties exist
                query = """
                MATCH (v:VolumetricMeasure)
                RETURN properties(v) as props
                LIMIT 5
                """

                sample_volumes = connector.run_query(query)
                if sample_volumes:
                    st.info(f"VolumetricMeasure nodes found but with different properties: {available_keys}")
                    st.write("Sample data:", sample_volumes[0] if sample_volumes else {})
                volumes = None
        else:
            volumes = None

            # Try alternative: Look for imaging-related data in other nodes
            st.info("No volumetric measures found. Checking for alternative imaging data...")

            # Check for ImageNode statistics
            query = """
            MATCH (i:ImageNode)
            WHERE i.modality IS NOT NULL
            RETURN i.modality as modality,
                   COUNT(i) as count,
                   COUNT(DISTINCT i.patient_id) as unique_patients
            ORDER BY count DESC
            """

            image_stats = connector.run_query(query)

            if image_stats:
                st.subheader("Available Imaging Data")
                df_img = pd.DataFrame(image_stats)

                fig = px.bar(df_img, x='modality', y='count',
                           title="Images by Modality",
                           text='count')
                fig.update_traces(texttemplate='%{text}', textposition='outside')
                st.plotly_chart(fig, use_container_width=True)

                # Show patient coverage
                for _, row in df_img.iterrows():
                    st.write(f"**{row['modality']}**: {row['count']} images from {row['unique_patients']} patients")

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

            # Additional analysis
            st.subheader("Volume Statistics by Region")
            st.dataframe(df, use_container_width=True)

def render_image_viewer_modal():
    """Render full-screen image viewer modal"""
    if st.session_state.selected_image and st.session_state.show_image_modal:
        img = st.session_state.selected_image

        # Create modal layout
        st.markdown("---")
        st.markdown("### 🖼️ Image Viewer")

        col1, col2 = st.columns([4, 1])

        with col1:
            # Try different image paths
            image_displayed = False

            # Try PNG path first
            if img.get('png_path'):
                path = Path(img['png_path'])
                if path.exists():
                    try:
                        pil_img = load_and_convert_image(path)
                        if pil_img:
                            st.image(pil_img,
                                     caption=img.get('series_description', 'Medical Image'),
                                     use_container_width=True)
                            image_displayed = True
                    except Exception as e:
                        logger.error(f"Error loading PNG: {e}")

            # Try thumbnail if PNG failed
            if not image_displayed and img.get('thumbnail_path'):
                path = Path(img['thumbnail_path'])
                if path.exists():
                    try:
                        pil_img = load_and_convert_image(path)
                        if pil_img:
                            # Scale up thumbnail for better visibility
                            width, height = pil_img.size
                            pil_img = pil_img.resize((width * 3, height * 3), Image.LANCZOS)
                            st.image(pil_img,
                                     caption=img.get('series_description', 'Medical Image'),
                                     use_container_width=True)
                            image_displayed = True
                    except Exception as e:
                        logger.error(f"Error loading thumbnail: {e}")

            if not image_displayed:
                st.error("Image file not found or could not be loaded")
                st.info(f"Tried paths: {img.get('png_path', 'N/A')}, {img.get('thumbnail_path', 'N/A')}")

        with col2:
            st.markdown("**Image Details**")
            st.text(f"ID: {img.get('image_id', 'N/A')[:20]}")
            st.text(f"Patient: {img.get('patient_id', 'N/A')}")
            st.text(f"Modality: {img.get('modality', 'N/A')}")
            st.text(f"Study Date: {img.get('study_date', 'N/A')}")

            if img.get('series_description'):
                st.text(f"Series: {img['series_description'][:30]}")

            st.markdown("---")

            if st.button("Close Viewer", type="primary", key="close_viewer"):
                st.session_state.show_image_modal = False
                st.session_state.selected_image = None
                st.rerun()


# ============================================================================
# FIXED RELATIONSHIP EXPLORER
# ============================================================================

def render_fixed_relationship_explorer(connector):
    """Fixed relationship explorer with all working options"""
    st.title("🔗 Relationship Explorer")

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
        render_clinical_progression(connector)

    elif selected_type == "Biomarker Correlations":
        render_biomarker_correlations(connector)

    elif selected_type == "Family Relationships":
        render_family_relationships(connector)

    elif selected_type == "Temporal Sequences":
        render_temporal_sequences(connector)

    elif selected_type == "Genetic Risk":
        render_genetic_risk_relationships(connector)

    elif selected_type == "Multimodal Connections":
        render_multimodal_connections(connector)


def render_temporal_sequences(connector):
    """Fixed temporal sequence visualization"""
    st.subheader("Temporal Sequences")

    # Get temporal relationships
    query = """
    MATCH (v1:Visit)-[r:FOLLOWED_BY|PRECEDES]->(v2:Visit)
    WITH v1.patient_id as patient,
         v1.months_from_baseline as start_month,
         v2.months_from_baseline as end_month,
         r.months_delta as duration
    WHERE duration IS NOT NULL
    RETURN AVG(duration) as avg_duration,
           MIN(duration) as min_duration,
           MAX(duration) as max_duration,
           COUNT(*) as sequence_count
    """

    result = connector.run_query(query)

    if result and result[0]['sequence_count'] > 0:
        stats = result[0]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Sequences", f"{stats['sequence_count']:,}")
        col2.metric("Avg Duration", f"{stats['avg_duration']:.1f} months")
        col3.metric("Min Duration", f"{stats['min_duration']:.1f} months")
        col4.metric("Max Duration", f"{stats['max_duration']:.1f} months")

        # Timeline visualization
        timeline_query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)
        WITH p.ptid as patient, 
             COLLECT({months: v.months_from_baseline, visit_id: v.visit_id}) as visits
        WHERE SIZE(visits) >= 3
        RETURN patient, visits
        ORDER BY SIZE(visits) DESC
        LIMIT 20
        """

        timeline_results = connector.run_query(timeline_query)

        if timeline_results:
            st.subheader("Patient Visit Timelines")

            fig = go.Figure()

            for idx, patient_data in enumerate(timeline_results):
                visits = sorted(patient_data['visits'], key=lambda x: x['months'])
                months = [v['months'] for v in visits]

                fig.add_trace(go.Scatter(
                    x=months,
                    y=[idx] * len(months),
                    mode='markers+lines',
                    name=patient_data['patient'][:10],
                    marker=dict(size=8),
                    line=dict(width=2)
                ))

            fig.update_layout(
                title="Patient Visit Sequences",
                xaxis_title="Months from Baseline",
                yaxis_title="Patient",
                height=600,
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No temporal sequences found. Creating them now...")

        # Create temporal relationships
        create_query = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v1:Visit)
        MATCH (p)-[:HAS_VISIT]->(v2:Visit)
        WHERE v1.months_from_baseline < v2.months_from_baseline
        WITH v1, v2, v2.months_from_baseline - v1.months_from_baseline as delta
        ORDER BY v1.visit_id, delta
        WITH v1, COLLECT({visit: v2, delta: delta})[0] as next_visit
        WHERE next_visit IS NOT NULL
        WITH v1, next_visit.visit as v2, next_visit.delta as delta
        MERGE (v1)-[r:FOLLOWED_BY {months_delta: delta}]->(v2)
        RETURN COUNT(r) as created
        """

        creation_result = connector.run_query(create_query)
        if creation_result:
            st.success(f"Created {creation_result[0]['created']} temporal relationships")
            st.rerun()


def render_genetic_risk_relationships(connector):
    """Fixed genetic risk visualization"""
    st.subheader("Genetic Risk Relationships")

    # Check for genetic risk profiles
    query = """
    MATCH (p:Patient)
    WHERE p.apoe_genotype IS NOT NULL
    WITH p.apoe_genotype as genotype,
         CASE 
            WHEN p.apoe_genotype CONTAINS '4/4' THEN 'Very High'
            WHEN p.apoe_genotype CONTAINS '4' THEN 'High'
            WHEN p.apoe_genotype CONTAINS '2' THEN 'Protective'
            ELSE 'Normal'
         END as risk_level,
         COUNT(p) as count
    RETURN genotype, risk_level, count
    ORDER BY count DESC
    """

    results = connector.run_query(query)

    if results:
        df = pd.DataFrame(results)

        # Create sunburst chart
        fig = px.sunburst(df, path=['risk_level', 'genotype'],
                          values='count',
                          title="APOE Genetic Risk Distribution",
                          color_discrete_sequence=px.colors.sequential.RdBu_r)
        st.plotly_chart(fig, use_container_width=True)

        # Risk correlation with diagnosis
        corr_query = """
        MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WHERE p.apoe_genotype IS NOT NULL
        WITH p.apoe_genotype as genotype,
             d.diagnosis_code as diagnosis,
             COUNT(*) as count
        RETURN genotype, diagnosis, count
        ORDER BY genotype, diagnosis
        """

        corr_results = connector.run_query(corr_query)

        if corr_results:
            df_corr = pd.DataFrame(corr_results)

            fig = px.bar(df_corr, x='genotype', y='count',
                         color='diagnosis', barmode='group',
                         title="Diagnosis Distribution by APOE Genotype")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No genetic risk data found")


def render_multimodal_connections(connector):
    """Fixed multimodal connections visualization"""
    st.subheader("Multimodal Connections")

    # Check for multimodal assessments
    query = """
    MATCH (ma:MultimodalAssessment)
    RETURN ma.cognitive_count as cognitive,
           ma.biomarker_count as biomarker,
           ma.diagnosis_count as diagnosis,
           COUNT(ma) as count
    ORDER BY count DESC
    LIMIT 20
    """

    results = connector.run_query(query)

    if results:
        df = pd.DataFrame(results)

        # Create 3D scatter plot
        fig = px.scatter_3d(df, x='cognitive', y='biomarker', z='diagnosis',
                            size='count', color='count',
                            title="Multimodal Assessment Distribution",
                            labels={'cognitive': 'Cognitive Tests',
                                    'biomarker': 'Biomarkers',
                                    'diagnosis': 'Diagnoses'})
        st.plotly_chart(fig, use_container_width=True)
    else:
        # Create multimodal assessments
        st.info("Creating multimodal assessment nodes...")

        create_query = """
        MATCH (v:Visit)
        OPTIONAL MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        OPTIONAL MATCH (v)-[:HAS_BIOMARKER]->(b:Biomarker)
        OPTIONAL MATCH (v)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WITH v, 
             COUNT(DISTINCT ca) as cog_count,
             COUNT(DISTINCT b) as bio_count,
             COUNT(DISTINCT d) as dx_count
        WHERE (cog_count + bio_count + dx_count) >= 2
        MERGE (ma:MultimodalAssessment {
            assessment_id: v.visit_id + '_multimodal',
            visit_id: v.visit_id
        })
        SET ma.cognitive_count = cog_count,
            ma.biomarker_count = bio_count,
            ma.diagnosis_count = dx_count
        MERGE (v)-[:HAS_MULTIMODAL_ASSESSMENT]->(ma)
        RETURN COUNT(ma) as created
        """

        creation_result = connector.run_query(create_query)
        if creation_result:
            st.success(f"Created {creation_result[0]['created']} multimodal assessments")
            st.rerun()


def render_clinical_progression(connector):
    """Render clinical progression patterns"""
    query = """
    MATCH (d1:Diagnosis)-[r:PROGRESSED_TO]->(d2:Diagnosis)
    WITH d1.diagnosis_code as from_dx,
         d2.diagnosis_code as to_dx,
         COUNT(r) as count
    RETURN from_dx, to_dx, count
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

        st.dataframe(df, use_container_width=True)
    else:
        st.info("No progression data found")


def render_biomarker_correlations(connector):
    """Render biomarker correlations"""
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

        # Create correlation network
        G = nx.Graph()
        for _, row in df.iterrows():
            G.add_edge(row['biomarker1'], row['biomarker2'],
                       weight=row['correlation_count'])

        pos = nx.spring_layout(G)

        edge_trace = []
        for edge in G.edges():
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_trace.append(go.Scatter(
                x=[x0, x1, None],
                y=[y0, y1, None],
                mode='lines',
                line=dict(width=G[edge[0]][edge[1]]['weight'] / 10, color='#888'),
                hoverinfo='none'
            ))

        node_trace = go.Scatter(
            x=[pos[node][0] for node in G.nodes()],
            y=[pos[node][1] for node in G.nodes()],
            mode='markers+text',
            text=list(G.nodes()),
            textposition="top center",
            marker=dict(size=15, color='#667eea'),
            hoverinfo='text'
        )

        fig = go.Figure(data=edge_trace + [node_trace],
                        layout=go.Layout(
                            title='Biomarker Correlation Network',
                            showlegend=False,
                            hovermode='closest'
                        ))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Creating biomarker correlations...")

        create_query = """
        MATCH (v:Visit)-[:HAS_BIOMARKER]->(b1:Biomarker)
        MATCH (v)-[:HAS_BIOMARKER]->(b2:Biomarker)
        WHERE id(b1) < id(b2)
        AND b1.analyte <> b2.analyte
        WITH b1, b2, v
        MERGE (b1)-[r:CORRELATES_WITH {
            same_visit: true,
            visit_id: v.visit_id
        }]->(b2)
        RETURN COUNT(r) as created
        """

        result = connector.run_query(create_query)
        if result:
            st.success(f"Created {result[0]['created']} correlations")
            st.rerun()


def render_family_relationships(connector):
    """Render family relationships"""
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

        st.dataframe(df, use_container_width=True)
    else:
        st.info("No family relationship data found")


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


def display_image_grid_fixed(images: List[Dict], context: str = ""):
    """Fixed image grid with working view buttons"""
    cols = st.columns(4)

    if not context:
        context = str(uuid.uuid4())[:8]

    for idx, img in enumerate(images[:12]):
        col_idx = idx % 4

        with cols[col_idx]:
            # Display thumbnail
            image_displayed = False

            if img.get('thumbnail_path'):
                path = Path(img['thumbnail_path'])
                if path.exists():
                    try:
                        pil_img = load_and_convert_image(path)
                        if pil_img:
                            st.image(pil_img,
                                     caption=img.get('series_description', 'Image')[:20],
                                     use_container_width=True)
                            image_displayed = True
                    except:
                        pass

            if not image_displayed and img.get('png_path'):
                path = Path(img['png_path'])
                if path.exists():
                    try:
                        pil_img = load_and_convert_image(path)
                        if pil_img:
                            pil_img.thumbnail((200, 200))
                            st.image(pil_img,
                                     caption=img.get('series_description', 'Image')[:20],
                                     use_container_width=True)
                            image_displayed = True
                    except:
                        pass

            if not image_displayed:
                st.markdown(f"""
                <div style="background: #f0f0f0; padding: 40px; 
                           border-radius: 10px; text-align: center;">
                    <p>📷</p>
                    <small>{img.get('modality', 'Image')}</small>
                </div>
                """, unsafe_allow_html=True)

            # Fixed view button
            button_key = f"view_{context}_{idx}_{str(uuid.uuid4())[:8]}"
            if st.button("View", key=button_key):
                st.session_state.selected_image = img
                st.session_state.show_image_modal = True
                st.rerun()

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


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_and_convert_image(path: Path) -> Optional[Image.Image]:
    """Load and convert image to displayable format"""
    try:
        img = Image.open(path)

        # Convert problematic modes
        if img.mode == 'I;16':
            img_array = np.array(img)
            if img_array.max() > img_array.min():
                img_array = ((img_array - img_array.min()) /
                             (img_array.max() - img_array.min()) * 255).astype(np.uint8)
            else:
                img_array = np.zeros_like(img_array, dtype=np.uint8)
            img = Image.fromarray(img_array, mode='L')
        elif img.mode == 'I':
            img = img.convert('L')

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

# Keep all original functions with their existing names
render_dashboard_overview = render_enhanced_dashboard

# ============================================================================
# MAIN APPLICATION WITH ENHANCED NAVIGATION
# ============================================================================

# Enhanced sidebar
with st.sidebar:
    st.title("🧠 ADNI Knowledge Graph")
    st.markdown("---")

    # Navigation
    page_categories = {
        "Core Analysis": ["Dashboard", "Patient Explorer", "Imaging Explorer"],
        "Biomarkers": ["Biomarker Analysis", "ATN Framework"],
        "Disease Insights": ["Disease Progression", "Cognitive Patterns"],
        "Relationships": ["Relationship Explorer", "Network Visualization"],
        "Advanced": ["Advanced Query", "Advanced Visualization"]
    }

    selected_category = st.selectbox("Category", list(page_categories.keys()))

    st.markdown("---")

    # Enhanced navigation with categories
    st.markdown("### Core Analysis")
    core_pages = [
        "Dashboard",
        "Patient Explorer",
        "Imaging Explorer"
    ]

    st.markdown("### Disease Insights")
    disease_pages = [
        "ATN Framework",
        "Disease Progression",
        "Cognitive Patterns"
    ]

    st.markdown("### Risk & Correlations")
    risk_pages = [
        "Biomarker Correlations",
        "Family Risk Network",
        "Multimodal Profiles"
    ]

    st.markdown("### Advanced")
    advanced_pages = [
        "Relationship Explorer",
        "Progression Tracking",
        "Network Visualization",
        "Biomarker Analysis",
        "Advanced Query"
    ]

    # Combined page selection
    all_pages = core_pages + disease_pages + risk_pages + advanced_pages
    selected_page = st.selectbox("Select Analysis", all_pages, label_visibility="collapsed")

    st.markdown("---")

    # Connection status
    connector = get_connector()
    es_indexer = get_es_indexer()

    if connector:
        st.success("✅ Connected to Neo4j")

        # Enhanced quick stats
        st.markdown("### Quick Stats")

        patients = connector.get_node_count("Patient")
        st.metric("Total Patients", f"{patients:,}")

        # Quick stats
        st.markdown("### Quick Stats")
        patients = connector.get_node_count("Patient")
        st.metric("Patients", f"{patients:,}")

        biomarkers = connector.get_node_count("Biomarker")
        st.metric("Biomarkers", f"{biomarkers:,}")

        images = connector.get_node_count("ImageNode")
        st.metric("Images", f"{images:,}")

        # ATN profiles
        query = "MATCH (p:Patient)-[:HAS_ATN_PROFILE]->() RETURN COUNT(DISTINCT p) as count"
        result = connector.run_query(query)
        atn_count = result[0]['count'] if result else 0
        st.metric("ATN Profiles", f"{atn_count:,}")

        # Disease stages
        query = "MATCH (p:Patient)-[:AT_STAGE]->() RETURN COUNT(DISTINCT p) as count"
        result = connector.run_query(query)
        stage_count = result[0]['count'] if result else 0
        st.metric("Staged Patients", f"{stage_count:,}")

        images = connector.get_node_count("ImageNode")
        st.metric("Medical Images", f"{images:,}")
    else:
        st.error("❌ Neo4j not connected")
        st.stop()

    if es_indexer:
        st.success("✅ Connected to Elasticsearch")
    else:
        st.warning("⚠️ Elasticsearch not connected")

# Main content area with enhanced pages
if selected_page == "Dashboard":
    render_enhanced_dashboard(connector)

elif selected_page == "ATN Framework":
    render_atn_framework_visualization(connector)

elif selected_page == "Disease Progression":
    render_disease_progression_pathways(connector)

elif selected_page == "Biomarker Correlations":
    render_fixed_biomarker_analysis(connector)

elif selected_page == "Family Risk Network":
    render_family_risk_network(connector)

elif selected_page == "Cognitive Patterns":
    render_cognitive_decline_patterns(connector)

elif selected_page == "Multimodal Profiles":
    render_multimodal_patient_profile(connector)

# Keep all original pages
elif selected_page == "Patient Explorer":
    st.title("🔍 Patient Explorer")

    # Enhanced search with filters
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        search_term = st.text_input("Search Patient ID", placeholder="e.g., 002_S_0295")

    with col2:
        diagnosis_filter = st.selectbox("Diagnosis", ["All", "CN", "MCI", "AD", "SMC", "EMCI", "LMCI"])

    with col3:
        apoe_filter = st.selectbox("APOE Status", ["All", "E4 Carrier", "Non-carrier"])

    if search_term or diagnosis_filter != "All" or apoe_filter != "All":
        # Build query with filters
        where_clauses = []

        if search_term:
            where_clauses.append(f"p.ptid CONTAINS '{search_term}'")

        if diagnosis_filter != "All":
            where_clauses.append(f"d.diagnosis_code = '{diagnosis_filter}'")

        if apoe_filter == "E4 Carrier":
            where_clauses.append("p.apoe_genotype CONTAINS 'E4'")
        elif apoe_filter == "Non-carrier":
            where_clauses.append("NOT p.apoe_genotype CONTAINS 'E4'")

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

        query = f"""
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        OPTIONAL MATCH (p)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
        WHERE {where_clause}
        RETURN DISTINCT p.ptid as id,
               p.gender as gender,
               p.age_at_baseline as age,
               p.apoe_genotype as apoe,
               d.diagnosis_code as diagnosis,
               atn.profile as atn_profile
        LIMIT 20
        """

        patients = connector.run_query(query)

        if patients:
            for patient in patients:
                with st.expander(f"Patient {patient['id']}"):
                    col1, col2, col3, col4 = st.columns(4)

                    col1.metric("Gender", patient['gender'] or 'Unknown')
                    col2.metric("Age", f"{patient['age']:.0f}" if patient['age'] else 'N/A')
                    col3.metric("APOE", patient['apoe'] or 'Unknown')

                    if patient['diagnosis']:
                        stage_class = f"stage-{patient['diagnosis'].lower()}"
                        col4.markdown(f'<div class="stage-badge {stage_class}">{patient["diagnosis"]}</div>',
                                    unsafe_allow_html=True)

                    if patient['atn_profile']:
                        st.markdown(f"**ATN Profile:** {patient['atn_profile']}")

elif selected_page == "Imaging Explorer":
    render_enhanced_imaging_explorer(connector, es_indexer)

elif selected_page == "Relationship Explorer":
    render_fixed_relationship_explorer(connector)

elif selected_page == "Progression Tracking":
    render_progression_tracking(connector)

elif selected_page == "Network Visualization":
    render_network_visualization_fixed(connector)

elif selected_page == "Biomarker Analysis":
    st.title("🧪 Biomarker Analysis")

    # Keep original biomarker analysis code
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

elif selected_page == "Advanced Visualization":
    st.title("🔧 Advanced Visualization")

    # Keep original advanced query interface
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
        "ATN Profile Distribution": """
MATCH (p:Patient)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
RETURN atn.profile as profile, 
       COUNT(p) as patients
ORDER BY patients DESC
        """,
        "High-Risk Patients": """
MATCH (p:Patient)
WHERE p.apoe_genotype CONTAINS 'E4/E4'
OPTIONAL MATCH (p)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember {has_dementia: true})
OPTIONAL MATCH (p)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
RETURN p.ptid as patient,
       p.apoe_genotype as apoe,
       COUNT(fm) as family_risk,
       atn.profile as atn
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

                    st.dataframe(df, use_container_width=True)

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

elif selected_page == "Advanced Query":
    st.title("🔧 Advanced Query Interface")

    query = st.text_area("Cypher Query", height=200)

    if st.button("Execute", type="primary"):
        if query:
            try:
                results = connector.run_query(query)
                if results:
                    df = pd.DataFrame(results)
                    st.success(f"Found {len(df)} results")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No results")
            except Exception as e:
                st.error(f"Query failed: {e}")

if st.session_state.show_image_modal:
    render_image_viewer_modal()

# Keep image viewer modal
if st.session_state.selected_image:
    st.markdown("---")
    st.subheader("Image Viewer")

    img = st.session_state.selected_image
    col1, col2 = st.columns([3, 1])

    with col1:
        if img.get('png_path'):
            path = Path(img['png_path'])
            if path.exists():
                try:
                    pil_img = load_and_convert_image(path)
                    if pil_img:
                        st.image(pil_img, caption=img.get('series_description', 'Medical Image'))
                except Exception as e:
                    st.error(f"Could not load image: {e}")
            else:
                st.warning(f"Image file not found: {path}")
        else:
            st.info("No image file path available")

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
        <p>ADNI Knowledge Graph Explorer | Enhanced Edition</p>
        <p style='font-size: 0.9em;'>Powered by Neo4j, Elasticsearch & Advanced AD Research</p>
    </div>
    """,
    unsafe_allow_html=True
)