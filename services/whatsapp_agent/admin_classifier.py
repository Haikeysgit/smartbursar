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

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Valid intent types
IntentType = Literal["APPROVED", "REJECTED", "UNKNOWN"]


class AdminClassifier:
    """
    Classifies admin replies into verification intents.
    
    Uses Gemini to understand natural language responses.
    """
    
    SYSTEM_PROMPT = """You are an Admin Intent Classifier for a school fee payment verification system.

Your task is to classify the admin's response into ONE of these categories:

APPROVED - The admin confirms the payment is valid.
Keywords/phrases: yes, confirmed, approved, okay, ok, seen, verified, valid, mark as paid, accept, correct, true, legit, genuine

REJECTED - The admin rejects the payment as fake or invalid.
Keywords/phrases: no, fake, reject, rejected, scam, fraud, not seen, invalid, lie, false, not valid, decline, wrong, bogus

UNKNOWN - The response is unrelated to payment verification or unclear.
Examples: "hello", "what?", random text, questions, off-topic messages

RULES:
1. Return ONLY ONE WORD: APPROVED, REJECTED, or UNKNOWN
2. Be case-insensitive when reading the admin's message
3. Nigerian slang: "e correct" = APPROVED, "na lie" = REJECTED
4. Partial words count: "conf" or "confir" likely means "confirmed" = APPROVED
5. If the message contains BOTH approval and rejection words, return UNKNOWN
6. Emojis: ✓ ✅ 👍 = APPROVED, ❌ 👎 🚫 = REJECTED

Examples:
"Yes, confirmed" -> APPROVED
"Fake receipt" -> REJECTED
"What's this about?" -> UNKNOWN
"E correct, I don see am" -> APPROVED
"Na scam be this" -> REJECTED
"✅" -> APPROVED"""

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY", "")
        self.model = None
        
        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(
                    model_name="gemini-1.5-flash",
                    system_instruction=self.SYSTEM_PROMPT
                )
                logger.info("Admin Classifier initialized with Gemini 1.5 Flash")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini for classifier: {e}")
        else:
            logger.warning("GOOGLE_API_KEY not set. Admin classification disabled.")
    
    def classify(self, admin_reply: str) -> IntentType:
        """
        Classify an admin's reply into APPROVED, REJECTED, or UNKNOWN.
        
        Args:
            admin_reply: The admin's message text
        
        Returns:
            Intent classification
        """
        if not self.model:
            # Fallback: simple keyword matching
            return self._fallback_classify(admin_reply)
        
        try:
            response = self.model.generate_content([
                f"Classify this admin reply: \"{admin_reply}\""
            ])
            
            result = response.text.strip().upper()
            
            # Validate response
            if result in ("APPROVED", "REJECTED", "UNKNOWN"):
                return result
            
            # Extract if response contains the word
            if "APPROVED" in result:
                return "APPROVED"
            if "REJECTED" in result:
                return "REJECTED"
            
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
