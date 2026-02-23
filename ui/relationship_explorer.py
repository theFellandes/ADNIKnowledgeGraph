# File: ui/relationship_explorer.py
"""
Relationship explorer component
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go


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


def render_temporal_sequences(connector):
    """Render temporal sequence visualization"""
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


def render_genetic_risk_relationships(connector):
    """Render genetic risk visualization"""
    st.subheader("Genetic Risk Relationships")

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

        import plotly.express as px
        fig = px.sunburst(df, path=['risk_level', 'genotype'],
                          values='count',
                          title="APOE Genetic Risk Distribution",
                          color_discrete_sequence=px.colors.sequential.RdBu_r)
        st.plotly_chart(fig, use_container_width=True)


def render_multimodal_connections(connector):
    """Render multimodal connections visualization"""
    st.subheader("Multimodal Connections")

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

        import plotly.express as px
        fig = px.scatter_3d(df, x='cognitive', y='biomarker', z='diagnosis',
                            size='count', color='count',
                            title="Multimodal Assessment Distribution",
                            labels={'cognitive': 'Cognitive Tests',
                                    'biomarker': 'Biomarkers',
                                    'diagnosis': 'Diagnoses'})
        st.plotly_chart(fig, use_container_width=True)


def render_biomarker_correlations(connector):
    """Render biomarker correlations"""
    # Implementation already in biomarker_correlations.py
    pass


def render_family_relationships(connector):
    """Render family relationships"""
    # Implementation already in family_risk.py
    pass
