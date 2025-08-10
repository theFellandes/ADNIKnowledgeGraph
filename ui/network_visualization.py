# File: ui/network_visualization.py
"""
Network visualization component
"""

import streamlit as st
import networkx as nx
import plotly.graph_objects as go


def render_network_visualization(connector):
    """Fixed network visualization with proper path handling"""
    st.title("🕸️ Network Visualization")

    # Network depth control
    depth = st.slider("Relationship Depth", 1, 4, 2)

    patient_id = st.text_input("Enter Patient ID for Network",
                               placeholder="e.g., 002_S_0295",
                               key="network_patient_id")

    if patient_id:
        with st.spinner("Building network..."):
            render_patient_network(connector, patient_id, depth)


def render_patient_network(connector, patient_id, depth):
    """Render patient network"""
    # Get relationships
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

    if rel_results:
        # Build network graph
        G = nx.Graph()

        # Add center node
        G.add_node(patient_id, type='Patient', label=patient_id)

        # Add edges
        for rel in rel_results:
            if rel:
                start_node = f"{rel.get('start_type', 'Unknown')}_{rel.get('start_id', '')}"[:20]
                end_node = f"{rel.get('end_type', 'Unknown')}_{rel.get('end_id', '')}"[:20]

                if start_node not in G:
                    G.add_node(start_node, type=rel.get('start_type', 'Unknown'))
                if end_node not in G:
                    G.add_node(end_node, type=rel.get('end_type', 'Unknown'))

                G.add_edge(start_node, end_node, type=rel.get('rel_type', 'RELATED'))

        # Create visualization
        if G.number_of_nodes() > 0:
            render_network_plot(G, patient_id, depth)
            render_network_statistics(G)
    else:
        st.warning(f"No network data found for patient {patient_id}")


def render_network_plot(G, patient_id, depth):
    """Render network plot"""
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


def render_network_statistics(G):
    """Render network statistics"""
    col1, col2, col3 = st.columns(3)
    col1.metric("Nodes", G.number_of_nodes())
    col2.metric("Edges", G.number_of_edges())
    if G.number_of_nodes() > 0:
        col3.metric("Density", f"{nx.density(G):.3f}")
