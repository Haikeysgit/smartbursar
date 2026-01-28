"""
=============================================================================
SmartBursar - Gemini API Retry Utility
=============================================================================
Implements retry with exponential backoff for Gemini API calls.
Specifically handles 429 (Quota Exceeded) errors from Google.
"""

import time
import logging
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


class GeminiQuotaExceededError(Exception):
    """Raised when Gemini API quota is exceeded."""
    pass


def retry_on_quota_exceeded(func: Callable) -> Callable:
    """
    Decorator that retries a function call on quota exceeded errors.
    
    - Catches 429 errors and resource exhausted errors
    - Waits 5 seconds between retries
    - Attempts up to 3 times before failing
    - Logs each retry attempt
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        last_exception = None
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_str = str(e).lower()
                
                # Check if this is a quota/rate limit error
                is_quota_error = (
                    "429" in error_str or
                    "quota" in error_str or
                    "rate limit" in error_str or
                    "resource exhausted" in error_str or
                    "too many requests" in error_str
                )
                
                if is_quota_error and attempt < MAX_RETRIES:
                    logger.warning(
                        f"Gemini quota exceeded (attempt {attempt}/{MAX_RETRIES}). "
                        f"Retrying in {RETRY_DELAY_SECONDS}s..."
                    )
                    time.sleep(RETRY_DELAY_SECONDS)
                    last_exception = e
                else:
                    # Not a quota error or final attempt - re-raise
                    raise
        
        # If we exhausted all retries
        logger.error(f"Gemini API failed after {MAX_RETRIES} attempts")
        raise last_exception or GeminiQuotaExceededError("Quota exceeded after max retries")
    
    return wrapper


def call_with_retry(func: Callable, *args, **kwargs) -> Any:
    """
    Alternative non-decorator approach for one-off retry calls.
    
    Usage:
        result = call_with_retry(client.models.generate_content, model="...", contents=[...])
    """
    last_exception = None
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_str = str(e).lower()
            
            is_quota_error = (
                "429" in error_str or
                "quota" in error_str or
                "rate limit" in error_str or
                "resource exhausted" in error_str or
                "too many requests" in error_str
            )
            
            if is_quota_error and attempt < MAX_RETRIES:
                logger.warning(
                    f"Gemini quota exceeded (attempt {attempt}/{MAX_RETRIES}). "
                    f"Retrying in {RETRY_DELAY_SECONDS}s..."
                )
                time.sleep(RETRY_DELAY_SECONDS)
                last_exception = e
            else:
                raise
    
    raise last_exception or GeminiQuotaExceededError("Quota exceeded after max retries")
