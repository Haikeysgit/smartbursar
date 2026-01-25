"""
Simulate WhatsApp Webhooks for local testing.
Sends POST requests to localhost:8000/webhook
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000/webhook"
ADMIN_URL = "http://localhost:8000/admin/trigger-test"

# Parent from seed_test_parent.py
VALID_PARENT_PHONE = "2348038004334"
UNKNOWN_PHONE = "2349999999999"

def send_webhook(phone, message_type, content):
    """Send a mocked webhook payload."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "15555555555",
                        "phone_number_id": "PHONE_NUMBER_ID"
                    },
                    "contacts": [{
                        "profile": {
                            "name": "Test User"
                        },
                        "wa_id": phone
                    }],
                    "messages": [{
                        "from": phone,
                        "id": f"wamid.HBgM{int(time.time())}",
                        "timestamp": str(int(time.time())),
                        "type": message_type,
                    }]
                },
                "field": "messages"
            }]
        }]
    }

    # Add content based on type
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    if message_type == "text":
        message["text"] = {"body": content}
    elif message_type == "image":
        message["image"] = {
            "mime_type": "image/jpeg",
            "sha": "IMAGE_SHA",
            "id": "IMAGE_ID" # This will fail download if not mocked, but tests routing
        }
    
    headers = {
        "Content-Type": "application/json",
        # "X-Hub-Signature-256": "sha256=..." # Skipped in dev usually
    }

    try:
        response = requests.post(BASE_URL, json=payload, headers=headers)
        print(f"Sent [{message_type}]: {content if message_type=='text' else 'MEDIA'} -> {response.status_code}")
        return response
    except Exception as e:
        print(f"Error sending webhook: {e}")
        return None

def test_flows():
    print("--- 1. Testing UNKNOWN USER ---")
    send_webhook(UNKNOWN_PHONE, "text", "Hello")
    time.sleep(1)

    print("\n--- 2. Testing VALID PARENT: 'Hello' (Greeting) ---")
    send_webhook(VALID_PARENT_PHONE, "text", "Hello")
    time.sleep(1)

    print("\n--- 3. Testing VALID PARENT: 'Pay' (Intent) ---")
    send_webhook(VALID_PARENT_PHONE, "text", "I want to pay school fees")
    time.sleep(1)

    print("\n--- 4. Testing VALID PARENT: 'Status' (Intent) ---")
    send_webhook(VALID_PARENT_PHONE, "text", "What is my outcome balance status?")
    time.sleep(1)

    print("\n--- 5. Testing ADMIN GOD MODE ---")
    try:
        res = requests.post(f"{ADMIN_URL}?phone=+{VALID_PARENT_PHONE}&tone=term_start")
        print(f"Admin Trigger: {res.status_code} - {res.json()}")
    except Exception as e:
        print(f"Admin Trigger Failed: {e}")

if __name__ == "__main__":
    try:
        # Check if server is running first
        requests.get("http://localhost:8000/health")
        test_flows()
    except requests.exceptions.ConnectionError:
        print("❌ Server is not running. Please start the server first.")
