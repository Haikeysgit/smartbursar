
import sys
import os
from pathlib import Path
from decimal import Decimal
from datetime import date, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.student import Student
from models.school import School
from services.scheduler.reminder_engine import generate_reminder_message

def test_ai_generation():
    print("Testing AI Message Generation...")
    
    # Mock School
    # Mock School
    school = School(
        school_code="SBA",
        school_name="SmartBursar Academy", # Verified field name is school_name
        address="123 Education Street",
        phone="08012345678",
        bank_name="GTBank",
        account_number="0123456789",
        account_name="SmartBursar Academy"
    ) 
    
    # Mock Student (Overdue)
    student = Student(
        full_name="John Doe",
        parent_name="Mr. Doe",
        fees_total_due=Decimal("150000.00"),
        amount_paid=Decimal("50000.00"),
        due_date=date.today() - timedelta(days=5),
        class_level="JSS 1"
    )
    
    # Test 1: Polite (5 days overdue)
    print("\n--- Test 1: Polite (5 days overdue) ---")
    msg = generate_reminder_message(student, school, is_exam_mode=False)
    print(f"Generated:\n{msg}")
    
    # Test 2: Urgent (Exam Mode)
    print("\n--- Test 2: Urgent (Exam Mode) ---")
    msg_urgent = generate_reminder_message(student, school, is_exam_mode=True)
    print(f"Generated:\n{msg_urgent}")

if __name__ == "__main__":
    test_ai_generation()
