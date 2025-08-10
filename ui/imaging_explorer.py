# File: ui/imaging_explorer.py
"""
Medical imaging explorer component
"""

import streamlit as st
from pathlib import Path
import logging
from typing import List, Dict
from .components import display_image_grid, load_and_convert_image

logger = logging.getLogger(__name__)


def render_imaging_explorer(connector, es_indexer=None):
    """Enhanced imaging explorer with Elasticsearch/Neo4j fallback"""
    st.title("🏥 Medical Imaging Explorer")

    # Check data sources
    data_sources = []
    if es_indexer and es_indexer.es and es_indexer.es.ping():
        data_sources.append("Elasticsearch")
    if connector:
        data_sources.append("Neo4j")

    if not data_sources:
        st.error("No data sources available for imaging data")
        return

    st.info(f"Using data sources: {', '.join(data_sources)}")

    # Statistics
    render_imaging_statistics(connector, es_indexer, data_sources)

    st.markdown("---")

    # Image Browser Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["Search Images", "Browse by Patient",
                                      "Browse by Study", "Image Analysis"])

    with tab1:
        render_image_search(connector, es_indexer, data_sources)

    with tab2:
        render_browse_by_patient(connector, es_indexer, data_sources)

    with tab3:
        render_browse_by_study(connector, es_indexer, data_sources)

    with tab4:
        render_image_analysis(connector)


def render_imaging_statistics(connector, es_indexer, data_sources):
    """Render imaging statistics"""
    col1, col2, col3, col4 = st.columns(4)

    # Get counts from available source
    if "Elasticsearch" in data_sources:
        try:
            stats = es_indexer.get_index_stats()
            total_images = stats.get('total_images', 0)
        except:
            total_images = connector.get_node_count("ImageNode") if "Neo4j" in data_sources else 0
    else:
        total_images = connector.get_node_count("ImageNode") if "Neo4j" in data_sources else 0

    col1.metric("Total Images", f"{total_images:,}")

    # Get modality counts from Neo4j
    if "Neo4j" in data_sources:
        query = "MATCH (i:ImageNode {modality: 'MRI'}) RETURN count(i) as count"
        mri_count = connector.run_query(query)
        col2.metric("MRI Scans", mri_count[0]['count'] if mri_count else 0)

        query = "MATCH (i:ImageNode {modality: 'PET'}) RETURN count(i) as count"
        pet_count = connector.run_query(query)
        col3.metric("PET Scans", pet_count[0]['count'] if pet_count else 0)

        query = "MATCH (p:Patient)-[:HAS_IMAGE]->() RETURN count(DISTINCT p) as count"
        img_patients = connector.run_query(query)
        col4.metric("Patients with Imaging", img_patients[0]['count'] if img_patients else 0)


def render_image_search(connector, es_indexer, data_sources):
    """Render image search interface"""
    st.subheader("Search Medical Images")

    # Search interface
    col1, col2 = st.columns([3, 1])
    with col1:
        search_query = st.text_input("Search (Patient ID, Description, etc.)",
                                     placeholder="e.g., 002_S_0295 or T1 or MRI")
    with col2:
        modality_filter = st.selectbox("Modality", ["All", "MRI", "PET", "CT"])

    if st.button("Search", type="primary"):
        images = search_images_with_fallback(search_query, modality_filter,
                                             es_indexer, connector, data_sources)

        if images:
            st.success(f"Found {len(images)} images")
            display_search_results(images)
        else:
            st.info("No images found matching your search")


def render_browse_by_patient(connector, es_indexer, data_sources):
    """Render browse by patient interface"""
    patient_id = st.text_input("Enter Patient ID", placeholder="e.g., 002_S_0295")

    if patient_id:
        images = get_patient_images_with_fallback(patient_id, es_indexer,
                                                  connector, data_sources)

        if images:
            st.subheader(f"Images for Patient {patient_id} ({len(images)} found)")

            # Group by modality
            mri_images = [img for img in images if img.get('modality') == 'MRI']
            pet_images = [img for img in images if img.get('modality') == 'PET']

            if mri_images:
                st.markdown("#### MRI Images")
                display_image_grid(mri_images, context=f"patient_{patient_id}_mri")

            if pet_images:
                st.markdown("#### PET Images")
                display_image_grid(pet_images, context=f"patient_{patient_id}_pet")
        else:
            st.info(f"No images found for patient {patient_id}")


def render_browse_by_study(connector, es_indexer, data_sources):
    """Render browse by study date interface"""
    st.subheader("Browse Images by Study Date")

    if "Neo4j" in data_sources:
        # Get available study dates
        query = """
        MATCH (i:ImageNode)
        WHERE i.study_date IS NOT NULL
        RETURN DISTINCT i.study_date as date
        ORDER BY date DESC
        LIMIT 30
        """

        dates = connector.run_query(query)

        if dates:
            selected_date = st.selectbox("Select Study Date",
                                         [d['date'] for d in dates])

            if selected_date:
                images = get_images_by_date_with_fallback(selected_date,
                                                          es_indexer, connector, data_sources)

                if images:
                    st.info(f"Found {len(images)} images from {selected_date}")
                    display_search_results(images)


def render_image_analysis(connector):
    """Render image analysis section"""
    st.subheader("Image Analysis and Correlations")

    # Check for volumetric measures
    query = """
    MATCH (v:VolumetricMeasure)
    RETURN v.region as region,
           AVG(v.volume) as avg_volume,
           MIN(v.volume) as min_volume,
           MAX(v.volume) as max_volume,
           COUNT(v) as count
    ORDER BY count DESC
    LIMIT 10
    """

    volumes = connector.run_query(query)

    if volumes:
        import plotly.graph_objects as go
        import pandas as pd

        df = pd.DataFrame(volumes)

        fig = go.Figure()
        for _, row in df.iterrows():
            fig.add_trace(go.Box(
                y=[row['min_volume'], row['avg_volume'], row['max_volume']],
                name=row['region'],
                boxmean=True
            ))

        fig.update_layout(title="Brain Region Volumes",
                          yaxis_title="Volume (mm³)")
        st.plotly_chart(fig, use_container_width=True)

        # Volume statistics
        st.subheader("Volume Statistics by Region")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No volumetric data available")


# Helper functions for image search
def search_images_with_fallback(query: str, modality: str, es_indexer, connector, data_sources) -> List[Dict]:
    """Search images with fallback between Elasticsearch and Neo4j"""
    images = []

    # Try Elasticsearch first if available
    if "Elasticsearch" in data_sources and es_indexer:
        try:
            filters = {}
            if modality != "All":
                filters["modality"] = modality

            results = es_indexer.search_images(query, filters=filters, size=100)
            images = [hit["source"] for hit in results["hits"]]

            if images:
                logger.info(f"Retrieved {len(images)} images from Elasticsearch")
                return images
        except Exception as e:
            logger.warning(f"Elasticsearch search failed: {e}, falling back to Neo4j")

    # Fallback to Neo4j
    if "Neo4j" in data_sources and connector:
        try:
            where_clauses = []
            if query:
                where_clauses.append(f"(i.patient_id CONTAINS '{query}' OR i.series_description CONTAINS '{query}')")
            if modality != "All":
                where_clauses.append(f"i.modality = '{modality}'")

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            neo4j_query = f"""
            MATCH (i:ImageNode)
            WHERE {where_clause}
            RETURN i.image_id as image_id,
                   i.patient_id as patient_id,
                   i.modality as modality,
                   i.series_description as series_description,
                   i.study_date as study_date,
                   i.png_path as png_path,
                   i.thumbnail_path as thumbnail_path,
                   i.dcm_path as dcm_path
            LIMIT 100
            """

            images = connector.run_query(neo4j_query)
            logger.info(f"Retrieved {len(images)} images from Neo4j")
        except Exception as e:
            logger.error(f"Neo4j search failed: {e}")

    return images


def get_patient_images_with_fallback(patient_id: str, es_indexer, connector, data_sources) -> List[Dict]:
    """Get patient images with fallback"""
    images = []

    if "Elasticsearch" in data_sources and es_indexer:
        try:
            images = es_indexer.get_patient_images(patient_id)
            if images:
                return images
        except Exception as e:
            logger.warning(f"Elasticsearch failed: {e}")

    if "Neo4j" in data_sources and connector:
        try:
            query = """
            MATCH (p:Patient {ptid: $patient_id})-[:HAS_IMAGE]->(i:ImageNode)
            RETURN i.image_id as image_id,
                   i.patient_id as patient_id,
                   i.modality as modality,
                   i.series_description as series_description,
                   i.study_date as study_date,
                   i.png_path as png_path,
                   i.thumbnail_path as thumbnail_path,
                   i.dcm_path as dcm_path
            ORDER BY i.study_date DESC, i.modality
            """

            images = connector.run_query(query, {'patient_id': patient_id})
        except Exception as e:
            logger.error(f"Neo4j query failed: {e}")

    return images


def get_images_by_date_with_fallback(study_date: str, es_indexer, connector, data_sources) -> List[Dict]:
    """Get images by date with fallback"""
    images = []

    if "Elasticsearch" in data_sources and es_indexer:
        try:
            filters = {"study_date": study_date}
            results = es_indexer.search_images("", filters=filters, size=200)
            images = [hit["source"] for hit in results["hits"]]
            if images:
                return images
        except Exception as e:
            logger.warning(f"Elasticsearch failed: {e}")

    if "Neo4j" in data_sources and connector:
        try:
            query = """
            MATCH (i:ImageNode {study_date: $date})
            RETURN i.image_id as image_id,
                   i.patient_id as patient_id,
                   i.modality as modality,
                   i.series_description as series_description,
                   i.png_path as png_path,
                   i.thumbnail_path as thumbnail_path
            LIMIT 200
            """

            images = connector.run_query(query, {'date': study_date})
        except Exception as e:
            logger.error(f"Neo4j query failed: {e}")

    return images


def display_search_results(images: List[Dict]):
    """Display image search results"""
    # Group by patient
    patients = {}
    for img in images:
        pid = img.get('patient_id', 'unknown')
        if pid not in patients:
            patients[pid] = []
        patients[pid].append(img)

    # Display first 10 patients
    for idx, (pid, patient_images) in enumerate(list(patients.items())[:10]):
        with st.expander(f"Patient {pid} ({len(patient_images)} images)"):
            display_image_grid(patient_images[:12], context=f"search_patient_{pid}_{idx}")