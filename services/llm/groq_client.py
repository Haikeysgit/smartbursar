"""
=============================================================================
SmartBursar - Groq AI Client
=============================================================================
Handles interaction with Groq API for generating context-aware responses.
Uses Llama 3 models for fast, high-quality text generation.
"""

import os
import logging
from typing import Optional, Dict, Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqClient:
    """Groq API client for text generation."""
    
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        self.model = "llama-3.3-70b-versatile"  # Groq production model
        
        if self.api_key:
            logger.info("Groq AI Client initialized successfully (Llama 3)")
        else:
            logger.warning("GROQ_API_KEY not found. AI features disabled.")
    
    @property
    def is_active(self) -> bool:
        """Check if client is initialized."""
        return bool(self.api_key)

    def generate_message(self, context: Dict[str, Any], tone: str = "polite", custom_prompt: str = None) -> Optional[str]:
        """
        Generate a response using Groq's Llama model.
        """
        if not self.is_active:
            logger.warning("Groq generate_message skipped: API key missing")
            return None
        
        try:
            # Use custom prompt if provided, otherwise build from context
            if custom_prompt:
                prompt = custom_prompt
            else:
                prompt = self._build_prompt(context, tone)
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a helpful school payment assistant. Be concise and friendly."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(GROQ_API_URL, headers=headers, json=payload)
                response.raise_for_status()
                
                result = response.json()
                message = result["choices"][0]["message"]["content"].strip()
                
                # Replace placeholders with real data
                message = self._replace_placeholders(message, context)
                return message
                
        except Exception as e:
            logger.error(f"Error generating message with Groq: {e}")
            return None
    
    def _build_prompt(self, context: Dict[str, Any], tone: str) -> str:
        """Build a prompt from context."""
        students = context.get("students", [])
        
        if not students:
            return "Generate a friendly greeting for a new user contacting a school payment system."
        
        student = students[0]
        prompt = f"""Generate a {tone} payment reminder for:
- Student: [STUDENT_NAME]
- Balance: ₦{student.get('balance', 0):,.2f}
- Status: {student.get('payment_status', 'PENDING')}

Keep it brief (2-3 sentences), friendly, and mention their specific balance."""
        
        return prompt
    
    def _replace_placeholders(self, message: str, context: Dict[str, Any]) -> str:
        """Replace placeholders with actual values."""
        students = context.get("students", [])
        
        if students:
            student = students[0]
            message = message.replace("[STUDENT_NAME]", student.get("full_name", "your child"))
            message = message.replace("[PARENT_NAME]", context.get("parent_name", ""))
        
        return message
    
    def analyze_intent(self, user_message: str) -> Dict[str, Any]:
        """
        Analyze user message to determine intent.
        Returns: {"intent": str, "confidence": float, "entities": dict}
        """
        if not self.api_key:
            return {"intent": "UNKNOWN", "confidence": 0.0, "entities": {}}
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "llama-3.1-8b-instant",  # Fast production model
                "messages": [
                    {"role": "system", "content": """Classify the user's intent. Return ONLY one of these categories:
- CHECK_BALANCE: User wants to know how much they owe
- MAKE_PAYMENT: User wants to pay or has paid
- SUBMIT_RECEIPT: User is sending proof of payment
- GREETING: User is saying hello
- QUESTION: User has a question
- OTHER: Anything else

Respond with just the category name, nothing else."""},
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0.1,
                "max_tokens": 20
            }
            
            with httpx.Client(timeout=15.0) as client:
                response = client.post(GROQ_API_URL, headers=headers, json=payload)
                response.raise_for_status()
                
                result = response.json()
                intent = result["choices"][0]["message"]["content"].strip().upper()
                
                # Normalize intent
                valid_intents = ["CHECK_BALANCE", "MAKE_PAYMENT", "SUBMIT_RECEIPT", "GREETING", "QUESTION", "OTHER"]
                if intent not in valid_intents:
                    intent = "OTHER"
                
                return {"intent": intent, "confidence": 0.9, "entities": {}}
                
        except Exception as e:
            logger.error(f"Error analyzing intent with Groq: {e}")
            return {"intent": "UNKNOWN", "confidence": 0.0, "entities": {}}


# Singleton instance
groq_client = GroqClient()
