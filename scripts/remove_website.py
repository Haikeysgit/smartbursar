"""
Script to remove the website from the WhatsApp Business Profile.
"""
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.whatsapp_agent.whatsapp_client import whatsapp_client

def remove_website():
    print("Updating WhatsApp Business Profile...")
    # Passing empty list clears the websites
    result = whatsapp_client.update_business_profile(websites=[])
    
    if result["success"]:
        print("✅ Website removed successfully!")
    else:
        print(f"❌ Failed to remove website: {result}")

if __name__ == "__main__":
    remove_website()
