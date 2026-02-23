# File: ui/cognitive_patterns.py
"""
Cognitive decline patterns component
"""

import streamlit as st
import pandas as pd
import plotly.express as px


def render_cognitive_patterns(connector):
    """Render cognitive decline pattern analysis"""
    st.title("🧠 Cognitive Decline Patterns")

    # Get cognitive trajectories
    query = """
    MATCH (p:Patient)-[:HAS_COGNITIVE_TRAJECTORY]->(traj:CognitiveTrajectory)
    WHERE traj.trajectory_type IN ['declining', 'stable', 'improving']
    RETURN traj.test_name as test,
           traj.trajectory_type as trajectory,
           COUNT(p) as patients,
           AVG(traj.change_rate) as avg_change_rate
    ORDER BY test, trajectory
    """

    trajectories = connector.run_query(query)

    if trajectories:
        render_trajectory_distribution(trajectories)
        render_decline_rates(trajectories)
    else:
        # Fallback: Calculate trajectories from raw data
        compute_and_render_trajectories(connector)


def render_trajectory_distribution(trajectories):
    """Render trajectory distribution"""
    df = pd.DataFrame(trajectories)

    # Create grouped bar chart
    fig = px.bar(df, x='test', y='patients', color='trajectory',
                 title="Cognitive Trajectory Distribution by Test",
                 color_discrete_map={
                     'declining': '#fa709a',
                     'stable': '#4facfe',
                     'improving': '#43e97b'
                 })
    st.plotly_chart(fig, use_container_width=True)


def render_decline_rates(trajectories):
    """Render decline rates"""
    st.subheader("Average Decline Rates")

    df = pd.DataFrame(trajectories)
    declining = df[df['trajectory'] == 'declining']

    if not declining.empty:
        cols = st.columns(len(declining))

        for idx, (_, row) in enumerate(declining.iterrows()):
            with cols[idx]:
                st.metric(
                    row['test'],
                    f"{abs(row['avg_change_rate']):.3f} points/month",
                    f"{row['patients']} patients"
                )


def compute_and_render_trajectories(connector):
    """Compute trajectories from raw data"""
    st.info("Computing cognitive trajectories from assessment data...")

    # Get cognitive assessment changes over time
    query = """
    MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
    WITH p, ca.test_name as test, 
         v.months_from_baseline as months,
         ca.total_score as score
    ORDER BY p.ptid, test, months
    WITH p.ptid as patient_id, test,
         COLLECT({months: months, score: score}) as scores
    WHERE SIZE(scores) >= 2
    WITH test, patient_id, scores,
         scores[0].score as first_score,
         scores[-1].score as last_score,
         scores[-1].months - scores[0].months as duration
    WHERE duration > 0
    WITH test, patient_id,
         CASE 
             WHEN test = 'MMSE' THEN
                 CASE 
                     WHEN (first_score - last_score) > 3 THEN 'declining'
                     WHEN (first_score - last_score) < -2 THEN 'improving'
                     ELSE 'stable'
                 END
             ELSE 'stable'
         END as trajectory,
         (first_score - last_score) / duration as change_rate
    RETURN test, trajectory, 
           COUNT(DISTINCT patient_id) as patients,
           AVG(change_rate) as avg_change_rate
    ORDER BY test, trajectory
    """

    trajectories = connector.run_query(query)

    if trajectories:
        render_trajectory_distribution(trajectories)
        render_trajectory_statistics(trajectories)
    else:
        st.warning("No cognitive assessment data available to compute trajectories")


def render_trajectory_statistics(trajectories):
    """Render trajectory statistics"""
    st.subheader("Trajectory Statistics")

    df = pd.DataFrame(trajectories)
    col1, col2, col3 = st.columns(3)

    total_patients = df['patients'].sum()
    if total_patients > 0:
        declining_patients = df[df['trajectory'] == 'declining']['patients'].sum()
        stable_patients = df[df['trajectory'] == 'stable']['patients'].sum()
        improving_patients = df[df['trajectory'] == 'improving']['patients'].sum()

        col1.metric("Declining", f"{declining_patients} patients",
                    f"{declining_patients / total_patients * 100:.1f}%")
        col2.metric("Stable", f"{stable_patients} patients",
                    f"{stable_patients / total_patients * 100:.1f}%")
        col3.metric("Improving", f"{improving_patients} patients",
                    f"{improving_patients / total_patients * 100:.1f}%")