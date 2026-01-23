"""
=============================================================================
PROJECT ATLAS - Theme System
=============================================================================
Dark purple theme with proper text visibility.
"""

import streamlit as st


def get_theme_css():
    """Theme CSS - Dark purple with white text, carefully scoped."""
    return """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        
        /* ============================================
           BASE STYLES
           ============================================ */
        
        .stApp {
            background: #1a1a2e !important;
            font-family: 'Inter', sans-serif !important;
            color: #ffffff !important;
        }
        
        .main .block-container {
            padding: 2rem !important;
            max-width: 1400px !important;
        }
        
        /* ============================================
           TYPOGRAPHY - White text on dark background
           ============================================ */
        
        /* Headings */
        .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
            color: #ffffff !important;
        }
        
        /* Markdown text */
        .stMarkdown {
            color: #ffffff !important;
        }
        
        .stMarkdown p {
            color: #ffffff !important;
        }
        
        .stMarkdown strong {
            color: #ffffff !important;
        }
        
        .stMarkdown em {
            color: #8b5cf6 !important;
        }
        
        /* Code styling */
        .stMarkdown code {
            background: #25253d !important;
            color: #8b5cf6 !important;
            padding: 2px 6px !important;
            border-radius: 4px !important;
        }
        
        /* Captions */
        .stCaption {
            color: #8888a8 !important;
        }
        
        /* ============================================
           SIDEBAR
           ============================================ */
        
        [data-testid="stSidebar"] {
            background: #25253d !important;
        }
        
        [data-testid="stSidebar"] .stMarkdown {
            color: #ffffff !important;
        }
        
        [data-testid="stSidebar"] .stMarkdown p,
        [data-testid="stSidebar"] .stMarkdown h1,
        [data-testid="stSidebar"] .stMarkdown h2,
        [data-testid="stSidebar"] .stMarkdown h3 {
            color: #ffffff !important;
        }
        
        [data-testid="stSidebar"] .stCaption {
            color: #8888a8 !important;
        }
        
        /* ============================================
           FORM INPUTS
           ============================================ */
        
        /* Input labels */
        .stTextInput label,
        .stNumberInput label,
        .stTextArea label,
        .stSelectbox label,
        .stMultiSelect label,
        .stDateInput label,
        .stTimeInput label,
        .stFileUploader label {
            color: #ffffff !important;
        }
        
        /* Input fields */
        .stTextInput input,
        .stNumberInput input,
        .stTextArea textarea {
            background: #25253d !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            color: #ffffff !important;
            border-radius: 8px !important;
        }
        
        .stTextInput input::placeholder,
        .stNumberInput input::placeholder,
        .stTextArea textarea::placeholder {
            color: #8888a8 !important;
        }
        
        /* Select boxes */
        .stSelectbox > div > div {
            background: #25253d !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            color: #ffffff !important;
        }
        
        /* ============================================
           BUTTONS
           ============================================ */
        
        .stButton > button,
        .stFormSubmitButton > button {
            background: #7c3aed !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
        }
        
        .stButton > button:hover,
        .stFormSubmitButton > button:hover {
            background: #8b5cf6 !important;
        }
        
        /* ============================================
           FORMS
           ============================================ */
        
        [data-testid="stForm"] {
            background: #2d2d4a !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            border-radius: 12px !important;
            padding: 1.5rem !important;
        }
        
        /* ============================================
           METRICS
           ============================================ */
        
        [data-testid="stMetric"] {
            background: #2d2d4a !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            border-radius: 12px !important;
            padding: 1rem !important;
        }
        
        [data-testid="stMetric"] label {
            color: #8888a8 !important;
            text-transform: uppercase !important;
            font-size: 0.75rem !important;
        }
        
        [data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: #ffffff !important;
            font-weight: 700 !important;
            font-size: 1.5rem !important;
        }
        
        /* ============================================
           ALERTS
           ============================================ */
        
        .stAlert {
            border-radius: 8px !important;
        }
        
        /* ============================================
           HORIZONTAL RULE
           ============================================ */
        
        hr {
            border-color: rgba(255, 255, 255, 0.1) !important;
        }
        
        /* ============================================
           HIDE STREAMLIT BRANDING & FORM HINTS
           ============================================ */
        
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* Hide Deploy button only, keep collapse working */
        [data-testid="stHeader"] {
            background: transparent !important;
        }
        
        /* Hide only the deploy button text/link */
        [data-testid="stHeader"] [data-testid="stDecoration"],
        [data-testid="stHeader"] a {
            display: none !important;
        }
        
        /* Ensure sidebar collapse button stays visible and functional */
        [data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] {
            display: flex !important;
            visibility: visible !important;
        }
        
        /* When collapsed, show expand button */
        [data-testid="stSidebarCollapsedControl"] {
            display: flex !important;
            visibility: visible !important;
        }
        
        /* Hide "Press Enter to submit" form hint */
        .stForm [data-testid="stFormSubmitButton"] + div {
            display: none !important;
        }
        
        /* Alternative selector for form hint */
        .stForm small {
            display: none !important;
        }
    </style>
    """


def apply_theme():
    st.markdown(get_theme_css(), unsafe_allow_html=True)


def init_session_state():
    pass
