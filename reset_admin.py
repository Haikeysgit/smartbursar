import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from config.database import get_db_context
from models import User

def reset_password():
    print("Connecting to database...")
    with get_db_context() as db:
        admin = db.query(User).filter(User.email == "admin@school.com").first()
        if admin:
            print(f"Found admin user: {admin.email}")
            admin.set_password("password123")
            db.commit()
            print("SUCCESS: Password reset to 'password123'")
        else:
            print("ERROR: Admin user 'admin@school.com' not found. Restart the dashboard to trigger auto-creation.")

if __name__ == "__main__":
    reset_password()
