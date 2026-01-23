"""
=============================================================================
PROJECT ATLAS - Date & Time Helpers
=============================================================================
All dates/times in the system use West Africa Time (WAT, UTC+1).

Key functions:
    - get_wat_now(): Current time in WAT
    - days_until(): Days remaining to a date
    - is_salary_week(): True if 25th-28th (optimal for reminders)
"""

from datetime import date, datetime, time, timedelta
from typing import Optional

import pytz

from config.settings import settings


# =============================================================================
# Timezone
# =============================================================================

# West Africa Time (Nigeria, Ghana, etc.)
WAT = pytz.timezone(settings.TIMEZONE)  # "Africa/Lagos"


# =============================================================================
# Current Time
# =============================================================================

def get_wat_now() -> datetime:
    """
    Get current datetime in West Africa Time.
    
    Returns:
        timezone-aware datetime in WAT
    
    Example:
        >>> get_wat_now()
        datetime(2026, 1, 7, 8, 30, 0, tzinfo=<DstTzInfo 'Africa/Lagos'>)
    """
    return datetime.now(WAT)


def get_today_wat() -> date:
    """
    Get today's date in West Africa Time.
    
    Returns:
        date object
    """
    return get_wat_now().date()


# =============================================================================
# Date Calculations
# =============================================================================

def days_until(target_date: date) -> int:
    """
    Calculate days until a target date.
    
    Args:
        target_date: The date to calculate days until
    
    Returns:
        Positive if future, 0 if today, negative if past
    
    Examples:
        >>> days_until(date(2026, 1, 10))  # Today is Jan 7
        3
        
        >>> days_until(date(2026, 1, 5))   # Today is Jan 7
        -2
    """
    today = get_today_wat()
    return (target_date - today).days


def days_since(past_date: date) -> int:
    """
    Calculate days since a past date.
    
    Args:
        past_date: The date to calculate days from
    
    Returns:
        Positive number of days since date (negative if date is in future)
    """
    return -days_until(past_date)


def is_overdue(due_date: date) -> bool:
    """
    Check if a date is in the past.
    
    Args:
        due_date: The due date to check
    
    Returns:
        True if due_date is before today
    """
    return days_until(due_date) < 0


# =============================================================================
# Nigerian Business Calendar
# =============================================================================

def is_salary_week() -> bool:
    """
    Check if current date is in salary week (25th-28th).
    
    Nigerian civil servants and many private sector employees
    get paid at the end of the month. This is the optimal time
    for payment reminders.
    
    Returns:
        True if today is between 25th and 28th of the month
    """
    today = get_today_wat()
    return 25 <= today.day <= 28


def is_weekend() -> bool:
    """
    Check if today is a weekend.
    
    Returns:
        True if Saturday (5) or Sunday (6)
    """
    return get_wat_now().weekday() >= 5


def is_business_hours(hour: Optional[int] = None) -> bool:
    """
    Check if current time is within business hours (8 AM - 6 PM WAT).
    
    Args:
        hour: Optional hour to check (0-23). If None, uses current time.
    
    Returns:
        True if within business hours
    """
    if hour is None:
        hour = get_wat_now().hour
    
    return 8 <= hour < 18


# =============================================================================
# School Term Calculations
# =============================================================================

def get_week_of_term(term_start_date: date) -> int:
    """
    Calculate which week of the term we're in.
    
    Args:
        term_start_date: When the school term started
    
    Returns:
        Week number (1, 2, 3, ...) or 0 if before term starts
    
    Example:
        >>> get_week_of_term(date(2026, 1, 6))  # Today is Jan 14
        2
    """
    today = get_today_wat()
    
    if today < term_start_date:
        return 0
    
    days_elapsed = (today - term_start_date).days
    week = (days_elapsed // 7) + 1
    
    return week


def get_term_progress(
    term_start_date: date,
    term_end_date: date
) -> float:
    """
    Calculate percentage progress through the term.
    
    Args:
        term_start_date: When term started
        term_end_date: When term ends
    
    Returns:
        Float from 0.0 to 1.0 (can exceed 1.0 if past term end)
    
    Example:
        >>> get_term_progress(date(2026, 1, 6), date(2026, 4, 5))
        0.10  # 10% through the term
    """
    today = get_today_wat()
    
    total_days = (term_end_date - term_start_date).days
    elapsed_days = (today - term_start_date).days
    
    if total_days <= 0:
        return 1.0
    
    return elapsed_days / total_days


# =============================================================================
# Message Scheduling
# =============================================================================

def get_optimal_send_time(
    evasion_status: str = "ENGAGED",
    zone: str = "POLITE"
) -> time:
    """
    Determine the optimal time to send a reminder.
    
    For engaged parents: Standard times (8 AM Mon, 4:30 PM Fri)
    For evasive parents: Randomized to avoid predictability
    
    Args:
        evasion_status: ENGAGED, LIKELY_ARCHIVED, etc.
        zone: POLITE, PINCER, NUCLEAR
    
    Returns:
        Optimal time of day to send
    """
    import random
    
    if evasion_status == "ENGAGED":
        # Standard times based on zone
        if zone == "POLITE":
            return time(8, 0)  # 8:00 AM
        elif zone == "PINCER":
            # Monday morning or Friday afternoon
            if get_wat_now().weekday() == 0:  # Monday
                return time(7, 30)  # 7:30 AM
            else:
                return time(16, 30)  # 4:30 PM
        else:  # NUCLEAR
            return time(8, 0)  # 8:00 AM
    
    else:
        # Randomize for archive busters
        possible_times = [
            time(7, 30),   # Before work
            time(14, 0),   # Lunch break
            time(19, 30),  # After work
            time(21, 0),   # Evening
        ]
        return random.choice(possible_times)


# =============================================================================
# Formatting
# =============================================================================

def format_date_nigerian(d: date) -> str:
    """
    Format date in Nigerian style (day month year).
    
    Example:
        >>> format_date_nigerian(date(2026, 1, 15))
        '15 January 2026'
    """
    return d.strftime("%d %B %Y")


def format_datetime_nigerian(dt: datetime) -> str:
    """
    Format datetime in Nigerian style with 12-hour time.
    
    Example:
        >>> format_datetime_nigerian(datetime(2026, 1, 15, 14, 30))
        '15 January 2026 at 2:30 PM'
    """
    return dt.strftime("%d %B %Y at %-I:%M %p")


def get_greeting() -> str:
    """
    Get appropriate Nigerian greeting based on time of day.
    
    Returns:
        "Good morning", "Good afternoon", or "Good evening"
    """
    hour = get_wat_now().hour
    
    if hour < 12:
        return "Good morning"
    elif hour < 17:
        return "Good afternoon"
    else:
        return "Good evening"
