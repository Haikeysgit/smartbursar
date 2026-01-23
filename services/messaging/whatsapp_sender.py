"""
=============================================================================
SmartBursar - WhatsApp Cloud API Sender
=============================================================================
Uses the official Meta WhatsApp Cloud API to send messages.

This is the production-ready sender that integrates with the dashboard
and scheduler for sending fee reminders.

Environment Variables Required:
    - WHATSAPP_TOKEN: Meta Graph API access token
    - WHATSAPP_PHONE_NUMBER_ID: WhatsApp Business Phone Number ID
"""

import os
import logging
import requests
import time
from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from models.message_log import (
    MessageLog, MessageChannel, MessageDirection, 
    MessageType, MessageStatus
)
from utils.date_helpers import get_wat_now

logger = logging.getLogger(__name__)

# WhatsApp is free (first 1000 conversations/month)
WHATSAPP_COST_PER_MESSAGE = Decimal("0.00")


class WhatsAppSender:
    """
    WhatsApp Cloud API sender for SmartBursar.
    
    Uses the official Meta WhatsApp Business Cloud API to send messages.
    Works with the dashboard and scheduler for automated reminders.
    """
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self, db: Session):
        self.db = db
        self.token = os.getenv("WHATSAPP_TOKEN", "")
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        
        self.is_available = bool(self.token and self.phone_number_id)
        
        if not self.is_available:
            logger.warning(
                "WhatsApp Cloud API not configured. "
                "Set WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID in .env"
            )
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def send_whatsapp(
        self,
        to_phone: str,
        message: str,
        student_id: int,
        school_id: int,
        message_type: str = MessageType.REMINDER,
        **kwargs,
    ) -> Tuple[Optional[MessageLog], Optional[str]]:
        """
        Send a WhatsApp message via Cloud API.
        
        Args:
            to_phone: Recipient phone (E.164 format, e.g., +2348012345678)
            message: Message content
            student_id: Student this message is about
            school_id: School sending the message
            message_type: Type of message
        
        Returns:
            Tuple of (MessageLog, error_message)
        """
        if not self.is_available:
            return None, "WhatsApp Cloud API not configured"
        
        # Clean phone number (API wants digits only, no +)
        clean_phone = self._clean_phone(to_phone)
        
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message
            }
        }
        
        try:
            logger.info(f"Sending WhatsApp to {clean_phone}...")
            
            response = requests.post(
                url, 
                headers=self.headers, 
                json=payload, 
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                message_id = result.get("messages", [{}])[0].get("id", "unknown")
                
                logger.info(f"WhatsApp sent to {clean_phone}: {message_id}")
                
                # Create success log entry
                log = MessageLog(
                    student_id=student_id,
                    school_id=school_id,
                    channel=MessageChannel.WHATSAPP,
                    direction=MessageDirection.OUTGOING,
                    message_type=message_type,
                    content=message,
                    status=MessageStatus.SENT,
                    sent_at=get_wat_now(),
                    cost=WHATSAPP_COST_PER_MESSAGE,
                    sender_number=self.phone_number_id,
                    external_id=message_id,
                )
                
                self.db.add(log)
                self.db.commit()
                self.db.refresh(log)
                
                return log, None
            else:
                # API returned an error
                error_data = response.json().get("error", {})
                error_msg = error_data.get("message", f"HTTP {response.status_code}")
                
                logger.error(f"WhatsApp API error: {error_msg}")
                
                # Create failed log entry
                log = MessageLog(
                    student_id=student_id,
                    school_id=school_id,
                    channel=MessageChannel.WHATSAPP,
                    direction=MessageDirection.OUTGOING,
                    message_type=message_type,
                    content=message,
                    status=MessageStatus.FAILED,
                    sent_at=get_wat_now(),
                    cost=Decimal("0.00"),
                    sender_number=self.phone_number_id,
                    external_id=f"failed_{int(time.time())}",
                )
                
                self.db.add(log)
                self.db.commit()
                
                return log, error_msg
                
        except Exception as e:
            error_msg = f"Failed to send WhatsApp: {str(e)}"
            logger.error(error_msg)
            
            # Log the failed attempt
            log = MessageLog(
                student_id=student_id,
                school_id=school_id,
                channel=MessageChannel.WHATSAPP,
                direction=MessageDirection.OUTGOING,
                message_type=message_type,
                content=message,
                status=MessageStatus.FAILED,
                sent_at=get_wat_now(),
                cost=Decimal("0.00"),
                sender_number=self.phone_number_id or "unknown",
                external_id=f"error_{int(time.time())}",
            )
            
            self.db.add(log)
            self.db.commit()
            
            return log, error_msg
    
    def _clean_phone(self, phone: str) -> str:
        """Clean phone number for API (digits only, no +)."""
        phone = phone.strip()
        
        # Remove +, spaces, dashes
        phone = phone.replace("+", "").replace(" ", "").replace("-", "")
        
        # Handle Nigerian numbers starting with 0
        if phone.startswith("0") and len(phone) == 11:
            phone = "234" + phone[1:]
        
        return phone


def get_whatsapp_sender(db: Session) -> WhatsAppSender:
    """Factory function to get WhatsApp sender."""
    return WhatsAppSender(db)
