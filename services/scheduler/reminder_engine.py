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

def run_reminder_cycle(db: Session, force: bool = False) -> dict:
    """
    Run one cycle of the reminder scheduler.
    
    Schedule (User Research Based):
    - Grace: 14 days after term start (no messages)
    - Phase 1: Mondays at 7 AM (polite)
    - Phase 2: Mon + Thu at 7 AM (strict, exam warning)
    
    Args:
        db: Database session
        force: If True, bypass day-of-week and time checks
    
    Returns:
        Summary dict with counts
    """
    stats = {
        "schools_processed": 0,
        "students_checked": 0,
        "reminders_sent": 0,
        "errors": 0,
        "skipped_rate_limit": 0,
        "phase_1_schools": 0,
        "phase_2_schools": 0,
        "grace_period_schools": 0,
    }
    
    print(f"\n[SmartBursar] Reminder Cycle - {get_wat_now().strftime('%Y-%m-%d %H:%M')} WAT")
    
    # Get all active schools
    active_schools = db.query(School).filter(
        School.status == "ACTIVE"
    ).all()
    
    for school in active_schools:
        if not school.is_active:
            print(f"[SKIP] {school.school_name} - subscription expired")
            continue
        
        # Check daily limit
        if school.messages_sent_today >= settings.MAX_MESSAGES_PER_DAY_PER_SCHOOL:
            print(f"[SKIP] {school.school_name} - daily limit reached")
            stats["skipped_rate_limit"] += 1
            continue
        
        stats["schools_processed"] += 1
        
        # Get current phase
        phase = get_current_phase(school)
        
        if phase == "GRACE":
            print(f"[SKIP] {school.school_name} - Grace Period (14 days)")
            stats["grace_period_schools"] += 1
            continue
        
        if phase == "EXAMS_STARTED" and not force:
            print(f"[SKIP] {school.school_name} - Exams started (messaging paused)")
            continue
        
        # Check if should send today (day of week)
        if not should_send_today(school, force=force):
            day_name = get_today_wat().strftime("%A")
            print(f"[SKIP] {school.school_name} - {phase}, not a messaging day ({day_name})")
            continue
        
        # Track phase stats
        if phase == "PHASE_1":
            stats["phase_1_schools"] += 1
            print(f"\n[SCHOOL] {school.school_name} - PHASE 1 (Weekly/Polite)")
        else:
            stats["phase_2_schools"] += 1
            print(f"\n[SCHOOL] {school.school_name} - PHASE 2 (Twice Weekly/Strict)")
        
        # Get students with OUTSTANDING BALANCE (critical: not status-based)
        students = db.query(Student).filter(
            Student.school_id == school.id,
            Student.fees_total_due > Student.amount_paid,  # balance_outstanding > 0
            Student.is_archived == False
        ).all()
        
        sender = get_message_sender(db)
        
        for student in students:
            stats["students_checked"] += 1
            
            # Check limit again
            if school.messages_sent_today >= settings.MAX_MESSAGES_PER_DAY_PER_SCHOOL:
                stats["skipped_rate_limit"] += 1
                break
            
            # Generate and send message
            message = generate_reminder_message(student, school, phase)
            
            try:
                log, error = sender.send_whatsapp(
                    to_phone=student.parent_phone_primary,
                    message=message,
                    student_id=student.id,
                    school_id=school.id,
                )
                
                if error:
                    print(f"  [ERROR] {student.full_name}: {error}")
                    stats["errors"] += 1
                else:
                    print(f"  [SENT] {student.full_name} - {format_naira(student.balance)}")
                    stats["reminders_sent"] += 1
                    
                    school.messages_sent_today += 1
                    school.monthly_spend += log.cost
                    db.commit()
                    
            except Exception as e:
                print(f"  [ERROR] {student.full_name}: {str(e)}")
                stats["errors"] += 1
    
    print(f"\n[SUMMARY] {stats['schools_processed']} schools, "
          f"{stats['reminders_sent']} sent, "
          f"Phase1: {stats['phase_1_schools']}, Phase2: {stats['phase_2_schools']}")
    
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
    Send a single test reminder immediately.
    Used for UI verification.
    """
    from services.messaging.mock_sender import get_message_sender
    sender = get_message_sender(db)
    
    student = db.query(Student).filter(Student.id == student_id).first()
    school = db.query(School).filter(School.id == school_id).first()
    
    if not student or not school:
        return None, "Student or School not found"
    
    # Generate message
    # For test reminders, we can assume a default phase or determine it dynamically if needed.
    # For simplicity, let's assume PHASE_1 for now or pass a default.
    # The original function used get_current_phase(school), let's keep that logic for message generation.
    phase = get_current_phase(school) # Re-adding phase determination for message generation
    message = generate_reminder_message(student, school, phase)
    
    # Send
    log, error = sender.send_whatsapp(
        to_phone=student.parent_phone_primary,
        message=message,
        student_id=student.id,
        school_id=school.id,
        message_type=MessageType.REMINDER
    )
    
    if error:
        print(f"[ERROR] {error}")
        return None, error
    
    print(f"[SUCCESS] Test message sent to {student.parent_name}")
    return log, None


# Legacy alias for backward compatibility
run_high_intensity_cycle = run_reminder_cycle
