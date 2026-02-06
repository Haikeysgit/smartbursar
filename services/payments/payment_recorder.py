"""
=============================================================================
PROJECT ATLAS - Payment Recorder Service
=============================================================================
Handles recording payments, updating balances, and managing verification.

TRUST-FIRST PHILOSOPHY:
    We never touch money. We just track and verify what schools tell us.
    The school admin remains in full control of verification.

Key Functions:
    - record_payment(): Log a new payment (creates PENDING or VERIFIED)
    - verify_payment(): Admin approves a pending payment
    - reject_payment(): Admin rejects a payment claim
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from config.settings import generate_receipt_number
from models.student import Student
from models.transaction import Transaction, PaymentMethod, TransactionStatus
from utils.date_helpers import get_wat_now


# =============================================================================
# Payment Recording
# =============================================================================

def record_payment(
    db: Session,
    student_id: int,
    amount: Decimal,
    method: str,
    school_id: int,
    notes: Optional[str] = None,
    auto_verify: bool = False,
    verified_by_id: Optional[int] = None,
) -> Tuple[Transaction, Optional[str]]:
    """
    Record a new payment for a student.
    
    Args:
        db: Database session
        student_id: The student receiving payment
        amount: Payment amount in Naira
        method: Payment method (BANK_TRANSFER, CASH, POS)
        school_id: School ID (for security validation)
        notes: Optional notes about the payment
        auto_verify: If True, mark as VERIFIED immediately (for cash/POS)
        verified_by_id: User ID who verified (required if auto_verify=True)
    
    Returns:
        Tuple of (Transaction, error_message)
        - Success: (transaction, None)
        - Failure: (None, "Error description")
    
    Security:
        The school_id is used to verify the student belongs to this school.
        This prevents cross-tenant data access.
    """
    # Validate payment method
    if method not in PaymentMethod.ALL:
        return None, f"Invalid payment method. Must be one of: {PaymentMethod.ALL}"
    
    # Validate amount
    if amount <= 0:
        return None, "Payment amount must be greater than zero"
    
    # Get student with security check
    student = db.query(Student).filter(
        Student.id == student_id,
        Student.school_id == school_id  # CRITICAL: Tenant isolation
    ).first()
    
    if not student:
        return None, "Student not found or access denied"
    
    # Get school for receipt number
    school = student.school
    
    # Generate receipt number
    current_year = get_wat_now().year
    receipt_number = generate_receipt_number(
        school_code=school.school_code,
        year=current_year,
        student_id=student.id,
        payment_sequence=student.next_payment_sequence
    )
    
    # Calculate balance changes
    balance_before = student.balance
    balance_after = balance_before - amount
    
    # Determine status
    if auto_verify:
        if not verified_by_id:
            return None, "verified_by_id required when auto_verify=True"
        status = TransactionStatus.VERIFIED
        verified_at = get_wat_now()
    else:
        status = TransactionStatus.PENDING
        verified_at = None
        verified_by_id = None
    
    # Create transaction
    transaction = Transaction(
        student_id=student_id,
        amount=amount,
        date=get_wat_now(),
        method=method,
        receipt_number=receipt_number,
        status=status,
        verified_by_id=verified_by_id,
        verified_at=verified_at,
        notes=notes,
        balance_before=balance_before,
        balance_after=balance_after,
    )
    
    db.add(transaction)
    
    # If auto-verified, update student balance immediately
    if auto_verify:
        student.amount_paid += amount
        student.next_payment_sequence += 1
        
        # Handle overpayment
        if student.balance < 0:
            student.credit_balance = abs(student.balance)
    
    db.commit()
    db.refresh(transaction)
    
    return transaction, None


# =============================================================================
# Payment Verification
# =============================================================================

# =============================================================================
# Payment Verification (Centralized)
# =============================================================================

def process_successful_payment(
    db: Session,
    transaction_id: int,
    verified_by_id: Optional[int] = None,
    send_pdf: bool = True
) -> Tuple[Transaction, Optional[str]]:
    """
    Single Source of Truth for processing a successful payment.
    
    Actions:
    1. Update Transaction Status -> VERIFIED
    2. Update Student Balance (decrease debt)
    3. Generate PDF Receipt
    4. Send WhatsApp Notification (Text + PDF)
    """
    from pathlib import Path
    from services.payments.receipt_generator import create_receipt_from_transaction, save_receipt_to_file
    from services.whatsapp_agent.whatsapp_client import whatsapp_client
    from config.settings import settings
    
    # 1. Fetch Transaction
    txn = db.query(Transaction).join(Student).filter(Transaction.id == transaction_id).first()
    if not txn:
        return None, "Transaction not found"
        
    student = txn.student
    school = student.school
    
    # 2. Update Status & Balance (Idempotent check)
    if txn.status != TransactionStatus.VERIFIED:
        txn.status = TransactionStatus.VERIFIED
        txn.verified_by_id = verified_by_id
        txn.verified_at = get_wat_now()
        
        # Update Balance
        student.amount_paid += txn.amount
        student.next_payment_sequence += 1
        
        if student.balance < 0:
            student.credit_balance = abs(student.balance)
            
        db.commit()
        db.refresh(txn)
    
    # 3. Generate PDF Receipt
    try:
        receipt_data = create_receipt_from_transaction(txn, student, school)
        
        # Define Receipts Directory (Relative to project root 'receipts')
        # Structure: <project_root>/receipts/
        RECEIPTS_DIR = Path(__file__).parent.parent.parent / "receipts"
        RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
        
        pdf_filename = f"receipt_{txn.receipt_number}.pdf"
        pdf_path = RECEIPTS_DIR / pdf_filename
        
        save_receipt_to_file(receipt_data, pdf_path)
        print(f"[INFO] Generated Receipt PDF: {pdf_path}")
        
        # 4. Send WhatsApp Notification
        # Construct Public URL
        app_url = "https://smartbursar.onrender.com"
        if hasattr(settings, 'APP_URL') and settings.APP_URL:
            app_url = settings.APP_URL.rstrip("/")
            
        pdf_url = f"{app_url}/receipts/{pdf_filename}"
        
        # Send Text
        whatsapp_client.send_text(
            student.parent_phone_primary,
            f"✅ *Payment Verified!*\n\n"
            f"Amount: ₦{txn.amount:,.2f}\n"
            f"Ref: {txn.receipt_number}\n"
            f"Student: {student.full_name}\n"
            f"New Balance: ₦{student.balance:,.2f}\n\n"
            f"Thank you! 🙏"
        )
        
        # Send PDF
        if send_pdf:
            whatsapp_client.send_document(
                student.parent_phone_primary,
                pdf_url,
                filename=pdf_filename,
                caption=f"🧾 Receipt {txn.receipt_number}"
            )
            print(f"[INFO] Sent Receipt PDF to {student.parent_phone_primary}")
            
    except Exception as e:
        print(f"[ERROR] Failed to generate/send receipt: {e}")
        # We don't fail the verification if receipt sending fails, but we log it.
        # Ideally, we might want to return a warning.
    
    return txn, None


def verify_payment(
    db: Session,
    transaction_id: int,
    school_id: int,
    verified_by_id: int,
    send_receipt: bool = True,
) -> Tuple[Transaction, Optional[str]]:
    """
    Admin verifies a payment (Dashboard Wrapper).
    Delegates to process_successful_payment.
    """
    # Security Check: Ensure transaction belongs to school
    txn = db.query(Transaction).join(Student).filter(
        Transaction.id == transaction_id,
        Student.school_id == school_id
    ).first()
    
    if not txn:
        return None, "Transaction not found or access denied"

    return process_successful_payment(db, transaction_id, verified_by_id, send_pdf=send_receipt)


# Deprecated internal helper - removed in favor of centralized logic
# def _send_receipt_to_parent(...)



def reject_payment(
    db: Session,
    transaction_id: int,
    school_id: int,
    rejected_by_id: int,
    reason: Optional[str] = None,
) -> Tuple[Transaction, Optional[str]]:
    """
    Reject a pending payment claim.
    
    Called when admin cannot verify a payment claim.
    Does NOT update student balance.
    
    Args:
        db: Database session
        transaction_id: The transaction to reject
        school_id: School ID (for security)
        rejected_by_id: User ID of the admin rejecting
        reason: Why the payment was rejected
    
    Returns:
        Tuple of (Transaction, error_message)
    """
    # Get transaction with security check
    transaction = db.query(Transaction).join(Student).filter(
        Transaction.id == transaction_id,
        Student.school_id == school_id
    ).first()
    
    if not transaction:
        return None, "Transaction not found or access denied"
    
    if transaction.status != TransactionStatus.PENDING:
        return None, f"Transaction is already {transaction.status}"
    
    # Update transaction
    transaction.status = TransactionStatus.REJECTED
    transaction.verified_by_id = rejected_by_id  # Track who rejected
    transaction.verified_at = get_wat_now()
    
    if reason:
        existing_notes = transaction.notes or ""
        transaction.notes = f"{existing_notes}\n\nREJECTED: {reason}".strip()
    
    db.commit()
    db.refresh(transaction)
    
    return transaction, None


# =============================================================================
# Query Helpers
# =============================================================================

def get_pending_payments(
    db: Session,
    school_id: int,
) -> list[Transaction]:
    """
    Get all pending payments for a school (awaiting verification).
    
    Used for the admin dashboard "Pending Verification" queue.
    """
    return db.query(Transaction).join(Student).filter(
        Student.school_id == school_id,
        Transaction.status == TransactionStatus.PENDING
    ).order_by(Transaction.date.desc()).all()


def get_student_payment_history(
    db: Session,
    student_id: int,
    school_id: int,
) -> list[Transaction]:
    """
    Get all payments for a specific student.
    
    Security: Validates school_id before returning data.
    """
    return db.query(Transaction).join(Student).filter(
        Transaction.student_id == student_id,
        Student.school_id == school_id  # Security check
    ).order_by(Transaction.date.desc()).all()


def get_total_collected_today(db: Session, school_id: int) -> Decimal:
    """
    Get total verified payments for today.
    
    Used for dashboard metrics.
    """
    from sqlalchemy import func
    
    today = get_wat_now().date()
    
    result = db.query(func.sum(Transaction.amount)).join(Student).filter(
        Student.school_id == school_id,
        Transaction.status == TransactionStatus.VERIFIED,
        func.date(Transaction.date) == today
    ).scalar()
    
    return result or Decimal("0")
