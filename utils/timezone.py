"""
=============================================================================
SmartBursar - Timezone Utilities
=============================================================================
Ensures all time operations use Nigeria Time (WAT / UTC+1).
Critical for reminders and receipt timestamps when running on US/EU servers.
"""

from datetime import datetime
import pytz

# Nigeria timezone (West Africa Time - UTC+1)
NIGERIA_TZ = pytz.timezone("Africa/Lagos")


def get_nigeria_time() -> datetime:
    """
    Get the current time in Nigeria (WAT / UTC+1).
    
    Use this instead of datetime.now() for all user-facing timestamps.
    """
    return datetime.now(NIGERIA_TZ)


def to_nigeria_time(dt: datetime) -> datetime:
    """
    Convert a datetime object to Nigeria time.
    
    Args:
        dt: A datetime object (naive or aware)
        
    Returns:
        Datetime in Nigeria timezone
    """
    if dt is None:
        return None
    
    # If naive (no timezone), assume it's UTC
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    
    return dt.astimezone(NIGERIA_TZ)


def get_nigeria_date() -> datetime.date:
    """Get current date in Nigeria."""
    return get_nigeria_time().date()


def get_nigeria_hour() -> int:
    """Get current hour (0-23) in Nigeria. Useful for reminder scheduling."""
    return get_nigeria_time().hour
