# File: ui/advanced_query.py
"""
Advanced query interface component
"""

import streamlit as st
import pandas as pd
from datetime import datetime


def render_advanced_query(connector):
    """Advanced query interface"""
    st.title("🔧 Advanced Query Interface")

    # Query templates
    templates = get_query_templates()

    selected_template = st.selectbox("Select Query Template", list(templates.keys()))

    query = st.text_area("Cypher Query",
                         value=templates[selected_template],
                         height=200)

    if st.button("Execute Query", type="primary"):
        execute_query(connector, query)


def get_query_templates():
    """Get query templates"""
    return {
        "Custom Query": "",
        "Find Converters (CN→AD)": """
MATCH (p:Patient)-[:HAS_VISIT]->(v1:Visit)-[:HAS_DIAGNOSIS]->(d1:Diagnosis {diagnosis_code: 'CN'})
MATCH (p)-[:HAS_VISIT]->(v2:Visit)-[:HAS_DIAGNOSIS]->(d2:Diagnosis {diagnosis_code: 'AD'})
WHERE v2.months_from_baseline > v1.months_from_baseline
RETURN p.ptid as patient, 
       v2.months_from_baseline - v1.months_from_baseline as months_to_conversion
ORDER BY months_to_conversion
LIMIT 25
        """,
        "ATN Profile Distribution": """
MATCH (p:Patient)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
RETURN atn.profile as profile, 
       COUNT(p) as patients
ORDER BY patients DESC
        """,
        "High-Risk Patients": """
MATCH (p:Patient)
WHERE p.apoe_genotype CONTAINS 'E4/E4'
OPTIONAL MATCH (p)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember {has_dementia: true})
OPTIONAL MATCH (p)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
RETURN p.ptid as patient,
       p.apoe_genotype as apoe,
       COUNT(fm) as family_risk,
       atn.profile as atn
LIMIT 25
        """
    }


def execute_query(connector, query):
    """Execute query and display results"""
    if query:
        try:
            with st.spinner("Executing query..."):
                results = connector.run_query(query)

            if results:
                df = pd.DataFrame(results)
                st.success(f"Found {len(df)} results")

                st.dataframe(df, use_container_width=True)

                # Download button
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download as CSV",
                    data=csv,
                    file_name=f"query_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("Query returned no results")

        except Exception as e:
            st.error(f"Query execution failed: {e}")