"""
Seed Test Data for SmartBursar
Creates a test school and student for verification.
"""
from sqlalchemy.orm import Session
from models.school import School
from models.student import Student

def seed_data(db: Session):
    print("--- Seeding Test Data ---")
    
    # Check if school exists
    school = db.query(School).filter(School.email == "test@smartbursar.com").first()
    if not school:
        school = School(
            name="SmartBursar Academy",
            school_name="SmartBursar Academy",  # Alias
            email="test@smartbursar.com",
            phone="08012345678",
            address="123 Test St, Lagos",
            password_hash="hashed_secret",
            account_name="IMISIOLUWA FAITH OBASEKI",  # Matches the receipt beneficiary
            account_number="0247848373",
            bank_name="Wema Bank"
        )
        db.add(school)
        db.commit()
        db.refresh(school)
        print(f"Created School: {school.name}")
    else:
        print(f"School exists: {school.name}")

    # Check if student exists
    # The test number from user logs: 2348038004334
    student = db.query(Student).filter(Student.parent_phone_primary == "+2348038004334").first()
    if not student:
        student = Student(
            full_name="Test Student",
            parent_name="Test Parent",
            parent_phone_primary="+2348038004334",
            school_id=school.id,
            fees_total_due=50000.00,
            amount_paid=0.00,
            # Due date in past for strict testing
            due_date=None 
        )
        db.add(student)
        db.commit()
        print(f"Created Student: {student.full_name} ({student.parent_phone_primary})")
    else:
        print(f"Student exists: {student.full_name}")

    print("--- Seeding Complete ---")

if __name__ == "__main__":
    from config.database import SessionLocal
    db = SessionLocal()
    seed_data(db)
    db.close()
