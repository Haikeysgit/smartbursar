"""
=============================================================================
SmartBursar - Payments Page
=============================================================================
Log payments, verify pending claims, view history.
"""

import streamlit as st
import pandas as pd
from decimal import Decimal
from datetime import timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.theme import apply_theme, init_session_state
from config.database import get_db_context
from models import Student, School, Transaction, FeeStructure # TransactionStatus if needed, usually Enum
from models.transaction import TransactionStatus
from services.payments.payment_recorder import (
    record_payment, verify_payment, reject_payment, get_pending_payments
)
from models.fee_structure import FeeStructure
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert


# =============================================================================
# Page Config
# =============================================================================

st.set_page_config(
    page_title="Payments - SmartBursar",
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
user_id = st.session_state.get("user_id")


# =============================================================================
# Header
# =============================================================================

st.title("Payments")

with get_db_context() as db:
    school = db.query(School).filter(School.id == school_id).first()
    if school:
        st.caption(f"{school.school_name} - SmartBursar")

st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs(["Log Payment", "Pending Verification", "History", "Fee Settings"])


# =============================================================================
# Tab 4: Fee Settings (Default Fees per Class)
# =============================================================================

with tab4:
    st.subheader("Default Class Fees")
    st.info("Set the standard school fees for each class. New students will default to this amount.")
    
    with get_db_context() as db:
        # Fetch current fees
        fees = db.query(FeeStructure).filter(FeeStructure.school_id == school_id).all()
        fee_map = {f.class_level: int(f.amount) for f in fees}
        
        # Define classes (Must match what's used in Students page)
        classes = [
            "Nursery 1", "Nursery 2", "Nursery 3",
            "Primary 1", "Primary 2", "Primary 3", "Primary 4", "Primary 5", "Primary 6",
            "JSS 1", "JSS 2", "JSS 3",
            "SS 1", "SS 2", "SS 3",
        ]
        
        with st.form("fee_settings_form"):
            col1, col2 = st.columns(2)
            
            new_fees = {}
            
            # Display inputs for each class
            for i, class_name in enumerate(classes):
                with col1 if i < len(classes)/2 else col2:
                    current_val = fee_map.get(class_name, 0)
                    new_fees[class_name] = st.number_input(
                        f"{class_name}", 
                        min_value=0, 
                        value=current_val,
                        step=5000,
                        key=f"fee_{class_name}"
                    )
            
            st.markdown("---")
            if st.form_submit_button("Save Fee Structure", type="primary", use_container_width=True):
                try:
                    # Upsert logic
                    for cls, amt in new_fees.items():
                        stmt = sqlite_upsert(FeeStructure).values(
                            school_id=school_id,
                            class_level=cls,
                            amount=Decimal(amt)
                        )
                        # SQLite upsert handling
                        stmt = stmt.on_conflict_do_update(
                            index_elements=['school_id', 'class_level'],
                            set_=dict(amount=Decimal(amt))
                        )
                        db.execute(stmt)
                    
                    db.commit()
                    st.success("Fee structure updated successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving fees: {e}")


# =============================================================================
# Tab 1: Log Payment
# =============================================================================

with tab1:
    st.subheader("Record New Payment")
    
    with get_db_context() as db:
        students = db.query(Student).filter(
            Student.school_id == school_id,
        ).order_by(Student.full_name).all()
        
        student_opts = {
            f"{s.full_name} ({s.class_level}) - Balance: ₦{int(s.balance):,}": s.id
            for s in students
        }
    
    # Search filter for quick lookup
    search_query = st.text_input("Search student by name or class", placeholder="Type to filter...")
    
    # Filter options based on search
    if search_query:
        filtered_opts = {k: v for k, v in student_opts.items() if search_query.lower() in k.lower()}
    else:
        filtered_opts = student_opts
    
    if not filtered_opts:
        st.warning("No students match your search")
    
    with st.form("payment_form"):
        selected = st.selectbox("Select Student", options=list(filtered_opts.keys()) if filtered_opts else ["No students found"])
        
        col1, col2 = st.columns(2)
        with col1:
            amount = st.number_input("Amount (N)", min_value=1000, max_value=1000000, step=1000)
        with col2:
            method = st.selectbox("Method", ["BANK_TRANSFER", "CASH", "POS", "CHEQUE"])
        
        notes = st.text_area("Notes (optional)")
        
        if st.form_submit_button("Record Payment", use_container_width=True):
            if selected and selected != "No students found" and selected in filtered_opts:
                student_id = filtered_opts[selected]
                with get_db_context() as db:
                    txn, err = record_payment(
                        db=db,
                        student_id=student_id,
                        amount=Decimal(str(amount)),
                        method=method,
                        school_id=school_id,
                        notes=notes,
                        auto_verify=True,
                        verified_by_id=user_id,
                    )
                    if err:
                        st.error(err)
                    else:
                        st.success(f"Payment recorded! Receipt #{txn.receipt_number}")
                        st.balloons()


# =============================================================================
# Tab 2: Pending Verification
# =============================================================================

with tab2:
    st.subheader("Awaiting Verification")
    
    with get_db_context() as db:
        pending = get_pending_payments(db, school_id)
        
        if not pending:
            st.success("No pending payments. All caught up!")
        else:
            st.warning(f"{len(pending)} payments need verification")
            
            for txn in pending:
                student = txn.student
                st.markdown(f"**{student.full_name}** - N{int(txn.amount):,} ({txn.method})")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Verify", key=f"v_{txn.id}", use_container_width=True):
                        with get_db_context() as db2:
                            _, err = verify_payment(db2, txn.id, school_id, user_id)
                            if err:
                                st.error(err)
                            else:
                                st.success("Verified!")
                                st.rerun()
                with col2:
                    if st.button("Reject", key=f"r_{txn.id}", use_container_width=True):
                        with get_db_context() as db2:
                            _, err = reject_payment(db2, txn.id, school_id, user_id, "Not verified")
                            if err:
                                st.error(err)
                            else:
                                st.warning("Rejected")
                                st.rerun()
                st.markdown("---")


# =============================================================================
# Tab 3: History
# =============================================================================

with tab3:
    st.subheader("Payment History")
    
    with get_db_context() as db:
        txns = db.query(Transaction).join(Student).filter(
            Student.school_id == school_id,
        ).order_by(Transaction.date.desc()).limit(50).all()
        
        if not txns:
            st.info("No payment history yet")
        else:
            txn_data = []
            for t in txns:
                txn_data.append({
                    "receipt": t.receipt_number,
                    "student": t.student.full_name,
                    "student_class": t.student.class_level,
                    "parent": t.student.parent_name,
                    "amount": float(t.amount),
                    "method": t.method,
                    "date": t.date,
                    "status": t.status,
                    "fees_total": float(t.student.fees_total_due),
                    "balance_before": float(t.balance_before),
                    "balance_after": float(t.balance_after),
                    "due_date": t.student.due_date,
                })
            
            if txn_data:
                display = []
                for t in txn_data:
                    display.append({
                        "Receipt": t["receipt"],
                        "Student": t["student"],
                        "Amount": f"N{int(t['amount']):,}",
                        "Method": t["method"],
                        "Date": t["date"].strftime("%Y-%m-%d"),
                        "Status": t["status"],
                    })
                
                df = pd.DataFrame(display)
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                st.subheader("Download Receipt")
                
                verified = [t for t in txn_data if t["status"] == "VERIFIED"]
                if verified:
                    opts = {f"{t['receipt']} - {t['student']} (N{int(t['amount']):,})": t for t in verified}
                    sel = st.selectbox("Select payment", options=list(opts.keys()))
                    
                    if st.button("Generate PDF Receipt", use_container_width=True):
                        t = opts[sel]
                        from services.payments.receipt_generator import ReceiptData, generate_receipt_pdf
                        
                        school = db.query(School).filter(School.id == school_id).first()
                        
                        data = ReceiptData(
                            school_name=school.school_name,
                            school_address=school.address,
                            school_phone=school.phone,
                            school_logo_base64=school.logo_base64,
                            receipt_number=t["receipt"],
                            date=t["date"],
                            student_name=t["student"],
                            class_level=t["student_class"],
                            parent_name=t["parent"],
                            fees_total=Decimal(str(t["fees_total"])),
                            previous_paid=Decimal(str(t["fees_total"] - t["balance_before"])),
                            this_payment=Decimal(str(t["amount"])),
                            balance_after=Decimal(str(t["balance_after"])),
                            payment_method=t["method"],
                            due_date=t["due_date"],
                        )
                        
                        pdf = generate_receipt_pdf(data)
                        
                        st.download_button("Download PDF", pdf, f"receipt_{t['receipt']}.pdf", "application/pdf")
                else:
                    st.info("No verified payments to generate receipts for.")
