import sys
import os
sys.path.append(os.getcwd())

from services.llm.gemini_client import gemini_client

# Manual context
context = {
    "student_name": "Test Student",
    "school_name": "Test School", 
    "amount_due": "N50,000",
    "due_date": "Tomorrow",
    "days_overdue": 5
}

def test():
    key = os.getenv('GOOGLE_API_KEY')
    if not key:
        print("❌ ERROR: GOOGLE_API_KEY is missing from environment.")
        return
        
    print(f"✅ Loaded Key: {key[:8]}...{key[-4:]} (Length: {len(key)})")
    
    try:
        import google.genai
        print(f"SDK Version: {getattr(google.genai, '__version__', 'Unknown')}")
    except:
        pass
    
    print("\n--- Sending Request (gemini-1.5-flash) ---")
    response = gemini_client.generate_message(context, tone="polite")
    
    if response:
        print(f"\n✅ SUCCESS!\nResponse: {response}")
    else:
        print("\n❌ FAILED - No response.")

if __name__ == "__main__":
    test()
