# File: ui/imaging_explorer.py
"""
Enhanced Medical Imaging Explorer with Smooth Rendering Support
Supports multiple lossless formats including pyramid TIFF and web viewer
"""

import streamlit as st
from pathlib import Path
import logging
from typing import List, Dict, Optional, Tuple
import json
import base64
from PIL import Image
import tifffile
import numpy as np
import plotly.graph_objects as go
import pandas as pd

# Set up logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def test_image_paths(connector):
    """Test function to verify image paths in Neo4j"""
    st.subheader("🔧 Image Path Testing")
    
    # Get a sample image
    query = """
    MATCH (i:ImageNode)
    RETURN i.image_hash as hash,
           i.patient_id as patient,
           i.lossless_png_path as png,
           i.thumbnail_path as thumb,
           i.smooth_tiff_path as smooth,
           i.pyramid_tiff_path as pyramid,
           i.viewer_html_path as viewer
    LIMIT 5
    """
    
    results = connector.run_query(query)
    
    if results:
        st.write(f"Found {len(results)} test images")
        
        for idx, img in enumerate(results):
            with st.expander(f"Test Image {idx + 1} - Patient: {img['patient']}"):
                st.json(img)
                
                # Test each path
                paths_to_test = [
                    ('PNG', img.get('png')),
                    ('Thumbnail', img.get('thumb')),
                    ('Smooth TIFF', img.get('smooth')),
                    ('Pyramid TIFF', img.get('pyramid')),
                    ('Web Viewer', img.get('viewer'))
                ]
                
                for name, path in paths_to_test:
                    if path:
                        if Path(path).exists():
                            st.success(f"[OK] {name}: {path} EXISTS")
                        else:
                            st.error(f"[X] {name}: {path} NOT FOUND")
                    else:
                        st.warning(f"[!] {name}: No path stored")
    else:
        st.error("No images found in database")


# Add test mode to the main explorer
def render_imaging_explorer(connector, es_indexer=None):
    """Enhanced imaging explorer with multiple format support"""
    st.title("Medical Imaging Explorer - Enhanced Edition")
    
    # Initialize session state for buttons if not exists
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
        # Pre-initialize common session state keys to prevent KeyErrors
        for i in range(100):  # Pre-initialize for up to 100 images
            for action in ['web', 'pyramid', 'full', 'download']:
                st.session_state[f'show_{action}_{i}'] = False

    # Check data sources
    data_sources = []
    if es_indexer and es_indexer.es and es_indexer.es.ping():
        data_sources.append("Elasticsearch")
    if connector:
        data_sources.append("Neo4j")

    if not data_sources:
        st.error("No data sources available for imaging data")
        return

    # Display available features
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.info(f"Data sources: {', '.join(data_sources)}")
    with col2:
        if st.button("Format Guide", key="format_guide"):
            show_format_guide()
    with col3:
        test_mode = st.checkbox("Test Mode", key="test_mode")

    # Show test interface if enabled
    if test_mode:
        test_image_paths(connector)
        st.markdown("---")

    # Statistics
    render_imaging_statistics(connector, es_indexer, data_sources)

    st.markdown("---")

    # Enhanced Image Browser Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Search Images", 
        "Browse by Patient",
        "Browse by Study", 
        "Image Analysis",
        "Advanced Viewer"
    ])

    with tab1:
        render_image_search(connector, es_indexer, data_sources)

    with tab2:
        render_browse_by_patient(connector, es_indexer, data_sources)

    with tab3:
        render_browse_by_study(connector, es_indexer, data_sources)

    with tab4:
        render_image_analysis(connector)
    
    with tab5:
        render_advanced_viewer(connector, es_indexer, data_sources)


def show_format_guide():
    """Show guide for different image formats"""
    with st.expander("Image Format Guide", expanded=True):
        st.markdown("""
        ### Available Image Formats
        
        | Format | Description | Best For |
        |--------|-------------|----------|
        | **PNG (16-bit)** | Lossless compression, original quality | Analysis & processing |
        | **TIFF** | Standard lossless format | Professional software |
        | **Smooth TIFF** | With interpolation instructions | Smooth zooming |
        | **Pyramid TIFF** | Multi-resolution levels | Fast zoom at any level |
        | **Web Viewer** | Interactive HTML5 viewer | Browser-based viewing |
        | **Thumbnail** | 256x256 JPEG preview | Quick browsing |
        
        ### Viewing Options
        - **Standard View**: Display in Streamlit
        - **Web Viewer**: Open in new tab with smooth zoom
        - **Download**: Get original quality file
        - **Analysis**: Load for processing
        """)


def render_imaging_statistics(connector, es_indexer, data_sources):
    """Render enhanced imaging statistics"""
    col1, col2, col3, col4, col5 = st.columns(5)

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

    # Get modality and format counts from Neo4j
    if "Neo4j" in data_sources:
        query = "MATCH (i:ImageNode {modality: 'MRI'}) RETURN count(i) as count"
        mri_count = connector.run_query(query)
        col2.metric("MRI Scans", mri_count[0]['count'] if mri_count else 0)

        query = "MATCH (i:ImageNode {modality: 'PET'}) RETURN count(i) as count"
        pet_count = connector.run_query(query)
        col3.metric("PET Scans", pet_count[0]['count'] if pet_count else 0)

        # Count enhanced formats
        query = "MATCH (i:ImageNode) WHERE i.has_web_viewer = true RETURN count(i) as count"
        web_viewer_count = connector.run_query(query)
        col4.metric("Web Viewers", web_viewer_count[0]['count'] if web_viewer_count else 0)

        query = "MATCH (i:ImageNode) WHERE i.has_pyramid = true RETURN count(i) as count"
        pyramid_count = connector.run_query(query)
        col5.metric("Pyramid TIFFs", pyramid_count[0]['count'] if pyramid_count else 0)


def render_image_search(connector, es_indexer, data_sources):
    """Render enhanced image search interface"""
    st.subheader("Search Medical Images")

    # Search interface with format selection
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        search_query = st.text_input("Search (Patient ID, Description, etc.)",
                                     placeholder="e.g., 002_S_0295 or T1 or MRI")
    with col2:
        modality_filter = st.selectbox("Modality", ["All", "MRI", "PET", "CT"])
    with col3:
        format_filter = st.selectbox("Format", ["All", "Web Viewer", "Pyramid", "Standard"])

    # Advanced search options
    with st.expander("Advanced Options"):
        col1, col2, col3 = st.columns(3)
        with col1:
            only_enhanced = st.checkbox("Only enhanced formats", value=False)
        with col2:
            min_resolution = st.number_input("Min Resolution", value=0, step=128)
        with col3:
            date_range = st.date_input("Date Range", value=None)

    if st.button("Search", type="primary"):
        with st.spinner("Searching..."):
            images = search_images_enhanced(
                search_query, modality_filter, format_filter,
                only_enhanced, min_resolution,
                es_indexer, connector, data_sources
            )

        if images:
            st.success(f"Found {len(images)} images")
            display_enhanced_search_results(images, connector)
        else:
            st.info("No images found matching your search")
            st.markdown("Try:")
            st.markdown("- Using a different search term")
            st.markdown("- Changing the modality filter")
            st.markdown("- Removing advanced filters")


def render_browse_by_patient(connector, es_indexer, data_sources):
    """Render enhanced browse by patient interface"""
    col1, col2 = st.columns([3, 1])
    with col1:
        patient_id = st.text_input("Enter Patient ID", placeholder="e.g., 002_S_0295")
    with col2:
        view_mode = st.selectbox("View Mode", ["Gallery", "List", "Comparison"])

    if patient_id:
        with st.spinner(f"Loading images for patient {patient_id}..."):
            images = get_patient_images_enhanced(patient_id, es_indexer, connector, data_sources)

        if images:
            st.success(f"Found {len(images)} images for Patient {patient_id}")

            # Display format statistics
            display_patient_format_stats(images)

            # Group by modality
            mri_images = [img for img in images if img.get('modality') == 'MRI']
            pet_images = [img for img in images if img.get('modality') == 'PET']
            other_images = [img for img in images if img.get('modality') not in ['MRI', 'PET']]

            if view_mode == "Gallery":
                if mri_images:
                    st.markdown("#### MRI Images")
                    display_enhanced_image_grid(mri_images, f"patient_{patient_id}_mri", connector)

                if pet_images:
                    st.markdown("#### PET Images")
                    display_enhanced_image_grid(pet_images, f"patient_{patient_id}_pet", connector)
                    
                if other_images:
                    st.markdown("#### Other Images")
                    display_enhanced_image_grid(other_images, f"patient_{patient_id}_other", connector)
            
            elif view_mode == "List":
                display_image_list(images, connector)
            
            elif view_mode == "Comparison":
                display_image_comparison(images, connector)
        else:
            st.warning(f"No images found for patient {patient_id}")
            st.info("Please check:")
            st.markdown("""
            - Patient ID is correct (format: XXX_S_XXXX)
            - Images have been processed for this patient
            - Database connection is working
            """)
            
            # Try to get patient info
            if connector:
                query = "MATCH (p:Patient {ptid: $ptid}) RETURN p.ptid as id, p.age_at_baseline as age"
                result = connector.run_query(query, {'ptid': patient_id})
                if result:
                    st.success(f"Patient {patient_id} exists in database (age: {result[0].get('age')})")
                    st.error("But no images are linked to this patient")
                else:
                    st.error(f"Patient {patient_id} not found in database")


def render_browse_by_study(connector, es_indexer, data_sources):
    """Render enhanced browse by study date interface"""
    st.subheader("📅 Browse Images by Study Date")

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
            col1, col2 = st.columns([2, 1])
            with col1:
                selected_date = st.selectbox("Select Study Date", [d['date'] for d in dates])
            with col2:
                group_by = st.selectbox("Group By", ["Patient", "Modality", "Format"])

            if selected_date:
                images = get_images_by_date_enhanced(selected_date, es_indexer, connector, data_sources)

                if images:
                    st.info(f"Found {len(images)} images from {selected_date}")
                    
                    if group_by == "Patient":
                        display_grouped_by_patient(images, connector)
                    elif group_by == "Modality":
                        display_grouped_by_modality(images, connector)
                    elif group_by == "Format":
                        display_grouped_by_format(images, connector)


def render_advanced_viewer(connector, es_indexer, data_sources):
    """Render advanced image viewer with multiple format options"""
    st.subheader("🖼️ Advanced Image Viewer")

    # Image selector
    col1, col2 = st.columns([3, 1])
    with col1:
        image_hash = st.text_input("Image Hash or ID", placeholder="Enter image hash or select from search")
    with col2:
        if st.button("Browse Images"):
            st.session_state['show_browser'] = True

    # Image browser
    if st.session_state.get('show_browser', False):
        selected_image = browse_for_image(connector, es_indexer, data_sources)
        if selected_image:
            image_hash = selected_image['image_hash']
            st.session_state['show_browser'] = False

    if image_hash:
        # Get image metadata
        image_data = get_image_metadata(image_hash, connector)
        
        if image_data:
            display_advanced_image_viewer(image_data, connector)
        else:
            st.error(f"Image {image_hash} not found")


def render_image_analysis(connector):
    """Render enhanced image analysis section"""
    st.subheader("📊 Image Analysis and Correlations")

    # Analysis options
    analysis_type = st.selectbox("Analysis Type", 
                                 ["Volume Statistics", "Resolution Distribution", 
                                  "Format Usage", "Processing Status"])

    if analysis_type == "Volume Statistics":
        render_volume_statistics(connector)
    elif analysis_type == "Resolution Distribution":
        render_resolution_distribution(connector)
    elif analysis_type == "Format Usage":
        render_format_usage(connector)
    elif analysis_type == "Processing Status":
        render_processing_status(connector)


# Enhanced helper functions

def search_images_enhanced(query: str, modality: str, format_filter: str,
                          only_enhanced: bool, min_resolution: int,
                          es_indexer, connector, data_sources) -> List[Dict]:
    """Enhanced image search with format filtering"""
    images = []

    # Build search filters
    filters = {}
    if modality != "All":
        filters["modality"] = modality
    
    # Try Elasticsearch first
    if "Elasticsearch" in data_sources and es_indexer:
        try:
            if only_enhanced:
                filters["has_web_viewer"] = True
            
            results = es_indexer.search_images(query, filters=filters, size=100)
            images = [hit["source"] for hit in results["hits"]]
            
            if images:
                logger.info(f"Retrieved {len(images)} images from Elasticsearch")
                return filter_by_format(images, format_filter, min_resolution)
        except Exception as e:
            logger.warning(f"Elasticsearch search failed: {e}, falling back to Neo4j")

    # Fallback to Neo4j with enhanced query
    if "Neo4j" in data_sources and connector:
        try:
            where_clauses = []
            if query:
                where_clauses.append(f"(i.patient_id CONTAINS '{query}' OR i.series_description CONTAINS '{query}')")
            if modality != "All":
                where_clauses.append(f"i.modality = '{modality}'")
            if only_enhanced:
                where_clauses.append("(i.has_web_viewer = true OR i.has_pyramid = true)")
            if format_filter == "Web Viewer":
                where_clauses.append("i.has_web_viewer = true")
            elif format_filter == "Pyramid":
                where_clauses.append("i.has_pyramid = true")

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            neo4j_query = f"""
            MATCH (i:ImageNode)
            WHERE {where_clause}
            RETURN i.image_hash as image_hash,
                   i.patient_id as patient_id,
                   i.modality as modality,
                   i.series_description as series_description,
                   i.study_date as study_date,
                   i.lossless_png_path as lossless_png_path,
                   i.png_path as png_path,
                   i.lossless_tiff_path as lossless_tiff_path,
                   i.tiff_path as tiff_path,
                   i.smooth_tiff_path as smooth_tiff_path,
                   i.pyramid_tiff_path as pyramid_tiff_path,
                   i.viewer_data_path as viewer_data_path,
                   i.viewer_html_path as viewer_html_path,
                   i.thumbnail_path as thumbnail_path,
                   i.original_resolution as resolution,
                   i.has_web_viewer as has_web_viewer,
                   i.has_pyramid as has_pyramid,
                   i.pyramid_levels as pyramid_levels
            LIMIT 100
            """

            images = connector.run_query(neo4j_query)
            logger.info(f"Retrieved {len(images)} images from Neo4j")
        except Exception as e:
            logger.error(f"Neo4j search failed: {e}")

    return images


def get_patient_images_enhanced(patient_id: str, es_indexer, connector, data_sources) -> List[Dict]:
    """Get patient images with enhanced format information"""
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
            # Updated query to get all image paths correctly
            query = """
            MATCH (p:Patient {ptid: $patient_id})-[:HAS_IMAGE]->(i:ImageNode)
            RETURN i.image_hash as image_hash,
                   i.patient_id as patient_id,
                   i.modality as modality,
                   i.series_description as series_description,
                   i.study_date as study_date,
                   i.lossless_png_path as lossless_png_path,
                   i.png_path as png_path,
                   i.lossless_tiff_path as lossless_tiff_path,
                   i.tiff_path as tiff_path,
                   i.smooth_tiff_path as smooth_tiff_path,
                   i.pyramid_tiff_path as pyramid_tiff_path,
                   i.viewer_data_path as viewer_data_path,
                   i.viewer_html_path as viewer_html_path,
                   i.thumbnail_path as thumbnail_path,
                   i.original_resolution as resolution,
                   i.has_web_viewer as has_web_viewer,
                   i.has_pyramid as has_pyramid,
                   i.pyramid_levels as pyramid_levels
            ORDER BY i.study_date DESC, i.modality
            """

            images = connector.run_query(query, {'patient_id': patient_id})
            
            # Log first image for debugging
            if images and len(images) > 0:
                logger.info(f"Retrieved {len(images)} images for patient {patient_id}")
                logger.debug(f"First image paths: {images[0]}")
                
        except Exception as e:
            logger.error(f"Neo4j query failed: {e}")

    return images


def get_images_by_date_enhanced(study_date: str, es_indexer, connector, data_sources) -> List[Dict]:
    """Get images by date with enhanced format information"""
    images = []

    if "Neo4j" in data_sources and connector:
        try:
            query = """
            MATCH (i:ImageNode {study_date: $date})
            RETURN i.image_hash as image_hash,
                   i.patient_id as patient_id,
                   i.modality as modality,
                   i.series_description as series_description,
                   i.lossless_png_path as png_path,
                   i.smooth_tiff_path as smooth_tiff_path,
                   i.pyramid_tiff_path as pyramid_tiff_path,
                   i.viewer_html_path as viewer_html_path,
                   i.thumbnail_path as thumbnail_path,
                   i.has_web_viewer as has_web_viewer,
                   i.has_pyramid as has_pyramid
            LIMIT 200
            """

            images = connector.run_query(query, {'date': study_date})
        except Exception as e:
            logger.error(f"Neo4j query failed: {e}")

    return images


def get_image_metadata(image_hash: str, connector) -> Optional[Dict]:
    """Get complete metadata for a single image"""
    query = """
    MATCH (i:ImageNode {image_hash: $hash})
    RETURN i
    LIMIT 1
    """
    
    result = connector.run_query(query, {'hash': image_hash})
    return result[0]['i'] if result else None


def display_enhanced_search_results(images: List[Dict], connector):
    """Display enhanced image search results with format options"""
    # Group by patient
    patients = {}
    for img in images:
        pid = img.get('patient_id', 'unknown')
        if pid not in patients:
            patients[pid] = []
        patients[pid].append(img)

    # Display first 10 patients
    for idx, (pid, patient_images) in enumerate(list(patients.items())[:10]):
        with st.expander(f"Patient {pid} ({len(patient_images)} images)", expanded=(idx == 0)):
            # Show format availability
            formats = {
                "Web Viewer": sum(1 for img in patient_images if img.get('has_web_viewer')),
                "Pyramid": sum(1 for img in patient_images if img.get('has_pyramid')),
                "Standard": len(patient_images)
            }
            
            st.caption(f"Formats: {', '.join(f'{k}: {v}' for k, v in formats.items() if v > 0)}")
            
            display_enhanced_image_grid(patient_images[:12], f"search_{pid}_{idx}", connector)


def display_enhanced_image_grid(images: List[Dict], context: str, connector):
    """Display image grid with enhanced viewing options"""
    if not images:
        st.info("No images to display")
        return

    # Display options
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col1:
        display_format = st.selectbox(f"Display Format", 
                                      ["Thumbnail", "Lossless PNG", "Web Viewer"],
                                      key=f"format_{context}")
    with col2:
        grid_cols = st.slider(f"Columns", 2, 6, 4, key=f"cols_{context}")
    with col3:
        show_info = st.checkbox(f"Show Info", value=True, key=f"info_{context}")
    with col4:
        debug_mode = st.checkbox(f"Debug Mode", value=False, key=f"debug_{context}")
    
    # Debug mode - show available paths
    if debug_mode:
        with st.expander("Debug: Image Data"):
            for idx, img in enumerate(images[:3]):  # Show first 3 for debugging
                st.write(f"**Image {idx}:**")
                st.json({
                    'patient_id': img.get('patient_id'),
                    'thumbnail_path': img.get('thumbnail_path'),
                    'png_path': img.get('png_path'),
                    'lossless_png_path': img.get('lossless_png_path'),
                    'lossless_tiff_path': img.get('lossless_tiff_path'),
                    'smooth_tiff_path': img.get('smooth_tiff_path'),
                    'pyramid_tiff_path': img.get('pyramid_tiff_path'),
                    'viewer_html_path': img.get('viewer_html_path'),
                    'has_web_viewer': img.get('has_web_viewer'),
                    'has_pyramid': img.get('has_pyramid')
                })

    # Create grid
    cols = st.columns(grid_cols)
    
    for idx, img in enumerate(images):
        col_idx = idx % grid_cols
        
        with cols[col_idx]:
            display_single_image_enhanced(img, display_format, show_info, f"{context}_{idx}", connector)

def display_single_image_enhanced(img: Dict, display_format: str, show_info: bool, key: str, connector):
    """Display a single image with enhanced format options using tabs"""
    
    # Container for the image
    container = st.container()
    
    with container:
        if show_info:
            st.caption(f"**{img.get('patient_id', 'Unknown')}** - {img.get('modality', 'Unknown')}")
            if img.get('study_date'):
                st.caption(f"Date: {img['study_date']}")
        
        # Display based on selected format
        if display_format == "Thumbnail":
            display_thumbnail(img, key)
        elif display_format == "Lossless PNG":
            display_lossless_png(img, key)
        elif display_format == "Web Viewer" and img.get('has_web_viewer'):
            display_web_viewer_button(img, key)
        else:
            display_thumbnail(img, key)  # Fallback
        
        # Create tabs for different actions
        available_tabs = ["Info"]
        if img.get('viewer_html_path'):
            available_tabs.append("Web Viewer")
        if img.get('pyramid_tiff_path'):
            available_tabs.append("Pyramid")
        available_tabs.extend(["Full View", "Download"])
        
        tabs = st.tabs(available_tabs)
        
        tab_index = 0
        with tabs[tab_index]:
            # Info tab
            st.write("**Image Details:**")
            st.write(f"- Hash: {img.get('image_hash', 'N/A')}")
            st.write(f"- Resolution: {img.get('resolution', 'N/A')}")
            st.write(f"- Series: {img.get('series_description', 'N/A')}")
            tab_index += 1
        
        if "Web Viewer" in available_tabs:
            with tabs[tab_index]:
                if img.get('viewer_html_path'):
                    open_web_viewer_inline(img.get('viewer_html_path'))
                tab_index += 1
        
        if "Pyramid" in available_tabs:
            with tabs[tab_index]:
                if img.get('pyramid_tiff_path'):
                    view_pyramid_tiff_inline(img.get('pyramid_tiff_path'), f"pyramid_view_{key}")
                tab_index += 1
        
        with tabs[tab_index]:  # Full View tab
            display_full_image(img, f"full_{key}")
            tab_index += 1
        
        with tabs[tab_index]:  # Download tab
            provide_download_options_inline(img, f"dl_{key}")

def display_full_image(img: Dict, key: str):
    """Display full resolution image"""
    # Try different path options
    image_path = None
    if img.get('lossless_png_path') and Path(img['lossless_png_path']).exists():
        image_path = img['lossless_png_path']
        format_name = "Lossless PNG"
    elif img.get('png_path') and Path(img['png_path']).exists():
        image_path = img['png_path']
        format_name = "PNG"
    elif img.get('lossless_tiff_path') and Path(img['lossless_tiff_path']).exists():
        image_path = img['lossless_tiff_path']
        format_name = "Lossless TIFF"
    elif img.get('thumbnail_path') and Path(img['thumbnail_path']).exists():
        image_path = img['thumbnail_path']
        format_name = "Thumbnail"
    
    if image_path:
        try:
            if image_path.endswith('.tiff') or image_path.endswith('.tif'):
                image_array = tifffile.imread(image_path)
                # Convert to 8-bit for display
                if image_array.dtype != np.uint8:
                    image_array = ((image_array - image_array.min()) / 
                                 (image_array.max() - image_array.min()) * 255).astype(np.uint8)
                image = Image.fromarray(image_array, mode='L')
            else:
                image = Image.open(image_path)
                
                # Convert 16-bit to 8-bit if needed
                if image.mode == 'I;16':
                    img_array = np.array(image)
                    img_array = ((img_array - img_array.min()) / 
                               (img_array.max() - img_array.min()) * 255).astype(np.uint8)
                    image = Image.fromarray(img_array, mode='L')
            
            st.image(image, caption=f"{format_name} - {image.size[0]}x{image.size[1]} pixels", 
                    use_container_width=True)
        except Exception as e:
            st.error(f"Failed to display image: {e}")
    else:
        st.warning("No image file found to display")


def open_web_viewer_inline(html_path: str):
    """Display web viewer inline in Streamlit"""
    if html_path and Path(html_path).exists():
        try:
            # Read the HTML file
            with open(html_path, 'r') as f:
                html_content = f.read()
            
            # Extract just the image data path
            import re
            data_file_match = re.search(r"fetch\('([^']+_data\.json)'\)", html_content)
            
            if data_file_match:
                data_file = data_file_match.group(1)
                data_path = Path(html_path).parent / data_file
                
                if data_path.exists():
                    with open(data_path, 'r') as f:
                        viewer_data = json.load(f)
                    
                    # Display the base resolution image
                    if 'resolutions' in viewer_data and 'x1' in viewer_data['resolutions']:
                        res_data = viewer_data['resolutions']['x1']
                        width = res_data['width']
                        height = res_data['height']
                        
                        # Decode base64 image
                        img_bytes = base64.b64decode(res_data['data'])
                        img_array = np.frombuffer(img_bytes, dtype=np.uint8).reshape(height, width)
                        img = Image.fromarray(img_array, mode='L')
                        
                        st.image(img, caption=f"Interactive View - {width}x{height}", 
                                use_container_width=True)
                        st.info("Note: This is a static view. For interactive controls, download the HTML file.")
            else:
                st.warning("Could not parse viewer data")
                
        except Exception as e:
            st.error(f"Failed to load web viewer: {e}")
    else:
        st.error("Web viewer file not found")


def view_pyramid_tiff_inline(pyramid_path: str, key: str):
    """View pyramid TIFF with level selection inline - robust version"""
    if not pyramid_path:
        st.warning("No pyramid TIFF path provided")
        return
        
    if not Path(pyramid_path).exists():
        st.error(f"Pyramid TIFF not found at: {pyramid_path}")
        return
    
    try:
        with tifffile.TiffFile(pyramid_path) as tif:
            num_levels = len(tif.pages)
            
            # Handle level selection
            if num_levels > 1:
                level = st.slider(
                    f"Pyramid Level (0=highest resolution)", 
                    min_value=0, 
                    max_value=max(0, num_levels-1),  # Ensure max is at least 0
                    value=0, 
                    key=f"pyramid_level_{key}"
                )
                st.caption(f"Pyramid has {num_levels} resolution levels")
            else:
                level = 0
                if num_levels == 0:
                    st.error("No image data in TIFF file")
                    return
                st.info("Single resolution image (not a pyramid TIFF)")
            
            # Read selected level
            image_data = tif.pages[level].asarray()
            
            # Handle empty or invalid image data
            if image_data.size == 0:
                st.error("Empty image data")
                return
            
            # Convert to 8-bit for display with proper handling
            if image_data.dtype != np.uint8:
                # Check if all pixels are the same value (avoid divide by zero)
                data_min = image_data.min()
                data_max = image_data.max()
                
                if data_min == data_max:
                    # All pixels have the same value
                    if data_min == 0:
                        # All black image
                        image_data = np.zeros_like(image_data, dtype=np.uint8)
                    else:
                        # Convert to middle gray
                        image_data = np.full_like(image_data, 128, dtype=np.uint8)
                else:
                    # Normal normalization
                    image_data = ((image_data - data_min) / (data_max - data_min) * 255).astype(np.uint8)
            
            # Create PIL image
            if len(image_data.shape) == 2:
                image = Image.fromarray(image_data, mode='L')
            elif len(image_data.shape) == 3:
                if image_data.shape[2] == 1:
                    image = Image.fromarray(image_data[:,:,0], mode='L')
                elif image_data.shape[2] == 3:
                    image = Image.fromarray(image_data, mode='RGB')
                elif image_data.shape[2] == 4:
                    image = Image.fromarray(image_data, mode='RGBA')
                else:
                    st.error(f"Unsupported number of channels: {image_data.shape[2]}")
                    return
            else:
                st.error(f"Unsupported image shape: {image_data.shape}")
                return
            
            # Display the image
            st.image(image, caption=f"Level {level} - Size: {image_data.shape[1]}x{image_data.shape[0]}", 
                    use_container_width=True)
            
            # Show additional pyramid info if multi-level
            if num_levels > 1:
                with st.expander("Pyramid Details"):
                    for i in range(min(num_levels, 10)):  # Show first 10 levels
                        try:
                            page = tif.pages[i]
                            st.write(f"Level {i}: {page.shape[1]}x{page.shape[0]} pixels")
                        except:
                            st.write(f"Level {i}: Unable to read dimensions")
                    if num_levels > 10:
                        st.write(f"... and {num_levels - 10} more levels")
                        
    except Exception as e:
        st.error(f"Failed to load pyramid TIFF: {str(e)}")
        logger.error(f"Detailed pyramid TIFF error for {pyramid_path}: {e}", exc_info=True)


def provide_download_options_inline(img: Dict, key: str):
    """Provide download options inline"""
    available_files = []
    
    # Check which files are available
    if img.get('lossless_png_path') and Path(img.get('lossless_png_path')).exists():
        available_files.append(('Lossless PNG', img['lossless_png_path'], 'image.png'))
    
    if img.get('lossless_tiff_path') and Path(img.get('lossless_tiff_path')).exists():
        available_files.append(('Lossless TIFF', img['lossless_tiff_path'], 'image.tiff'))
    
    if img.get('smooth_tiff_path') and Path(img.get('smooth_tiff_path')).exists():
        available_files.append(('Smooth TIFF', img['smooth_tiff_path'], 'image_smooth.tiff'))
    
    if img.get('pyramid_tiff_path') and Path(img.get('pyramid_tiff_path')).exists():
        available_files.append(('Pyramid TIFF', img['pyramid_tiff_path'], 'image_pyramid.tiff'))
    
    if img.get('viewer_html_path') and Path(img.get('viewer_html_path')).exists():
        available_files.append(('Web Viewer HTML', img['viewer_html_path'], 'viewer.html'))
    
    if img.get('thumbnail_path') and Path(img.get('thumbnail_path')).exists():
        available_files.append(('Thumbnail', img['thumbnail_path'], 'thumbnail.jpg'))
    
    if not available_files:
        st.warning("No files available for download")
        return
    
    for file_type, file_path, filename in available_files:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.text(file_type)
        with col2:
            with open(file_path, 'rb') as f:
                file_data = f.read()
            st.download_button(
                label="Download",
                data=file_data,
                file_name=filename,
                mime="application/octet-stream",
                key=f"{key}_{file_type.replace(' ', '_')}"
            )


def display_thumbnail(img: Dict, key: str) -> bool:
    """Display thumbnail image"""
    thumb_path = img.get('thumbnail_path')
    if thumb_path and Path(thumb_path).exists():
        try:
            image = Image.open(thumb_path)
            st.image(image, use_container_width=True)
            return True
        except Exception as e:
            st.error(f"Failed to load thumbnail from {thumb_path}: {e}")
            return False
    else:
        st.info("No thumbnail available")
        return False


def display_lossless_png(img: Dict, key: str):
    """Display lossless PNG with proper handling of 16-bit images"""
    # Try multiple path fields
    png_path = img.get('lossless_png_path') or img.get('png_path')
    
    if png_path and Path(png_path).exists():
        try:
            image = Image.open(png_path)
            
            # Convert 16-bit to 8-bit for display if needed
            if image.mode == 'I;16':
                # Convert to numpy array
                img_array = np.array(image)
                # Normalize to 8-bit
                img_array = ((img_array - img_array.min()) / 
                            (img_array.max() - img_array.min()) * 255).astype(np.uint8)
                image = Image.fromarray(img_array, mode='L')
            
            st.image(image, use_container_width=True)
        except Exception as e:
            st.error(f"Failed to load PNG from {png_path}: {e}")
    else:
        # Fallback to thumbnail
        display_thumbnail(img, key)


def display_web_viewer_button(img: Dict, key: str):
    """Display button to open web viewer"""
    if img.get('viewer_html_path'):
        st.markdown(f"""
        <div style="border: 2px solid #4CAF50; border-radius: 10px; padding: 20px; text-align: center;">
            <h4>Interactive Web Viewer Available</h4>
            <p>Click button above to open smooth zoom viewer</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        display_thumbnail(img, key)


def view_pyramid_tiff(pyramid_path: str, key: str):
    """View pyramid TIFF with level selection"""
    if Path(pyramid_path).exists():
        try:
            with tifffile.TiffFile(pyramid_path) as tif:
                num_levels = len(tif.pages)
                
                level = st.slider(f"Pyramid Level", 0, num_levels-1, 0, 
                                 key=f"pyramid_level_{key}")
                
                # Read selected level
                image_data = tif.pages[level].asarray()
                
                # Convert to 8-bit for display
                if image_data.dtype != np.uint8:
                    image_data = ((image_data - image_data.min()) / 
                                 (image_data.max() - image_data.min()) * 255).astype(np.uint8)
                
                image = Image.fromarray(image_data, mode='L')
                st.image(image, use_container_width=True)
                st.caption(f"Level {level} - Size: {image_data.shape}")
        except Exception as e:
            st.error(f"Failed to load pyramid TIFF: {e}")
    else:
        st.error("Pyramid TIFF not found")


def open_web_viewer(html_path: str):
    """Open web viewer - fallback function for compatibility"""
    open_web_viewer_inline(html_path)


def provide_download_options(img: Dict, key: str):
    """Provide download options - fallback function for compatibility"""
    provide_download_options_inline(img, key)


def display_patient_format_stats(images: List[Dict]):
    """Display format statistics for patient images"""
    stats = {
        "Total Images": len(images),
        "With Web Viewer": sum(1 for img in images if img.get('has_web_viewer')),
        "With Pyramid": sum(1 for img in images if img.get('has_pyramid')),
        "With Smooth TIFF": sum(1 for img in images if img.get('smooth_tiff_path'))
    }
    
    cols = st.columns(len(stats))
    for col, (label, value) in zip(cols, stats.items()):
        col.metric(label, value)


def display_image_list(images: List[Dict], connector):
    """Display images in list format with details"""
    for img in images:
        with st.container():
            col1, col2, col3, col4 = st.columns([1, 2, 2, 2])
            
            with col1:
                if img.get('thumbnail_path'):
                    display_thumbnail(img, f"list_{img.get('image_hash', '')}")
            
            with col2:
                st.write(f"**Patient:** {img.get('patient_id', 'Unknown')}")
                st.write(f"**Modality:** {img.get('modality', 'Unknown')}")
                st.write(f"**Date:** {img.get('study_date', 'Unknown')}")
            
            with col3:
                st.write(f"**Resolution:** {img.get('resolution', 'Unknown')}")
                formats = []
                if img.get('has_web_viewer'):
                    formats.append("Web Viewer")
                if img.get('has_pyramid'):
                    formats.append(f"Pyramid ({img.get('pyramid_levels', 0)} levels)")
                st.write(f"**Formats:** {', '.join(formats) if formats else 'Standard'}")
            
            with col4:
                if img.get('viewer_html_path'):
                    if st.button("Open Viewer", key=f"open_{img.get('image_hash', '')}"):
                        open_web_viewer(img['viewer_html_path'])
            
            st.divider()


def display_image_comparison(images: List[Dict], connector):
    """Display side-by-side image comparison"""
    if len(images) < 2:
        st.info("Need at least 2 images for comparison")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        idx1 = st.selectbox("Image 1", range(len(images)), 
                           format_func=lambda x: f"{images[x].get('modality', '')} - {images[x].get('study_date', '')}")
        display_single_image_enhanced(images[idx1], "Lossless PNG", True, "comp1", connector)
    
    with col2:
        idx2 = st.selectbox("Image 2", range(len(images)), index=min(1, len(images)-1),
                           format_func=lambda x: f"{images[x].get('modality', '')} - {images[x].get('study_date', '')}")
        display_single_image_enhanced(images[idx2], "Lossless PNG", True, "comp2", connector)


def display_grouped_by_patient(images: List[Dict], connector):
    """Display images grouped by patient"""
    patients = {}
    for img in images:
        pid = img.get('patient_id', 'unknown')
        if pid not in patients:
            patients[pid] = []
        patients[pid].append(img)
    
    for pid, patient_images in patients.items():
        with st.expander(f"Patient {pid} ({len(patient_images)} images)"):
            display_enhanced_image_grid(patient_images, f"patient_{pid}", connector)


def display_grouped_by_modality(images: List[Dict], connector):
    """Display images grouped by modality"""
    modalities = {}
    for img in images:
        mod = img.get('modality', 'unknown')
        if mod not in modalities:
            modalities[mod] = []
        modalities[mod].append(img)
    
    tabs = st.tabs(list(modalities.keys()))
    for tab, (modality, mod_images) in zip(tabs, modalities.items()):
        with tab:
            display_enhanced_image_grid(mod_images, f"modality_{modality}", connector)


def display_grouped_by_format(images: List[Dict], connector):
    """Display images grouped by available formats"""
    format_groups = {
        "Web Viewer Ready": [img for img in images if img.get('has_web_viewer')],
        "Pyramid Available": [img for img in images if img.get('has_pyramid')],
        "Standard Only": [img for img in images if not img.get('has_web_viewer') and not img.get('has_pyramid')]
    }
    
    for format_name, format_images in format_groups.items():
        if format_images:
            with st.expander(f"{format_name} ({len(format_images)} images)"):
                display_enhanced_image_grid(format_images, f"format_{format_name}", connector)


def display_advanced_image_viewer(image_data: Dict, connector):
    """Display advanced viewer for a single image with all format options"""
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader(f"Image: {image_data.get('patient_id', 'Unknown')}")
        
        # Format selector
        available_formats = []
        if image_data.get('thumbnail_path'):
            available_formats.append("Thumbnail")
        if image_data.get('lossless_png_path'):
            available_formats.append("Lossless PNG")
        if image_data.get('smooth_tiff_path'):
            available_formats.append("Smooth TIFF")
        if image_data.get('pyramid_tiff_path'):
            available_formats.append("Pyramid TIFF")
        if image_data.get('viewer_html_path'):
            available_formats.append("Web Viewer")
        
        selected_format = st.selectbox("Select Format", available_formats)
        
        # Display selected format
        if selected_format == "Thumbnail":
            display_thumbnail(image_data, "advanced")
        elif selected_format == "Lossless PNG":
            display_lossless_png(image_data, "advanced")
        elif selected_format == "Smooth TIFF":
            display_smooth_tiff(image_data, "advanced")
        elif selected_format == "Pyramid TIFF":
            view_pyramid_tiff(image_data['pyramid_tiff_path'], "advanced")
        elif selected_format == "Web Viewer":
            if st.button("Open Interactive Viewer"):
                open_web_viewer_inline(image_data['viewer_html_path'])
    
    with col2:
        st.subheader("Metadata")
        metadata_display = {
            "Patient ID": image_data.get('patient_id'),
            "Modality": image_data.get('modality'),
            "Study Date": image_data.get('study_date'),
            "Resolution": image_data.get('original_resolution'),
            "Has Web Viewer": "[Yes]" if image_data.get('has_web_viewer') else "[No]",
            "Has Pyramid": "[Yes]" if image_data.get('has_pyramid') else "[No]",
            "Pyramid Levels": image_data.get('pyramid_levels', 0)
        }
        
        for key, value in metadata_display.items():
            st.write(f"**{key}:** {value}")
        
        # Download section
        st.subheader("Downloads")
        provide_download_options_inline(image_data, "advanced")


def display_smooth_tiff(image_data: Dict, key: str):
    """Display smooth TIFF with interpolation"""
    tiff_path = image_data.get('smooth_tiff_path')
    if tiff_path and Path(tiff_path).exists():
        try:
            image = tifffile.imread(tiff_path)
            
            # Convert to 8-bit for display
            if image.dtype != np.uint8:
                image = ((image - image.min()) / 
                        (image.max() - image.min()) * 255).astype(np.uint8)
            
            img_pil = Image.fromarray(image, mode='L')
            st.image(img_pil, use_container_width=True)
            st.caption("Smooth TIFF with interpolation instructions")
        except Exception as e:
            st.error(f"Failed to load smooth TIFF: {e}")
    else:
        st.info("Smooth TIFF not available")


def browse_for_image(connector, es_indexer, data_sources) -> Optional[Dict]:
    """Browse and select an image"""
    # Quick search
    search = st.text_input("Quick search for image selection")
    if search:
        images = search_images_enhanced(search, "All", "All", False, 0, 
                                       es_indexer, connector, data_sources)
        if images:
            selected_idx = st.selectbox("Select Image", 
                                       range(len(images)),
                                       format_func=lambda x: f"{images[x].get('patient_id')} - {images[x].get('modality')} - {images[x].get('study_date')}")
            if st.button("Select This Image"):
                return images[selected_idx]
    return None


def render_volume_statistics(connector):
    """Render volume statistics analysis"""
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

        st.subheader("Volume Statistics by Region")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No volumetric data available")


def render_resolution_distribution(connector):
    """Render resolution distribution analysis"""
    query = """
    MATCH (i:ImageNode)
    WHERE i.original_resolution IS NOT NULL
    RETURN i.original_resolution as resolution,
           i.modality as modality,
           COUNT(i) as count
    ORDER BY count DESC
    LIMIT 20
    """
    
    results = connector.run_query(query)
    
    if results:
        df = pd.DataFrame(results)
        
        fig = go.Figure(data=[
            go.Bar(x=df['resolution'], y=df['count'], 
                  text=df['modality'],
                  textposition='auto')
        ])
        
        fig.update_layout(title="Image Resolution Distribution",
                         xaxis_title="Resolution",
                         yaxis_title="Count")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No resolution data available")


def render_format_usage(connector):
    """Render format usage statistics"""
    query = """
    MATCH (i:ImageNode)
    RETURN 
        COUNT(CASE WHEN i.has_web_viewer = true THEN 1 END) as web_viewer_count,
        COUNT(CASE WHEN i.has_pyramid = true THEN 1 END) as pyramid_count,
        COUNT(CASE WHEN i.smooth_tiff_path IS NOT NULL THEN 1 END) as smooth_count,
        COUNT(i) as total_count
    """
    
    results = connector.run_query(query)
    
    if results:
        data = results[0]
        
        fig = go.Figure(data=[go.Pie(
            labels=['Web Viewer', 'Pyramid TIFF', 'Smooth TIFF', 'Standard Only'],
            values=[
                data['web_viewer_count'],
                data['pyramid_count'],
                data['smooth_count'],
                data['total_count'] - max(data['web_viewer_count'], data['pyramid_count'], data['smooth_count'])
            ]
        )])
        
        fig.update_layout(title="Image Format Distribution")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No format data available")


def render_processing_status(connector):
    """Render processing status overview"""
    col1, col2, col3 = st.columns(3)
    
    # Get processing stats
    query = """
    MATCH (i:ImageNode)
    RETURN 
        COUNT(i) as total,
        COUNT(CASE WHEN i.lossless_png_path IS NOT NULL THEN 1 END) as processed,
        COUNT(CASE WHEN i.has_web_viewer = true THEN 1 END) as enhanced
    """
    
    results = connector.run_query(query)
    
    if results:
        data = results[0]
        
        with col1:
            st.metric("Total Images", f"{data['total']:,}")
        
        with col2:
            processed_pct = (data['processed'] / data['total'] * 100) if data['total'] > 0 else 0
            st.metric("Processed", f"{data['processed']:,}", f"{processed_pct:.1f}%")
        
        with col3:
            enhanced_pct = (data['enhanced'] / data['total'] * 100) if data['total'] > 0 else 0
            st.metric("Enhanced", f"{data['enhanced']:,}", f"{enhanced_pct:.1f}%")
        
        # Progress bars
        st.progress(processed_pct / 100)
        st.caption(f"Processing Progress: {processed_pct:.1f}%")
        
        st.progress(enhanced_pct / 100)
        st.caption(f"Enhancement Progress: {enhanced_pct:.1f}%")


def filter_by_format(images: List[Dict], format_filter: str, min_resolution: int) -> List[Dict]:
    """Filter images by format and resolution"""
    filtered = images
    
    if format_filter == "Web Viewer":
        filtered = [img for img in filtered if img.get('has_web_viewer')]
    elif format_filter == "Pyramid":
        filtered = [img for img in filtered if img.get('has_pyramid')]
    
    if min_resolution > 0:
        filtered = [img for img in filtered 
                   if parse_resolution(img.get('resolution', '0x0')) >= min_resolution]
    
    return filtered


def parse_resolution(resolution_str: str) -> int:
    """Parse resolution string and return max dimension"""
    try:
        if 'x' in resolution_str:
            dims = resolution_str.split('x')
            return max(int(dims[0]), int(dims[1]))
    except:
        pass
    return 0