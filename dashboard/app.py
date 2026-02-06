"""
=============================================================================
SmartBursar - Streamlit Dashboard
=============================================================================
Turn Debts Into Alerts - School Fee Recovery System
"""

import streamlit as st
import base64
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, date

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.theme import apply_theme, init_session_state
from config.database import get_db_context
from models import User, School, FeeStructure


# =============================================================================
# Page Config
# =============================================================================

st.set_page_config(
    page_title="SmartBursar",
    page_icon="SB",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session_state()
apply_theme()


# =============================================================================
# Session Persistence using localStorage (via Streamlit JS injection)
# =============================================================================

import streamlit.components.v1 as components
import hmac
import hashlib

# Get secret key for signing
from config.settings import settings
SESSION_SECRET = settings.SECRET_KEY


def create_signed_session(user_data: dict) -> str:
    """Create HMAC-signed session token with expiration."""
    import base64
    # Add expiration (24 hours from now)
    payload = {
        **user_data,
        "exp": (datetime.now() + timedelta(hours=24)).isoformat()
    }
    payload_json = json.dumps(payload)
    # Create HMAC signature
    signature = hmac.new(
        SESSION_SECRET.encode(),
        payload_json.encode(),
        hashlib.sha256
    ).hexdigest()
    # Combine payload and signature
    token = base64.b64encode(f"{payload_json}|{signature}".encode()).decode()
    return token


def verify_signed_session(token: str) -> dict | None:
    """Verify HMAC signature and expiration of session token."""
    import base64
    try:
        decoded = base64.b64decode(token).decode()
        payload_json, signature = decoded.rsplit("|", 1)
        
        # Verify signature
        expected = hmac.new(
            SESSION_SECRET.encode(),
            payload_json.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected):
            return None  # Tampered!
        
        payload = json.loads(payload_json)
        
        # Check expiration
        exp = datetime.fromisoformat(payload.get("exp", "2000-01-01"))
        if datetime.now() > exp:
            return None  # Expired
        
        return payload
    except Exception:
        return None


def save_session_to_storage(user_data: dict):
    """Save SIGNED user session to browser localStorage."""
    token = create_signed_session(user_data)
    components.html(
        f"""
        <script>
            localStorage.setItem('smartbursar_session', '{token}');
        </script>
        """,
        height=0,
        width=0,
    )

def clear_session_storage():
    """Clear all session data from browser storage and force logout."""
    components.html(
        """
        <script>
            // 1. Clear localStorage
            localStorage.removeItem('smartbursar_session');
            localStorage.clear();
            
            // 2. Clear sessionStorage
            sessionStorage.clear();
            
            // 3. Clear cookies (set to expire immediately)
            document.cookie.split(";").forEach(function(c) { 
                document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/"); 
            });
            
            // 4. Clear URL query params and force redirect
            const url = new URL(window.parent.location.href);
            url.searchParams.delete('session');
            window.parent.location.href = url.origin + url.pathname;
        </script>
        """,
        height=0,
        width=0,
    )

# SESSION RECOVERY HOOK: Source of truth for persistence
# 1. Try to get token from query params (Streamlit native)
query_params = st.query_params
session_token = query_params.get("session", None)

# 2. If no query param, try to recover from localStorage via JS "Bridge"
if "role" not in st.session_state and not session_token:
    components.html(
        """
        <script>
            const token = localStorage.getItem('smartbursar_session');
            if (token) {
                const url = new URL(window.location.href);
                url.searchParams.set('session', token);
                window.parent.location.href = url.href;
            }
        </script>
        """,
        height=0,
    )

# 3. Verify token if present
if "role" not in st.session_state and session_token:
    session_data = verify_signed_session(session_token)
    if session_data and "user_id" in session_data:
        with get_db_context() as db:
            user = db.query(User).filter(
                User.id == session_data["user_id"],
                User.is_active == True
            ).first()
            
            if user:
                st.session_state["user_id"] = user.id
                st.session_state["email"] = user.email
                st.session_state["role"] = user.role
                st.session_state["school_id"] = user.school_id
                st.session_state["last_activity"] = datetime.now()
                # DO NOT clear query params here, they are our backup on refresh!

# 4. If logged in but query param is missing, sync it (Ensures NEXT refresh works)
if "role" in st.session_state and not session_token:
    # We need the token to sync to the URL
    with get_db_context() as db:
        user_info = {
            "user_id": st.session_state["user_id"],
            "email": st.session_state["email"],
            "role": st.session_state["role"],
            "school_id": st.session_state["school_id"]
        }
        token = create_signed_session(user_info)
        st.query_params["session"] = token


# =============================================================================
# Logo Helper
# =============================================================================

def get_logo_base64():
    """Get logo as base64 for embedding."""
    logo_path = Path(__file__).parent / "assets" / "logo.png"
    if logo_path.exists():
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None


# =============================================================================
# Authentication & Bootstrap
# =============================================================================

def bootstrap_admin():
    """Auto-create or reset default admin. Does NOT auto-create schools."""
    with get_db_context() as db:
        # 1. SUPER ADMIN (admin@school.com)
        admin = db.query(User).filter(User.email == "admin@school.com").first()
        if not admin:
            # Create Super Admin WITHOUT auto-creating a test school
            # Super Admins don't need a school_id - they have access to all schools
            admin = User(
                email="admin@school.com",
                role="SUPER_ADMIN",
                school_id=None,  # Super Admin doesn't need a specific school
                is_active=True
            )
            admin.set_password("password123")
            db.add(admin)
            print("Status: Created Super Admin (without test school)")
        else:
            # Login successful, no forced reset needed.
            print("Status: Admin Exists (No Reset)")
            pass
        
        # NOTE: Schools are no longer auto-created on startup.
        # Deleting a school from the dashboard is now permanent.
            
        db.commit()
        return True
    return False

# Run bootstrap check once on script load
try:
    if bootstrap_admin():
        pass # Admin created silently
except Exception:
    pass # Database might not be ready, skip

# =============================================================================
# Authentication
# =============================================================================

def check_login(email: str, password: str):
    with get_db_context() as db:
        user = db.query(User).filter(
            User.email == email.lower().strip(),
            User.is_active == True,
        ).first()
        
        if user and user.check_password(password):
            return {
                "user_id": user.id,
                "email": user.email,
                "role": user.role,
                "school_id": user.school_id,
            }
    return None


# =============================================================================
# Main App
# =============================================================================

if "role" not in st.session_state:
    # ==========================================================================
    # PROFESSIONAL LANDING PAGE - Split Layout with Dark Purple Theme
    # ==========================================================================
    
    # Two-column split layout
    col_hero, col_login = st.columns([1.2, 1], gap="large")
    
    # --------------------------------------------------------------------------
    # LEFT COLUMN: Hero Section
    # --------------------------------------------------------------------------
    with col_hero:
        # SmartBursar Logo/Brand
        st.markdown("""
        <div style="margin-bottom: 2rem;">
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 2rem;">
                <div style="
                    width: 44px; 
                    height: 44px; 
                    background: linear-gradient(135deg, #7c3aed 0%, #8b5cf6 100%); 
                    border-radius: 10px; 
                    display: flex; 
                    align-items: center; 
                    justify-content: center; 
                    color: white; 
                    font-weight: 800; 
                    font-size: 22px;
                    box-shadow: 0 4px 15px rgba(124, 58, 237, 0.4);
                ">S</div>
                <span style="font-size: 1.5rem; font-weight: 700; color: #ffffff;">SmartBursar</span>
            </div>
            <h1 style="
                font-size: 2.5rem; 
                font-weight: 800; 
                color: #ffffff; 
                line-height: 1.15; 
                margin: 0 0 1rem 0;
                letter-spacing: -0.02em;
            ">
                Automated Fee<br>
                <span style="color: #8b5cf6;">Collection</span> System.
            </h1>
            <p style="
                font-size: 1rem; 
                color: #b8b8d1; 
                line-height: 1.6; 
                margin: 0 0 1.5rem 0;
                max-width: 380px;
            ">
                From overdue payments to instant alerts. The complete financial dashboard for modern schools.
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # Feature Highlights - Using Unicode checkmarks instead of SVGs
        st.markdown("""
        <div style="display: flex; flex-direction: column; gap: 0.8rem;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <div style="width: 28px; height: 28px; background: rgba(124, 58, 237, 0.15); border-radius: 6px; display: flex; align-items: center; justify-content: center;">
                    <span style="color: #8b5cf6; font-size: 14px; font-weight: bold;">✓</span>
                </div>
                <span style="color: #ffffff; font-size: 0.95rem;">Instant Payment Tracking</span>
            </div>
            <div style="display: flex; align-items: center; gap: 10px;">
                <div style="width: 28px; height: 28px; background: rgba(124, 58, 237, 0.15); border-radius: 6px; display: flex; align-items: center; justify-content: center;">
                    <span style="color: #8b5cf6; font-size: 14px; font-weight: bold;">✓</span>
                </div>
                <span style="color: #ffffff; font-size: 0.95rem;">Automated WhatsApp Alerts</span>
            </div>
            <div style="display: flex; align-items: center; gap: 10px;">
                <div style="width: 28px; height: 28px; background: rgba(124, 58, 237, 0.15); border-radius: 6px; display: flex; align-items: center; justify-content: center;">
                    <span style="color: #8b5cf6; font-size: 14px; font-weight: bold;">✓</span>
                </div>
                <span style="color: #ffffff; font-size: 0.95rem;">Real-time Debtor Reports</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # WhatsApp Contact Button with hover effect
        st.markdown("""
        <style>
            .whatsapp-btn {
                display: inline-flex !important;
                align-items: center !important;
                gap: 10px !important;
                background: linear-gradient(135deg, #25D366 0%, #128C7E 100%) !important;
                color: white !important;
                padding: 0.8rem 1.5rem !important;
                border-radius: 10px !important;
                font-weight: 600 !important;
                font-size: 0.95rem !important;
                box-shadow: 0 4px 15px rgba(37, 211, 102, 0.3) !important;
                transition: transform 0.2s ease, box-shadow 0.2s ease !important;
                text-decoration: none !important;
            }
            .whatsapp-btn:hover {
                transform: translateY(-3px) !important;
                box-shadow: 0 8px 25px rgba(37, 211, 102, 0.5) !important;
                color: white !important;
                text-decoration: none !important;
            }
            .whatsapp-btn:visited, .whatsapp-btn:active, .whatsapp-btn:focus {
                color: white !important;
                text-decoration: none !important;
            }

            /* STANDARD LAYOUT RESTORATION */
            /* Default padding adjustments only */
            .block-container {
                padding-top: 2rem !important;
                padding-bottom: 3rem !important;
                max-width: 100% !important;
            }
            
            /* CUSTOM GRADIENT DIVIDER */
            hr {
                margin: 2em 0;
                border: 0;
                height: 1px;
                background-image: linear-gradient(to right, rgba(0, 0, 0, 0), rgba(124, 58, 237, 0.5), rgba(0, 0, 0, 0));
            }
            
            /* GLOBAL TEXT COLOR FIX */
            p, h1, h2, h3, span, div, label {
                color: #e2e8f0 !important;
            }
            
            /* INPUT FIELDS: Modern Dark Theme */
            .stTextInput > div > div > input {
                background-color: #1e293b !important;
                color: #f8fafc !important;
                border: 1px solid #334155 !important;
                border-radius: 8px !important;
                padding: 10px 12px !important;
            }
            .stTextInput > div > div > input:focus {
                border-color: #7c3aed !important;
                box-shadow: 0 0 0 1px #7c3aed !important;
            }
            
            /* BUTTONS: Primary Action Color */
            .stButton > button {
                background-color: #7c3aed !important;
                color: white !important;
                border: none !important;
                border-radius: 8px !important;
                font-weight: 600 !important;
                padding: 0.5rem 1rem !important;
                transition: all 0.2s ease !important;
            }
            .stButton > button:hover {
                background-color: #6d28d9 !important;
                transform: translateY(-1px);
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            }
        </style>
        <div style="margin-top: 2rem;">
            <a href="https://wa.me/2348038004334?text=Hi, I'd like to learn more about SmartBursar" target="_blank" class="whatsapp-btn">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
                    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
                </svg>
                Get in touch with SmartBursar admin
            </a>
        </div>
        """, unsafe_allow_html=True)
    
    # --------------------------------------------------------------------------
    # RIGHT COLUMN: Login Card
    # --------------------------------------------------------------------------
    with col_login:
        # Login Card Header - Compact
        st.markdown("""
        <div style="margin-bottom: 0.5rem;">
            <h2 style="
                font-size: 1.2rem; 
                font-weight: 700; 
                color: #ffffff; 
                margin: 0 0 0.2rem 0;
            ">Client Portal Login</h2>
            <p style="
                color: #8888a8; 
                font-size: 0.85rem; 
                margin: 0;
            ">Access your school dashboard</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Login Form
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="Enter your email")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submit = st.form_submit_button("Sign In", use_container_width=True)
            
            if submit:
                # Run bootstrap lightly (only creates if missing)
                try:
                     bootstrap_admin()
                except Exception:
                    pass  # Fail silent now that it works

                # SECURITY: Rate limiting to prevent brute force attacks
                from datetime import datetime, timedelta
                
                if "login_attempts" not in st.session_state:
                    st.session_state["login_attempts"] = 0
                    st.session_state["lockout_until"] = None
                
                # Check if locked out
                if st.session_state["lockout_until"]:
                    if datetime.now() < st.session_state["lockout_until"]:
                        remaining = (st.session_state["lockout_until"] - datetime.now()).seconds
                        st.error(f"Too many failed attempts. Please wait {remaining // 60} minutes.")
                        st.stop()
                    else:
                        # Lockout expired, reset
                        st.session_state["login_attempts"] = 0
                        st.session_state["lockout_until"] = None
                
                if not email or not password:
                    st.error("Please enter both email and password")
                else:
                    user_info = check_login(email, password)
                    if user_info:
                        # Successful login - reset attempts
                        st.session_state["login_attempts"] = 0
                        st.session_state["lockout_until"] = None
                        st.session_state["user_id"] = user_info["user_id"]
                        st.session_state["email"] = user_info["email"]
                        st.session_state["role"] = user_info["role"]
                        st.session_state["school_id"] = user_info["school_id"]
                        st.session_state["impersonating"] = False
                        st.session_state["login_time"] = datetime.now()  # For session timeout
                        
                        # Save session to localStorage for persistence across refreshes
                        save_session_to_storage(user_info)
                        
                        st.rerun()
                    else:
                        # Failed login - increment counter
                        st.session_state["login_attempts"] += 1
                        if st.session_state["login_attempts"] >= 5:
                            st.session_state["lockout_until"] = datetime.now() + timedelta(minutes=5)
                            st.error("Too many failed attempts. Locked for 5 minutes.")
                        else:
                            remaining = 5 - st.session_state["login_attempts"]
                            st.error(f"Invalid email or password. {remaining} attempts remaining.")

        # Contact Info (no credentials shown for security)
        st.markdown("""
        <div style="
            background: rgba(124, 58, 237, 0.08);
            border: 1px solid rgba(124, 58, 237, 0.2);
            border-radius: 10px;
            padding: 1rem;
            margin-top: 1rem;
        ">
            <p style="margin: 0; font-size: 0.85rem; color: #b8b8d1;">
                <strong style="color: #8b5cf6;">Need access?</strong> Contact your school administrator or SmartBursar support.
            </p>
        </div>
        """, unsafe_allow_html=True)

    # ==========================================================================
    # FULL WIDTH FOOTER (Outside Columns)
    # ==========================================================================
    st.markdown("""
        <div style="
            width: 100%;
            text-align: center;
            margin-top: 5rem;
            padding: 2rem 0;
            border-top: 1px solid rgba(255,255,255,0.05);
            color: #888888;
            font-size: 0.75rem;
            font-family: 'Source Sans Pro', sans-serif;
        ">
            <p style="margin-bottom: 0.8rem;">
                © 2026 SMARTBURS TECHNOLOGIES. All Rights Reserved.
            </p>
            <div style="
                display: flex; 
                justify-content: center; 
                gap: 1.5rem; 
                margin-bottom: 0.8rem;
            ">
                <a href="#" style="color: #888888; text-decoration: none; transition: color 0.3s;">Privacy Policy</a>
                <span style="color: #444;">|</span>
                <a href="#" style="color: #888888; text-decoration: none; transition: color 0.3s;">Terms of Use</a>
            </div>
            <div style="
                display: flex; 
                justify-content: center; 
                gap: 1.2rem;
                align-items: center;
            ">
                <a href="https://x.com/smartbursar" target="_blank" style="color: #888888; text-decoration: none; font-size: 1.1rem;">𝕏</a>
                <a href="mailto:smartbursar@gmail.com" style="color: #888888; text-decoration: none;">Contact Support</a>
            </div>
        </div>
    """, unsafe_allow_html=True)





else:
    # =========================================================================
    # SECURITY: Session Timeout (Prevents "Zombie" Sessions)
    # =========================================================================
    from datetime import datetime, timedelta
    
    if "login_time" in st.session_state:
        session_duration = datetime.now() - st.session_state["login_time"]
        if session_duration > timedelta(hours=2):
            # Session expired - force logout
            st.session_state.clear()
            st.warning("Your session has expired. Please log in again.")
            st.rerun()
    
    # LOGGED IN - SHOW SIDEBAR
    with st.sidebar:
        # Title (no logo)
        st.markdown("### SmartBursar")
        
        st.markdown(f"**{st.session_state.get('email', '')}**")
        
        role = st.session_state.get("role", "SCHOOL_ADMIN")
        
        if role == "SUPER_ADMIN" and not st.session_state.get("impersonating"):
            st.caption("Super Admin")
        elif st.session_state.get("impersonating"):
            # Show which school is being viewed
            school_id = st.session_state.get("school_id")
            if school_id:
                with get_db_context() as db:
                    school = db.query(School).filter(School.id == school_id).first()
                    if school:
                        st.success(f"Viewing: {school.school_name}")
            st.caption("Impersonating School Admin")
            if st.button("Exit School View", use_container_width=True, type="primary"):
                st.session_state["school_id"] = st.session_state.get("original_school_id")
                st.session_state["impersonating"] = False
                st.rerun()
        


        else:
            # School Admin - Show Plan Status
            st.caption("School Admin")
            
            school_id = st.session_state.get("school_id")
            if school_id:
                with get_db_context() as db:
                    from models.student import Student
                    school = db.query(School).filter(School.id == school_id).first()
                    if school:
                        debtor_count = db.query(Student).filter(
                            Student.school_id == school_id,
                            Student.fees_total_due > Student.amount_paid
                        ).count()
                        
                        limit = getattr(school, 'debtor_limit', 150)
                        
                        # Plan Status with color
                        if debtor_count <= limit:
                            st.markdown(
                                f'<div style="padding: 8px; background: rgba(34, 197, 94, 0.2); border-radius: 8px; margin: 10px 0;">'
                                f'<span style="color: #22c55e;">Active Debtors: {debtor_count}/{limit}</span></div>',
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown(
                                f'<div style="padding: 8px; background: rgba(239, 68, 68, 0.2); border-radius: 8px; margin: 10px 0;">'
                                f'<span style="color: #ef4444;">Active Debtors: {debtor_count}/{limit} - Over Limit</span></div>',
                                unsafe_allow_html=True
                            )
        
        st.markdown("---")
        st.markdown("**Navigation**")
        
        if role == "SUPER_ADMIN" and not st.session_state.get("impersonating"):
            # Super Admin sees everything
            st.page_link("app.py", label="Home")
            st.page_link("pages/06_admin.py", label="Admin Panel")
        else:
            # School Admin sees only their pages (no super admin)
            st.page_link("app.py", label="Home")
            st.page_link("pages/02_students.py", label="Students")
            st.page_link("pages/03_payments.py", label="Payments")
            st.page_link("pages/04_messages.py", label="Messages")
            st.page_link("pages/05_settings.py", label="Settings")
        
        st.markdown("---")
        
        if st.button("Sign Out", use_container_width=True):
            # NUKE & REDIRECT: Clear everything and force redirect
            
            # 1. Clear ALL Streamlit session state
            st.session_state.clear()
            
            # 2. Clear query params
            st.query_params.clear()
            
            # 3. Nuclear option: Clear browser storage + hard redirect to root
            components.html(
                """
                <script>
                    // NUKE ALL STORAGE
                    localStorage.clear();
                    sessionStorage.clear();
                    
                    // Clear all cookies
                    document.cookie.split(";").forEach(function(c) { 
                        document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/"); 
                    });
                    
                    // HARD REDIRECT - forces full page reload with clean state
                    window.parent.location.replace(window.parent.location.origin);
                </script>
                """,
                height=0,
                width=0,
            )
    
    
    # MAIN CONTENT
    role = st.session_state.get("role", "SCHOOL_ADMIN")
    
    if role == "SUPER_ADMIN" and not st.session_state.get("impersonating"):
        # SUPER ADMIN DASHBOARD
        st.title("SmartBursar Admin")
        st.caption("Platform Overview - Turn Debts Into Alerts")
        
        with get_db_context() as db:
            from models.student import Student
            schools = db.query(School).all()
            active = sum(1 for s in schools if s.is_active)
            expiring = sum(1 for s in schools if 0 <= s.days_remaining <= 7)
            # Calculate term revenue: N150,000 base + N500 per extra debtor
            term_revenue = 0
            for school in schools:
                if school.is_active:
                    debtor_count = db.query(Student).filter(
                        Student.school_id == school.id,
                        Student.fees_total_due > Student.amount_paid
                    ).count()
                    limit = getattr(school, 'debtor_limit', 150)
                    
                    base = 150000  # N150,000 per term
                    overage = max(0, debtor_count - limit) * 500  # N500 per extra debtor
                    term_revenue += base + overage
            
            total_students = db.query(Student).count()
            
            # Check for over-limit schools
            over_limit_schools = []
            for school in schools:
                debtor_count = db.query(Student).filter(
                    Student.school_id == school.id,
                    Student.fees_total_due > Student.amount_paid
                ).count()
                limit = getattr(school, 'debtor_limit', 150)
                if debtor_count > limit:
                    extra = debtor_count - limit
                    extra_cost = extra * 500
                    over_limit_schools.append({
                        "name": school.school_name,
                        "count": debtor_count,
                        "limit": limit,
                        "extra_cost": extra_cost,
                    })
        
        st.markdown("---")
        
        # Over-limit alerts with pricing
        if over_limit_schools:
            st.error(f"**Fair Usage Alerts:** {len(over_limit_schools)} school(s) over limit")
            for s in over_limit_schools:
                st.warning(f"{s['name']}: {s['count']}/{s['limit']} debtors (+N{s['extra_cost']:,} overage)")
            st.markdown("---")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Term Revenue", f"N{int(term_revenue):,}")
        with col2:
            st.metric("Active Schools", f"{active}")
        with col3:
            st.metric("Total Students", f"{total_students}")
        with col4:
            st.metric("Expiring Soon", f"{expiring}")
        
        st.markdown("---")
        st.info("Go to **God Mode** in the sidebar for full school management")
    
    else:
        # SCHOOL ADMIN DASHBOARD
        school_id = st.session_state.get("school_id")
        
        if not school_id:
            st.error("No school assigned")
        else:
            with get_db_context() as db:
                school = db.query(School).filter(School.id == school_id).first()
                
                if not school:
                    st.error("School not found")
                else:
                    st.title(school.school_name)
                    st.caption("SmartBursar Dashboard - Turn Debts Into Alerts")
                    
                    from models.student import Student
                    from models.transaction import Transaction, TransactionStatus
                    
                    students = db.query(Student).filter(Student.school_id == school_id).all()
                    
                    total = len(students)
                    owing = sum(1 for s in students if s.balance > 0)
                    outstanding = sum(s.balance for s in students if s.balance > 0)
                    collected = sum(s.amount_paid for s in students)
                    
                    pending = db.query(Transaction).join(Student).filter(
                        Student.school_id == school_id,
                        Transaction.status == TransactionStatus.PENDING,
                    ).count()
            
            st.markdown("---")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Students", f"{total}")
            with col2:
                st.metric("Still Owing", f"{owing}")
            with col3:
                st.metric("Outstanding", f"N{int(outstanding):,}")
            with col4:
                st.metric("Collected", f"N{int(collected):,}")
            
            st.markdown("---")
            
            if pending > 0:
                st.warning(f"You have {pending} payments awaiting verification")
                
                # Fetch pending transactions for quick action
                from services.payments.payment_recorder import verify_payment, reject_payment
                
                pending_txns = db.query(Transaction).join(Student).filter(
                    Student.school_id == school_id,
                    Transaction.status == TransactionStatus.PENDING,
                ).order_by(Transaction.date.desc()).limit(5).all()
                
                user_id = st.session_state.get("user_id")
                
                for txn in pending_txns:
                    with st.expander(f"Verify: {txn.student.full_name} - N{int(txn.amount):,}", expanded=True):
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("Approve", key=f"dash_verify_{txn.id}", use_container_width=True):
                                verify_payment(db, txn.id, school_id, user_id)
                                st.success("Verified!")
                                st.rerun()
                        with c2:
                            if st.button("Reject", key=f"dash_reject_{txn.id}", use_container_width=True):
                                reject_payment(db, txn.id, school_id, user_id, "Rejected from Dashboard")
                                st.warning("Rejected.")
                                st.rerun()
                
                if pending > 5:
                    if st.button("View All Pending Payments"):
                        st.switch_page("pages/03_payments.py")
            
            # Check for overpaid students - Flag for refund (using raw SQL to avoid ORM cache issues)
            from sqlalchemy import text
            with get_db_context() as db:
                result = db.execute(text("""
                    SELECT id, full_name, class_level, amount_paid, fees_total_due, parent_name, parent_phone_primary
                    FROM students 
                    WHERE school_id = :school_id 
                    AND amount_paid > fees_total_due 
                    AND (refund_processed IS NULL OR refund_processed = FALSE)
                """), {"school_id": school_id})
                
                overpaid_data = []
                for row in result:
                    overpaid_data.append({
                        "id": row[0],
                        "name": row[1],
                        "class": row[2],
                        "overpayment": float(row[3]) - float(row[4]),
                        "parent": row[5],
                        "phone": row[6],
                    })
            
            if overpaid_data:
                st.error(f"**Refund Required:** {len(overpaid_data)} student(s) have overpaid")
                for s in overpaid_data:
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.info(f"**{s['name']}** ({s['class']}) - Overpaid by **N{int(s['overpayment']):,}**. Parent: {s['parent']} ({s['phone']})")
                    with col2:
                        if st.button("Mark Refunded", key=f"refund_{s['id']}", use_container_width=True):
                            with get_db_context() as db:
                                # Set refund_processed AND reset amount_paid to match fees_total_due
                                db.execute(
                                    text("UPDATE students SET refund_processed = TRUE, amount_paid = fees_total_due WHERE id = :sid"),
                                    {"sid": s['id']}
                                )
                                db.commit()
                            st.rerun()
            
            st.subheader("Quick Actions")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("View Students", use_container_width=True):
                    st.switch_page("pages/02_students.py")
            with col2:
                if st.button("Log Payment", use_container_width=True):
                    st.switch_page("pages/03_payments.py")
            with col3:
                if st.button("Send Reminders", use_container_width=True):
                    st.switch_page("pages/04_messages.py")
            
            st.markdown("---")
            st.subheader("Top 10 Owing Students")
            
            with get_db_context() as db:
                from models.student import Student
                top = db.query(Student).filter(
                    Student.school_id == school_id,
                    Student.fees_total_due > Student.amount_paid,
                ).order_by(
                    (Student.fees_total_due - Student.amount_paid).desc()
                ).limit(10).all()
                
                if top:
                    import pandas as pd
                    data = [{
                        "Student": s.full_name,
                        "Class": s.class_level,
                        "Parent": s.parent_name,
                        "Balance": f"N{int(s.balance):,}",
                        "Status": s.payment_status,
                    } for s in top]
                    
                    df = pd.DataFrame(data)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.success("All students are fully paid!")
