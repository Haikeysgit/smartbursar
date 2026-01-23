"""
=============================================================================
SmartBursar - Universal File Handler
=============================================================================
Handles various file formats for receipt processing.

Supported Formats:
- Images: JPG, PNG, HEIC, WEBP
- Documents: PDF
- Text: DOCX, TXT

For images/PDFs: Pass directly to Gemini (it supports these natively)
For DOCX/TXT: Extract text first, then send to Gemini
"""

import os
import mimetypes
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

# Receipts storage directory
RECEIPTS_DIR = Path(__file__).parent.parent.parent / "receipts"
RECEIPTS_DIR.mkdir(exist_ok=True)


class FileHandler:
    """
    Universal file handler for receipt processing.
    
    Detects file type and prepares it for Gemini AI processing.
    """
    
    # MIME type mappings
    IMAGE_MIMES = {"image/jpeg", "image/png", "image/heic", "image/webp", "image/gif"}
    PDF_MIMES = {"application/pdf"}
    DOCX_MIMES = {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    TEXT_MIMES = {"text/plain"}
    
    def __init__(self):
        self.receipts_dir = RECEIPTS_DIR
        self.max_file_size = 10 * 1024 * 1024  # 10MB max
    
    def save_file_locally(self, file_content: bytes, original_filename: str) -> str:
        """
        Save uploaded file to local storage.
        
        Args:
            file_content: Raw file bytes
            original_filename: Original filename for extension detection
        
        Returns:
            Local file path
        
        Raises:
            ValueError: If file exceeds size limit
        """
        # SECURITY: Check file size limit
        if len(file_content) > self.max_file_size:
            raise ValueError(f"File too large. Maximum size: {self.max_file_size // 1024 // 1024}MB")
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        ext = Path(original_filename).suffix or ".bin"
        filename = f"receipt_{timestamp}_{unique_id}{ext}"
        
        file_path = self.receipts_dir / filename
        
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        logger.info(f"File saved: {file_path}")
        return str(file_path)
    
    def detect_mime_type(self, file_path: str) -> str:
        """
        Detect MIME type of a file.
        
        Args:
            file_path: Path to file
        
        Returns:
            MIME type string
        """
        mime_type, _ = mimetypes.guess_type(file_path)
        
        if not mime_type:
            # Fallback based on extension
            ext = Path(file_path).suffix.lower()
            ext_map = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".heic": "image/heic",
                ".webp": "image/webp",
                ".pdf": "application/pdf",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".txt": "text/plain",
            }
            mime_type = ext_map.get(ext, "application/octet-stream")
        
        return mime_type
    
    def prepare_for_gemini(self, file_path: str) -> Dict[str, Any]:
        """
        Prepare a file for Gemini AI processing.
        
        For images/PDFs: Returns file path for direct upload
        For DOCX/TXT: Extracts text content
        
        Args:
            file_path: Path to the file
        
        Returns:
            Dict with:
                - type: "file" or "text"
                - content: file path or extracted text
                - mime_type: MIME type
                - error: error message if any
        """
        mime_type = self.detect_mime_type(file_path)
        
        # Images - pass directly to Gemini
        if mime_type in self.IMAGE_MIMES:
            return {
                "type": "file",
                "content": file_path,
                "mime_type": mime_type,
                "error": None
            }
        
        # PDFs - pass directly to Gemini (it supports PDF natively)
        if mime_type in self.PDF_MIMES:
            return {
                "type": "file",
                "content": file_path,
                "mime_type": mime_type,
                "error": None
            }
        
        # DOCX - extract text
        if mime_type in self.DOCX_MIMES:
            text = self._extract_docx_text(file_path)
            if text:
                return {
                    "type": "text",
                    "content": text,
                    "mime_type": "text/plain",
                    "error": None
                }
            return {
                "type": "text",
                "content": "",
                "mime_type": "text/plain",
                "error": "Failed to extract text from DOCX"
            }
        
        # Plain text
        if mime_type in self.TEXT_MIMES:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
                return {
                    "type": "text",
                    "content": text,
                    "mime_type": "text/plain",
                    "error": None
                }
            except Exception as e:
                return {
                    "type": "text",
                    "content": "",
                    "mime_type": "text/plain",
                    "error": f"Failed to read text file: {e}"
                }
        
        # Unsupported format - try text extraction as fallback
        return {
            "type": "text",
            "content": "",
            "mime_type": mime_type,
            "error": f"Unsupported file type: {mime_type}"
        }
    
    def _extract_docx_text(self, file_path: str) -> Optional[str]:
        """
        Extract text from a DOCX file.
        
        Uses python-docx if available, otherwise returns None.
        """
        try:
            from docx import Document
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)
        except ImportError:
            logger.warning("python-docx not installed. Install with: pip install python-docx")
            # Fallback: try to extract raw text (won't be pretty but might work)
            try:
                import zipfile
                import re
                with zipfile.ZipFile(file_path) as z:
                    xml_content = z.read("word/document.xml").decode("utf-8")
                    # Strip XML tags - crude but effective
                    text = re.sub(r"<[^>]+>", "", xml_content)
                    return text.strip()
            except Exception:
                return None
        except Exception as e:
            logger.error(f"Failed to extract DOCX text: {e}")
            return None
    
    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """
        Delete files older than max_age_hours.
        
        Args:
            max_age_hours: Maximum file age in hours
        
        Returns:
            Number of files deleted
        """
        deleted = 0
        now = datetime.now()
        
        for file_path in self.receipts_dir.glob("*"):
            if file_path.is_file():
                try:
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    age_hours = (now - mtime).total_seconds() / 3600
                    
                    if age_hours > max_age_hours:
                        file_path.unlink()
                        deleted += 1
                        logger.info(f"Deleted old file: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to delete {file_path}: {e}")
        
        return deleted


# Singleton instance
file_handler = FileHandler()
