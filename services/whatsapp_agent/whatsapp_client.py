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
    
    def send_template(self, to: str, template_name: str, language_code: str = "en_US") -> Dict[str, Any]:
        """
        Send a template message (bypasses 24h window).
        """
        # Validation
        if not self.token or not self.phone_number_id:
            return {"success": False, "error": "WhatsApp Credentials Missing"}

        to_clean = to.replace("+", "").replace(" ", "").replace("-", "")
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_clean,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language_code
                }
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            return {"success": True, "data": response.json()}
        except Exception as e:
            logger.error(f"Failed to send template: {e}")
            return {"success": False, "error": str(e)}

    def send_text(self, to: str, message: str) -> Dict[str, Any]:
        """
        Send a text message.
        Falls back to 'hello_world' template if 24h window is closed.
        """
        # Validation: Check for credentials
        if not self.token or not self.phone_number_id:
            return {
                "success": False, 
                "error": "WhatsApp Credentials Missing", 
                "detail": "Set WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID in Render Environment Variables."
            }

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
            # Check for 24h window error (Code 131047)
            error_detail = {}
            try:
                error_detail = e.response.json()
            except:
                pass
            
            # If 24h window closed, try fallback template
            if error_detail.get("error", {}).get("code") == 131047:
                logger.warning(f"24h Window Closed for {to_clean}. Attempting fallback template.")
                return self.send_template(to_clean, "hello_world")

            logger.error(f"WhatsApp API Error: {error_detail}")
            return {"success": False, "error": str(e), "detail": error_detail}
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send WhatsApp message: {e}")
            return {"success": False, "error": str(e)}
    
    def send_image(self, to: str, image_url: str, caption: str = "") -> Dict[str, Any]:
        """
        Send an image message.
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

    def send_interactive_message(self, to: str, body_text: str, buttons: list) -> Dict[str, Any]:
        """
        Send an interactive button message.
        
        Args:
            to: Recipient phone number
            body_text: Main message text
            buttons: List of dicts, e.g. [{"id": "btn1", "title": "Yes"}, ...]
                     (Max 3 buttons)
        """
        to_clean = to.replace("+", "").replace(" ", "").replace("-", "")
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
        
        # Format buttons for API
        formatted_buttons = []
        for btn in buttons[:3]: # Limit to 3
            formatted_buttons.append({
                "type": "reply",
                "reply": {
                    "id": btn.get("id"),
                    "title": btn.get("title")
                }
            })
            
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_clean,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": body_text
                },
                "action": {
                    "buttons": formatted_buttons
                }
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            return {"success": True, "data": response.json()}
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send interactive message: {e}")
            # Fallback to text if interactive fails (e.g. 24h window issues)
            fallback_text = body_text + "\n\n" + "\n".join([f"- {b['title']}" for b in buttons])
            return self.send_text(to, fallback_text)
    
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

    # =========================================================================
    # Business Profile Management
    # =========================================================================

    def update_business_profile(self, websites: list = None, email: str = None, description: str = None, address: str = None, vertical: str = None) -> Dict[str, Any]:
        """
        Update WhatsApp Business Profile.
        
        Args:
            websites: List of websites (max 2). Pass [] to clear.
            email: Business email contact.
            description: Business description (max 256 chars).
            address: Business address.
            vertical: Industry vertical (e.g., "EDU", "FINANCE").
            
        Returns:
            API response dict
        """
        url = f"{self.BASE_URL}/{self.phone_number_id}/whatsapp_business_profile"
        
        payload = {"messaging_product": "whatsapp"}
        
        # Only include fields that are not None
        if websites is not None:
            payload["websites"] = websites
        if email is not None:
            payload["email"] = email
        if description is not None:
            payload["description"] = description
        if address is not None:
            payload["address"] = address
        if vertical is not None:
            payload["vertical"] = vertical
            
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            logger.info("Business profile updated successfully")
            return {"success": True, "data": response.json()}
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to update business profile: {e}")
            try:
                error_detail = e.response.json()
                logger.error(f"Error detail: {error_detail}")
                return {"success": False, "error": str(e), "detail": error_detail}
            except:
                return {"success": False, "error": str(e)}


# Singleton instance
whatsapp_client = WhatsAppCloudAPI()
