"""
=============================================================================
PROJECT ATLAS - Pressure Zones
=============================================================================
The "Pressure Cooker" scheduling system.

We don't use flat weekly reminders. We use a dynamic urgency curve
based on the school term timeline.

ZONE 1 (POLITE): Weeks 1-4
    - Monthly reminders
    - Salary week (25th-28th) push
    - Tone: "Gentle reminder", "Welcome back"

ZONE 2 (PINCER): Weeks 5-10
    - Bi-weekly pressure
    - Monday 7:30 AM: "Plan your week"
    - Friday 4:30 PM: "Clear before weekend"
    - Tone: Firm but professional

ZONE 3 (NUCLEAR): Weeks 11-14 (Exam Period)
    - Every 2-3 days → Daily as exams approach
    - Tone: "URGENT", "FINAL WARNING", "EXAM ACCESS"
"""

from datetime import date, time
from enum import Enum
from typing import Optional

from utils.date_helpers import (
    get_wat_now, get_today_wat, get_week_of_term,
    is_salary_week, is_weekend
)


# =============================================================================
# Pressure Zone Enum
# =============================================================================

class PressureZone(Enum):
    """
    The three pressure zones for fee collection.
    
    Each zone has different:
        - Reminder frequency
        - Message tone
        - Send times
    """
    POLITE = "polite"      # Weeks 1-4
    PINCER = "pincer"      # Weeks 5-10
    NUCLEAR = "nuclear"    # Weeks 11-14
    
    @property
    def description(self) -> str:
        """Human-readable description."""
        descriptions = {
            "polite": "Early term - gentle reminders",
            "pincer": "Mid term - increased pressure",
            "nuclear": "Exam period - maximum urgency",
        }
        return descriptions.get(self.value, "Unknown")


# =============================================================================
# Zone Detection
# =============================================================================

def get_current_zone(
    term_start_date: date,
    term_end_date: date,
    exam_start_date: Optional[date] = None,
) -> PressureZone:
    """
    Determine the current pressure zone based on term timeline.
    
    Args:
        term_start_date: When the school term started
        term_end_date: When the term ends
        exam_start_date: When exams start (defaults to 2 weeks before term end)
    
    Returns:
        Current PressureZone
    
    Logic:
        - Weeks 1-4: POLITE
        - Weeks 5-10: PINCER
        - Weeks 11+ or within 2 weeks of exams: NUCLEAR
    """
    week_num = get_week_of_term(term_start_date)
    
    # If before term starts, be polite
    if week_num == 0:
        return PressureZone.POLITE
    
    # Check if we're in exam period
    if exam_start_date is None:
        # Default: Exams start 2 weeks before term ends
        days_to_term_end = (term_end_date - get_today_wat()).days
        if days_to_term_end <= 14:
            return PressureZone.NUCLEAR
    else:
        days_to_exams = (exam_start_date - get_today_wat()).days
        if days_to_exams <= 7:  # Within a week of exams
            return PressureZone.NUCLEAR
    
    # Week-based zones
    if week_num <= 4:
        return PressureZone.POLITE
    elif week_num <= 10:
        return PressureZone.PINCER
    else:
        return PressureZone.NUCLEAR


# =============================================================================
# Reminder Scheduling Logic
# =============================================================================

def should_send_reminder_today(
    zone: PressureZone,
    last_reminder_date: Optional[date] = None,
    student_balance: float = 0,
) -> bool:
    """
    Determine if a reminder should be sent today based on zone.
    
    Args:
        zone: Current pressure zone
        last_reminder_date: When we last sent a reminder to this parent
        student_balance: Amount owed (for prioritization)
    
    Returns:
        True if we should send a reminder today
    """
    today = get_today_wat()
    
    # Don't send to zero-balance students
    if student_balance <= 0:
        return False
    
    # Calculate days since last reminder
    if last_reminder_date:
        days_since_last = (today - last_reminder_date).days
    else:
        days_since_last = 999  # Never sent, so send now
    
    if zone == PressureZone.POLITE:
        # Monthly + salary week
        if is_salary_week():
            return days_since_last >= 3  # At most twice during salary week
        return days_since_last >= 7  # Weekly (softer than monthly for MVP testing)
    
    elif zone == PressureZone.PINCER:
        # Bi-weekly: Monday and Friday
        weekday = today.weekday()
        
        if weekday == 0:  # Monday
            return days_since_last >= 3
        elif weekday == 4:  # Friday
            return days_since_last >= 3
        
        return False  # Other days, no reminder
    
    elif zone == PressureZone.NUCLEAR:
        # Aggressive: Every 2-3 days, daily in final week
        return days_since_last >= 2
    
    return False


def get_send_time(
    zone: PressureZone,
    evasion_status: str = "ENGAGED",
) -> time:
    """
    Get the optimal send time based on zone and parent behavior.
    
    Args:
        zone: Current pressure zone
        evasion_status: Parent's engagement status
    
    Returns:
        Time of day to send the reminder
    """
    import random
    
    # For evasive parents, randomize send times
    if evasion_status in ["LIKELY_ARCHIVED", "POSSIBLY_MUTED"]:
        random_hours = [7, 14, 19, 21]
        random_minutes = [0, 15, 30, 45]
        return time(random.choice(random_hours), random.choice(random_minutes))
    
    # Standard times based on zone
    today = get_today_wat()
    weekday = today.weekday()
    
    if zone == PressureZone.POLITE:
        return time(8, 0)  # 8:00 AM
    
    elif zone == PressureZone.PINCER:
        if weekday == 0:  # Monday
            return time(7, 30)  # 7:30 AM - Start of week
        else:
            return time(16, 30)  # 4:30 PM - End of week push
    
    else:  # NUCLEAR
        return time(8, 0)  # 8:00 AM - Maximum visibility


# =============================================================================
# Message Tone Selection
# =============================================================================

def get_message_tone(zone: PressureZone) -> dict:
    """
    Get the message tone parameters for the current zone.
    
    Returns dict with:
        - greeting_style: formal/casual
        - urgency_level: low/medium/high
        - include_deadline: bool
        - include_consequences: bool
    """
    tones = {
        PressureZone.POLITE: {
            "greeting_style": "polite",
            "urgency_level": "low",
            "include_deadline": False,
            "include_consequences": False,
            "sample_opening": "Good morning Sir/Ma, this is a friendly reminder",
            "sample_closing": "Thank you and God bless!",
        },
        PressureZone.PINCER: {
            "greeting_style": "formal",
            "urgency_level": "medium",
            "include_deadline": True,
            "include_consequences": False,
            "sample_opening": "Dear Parent, this is to remind you",
            "sample_closing": "Kindly treat as urgent. Thank you.",
        },
        PressureZone.NUCLEAR: {
            "greeting_style": "urgent",
            "urgency_level": "high",
            "include_deadline": True,
            "include_consequences": True,
            "sample_opening": "URGENT: FINAL NOTICE",
            "sample_closing": "Failure to pay may affect exam access.",
        },
    }
    
    return tones.get(zone, tones[PressureZone.POLITE])
