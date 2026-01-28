from sqlalchemy.orm import Session
from models.user import User, UserRole
from models.school import School
from config.database import SessionLocal
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_admin():
    db = SessionLocal()
    print("--- Creating Super Admin User ---")
    
    email = "admin@school.com"
    password = "password123"
    
    # Check if exists
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Create Dummy School for context if needed
        school = db.query(School).first()
        
        user = User(
            email=email,
            hashed_password=pwd_context.hash(password),
            role=UserRole.SUPER_ADMIN,
            school_id=school.id if school else None,
            is_active=True
        )
        db.add(user)
        db.commit()
        print(f"✅ Created Admin User: {email}")
        print(f"🔑 Password: {password}")
    else:
        print(f"ℹ️ User {email} already exists.")
        # Optional: Reset password if it exists
        user.hashed_password = pwd_context.hash(password)
        db.commit()
        print(f"🔄 Password reset to: {password}")

    db.close()

if __name__ == "__main__":
    create_admin()
