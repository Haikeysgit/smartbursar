"""
=============================================================================
SmartBursar - Gemini AI Client
=============================================================================
Handles interaction with Google's Gemini API for generating
context-aware payment reminders.
"""

import os
import logging
from typing import Optional, Dict, Any
import google.generativeai as genai
from dotenv import load_dotenv

# Load env to ensure we have the key
load_dotenv()

logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.is_active = False
        
        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                # Using gemini-2.0-flash as it is the available model
                self.model = genai.GenerativeModel('gemini-2.0-flash')
                self.is_active = True
                logger.info("Gemini AI Client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini AI: {e}")
        else:
            logger.warning("GOOGLE_API_KEY not found. AI features disabled.")

    def generate_message(self, context: Dict[str, Any], tone: str = "polite") -> Optional[str]:
        """
        Generate a payment reminder message using Gemini.
        
        Args:
            context: Dictionary containing student and debt details
            tone: 'polite', 'firm', or 'urgent'
            
        Returns:
            Generated message string or None if generation fails
        """
        if not self.is_active:
            return None

        try:
            prompt = self._build_prompt(context, tone)
            
            # Generate content
            response = self.model.generate_content(prompt)
            
            if response.text:
                # SECURITY: Replace placeholders with real names LOCALLY
                # This ensures PII is never sent to Google
                message = self._replace_placeholders(response.text.strip(), context)
                return message
            return None
            
        except Exception as e:
            logger.error(f"Error generating message with Gemini: {e}")
            return None
            return None

    def _build_prompt(self, context: Dict[str, Any], tone: str) -> str:
        """
        Construct the prompt for the AI.
        
        SECURITY: We use anonymous placeholders to avoid sending PII to Google.
        The actual names are swapped back AFTER we receive the AI response.
        """
        
        # ANONYMIZED - We do NOT send real names to Google
        amount_due = context.get('amount_due', '0')
        due_date = context.get('due_date', 'soon')
        days_overdue = context.get('days_overdue', 0)
        
        base_instruction = (
            "You are a school Bursar. Write a short, professional WhatsApp payment reminder "
            "for a parent. Use the placeholder [STUDENT_NAME] for the student and [SCHOOL_NAME] for the school."
        )
        
        details = (
            f"\nDetails:"
            f"\n- Amount Due: {amount_due}"
            f"\n- Due Date: {due_date}"
            f"\n- Days Overdue: {days_overdue}"
        )
        
        tone_instruction = ""
        if tone == "polite":
            tone_instruction = (
                "\nTone: Friendly, polite, and understanding. Assume it might be an oversight. "
                "Keep it under 30 words."
            )
        elif tone == "firm":
            tone_instruction = (
                "\nTone: Professional and firm. Emphasize that the payment is late. "
                "Keep it under 30 words."
            )
        elif tone == "urgent":
            tone_instruction = (
                "\nTone: Urgent and serious. Mention potential consequences like denying entry. "
                "Keep it under 30 words."
            )
            
        constraints = (
            "\nOutput ONLY the message body. Do not include 'Subject:' or quotes. "
            "You MUST use [STUDENT_NAME] and [SCHOOL_NAME] as placeholders."
        )
        
        return f"{base_instruction}{details}{tone_instruction}{constraints}"
    
    def _replace_placeholders(self, message: str, context: Dict[str, Any]) -> str:
        """Replace anonymous placeholders with real names LOCALLY (not sent to Google)."""
        student_name = context.get('student_name', 'Student')
        school_name = context.get('school_name', 'the school')
        
        message = message.replace("[STUDENT_NAME]", student_name)
        message = message.replace("[SCHOOL_NAME]", school_name)
        return message

# Singleton instance
gemini_client = GeminiClient()
