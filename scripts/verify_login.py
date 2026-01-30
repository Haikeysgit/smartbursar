import sys
import os
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from config.database import get_db_context
from models.user import User

def verify():
    print(f"--- Verifying Credentials (Env: {os.getenv('ENVIRONMENT', 'dev')}) ---")
    
    try:
        with get_db_context() as db:
            users = db.query(User).all()
            print(f"Total Users Found: {len(users)}\n")
            
            if not users:
                print("⚠️  NO USERS FOUND! The database is empty.")
                return

            for u in users:
                print(f"👤 User: {u.email}")
                print(f"   Role: {u.role}")
                print(f"   School ID: {u.school_id}")
                
                # Test Passwords
                if u.email == "admin@abcschool.com":
                    is_valid = u.check_password("school123")
                    result = "✅ CORRECT" if is_valid else "❌ INCORRECT"
                    print(f"   > Password 'school123': {result}")
                
                elif u.email == "admin@school.com":
                    is_valid = u.check_password("password123")
                    result = "✅ CORRECT" if is_valid else "❌ INCORRECT"
                    print(f"   > Password 'password123': {result}")
                
                else:
                    print(f"   > (Custom User - Unknown Password)")
                
                print("-" * 30)

    except Exception as e:
        print(f"❌ Error connecting to database: {e}")

if __name__ == "__main__":
    verify()
