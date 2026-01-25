"""
=============================================================================
SmartBursar - Main Application Entry Point
=============================================================================
"""
import os
import logging
from datetime import date

from fastapi import FastAPI, Query, HTTPException, Form
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


# =============================================================================
# LIGHTWEIGHT ADMIN UI (HTML)
# =============================================================================
from fastapi.responses import HTMLResponse

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard():
    """Simple HTML Dashboard to view and manage data."""
    db = SessionLocal()
    try:
        students = db.query(Student).all()
        schools = db.query(School).all()
        
        # Build HTML Table
        rows = ""
        for s in students:
            rows += f"""
            <tr>
                <td>{s.id}</td>
                <td>{s.full_name}</td>
                <td>{s.parent_phone_primary}</td>
                <td>₦{s.fees_total_due:,.2f}</td>
                <td>₦{s.amount_paid:,.2f}</td>
                <td>{s.balance:,.2f}</td>
                <td>
                    <form action="/admin/update-payment" method="post" style="display:inline;">
                        <input type="hidden" name="student_id" value="{s.id}">
                        <input type="number" name="amount" placeholder="Add Payment" style="width:100px;">
                        <button type="submit">Pay</button>
                    </form>
                </td>
            </tr>
            """
            
        html = f"""
        <html>
        <head>
            <title>SmartBursar Mini-Admin</title>
            <style>
                body {{ font-family: sans-serif; padding: 2rem; max-width: 1000px; margin: 0 auto; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .btn {{ display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
                .btn-danger {{ background: #dc3545; }}
            </style>
        </head>
        <body>
            <h1>🎓 SmartBursar Admin (Lite)</h1>
            <p>Manage your test data here without complex dashboards.</p>
            
            <div style="margin-bottom: 20px; padding: 15px; background: #e9ecef; border-radius: 8px;">
                <h3>🛠️ Quick Actions</h3>
                <form action="/admin/seed" method="post" style="display:inline;">
                    <button type="submit" class="btn">🌱 Reset & Seed Test Data</button>
                </form>
                <p><small>This wipes the database and creates "David" (Student) linked to your number.</small></p>
            </div>

            <h3>Students</h3>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Parent Phone</th>
                    <th>Fees Due</th>
                    <th>Paid</th>
                    <th>Balance</th>
                    <th>Actions</th>
                </tr>
                {rows}
            </table>
            
            <br>
            <h3>Registered Schools</h3>
            <ul>
                {"".join([f"<li>{s.school_name} (Bank: {s.bank_name})</li>" for s in schools])}
            </ul>
        </body>
        </html>
        """
        return html
    finally:
        db.close()

@app.post("/admin/seed", response_class=HTMLResponse)
def admin_seed_data():
    """Wipe and Reseed for Testing."""
    db = SessionLocal()
    try:
        # Wipe
        db.query(Student).delete()
        db.query(School).delete()
        
        # Create School
        school = School(
            school_code="SCH-TEST",
            school_name="Excel International College",
            address="Lagos, Nigeria",
            phone="+2348000000000",
            bank_name="Zenith Bank",
            account_number="1234567890",
            account_name="Excel College Tuition",
            country_code="NG"
        )
        db.add(school)
        db.flush() 
        
        # Create Student
        # HARDCODED to the number user provided in screenshot: 2349163031534
        student = Student(
            full_name="David Adeleke",
            parent_name="Chief Adeleke",
            parent_phone_primary="+2349163031534", # The number from the screenshot
            class_level="SS 3",
            fees_total_due=150000.00,
            amount_paid=50000.00, # Partial payment
            due_date=date(2026, 2, 1),
            school_id=school.id
        )
        db.add(student)
        db.commit()
        
        return f"""
        <h1>✅ Data Reset!</h1>
        <p>Created School: <b>{school.school_name}</b></p>
        <p>Created Student: <b>{student.full_name}</b></p>
        <p>Linked to Phone: <b>{student.parent_phone_primary}</b></p>
        <p>Balance: <b>N{student.balance:,.2f}</b></p>
        <br>
        <a href="/admin">Back to Dashboard</a>
        """
    except Exception as e:
        db.rollback()
        return f"<h1>Error</h1><p>{e}</p>"
    finally:
        db.close()

@app.post("/admin/update-payment", response_class=HTMLResponse)
def admin_update_payment(student_id: int = Query(...), amount: float = Query(...)):
    """Update payment for a student."""
    db = SessionLocal()
    try:
        student = db.query(Student).get(student_id)
        if student:
            student.amount_paid += amount
            db.commit()
        return f"""
        <h1>✅ Payment Updated</h1>
        <meta http-equiv="refresh" content="1;url=/admin" />
        <p>Redirecting...</p>
        """
    finally:
        db.close()

