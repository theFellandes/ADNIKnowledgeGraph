"""
Dashboard component for ADNI Knowledge Graph UI
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from .components import render_metric_cards


def render_dashboard(connector):
    """Enhanced dashboard with new visualizations"""
    st.title("🧠 ADNI Knowledge Graph Dashboard")

    # Enhanced metrics with gradients
    metrics = {}

    # Get patient count
    patient_count = connector.get_node_count("Patient")
    metrics["Patients"] = (f"{patient_count:,}", "Total Patients")

    # Get patients with ATN profiles
    query = "MATCH (p:Patient)-[:HAS_ATN_PROFILE]->() RETURN COUNT(DISTINCT p) as count"
    result = connector.run_query(query)
    atn_count = result[0]['count'] if result else 0
    metrics["ATN Profiles"] = (f"{atn_count:,}", "ATN Profiles")

    # Get biomarker count
    biomarker_count = connector.get_node_count("Biomarker")
    metrics["Biomarkers"] = (f"{biomarker_count:,}", "Biomarkers")

    # Get progression events
    query = "MATCH ()-[r:PROGRESSED_TO]->() RETURN COUNT(r) as count"
    result = connector.run_query(query)
    prog_count = result[0]['count'] if result else 0
    metrics["Progressions"] = (f"{prog_count:,}", "Progressions")

    render_metric_cards(metrics)

    # Disease stage distribution
    st.markdown("### 📊 Disease Stage Distribution")

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