"""
Script to sync Super Admin credentials from .env to the database.
"""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from config.database import get_db_context
from models.user import User, create_user

def update_admin():
    email = os.getenv("SUPER_ADMIN_EMAIL")
    password = os.getenv("SUPER_ADMIN_PASSWORD")
    
    if not email or not password:
        print("❌ Missing SUPER_ADMIN_EMAIL or SUPER_ADMIN_PASSWORD in .env")
        return

    print(f"🔄 Syncing Super Admin for: {email}")
    
    with get_db_context() as db:
        user = db.query(User).filter(User.email == email).first()
        
        if user:
            print(f"✅ User found. Updating password...")
            user.set_password(password)
            user.role = "SUPER_ADMIN" # Ensure role is correct
            db.commit()
            print("✅ Password updated successfully.")
        else:
            print(f"⚠️ User not found. Creating new Super Admin...")
            # Check if there is ANY super admin to avoid duplicates if email changed
            # But requirement says "update to what is on railway". We assume this email is the one desired.
            
            try:
                new_user = create_user(
                    email=email,
                    password=password,
                    role="SUPER_ADMIN",
                    school_id=None
                )
                db.add(new_user)
                db.commit()
                print("✅ New Super Admin created.")
            except Exception as e:
                print(f"❌ Error creating user: {e}")

if __name__ == "__main__":
    update_admin()
