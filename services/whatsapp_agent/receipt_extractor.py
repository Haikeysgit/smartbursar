"""
=============================================================================
SmartBursar - Receipt Extractor (Gemini OCR)
=============================================================================
Uses Google Gemini 1.5 Flash to extract payment details from receipts.

Extracts:
- amount: Payment amount (number only, no currency symbol)
- date: Payment date (DD-MM-YYYY)
- bank_name: Bank name
- sender_name: Account holder name
- transaction_ref: Transaction reference number
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class ReceiptExtractor:
    """
    Gemini-powered receipt OCR engine.
    
    Extracts structured payment data from receipt images/PDFs.
    """
    
    SYSTEM_PROMPT = """You are a precise financial OCR engine for Nigerian bank receipts and transfer confirmations.

Analyze the input (image, PDF, or text) and extract these fields into a JSON object:

{
    "amount": <number - payment amount without currency symbols>,
    "date": "<string - payment date in DD-MM-YYYY format>",
    "bank_name": "<string - bank name, e.g., GTBank, First Bank, Access Bank>",
    "sender_name": "<string - name of the person who made the payment>",
    "transaction_ref": "<string - transaction reference number or session ID>",
    "error": false
}

STRICT RULES:
1. If the input is NOT a payment receipt or bank transfer confirmation, return: {"error": true, "reason": "Not a valid receipt"}
2. Ignore currency symbols (₦, NGN, N). Return amount as a number only.
3. If the image is blurry, corrupted, or unreadable, return: {"error": true, "reason": "Image unreadable"}
4. If a field is not found, use null for that field.
5. Return ONLY valid JSON. No explanations, no markdown.
6. Common Nigerian receipt formats: Bank alerts (SMS screenshots), transfer confirmations, POS receipts, bank statements.

Example valid output:
{"amount": 75000, "date": "11-01-2026", "bank_name": "GTBank", "sender_name": "John Doe", "transaction_ref": "NIP123456789", "error": false}"""

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
                logger.info("Receipt Extractor initialized with Gemini 1.5 Flash")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
        else:
            logger.warning("GOOGLE_API_KEY not set. Receipt extraction disabled.")
    
    def extract_from_file(self, file_path: str) -> Dict[str, Any]:
        """
        Extract payment details from a receipt file (image or PDF).
        
        Args:
            file_path: Path to the receipt file
        
        Returns:
            Dict with extracted fields or error
        """
        if not self.model:
            return {"error": True, "reason": "Gemini not initialized"}
        
        try:
            # Upload file to Gemini
            uploaded_file = genai.upload_file(file_path)
            
            # Generate response
            response = self.model.generate_content([
                "Extract payment details from this receipt:",
                uploaded_file
            ])
            
            # Parse JSON response
            return self._parse_response(response.text)
            
        except Exception as e:
            logger.error(f"Receipt extraction failed: {e}")
            return {"error": True, "reason": f"Extraction failed: {str(e)}"}
    
    def extract_from_text(self, text: str) -> Dict[str, Any]:
        """
        Extract payment details from text content.
        
        Args:
            text: Receipt text content
        
        Returns:
            Dict with extracted fields or error
        """
        if not self.model:
            return {"error": True, "reason": "Gemini not initialized"}
        
        try:
            response = self.model.generate_content([
                "Extract payment details from this receipt text:",
                text
            ])
            
            return self._parse_response(response.text)
            
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")
            return {"error": True, "reason": f"Extraction failed: {str(e)}"}
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse Gemini response into structured data.
        
        Args:
            response_text: Raw response from Gemini
        
        Returns:
            Parsed JSON dict
        """
        try:
            # Clean response (remove markdown code blocks if present)
            cleaned = response_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            # Parse JSON
            data = json.loads(cleaned)
            
            # Validate required fields
            if data.get("error"):
                return data
            
            # SECURITY: Amount sanity validation
            amount = data.get("amount")
            if amount is not None:
                try:
                    amount = float(amount)
                    # Cap at ₦10 million (unlikely school fee)
                    if amount > 10_000_000:
                        return {
                            "error": True, 
                            "reason": f"Amount ₦{amount:,.0f} exceeds maximum. Manual review required."
                        }
                    if amount <= 0:
                        return {"error": True, "reason": "Invalid amount (zero or negative)"}
                    # Flag large amounts for extra scrutiny
                    if amount > 1_000_000:
                        data["requires_extra_verification"] = True
                except (ValueError, TypeError):
                    return {"error": True, "reason": "Amount could not be parsed"}
            
            return {
                "amount": data.get("amount"),
                "date": data.get("date"),
                "bank_name": data.get("bank_name"),
                "sender_name": data.get("sender_name"),
                "transaction_ref": data.get("transaction_ref"),
                "requires_extra_verification": data.get("requires_extra_verification", False),
                "error": False
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response: {response_text}")
            return {"error": True, "reason": f"Invalid JSON response: {str(e)}"}


# Singleton instance
receipt_extractor = ReceiptExtractor()
