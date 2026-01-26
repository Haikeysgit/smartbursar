import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from decimal import Decimal

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class ReceiptExtractor:
    """
    Gemini-powered receipt OCR engine (Updated for google-genai SDK).
    """
    
    SYSTEM_PROMPT = """Analyze this image. If it is a payment receipt, extract the following fields in JSON format: {'amount': float, 'beneficiary_name': string, 'date': string, 'sender_name': string}. If any field is invisible, return null. Do not hallucinate values.
    Rules:
    1. Ignore currency symbols. Return numbers only.
    2. If not a receipt, return {"error": true, "reason": "Not a valid receipt"}.
    3. If unreadable, return {"error": true, "reason": "Image unreadable"}.
    """

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY", "")
        self.client = None
        
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info("Receipt Extractor initialized with google-genai SDK")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini Client: {e}")
        else:
            logger.warning("GOOGLE_API_KEY not set. Receipt extraction disabled.")
    
    def extract_from_file(self, file_path: str) -> Dict[str, Any]:
        if not self.client:
            return {"error": True, "reason": "Gemini not initialized"}
        
        try:
            # Read file bytes
            with open(file_path, "rb") as f:
                file_bytes = f.read()

            # Determine MIME type based on extension
            is_pdf = file_path.lower().endswith(".pdf")
            mime_type = "application/pdf" if is_pdf else "image/jpeg"

            # Create prompt with robust Blob construction
            prompt_content = [
                self.SYSTEM_PROMPT,
                types.Part(
                    inline_data=types.Blob(
                        mime_type=mime_type,
                        data=file_bytes
                    )
                )
            ]

            response = self.client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt_content,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            
            return self._parse_response(response.text)
            
        except Exception as e:
            logger.error(f"Receipt extraction failed: {e}")
            return {"error": True, "reason": f"AI Processing Failed: {str(e)}"}

    def extract_from_text(self, text: str) -> Dict[str, Any]:
        if not self.client:
            return {"error": True, "reason": "Gemini not initialized"}
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=[self.SYSTEM_PROMPT, text],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            return self._parse_response(response.text)
            
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")
            return {"error": True, "reason": "AI Processing Failed"}
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse strict JSON response."""
        try:
            if not response_text:
                return {"error": True, "reason": "Empty response from AI"}

            data = json.loads(response_text)
            
            if data.get("error"):
                return data

            # Sanity check amount
            amount = data.get("amount")
            if amount:
                try:
                    amt_float = float(amount)
                    if amt_float > 10_000_000:
                        return {"error": True, "reason": "Amount too large (Safety Check)"}
                except:
                    pass
            
            return data
            
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from Gemini: {response_text}")
            return {"error": True, "reason": "Invalid Data Format"}

# Singleton
receipt_extractor = ReceiptExtractor()
