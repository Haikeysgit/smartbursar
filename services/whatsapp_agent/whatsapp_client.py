"""
=============================================================================
SmartBursar - WhatsApp Cloud API Client
=============================================================================
Official Meta WhatsApp Cloud API integration.

Features:
- Send text messages
- Send media messages (images, documents)
- Webhook verification for Meta handshake
- Download media from WhatsApp servers

Environment Variables Required:
- WHATSAPP_TOKEN: Meta Graph API access token
- WHATSAPP_PHONE_NUMBER_ID: WhatsApp Business Phone Number ID
- WHATSAPP_VERIFY_TOKEN: Custom token for webhook verification
"""

import os
import logging
import requests
from typing import Optional, Dict, Any
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class WhatsAppCloudAPI:
    """
    Official Meta WhatsApp Cloud API client.
    
    Usage:
        wa = WhatsAppCloudAPI()
        wa.send_text("+2348012345678", "Hello from SmartBursar!")
    """
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self):
        self.token = os.getenv("WHATSAPP_TOKEN", "")
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        self.verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "smartbursar_verify_2026")
        
        if not self.token or not self.phone_number_id:
            logger.warning("WhatsApp Cloud API credentials not configured. Set WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID in .env")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    # =========================================================================
    # Sending Messages
    # =========================================================================
    
    def send_text(self, to: str, message: str) -> Dict[str, Any]:
        """
        Send a text message.
        
        Args:
            to: Recipient phone number (E.164 format, e.g., +2348012345678)
            message: Text message content
        
        Returns:
            API response dict
        """
        # Clean phone number (remove + for API)
        to_clean = to.replace("+", "").replace(" ", "").replace("-", "")
        
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_clean,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            logger.info(f"Message sent to {to_clean}: {result.get('messages', [{}])[0].get('id', 'unknown')}")
            return {"success": True, "data": result}
        except requests.exceptions.HTTPError as e:
            # Log the FULL error response from Meta
            error_detail = ""
            try:
                error_detail = e.response.json()
                logger.error(f"WhatsApp API Error: {error_detail}")
            except:
                error_detail = e.response.text
                logger.error(f"WhatsApp API Error (raw): {error_detail}")
            return {"success": False, "error": str(e), "detail": error_detail}
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send WhatsApp message: {e}")
            return {"success": False, "error": str(e)}
    
    def send_image(self, to: str, image_url: str, caption: str = "") -> Dict[str, Any]:
        """
        Send an image message.
        
        Args:
            to: Recipient phone number
            image_url: Public URL of the image
            caption: Optional caption text
        
        Returns:
            API response dict
        """
        to_clean = to.replace("+", "").replace(" ", "").replace("-", "")
        
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_clean,
            "type": "image",
            "image": {
                "link": image_url,
                "caption": caption
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            return {"success": True, "data": response.json()}
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send image: {e}")
            return {"success": False, "error": str(e)}
    
    def send_document(self, to: str, document_url: str, filename: str, caption: str = "") -> Dict[str, Any]:
        """
        Send a document message.
        
        Args:
            to: Recipient phone number
            document_url: Public URL of the document
            filename: Display filename
            caption: Optional caption
        
        Returns:
            API response dict
        """
        to_clean = to.replace("+", "").replace(" ", "").replace("-", "")
        
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_clean,
            "type": "document",
            "document": {
                "link": document_url,
                "filename": filename,
                "caption": caption
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            return {"success": True, "data": response.json()}
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send document: {e}")
            return {"success": False, "error": str(e)}
    
    # =========================================================================
    # Media Download
    # =========================================================================
    
    def download_media(self, media_id: str, save_path: str) -> Optional[str]:
        """
        Download media from WhatsApp servers.
        
        Args:
            media_id: WhatsApp media ID from webhook
            save_path: Local path to save the file
        
        Returns:
            Local file path if successful, None otherwise
        """
        try:
            # Step 1: Get media URL
            url = f"{self.BASE_URL}/{media_id}"
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            media_url = response.json().get("url")
            
            if not media_url:
                logger.error("No media URL returned")
                return None
            
            # Step 2: Download the actual file
            file_response = requests.get(
                media_url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=60
            )
            file_response.raise_for_status()
            
            # Step 3: Save to disk
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(file_response.content)
            
            logger.info(f"Media downloaded: {save_path}")
            return save_path
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download media: {e}")
            return None
    
    # =========================================================================
    # Webhook Verification (for Meta handshake)
    # =========================================================================
    
    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """
        Verify webhook subscription (GET request from Meta).
        
        Args:
            mode: hub.mode from query params
            token: hub.verify_token from query params
            challenge: hub.challenge from query params
        
        Returns:
            Challenge string if valid, None otherwise
        """
        if mode == "subscribe" and token == self.verify_token:
            logger.info("Webhook verified successfully")
            return challenge
        
        logger.warning(f"Webhook verification failed. Mode: {mode}, Token: {token}")
        return None


# Singleton instance
whatsapp_client = WhatsAppCloudAPI()
