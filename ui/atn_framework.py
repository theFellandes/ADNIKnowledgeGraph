"""
ATN Framework visualization component
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from .components import render_atn_status, render_risk_indicator


def render_atn_framework(connector):
    """Render ATN (Amyloid-Tau-Neurodegeneration) framework visualization"""
    st.title("🧬 ATN Framework Analysis")
    st.markdown("""
    The ATN framework is a biological classification system for Alzheimer's disease based on:
    - **A**: Amyloid β deposition (Aβ42)
    - **T**: Tau pathology (p-Tau181)
    - **N**: Neurodegeneration (Total Tau, FDG-PET, MRI atrophy)
    """)

    # Check for ATN profiles
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

    # If no ATN profiles exist, compute from biomarkers
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

            # Bar chart
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
                # Determine risk level
                risk_level = "high" if 'A+' in profile['A'] and 'T+' in profile['T'] else "moderate" if 'A+' in profile[
                    'A'] else "low"

                st.markdown(f"""
                <div class="atn-profile">
                    <h4>{profile['profile']}</h4>
                    {render_atn_status(profile['A'])}
                    {render_atn_status(profile['T'])}
                    {render_atn_status(profile['N'])}
                    <p style="margin-top: 10px;">Patients: <strong>{profile['count']}</strong></p>
                    {render_risk_indicator(risk_level)}
                </div>
                """, unsafe_allow_html=True)
    else:
        st.warning("No biomarker data available to compute ATN profiles")

    # ATN correlation with diagnosis
    render_atn_diagnosis_correlation(connector)


def render_atn_diagnosis_correlation(connector):
    """Render ATN correlation with diagnosis"""
    st.subheader("ATN Profiles and Clinical Diagnosis")

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

        # Create pivot table
        if not df_corr.empty:
            pivot = df_corr.pivot_table(index='atn_profile', columns='diagnosis',
                                        values='count', fill_value=0)

            fig = px.imshow(pivot,
                            labels=dict(x="Clinical Diagnosis", y="ATN Profile", color="Count"),
                            title="ATN Profile vs Clinical Diagnosis Correlation",
                            color_continuous_scale='Viridis')
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Insufficient data to show ATN-diagnosis correlations")