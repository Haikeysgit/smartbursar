"""
=============================================================================
PROJECT ATLAS - Seed Dummy School
=============================================================================
Creates test data for development and testing.

This script creates:
    - 1 test school ("ABC Primary School")
    - 1 super admin user
    - 1 school admin user
    - 50 fake students with varied balances

Run this script to set up a local development environment.

Usage:
    python scripts/seed_dummy_school.py
"""

import random
from datetime import date, timedelta
from decimal import Decimal

# Add parent directory to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.database import init_db, get_db_context
from models.school import School
from models.user import User, create_user
from models.student import Student


# =============================================================================
# Nigerian Names for Realistic Data
# =============================================================================

NIGERIAN_FIRST_NAMES = [
    "Adaeze", "Chukwuemeka", "Oluwaseun", "Blessing", "Emmanuel",
    "Chidinma", "Tochukwu", "Ayomide", "Favour", "David",
    "Nneka", "Obinna", "Funmilayo", "Ikenna", "Amara",
    "Chinedu", "Oluwadamilola", "Grace", "Victor", "Adaobi",
    "Nnamdi", "Temitope", "Jennifer", "Samuel", "Ngozi",
    "Ifeanyi", "Titilayo", "Michael", "Chiamaka", "Daniel",
    "Uchenna", "Busayo", "Peter", "Adanna", "Joshua",
    "Somtochukwu", "Omolara", "John", "Chinaza", "Stephen",
    "Obiora", "Yetunde", "Abraham", "Chisom", "Moses",
    "Chibuzo", "Morenike", "Paul", "Adaugo", "James",
]

NIGERIAN_SURNAMES = [
    "Okonkwo", "Adeyemi", "Ibrahim", "Okafor", "Balogun",
    "Obi", "Abubakar", "Nwosu", "Oluwole", "Eze",
    "Ogundimu", "Musa", "Chukwu", "Adebayo", "Oyelaran",
    "Okoro", "Mohammed", "Nwachukwu", "Oyedepo", "Igwe",
    "Adeleke", "Suleiman", "Nnadi", "Akinyemi", "Ogbu",
]

CLASS_LEVELS = [
    "Nursery 1", "Nursery 2", "Nursery 3",
    "Primary 1", "Primary 2", "Primary 3", "Primary 4", "Primary 5", "Primary 6",
    "JSS 1", "JSS 2", "JSS 3",
    "SS 1", "SS 2", "SS 3",
]


def generate_nigerian_phone() -> str:
    """Generate a fake Nigerian phone number in E.164 format."""
    # Nigerian mobile prefixes
    prefixes = ["803", "805", "806", "807", "808", "809", "810", "811", "812", "813", "814", "815", "816", "817", "818"]
    prefix = random.choice(prefixes)
    number = "".join([str(random.randint(0, 9)) for _ in range(7)])
    return f"+234{prefix}{number}"


def generate_fee_data() -> tuple[Decimal, Decimal]:
    """
    Generate realistic fee data.
    
    Returns:
        (fees_total_due, amount_paid)
    """
    # Fee tiers based on class level
    fee_options = [
        Decimal("45000"),   # Nursery
        Decimal("55000"),   # Primary
        Decimal("65000"),   # JSS
        Decimal("75000"),   # SS
    ]
    
    fees_total = random.choice(fee_options)
    
    # Payment scenarios:
    # 40% - Haven't paid anything
    # 30% - Paid something (partial)
    # 20% - Paid exactly half
    # 10% - Fully paid
    
    roll = random.random()
    
    if roll < 0.40:
        amount_paid = Decimal("0")
    elif roll < 0.70:
        # Random partial payment
        paid_percentage = random.uniform(0.2, 0.8)
        amount_paid = (fees_total * Decimal(str(paid_percentage))).quantize(Decimal("1000"))
    elif roll < 0.90:
        amount_paid = fees_total / 2
    else:
        amount_paid = fees_total
    
    return fees_total, amount_paid


# =============================================================================
# Main Seed Function
# =============================================================================

def seed_database():
    """Create all test data."""
    
    print("="*60)
    print("PROJECT ATLAS - Database Seeder")
    print("="*60)
    
    # Initialize database tables
    print("\n[1/5] Initializing database tables...")
    init_db()
    print("      [OK] Tables created")
    
    with get_db_context() as db:
        # Check if already seeded
        existing_school = db.query(School).filter(School.school_code == "ABC").first()
        if existing_school:
            print("\n[!] Database already seeded. Skipping...")
            print(f"    School: {existing_school.school_name}")
            print(f"    Students: {len(existing_school.students)}")
            return
        
        # Create school
        print("\n[2/5] Creating test school...")
        school = School(
            school_code="ABC",
            school_name="ABC Primary & Secondary School",
            address="123 Education Lane, Ikeja, Lagos",
            phone="+2348012345678",
            country_code="NG",
            bank_name="GTBank",
            account_number="0123456789",
            account_name="ABC Primary School",
            plan_type="TERMLY",
            subscription_end_date=date.today() + timedelta(days=90),
            status="ACTIVE",
            settings_config={
                "term_start_date": "2026-01-06",
                "term_end_date": "2026-04-05",
                "exam_start_date": "2026-03-23",
                "reminder_hour": 8,
            }
        )
        db.add(school)
        db.flush()  # Get school.id
        print(f"      [OK] Created: {school.school_name}")
        
        # Create super admin
        print("\n[3/5] Creating admin users...")
        super_admin = create_user(
            email="admin@atlas.com",
            password="admin123",
            role="SUPER_ADMIN",
            school_id=None,
        )
        db.add(super_admin)
        print(f"      [OK] Super Admin: {super_admin.email} (password: admin123)")
        
        # Create school admin
        school_admin = create_user(
            email="admin@abcschool.com",
            password="school123",
            role="SCHOOL_ADMIN",
            school_id=school.id,
        )
        db.add(school_admin)
        print(f"      [OK] School Admin: {school_admin.email} (password: school123)")
        
        # Create students
        print("\n[4/5] Creating 50 test students...")
        students_created = 0
        
        for i in range(50):
            first_name = random.choice(NIGERIAN_FIRST_NAMES)
            surname = random.choice(NIGERIAN_SURNAMES)
            class_level = random.choice(CLASS_LEVELS)
            fees_total, amount_paid = generate_fee_data()
            
            student = Student(
                school_id=school.id,
                full_name=f"{first_name} {surname}",
                parent_name=f"Mr/Mrs {surname}",
                parent_phone_primary=generate_nigerian_phone(),
                parent_phone_secondary=generate_nigerian_phone() if random.random() < 0.3 else None,
                class_level=class_level,
                fees_total_due=fees_total,
                amount_paid=amount_paid,
                due_date=date(2026, 2, 28),  # End of February
                evasion_status="ENGAGED",
                engagement_score=random.randint(30, 100),
            )
            db.add(student)
            students_created += 1
        
        print(f"      [OK] Created {students_created} students")
        
        # Summary
        print("\n[5/5] Finalizing...")
        db.commit()
        
        # Calculate stats
        all_students = db.query(Student).filter(Student.school_id == school.id).all()
        owing = sum(1 for s in all_students if s.balance > 0)
        paid = sum(1 for s in all_students if s.balance <= 0)
        total_outstanding = sum(s.balance for s in all_students if s.balance > 0)
        
        print("\n" + "="*60)
        print("SEED COMPLETE!")
        print("="*60)
        print(f"\nSchool: {school.school_name}")
        print(f"Code: {school.school_code}")
        print(f"\nStudents: {len(all_students)}")
        print(f"  - Owing: {owing}")
        print(f"  - Paid: {paid}")
        print(f"  - Total Outstanding: N{total_outstanding:,.0f}")
        print(f"\nLogin Credentials:")
        print(f"  Super Admin: admin@atlas.com / admin123")
        print(f"  School Admin: admin@abcschool.com / school123")
        print("\n" + "="*60)


if __name__ == "__main__":
    seed_database()
