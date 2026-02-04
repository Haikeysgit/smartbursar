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
    # Helper
    # =========================================================================
    
    def _clean_phone_number(self, phone: str) -> str:
        """
        Normalize phone number to international format (starting with country code).
        Handles Nigerian local format (080...) -> 23480...
        """
        # Remove common separators
        cleaned = phone.replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        
        # Specific handling for Nigeria (common issue)
        if cleaned.startswith("0") and len(cleaned) == 11:
            cleaned = "234" + cleaned[1:]
            
        return cleaned

    # =========================================================================
    # Sending Messages
    # =========================================================================
    
    def send_template(self, to: str, template_name: str, template_vars: list = None, language_code: str = "en_US") -> Dict[str, Any]:
        """
        Send a template message (bypasses 24h window).
        
        Args:
            to: Recipient phone number
            template_name: Name of the approved template (e.g., 'fee_alert_v1')
            template_vars: List of variable values in order (e.g., ["₦50,000", "Daniel Okon", ...])
            language_code: Template language code (default: en_US)
        
        Returns:
            API response dict with success status
        """
        # Validation
        if not self.token or not self.phone_number_id:
            return {"success": False, "error": "WhatsApp Credentials Missing"}

        to_clean = self._clean_phone_number(to)
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
        
        # Build template object
        template_obj = {
            "name": template_name,
            "language": {
                "code": language_code
            }
        }
        
        # Add components if variables are provided
        if template_vars:
            template_obj["components"] = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(var)} for var in template_vars
                    ]
                }
            ]
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_clean,
            "type": "template",
            "template": template_obj
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            
            # 1. LOG THE RAW RESPONSE IMMEDIATELY
            print(f"META TEMPLATE RESPONSE: {response.status_code} - {response.text}", flush=True)
            
            # 2. CHECK FOR SPECIFIC ERRORS
            response_json = {}
            try:
                response_json = response.json()
            except:
                pass
                
            error_code = 0
            if "error" in response_json:
                error_code = response_json["error"].get("code", 0)
                
            if error_code == 190:
                print("ERROR: Access Token Expired.", flush=True)
                return {"success": False, "error": "Access Token Expired"}
            
            # 3. RETURN FALSE ON FAILURE
            if response.status_code != 200:
                print(f"ERROR: Template failed ({response.status_code})", flush=True)
                return {"success": False, "error": f"HTTP {response.status_code}", "detail": response.text}

            return {"success": True, "data": response_json}
        except Exception as e:
            print(f"ERROR: Template Connection Failed - {e}", flush=True)
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
        to_clean = self._clean_phone_number(to)
        
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
            
            # 1. LOG THE RAW RESPONSE IMMEDIATELY
            print(f"META RESPONSE: {response.status_code} - {response.text}", flush=True)
            
            # Check for application-level errors even if status is 200 (Meta sometimes does this)
            response_json = {}
            try:
                response_json = response.json()
            except:
                pass
                
            # 2. CHECK FOR SPECIFIC ERRORS
            error_code = 0
            if "error" in response_json:
                error_code = response_json["error"].get("code", 0)
                
            if error_code == 131047:
                print("ERROR: 24-Hour Window Closed. Switching to Template.", flush=True)
                # Fallback logic
                logger.warning(f"24h Window Closed for {to_clean}. Attempting fallback template.")
                return self.send_template(to_clean, "hello_world")
            
            if error_code == 190:
                print("ERROR: Access Token Expired.", flush=True)
                return {"success": False, "error": "Access Token Expired"}
            
            # 3. RETURN FALSE ON FAILURE
            if response.status_code != 200:
                print(f"ERROR: Non-200 Status Code ({response.status_code})", flush=True)
                return {"success": False, "error": f"HTTP {response.status_code}", "detail": response.text}
            
            # If we got here, it's a real success
            result = response.json()
            logger.info(f"Message sent to {to_clean}: {result.get('messages', [{}])[0].get('id', 'unknown')}")
            return {"success": True, "data": result}

        except requests.exceptions.RequestException as e:
            print(f"ERROR: Connection Failed - {e}", flush=True)
            logger.error(f"Failed to send WhatsApp message: {e}")
            return {"success": False, "error": str(e)}
    
    def send_image(self, to: str, image_url: str, caption: str = "") -> Dict[str, Any]:
        """
        Send an image message.
        """
        to_clean = self._clean_phone_number(to)
        
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
            
            # 1. LOG THE RAW RESPONSE IMMEDIATELY
            print(f"META IMAGE RESPONSE: {response.status_code} - {response.text}", flush=True)
            
            if response.status_code != 200:
                return {"success": False, "error": f"HTTP {response.status_code}", "detail": response.text}
                
            return {"success": True, "data": response.json()}
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Image Send Failed - {e}", flush=True)
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
