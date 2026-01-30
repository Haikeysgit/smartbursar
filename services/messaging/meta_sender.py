"""
=============================================================================
SmartBursar - Meta WhatsApp API Sender Adapter
=============================================================================
Wraps the singleton `whatsapp_client` to conform to the sender interface
expected by the reminder engine.
"""

from typing import Tuple, Optional
from sqlalchemy.orm import Session
from services.whatsapp_agent.whatsapp_client import whatsapp_client
from models.message_log import (
    MessageLog, MessageChannel, MessageDirection, 
    MessageType, MessageStatus
)
from utils.date_helpers import get_wat_now

class MetaWhatsAppSender:
    """Adapter for the official Meta WhatsApp Cloud API client."""
    
    def __init__(self, db: Session):
        self.db = db
        
    def send_whatsapp(
        self,
        to_phone: str,
        message: str,
        student_id: int,
        school_id: int,
        message_type: str = MessageType.REMINDER,
        is_template: bool = False,
        template_name: str = None,
    ) -> Tuple[MessageLog, Optional[str]]:
        """
        Send a WhatsApp message using the Meta Cloud API.
        If is_template is True, uses template_name (defaulting to message as content placeholder logic if needed, 
        but for hello_world there are no params).
        """
        # Call the actual client
        if is_template and template_name:
            result = whatsapp_client.send_template(to_phone, template_name)
            content_logged = f"[TEMPLATE: {template_name}]"
        else:
            result = whatsapp_client.send_text(to_phone, message)
            content_logged = message
        
        status = MessageStatus.SENT if result["success"] else MessageStatus.FAILED
        error_msg = result.get("error") if not result["success"] else None
        external_id = "unknown"
        
        if result["success"]:
            # Meta returns a message ID structure
            try:
                external_id = result["data"]["messages"][0]["id"]
            except (KeyError, IndexError):
                pass
        
        # Log to database
        log = MessageLog(
            student_id=student_id,
            school_id=school_id,
            channel=MessageChannel.WHATSAPP,
            direction=MessageDirection.OUTGOING,
            message_type=message_type,
            content=content_logged,
            status=status,
            sent_at=get_wat_now(),
            cost=0.50, # Estimated cost placeholder
            sender_number="META_API",
            external_id=external_id,
        )
        
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        
        return log, error_msg
