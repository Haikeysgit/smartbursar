"""
=============================================================================
SmartBursar - Messages Page
=============================================================================
View message history and send test reminders.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.theme import apply_theme, init_session_state
from config.database import get_db_context
from models.student import Student
from models.school import School
from models.message_log import MessageLog, MessageStatus


# =============================================================================
# Page Config
# =============================================================================

st.set_page_config(
    page_title="Messages - SmartBursar",
    page_icon="SB",
    layout="wide",
)

init_session_state()
apply_theme()


# =============================================================================
# Security
# =============================================================================

def check_access():
    if "role" not in st.session_state:
        st.error("Please login first")
        st.stop()
    
    if st.session_state.get("role") == "SUPER_ADMIN" and not st.session_state.get("impersonating"):
        st.warning("Please select a school from God Mode")
        st.stop()
    
    if not st.session_state.get("school_id"):
        st.error("No school assigned")
        st.stop()


check_access()
school_id = st.session_state.get("school_id")


# =============================================================================
# Header
# =============================================================================

st.title("Messages")

with get_db_context() as db:
    school = db.query(School).filter(School.id == school_id).first()
    if school:
        st.caption(f"{school.school_name} - SmartBursar")

st.markdown("---")


# =============================================================================
# Statistics
# =============================================================================

st.subheader("Delivery Statistics (Last 30 Days)")

with get_db_context() as db:
    cutoff = datetime.now() - timedelta(days=30)
    messages = db.query(MessageLog).filter(
        MessageLog.school_id == school_id,
        MessageLog.sent_at >= cutoff,
    ).all()
    
    total = len(messages)
    delivered = sum(1 for m in messages if m.status == MessageStatus.DELIVERED)
    read = sum(1 for m in messages if m.status == MessageStatus.READ)
    failed = sum(1 for m in messages if m.status == MessageStatus.FAILED)
    cost = sum(float(m.cost) for m in messages)

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Total Sent", f"{total}")
with col2:
    st.metric("Delivered", f"{delivered}")
with col3:
    st.metric("Read", f"{read}")
with col4:
    st.metric("Failed", f"{failed}")
with col5:
    st.metric("Total Cost", f"N{cost:,.2f}")

st.markdown("---")


# =============================================================================
# Message History
# =============================================================================

st.subheader("Recent Messages")

with get_db_context() as db:
    recent = db.query(MessageLog).filter(
        MessageLog.school_id == school_id,
    ).order_by(MessageLog.sent_at.desc()).limit(50).all()
    
    if not recent:
        st.info("No messages sent yet")
        msg_data = []
    else:
        msg_data = []
        for m in recent:
            student = m.student
            msg_data.append({
                "sent_at": m.sent_at,
                "student": student.full_name if student else "Unknown",
                "channel": m.channel,
                "type": m.message_type,
                "status": m.status,
                "cost": float(m.cost),
            })

if msg_data:
    display = []
    for m in msg_data:
        display.append({
            "Date": m["sent_at"].strftime("%Y-%m-%d %H:%M"),
            "Student": m["student"],
            "Channel": m["channel"],
            "Type": m["type"],
            "Status": m["status"],
            "Cost": f"N{m['cost']:.2f}",
        })
    
    df = pd.DataFrame(display)
    st.dataframe(df, use_container_width=True, hide_index=True)

st.markdown("---")


# =============================================================================
# Test Message
# =============================================================================

st.subheader("Send Test Message")

st.info("Schedule: 7:00 AM WAT | Phase 1 (before mid-term): Mondays | Phase 2 (after mid-term): Mon + Thu | 14-day grace after term start")

with get_db_context() as db:
    students = db.query(Student).filter(
        Student.school_id == school_id,
        Student.fees_total_due > Student.amount_paid,
    ).order_by(Student.full_name).all()
    
    opts = {f"{s.full_name} - N{int(s.balance):,}": s.id for s in students}

if opts:
    sel = st.selectbox("Select student to send reminder", options=list(opts.keys()))
    
    if st.button("Send Test Reminder", use_container_width=True):
        student_id = opts[sel]
        from services.scheduler.reminder_engine import send_test_reminder
        
        with get_db_context() as db2:
            log = send_test_reminder(db2, student_id, school_id)
            if log:
                st.success("Test message sent! Check your terminal output.")
            else:
                st.error("Failed to send test message")
else:
    st.warning("No students with outstanding balances to send reminders to.")
