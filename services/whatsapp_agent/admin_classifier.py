"""
=============================================================================
SmartBursar - Admin Intent Classifier
=============================================================================
Uses Groq to classify admin responses for payment verification.

Classifications:
- APPROVED: Admin confirms the payment is valid
- REJECTED: Admin rejects the payment as fake/invalid
- UNKNOWN: Response doesn't relate to verification
"""

import os
import logging
from typing import Literal

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Valid intent types
IntentType = Literal["APPROVED", "REJECTED", "UNKNOWN"]

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


class AdminClassifier:
    """
    Classifies admin replies into verification intents using Groq.
    """
    
    SYSTEM_PROMPT = """You are an Admin Intent Classifier.
    Classify the response into ONE of: APPROVED, REJECTED, UNKNOWN.
    
    - APPROVED: yes, confirmed, okay, seen, valid, correct, true, genuine, ✅, 👍, e correct
    - REJECTED: no, fake, reject, fraud, invalid, lie, false, wrong, bogus, na lie, ❌, 👎
    - UNKNOWN: unrelated text, questions
    
    Return ONLY the category word, nothing else."""

    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY", "")
        
        if self.api_key:
            logger.info("Admin Classifier initialized with Groq")
        else:
            logger.warning("GROQ_API_KEY not set. Using fallback classification.")
    
    def classify(self, admin_reply: str) -> IntentType:
        if not self.api_key:
            return self._fallback_classify(admin_reply)
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "llama-3.1-8b-instant",  # Fast model for classification
                "messages": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": f"Admin says: '{admin_reply}'"}
                ],
                "temperature": 0.1,
                "max_tokens": 20
            }
            
            with httpx.Client(timeout=15.0) as client:
                response = client.post(GROQ_API_URL, headers=headers, json=payload)
                response.raise_for_status()
                
                result = response.json()
                intent = result["choices"][0]["message"]["content"].strip().upper()
            
            if "APPROVED" in intent: return "APPROVED"
            if "REJECTED" in intent: return "REJECTED"
            if "UNKNOWN" in intent: return "UNKNOWN"
            
            # Direct match
            if intent in ("APPROVED", "REJECTED", "UNKNOWN"):
                return intent
            
            return "UNKNOWN"
            
        except Exception as e:
            logger.error(f"Admin classification failed: {e}")
            return self._fallback_classify(admin_reply)
    
    def _fallback_classify(self, text: str) -> IntentType:
        """
        Simple keyword-based fallback classification.
        
        Used when Groq is unavailable.
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
