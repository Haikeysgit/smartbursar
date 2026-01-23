"""
=============================================================================
PROJECT ATLAS - Mock Message Sender
=============================================================================
Phase 1 implementation: Prints messages to console instead of sending.

This allows full development and testing without API costs.
When ready for production, swap this for the real Twilio sender.

The mock sender:
    - Prints messages with [MOCK WHATSAPP] or [MOCK SMS] prefix
    - Simulates delivery/read statuses
    - Logs to database just like the real sender would
    - Respects cost limits (for testing the logic)
"""

import random
from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from config.settings import settings
from models.message_log import (
    MessageLog, MessageChannel, MessageDirection, 
    MessageType, MessageStatus
)
from models.student import Student
from utils.date_helpers import get_wat_now


def safe_print(text: str) -> None:
    """Print text safely on Windows by replacing Unicode chars."""
    # Replace problematic characters for Windows console
    safe_text = text.replace("\u20a6", "N")  # Naira symbol
    safe_text = safe_text.replace("\u2713", "[OK]")  # Checkmark
    try:
        print(safe_text)
    except UnicodeEncodeError:
        print(safe_text.encode('ascii', 'replace').decode('ascii'))


# =============================================================================
# Cost Constants (for cost tracking even in mock mode)
# =============================================================================

WHATSAPP_COST_PER_MESSAGE = Decimal("0.50")  # Naira
SMS_COST_PER_MESSAGE = Decimal("3.00")       # Naira


# =============================================================================
# Mock Sender
# =============================================================================

class MockMessageSender:
    """
    Mock message sender for Phase 1 development.
    
    Prints messages to console and logs to database.
    Simulates random delivery/read statuses for testing.
    """
    
    def __init__(self, db: Session):
        """
        Initialize the mock sender.
        
        Args:
            db: Database session for logging messages
        """
        self.db = db
    
    def send_whatsapp(
        self,
        to_phone: str,
        message: str,
        student_id: int,
        school_id: int,
        message_type: str = MessageType.REMINDER,
    ) -> Tuple[MessageLog, Optional[str]]:
        """
        Mock send a WhatsApp message.
        
        Args:
            to_phone: Recipient phone (E.164 format)
            message: Message content
            student_id: Student this message is about
            school_id: School sending the message
            message_type: Type of message (REMINDER, RECEIPT, etc.)
        
        Returns:
            Tuple of (MessageLog, error_message)
        """
        # Print to console with mock prefix
        safe_print("\n" + "="*60)
        safe_print(f"[MOCK WHATSAPP] To: {to_phone}")
        safe_print("-"*60)
        safe_print(message)
        safe_print("="*60 + "\n")
        
        # Simulate delivery status (for testing archive detection)
        simulated_status = self._simulate_delivery_status()
        
        # Create log entry
        log = MessageLog(
            student_id=student_id,
            school_id=school_id,
            channel=MessageChannel.WHATSAPP,
            direction=MessageDirection.OUTGOING,
            message_type=message_type,
            content=message,
            status=simulated_status,
            sent_at=get_wat_now(),
            delivered_at=get_wat_now() if simulated_status in ["DELIVERED", "READ"] else None,
            read_at=get_wat_now() if simulated_status == "READ" else None,
            cost=WHATSAPP_COST_PER_MESSAGE,
            sender_number="+2340000000000",  # Mock number
            external_id=f"mock_wa_{random.randint(10000, 99999)}",
        )
        
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        
        return log, None
    
    def send_sms(
        self,
        to_phone: str,
        message: str,
        student_id: int,
        school_id: int,
        message_type: str = MessageType.REMINDER,
    ) -> Tuple[MessageLog, Optional[str]]:
        """
        Mock send an SMS message.
        
        Args:
            to_phone: Recipient phone (E.164 format)
            message: Message content
            student_id: Student this message is about
            school_id: School sending the message
            message_type: Type of message
        
        Returns:
            Tuple of (MessageLog, error_message)
        """
        # SMS has character limit - truncate if needed
        if len(message) > 160:
            # Show warning in mock mode
            print(f"[WARNING] SMS truncated from {len(message)} to 160 chars")
            message = message[:157] + "..."
        
        # Print to console
        safe_print("\n" + "="*60)
        safe_print(f"[MOCK SMS] To: {to_phone}")
        safe_print("-"*60)
        safe_print(message)
        safe_print("="*60 + "\n")
        
        # SMS doesn't have read receipts - only SENT/DELIVERED/FAILED
        simulated_status = random.choice(["SENT", "DELIVERED", "DELIVERED"])
        
        # Create log entry
        log = MessageLog(
            student_id=student_id,
            school_id=school_id,
            channel=MessageChannel.SMS,
            direction=MessageDirection.OUTGOING,
            message_type=message_type,
            content=message,
            status=simulated_status,
            sent_at=get_wat_now(),
            delivered_at=get_wat_now() if simulated_status == "DELIVERED" else None,
            read_at=None,  # SMS has no read receipts
            cost=SMS_COST_PER_MESSAGE,
            sender_number="SCHOOL",  # SMS sender ID
            external_id=f"mock_sms_{random.randint(10000, 99999)}",
        )
        
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        
        return log, None
    
    def _simulate_delivery_status(self) -> str:
        """
        Simulate random delivery status for testing.
        
        Distribution (for realistic testing):
            - 60% READ (engaged parents)
            - 25% DELIVERED (possible archive)
            - 10% SENT (pending delivery)
            - 5% FAILED (blocked/wrong number)
        """
        roll = random.random()
        
        if roll < 0.60:
            return MessageStatus.READ
        elif roll < 0.85:
            return MessageStatus.DELIVERED
        elif roll < 0.95:
            return MessageStatus.SENT
        else:
            return MessageStatus.FAILED


# =============================================================================
# Factory Function
# =============================================================================

def get_message_sender(db: Session):
    """
    Get the appropriate message sender based on settings.
    
    Modes:
        - MOCK_MODE=True: Prints to console (testing)
        - MOCK_MODE=False + WHATSAPP_MODE=True: Uses WhatsApp Web (pywhatkit)
        - MOCK_MODE=False + WHATSAPP_MODE=False: Uses Twilio (production)
    """
    if settings.MOCK_MODE:
        return MockMessageSender(db)
    
    # Check for WhatsApp mode
    whatsapp_mode = getattr(settings, 'WHATSAPP_MODE', False)
    if whatsapp_mode:
        from services.messaging.whatsapp_sender import WhatsAppSender
        return WhatsAppSender(db)
    
    # Default: Twilio (not implemented yet)
    raise NotImplementedError("Twilio sender not yet implemented. Set MOCK_MODE=True or WHATSAPP_MODE=True")

