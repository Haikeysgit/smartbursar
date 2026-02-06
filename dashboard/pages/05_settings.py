"""
=============================================================================
SmartBursar - School Settings
=============================================================================
Configure term dates, messaging schedule, and notification routing.
"""

import streamlit as st
from datetime import date, timedelta
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.theme import apply_theme, init_session_state
from config.database import get_db_context
from models import School

st.set_page_config(
    page_title="Settings - SmartBursar",
    page_icon="S",
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

st.title("Settings")

with get_db_context() as db:
    school = db.query(School).filter(School.id == school_id).first()
    if school:
        st.caption(f"{school.school_name}")

st.markdown("---")


# =============================================================================
# Term Schedule
# =============================================================================

st.subheader("Term Schedule")
st.info(
    "**Reminder Schedule:** Grace Period (14 days after term start) → "
    "Phase 1 (Mondays, polite) → Phase 2 (Mon + Thu, strict with exam warning)"
)

with get_db_context() as db:
    school = db.query(School).filter(School.id == school_id).first()
    
    if not school:
        st.error("School not found")
        st.stop()
    
    # Get current settings
    config = school.settings_config or {}
    
    # Parse existing dates
    def parse_date(date_str, default_offset=0):
        if date_str:
            try:
                return date.fromisoformat(date_str)
            except:
                pass
        return date.today() + timedelta(days=default_offset)
    
    current_term_start = parse_date(config.get("term_start_date"), 0)
    current_mid_term = parse_date(config.get("mid_term_date"), 42)
    current_exam_date = parse_date(config.get("exam_date"), 84)
    
    with st.form("term_schedule_form"):
        c1, c2, c3 = st.columns(3)
        
        with c1:
            term_start = st.date_input(
                "Term Start Date",
                value=current_term_start,
                help="First day of the current term. 14-day grace period starts here."
            )
        
        with c2:
            mid_term = st.date_input(
                "Mid-Term Date",
                value=current_mid_term,
                help="Messaging switches from Phase 1 (weekly) to Phase 2 (twice weekly)."
            )
        
        with c3:
            exam_date = st.date_input(
                "Exam Start Date", 
                value=current_exam_date,
                help="Messaging pauses once exams begin."
            )
        
        if st.form_submit_button("Save Term Dates", type="primary", use_container_width=True):
            try:
                new_config = config.copy()
                new_config["term_start_date"] = str(term_start)
                new_config["mid_term_date"] = str(mid_term)
                new_config["exam_date"] = str(exam_date)
                
                school.settings_config = new_config
                db.commit()
                st.success("Term dates updated!")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

st.markdown("---")


# =============================================================================
# Notification Routing
# =============================================================================

st.subheader("Notification Routing")
st.info(
    "**Payment Receipts:** When a parent uploads a payment receipt, "
    "the verification alert goes to this number. If empty, alerts go to the school owner."
)

with get_db_context() as db:
    school = db.query(School).filter(School.id == school_id).first()
    current_admin_phone = getattr(school, 'admin_whatsapp_number', None) or ""
    
    with st.form("notification_form"):
        admin_phone = st.text_input(
            "Secretary/Admin WhatsApp Number (Optional)",
            value=current_admin_phone,
            placeholder="+2348012345678",
            help="Include country code. Leave empty to use school owner's number."
        )
        
        if st.form_submit_button("Save Notification Settings", type="primary", use_container_width=True):
            try:
                if hasattr(school, 'admin_whatsapp_number'):
                    school.admin_whatsapp_number = admin_phone.strip() if admin_phone.strip() else None
                    db.commit()
                    st.success("Notification routing updated!")
                    st.rerun()
                else:
                    st.warning("Admin phone feature requires database update. Contact support.")
            except Exception as e:
                st.error(f"Error: {e}")

st.markdown("---")


# =============================================================================
# Start New Term (Term Reset)
# =============================================================================

st.subheader("Start New Term")
st.warning(
    "**Use this when a new term begins.** This will add the new term's fees "
    "to each student's balance. Students who still owe from last term will have "
    "their old debt PLUS the new term fee."
)

with get_db_context() as db:
    from models import Student
    
    school = db.query(School).filter(School.id == school_id).first()
    
    if school:
        # Get current student count and average fee
        students = db.query(Student).filter(Student.school_id == school_id).all()
        student_count = len(students)
        
        if student_count > 0:
            avg_fee = sum(s.fees_total_due for s in students) / student_count
            total_outstanding = sum(s.balance for s in students)
        else:
            avg_fee = Decimal("0")
            total_outstanding = Decimal("0")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Students", student_count)
        with col2:
            st.metric("Average Fee", f"₦{int(avg_fee):,}")
        with col3:
            st.metric("Total Outstanding", f"₦{int(total_outstanding):,}")
        
        with st.container():
            st.markdown("**New Term Details**")
            
            c1, c2 = st.columns(2)
            with c1:
                # Default logic: if avg_fee > 0 use it, else default to 0 (USER REQ)
                default_fee = int(avg_fee) if avg_fee > 0 else 0
                new_term_fee = st.number_input(
                    "New Term Fee (₦)",
                    min_value=0,
                    value=default_fee,
                    step=5000,
                    help="This amount will be ADDED to each student's current balance."
                )
            with c2:
                new_due_date = st.date_input(
                    "New Due Date",
                    value=date.today() + timedelta(days=30),
                    help="When should the new term fees be paid?"
                )
            
            st.markdown("**New Term Schedule**")
            c1, c2, c3 = st.columns(3)
            with c1:
                new_term_start = st.date_input("Term Start", value=date.today())
            with c2:
                new_mid_term = st.date_input("Mid-Term", value=date.today() + timedelta(days=42))
            with c3:
                new_exam_date = st.date_input("Exam Date", value=date.today() + timedelta(days=84))
            
            # Confirmation checkbox (Outside form so it updates dynamically)
            confirm = st.checkbox(
                f"I confirm I want to add ₦{new_term_fee:,} to ALL {student_count} students' balances",
                value=False
            )
            
            if st.button("Start New Term", type="primary", use_container_width=True):
                if not confirm:
                    st.error("Please check the confirmation box to proceed.")
                elif student_count == 0:
                    st.warning("No students to update.")
                else:
                    try:
                        # Update each student's fees_total_due
                        updated_count = 0
                        for student in students:
                            student.fees_total_due = student.fees_total_due + Decimal(str(new_term_fee))
                            student.due_date = new_due_date
                            updated_count += 1
                        
                        # Update term dates in school settings
                        config = school.settings_config or {}
                        config["term_start_date"] = str(new_term_start)
                        config["mid_term_date"] = str(new_mid_term)
                        config["exam_date"] = str(new_exam_date)
                        config["last_term_reset"] = str(date.today())
                        config["last_term_fee_added"] = new_term_fee
                        school.settings_config = config
                        
                        # Update subscription end date to new exam date
                        school.subscription_end_date = new_exam_date
                        
                        db.commit()
                        
                        st.success(f"New term started! Added ₦{new_term_fee:,} to {updated_count} students.")
                        st.balloons()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

st.markdown("---")


# =============================================================================
# School Information (Editable)
# =============================================================================

st.subheader("School Information")

# Toggle edit mode
if "edit_school_info" not in st.session_state:
    st.session_state["edit_school_info"] = False

with get_db_context() as db:
    school = db.query(School).filter(School.id == school_id).first()
    
    if school:
        # Header with Edit button
        if not st.session_state["edit_school_info"]:
            if st.button("Edit Details"):
                st.session_state["edit_school_info"] = True
                st.rerun()
        
        if st.session_state["edit_school_info"]:
            # EDIT MODE - Show form with input fields
            with st.form("school_info_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    new_school_name = st.text_input(
                        "School Name",
                        value=school.school_name,
                        help="Used for OCR beneficiary matching"
                    )
                    new_school_code = st.text_input(
                        "School Code",
                        value=school.school_code,
                        disabled=True,
                        help="Cannot be changed"
                    )
                    new_phone = st.text_input(
                        "Owner Phone",
                        value=school.phone,
                        help="Primary contact number"
                    )
                
                with col2:
                    new_bank_name = st.text_input(
                        "Bank Name",
                        value=school.bank_name,
                        help="Bank where school account is held"
                    )
                    new_account_number = st.text_input(
                        "Account Number",
                        value=school.account_number,
                        help="10-digit account number"
                    )
                    new_account_name = st.text_input(
                        "Account Name",
                        value=school.account_name,
                        help="CRITICAL: Must match bank statement exactly for OCR"
                    )
                
                
                col_save, col_cancel = st.columns(2)
                with col_save:
                    save_btn = st.form_submit_button("Save Changes", type="primary", use_container_width=True)
                with col_cancel:
                    cancel_btn = st.form_submit_button("Cancel", use_container_width=True)
                
                if save_btn:
                    try:
                        # Validate required fields
                        if not new_school_name.strip():
                            st.error("School Name is required")
                        elif not new_account_name.strip():
                            st.error("Account Name is required")
                        elif not new_account_number.strip():
                            st.error("Account Number is required")
                        else:
                            # Update school record
                            school.school_name = new_school_name.strip()
                            school.phone = new_phone.strip()
                            school.bank_name = new_bank_name.strip()
                            school.account_number = new_account_number.strip()
                            school.account_name = new_account_name.strip()
                            
                            db.commit()
                            
                            st.session_state["edit_school_info"] = False
                            st.success("School information updated!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error saving: {e}")
                
                if cancel_btn:
                    st.session_state["edit_school_info"] = False
                    st.rerun()
        
        else:
            # VIEW MODE - Show static display
            col1, col2 = st.columns(2)
            
            with col1:
                st.text_input("School Name", value=school.school_name, disabled=True)
                st.text_input("School Code", value=school.school_code, disabled=True)
                st.text_input("Owner Phone", value=school.phone, disabled=True)
            
            with col2:
                st.text_input("Bank Name", value=school.bank_name, disabled=True)
                st.text_input("Account Number", value=school.account_number, disabled=True)
                st.text_input("Account Name", value=school.account_name, disabled=True)


st.markdown("---")

# =============================================================================
# Danger Zone / Debug Tools
# =============================================================================

st.subheader("Danger Zone")

with st.expander("🛠️ Admin Tools (Use with Caution)", expanded=False):
    st.warning("These actions are destructive. Only use if instructed by support.")
    
    # Tool 1: Scrub Admin Phone
    st.markdown("#### 1. Fix 'Admin Identified as Parent' Conflict")
    st.caption("Use this if your 'Confirmed' replies are failing because the bot thinks you are a student.")
    
    scrub_phone = st.text_input("Enter Admin Phone Number to Fix", placeholder="23480...", help="Enter the number that is having issues")
    
    if st.button("Fix Admin Identity", type="primary"):
        if not scrub_phone:
            st.error("Please enter a phone number")
        else:
            with get_db_context() as db:
                from models.student import Student
                from models.transaction import Transaction
                from sqlalchemy import or_
                
                # Normalize phone
                clean_phone = scrub_phone.replace("+", "").replace(" ", "").replace("-", "")
                st.write(f"Scanning for phone: `{clean_phone}`...")
                
                # Search patterns
                patterns = [
                    clean_phone,
                    f"+{clean_phone}",
                    f"234{clean_phone[-10:]}" if len(clean_phone) >= 10 else clean_phone,
                    f"0{clean_phone[-10:]}" if len(clean_phone) >= 10 else clean_phone,
                ]
                
                # Find students
                students_found = []
                for pattern in patterns:
                    matches = db.query(Student).filter(
                        Student.parent_phone.contains(pattern[-10:])
                    ).all()
                    students_found.extend(matches)
                
                # Deduplicate by ID
                students_found = {s.id: s for s in students_found}.values()
                
                if not students_found:
                    st.info("No conflicting student records found with this number.")
                else:
                    count = 0
                    for student in students_found:
                        # Delete related transactions
                        db.query(Transaction).filter(Transaction.student_id == student.id).delete()
                        # Delete student
                        st.write(f"❌ Deleting conflict: Student '{student.full_name}' (ID: {student.id})")
                        db.delete(student)
                        count += 1
                    
                    # Also cancel stuck transactions
                    stuck = db.query(Transaction).filter(Transaction.status == "pending_verification").count()
                    if stuck > 0:
                        db.query(Transaction).filter(Transaction.status == "pending_verification").update(
                            {"status": "cancelled", "notes": "Auto-cancelled by admin fix"},
                            synchronize_session=False
                        )
                        st.write(f"🚫 Cancelled {stuck} stuck pending transactions.")
                    
                    db.commit()
                    st.success(f"✅ FIXED! Removed {count} conflicting student records. You can now reply 'Confirmed' freely.")

