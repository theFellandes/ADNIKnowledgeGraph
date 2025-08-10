"""
Disease progression pathways component
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def render_disease_progression(connector):
    """Render comprehensive disease progression pathways"""
    st.title("📈 Disease Progression Pathways")

    # Create tabs with dark mode support
    tab1, tab2, tab3, tab4 = st.tabs(["Progression Patterns", "Individual Trajectories",
                                      "Risk Factors", "Survival Analysis"])

    with tab1:
        render_progression_patterns(connector)

    with tab2:
        render_individual_trajectories(connector)

    with tab3:
        render_risk_factors(connector)

    with tab4:
        render_survival_analysis(connector)


def render_progression_patterns(connector):
    """Render progression patterns"""
    st.subheader("Common Progression Patterns")

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

        # Statistics
        render_progression_statistics(df)


def render_progression_statistics(df):
    """Render progression statistics"""
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


def render_individual_trajectories(connector):
    """Render individual patient trajectories"""
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
            render_patient_trajectory_plot(trajectory, patient_id)
        else:
            st.info(f"No trajectory data found for patient {patient_id}")


def render_patient_trajectory_plot(trajectory, patient_id):
    """Render patient trajectory plot"""
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


def render_risk_factors(connector):
    """Render risk factor analysis"""
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
            render_combined_risk_factors(connector)


def render_combined_risk_factors(connector):
    """Render combined risk factors"""
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


def render_survival_analysis(connector):
    """Render survival analysis"""
    st.subheader("Survival Analysis")
    st.info("Survival analysis implementation - tracking time to progression events")

    # Placeholder for survival curves
    # This would include Kaplan-Meier curves and Cox regression results
