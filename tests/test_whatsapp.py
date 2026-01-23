"""
=============================================================================
SmartBursar - WhatsApp Test Script
=============================================================================
Run this to test WhatsApp messaging.

INSTRUCTIONS:
1. Make sure you are logged into WhatsApp Web in your browser
2. Run: python tests/test_whatsapp.py
3. A browser window will open
4. The message will be sent to the number you specify
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_whatsapp():
    print("=" * 60)
    print("SmartBursar - WhatsApp Test")
    print("=" * 60)
    
    # Get the phone number from user
    phone = input("\nEnter YOUR phone number (e.g., +2348012345678): ").strip()
    
    if not phone:
        print("No phone number entered. Exiting.")
        return
    
    # Clean up the number
    if not phone.startswith("+"):
        if phone.startswith("0"):
            phone = "+234" + phone[1:]
        else:
            phone = "+" + phone
    
    print(f"\nWill send test message to: {phone}")
    print("\n⚠️  IMPORTANT:")
    print("   1. A browser window will open")
    print("   2. If not logged into WhatsApp Web, log in first")
    print("   3. The message will be sent automatically")
    print("   4. Keep the browser open until the message sends")
    
    confirm = input("\nPress ENTER to send, or 'q' to quit: ")
    if confirm.lower() == 'q':
        print("Cancelled.")
        return
    
    try:
        import pywhatkit
        
        message = (
            "🧪 *SmartBursar Test Message*\n\n"
            "If you see this, WhatsApp integration is working!\n\n"
            "This is an automated test from your fee collection system."
        )
        
        print("\n📱 Opening WhatsApp Web...")
        print("   (This may take 15-20 seconds)")
        
        pywhatkit.sendwhatmsg_instantly(
            phone_no=phone,
            message=message,
            wait_time=20,  # Wait 20 seconds for WhatsApp to load
            tab_close=True,
            close_time=5,
        )
        
        print("\n✅ Message sent successfully!")
        print("   Check your WhatsApp to confirm.")
        
    except ImportError:
        print("\n❌ Error: pywhatkit not installed")
        print("   Run: pip install pywhatkit")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("   1. Make sure Chrome is installed")
        print("   2. Make sure you're logged into WhatsApp Web")
        print("   3. Check your internet connection")


if __name__ == "__main__":
    test_whatsapp()
