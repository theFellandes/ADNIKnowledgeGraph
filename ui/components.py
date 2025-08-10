"""
Shared UI components
"""

import streamlit as st
import uuid
from pathlib import Path
from PIL import Image
import numpy as np
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def load_and_convert_image(path: Path) -> Optional[Image.Image]:
    """Load and convert image to displayable format"""
    try:
        img = Image.open(path)

        # Convert problematic modes
        if img.mode == 'I;16':
            img_array = np.array(img)
            if img_array.max() > img_array.min():
                img_array = ((img_array - img_array.min()) /
                             (img_array.max() - img_array.min()) * 255).astype(np.uint8)
            else:
                img_array = np.zeros_like(img_array, dtype=np.uint8)
            img = Image.fromarray(img_array, mode='L')
        elif img.mode == 'I':
            img = img.convert('L')

        if img.mode not in ['RGB', 'RGBA']:
            img = img.convert('RGB')

        return img
    except Exception as e:
        logger.error(f"Error converting image: {e}")
        return None


def display_image_grid(images: List[Dict], context: str = "", on_view_callback=None):
    """
    Display images in a grid with working view buttons

    Args:
        images: List of image dictionaries
        context: Unique context string for button keys
        on_view_callback: Optional callback function when view is clicked
    """
    if not images:
        st.info("No images to display")
        return

    cols = st.columns(4)

    # Generate unique context if not provided
    if not context:
        context = str(uuid.uuid4())[:8]

    for idx, img in enumerate(images[:12]):  # Limit to 12 images
        col_idx = idx % 4

        with cols[col_idx]:
            # Try to display the image
            image_displayed = False

            # Try thumbnail first
            if img.get('thumbnail_path'):
                path = Path(img['thumbnail_path'])
                if path.exists():
                    try:
                        pil_img = load_and_convert_image(path)
                        if pil_img:
                            st.image(pil_img,
                                     caption=img.get('series_description', 'Image')[:20],
                                     use_container_width=True)
                            image_displayed = True
                    except Exception as e:
                        logger.error(f"Error loading thumbnail: {e}")

            # Try PNG if thumbnail failed
            if not image_displayed and img.get('png_path'):
                path = Path(img['png_path'])
                if path.exists():
                    try:
                        pil_img = load_and_convert_image(path)
                        if pil_img:
                            # Resize for display
                            pil_img.thumbnail((200, 200))
                            st.image(pil_img,
                                     caption=img.get('series_description', 'Image')[:20],
                                     use_container_width=True)
                            image_displayed = True
                    except Exception as e:
                        logger.error(f"Error loading PNG: {e}")

            # Show placeholder if no image could be displayed
            if not image_displayed:
                st.markdown(f"""
                <div style="background: #f0f0f0; padding: 40px; 
                           border-radius: 10px; text-align: center;">
                    <p>📷</p>
                    <small>{img.get('modality', 'Image')}</small>
                </div>
                """, unsafe_allow_html=True)

            # FIXED: Create a callback function for the button
            def make_callback(image_data):
                def callback():
                    st.session_state.selected_image = image_data
                    st.session_state.show_image_modal = True
                    if on_view_callback:
                        on_view_callback(image_data)

                return callback

            # Add view button with callback
            button_key = f"view_{context}_{idx}_{str(uuid.uuid4())[:8]}"
            st.button("View", key=button_key, on_click=make_callback(img))


def render_metric_cards(metrics: Dict[str, tuple]):
    """
    Render metric cards

    Args:
        metrics: Dictionary of {title: (value, subtitle)}
    """
    cols = st.columns(len(metrics))

    for idx, (title, (value, subtitle)) in enumerate(metrics.items()):
        with cols[idx]:
            st.markdown(f"""
            <div class="metric-card">
                <h2 style="color: white; margin: 0;">{value}</h2>
                <p style="color: rgba(255,255,255,0.9); margin: 0;">{subtitle}</p>
            </div>
            """, unsafe_allow_html=True)


def render_stage_badge(stage: str):
    """Render a disease stage badge"""
    stage_class = f"stage-{stage.lower()}"
    return f'<div class="stage-badge {stage_class}">{stage}</div>'


def render_risk_indicator(risk_level: str):
    """Render a risk indicator"""
    risk_class = f"risk-{risk_level.lower().replace(' ', '-')}"
    return f'<div class="risk-indicator {risk_class}">Risk: {risk_level.upper()}</div>'


def render_atn_status(status: str):
    """Render ATN status badge"""
    status_class = 'atn-positive' if '+' in status else 'atn-negative'
    return f'<span class="atn-status {status_class}">{status}</span>'


def render_image_viewer_modal():
    """Render image viewer modal"""
    if st.session_state.selected_image and st.session_state.show_image_modal:
        img = st.session_state.selected_image

        # Create modal layout
        st.markdown("---")
        st.markdown("### 🖼️ Image Viewer")

        col1, col2 = st.columns([4, 1])

        with col1:
            # Try to display the image
            image_displayed = False

            # Try PNG path first
            if img.get('png_path'):
                path = Path(img['png_path'])
                if path.exists():
                    try:
                        pil_img = load_and_convert_image(path)
                        if pil_img:
                            st.image(pil_img,
                                     caption=img.get('series_description', 'Medical Image'),
                                     use_container_width=True)
                            image_displayed = True
                    except Exception as e:
                        logger.error(f"Error loading PNG: {e}")

            # Try thumbnail if PNG failed
            if not image_displayed and img.get('thumbnail_path'):
                path = Path(img['thumbnail_path'])
                if path.exists():
                    try:
                        pil_img = load_and_convert_image(path)
                        if pil_img:
                            # Scale up thumbnail for better visibility
                            width, height = pil_img.size
                            pil_img = pil_img.resize((width * 3, height * 3), Image.LANCZOS)
                            st.image(pil_img,
                                     caption=img.get('series_description', 'Medical Image'),
                                     use_container_width=True)
                            image_displayed = True
                    except Exception as e:
                        logger.error(f"Error loading thumbnail: {e}")

            if not image_displayed:
                st.error("Image file not found or could not be loaded")
                st.info(f"Tried paths: {img.get('png_path', 'N/A')}, {img.get('thumbnail_path', 'N/A')}")

        with col2:
            st.markdown("**Image Details**")
            st.text(f"ID: {img.get('image_id', 'N/A')[:20]}")
            st.text(f"Patient: {img.get('patient_id', 'N/A')}")
            st.text(f"Modality: {img.get('modality', 'N/A')}")
            st.text(f"Study Date: {img.get('study_date', 'N/A')}")

            if img.get('series_description'):
                st.text(f"Series: {img['series_description'][:30]}")

            st.markdown("---")

            if st.button("Close Viewer", type="primary", key="close_viewer"):
                st.session_state.show_image_modal = False
                st.session_state.selected_image = None
                st.rerun()