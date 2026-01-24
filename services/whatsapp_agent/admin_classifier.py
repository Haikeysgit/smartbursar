"""
=============================================================================
SmartBursar - Admin Intent Classifier
=============================================================================
Uses Gemini to classify admin responses for payment verification.

Classifications:
- APPROVED: Admin confirms the payment is valid
- REJECTED: Admin rejects the payment as fake/invalid
- UNKNOWN: Response doesn't relate to verification
"""

import os
import logging
from typing import Literal

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Valid intent types
IntentType = Literal["APPROVED", "REJECTED", "UNKNOWN"]


class AdminClassifier:
    """
    Classifies admin replies into verification intents.
    """
    
    SYSTEM_PROMPT = """You are an Admin Intent Classifier.
    Classify the response into ONE of: APPROVED, REJECTED, UNKNOWN.
    
    - APPROVED: yes, confirmed, okay, seen, valid, correct, true, genuine, ✅, 👍, e correct
    - REJECTED: no, fake, reject, fraud, invalid, lie, false, wrong, bogus, na lie, ❌, 👎
    - UNKNOWN: unrelated text, questions
    
    Return ONLY the category word."""

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY", "")
        self.client = None
        
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info("Admin Classifier initialized with google-genai SDK")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini for classifier: {e}")
        else:
            logger.warning("GOOGLE_API_KEY not set. Admin classification disabled.")
    
    def classify(self, admin_reply: str) -> IntentType:
        if not self.client:
            return self._fallback_classify(admin_reply)
        
        try:
            response = self.client.models.generate_content(
                model="gemini-1.5-flash",
                contents=[self.SYSTEM_PROMPT, f"Admin says: '{admin_reply}'"],
                config=types.GenerateContentConfig(
                    response_mime_type="text/plain"
                )
            )
            
            result = response.text.strip().upper()
            
            if "APPROVED" in result: return "APPROVED"
            if "REJECTED" in result: return "REJECTED"
            if "UNKNOWN" in result: return "UNKNOWN"
            
            # Direct match
            if result in ("APPROVED", "REJECTED", "UNKNOWN"):
                return result
            
            return "UNKNOWN"
            
        except Exception as e:
            logger.error(f"Admin classification failed: {e}")
            return self._fallback_classify(admin_reply)
    
    def _fallback_classify(self, text: str) -> IntentType:
        """
        Simple keyword-based fallback classification.
        
        Used when Gemini is unavailable.
        """
        text_lower = text.lower().strip()
        
        # Approval keywords
        approve_keywords = [
            "yes", "confirm", "approved", "okay", "ok", "seen", "verified",
            "valid", "paid", "accept", "correct", "true", "legit", "genuine",
            "e correct", "i don see", "✓", "✅", "👍"
        ]
        
        # Rejection keywords
        reject_keywords = [
            "no", "fake", "reject", "scam", "fraud", "not seen", "invalid",
            "lie", "false", "decline", "wrong", "bogus", "na lie", "❌", "👎", "🚫"
        ]
        
        # Check for approval
        for keyword in approve_keywords:
            if keyword in text_lower:
                return "APPROVED"
        
        # Check for rejection
        for keyword in reject_keywords:
            if keyword in text_lower:
                return "REJECTED"
        
        return "UNKNOWN"


# Singleton instance
admin_classifier = AdminClassifier()
