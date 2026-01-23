"""
=============================================================================
SmartBursar - Super Admin (God Mode)
=============================================================================
Platform-wide administration for super admins.
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.theme import apply_theme, init_session_state
from config.database import get_db_context
from models import School, User, Student, create_user, FeeStructure


# =============================================================================
# Page Config
# =============================================================================

st.set_page_config(
    page_title="Admin Panel - SmartBursar",
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
    
    if st.session_state.get("role") != "SUPER_ADMIN":
        st.error("Access denied. Super Admin only.")
        st.stop()


check_access()


# =============================================================================
# Header
# =============================================================================

st.title("Admin Panel")
st.caption("SmartBursar Platform Administration")

st.markdown("---")


# =============================================================================
# Platform Metrics (Updated Pricing)
# =============================================================================

st.subheader("Platform Health")

with get_db_context() as db:
    schools = db.query(School).all()
    
    active = sum(1 for s in schools if s.is_active)
    expiring = sum(1 for s in schools if 0 <= s.days_remaining <= 7)
    expired = sum(1 for s in schools if s.days_remaining < 0)
    
    # Calculate term revenue: ₦150k base for 150 debtors + ₦500 per overage
    # Pricing: BASE_PRICE=150000, DEBTOR_LIMIT=150, OVERAGE_RATE=500
    term_revenue = 0
    total_overage = 0
    for school in schools:
        if school.is_active:
            debtor_count = db.query(Student).filter(
                Student.school_id == school.id,
                Student.fees_total_due > Student.amount_paid
            ).count()
            base = 150000  # ₦150,000 per term
            limit = 150    # 150 debtors included
            overage = max(0, debtor_count - limit) * 500  # ₦500 per extra
            term_revenue += base + overage
            total_overage += overage
    
    base_revenue = term_revenue - total_overage
    total_students = db.query(Student).count()

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Term Revenue", f"₦{int(term_revenue):,}")
with col2:
    st.metric("Active Schools", f"{active}")
with col3:
    st.metric("Total Students", f"{total_students}")
with col4:
    st.metric("Expiring Soon", f"{expiring}")
with col5:
    st.metric("Expired", f"{expired}")

# =============================================================================
# EXPIRY ALERT BANNER - Remind Super Admin to follow up
# =============================================================================

with get_db_context() as db:
    expiring_schools = db.query(School).filter(
        School.status == "ACTIVE"
    ).all()
    expiring_schools = [s for s in expiring_schools if 0 <= s.days_remaining <= 7]
    
    if expiring_schools:
        st.error(f"**ACTION REQUIRED:** {len(expiring_schools)} school(s) expiring within 7 days!")
        
        for school in expiring_schools:
            # Format WhatsApp link with XSS sanitization
            import re
            from urllib.parse import quote
            
            # SECURITY: Sanitize phone number - only allow digits
            phone = re.sub(r'[^\d]', '', school.phone)
            if phone.startswith("0"):
                phone = "234" + phone[1:]
            
            # SECURITY: URL-encode the message text
            message = quote(f"Hi, this is SmartBursar. Your subscription expires in {school.days_remaining} days. Please renew to continue service.")
            wa_link = f"https://wa.me/{phone}?text={message}"
            
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.warning(f"**{school.school_name}** - {school.days_remaining} days left (expires {school.subscription_end_date})")
            with col2:
                st.markdown(f'<a href="{wa_link}" target="_blank" style="display:inline-block;background:#25D366;color:white;padding:8px 16px;border-radius:6px;text-decoration:none;font-weight:600;">WhatsApp</a>', unsafe_allow_html=True)
            with col3:
                st.caption(school.phone)

st.markdown("---")


# =============================================================================
# Tabs
# =============================================================================

tab1, tab2, tab3 = st.tabs(["Schools", "Import Students", "Add School"])


# =============================================================================
# Tab 1: Schools
# =============================================================================

with tab1:
    st.subheader("All Schools")
    
    with get_db_context() as db:
        schools = db.query(School).order_by(School.school_name).all()
        
        school_data = []
        for s in schools:
            debtor_count = db.query(Student).filter(
                Student.school_id == s.id,
                Student.fees_total_due > Student.amount_paid
            ).count()
            limit = getattr(s, 'debtor_limit', 150)
            
            school_data.append({
                "id": s.id,
                "code": s.school_code,
                "name": s.school_name,
                "plan": s.plan_type,
                "status": s.status,
                "days": s.days_remaining,
                "students": len(s.students),
                "debtors": debtor_count,
                "limit": limit,
            })
    
    if school_data:
        display = []
        for s in school_data:
            status = "Active"
            if s["days"] < 0:
                status = "Expired"
            elif s["days"] <= 7:
                status = "Expiring"
            
            display.append({
                "Code": s["code"],
                "School Name": s["name"],
                "Status": status,
                "Days Left": s["days"],
                "Students": s["students"],
                "Debtors": f"{s['debtors']}/{s['limit']}",
            })
        
        df = pd.DataFrame(display)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.subheader("Switch to School View")
        
        opts = {f"{s['name']} ({s['code']})": s["id"] for s in school_data}
        sel = st.selectbox("Select school", options=list(opts.keys()))
        
        if st.button("Switch to School View", use_container_width=True, type="primary"):
            st.session_state["original_school_id"] = st.session_state.get("school_id")
            st.session_state["school_id"] = opts[sel]
            st.session_state["impersonating"] = True
            st.success("Switching to school view...")
            st.switch_page("pages/02_students.py")
        
        # =====================================================================
        # DELETE SCHOOL SECTION
        # =====================================================================
        st.markdown("---")
        st.subheader("Delete School")
        st.warning("**Danger Zone:** Deleting a school removes ALL data permanently including students, payments, and messages.")
        
        delete_opts = {f"{s['name']} ({s['code']})": s for s in school_data}
        del_sel = st.selectbox("Select school to delete", options=list(delete_opts.keys()), key="delete_school_select")
        del_school = delete_opts[del_sel]
        
        # Two-step confirmation
        st.markdown(f"To confirm, type **{del_school['code']}** below:")
        confirm_text = st.text_input("Type school code to confirm", key="delete_confirm", placeholder=del_school['code'])
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("DELETE SCHOOL", type="primary", use_container_width=True):
                if confirm_text.upper() != del_school['code'].upper():
                    st.error(f"Confirmation failed. Please type '{del_school['code']}' exactly.")
                else:
                    # Perform cascading delete
                    from sqlalchemy import text
                    with get_db_context() as db:
                        school_id = del_school['id']
                        
                        # Delete all related data in order
                        db.execute(text("DELETE FROM message_logs WHERE student_id IN (SELECT id FROM students WHERE school_id = :sid)"), {"sid": school_id})
                        db.execute(text("DELETE FROM transactions WHERE student_id IN (SELECT id FROM students WHERE school_id = :sid)"), {"sid": school_id})
                        db.execute(text("DELETE FROM students WHERE school_id = :sid"), {"sid": school_id})
                        db.execute(text("DELETE FROM fee_structures WHERE school_id = :sid"), {"sid": school_id})
                        db.execute(text("DELETE FROM users WHERE school_id = :sid"), {"sid": school_id})
                        db.execute(text("DELETE FROM schools WHERE id = :sid"), {"sid": school_id})
                        db.commit()
                    
                    st.success(f"School '{del_school['name']}' and all its data have been permanently deleted.")
                    st.rerun()
        with col2:
            st.caption("This action cannot be undone!")
        
        # =====================================================================
        # RESET PASSWORD SECTION
        # =====================================================================
        st.markdown("---")
        st.subheader("Reset School Admin Password")
        
        reset_opts = {f"{s['name']} ({s['code']})": s for s in school_data}
        reset_sel = st.selectbox("Select school", options=list(reset_opts.keys()), key="reset_pwd_select")
        reset_school = reset_opts[reset_sel]
        
        new_password = st.text_input("New Password", type="password", key="new_pwd", placeholder="Enter new password")
        confirm_password = st.text_input("Confirm Password", type="password", key="confirm_pwd", placeholder="Confirm new password")
        
        if st.button("Reset Password", use_container_width=True):
            if not new_password or len(new_password) < 6:
                st.error("Password must be at least 6 characters")
            elif new_password != confirm_password:
                st.error("Passwords do not match")
            else:
                from sqlalchemy import text
                import bcrypt
                # Hash the new password with bcrypt
                password_bytes = new_password.encode('utf-8')
                salt = bcrypt.gensalt()
                pwd_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
                
                with get_db_context() as db:
                    result = db.execute(
                        text("UPDATE users SET password_hash = :pwd WHERE school_id = :sid AND role = 'SCHOOL_ADMIN'"),
                        {"pwd": pwd_hash, "sid": reset_school['id']}
                    )
                    db.commit()
                    
                    if result.rowcount > 0:
                        st.success(f"Password reset successfully for {reset_school['name']}!")
                        st.info(f"Tell them to login with their email and new password: **{new_password}**")
                    else:
                        st.warning("No admin user found for this school")
    else:
        st.info("No schools registered yet")

# =============================================================================
# Tab 2: Import Students for Any School
# =============================================================================

with tab2:
    st.subheader("Import Students for a School")
    
    with get_db_context() as db:
        schools = db.query(School).order_by(School.school_name).all()
        school_opts = {f"{s.school_name} ({s.school_code})": s.id for s in schools}
    
    if not school_opts:
        st.warning("No schools available. Create a school first.")
    else:
        selected_school = st.selectbox("Select School", options=list(school_opts.keys()))
        target_school_id = school_opts[selected_school]
        
        st.info("""
        **CSV Format Required:**
        | Name | Class | Parent | Phone | Fees | Paid | Due Date |
        """)
        
        # Download template
        template_df = pd.DataFrame({
            "Name": ["Adaeze Okonkwo", "Chinedu Eze"],
            "Class": ["Primary 3", "JSS 1"],
            "Parent": ["Mr. Chukwu Okonkwo", "Mrs. Ngozi Eze"],
            "Phone": ["08012345678", "08098765432"],
            "Fees": [150000, 200000],
            "Paid": [50000, 100000],
            "Due Date": ["2026-03-15", "2026-03-15"],
        })
        
        template_csv = template_df.to_csv(index=False)
        st.download_button(
            "Download CSV Template",
            template_csv,
            "student_import_template.csv",
            "text/csv",
        )
        
        st.markdown("---")
        
        uploaded_file = st.file_uploader("Upload CSV File", type=["csv"], key="godmode_csv")
        
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)
                
                required_cols = ["Name", "Class", "Parent", "Phone", "Fees", "Paid", "Due Date"]
                missing = [c for c in required_cols if c not in df.columns]
                
                if missing:
                    st.error(f"Missing columns: {', '.join(missing)}")
                    st.info(f"Your columns: {list(df.columns)}")
                else:
                    st.success(f"Found {len(df)} students in file")
                    st.dataframe(df.head(10), use_container_width=True, hide_index=True)
                    
                    # Use a form to ensure button works
                    with st.form("import_form"):
                        st.write(f"Ready to import {len(df)} students to **{selected_school}**")
                        submit = st.form_submit_button("Import Students", type="primary", use_container_width=True)
                        
                        if submit:
                            imported = 0
                            errors = []
                            
                            with get_db_context() as db:
                                for idx, row in df.iterrows():
                                    try:
                                        due_date_str = str(row["Due Date"])
                                        try:
                                            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
                                        except:
                                            due_date = date.today()
                                        
                                        student = Student(
                                            school_id=target_school_id,
                                            full_name=str(row["Name"]).strip(),
                                            class_level=str(row["Class"]).strip(),
                                            parent_name=str(row["Parent"]).strip(),
                                            parent_phone_primary=str(row["Phone"]).strip(),
                                            fees_total_due=Decimal(str(row["Fees"])),
                                            amount_paid=Decimal(str(row["Paid"])),
                                            due_date=due_date,
                                        )
                                        db.add(student)
                                        imported += 1
                                    except Exception as e:
                                        errors.append(f"Row {idx + 2}: {str(e)}")
                                
                                db.commit()
                            
                            if imported > 0:
                                st.success(f"Successfully imported {imported} students!")
                                st.balloons()
                            
                            if errors:
                                st.warning(f"Errors ({len(errors)}):")
                                for e in errors[:5]:
                                    st.text(e)
                        
            except Exception as e:
                st.error(f"Error reading file: {str(e)}")


# =============================================================================
# Tab 3: Add New School
# =============================================================================

with tab3:
    st.subheader("Add New School")
    
    with st.form("new_school"):
        st.markdown("**School Details**")
        col1, col2 = st.columns(2)
        
        with col1:
            code = st.text_input("School Code", placeholder="ABC", max_chars=10)
            name = st.text_input("School Name", placeholder="ABC Primary School")
            address = st.text_input("Address", placeholder="123 School Road, Lagos")
        
        with col2:
            phone = st.text_input("Owner Phone (WhatsApp)", placeholder="+2348012345678")
        
        st.markdown("**Secretary/Admin Contact (Optional)**")
        admin_whatsapp = st.text_input(
            "Admin/Secretary WhatsApp Number", 
            placeholder="+2348012345678",
            help="If set, payment receipts go to this person instead of the owner"
        )
        
        st.markdown("**Bank Details**")
        c1, c2, c3 = st.columns(3)
        with c1:
            bank = st.text_input("Bank Name", placeholder="GTBank")
        with c2:
            acc_num = st.text_input("Account Number", placeholder="0123456789")
        with c3:
            acc_name = st.text_input("Account Name", placeholder="School Name")
        
        st.markdown("**Term Schedule** *(for automated reminders)*")
        st.info("Grace Period: No messages for 14 days after term start. Phase 1 (before mid-term): Mondays. Phase 2 (after mid-term): Mon + Thu.")
        c1, c2, c3 = st.columns(3)
        with c1:
            term_start = st.date_input("Term Start Date", value=date.today())
        with c2:
            mid_term = st.date_input("Mid-Term Date", value=date.today() + timedelta(days=42))
        with c3:
            exam_date = st.date_input("Exam Start Date", value=date.today() + timedelta(days=84))
        
        st.markdown("**Admin User**")
        c1, c2 = st.columns(2)
        with c1:
            email = st.text_input("Admin Email", placeholder="admin@school.com")
        with c2:
            pwd = st.text_input("Admin Password", type="password", placeholder="password123")
        
        if st.form_submit_button("Create School", use_container_width=True):
            if not all([code, name, address, phone, bank, acc_num, acc_name, email, pwd]):
                st.error("All fields are required")
            elif "@" not in email or "." not in email:
                st.error("Invalid email format. Must contain '@' and '.'")
            else:
                try:
                    with get_db_context() as db:
                        existing = db.query(School).filter(School.school_code == code.upper()).first()
                        if existing:
                            st.error(f"School code {code.upper()} already exists")
                        else:
                            new_school = School(
                                school_code=code.upper(),
                                school_name=name,
                                address=address,
                                phone=phone,
                                admin_whatsapp_number=admin_whatsapp if admin_whatsapp else None,
                                country_code="NG",
                                bank_name=bank,
                                account_number=acc_num,
                                account_name=acc_name,
                                plan_type="TERMLY",
                                subscription_end_date=exam_date,  # Subscription ends when term ends
                                status="ACTIVE",
                                settings_config={
                                    "term_start_date": str(term_start),
                                    "mid_term_date": str(mid_term),
                                    "exam_date": str(exam_date)
                                },
                            )
                            db.add(new_school)
                            db.flush()
                            
                            admin = create_user(email, pwd, "SCHOOL_ADMIN", new_school.id)
                            db.add(admin)
                            db.commit()
                            
                            st.success(f"School created successfully! Admin email: {email}")
                            st.rerun()
                except Exception as e:
                    st.error(f"Error creating school: {e}")
