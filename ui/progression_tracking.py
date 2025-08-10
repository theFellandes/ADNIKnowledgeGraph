# File: ui/progression_tracking.py
"""
Disease progression tracking component
"""

import streamlit as st
import pandas as pd
from plotly.subplots import make_subplots
import plotly.graph_objects as go


def render_progression_tracking(connector):
    """Disease progression tracking"""
    st.title("📊 Disease Progression Tracking")

    # Individual progression paths
    st.subheader("Patient Progression Paths")

    patient_id = st.text_input("Enter Patient ID for Progression Analysis",
                               key="prog_patient_id")

    if patient_id:
        render_patient_progression(connector, patient_id)


def render_patient_progression(connector, patient_id):
    """Render patient progression"""
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