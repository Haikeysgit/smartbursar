"""
=============================================================================
PROJECT ATLAS - Student Model
=============================================================================
The core of the system - students and their fee balances.

CRITICAL Multi-Tenant Rule:
    Every query for students MUST include: WHERE school_id = ?
    Never query students without filtering by school!

Phone Numbers:
    Stored in E.164 format: +2348012345678
    Always validated before storage.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, 
    Numeric, String, Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.school import School
    from models.transaction import Transaction
    from models.message_log import MessageLog


class Student(Base, TimestampMixin):
    """
    A student enrolled in a school.
    
    The balance is automatically calculated as:
        balance = fees_total_due - amount_paid
    
    Payment status is derived from balance:
        - OWING: balance > 0 and amount_paid == 0
        - PARTIAL: balance > 0 and amount_paid > 0
        - PAID: balance == 0
        - OVERPAID: balance < 0 (they paid too much)
    """
    __tablename__ = "students"
    
    # -------------------------------------------------------------------------
    # Primary Key
    # -------------------------------------------------------------------------
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # -------------------------------------------------------------------------
    # School Link (CRITICAL - NEVER QUERY WITHOUT THIS!)
    # -------------------------------------------------------------------------
    school_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # Fast lookups by school
        comment="CRITICAL: Always filter by this!"
    )
    
    # -------------------------------------------------------------------------
    # Student Identity
    # -------------------------------------------------------------------------
    full_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    class_level: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="e.g., 'JSS 2', 'Primary 4', 'SS 3'"
    )
    
    # -------------------------------------------------------------------------
    # Parent Contact (E.164 format)
    # -------------------------------------------------------------------------
    parent_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    parent_phone_primary: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="E.164 format: +2348012345678"
    )
    parent_phone_secondary: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Backup number (for divorced parents, etc.)"
    )
    
    # -------------------------------------------------------------------------
    # Financial Data
    # -------------------------------------------------------------------------
    fees_total_due: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),  # Up to 9,999,999,999.99
        nullable=False,
        comment="Total fees for the term"
    )
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
        comment="Cumulative amount paid (updated on each payment)"
    )
    due_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="When full payment is expected"
    )
    
    # Credit for overpayments
    credit_balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
        comment="Applied to next term if they overpaid"
    )
    
    # -------------------------------------------------------------------------
    # Engagement Tracking (for archive detection)
    # -------------------------------------------------------------------------
    evasion_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ENGAGED",
        comment="ENGAGED, LIKELY_ARCHIVED, POSSIBLY_MUTED, BLOCKED, SMS_ONLY"
    )
    engagement_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=50,
        comment="0-100 based on read rate, replies, payment history"
    )
    consecutive_unread_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="How many messages in a row not read"
    )
    last_interaction_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time parent replied or we confirmed read"
    )
    
    # -------------------------------------------------------------------------
    # Payment Tracking
    # -------------------------------------------------------------------------
    next_payment_sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="For receipt numbers: 01, 02, 03..."
    )
    
    # -------------------------------------------------------------------------
    # Flags
    # -------------------------------------------------------------------------
    is_vip: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Principal's kid, big donor, etc. (extra care needed)"
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Admin notes (e.g., 'Divorced parents - send to both')"
    )
    refund_processed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if overpayment has been refunded or credited"
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if student has left or graduated (stops messaging)"
    )
    
    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    school: Mapped["School"] = relationship(
        "School",
        back_populates="students",
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="student",
        cascade="all, delete-orphan",
        order_by="Transaction.date.desc()",
    )
    messages: Mapped[list["MessageLog"]] = relationship(
        "MessageLog",
        back_populates="student",
        cascade="all, delete-orphan",
        order_by="MessageLog.sent_at.desc()",
    )
    
    # -------------------------------------------------------------------------
    # Computed Properties
    # -------------------------------------------------------------------------
    @property
    def balance(self) -> Decimal:
        """
        Current balance (what they still owe).
        
        Positive = they owe money
        Zero = fully paid
        Negative = they overpaid
        """
        return self.fees_total_due - self.amount_paid
    
    @property
    def payment_status(self) -> str:
        """
        Derived payment status based on balance.
        
        Returns one of: OWING, PARTIAL, PAID, OVERPAID
        """
        balance = self.balance
        
        if balance < 0:
            return "OVERPAID"
        elif balance == 0:
            return "PAID"
        elif self.amount_paid > 0:
            return "PARTIAL"
        else:
            return "OWING"
    
    @property
    def payment_percentage(self) -> float:
        """How much of the total they've paid (0.0 to 1.0+)."""
        if self.fees_total_due == 0:
            return 1.0
        return float(self.amount_paid / self.fees_total_due)
    
    @property
    def is_overdue(self) -> bool:
        """True if past due date and still has balance."""
        return self.balance > 0 and date.today() > self.due_date
    
    @property
    def days_until_due(self) -> int:
        """Days until due date (negative if overdue)."""
        return (self.due_date - date.today()).days
    
    # -------------------------------------------------------------------------
    # Methods
    # -------------------------------------------------------------------------
    def record_payment(self, amount: Decimal) -> None:
        """
        Record a payment and update amount_paid.
        
        Note: This just updates the student record. The actual Transaction
        should be created separately by the payment service.
        """
        self.amount_paid += amount
        self.next_payment_sequence += 1
        
        # Handle overpayment
        if self.balance < 0:
            self.credit_balance = abs(self.balance)
