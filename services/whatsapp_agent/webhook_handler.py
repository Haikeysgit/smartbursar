"""
=============================================================================
SmartBursar - WhatsApp Webhook Handler (Router)
=============================================================================
FastAPI endpoints for Meta WhatsApp Cloud API webhooks.
"""

import os
import logging
import hmac
import hashlib
from typing import Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, Request, Query, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address

load_dotenv()

from .whatsapp_client import whatsapp_client
from .verification_pipeline import verification_pipeline
from .conversation_manager import conversation_manager
from config.database import get_db_context
from models.student import Student
from models.school import School

logger = logging.getLogger(__name__)

# Security: Get app secret for webhook signature verification
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Initialize Router
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# Settings (Reciepts dir is now mounted in main.py, but we need the path here for logic)
RECEIPTS_DIR = Path(__file__).parent.parent.parent / "receipts"
RECEIPTS_DIR.mkdir(exist_ok=True)


# =============================================================================
# Webhook Signature Verification Helper
# =============================================================================

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify the X-Hub-Signature-256 header from Meta."""
    if not WHATSAPP_APP_SECRET:
        if ENVIRONMENT == "development":
            logger.warning("WHATSAPP_APP_SECRET not set - skipping signature verification (dev only)")
            return True
        return False
    
    if not signature or not signature.startswith("sha256="):
        return False
    
    expected = "sha256=" + hmac.new(
        WHATSAPP_APP_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected)


# =============================================================================
# Identity Gatekeeper
# =============================================================================

def get_user_context(phone_number: str) -> Dict[str, Any]:
    """
    Step 1: IDENTITY & CONTEXT (The Gatekeeper)
    """
    # Normalize: Ensure we have a clean string
    raw_phone = phone_number.strip()
    
    # Create variations to search (Robust Matching)
    # 1. As received (e.g. "23480...")
    # 2. With plus (e.g. "+23480...")
    # 3. Without plus (e.g. "23480...")
    variations = {raw_phone}
    if not raw_phone.startswith("+"):
        variations.add(f"+{raw_phone}")
    else:
        variations.add(raw_phone.lstrip("+"))
    
    formatted_phone = f"+{raw_phone}" if not raw_phone.startswith("+") else raw_phone
    
    if formatted_phone in verification_pipeline.admin_pending:
        return {"user_type": "ADMIN", "students": [], "schools": []}

    with get_db_context() as db:
        students = db.query(Student).filter(
            (Student.parent_phone_primary.in_(variations)) | 
            (Student.parent_phone_secondary.in_(variations))
        ).all()
        
        if not students:
            # Debugging: Return formatted phone so we can tell user what we saw
            return {"user_type": "NEW_USER", "students": [], "schools": [], "debug_phone": formatted_phone}
        
        # Prepare safe data dictionaries (avoid DetachedInstanceError)
        safe_students = []
        safe_schools = []
        school_map = {}
        
        for student in students:
            # Load school if needed
            if student.school_id not in school_map:
                school = db.query(School).get(student.school_id)
                if school:
                    school_map[student.school_id] = school
            
            # Serialize student to dict including computed properties
            safe_students.append({
                "full_name": student.full_name,
                "class_level": student.class_level,
                "fees_total_due": float(student.fees_total_due),
                "amount_paid": float(student.amount_paid),
                "balance": float(student.balance),
                "payment_status": student.payment_status,
                "due_date": student.due_date,
                "days_until_due": student.days_until_due
            })
        
        # Serialize schools to dicts
        for school in school_map.values():
            safe_schools.append({
                "school_name": school.school_name,
                "bank_name": school.bank_name,
                "account_number": school.account_number,
                "account_name": school.account_name,
                "phone": school.phone
            })

        return {
            "user_type": "EXISTING_PARENT", 
            "students": safe_students, 
            "schools": safe_schools
        }


# =============================================================================
# Webhook Verification (GET - Meta Handshake)
# =============================================================================

@router.get("/webhook")
@limiter.limit("60/minute")
async def verify_webhook(request: Request,
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge")
):
    """Meta webhook verification endpoint."""
    if not hub_mode or not hub_verify_token or not hub_challenge:
        raise HTTPException(status_code=400, detail="Missing verification parameters")
    
    result = whatsapp_client.verify_webhook(hub_mode, hub_verify_token, hub_challenge)
    
    if result:
        return PlainTextResponse(content=result)
    
    raise HTTPException(status_code=403, detail="Verification failed")


# =============================================================================
# Incoming Messages (POST - Message Handler - THE ROUTER)
# =============================================================================

@router.post("/webhook")
@limiter.limit("60/minute")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handle incoming WhatsApp messages.
    Implements Identity Gatekeeper -> Intent Router -> Action.
    """
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    
    if not verify_webhook_signature(body, signature):
        logger.warning(f"Invalid webhook signature from {request.client.host}")
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    try:
        import json
        body_json = json.loads(body)
        
        entry = body_json.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        
        # FIX: Safety Check for Status Updates
        if "messages" not in value:
             return {"status": "ignored"}
             
        messages = value.get("messages", [])
        
        if not messages:
            return {"status": "ok"}
        
        message = messages[0]
        sender = message.get("from")
        message_type = message.get("type")
        
        contacts = value.get("contacts", [{}])
        sender_profile_name = contacts[0].get("profile", {}).get("name", "Unknown")
        
        logger.info(f"Incoming message from {sender} ({sender_profile_name}): type={message_type}")
        
        context = get_user_context(sender)
        user_type = context["user_type"]
        
        if user_type == "NEW_USER":
            debug_phone = context.get("debug_phone", sender)
            background_tasks.add_task(
                whatsapp_client.send_text,
                sender,
                f"🚫 I do not recognize this number ({debug_phone}). Please contact your School Admin to register."
            )
            return {"status": "ok"}
            
        background_tasks.add_task(
            route_message,
            sender=sender,
            message=message,
            context=context,
            sender_profile_name=sender_profile_name
        )
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}


async def route_message(sender: str, message: dict, context: dict, sender_profile_name: str):
    """Step 2: INTENT DETECTION"""
    message_type = message.get("type")
    
    if context["user_type"] == "ADMIN":
        text = message.get("text", {}).get("body", "") if message_type == "text" else ""
        if text:
             verification_pipeline.process_admin_reply(
                admin_phone=f"+{sender}" if not sender.startswith("+") else sender,
                reply_text=text
            )
             return

    if message_type in ("image", "document"):
        media = message.get(message_type, {})
        await handle_media_message(sender, media, message_type, context)
        return

    if message_type == "text":
        text = message.get("text", {}).get("body", "")
        await handle_text_message(sender, text, context, sender_profile_name)
        return
        
    whatsapp_client.send_text(sender, "⚠️ I can only process text messages and receipt images/PDFs.")


async def handle_text_message(sender: str, text: str, context: dict, sender_name: str):
    # Use the SAFETY WRAPPER to catch crashes
    action, reply = conversation_manager.safe_analyze_intent(
        text=text,
        sender=sender,  # Fixed: Match method signature (was sender_phone)
        context=context,
        name=sender_name # Fixed: Match method signature (was sender_name)
    )
    if reply:
        whatsapp_client.send_text(sender, reply)


async def handle_media_message(sender: str, media: dict, media_type: str, context: dict):
    media_id = media.get("id")
    if not media_id:
        return
        
    mime_type = media.get("mime_type", "")
    ext_map = {
        "image/jpeg": ".jpg", "image/png": ".png", "image/heic": ".heic",
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    }
    ext = ext_map.get(mime_type, ".bin")
    filename = f"{media_id}{ext}"
    file_path = str(RECEIPTS_DIR / filename)
    
    downloaded = whatsapp_client.download_media(media_id, file_path)
    
    if not downloaded:
        whatsapp_client.send_text(sender, "❌ Download failed. Please try again.")
        return
        
    with open(file_path, "rb") as f:
        file_content = f.read()

    if not context["schools"]:
        whatsapp_client.send_text(sender, "⚠️ Error: No school linked to your profile.")
        return

    target_school = context["schools"][0]
    
    verification_pipeline.process_parent_receipt(
        parent_phone=f"+{sender}" if not sender.startswith("+") else sender,
        file_content=file_content,
        filename=filename,
        school_id=target_school.id
    )

# Endpoints for admin tests moved to main.py
# Privacy/Terms moved to main.py (or could stay here, but better in main if global)
