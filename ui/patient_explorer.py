"""
Patient explorer component
"""

import streamlit as st
from .components import render_stage_badge


def render_patient_explorer(connector):
    """Render patient explorer interface"""
    st.title("🔍 Patient Explorer")

    # Enhanced search with filters
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        search_term = st.text_input("Search Patient ID", placeholder="e.g., 002_S_0295")

    with col2:
        diagnosis_filter = st.selectbox("Diagnosis", ["All", "CN", "MCI", "AD", "SMC", "EMCI", "LMCI"])

    with col3:
        apoe_filter = st.selectbox("APOE Status", ["All", "E4 Carrier", "Non-carrier"])

    if search_term or diagnosis_filter != "All" or apoe_filter != "All":
        render_patient_search_results(connector, search_term, diagnosis_filter, apoe_filter)


def render_patient_search_results(connector, search_term, diagnosis_filter, apoe_filter):
    """Render patient search results"""
    # Build query with filters
    where_clauses = []

    if search_term:
        where_clauses.append(f"p.ptid CONTAINS '{search_term}'")

    if diagnosis_filter != "All":
        where_clauses.append(f"d.diagnosis_code = '{diagnosis_filter}'")

    if apoe_filter == "E4 Carrier":
        where_clauses.append("p.apoe_genotype CONTAINS 'E4'")
    elif apoe_filter == "Non-carrier":
        where_clauses.append("NOT p.apoe_genotype CONTAINS 'E4'")

    where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

    query = f"""
    MATCH (p:Patient)
    OPTIONAL MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
    OPTIONAL MATCH (p)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
    WHERE {where_clause}
    RETURN DISTINCT p.ptid as id,
           p.gender as gender,
           p.age_at_baseline as age,
           p.apoe_genotype as apoe,
           d.diagnosis_code as diagnosis,
           atn.profile as atn_profile
    LIMIT 20
    """

    patients = connector.run_query(query)

    if patients:
        for patient in patients:
            render_patient_card(patient)
    else:
        st.info("No patients found matching the search criteria")


def render_patient_card(patient):
    """Render individual patient card"""
    with st.expander(f"Patient {patient['id']}"):
        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Gender", patient['gender'] or 'Unknown')
        col2.metric("Age", f"{patient['age']:.0f}" if patient['age'] else 'N/A')
        col3.metric("APOE", patient['apoe'] or 'Unknown')

        if patient['diagnosis']:
            col4.markdown(render_stage_badge(patient['diagnosis']), unsafe_allow_html=True)

        if patient['atn_profile']:
            st.markdown(f"**ATN Profile:** {patient['atn_profile']}")

        # Action buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("View Timeline", key=f"timeline_{patient['id']}"):
                st.session_state.selected_patient = patient['id']
                st.session_state.view_mode = 'timeline'

        with col2:
            if st.button("View Images", key=f"images_{patient['id']}"):
                st.session_state.selected_patient = patient['id']
                st.session_state.view_mode = 'images'

        with col3:
            if st.button("View Network", key=f"network_{patient['id']}"):
                st.session_state.selected_patient = patient['id']
                st.session_state.view_mode = 'network'