# File: ui/family_risk.py
"""
Family risk network component
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_family_risk_network(connector):
    """Render family history and genetic risk network"""
    st.title("👨‍👩‍👧‍👦 Family History & Genetic Risk Network")

    col1, col2 = st.columns([2, 1])

    with col1:
        render_family_risk_statistics(connector)

    with col2:
        render_family_risk_categories(connector)

    # Combined genetic and family risk
    render_combined_risk_analysis(connector)


def render_family_risk_statistics(connector):
    """Render family risk statistics"""
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


def render_family_risk_categories(connector):
    """Render family risk categories"""
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


def render_combined_risk_analysis(connector):
    """Render combined genetic and family risk analysis"""
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