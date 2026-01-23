"""
=============================================================================
SmartBursar - Students Page
=============================================================================
View, manage, and import students for the current school.
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import text

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.theme import apply_theme, init_session_state
from config.database import get_db_context
from models import Student, School, FeeStructure


# =============================================================================
# Page Config
# =============================================================================

st.set_page_config(
    page_title="Students - SmartBursar",
    page_icon="SB",
    layout="wide",
)

init_session_state()
apply_theme()


# =============================================================================
# Security Check
# =============================================================================

def check_access():
    if "role" not in st.session_state:
        st.error("Please login first")
        st.stop()
    
    if st.session_state.get("role") == "SUPER_ADMIN" and not st.session_state.get("impersonating"):
        st.warning("Please select a school to view from God Mode")
        st.stop()
    
    if not st.session_state.get("school_id"):
        st.error("No school assigned")
        st.stop()


check_access()
school_id = st.session_state.get("school_id")


# =============================================================================
# Header
# =============================================================================

st.title("Students")

with get_db_context() as db:
    school = db.query(School).filter(School.id == school_id).first()
    if school:
        st.caption(f"{school.school_name} - SmartBursar")

st.markdown("---")


# =============================================================================
# Tabs: View Students | Import CSV
# =============================================================================

tab1, tab2, tab3 = st.tabs(["View Students", "Add Student", "Import CSV"])


# =============================================================================
# Tab 1: View Students
# =============================================================================

with tab1:
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_query = st.text_input("Search", placeholder="Student or parent name...")
    
    with col2:
        status_filter = st.selectbox(
            "Payment Status",
            ["All", "Owing", "Partial", "Paid", "Overpaid"],
        )
    
    with col3:
        class_filter = st.selectbox(
            "Class",
            ["All"] + [
                "Nursery 1", "Nursery 2", "Nursery 3",
                "Primary 1", "Primary 2", "Primary 3", "Primary 4", "Primary 5", "Primary 6",
                "JSS 1", "JSS 2", "JSS 3", "SS 1", "SS 2", "SS 3",
            ],
        )
    
    # Data Fetch
    with get_db_context() as db:
        query = db.query(Student).filter(Student.school_id == school_id)
        
        if search_query:
            query = query.filter(
                (Student.full_name.ilike(f"%{search_query}%")) |
                (Student.parent_name.ilike(f"%{search_query}%"))
            )
        
        if class_filter != "All":
            query = query.filter(Student.class_level == class_filter)
        
        # Filter archive
        show_archived = st.checkbox("Show Archived Students", value=False)
        
        if not show_archived:
            query = query.filter(Student.is_archived == False)
            
        students = query.order_by(
            (Student.fees_total_due - Student.amount_paid).desc()
        ).all()
        
        student_data = []
        for s in students:
            balance = float(s.fees_total_due - s.amount_paid)
            status = s.payment_status
            
            if status_filter != "All" and status.upper() != status_filter.upper():
                continue
            
            student_data.append({
                "id": s.id,
                "full_name": s.full_name,
                "class_level": s.class_level,
                "parent_name": s.parent_name,
                "parent_phone": s.parent_phone_primary,
                "fees_due": float(s.fees_total_due),
                "paid": float(s.amount_paid),
                "balance": balance,
                "status": status,
                "due_date": s.due_date,
            })
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Students", f"{len(student_data)}")
    
    with col2:
        owing = sum(1 for s in student_data if s["balance"] > 0)
        st.metric("Still Owing", f"{owing}")
    
    with col3:
        total_owed = sum(s["balance"] for s in student_data if s["balance"] > 0)
        st.metric("Outstanding", f"N{int(total_owed):,}")
    
    with col4:
        collected = sum(s["paid"] for s in student_data)
        st.metric("Collected", f"N{int(collected):,}")
    
    st.markdown("---")
    
    # Data Table
    if not student_data:
        st.info("No students found matching your filters.")
    else:
        # Display table with formatted values
        display = []
        for s in student_data:
            display.append({
                "Name": s["full_name"],
                "Class": s["class_level"],
                "Parent": s["parent_name"],
                "Phone": s["parent_phone"],
                "Fees": f"N{int(s['fees_due']):,}",
                "Paid": f"N{int(s['paid']):,}",
                "Balance": f"N{int(s['balance']):,}",
                "Status": s["status"],
            })
        
        df = pd.DataFrame(display)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # Export with import-compatible format (raw values, includes Due Date)
        export_data = []
        for s in student_data:
            export_data.append({
                "Name": s["full_name"],
                "Class": s["class_level"],
                "Parent": s["parent_name"],
                "Phone": s["parent_phone"],
                "Fees": int(s["fees_due"]),
                "Paid": int(s["paid"]),
                "Due Date": s["due_date"].strftime("%Y-%m-%d") if s["due_date"] else "",
            })
        
        export_df = pd.DataFrame(export_data)
        csv = export_df.to_csv(index=False)
        st.download_button(
            label="Export to CSV",
            data=csv,
            file_name="students_export.csv",
            mime="text/csv",
        )
        
        # Student Management Section
        st.markdown("---")
        st.subheader("Student Management")
        
        manage_opts = {f"{s['full_name']} ({s['class_level']})": s['id'] for s in student_data}
        if manage_opts:
            col1, col2 = st.columns([2, 1])
            with col1:
                manage_sel = st.selectbox("Select Student", options=list(manage_opts.keys()), key="manage_student_sel")
                student_id_to_manage = manage_opts[manage_sel]
            
            with col2:
                st.write("") # Spacer
                st.write("")
                if show_archived:
                    if st.button("Unarchive Student", type="primary", use_container_width=True):
                        with get_db_context() as db:
                            db.execute(
                                text("UPDATE students SET is_archived = 0 WHERE id = :sid"),
                                {"sid": student_id_to_manage}
                            )
                            db.commit()
                        st.success("Student unarchived successfully!")
                        st.rerun()
                else:
                    if st.button("Archive Student", type="primary", use_container_width=True):
                        with get_db_context() as db:
                            db.execute(
                                text("UPDATE students SET is_archived = 1 WHERE id = :sid"),
                                {"sid": student_id_to_manage}
                            )
                            db.commit()
                        st.success("Student archived! They will no longer receive payment reminders.")
                        st.rerun()
        else:
            st.info("No students available to manage.")


# =============================================================================
# Tab 2: Add Single Student
# =============================================================================

with tab2:
    st.subheader("Add New Student")
    
    with st.form("add_student_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            full_name = st.text_input("Student Name", placeholder="e.g. John Doe")
            parent_name = st.text_input("Parent Name", placeholder="e.g. Mr. Doe")
            phone = st.text_input("Phone Number", placeholder="080...")
        
        with col2:
            # Class Selection
            classes = [
                "Nursery 1", "Nursery 2", "Nursery 3",
                "Primary 1", "Primary 2", "Primary 3", "Primary 4", "Primary 5", "Primary 6",
                "JSS 1", "JSS 2", "JSS 3",
                "SS 1", "SS 2", "SS 3",
            ]
            
            selected_class = st.selectbox("Class", classes)
            
            fees_due = st.number_input("School Fees", min_value=0, value=0, help="Leave as 0 to auto-use Class Default Fee")
            amount_paid = st.number_input("Amount Paid", min_value=0, value=0)
            
            # Auto-populate due date from school's exam_date setting
            with get_db_context() as db:
                school_for_dates = db.query(School).filter(School.id == school_id).first()
                exam_date_str = None
                if school_for_dates and school_for_dates.settings_config:
                    exam_date_str = school_for_dates.settings_config.get("exam_date")
                
                if exam_date_str:
                    try:
                        default_due = date.fromisoformat(exam_date_str)
                    except:
                        default_due = date.today() + pd.Timedelta(days=90)
                else:
                    default_due = date.today() + pd.Timedelta(days=90)
            
            st.caption(f"Due Date: **{default_due.strftime('%d %B %Y')}** (from Exam Date in Settings)")
            due_date = default_due  # Hidden - auto-set from exam date
        
        st.markdown("---")
        submitted = st.form_submit_button("Add Student", type="primary", use_container_width=True)
        
        if submitted:
            if not full_name or not parent_name or not phone:
                st.error("Name, Parent Name, and Phone are required")
            else:
                try:
                    # Fee Auto-fill Logic
                    final_fee = Decimal(fees_due)
                    if final_fee == 0:
                        with get_db_context() as db:
                            from models.fee_structure import FeeStructure
                            default = db.query(FeeStructure).filter(
                                FeeStructure.school_id == school_id,
                                FeeStructure.class_level == selected_class
                            ).first()
                            if default:
                                final_fee = default.amount
                    
                    if final_fee == 0:
                         st.warning(f"Warning: School fee is N0 for {selected_class}. Please set a fee in Payments > Fee Settings or enter manually.")

                    with get_db_context() as db:
                        new_student = Student(
                            school_id=school_id,
                            full_name=full_name,
                            class_level=selected_class,
                            parent_name=parent_name,
                            parent_phone_primary=phone,
                            fees_total_due=final_fee,
                            amount_paid=Decimal(amount_paid),
                            due_date=due_date
                        )
                        db.add(new_student)
                        db.commit()
                        
                    st.success(f"Added {full_name} to {selected_class}!")
                    if final_fee > 0:
                        st.info(f"Fees set to: N{int(final_fee):,}")
                        
                except Exception as e:
                    st.error(f"Error adding student: {e}")


# =============================================================================
# Tab 3: Import CSV
# =============================================================================

with tab3:
    st.subheader("Import Students from CSV")
    
    st.info("""
    **CSV Format Required:**
    | Name | Class | Parent | Phone | Fees | Paid | Due Date |
    |------|-------|--------|-------|------|------|----------|
    | Adaeze Okonkwo | Primary 3 | Mr. Chukwu | 08012345678 | 150000 | 50000 | 2026-03-15 |
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
    
    # File upload
    uploaded_file = st.file_uploader("Upload CSV File", type=["csv"])
    
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            
            # Validate columns - using simpler names
            required_cols = ["Name", "Class", "Parent", "Phone", "Fees", "Paid", "Due Date"]
            missing = [c for c in required_cols if c not in df.columns]
            
            if missing:
                st.error(f"Missing columns: {', '.join(missing)}")
                st.info(f"Your columns: {list(df.columns)}")
            else:
                st.success(f"Found {len(df)} students in file")
                
                # Preview
                st.subheader("Preview")
                st.dataframe(df.head(10), use_container_width=True, hide_index=True)
                
                # Use form to ensure button works
                with st.form("import_students_form"):
                    st.write(f"Ready to import **{len(df)} students** to this school")
                    submit = st.form_submit_button("Import Students", type="primary", use_container_width=True)
                    
                    if submit:
                        imported = 0
                        errors = []
                        
                        with get_db_context() as db:
                            for idx, row in df.iterrows():
                                try:
                                    # Parse due date
                                    due_date_str = str(row["Due Date"])
                                    try:
                                        due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
                                    except:
                                        due_date = date.today()
                                    
                                    # Get Default Fee if needed
                                    class_val = str(row["Class"]).strip()
                                    fee_val = Decimal(str(row["Fees"]))
                                    
                                    # If fee is 0 or empty, try to find default
                                    if fee_val == 0:
                                        from models.fee_structure import FeeStructure
                                        default_fee = db.query(FeeStructure).filter(
                                            FeeStructure.school_id == school_id,
                                            FeeStructure.class_level == class_val
                                        ).first()
                                        if default_fee:
                                            fee_val = default_fee.amount
                                    
                                    # Create student
                                    student = Student(
                                        school_id=school_id,
                                        full_name=str(row["Name"]).strip(),
                                        class_level=class_val,
                                        parent_name=str(row["Parent"]).strip(),
                                        parent_phone_primary=str(row["Phone"]).strip(),
                                        fees_total_due=fee_val,
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
                            if len(errors) > 5:
                                st.text(f"... and {len(errors) - 5} more")
                    
        except Exception as e:
            st.error(f"Error reading file: {str(e)}")

