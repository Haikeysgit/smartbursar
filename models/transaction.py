"""
=============================================================================
PROJECT ATLAS - Transaction Model
=============================================================================
Records every payment made by a parent.

Each payment generates a transaction with:
    - Unique receipt number (ABC-2026-00247-01)
    - Verification status (PENDING → VERIFIED or REJECTED)
    - Method (BANK_TRANSFER, CASH, POS)

The receipt_number format is:
    {school_code}-{year}-{student_id:05d}-{payment_seq:02d}
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime, ForeignKey, Integer, Numeric, String, Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.student import Student
    from models.user import User


class Transaction(Base, TimestampMixin):
    """
    A payment transaction for a student.
    
    Status workflow:
        PENDING → Admin reviews proof → VERIFIED or REJECTED
    
    For admin-logged payments (cash/POS), status can be VERIFIED immediately.
    """
    __tablename__ = "transactions"
    
    # -------------------------------------------------------------------------
    # Primary Key
    # -------------------------------------------------------------------------
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # -------------------------------------------------------------------------
    # Links
    # -------------------------------------------------------------------------
    student_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # -------------------------------------------------------------------------
    # Payment Details
    # -------------------------------------------------------------------------
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When payment was made (not when logged)"
    )
    method: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="BANK_TRANSFER, CASH, POS, CHEQUE"
    )
    
    # -------------------------------------------------------------------------
    # Receipt
    # -------------------------------------------------------------------------
    receipt_number: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        unique=True,
        index=True,
        comment="Format: ABC-2026-00247-01"
    )
    
    # -------------------------------------------------------------------------
    # Verification
    # -------------------------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        comment="PENDING, VERIFIED, REJECTED"
    )
    verified_by_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Admin who verified this payment"
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # -------------------------------------------------------------------------
    # Notes & Proof
    # -------------------------------------------------------------------------
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Admin notes or parent's message"
    )
    proof_description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Description of proof provided (bank alert, receipt photo, etc.)"
    )
    
    # -------------------------------------------------------------------------
    # Duplicate Receipt Detection (SECURITY)
    # -------------------------------------------------------------------------
    receipt_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="SHA-256 hash of receipt file for duplicate detection"
    )
    receipt_reference: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Transaction reference/ID from receipt (for duplicate detection)"
    )
    
    # -------------------------------------------------------------------------
    # Snapshot of balance at time of payment (for receipts)
    # -------------------------------------------------------------------------
    balance_before: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Student's balance before this payment"
    )
    balance_after: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Student's balance after this payment"
    )
    
    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    student: Mapped["Student"] = relationship(
        "Student",
        back_populates="transactions",
    )
    verified_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[verified_by_id],
    )
    
    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------
    @property
    def is_verified(self) -> bool:
        """True if payment has been verified."""
        return self.status == "VERIFIED"
    
    @property
    def is_pending(self) -> bool:
        """True if payment is awaiting verification."""
        return self.status == "PENDING"
    
    @property
    def is_rejected(self) -> bool:
        """True if payment was rejected."""
        return self.status == "REJECTED"


# =============================================================================
# Payment Methods (Constants)
# =============================================================================
class PaymentMethod:
    """Valid payment methods."""
    BANK_TRANSFER = "BANK_TRANSFER"
    CASH = "CASH"
    POS = "POS"
    CHEQUE = "CHEQUE"
    
    ALL = [BANK_TRANSFER, CASH, POS, CHEQUE]


class TransactionStatus:
    """Valid transaction statuses."""
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    
    ALL = [PENDING, VERIFIED, REJECTED]
