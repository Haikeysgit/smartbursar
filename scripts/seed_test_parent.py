"""
Script to seed a test parent for immediate testing.
Ensures the parent is linked to a School with valid Bank Details.
"""
import sys
import os
from datetime import date, timedelta

# Add parent directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import get_db_context
from models.school import School
from models.student import Student

def seed_test_data():
    print("🌱 Seeding Test Data...")
    
    with get_db_context() as db:
        # 1. Ensure School Exists (with valid Bank Details)
        school = db.query(School).filter(School.school_code == "TST").first()
        
        if not school:
            print("Creating Test School...")
            school = School(
                school_code="TST",
                school_name="SmartBursar Academy",
                address="123 Innovation Drive, Lagos",
                phone="+2348000000000",
                country_code="NG",
                bank_name="GTBank",
                account_number="0123456789",
                account_name="SmartBursar Academy Ltd",
                plan_type="YEARLY",
                subscription_end_date=date.today() + timedelta(days=365),
                status="ACTIVE",
                settings_config={"admin_phone": "+2348000000000"}
            )
            db.add(school)
            db.commit()
            db.refresh(school)
        else:
            # Update bank details just in case
            school.bank_name = "GTBank"
            school.account_number = "0123456789"
            school.account_name = "SmartBursar Academy Ltd"
            db.commit()
            print("Test School updated.")

        # 2. Ensure Student/Parent Exists
        # Parent: Obaseki Imisioluwa (+2348038004334)
        target_phone = "+2348038004334"
        
        student = db.query(Student).filter(
            Student.parent_phone_primary == target_phone,
            Student.school_id == school.id
        ).first()
        
        if not student:
            print("Creating Test Student & Parent...")
            student = Student(
                school_id=school.id,
                full_name="Test Student",
                class_level="SS 3",
                parent_name="Obaseki Imisioluwa",
                parent_phone_primary=target_phone,
                fees_total_due=150000.00,
                amount_paid=100000.00, # Outstanding: 50,000
                due_date=date.today() + timedelta(days=30),
                evasion_status="ENGAGED"
            )
            db.add(student)
            db.commit()
            print(f"✅ Created parent {target_phone} linked to {student.full_name}")
        else:
            # Reset balance to known state (50k outstanding)
            student.fees_total_due = 150000.00
            student.amount_paid = 100000.00
            db.commit()
            print(f"✅ Reset parent {target_phone} balance to 50,000 outstanding")

if __name__ == "__main__":
    seed_test_data()
