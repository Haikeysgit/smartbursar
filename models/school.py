"""
=============================================================================
PROJECT ATLAS - School Model (The Tenant)
=============================================================================
Each school is a separate tenant in our multi-tenant system.
A school should NEVER see another school's data.

CRITICAL:
    - school_code is used in receipt numbers (e.g., "ABC-2026-00247-01")
    - logo_base64 stores the school logo for receipts (keep under 50KB)
    - subscription_end_date controls if the bot keeps working
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.user import User
    from models.student import Student


class School(Base, TimestampMixin):
    """
    A school (tenant) in the system.
    
    This is the core of multi-tenancy. Every student, transaction, and message
    belongs to exactly one school.
    """
    __tablename__ = "schools"
    
    # -------------------------------------------------------------------------
    # Primary Key
    # -------------------------------------------------------------------------
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # -------------------------------------------------------------------------
    # Identity (Used in receipts and UI)
    # -------------------------------------------------------------------------
    school_code: Mapped[str] = mapped_column(
        String(10), 
        unique=True, 
        nullable=False,
        comment="3-letter code used in receipts, e.g., 'ABC'"
    )
    school_name: Mapped[str] = mapped_column(
        String(200), 
        nullable=False,
        comment="Full school name, e.g., 'ABC Primary School'"
    )
    address: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Full address for receipts"
    )
    phone: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="E.164 format: +2348012345678"
    )
    
    # -------------------------------------------------------------------------
    # Admin/Secretary Contact (for payment receipt routing)
    # -------------------------------------------------------------------------
    admin_whatsapp_number: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Secretary/Admin phone for payment alerts (optional, falls back to owner)"
    )
    
    # -------------------------------------------------------------------------
    # Country (for phone number parsing)
    # -------------------------------------------------------------------------
    country_code: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        default="NG",
        comment="ISO 3166-1 alpha-2: NG, GH, KE, etc."
    )
    
    # -------------------------------------------------------------------------
    # Bank Details (for receipts and payment instructions)
    # -------------------------------------------------------------------------
    bank_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="e.g., 'GTBank', 'First Bank'"
    )
    account_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    account_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Account holder name (usually school name)"
    )
    
    # -------------------------------------------------------------------------
    # Logo (Base64 encoded, for receipts)
    # -------------------------------------------------------------------------
    logo_base64: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Base64 encoded logo image (PNG/JPG, max 50KB)"
    )
    
    # -------------------------------------------------------------------------
    # Subscription Management
    # -------------------------------------------------------------------------
    plan_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="TERMLY",
        comment="TERMLY or YEARLY"
    )
    subscription_end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Bot stops working after this date"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
        comment="ACTIVE or SUSPENDED"
    )
    
    # -------------------------------------------------------------------------
    # Settings (JSON for flexibility)
    # -------------------------------------------------------------------------
    settings_config: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Flexible settings: reminder_hour, term_start_date, etc."
    )
    
    # -------------------------------------------------------------------------
    # Cost Control
    # -------------------------------------------------------------------------
    messages_sent_today: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Reset daily, for rate limiting"
    )
    monthly_spend: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
        comment="Running total for the month in Naira"
    )
    
    # -------------------------------------------------------------------------
    # Fair Usage Policy
    # -------------------------------------------------------------------------
    debtor_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=150,
        comment="Maximum debtors covered by license (default 150)"
    )
    
    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    students: Mapped[list["Student"]] = relationship(
        "Student",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    fee_structures: Mapped[list["FeeStructure"]] = relationship(
        "FeeStructure",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    
    # -------------------------------------------------------------------------
    # Computed Properties
    # -------------------------------------------------------------------------
    @property
    def is_active(self) -> bool:
        """True if school is active AND subscription hasn't expired."""
        return (
            self.status == "ACTIVE" 
            and self.subscription_end_date >= date.today()
        )
    
    @property
    def days_remaining(self) -> int:
        """Days until subscription expires (negative if expired)."""
        return (self.subscription_end_date - date.today()).days
    
    @property
    def bank_details_formatted(self) -> str:
        """Formatted bank details for messages."""
        return f"{self.bank_name}\n{self.account_number}\n{self.account_name}"
