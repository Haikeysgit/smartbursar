"""
=============================================================================
SmartBursar - Main Application Entry Point
=============================================================================
"""
import os
import logging
from datetime import date

from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

from config.database import get_db_context, init_db, SessionLocal
from models.student import Student
from models.school import School
from services.whatsapp_agent.whatsapp_client import whatsapp_client
# Import the webhook router (we will update webhook_handler.py next)
from services.whatsapp_agent.webhook_handler import router as webhook_router

load_dotenv()
logger = logging.getLogger(__name__)

# =============================================================================
# App Setup
# =============================================================================
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="SmartBursar WhatsApp Agent",
    description="WhatsApp AI Payment Agent for School Fee Verification",
    version="2.0.2"
)

# Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include Webhook Router
app.include_router(webhook_router)

# Mount receipts
import pathlib
RECEIPTS_DIR = pathlib.Path(__file__).parent / "receipts"
RECEIPTS_DIR.mkdir(exist_ok=True)
app.mount("/receipts", StaticFiles(directory=str(RECEIPTS_DIR)), name="receipts")


# =============================================================================
# Startup & Health
# =============================================================================

@app.on_event("startup")
def startup_event():
    """Ensure database tables are created on startup."""
    try:
        logger.info("Checking database schema...")
        init_db()
        logger.info("Database schema check complete.")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")

@app.get("/health")
async def health_check():
    """Simple health check for Railway deployment."""
    return {"status": "healthy", "service": "whatsapp-webhook"}

@app.get("/")
def home():
    return {"message": "SmartBursar API is running. WhatsApp Webhook at /webhook"}


# =============================================================================
# Admin Endpoints (Moved from webhook_handler.py)
# =============================================================================

@app.post("/admin/trigger-test")
async def admin_trigger_test(
    phone: str = Query(..., description="Target phone number"),
    tone: str = Query(..., description="Tone type (term_start, exam_week)")
):
    """
    Step 5: ADMIN 'GOD MODE'
    Force a specific reminder tone to a specific number.
    """
    message = f"[TEST MODE] Triggering '{tone}' reminder for {phone}"
    
    if tone == "term_start":
        msg_content = "📢 *Term Start Reminder*\nWelcome back! Please ensure 50% fees are paid before resumption."
    elif tone == "exam_week":
        msg_content = "🎓 *Exam Week Alert*\nExams start Monday. Please clear all outstanding dues to obtain exam pass."
    else:
        msg_content = f"🔔 Test Reminder: {tone}"
        
    whatsapp_client.send_text(phone, msg_content)
    
    return {"status": "success", "message": message}


@app.get("/admin/fix-my-data")
def fix_my_data():
    """Manual fix to seed admin data in production."""
    db = SessionLocal()
    try:
        # Ensure School exists
        school = db.query(School).get(1)
        if not school:
            school = School(
                id=1,
                school_code="SCH001",
                school_name="Admin Test School",
                address="123 Test St",
                phone="+2348000000000",
                country_code="NG",
                bank_name="Test Bank",
                account_number="1234567890",
                account_name="Test School Account",
                subscription_end_date=date(2030, 1, 1)
            )
            db.add(school)
            db.commit()

        # Check if student exists
        existing = db.query(Student).filter(Student.parent_phone_primary == "+2348038004334").first()
        if not existing:
            new_student = Student(
                full_name="Test Student",
                parent_name="Obaseki Imisioluwa",
                parent_phone_primary="+2348038004334",
                class_level="JSS 1",
                due_date=date(2026, 12, 31),
                school_id=1,
                fees_total_due=50000,
                amount_paid=0
            )
            db.add(new_student)
            db.commit()
            return "✅ SUCCESS: You are now registered. Go say 'Hello' to the bot."
        return "⚠️ You were already registered."
    except Exception as e:
        return f"Error: {str(e)}"
    finally:
        db.close()
