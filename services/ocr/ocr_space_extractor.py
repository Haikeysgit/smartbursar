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
        Apply strict ANCHOR-BASED parsing for Sender/Beneficiary extraction.
        
        CRITICAL: Only assign names if they follow a specific label anchor.
        DO NOT rely on line position or guess - require explicit labels.
        
        Sender Anchors: "Sender", "From", "Payer", "Sender Details", "Sent by"
        Recipient Anchors: "Beneficiary", "Receiver", "To", "Recipient", "Recipient Details", "Received by"
        """
        import re
        
        # Normalize text - split into lines for line-by-line analysis
        lines = text.split('\n')
        
        # Define anchor patterns with priority (most specific first)
        SENDER_ANCHORS = [
            r"sender\s*details?\s*[:\-]?\s*",
            r"sent\s*by\s*[:\-]?\s*",
            r"sender\s*[:\-]?\s*",
            r"from\s*[:\-]?\s*",
            r"payer\s*[:\-]?\s*",
            r"debited?\s*from\s*[:\-]?\s*",
        ]
        
        RECIPIENT_ANCHORS = [
            r"recipient\s*details?\s*[:\-]?\s*",
            r"beneficiary\s*[:\-]?\s*",
            r"receiver\s*[:\-]?\s*",
            r"received?\s*by\s*[:\-]?\s*",
            r"credited?\s*to\s*[:\-]?\s*",
            r"to\s*[:\-]\s*",  # Require colon/dash for "to" to avoid false positives
        ]
        
        # Reserved keywords/labels to skip (not actual names)
        RESERVED_KEYWORDS = [
            "transaction", "session", "reference", "amount", "date", "time",
            "status", "bank", "details", "name", "account", "number", "fee",
            "charge", "balance", "total", "transfer", "payment", "successful",
            "pending", "failed", "completed", "id", "no", "ref"
        ]
        
        def is_valid_name(text: str) -> bool:
            """Check if text is a valid person/company name (not a keyword or number)."""
            if not text:
                return False
            clean = text.strip()
            clean_lower = clean.lower()
            
            # Skip if too short
            if len(clean) < 3:
                return False
                
            # Skip if it's a reserved keyword
            for keyword in RESERVED_KEYWORDS:
                if keyword == clean_lower or clean_lower.startswith(keyword + " ") or clean_lower.endswith(" " + keyword):
                    return False
                    
            # Skip if it's mostly/all digits (like Transaction No)
            digits_only = clean.replace(" ", "").replace("-", "").replace(".", "")
            if digits_only.isdigit():
                return False
                
            # Skip if it looks like a phone number or account number
            if re.match(r"^[\d\+\-\s\(\)]{8,}$", clean):
                return False
                
            # Should contain at least some letters
            if not any(c.isalpha() for c in clean):
                return False
                
            return True
        
        def extract_name_after_anchor(line: str, anchor_pattern: str, lines: list, line_idx: int) -> str:
            """
            Extract name that appears AFTER an anchor label.
            Checks: (1) Same line after colon, (2) Next 1-2 lines.
            """
            # Try regex match on current line
            match = re.search(anchor_pattern + r"(.+)$", line, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                # Clean up any trailing punctuation
                candidate = re.sub(r"[:\-,;]+$", "", candidate).strip()
                if is_valid_name(candidate):
                    return candidate
            
            # Check if line contains ONLY the anchor (name on next line)
            anchor_only = re.match(anchor_pattern + r"$", line.strip(), re.IGNORECASE)
            if anchor_only or re.search(anchor_pattern.rstrip(r"\s*"), line, re.IGNORECASE):
                # Look at next 1-2 lines for a valid name
                for offset in [1, 2]:
                    if line_idx + offset < len(lines):
                        next_line = lines[line_idx + offset].strip()
                        # Skip if next line starts with another label
                        if any(re.match(p, next_line, re.IGNORECASE) for p in SENDER_ANCHORS + RECIPIENT_ANCHORS):
                            break
                        if is_valid_name(next_line):
                            return next_line
            
            return None
        
        # Execute anchor-based extraction
        sender_name = None
        beneficiary_name = None
        
        for i, line in enumerate(lines):
            line_clean = line.strip()
            if not line_clean:
                continue
                
            # Check for SENDER anchors
            if not sender_name:
                for anchor in SENDER_ANCHORS:
                    result = extract_name_after_anchor(line_clean, anchor, lines, i)
                    if result:
                        sender_name = result
                        logger.info(f"ANCHOR PARSE: Found Sender '{sender_name}' via anchor '{anchor}'")
                        break
            
            # Check for RECIPIENT anchors
            if not beneficiary_name:
                for anchor in RECIPIENT_ANCHORS:
                    result = extract_name_after_anchor(line_clean, anchor, lines, i)
                    if result:
                        beneficiary_name = result
                        logger.info(f"ANCHOR PARSE: Found Beneficiary '{beneficiary_name}' via anchor '{anchor}'")
                        break
        
        # Override parsed_data with anchor-extracted values (if found)
        if sender_name:
            logger.info(f"ANCHOR OVERRIDE: Setting sender_name = '{sender_name}'")
            parsed_data["sender_name"] = sender_name
        else:
            logger.warning("ANCHOR PARSE: No sender name found via anchors - leaving as-is")
            
        if beneficiary_name:
            logger.info(f"ANCHOR OVERRIDE: Setting beneficiary_name = '{beneficiary_name}'")
            parsed_data["beneficiary_name"] = beneficiary_name
        else:
            logger.warning("ANCHOR PARSE: No beneficiary name found via anchors - leaving as-is")
    
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
