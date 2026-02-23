# File: ui/biomarker_correlations.py
"""
Biomarker correlations component
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go


def render_biomarker_correlations(connector):
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
        render_correlation_matrix(correlations)
        render_biomarker_trajectories(connector)
    else:
        st.info("No biomarker correlation data available")


def render_correlation_matrix(correlations):
    """Render correlation matrix"""
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


def render_biomarker_trajectories(connector):
    """Render biomarker trajectories by diagnosis"""
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
        from plotly.subplots import make_subplots

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
                        row=1, col=idx + 1
                    )

        fig.update_xaxes(title_text="Months from Baseline")
        fig.update_layout(height=400, title="Biomarker Trajectories by Diagnosis Group")
        st.plotly_chart(fig, use_container_width=True)