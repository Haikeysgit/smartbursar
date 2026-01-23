"""
=============================================================================
PROJECT ATLAS - Message Log Model
=============================================================================
Tracks every message sent to and received from parents.

Critical for:
    1. Debugging "I didn't get the message" complaints
    2. Archive detection (delivered but not read)
    3. Cost tracking (WhatsApp vs SMS costs)
    4. Audit trail
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime, ForeignKey, Integer, Numeric, String, Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base

if TYPE_CHECKING:
    from models.student import Student


class MessageLog(Base):
    """
    Log of all messages sent/received.
    
    Status progression for outgoing:
        QUEUED → SENT → DELIVERED → READ
                   ↓
                 FAILED
    """
    __tablename__ = "message_logs"
    
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
    # Denormalized for faster queries (avoid join to get school_id)
    school_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # -------------------------------------------------------------------------
    # Message Type
    # -------------------------------------------------------------------------
    channel: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="WHATSAPP, SMS"
    )
    direction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="OUTGOING (we sent) or INCOMING (parent replied)"
    )
    message_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="REMINDER, RECEIPT, REPLY, PAYMENT_CLAIM, etc."
    )
    
    # -------------------------------------------------------------------------
    # Content
    # -------------------------------------------------------------------------
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    
    # -------------------------------------------------------------------------
    # Status Tracking
    # -------------------------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="QUEUED",
        comment="QUEUED, SENT, DELIVERED, READ, FAILED"
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When we sent/received the message"
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When parent opened the message (WhatsApp only)"
    )
    
    # -------------------------------------------------------------------------
    # Cost Tracking
    # -------------------------------------------------------------------------
    cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        default=0,
        comment="Cost in Naira (WhatsApp ~₦0.50, SMS ~₦3)"
    )
    
    # -------------------------------------------------------------------------
    # Sender Tracking (for rotation)
    # -------------------------------------------------------------------------
    sender_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Which number we sent from (for rotation tracking)"
    )
    
    # -------------------------------------------------------------------------
    # Error Tracking
    # -------------------------------------------------------------------------
    failure_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="If FAILED, why?"
    )
    
    # External reference (Twilio message SID, etc.)
    external_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Twilio SID or other API reference"
    )
    
    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    student: Mapped["Student"] = relationship(
        "Student",
        back_populates="messages",
    )
    
    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------
    @property
    def is_delivered(self) -> bool:
        """True if message was delivered."""
        return self.status in ("DELIVERED", "READ")
    
    @property
    def is_read(self) -> bool:
        """True if message was read by parent."""
        return self.status == "READ"
    
    @property
    def is_failed(self) -> bool:
        """True if message failed to send."""
        return self.status == "FAILED"
    
    @property
    def hours_since_sent(self) -> float:
        """Hours since message was sent."""
        delta = datetime.now(self.sent_at.tzinfo) - self.sent_at
        return delta.total_seconds() / 3600


# =============================================================================
# Constants
# =============================================================================
class MessageChannel:
    """Valid message channels."""
    WHATSAPP = "WHATSAPP"
    SMS = "SMS"
    
    ALL = [WHATSAPP, SMS]


class MessageDirection:
    """Message direction."""
    OUTGOING = "OUTGOING"  # We sent it
    INCOMING = "INCOMING"  # Parent replied
    
    ALL = [OUTGOING, INCOMING]


class MessageType:
    """Types of messages."""
    REMINDER = "REMINDER"
    RECEIPT = "RECEIPT"
    REPLY = "REPLY"
    PAYMENT_CLAIM = "PAYMENT_CLAIM"
    PROMISE_TO_PAY = "PROMISE_TO_PAY"
    DISPUTE = "DISPUTE"
    GENERAL = "GENERAL"
    
    ALL = [REMINDER, RECEIPT, REPLY, PAYMENT_CLAIM, PROMISE_TO_PAY, DISPUTE, GENERAL]


class MessageStatus:
    """Message delivery status."""
    QUEUED = "QUEUED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"
    FAILED = "FAILED"
    
    ALL = [QUEUED, SENT, DELIVERED, READ, FAILED]
