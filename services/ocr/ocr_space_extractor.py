"""
=============================================================================
SmartBursar - OCR.space Receipt Extractor
=============================================================================
Uses OCR.space free API to extract text from receipt images,
then uses Groq to parse the extracted text into structured data.
"""

import os
import logging
import json
import base64
from typing import Dict, Any
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OCR_SPACE_URL = "https://api.ocr.space/parse/image"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


class OCRSpaceExtractor:
    """
    Two-stage receipt extractor:
    1. OCR.space extracts text from image
    2. Groq parses the text to extract payment details
    """
    
    def __init__(self):
        self.ocr_api_key = os.getenv("OCR_SPACE_API_KEY", "")
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        
        if self.ocr_api_key and self.groq_api_key:
            logger.info("OCR.space + Groq Receipt Extractor initialized")
        else:
            if not self.ocr_api_key:
                logger.warning("OCR_SPACE_API_KEY not set. Receipt OCR disabled.")
            if not self.groq_api_key:
                logger.warning("GROQ_API_KEY not set. Receipt parsing disabled.")
    
    def extract_from_file(self, file_path: str) -> Dict[str, Any]:
        """
        Extract payment details from a receipt image file.
        """
        if not self.ocr_api_key or not self.groq_api_key:
            return {"error": True, "reason": "OCR service not configured"}
        
        try:
            # Step 1: Extract text using OCR.space
            ocr_text = self._ocr_extract(file_path)
            
            if not ocr_text:
                return {"error": True, "reason": "Could not read text from image"}
            
            logger.info(f"OCR extracted text: {ocr_text[:200]}...")
            
            # Step 2: Parse text using Groq
            return self._parse_receipt_text(ocr_text)
            
        except Exception as e:
            logger.error(f"Receipt extraction failed: {e}")
            return {"error": True, "reason": f"Processing failed: {str(e)}"}
    
    def _ocr_extract(self, file_path: str) -> str:
        """Use OCR.space API to extract text from image."""
        try:
            # Read and encode file
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            
            # Determine file type
            is_pdf = file_path.lower().endswith(".pdf")
            
            # Prepare multipart form data
            files = {
                "file": (Path(file_path).name, file_bytes)
            }
            
            data = {
                "apikey": self.ocr_api_key,
                "language": "eng",
                "isOverlayRequired": "false",
                "detectOrientation": "true",
                "scale": "true",
                "OCREngine": "2"  # More accurate engine
            }
            
            if is_pdf:
                data["isCreateSearchablePdf"] = "false"
            
            with httpx.Client(timeout=60.0) as client:
                response = client.post(OCR_SPACE_URL, data=data, files=files)
                response.raise_for_status()
                
                result = response.json()
                
                if result.get("IsErroredOnProcessing"):
                    logger.error(f"OCR.space error: {result.get('ErrorMessage')}")
                    return ""
                
                # Extract text from all parsed results
                parsed_results = result.get("ParsedResults", [])
                if parsed_results:
                    return parsed_results[0].get("ParsedText", "")
                
                return ""
                
        except Exception as e:
            logger.error(f"OCR.space extraction failed: {e}")
            return ""
    
    def _parse_receipt_text(self, text: str) -> Dict[str, Any]:
        """Use Groq to parse receipt text into structured data."""
        try:
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "system", "content": """You are a receipt parser. Extract payment details from the text and return ONLY valid JSON in this exact format:
{
    "amount": <number or null>,
    "beneficiary_name": "<string or null>",
    "sender_name": "<string or null>",
    "date": "<string or null>",
    "reference": "<string or null>"
}

Rules:
- amount: Extract the main transaction amount as a number (no currency symbols)
- beneficiary_name: Who received the payment (school name, account name)
- sender_name: Who sent the payment (payer name)
- date: Transaction date in any format found
- reference: Transaction reference/ID if present
- Use null for any field you cannot find
- Return ONLY the JSON, no other text"""},
                    {"role": "user", "content": f"Parse this receipt:\n\n{text}"}
                ],
                "temperature": 0.1,
                "max_tokens": 200
            }
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(GROQ_API_URL, headers=headers, json=payload)
                response.raise_for_status()
                
                result = response.json()
                content = result["choices"][0]["message"]["content"].strip()
                
                # Try to parse JSON from response
                try:
                    # Handle potential markdown code blocks
                    if "```" in content:
                        content = content.split("```")[1]
                        if content.startswith("json"):
                            content = content[4:]
                        content = content.strip()
                    
                    parsed = json.loads(content)
                    parsed["error"] = False
                    return parsed
                    
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse Groq response as JSON: {content}")
                    return {"error": True, "reason": "Could not parse receipt details"}
                
        except Exception as e:
            logger.error(f"Groq parsing failed: {e}")
            return {"error": True, "reason": "AI parsing failed"}
    
    def extract_from_text(self, text: str) -> Dict[str, Any]:
        """
        Extract payment details from text description.
        Used when parent describes payment in words.
        """
        if not self.groq_api_key:
            return {"error": True, "reason": "AI service not configured"}
        
        return self._parse_receipt_text(text)


# Create singleton instance
receipt_extractor = OCRSpaceExtractor()
