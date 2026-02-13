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

# Debug / Environment Status
from config.settings import settings
import os

env = os.getenv("ENVIRONMENT", "development")
is_mock = settings.MOCK_MODE

# Only show warning if in mock mode (for admin debugging)
if is_mock:
    st.error(f"⚠️ MOCK MODE - Messages will NOT be sent to phones.")
    st.caption("To fix: Set ENVIRONMENT=production in Render.")


st.title("Messages")

with get_db_context() as db:
    school = db.query(School).filter(School.id == school_id).first()
    if school:
        st.caption(f"{school.school_name} - SmartBursar")

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
        is_super = st.session_state.get("role") == "SUPER_ADMIN"
        for m in recent:
            student = m.student
            item = {
                "sent_at": m.sent_at,
                "student": student.full_name if student else "Unknown",
                "channel": m.channel,
                "type": m.message_type,
                "status": m.status,
            }
            if is_super:
                item["cost"] = float(m.cost)
            msg_data.append(item)

if msg_data:
    display = []
    is_super = st.session_state.get("role") == "SUPER_ADMIN"
    for m in msg_data:
        row = {
            "Date": m["sent_at"].strftime("%Y-%m-%d %H:%M"),
            "Student": m["student"],
            "Channel": m["channel"],
            "Type": m["type"],
            "Status": m["status"],
        }
        if is_super:
            row["Cost"] = f"N{m['cost']:.2f}"
        display.append(row)
    
    df = pd.DataFrame(display)
    st.dataframe(df, use_container_width=True, hide_index=True)

st.markdown("---")


# =============================================================================
# Test Message
# =============================================================================

st.subheader("Send Test Message")

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
            log, error_msg = send_test_reminder(db2, student_id, school_id)
            if log and not error_msg:
                st.success(f"✅ Success! Reminder sent to parent ({log.status if log.status else 'Sent'})")
                st.balloons()
                st.rerun()
            else:
                st.error(f"❌ Failed to send test message: {error_msg if error_msg else 'Unknown error'}")
                if error_msg and "token" in error_msg.lower():
                    st.info("💡 Hint: Check your WhatsApp Token in Render Environment Variables.")
else:
    st.warning("No students with outstanding balances to send reminders to.")
