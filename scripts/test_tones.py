"""
Script to manually trigger payment reminders in all 3 tones.
Run this locally or via Railway to test AI generation.
"""
import sys
import os
import asyncio

# Ensure project root is in path
sys.path.append(os.getcwd())

from services.llm.gemini_client import gemini_client
from services.whatsapp_agent.whatsapp_client import whatsapp_client
from config.database import get_db_context
from models.student import Student

# MOCK DATA (Since we want to verify the AI, not the DB query right now)
MOCK_CONTEXT = {
    "student_name": "David",
    "school_name": "Excel College",
    "amount_due": "N150,000",
    "due_date": "Jan 30th, 2026",
    "days_overdue": 5
}

async def send_test_reminders():
    # 1. Get User Phone
    # We will try to find a student in DB to get a real phone number, 
    # OR you can hardcode your number for the test.
    target_phone = "2349163031534" # Extracted from your screenshot
    
    print(f"🚀 Sending 3 Test Reminders to {target_phone}...")
    
    tones = ["polite", "firm", "urgent"]
    
    for tone in tones:
        print(f"\n--- Generating {tone.upper()} Reminder ---")
        message = gemini_client.generate_message(MOCK_CONTEXT, tone=tone)
        
        if message:
            print(f"Generated: {message}")
            whatsapp_client.send_text(target_phone, f"*[TEST: {tone.upper()}]*\n{message}")
            print("✅ Sent.")
        else:
            print("❌ AI Generation Failed.")
        
        await asyncio.sleep(2) # Brief pause

if __name__ == "__main__":
    asyncio.run(send_test_reminders())
