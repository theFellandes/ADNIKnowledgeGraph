# File: ui/multimodal_profiles.py
"""
Multimodal patient profiles component
"""

import streamlit as st
import plotly.graph_objects as go
from .components import render_stage_badge, render_atn_status


def render_multimodal_profiles(connector):
    """Render comprehensive multimodal patient profiles"""
    st.title("🔬 Multimodal Patient Profiles")

    patient_id = st.text_input("Patient ID for Multimodal Analysis",
                               placeholder="e.g., 002_S_0295")

    if patient_id:
        render_patient_profile(connector, patient_id)
        render_multimodal_timeline(connector, patient_id)


def render_patient_profile(connector, patient_id):
    """Render comprehensive patient profile"""
    col1, col2, col3 = st.columns(3)

    # Basic demographics
    with col1:
        render_demographics(connector, patient_id)

    # Current diagnosis
    with col2:
        render_current_diagnosis(connector, patient_id)

    # ATN Profile
    with col3:
        render_patient_atn_profile(connector, patient_id)


def render_demographics(connector, patient_id):
    """Render patient demographics"""
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


def render_current_diagnosis(connector, patient_id):
    """Render current diagnosis"""
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

        st.markdown(render_stage_badge(diagnosis), unsafe_allow_html=True)
        st.write(f"**Confidence:** {confidence * 100:.0f}%")


def render_patient_atn_profile(connector, patient_id):
    """Render patient's ATN profile"""
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
            {render_atn_status(profile['A'])}
            {render_atn_status(profile['T'])}
            {render_atn_status(profile['N'])}
        </div>
        """, unsafe_allow_html=True)


def render_multimodal_timeline(connector, patient_id):
    """Render multimodal data timeline"""
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
        import pandas as pd
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
