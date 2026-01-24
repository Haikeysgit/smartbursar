"""
=============================================================================
SmartBursar - WhatsApp Webhook Handler
=============================================================================
FastAPI endpoints for Meta WhatsApp Cloud API webhooks.

Endpoints:
- GET /webhook: Meta verification handshake
- POST /webhook: Incoming message handler

To run:
    uvicorn services.whatsapp_agent.webhook_handler:app --port 8000 --reload

For production, use ngrok or deploy to a public server:
    ngrok http 8000
"""

import os
import logging
import hmac
import hashlib
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, Request, Query, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

from .whatsapp_client import whatsapp_client
from .verification_pipeline import verification_pipeline

logger = logging.getLogger(__name__)

# Security: Get app secret for webhook signature verification
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Rate limiting setup
limiter = Limiter(key_func=get_remote_address)

# FastAPI app
app = FastAPI(
    title="SmartBursar WhatsApp Agent",
    description="WhatsApp AI Payment Agent for School Fee Verification",
    version="1.0.0"
)

# Add rate limiter to app state and error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# =============================================================================
# Health Check (CRITICAL FOR RAILWAY)
# =============================================================================
@app.get("/health")
async def health_check():
    """
    Simple health check for Railway deployment.
    Returns 200 OK immediately without checking DB/AI.
    """
    return {"status": "healthy", "service": "whatsapp-webhook"}


# =============================================================================
# Security Headers Middleware
# =============================================================================

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    
    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"
    
    # XSS Protection (legacy browsers)
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    # Control referrer information
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # Prevent caching of sensitive responses
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    
    # Content Security Policy
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
    
    return response


# Mount receipts folder for static serving (development only)
RECEIPTS_DIR = Path(__file__).parent.parent.parent / "receipts"
RECEIPTS_DIR.mkdir(exist_ok=True)
app.mount("/receipts", StaticFiles(directory=str(RECEIPTS_DIR)), name="receipts")


# =============================================================================
# Webhook Signature Verification Helper
# =============================================================================

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify the X-Hub-Signature-256 header from Meta.
    
    Args:
        payload: Raw request body
        signature: X-Hub-Signature-256 header value
    
    Returns:
        True if signature is valid, False otherwise
    """
    if not WHATSAPP_APP_SECRET:
        # In development without app secret, log warning but allow
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
# Webhook Verification (GET - Meta Handshake)
# =============================================================================

@app.get("/webhook")
@limiter.limit("60/minute")
async def verify_webhook(request: Request,
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge")
):
    """
    Meta webhook verification endpoint.
    
    Called by Meta when you register your webhook URL.
    Returns the challenge to complete verification.
    """
    if not hub_mode or not hub_verify_token or not hub_challenge:
        raise HTTPException(status_code=400, detail="Missing verification parameters")
    
    result = whatsapp_client.verify_webhook(hub_mode, hub_verify_token, hub_challenge)
    
    if result:
        return PlainTextResponse(content=result)
    
    raise HTTPException(status_code=403, detail="Verification failed")


# =============================================================================
# Incoming Messages (POST - Message Handler)
# =============================================================================

@app.post("/webhook")
@limiter.limit("60/minute")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handle incoming WhatsApp messages.
    
    Parses the webhook payload and routes to appropriate handler.
    Processing is done in background to respond quickly to Meta.
    
    SECURITY: Verifies X-Hub-Signature-256 header before processing.
    """
    # SECURITY: Verify webhook signature first
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    
    if not verify_webhook_signature(body, signature):
        logger.warning(f"Invalid webhook signature from {request.client.host}")
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    try:
        import json
        body_json = json.loads(body)
        
        # Extract message data from webhook payload
        entry = body_json.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        
        # Check if this is a message event
        messages = value.get("messages", [])
        if not messages:
            # Status update or other event - acknowledge and ignore
            return {"status": "ok"}
        
        message = messages[0]
        sender = message.get("from")  # Phone number
        message_type = message.get("type")
        
        # Get contact info
        contacts = value.get("contacts", [{}])
        sender_name = contacts[0].get("profile", {}).get("name", "Unknown")
        
        logger.info(f"Incoming message from {sender} ({sender_name}): type={message_type}")
        
        # Route based on message type
        if message_type == "text":
            text = message.get("text", {}).get("body", "")
            background_tasks.add_task(
                handle_text_message,
                sender=sender,
                text=text,
                sender_name=sender_name
            )
        
        elif message_type in ("image", "document"):
            media = message.get(message_type, {})
            background_tasks.add_task(
                handle_media_message,
                sender=sender,
                media=media,
                media_type=message_type,
                sender_name=sender_name
            )
        
        else:
            logger.info(f"Unsupported message type: {message_type}")
        
        # Always return 200 OK quickly
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        # Still return 200 to prevent Meta from retrying
        return {"status": "error", "message": str(e)}


# =============================================================================
# Message Handlers (Background Tasks)
# =============================================================================

from .conversation_manager import conversation_manager

async def handle_text_message(sender: str, text: str, sender_name: str):
    """
    Handle incoming text messages with state management.
    """
    try:
        # Check if sender is an admin with pending verifications
        admin_phone_formatted = f"+{sender}" if not sender.startswith("+") else sender
        
        if admin_phone_formatted in verification_pipeline.admin_pending:
            # This is likely a verification response
            result = verification_pipeline.process_admin_reply(
                admin_phone=admin_phone_formatted,
                reply_text=text
            )
            logger.info(f"Admin reply processed: {result}")
            return

        # --- User Flow (Parents) ---
        sender_phone = f"+{sender}" if not sender.startswith("+") else sender
        
        # 1. Check if we are waiting for a Student Name (Fallback from failed receipt lookup)
        state = conversation_manager.get_user_state(sender_phone)
        
        if state == "IDENTIFYING_STUDENT":
            context = conversation_manager.get_context(sender_phone)
            if context:
                res = verification_pipeline.retry_with_student_name(
                    sender_phone,
                    text, 
                    context.get("extraction", {}),
                    context.get("file_path", ""),
                    context.get("school_id")
                )
                
                if res.get("success"):
                     conversation_manager.clear_session(sender_phone)
                else:
                     whatsapp_client.send_text(sender, "❌ Still couldn't find a student with that name. Please check spelling or contact Admin.")
            else:
                conversation_manager.clear_session(sender_phone)
                whatsapp_client.send_text(sender, "⚠️ Session expired. Please upload receipt again.")
            return 

        # 2. Get next action from Conversation Manager
        action, reply_message = conversation_manager.handle_incoming_text(text, sender_phone)
        
        if action == "SEND_MENU":
            whatsapp_client.send_interactive_message(
                sender,
                "👋 *Welcome to SmartBursar!*\n\nI can help you verify school fee payments instantly.\n\nWhat would you like to do?",
                [
                    {"id": "btn_pay", "title": "Submit Receipt"},
                    {"id": "btn_status", "title": "Check Balance"}
                ]
            )
        
        elif reply_message:
            whatsapp_client.send_text(sender, reply_message)
            
    except Exception as e:
        logger.error(f"Text handler error: {e}")


async def handle_media_message(sender: str, media: dict, media_type: str, sender_name: str):
    """
    Handle incoming media messages (images, documents).
    
    Assumes media is a payment receipt for processing.
    """
    try:
        media_id = media.get("id")
        
        if not media_id:
            whatsapp_client.send_text(sender, "❌ Could not process media. Please try again.")
            return
        
        # Determine file extension
        mime_type = media.get("mime_type", "")
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/heic": ".heic",
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        }
        ext = ext_map.get(mime_type, ".bin")
        
        # Download media
        filename = f"{media_id}{ext}"
        file_path = str(RECEIPTS_DIR / filename)
        
        downloaded = whatsapp_client.download_media(media_id, file_path)
        
        if not downloaded:
            whatsapp_client.send_text(sender, "❌ Could not download media. Please try again.")
            return
        
        # Read file content
        with open(file_path, "rb") as f:
            file_content = f.read()
        
        # For now, we need to know which school this parent belongs to
        # This is a limitation - we'll need to implement parent registration
        # For demo, we'll use the first school
        from config.database import get_db_context
        from models.school import School
        
        with get_db_context() as db:
            school = db.query(School).first()
            if not school:
                whatsapp_client.send_text(
                    sender,
                    "⚠️ System not configured. Please contact support."
                )
                return
            
            school_id = school.id
        
        # Process receipt
        result = verification_pipeline.process_parent_receipt(
            parent_phone=f"+{sender}" if not sender.startswith("+") else sender,
            file_content=file_content,
            filename=filename,
            school_id=school_id
        )
        
        # Check if we need to ask user for student name
        if result.get("requires_student_info"):
            conversation_manager.update_user_state(
                f"+{sender}" if not sender.startswith("+") else sender,
                "IDENTIFYING_STUDENT",
                context_update={
                    "extraction": result["extraction"],
                    "file_path": result["file_path"],
                    "school_id": result["school_id"]
                }
            )
        
        logger.info(f"Receipt processed: {result}")
        
    except Exception as e:
        logger.error(f"Media handler error: {e}")
        whatsapp_client.send_text(sender, "❌ Error processing receipt. Please try again.")


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
@limiter.limit("30/minute")
async def health_check(request: Request):
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "SmartBursar WhatsApp Agent",
        "whatsapp_configured": bool(whatsapp_client.token)
    }


# =============================================================================
# Privacy Policy & Terms (Required for Meta Live Mode)
# =============================================================================

@app.get("/privacy")
async def privacy_policy():
    """Privacy Policy page for Meta app verification."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content="""
<!DOCTYPE html>
<html>
<head>
    <title>Privacy Policy - SmartBursar</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        h1 { color: #333; }
        p { line-height: 1.6; color: #555; }
    </style>
</head>
<body>
    <h1>Privacy Policy</h1>
    <p><strong>Last updated:</strong> January 2026</p>
    
    <h2>Introduction</h2>
    <p>SmartBursar ("we", "our", or "us") is committed to protecting your privacy. This Privacy Policy explains how we collect, use, and safeguard your information when you use our WhatsApp-based school fee management service.</p>
    
    <h2>Information We Collect</h2>
    <p>We collect the following information:</p>
    <ul>
        <li>Phone numbers for WhatsApp communication</li>
        <li>Payment receipt images submitted for verification</li>
        <li>Student and payment information provided by schools</li>
    </ul>
    
    <h2>How We Use Your Information</h2>
    <p>We use your information to:</p>
    <ul>
        <li>Process and verify school fee payments</li>
        <li>Send payment confirmations and reminders via WhatsApp</li>
        <li>Provide customer support</li>
    </ul>
    
    <h2>Data Security</h2>
    <p>We implement appropriate security measures to protect your personal information from unauthorized access, alteration, or disclosure.</p>
    
    <h2>Contact Us</h2>
    <p>If you have questions about this Privacy Policy, please contact us through the school administration.</p>
</body>
</html>
    """)


@app.get("/terms")
async def terms_of_service():
    """Terms of Service page for Meta app verification."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content="""
<!DOCTYPE html>
<html>
<head>
    <title>Terms of Service - SmartBursar</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        h1 { color: #333; }
        p { line-height: 1.6; color: #555; }
    </style>
</head>
<body>
    <h1>Terms of Service</h1>
    <p><strong>Last updated:</strong> January 2026</p>
    
    <h2>Acceptance of Terms</h2>
    <p>By using SmartBursar's WhatsApp service, you agree to these Terms of Service.</p>
    
    <h2>Description of Service</h2>
    <p>SmartBursar provides a WhatsApp-based school fee management and verification service for schools and parents.</p>
    
    <h2>User Responsibilities</h2>
    <p>Users agree to:</p>
    <ul>
        <li>Provide accurate payment information</li>
        <li>Submit genuine payment receipts</li>
        <li>Use the service only for legitimate school fee purposes</li>
    </ul>
    
    <h2>Limitation of Liability</h2>
    <p>SmartBursar is not liable for any indirect, incidental, or consequential damages arising from the use of our service.</p>
    
    <h2>Contact</h2>
    <p>For questions about these terms, please contact the school administration.</p>
</body>
</html>
    """)


# =============================================================================
# Test Endpoint (Development Only - BLOCKED IN PRODUCTION)
# =============================================================================

@app.post("/test/send")
@limiter.limit("5/minute")
async def test_send_message(request: Request, to: str, message: str):
    """
    Test endpoint to send a WhatsApp message.
    
    SECURITY: Only available in development mode. Rate limited to 5/min.
    
    Usage: POST /test/send?to=+2348012345678&message=Hello
    """
    # SECURITY: Block in production
    if ENVIRONMENT == "production":
        raise HTTPException(status_code=404, detail="Not found")
    
    result = whatsapp_client.send_text(to, message)
    return result
