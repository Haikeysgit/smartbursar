from services.whatsapp_agent.conversation_manager import conversation_manager
from models.student import Student
from models.school import School
from datetime import date
from decimal import Decimal

# Mock Context
mock_student = Student(
    full_name="Test Student",
    parent_name="Parent",
    parent_phone_primary="+123",
    class_level="JSS1",
    fees_total_due=Decimal("50000"),
    amount_paid=Decimal("0"),
    due_date=date(2025, 1, 1),
    school_id=1
)
mock_school = School(
    id=1, school_name="Test School", bank_name="Bank", account_number="123", account_name="School"
)
context = {
    "students": [mock_student],
    "schools": [mock_school], 
    "user_type": "EXISTING_PARENT"
}

def test(text):
    print(f"\n--- Testing '{text}' ---")
    action, reply = conversation_manager.analyze_intent(text, "+123", context, "Parent")
    print(f"Action: {action}")
    print(f"Reply: {reply[:50]}...") # truncate

if __name__ == "__main__":
    test("Status")
    test("Pay")
    test("Paul")
    test("Hello")
