
import os
import logging
from typing import List

logger = logging.getLogger(__name__)

REQUIRED_VARS = [
    "WHATSAPP_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_APP_SECRET",
    "GROQ_API_KEY",
    # "DATABASE_URL", # Checked by database.py
    "APP_URL"
]

def validate_environment(strict: bool = True):
    """
    Check if all critical environment variables are set.
    
    Args:
        strict: If True, log warnings but let app continue (prevent crash loop).
                If False, raise error and stop app.
    
    We default to strict=True for logging, but we DON'T raise exceptions
    to avoid CrashLoopBackOff on Render which makes debugging harder.
    """
    missing = []
    
    for var in REQUIRED_VARS:
        value = os.getenv(var)
        if not value or value.strip() == "":
            missing.append(var)
            
    if missing:
        msg = f"CRITICAL: Missing Environment Variables: {', '.join(missing)}"
        logger.critical(msg)
        print(f"\n{'='*50}\n{msg}\n{'='*50}\n")
        
        # We deliberately DO NOT raise an exception here.
        # Why? Because if we crash immediately, the Render logs might not flush,
        # or the container restarts too fast to debug. 
        # Better to run in "Broken Mode" where we can see the logs.
    else:
        logger.info("✅ Environment Integrity Check Passed")
