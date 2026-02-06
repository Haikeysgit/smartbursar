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
            logger.info(f"OCR.space: Starting extraction for {file_path}")
            
            # Read and encode file
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            
            logger.info(f"OCR.space: File size = {len(file_bytes)} bytes")
            
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
            
            logger.info(f"OCR.space: Sending request to API...")
            
            with httpx.Client(timeout=60.0) as client:
                response = client.post(OCR_SPACE_URL, data=data, files=files)
                logger.info(f"OCR.space: Response status = {response.status_code}")
                response.raise_for_status()
                
                result = response.json()
                logger.info(f"OCR.space: Response keys = {result.keys()}")
                
                if result.get("IsErroredOnProcessing"):
                    error_msg = result.get("ErrorMessage", ["Unknown error"])
                    logger.error(f"OCR.space error: {error_msg}")
                    return ""
                
                # Extract text from all parsed results
                parsed_results = result.get("ParsedResults", [])
                logger.info(f"OCR.space: Found {len(parsed_results)} parsed results")
                
                if parsed_results:
                    text = parsed_results[0].get("ParsedText", "")
                    logger.info(f"OCR.space: Extracted {len(text)} characters of text")
                    return text
                
                logger.warning("OCR.space: No parsed results returned")
                return ""
                
        except Exception as e:
            logger.error(f"OCR.space extraction failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
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
                    
                    # --- CRITICAL FIX: OPay Strict Label Extraction ---
                    # The LLM sometimes swaps Sender/Receiver on OPay receipts.
                    # We run a strict regex pass to correct this if labels are found.
                    self._apply_strict_opay_rules(text, parsed)
                    
                    return parsed
                    
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse Groq response as JSON: {content}")
                    return {"error": True, "reason": "Could not parse receipt details"}
                
        except Exception as e:
            logger.error(f"Groq parsing failed: {e}")
            return {"error": True, "reason": "AI parsing failed"}

    def _apply_strict_opay_rules(self, text: str, parsed_data: Dict[str, Any]):
        """
        Apply strict regex rules for OPay and similar templates where
        Sender/Receiver are clearly labeled but often swapped by AI.
        """
        import re
        
        # Normalize text for easier matching
        # Replace multiple newlines with single newline to handle spacing
        # Keep case for name extraction but use case-insensitive matching for labels
        lines = text.split('\n')
        
        # Regex patterns for OPay and common apps
        # We look for the Label, then capture the text on the SAME line or NEXT line.
        patterns = {
            "sender": [
                r"Sender Details\s*[:\-\n]?\s*([A-Za-z\s\.]+)",
                r"Sender\s*[:\-\n]?\s*([A-Za-z\s\.]+)",
                r"From\s*[:\-\n]?\s*([A-Za-z\s\.]+)"
            ],
            "beneficiary": [
                r"Recipient Details\s*[:\-\n]?\s*([A-Za-z\s\.]+)",
                r"Beneficiary\s*[:\-\n]?\s*([A-Za-z\s\.]+)",
                r"Receiver\s*[:\-\n]?\s*([A-Za-z\s\.]+)",
                r"To\s*[:\-\n]?\s*([A-Za-z\s\.]+)"
            ]
        }
        
        # Helper to find match
        def find_value(type_patterns):
            for pattern in type_patterns:
                # Search the whole text? Or iterate lines?
                # Text usually comes from OCR with newlines.
                # Let's try finding the LABEL, then looking at immediate context.
                
                # regex that matches "Label: Value" or "Label \n Value"
                # (?i) = case insensitive flag
                # \s* = optional whitespace
                # ([^\n]+) = capture rest of line or next non-empty line?
                
                # Better approach: Iterate lines to find label, grab next non-empty line or same line
                for i, line in enumerate(lines):
                    clean_line = line.strip().lower()
                    
                    # Check if line contains label
                    # Remove " Details" to match "Sender" or "Sender Details"
                    label_key = pattern.split(r"\s")[0].lower().replace("\\", "") # approximate extraction of "sender" from regex
                    
                    if "sender" in pattern.lower() and ("sender details" in clean_line or "sender:" in clean_line):
                        # Found label. Correct value is likely here or next line.
                        # Check if value is on same line: "Sender Details: John Doe"
                        parts = line.split(":", 1)
                        if len(parts) > 1 and parts[1].strip():
                            val = parts[1].strip()
                            # Check if it's just "Details" or empty
                            if val.lower() not in ["details", "name", "bank"]: 
                                return val
                                
                        # Else check next lines
                        if i + 1 < len(lines):
                            next_line = lines[i+1].strip()
                            if next_line and len(next_line) > 3: # Avoid grabbing "Amount" or "Date"
                                return next_line
                                
                    if "recipient" in pattern.lower() and ("recipient details" in clean_line or "beneficiary" in clean_line):
                        parts = line.split(":", 1)
                        if len(parts) > 1 and parts[1].strip():
                             val = parts[1].strip()
                             if val.lower() not in ["details", "name", "bank"]:
                                 return val
                        if i + 1 < len(lines):
                            next_line = lines[i+1].strip()
                            if next_line:
                                return next_line
                                
            return None

        # Execute extraction
        strict_sender = find_value(patterns["sender"])
        strict_beneficiary = find_value(patterns["beneficiary"])
        
        # Override if found
        if strict_sender:
            logger.info(f"STRICT OCR: Overriding Sender with '{strict_sender}'")
            parsed_data["sender_name"] = strict_sender
            
        if strict_beneficiary:
            logger.info(f"STRICT OCR: Overriding Beneficiary with '{strict_beneficiary}'")
            parsed_data["beneficiary_name"] = strict_beneficiary
    
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
