"""
=============================================================================
SmartBursar - Groq Vision Receipt Extractor
=============================================================================
Sends receipt images DIRECTLY to Groq's vision model for parsing.
No OCR middleman. The AI sees the receipt spatially and returns structured JSON.

Replaces the old OCR.space + regex pipeline that caused name swap bugs.
=============================================================================
"""

import os
import io
import logging
import json
import base64
import time
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path

import httpx
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# ---- Model Priority (tried in order) ----
# Set GROQ_VISION_MODEL env var to override
DEFAULT_VISION_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",  # Latest, most capable
    "llama-3.2-11b-vision-preview",                 # Fallback
]

# ---- Image Constraints ----
MAX_IMAGE_DIMENSION = 1024      # Max pixels on longest side
JPEG_QUALITY = 85               # JPEG compression quality
MAX_BASE64_SIZE_MB = 3.5        # Stay safely under Groq's 4MB limit

# ---- Receipt Parsing Prompt ----
RECEIPT_SYSTEM_PROMPT = """You are a receipt parser AI. You are looking at a bank transfer receipt image.

Your job: Extract the payment details from this receipt and return ONLY valid JSON.

CRITICAL RULES FOR SENDER vs BENEFICIARY:
- "Sender" = the person who SENT/PAID the money (the payer, the source)
- "Beneficiary" = the person who RECEIVED the money (the payee, the destination)
- On OPay receipts: "Sender Details" section = the SENDER. "Recipient" section = the BENEFICIARY.
- On bank transfer receipts: "From" / "Source" / "Debited" = SENDER. "To" / "Destination" / "Credited" = BENEFICIARY.
- On PalmPay receipts: The name at the top under "Transfer to" is the BENEFICIARY, the sender name may be at the bottom or in "Account Name".
- NEVER swap these. If unsure, set the field to null.

Return ONLY this JSON format, no extra text:
{
    "amount": <number or null>,
    "beneficiary_name": "<string or null>",
    "sender_name": "<string or null>",
    "date": "<string or null>",
    "reference": "<string or null>",
    "bank_name": "<string or null>"
}

Rules:
- amount: The main transaction amount as a number (no currency symbols, no commas)
- beneficiary_name: Full name of who RECEIVED the money
- sender_name: Full name of who SENT the money
- date: Transaction date in any format found
- reference: Transaction reference/ID if present
- bank_name: The bank or payment platform (e.g., "OPay", "Access Bank", "UBA", "Spenda")
- Use null for any field you cannot find
- Return ONLY the JSON, no explanation"""


class GroqVisionExtractor:
    """
    Vision-first receipt parser.
    Sends receipt images directly to Groq's vision model.
    
    Flow:
        1. Compress image (resize + JPEG) to stay under API limits
        2. Base64 encode
        3. Send to Groq vision model
        4. Parse JSON response
    
    On failure: Returns error dict (caller handles user messaging).
    """
    
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY", "")
        self.model_override = os.getenv("GROQ_VISION_MODEL", "")
        
        if self.api_key:
            logger.info("✅ Groq Vision Extractor initialized")
        else:
            logger.warning("⚠️ GROQ_API_KEY not set — Vision extraction disabled")
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    def extract_from_file(self, file_path: str) -> Dict[str, Any]:
        """
        Extract payment details from a receipt image.
        
        Args:
            file_path: Path to the receipt image file
            
        Returns:
            Dict with keys: amount, beneficiary_name, sender_name, date, 
            reference, bank_name, error, reason
        """
        if not self.api_key:
            return {"error": True, "reason": "Vision service not configured (no API key)"}
        
        try:
            # Step 1: Compress & encode image
            image_b64, mime_type = self._prepare_image(file_path)
            if not image_b64:
                return {"error": True, "reason": "Could not read or compress image"}
            
            # Step 2: Call Groq Vision API (with model fallback + retry)
            result = self._call_vision_api(image_b64, mime_type)
            return result
            
        except Exception as e:
            logger.error(f"Vision extraction failed: {e}")
            return {"error": True, "reason": f"Vision processing failed: {str(e)}"}
    
    async def extract_from_file_async(self, file_path: str) -> Dict[str, Any]:
        """Async wrapper — runs blocking vision call in thread executor."""
        loop = asyncio.get_event_loop()
        logger.info(f"🔄 VISION: Starting async extraction for {file_path}")
        
        try:
            result = await loop.run_in_executor(None, self.extract_from_file, file_path)
            logger.info(f"✅ VISION: Async extraction complete")
            return result
        except Exception as e:
            logger.error(f"❌ VISION: Async executor failed: {e}")
            return {"error": True, "reason": f"Async vision processing failed: {str(e)}"}
    
    # =========================================================================
    # IMAGE PREPARATION
    # =========================================================================
    
    def _prepare_image(self, file_path: str) -> tuple:
        """
        Compress and base64-encode an image for the Groq API.
        
        - Resizes to max 1024px on longest side
        - Converts to JPEG (quality 85)
        - Returns (base64_string, mime_type) or (None, None) on failure
        """
        try:
            path = Path(file_path)
            if not path.exists():
                logger.error(f"Image file not found: {file_path}")
                return None, None
            
            # Handle PDF files — convert first page to image
            if path.suffix.lower() == ".pdf":
                logger.info("PDF detected — converting first page to image")
                try:
                    import fitz  # PyMuPDF
                    doc = fitz.open(file_path)
                    if len(doc) == 0:
                        logger.error("PDF has no pages")
                        doc.close()
                        return None, None
                    page = doc[0]  # First page only
                    # Render at 150 DPI (not 300) — saves ~4x memory on Render's 512MB free tier
                    # 150 DPI is plenty since we resize to 1024px anyway
                    mat = fitz.Matrix(150/72, 150/72)
                    pix = page.get_pixmap(matrix=mat)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    logger.info(f"PDF page rendered: {pix.width}x{pix.height}")
                    # Explicit cleanup to free memory immediately
                    del pix
                    doc.close()
                    del doc
                except Exception as pdf_err:
                    logger.error(f"PDF conversion failed: {pdf_err}")
                    return None, None
            else:
                # Open regular image
                img = Image.open(file_path)
            
            # Convert RGBA/P to RGB (JPEG doesn't support transparency)
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")
            
            # Resize if too large
            original_size = img.size
            img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)
            
            if img.size != original_size:
                logger.info(f"Image resized: {original_size} → {img.size}")
            
            # Compress to JPEG in memory
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            buffer.seek(0)
            
            # Base64 encode
            image_bytes = buffer.getvalue()
            size_mb = len(image_bytes) / (1024 * 1024)
            
            if size_mb > MAX_BASE64_SIZE_MB:
                # Try harder compression
                logger.warning(f"Image still {size_mb:.1f}MB after compression, trying lower quality")
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=60, optimize=True)
                buffer.seek(0)
                image_bytes = buffer.getvalue()
                size_mb = len(image_bytes) / (1024 * 1024)
                
                if size_mb > MAX_BASE64_SIZE_MB:
                    logger.error(f"Image too large even after aggressive compression: {size_mb:.1f}MB")
                    return None, None
            
            logger.info(f"Image compressed: {size_mb:.2f}MB, ready for vision API")
            
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            return image_b64, "image/jpeg"
            
        except Exception as e:
            logger.error(f"Image preparation failed: {e}")
            return None, None
    
    # =========================================================================
    # GROQ VISION API CALL
    # =========================================================================
    
    def _call_vision_api(self, image_b64: str, mime_type: str) -> Dict[str, Any]:
        """
        Call Groq's vision API with model fallback and retry logic.
        
        Strategy:
            1. Try configured model (env var) or first default model
            2. If model fails (404), try next model in list
            3. If rate limited (429), wait 2s and retry once
            4. On any other error, return error dict
        """
        models_to_try = self._get_model_list()
        
        for model_id in models_to_try:
            result = self._try_model(model_id, image_b64, mime_type)
            
            if result.get("_model_not_found"):
                # This model doesn't exist, try next
                logger.warning(f"Model {model_id} not found, trying next...")
                continue
            
            return result
        
        # All models failed
        return {"error": True, "reason": "All vision models failed. Please resend your receipt in 2 minutes."}
    
    def _try_model(self, model_id: str, image_b64: str, mime_type: str, 
                   is_retry: bool = False) -> Dict[str, Any]:
        """
        Attempt to call a specific vision model. Handles rate limits with one retry.
        """
        logger.info(f"VISION: Calling model {model_id}" + (" (retry)" if is_retry else ""))
        
        payload = {
            "model": model_id,
            "messages": [
                {
                    "role": "system",
                    "content": RECEIPT_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Parse this receipt image and extract the payment details:"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_b64}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.1,
            "max_tokens": 300
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(GROQ_API_URL, json=payload, headers=headers)
            
            # ---- Handle specific HTTP errors ----
            
            if response.status_code == 404:
                logger.warning(f"Model {model_id} returned 404 — not available")
                return {"_model_not_found": True}
            
            if response.status_code == 429:
                if not is_retry:
                    logger.warning(f"Rate limited on {model_id} — waiting 2s for retry")
                    time.sleep(2)
                    return self._try_model(model_id, image_b64, mime_type, is_retry=True)
                else:
                    logger.error(f"Rate limited on {model_id} even after retry")
                    return {
                        "error": True, 
                        "reason": "rate_limited",
                        "user_message": "⏳ Our receipt reader is temporarily busy. Please resend your receipt in 2 minutes."
                    }
            
            if response.status_code == 413:
                logger.error(f"Payload too large for {model_id}")
                return {"error": True, "reason": "Image too large for API"}
            
            if response.status_code != 200:
                logger.error(f"Groq Vision API error {response.status_code}: {response.text[:300]}")
                return {"error": True, "reason": f"API error (HTTP {response.status_code})"}
            
            # ---- Parse successful response ----
            return self._parse_response(response.json(), model_id)
            
        except httpx.TimeoutException:
            logger.error(f"Timeout calling {model_id}")
            return {"error": True, "reason": "Vision API timed out. Please resend your receipt."}
        except Exception as e:
            logger.error(f"Error calling {model_id}: {e}")
            return {"error": True, "reason": f"Vision API error: {str(e)}"}
    
    def _parse_response(self, response_json: dict, model_id: str) -> Dict[str, Any]:
        """
        Parse the Groq API response and extract the JSON receipt data.
        """
        try:
            content = response_json["choices"][0]["message"]["content"]
            logger.info(f"VISION ({model_id}): Raw response: {content[:200]}")
            
            # Clean markdown code blocks if present
            cleaned = content.strip()
            if cleaned.startswith("```"):
                # Remove ```json ... ``` wrapper
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned
                cleaned = cleaned.strip()
            
            # Parse JSON
            parsed = json.loads(cleaned)
            
            # Normalize output — ensure all expected keys exist
            result = {
                "amount": parsed.get("amount"),
                "beneficiary_name": parsed.get("beneficiary_name"),
                "sender_name": parsed.get("sender_name"),
                "date": parsed.get("date"),
                "reference": parsed.get("reference"),
                "bank_name": parsed.get("bank_name"),
                "error": False,
                "extraction_method": f"groq_vision:{model_id}"
            }
            
            logger.info(
                f"✅ VISION PARSED: sender={result['sender_name']}, "
                f"beneficiary={result['beneficiary_name']}, "
                f"amount={result['amount']}, bank={result['bank_name']}"
            )
            
            return result
            
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error(f"Failed to parse vision response: {e}")
            logger.error(f"Raw content: {response_json}")
            return {"error": True, "reason": f"AI returned unparseable response: {str(e)}"}
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _get_model_list(self) -> list:
        """Get ordered list of models to try."""
        if self.model_override:
            # User specified a model — try it first, then defaults
            return [self.model_override] + [m for m in DEFAULT_VISION_MODELS if m != self.model_override]
        return DEFAULT_VISION_MODELS


# =============================================================================
# Singleton
# =============================================================================
groq_vision_extractor = GroqVisionExtractor()
