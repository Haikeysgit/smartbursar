"""
=============================================================================
SmartBursar - Intelligent Reminder Engine
=============================================================================
User Research-Based Messaging Schedule:

Grace Period: 14 days after Term Start Date (no messages)
Phase 1 (Before Mid-Term): Mondays at 7:00 AM, Polite tone
Phase 2 (After Mid-Term): Mon + Thu at 7:00 AM, Strict tone (exam barring)

All cron jobs run at 7:00 AM WAT only.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from config.settings import settings
from models.school import School
from models.student import Student
from models.message_log import MessageLog, MessageType
from services.messaging.mock_sender import get_message_sender
from utils.currency import format_naira
from utils.date_helpers import get_wat_now, get_today_wat, format_date_nigerian


# =============================================================================
# Date Configuration Helpers
# =============================================================================

def get_term_start_date(school: School) -> Optional[date]:
    """Get term start date from school settings."""
    if not school.settings_config:
        return None
    
    date_str = school.settings_config.get("term_start_date")
    if not date_str:
        return None
    
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def get_mid_term_date(school: School) -> Optional[date]:
    """Get mid-term date from school settings."""
    if not school.settings_config:
        return None
    
    date_str = school.settings_config.get("mid_term_date")
    if not date_str:
        return None
    
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def get_exam_date(school: School) -> Optional[date]:
    """Get exam date from school settings."""
    if not school.settings_config:
        return None
    
    date_str = school.settings_config.get("exam_date")
    if not date_str:
        return None
    
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


# =============================================================================
# Grace Period & Phase Detection
# =============================================================================

def is_within_grace_period(school: School) -> bool:
    """
    Check if we're within the 14-day grace period after term start.
    
    No messages should be sent during grace period.
    """
    term_start = get_term_start_date(school)
    if not term_start:
        # No term start date set - proceed without grace period
        return False
    
    today = get_today_wat()
    days_since_term_start = (today - term_start).days
    
    # Within first 14 days = grace period
    return 0 <= days_since_term_start < 14


def get_current_phase(school: School) -> str:
    """
    Determine current messaging phase.
    
    Returns:
        "GRACE" - Within 14-day grace period (no messaging)
        "PHASE_1" - Before mid-term (weekly, polite)
        "PHASE_2" - After mid-term (twice weekly, strict)
        "EXAMS_STARTED" - Exams have begun (pause messaging)
    """
    today = get_today_wat()
    
    # Check if exams have started
    exam_date = get_exam_date(school)
    if exam_date and today >= exam_date:
        return "EXAMS_STARTED"
    
    # Check grace period
    if is_within_grace_period(school):
        return "GRACE"
    
    # Check mid-term
    mid_term = get_mid_term_date(school)
    if not mid_term:
        # No mid-term set - default to Phase 1
        return "PHASE_1"
    
    if today < mid_term:
        return "PHASE_1"
    else:
        return "PHASE_2"


def get_phase_tone(phase: str) -> str:
    """Get message tone based on current phase."""
    if phase == "PHASE_2":
        return "strict"  # Mention exam barring
    return "polite"


# =============================================================================
# Schedule Checking (Day of Week Logic)
# =============================================================================

def should_send_today(school: School, force: bool = False) -> bool:
    """
    Check if reminders should be sent today based on phase schedule.
    
    Phase 1 (Before Mid-Term): Mondays only
    Phase 2 (After Mid-Term): Mondays and Thursdays
    
    Args:
        school: School to check
        force: If True, bypass day-of-week checks (for manual triggers)
    
    Returns:
        True if should send today, False otherwise
    """
    if force:
        return True

    phase = get_current_phase(school)
    
    # No messaging during grace period or exams
    if phase in ("GRACE", "EXAMS_STARTED"):
        return False
    
    today = get_today_wat()
    day_of_week = today.weekday()  # 0=Monday, 3=Thursday
    
    if phase == "PHASE_1":
        # Mondays only
        return day_of_week == 0
    
    if phase == "PHASE_2":
        # Mondays and Thursdays
        return day_of_week in (0, 3)
    
    return False


def is_correct_time_window() -> bool:
    """
    Check if current time is within the 7:00 AM window.
    
    Window: 6:45 AM - 7:30 AM WAT
    """
    current_hour = get_wat_now().hour
    current_minute = get_wat_now().minute
    
    # 7 AM window: between 6:45 and 7:30
    if current_hour == 6 and current_minute >= 45:
        return True
    if current_hour == 7 and current_minute <= 30:
        return True
    
    return False


# =============================================================================
# Message Generation
# =============================================================================

def generate_reminder_message(
    student: Student,
    school: School,
    phase: str = "PHASE_1",
) -> str:
    """
    Generate a reminder message using Gemini AI.
    
    Args:
        student: Student with outstanding balance
        school: School sending the reminder
        phase: Current phase (affects tone)
    
    Returns:
        Formatted message string
    """
    from services.llm.groq_client import groq_client
    
    # Calculate days overdue
    today = get_today_wat()
    days_overdue = 0
    if student.due_date and student.due_date < today:
        days_overdue = (today - student.due_date).days
    
    # Use current balance (critical for partial payments)
    amount_formatted = format_naira(student.balance)
    
    # Context for AI
    context = {
        "student_name": student.full_name,
        "amount_due": amount_formatted,
        "due_date": format_date_nigerian(student.due_date),
        "school_name": school.school_name if hasattr(school, 'school_name') else school.name,
        "days_overdue": days_overdue
    }
    
    # Determine tone based on phase
    tone = get_phase_tone(phase)
    
    # Try AI generation
    if groq_client.is_active:
        try:
            ai_message = groq_client.generate_message(context, tone)
            if ai_message:
                # Add exam barring warning for Phase 2
                if phase == "PHASE_2" and "exam" not in ai_message.lower():
                    ai_message += "\n\n⚠️ Please note: Outstanding fees may affect exam participation."
                return ai_message
        except Exception as e:
            # Log error but fallback gracefully
            print(f"[WARNING] Groq generation failed: {e}")
    
    # Fallback to template
    return _get_fallback_template(context, tone, phase)


def _get_fallback_template(context: dict, tone: str, phase: str) -> str:
    """Static templates if AI is offline."""
    s_name = context['student_name']
    amt = context['amount_due']
    school = context['school_name']
    
    if phase == "PHASE_2" or tone == "strict":
        return (
            f"⚠️ IMPORTANT: Outstanding fees of {amt} for {s_name} at {school} "
            f"require immediate attention. Please settle this balance to ensure "
            f"uninterrupted exam participation."
        )
    else:
        return (
            f"Dear Parent, friendly reminder that {amt} is due for {s_name} at {school}. "
            f"Thank you for your continued partnership."
        )


# =============================================================================
# Core Scheduler
# =============================================================================

def _get_weekly_template_for_school(school: School) -> Tuple[Optional[str], str]:
    """
    Determine which template to use based on term progress.
    
    3-Stage Logic:
    1. Weeks 0-2 (Grace): None
    2. Weeks 3-6 (Early): fee_alert_soft (Polite)
    3. Weeks 7-MidTerm (Mid): fee_alert_v1 (Standard)
    4. After MidTerm (Late): fee_alert_urgent (Strict)
    
    Returns:
        (template_name, tone_label) or (None, "GRACE")
    """
    term_start = get_term_start_date(school)
    if not term_start:
        return ("fee_alert_v1", "DEFAULT")  # Fallback if no dates set
        
    today = get_today_wat()
    days_since_start = (today - term_start).days
    
    if days_since_start < 14:
        return (None, "GRACE")
    
    if days_since_start < 42:  # Weeks 3-6 (up to day 42)
        return ("fee_alert_soft", "EARLY_TERM")
        
    # Check Mid-Term for Phase 2 transition
    mid_term = get_mid_term_date(school)
    if mid_term and today >= mid_term:
        return ("fee_alert_urgent", "LATE_TERM")
    
    # Between Week 6 and Mid-Term
    return ("fee_alert_v1", "MID_TERM")


def run_reminder_cycle(db: Session, force: bool = False) -> dict:
    """
    Run the Weekly Reminder Cycle using 3-Stage Templates.
    
    Schedule:
    - Mondays: Send appropriate template (Soft/Standard/Urgent)
    - Thursdays: Send Urgent template ONLY if in Late Term (Phase 2)
    """
    stats = {
        "schools_processed": 0,
        "students_checked": 0,
        "reminders_sent": 0,
        "errors": 0,
        "skipped_rate_limit": 0,
        "skipped_grace_period": 0,
        "template_soft": 0,
        "template_standard": 0,
        "template_urgent": 0,
    }
    
    print(f"\n[SmartBursar] Weekly Cycle ({get_today_wat().strftime('%A')})")
    
    active_schools = db.query(School).filter(School.status == "ACTIVE").all()
    today_weekday = get_today_wat().weekday()  # 0=Mon, 3=Thu
    
    for school in active_schools:
        if not school.is_active:
            continue
            
        # 1. Determine Template & Phase
        template_name, phase_label = _get_weekly_template_for_school(school)
        
        if phase_label == "GRACE":
            print(f"[SKIP] {school.school_name} - Grace Period")
            stats["skipped_grace_period"] += 1
            continue
            
        # 2. Schedule Check (Monday vs Thursday)
        # - Monday: Send ALWAYS (if not Grace)
        # - Thursday: Send ONLY if Late Term (Urgent)
        is_monday = (today_weekday == 0)
        is_thursday = (today_weekday == 3)
        
        should_run = False
        if force:
            should_run = True
        elif is_monday:
            should_run = True
        elif is_thursday and phase_label == "LATE_TERM":
            should_run = True
            
        if not should_run:
            print(f"[SKIP] {school.school_name} - No schedule today ({phase_label})")
            continue

        stats["schools_processed"] += 1
        print(f"\n[SCHOOL] {school.school_name} | {phase_label} | {template_name}")
        
        # 3. Get Debtors
        students = db.query(Student).filter(
            Student.school_id == school.id,
            Student.fees_total_due > Student.amount_paid,
            Student.is_archived == False
        ).all()
        
        sender = get_message_sender(db)
        
        for student in students:
            stats["students_checked"] += 1
            
            # Rate Limit
            if school.messages_sent_today >= settings.MAX_MESSAGES_PER_DAY_PER_SCHOOL:
                stats["skipped_rate_limit"] += 1
                break
            
            # Build Template Vars
            # {{1}}=Amount, {{2}}=Student, {{3}}=School, {{4}}=Bank, {{5}}=AcctNum, {{6}}=AcctName
            template_vars = [
                format_naira(student.balance),
                student.full_name,
                school.school_name,
                school.bank_name,
                school.account_number,
                school.account_name,
            ]
            
            try:
                log, error = sender.send_whatsapp(
                    to_phone=student.parent_phone_primary,
                    message="",  # Template uses vars
                    student_id=student.id,
                    school_id=school.id,
                    message_type=MessageType.REMINDER,
                    is_template=True,
                    template_name=template_name,
                    template_vars=template_vars
                )
                
                if error:
                    print(f"  [ERROR] {student.full_name}: {error}")
                    stats["errors"] += 1
                else:
                    print(f"  [SENT] {student.full_name} -> {template_name}")
                    stats["reminders_sent"] += 1
                    
                    # Track breakdown
                    if template_name == "fee_alert_soft": stats["template_soft"] += 1
                    elif template_name == "fee_alert_v1": stats["template_standard"] += 1
                    elif template_name == "fee_alert_urgent": stats["template_urgent"] += 1
                    
                    school.messages_sent_today += 1
                    school.monthly_spend += log.cost
                    db.commit()
                    
            except Exception as e:
                print(f"  [ERROR] {student.full_name}: {str(e)}")
                stats["errors"] += 1
                
    return stats


def reset_daily_counters(db: Session) -> int:
    """Reset daily message counters for all schools."""
    result = db.query(School).update({"messages_sent_today": 0})
    db.commit()
    return result


# =============================================================================
# Manual Trigger (for dashboard)
# =============================================================================

def send_test_reminder(db: Session, student_id: int, school_id: int) -> Tuple[Optional[MessageLog], Optional[str]]:
    """
    Send a single test reminder immediately using the fee_alert_v1 template.
    Used for UI verification.
    """
    from services.messaging.mock_sender import get_message_sender
    sender = get_message_sender(db)
    
    student = db.query(Student).filter(Student.id == student_id).first()
    school = db.query(School).filter(School.id == school_id).first()
    
    if not student or not school:
        return None, "Student or School not found"
    
    # Build template variables for fee_alert_v1
    # Order: Amount, Student Name, School Name, Bank, Account Number, Account Name
    template_vars = [
        format_naira(student.balance),      # {{1}} - Amount (e.g., "₦50,000")
        student.full_name,                   # {{2}} - Student Name
        school.school_name,                  # {{3}} - School Name
        school.bank_name,                    # {{4}} - Bank (direct column on School)
        school.account_number,               # {{5}} - Account Number (direct column)
        school.account_name,                 # {{6}} - Account Name (direct column)
    ]
    
    # Send with Template "fee_alert_v1"
    log, error = sender.send_whatsapp(
        to_phone=student.parent_phone_primary,
        message="",  # Not used for template messages
        student_id=student.id,
        school_id=school.id,
        message_type=MessageType.REMINDER,
        is_template=True,
        template_name="fee_alert_v1",
        template_vars=template_vars,
    )
    
    if error:
        print(f"[ERROR] {error}")
        return None, error
    
    print(f"[SUCCESS] Test template sent to {student.parent_name}")
    return log, None


# Legacy alias for backward compatibility
run_high_intensity_cycle = run_reminder_cycle


# =============================================================================
# 3-Tier Due-Date Template Scheduling (NEW)
# =============================================================================

def get_template_for_due_date(student: Student) -> Optional[Tuple[str, str]]:
    """
    Determine which template to send based on days until/since due date.
    
    Returns:
        Tuple of (template_name, context) or None if no trigger today
    """
    if not student.due_date:
        return None
    
    today = get_today_wat()
    days_diff = (student.due_date - today).days  # Positive = future, Negative = past
    
    # 3-Tier Logic
    if days_diff == 3:
        return ("fee_alert_soft", "POLITE")      # 3 days before due
    elif days_diff == 0:
        return ("fee_alert_v1", "FORMAL")        # Due today
    elif days_diff == -7:
        return ("fee_alert_urgent", "DEMAND")    # 7 days overdue
    
    return None


def build_template_vars(student: Student, school: School) -> list:
    """Build the 6 template variables in correct order."""
    return [
        format_naira(student.balance),   # {{1}} - Amount
        student.full_name,                # {{2}} - Student Name
        school.school_name,               # {{3}} - School Name
        school.bank_name,                 # {{4}} - Bank
        school.account_number,            # {{5}} - Account Number
        school.account_name,              # {{6}} - Account Name
    ]


def run_template_reminder_cycle(db: Session) -> dict:
    """
    Run 3-tier due-date based template reminders.
    
    Schedule: Daily at 8:00 AM WAT
    
    Triggers:
        - 3 days before due_date -> fee_alert_soft
        - On due_date -> fee_alert_v1
        - 7 days after due_date -> fee_alert_urgent
    
    Returns:
        Summary dict with counts
    """
    stats = {
        "schools_processed": 0,
        "students_checked": 0,
        "templates_sent": 0,
        "soft_reminders": 0,
        "standard_reminders": 0,
        "urgent_reminders": 0,
        "skipped_no_trigger": 0,
        "errors": 0,
    }
    
    print(f"\n[SmartBursar] Template Reminder Cycle - {get_wat_now().strftime('%Y-%m-%d %H:%M')} WAT")
    print("="*60)
    
    # Get all active schools
    active_schools = db.query(School).filter(School.status == "ACTIVE").all()
    
    for school in active_schools:
        if not school.is_active:
            print(f"[SKIP] {school.school_name} - subscription expired")
            continue
        
        stats["schools_processed"] += 1
        print(f"\n[SCHOOL] {school.school_name}")
        
        # Get students with outstanding balance
        students = db.query(Student).filter(
            Student.school_id == school.id,
            Student.fees_total_due > Student.amount_paid,
            Student.is_archived == False,
            Student.due_date.isnot(None),
        ).all()
        
        sender = get_message_sender(db)
        
        for student in students:
            stats["students_checked"] += 1
            
            # Check if this student triggers a template today
            trigger = get_template_for_due_date(student)
            
            if not trigger:
                stats["skipped_no_trigger"] += 1
                continue
            
            template_name, context = trigger
            template_vars = build_template_vars(student, school)
            
            try:
                log, error = sender.send_whatsapp(
                    to_phone=student.parent_phone_primary,
                    message="",  # Not used for templates
                    student_id=student.id,
                    school_id=school.id,
                    message_type=MessageType.REMINDER,
                    is_template=True,
                    template_name=template_name,
                    template_vars=template_vars,
                )
                
                if error:
                    print(f"  [ERROR] {student.full_name}: {error}")
                    stats["errors"] += 1
                else:
                    days_diff = (student.due_date - get_today_wat()).days
                    print(f"  [SENT] {student.full_name} | {template_name} | days_diff={days_diff}")
                    stats["templates_sent"] += 1
                    
                    # Track by type
                    if template_name == "fee_alert_soft":
                        stats["soft_reminders"] += 1
                    elif template_name == "fee_alert_v1":
                        stats["standard_reminders"] += 1
                    elif template_name == "fee_alert_urgent":
                        stats["urgent_reminders"] += 1
                    
            except Exception as e:
                print(f"  [ERROR] {student.full_name}: {str(e)}")
                stats["errors"] += 1
    
    print(f"\n{'='*60}")
    print(f"[SUMMARY] {stats['schools_processed']} schools, {stats['students_checked']} students checked")
    print(f"          Sent: {stats['templates_sent']} (Soft: {stats['soft_reminders']}, "
          f"Standard: {stats['standard_reminders']}, Urgent: {stats['urgent_reminders']})")
    print(f"          Skipped: {stats['skipped_no_trigger']}, Errors: {stats['errors']}")
    
    return stats
