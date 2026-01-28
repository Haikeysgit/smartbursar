import streamlit as st
import pandas as pd
import os
import plotly.express as px
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, desc
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="SmartBursar Admin", page_icon="🏫", layout="wide")

# Auth Secrets
ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL", "admin@school.com")
ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "admin")

# Database Connection
from config.database import get_db, engine
from models.student import Student
from models.transaction import Transaction, TransactionStatus
from models.school import School

# --- AUTHENTICATION ---
def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["username"] == ADMIN_EMAIL and st.session_state["password"] == ADMIN_PASSWORD:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
            del st.session_state["username"]
        else:
            import time
            time.sleep(3)  # Anti-Brute Force Delay
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show inputs
        st.text_input("Username", key="username")
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error
        st.text_input("Username", key="username")
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.error("😕 User not known or password incorrect")
        return False
    else:
        # Password correct
        return True

if not check_password():
    st.stop()

# --- MAIN APP ---
st.title("🏫 SmartBursar Admin Dashboard")

# Tabs
tab1, tab2, tab3 = st.tabs(["💰 Transactions", "🎓 Students", "⚙️ System"])

# --- TAB 1: TRANSACTIONS ---
with tab1:
    st.header("Recent Transactions")
    
    with Session(engine) as db:
        txns = db.query(Transaction).order_by(desc(Transaction.created_at)).limit(50).all()
        
        if not txns:
            st.info("No transactions found.")
        else:
            data = []
            for t in txns:
                data.append({
                    "ID": t.id,
                    "Date": t.created_at,
                    "Student": t.student.full_name if t.student else "Unknown",
                    "Amount": f"₦{t.amount:,.2f}",
                    "Status": t.status.value,
                    "Confidence": f"{t.confidence_score}%",
                    "Method": t.payment_method.value
                })
            
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
            
            # Metrics
            total_collected = db.query(Transaction).filter(Transaction.status == TransactionStatus.VERIFIED).with_entities(Transaction.amount).all()
            total_val = sum([t.amount for t in total_collected])
            st.metric("Total Collected (Verified)", f"₦{total_val:,.2f}")

# --- TAB 2: STUDENTS ---
with tab2:
    st.header("Student Registry")
    
    with Session(engine) as db:
        students = db.query(Student).all()
        
        if not students:
            st.info("No students registered.")
        else:
            s_data = []
            for s in students:
                s_data.append({
                    "Name": s.full_name,
                    "Class": s.class_level,
                    "Parent": s.parent_name,
                    "Phone": s.parent_phone_primary,
                    "Due": f"₦{s.fees_total_due:,.2f}",
                    "Paid": f"₦{s.amount_paid:,.2f}",
                    "Balance": f"₦{s.balance:,.2f}"
                })
            
            st_df = pd.DataFrame(s_data)
            st.dataframe(st_df, use_container_width=True)

# --- TAB 3: SYSTEM ---
with tab3:
    st.header("System Status")
    st.success(f"✅ Database Connected: {engine.url.database}")
    
    st.subheader("Environment Check")
    req_vars = ["GROQ_API_KEY", "WHATSAPP_TOKEN", "DATABASE_URL"]
    for var in req_vars:
        val = os.getenv(var)
        if val:
            st.caption(f"✅ {var} is set")
        else:
            st.error(f"❌ {var} is MISSING")

    if st.button("Refresh Data"):
        st.rerun()
