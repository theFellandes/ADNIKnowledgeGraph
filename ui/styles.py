"""
Custom CSS styles for the ADNI Knowledge Graph UI
"""

import streamlit as st


def apply_custom_styles():
    """Apply all custom CSS styles with comprehensive dark mode support"""
    st.markdown("""
    <style>
        /* Enhanced Dark Mode Support */
        @media (prefers-color-scheme: dark) {
            /* Fix for all tab panels and content */
            .stTabs [data-baseweb="tab-panel"] {
                background-color: transparent !important;
            }

            .stTabs [data-baseweb="tab-list"] {
                background-color: rgba(39, 40, 43, 0.5) !important;
                gap: 8px;
                padding: 8px;
                border-radius: 10px;
            }

            .stTabs [data-baseweb="tab"] {
                background-color: rgba(80, 80, 80, 0.3) !important;
                color: rgba(250, 250, 250, 0.9) !important;
                border-radius: 8px;
                padding: 8px 16px;
            }

            .stTabs [aria-selected="true"] {
                background: linear-gradient(135deg, #667eea, #764ba2) !important;
                color: white !important;
            }

            /* Tab content text fix */
            .stTabs [data-baseweb="tab-panel"] p,
            .stTabs [data-baseweb="tab-panel"] h1,
            .stTabs [data-baseweb="tab-panel"] h2,
            .stTabs [data-baseweb="tab-panel"] h3,
            .stTabs [data-baseweb="tab-panel"] h4,
            .stTabs [data-baseweb="tab-panel"] span,
            .stTabs [data-baseweb="tab-panel"] div {
                color: inherit !important;
            }

            /* Fix metric cards in dark mode */
            .metric-card {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
                color: white !important;
            }

            .metric-card h2, .metric-card p {
                color: white !important;
            }

            /* Fix ATN profile cards */
            .atn-profile {
                background: rgba(39, 40, 43, 0.8) !important;
                border: 1px solid rgba(255, 255, 255, 0.1) !important;
                color: rgba(250, 250, 250, 0.9) !important;
            }

            .atn-profile h4, .atn-profile p {
                color: rgba(250, 250, 250, 0.9) !important;
            }

            /* Fix patient cards */
            .patient-card {
                background: rgba(39, 40, 43, 0.8) !important;
                border-left: 5px solid #667eea !important;
                color: rgba(250, 250, 250, 0.9) !important;
            }

            .patient-card h4, .patient-card p {
                color: rgba(250, 250, 250, 0.9) !important;
            }

            /* Fix network legend */
            .network-legend {
                background: rgba(39, 40, 43, 0.8) !important;
                color: rgba(250, 250, 250, 0.9) !important;
            }

            /* Fix select boxes and inputs */
            .stSelectbox > div > div {
                background-color: rgba(39, 40, 43, 0.5) !important;
            }

            .stTextInput > div > div > input {
                background-color: rgba(39, 40, 43, 0.5) !important;
                color: rgba(250, 250, 250, 0.9) !important;
            }

            /* Fix expandable sections */
            .streamlit-expanderHeader {
                background-color: rgba(39, 40, 43, 0.5) !important;
                color: rgba(250, 250, 250, 0.9) !important;
            }

            .streamlit-expanderContent {
                background-color: rgba(39, 40, 43, 0.3) !important;
            }

            /* Fix dataframes */
            .stDataFrame {
                background-color: rgba(39, 40, 43, 0.5) !important;
            }

            /* Risk indicators with better dark mode contrast */
            .risk-low {
                background: rgba(82, 196, 26, 0.2) !important;
                color: #52c41a !important;
                border: 1px solid #52c41a !important;
            }

            .risk-moderate {
                background: rgba(250, 173, 20, 0.2) !important;
                color: #faad14 !important;
                border: 1px solid #faad14 !important;
            }

            .risk-high {
                background: rgba(245, 34, 45, 0.2) !important;
                color: #f5222d !important;
                border: 1px solid #f5222d !important;
            }

            .risk-very-high {
                background: rgba(207, 19, 34, 0.3) !important;
                color: #ff4d4f !important;
                border: 1px solid #cf1322 !important;
            }

            /* ATN status badges */
            .atn-positive {
                background: rgba(255, 107, 107, 0.8) !important;
                color: white !important;
            }

            .atn-negative {
                background: rgba(81, 207, 102, 0.8) !important;
                color: white !important;
            }

            /* Stage badges with better visibility */
            .stage-badge {
                color: white !important;
                font-weight: bold !important;
            }

            /* Biomarker trend indicators */
            .trend-up {
                background: rgba(255, 107, 107, 0.2) !important;
                color: #ff6b6b !important;
                border: 1px solid #ff6b6b !important;
            }

            .trend-down {
                background: rgba(81, 207, 102, 0.2) !important;
                color: #51cf66 !important;
                border: 1px solid #51cf66 !important;
            }

            .trend-stable {
                background: rgba(79, 172, 254, 0.2) !important;
                color: #4facfe !important;
                border: 1px solid #4facfe !important;
            }
        }

        /* Light mode styles (default) */
        .main { padding-top: 1rem; }

        /* Enhanced metric cards */
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 15px;
            margin: 10px 0;
            box-shadow: 0 10px 20px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }

        .metric-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 30px rgba(0,0,0,0.15);
        }

        .metric-card h2, .metric-card p {
            color: white !important;
            margin: 0;
        }

        /* ATN Profile styles */
        .atn-profile {
            background: white;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            margin: 15px 0;
        }

        .atn-status {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            margin: 5px;
        }

        .atn-positive { 
            background: #ff6b6b; 
            color: white !important;
        }

        .atn-negative { 
            background: #51cf66; 
            color: white !important;
        }

        /* Disease stage badges */
        .stage-badge {
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: bold;
            margin: 5px;
            display: inline-block;
            text-transform: uppercase;
            font-size: 0.9rem;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            color: white !important;
        }

        .stage-cn { background: linear-gradient(135deg, #667eea, #764ba2); }
        .stage-smc { background: linear-gradient(135deg, #f093fb, #f5576c); }
        .stage-emci { background: linear-gradient(135deg, #4facfe, #00f2fe); }
        .stage-lmci { background: linear-gradient(135deg, #43e97b, #38f9d7); }
        .stage-mci { background: linear-gradient(135deg, #38f9d7, #43e97b); }
        .stage-ad { background: linear-gradient(135deg, #fa709a, #fee140); }

        /* Risk level indicators */
        .risk-indicator {
            padding: 12px 24px;
            border-radius: 30px;
            font-weight: bold;
            text-align: center;
            margin: 10px 0;
        }

        .risk-low { 
            background: #d3f9d8; 
            color: #2b8a3e !important;
        }

        .risk-moderate { 
            background: #fff3cd; 
            color: #f08c00 !important;
        }

        .risk-high { 
            background: #ffe0e0; 
            color: #c92a2a !important;
        }

        .risk-very-high { 
            background: #ff6b6b; 
            color: white !important;
        }

        /* Enhanced patient card */
        .patient-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            border-left: 5px solid #667eea;
            transition: all 0.3s ease;
        }

        .patient-card:hover {
            transform: translateX(5px);
            box-shadow: 0 8px 20px rgba(0,0,0,0.15);
        }

        /* Biomarker trend indicator */
        .biomarker-trend {
            display: inline-flex;
            align-items: center;
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 0.9rem;
        }

        .trend-up { 
            background: #ffe0e0; 
            color: #c92a2a !important;
        }

        .trend-down { 
            background: #d3f9d8; 
            color: #2b8a3e !important;
        }

        .trend-stable { 
            background: #e3fafc; 
            color: #0c8599 !important;
        }

        /* Network legend */
        .network-legend {
            background: white;
            border-radius: 10px;
            padding: 15px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-top: 20px;
        }

        /* Tab styling for both light and dark modes */
        .stTabs [data-baseweb="tab-list"] {
            gap: 24px;
            background: linear-gradient(to right, #f8f9fa, #ffffff);
            padding: 10px;
            border-radius: 10px;
        }

        .stTabs [data-baseweb="tab"] {
            height: 50px;
            padding: 0 24px;
            background-color: white;
            border-radius: 10px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        }

        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white !important;
        }
    </style>
    """, unsafe_allow_html=True)