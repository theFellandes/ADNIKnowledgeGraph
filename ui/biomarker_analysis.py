# File: ui/biomarker_analysis.py
"""
Biomarker analysis component
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_biomarker_analysis(connector):
    """Comprehensive biomarker analysis"""
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
            render_biomarker_overview(connector)

        with tabs[1]:
            render_csf_biomarkers(connector)

        with tabs[2]:
            render_genetic_markers(connector)

        with tabs[3]:
            render_atn_profiles(connector)

        with tabs[4]:
            render_biomarker_correlations_tab(connector)
    else:
        st.warning("No biomarker data found in the database")


def render_biomarker_overview(connector):
    """Render biomarker overview"""
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


def render_csf_biomarkers(connector):
    """Render CSF biomarker analysis"""
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
        render_csf_abnormality_rates(connector)


def render_csf_abnormality_rates(connector):
    """Render CSF abnormality rates"""
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


def render_genetic_markers(connector):
    """Render genetic markers analysis"""
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
    else:
        st.info("No genetic marker data available")


def render_atn_profiles(connector):
    """Render ATN profile analysis"""
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
    else:
        st.info("No ATN profile data available")


def render_biomarker_correlations_tab(connector):
    """Render biomarker correlations tab"""
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
        render_correlation_network(corr_results)
    else:
        st.info("No biomarker correlations found")


def render_correlation_network(corr_results):
    """Render biomarker correlation network"""
    import networkx as nx

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