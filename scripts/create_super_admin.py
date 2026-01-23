#!/usr/bin/env python
"""
=============================================================================
SmartBursar - Create Super Admin CLI
=============================================================================
Creates the master Super Admin account for production deployment.

Usage:
    python scripts/create_super_admin.py

The script will prompt for email and password interactively.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from getpass import getpass
from config.database import get_db_context, init_db
from models.user import User, create_user


def main():
    print("\n" + "="*60)
    print("SmartBursar - Super Admin Setup")
    print("="*60 + "\n")
    
    # Initialize database if not exists
    init_db()
    
    # Get credentials
    email = input("Enter Super Admin email: ").strip().lower()
    
    if not email or "@" not in email:
        print("❌ Invalid email address")
        return
    
    password = getpass("Enter password (hidden): ")
    confirm = getpass("Confirm password: ")
    
    if password != confirm:
        print("❌ Passwords do not match")
        return
    
    if len(password) < 6:
        print("❌ Password must be at least 6 characters")
        return
    
    # Check if user already exists
    with get_db_context() as db:
        existing = db.query(User).filter(User.email == email).first()
        
        if existing:
            print(f"❌ User with email '{email}' already exists")
            return
        
        # Create Super Admin
        try:
            user = create_user(
                email=email,
                password=password,
                role="SUPER_ADMIN",
                school_id=None
            )
            db.add(user)
            db.commit()
            
            print("\n" + "="*60)
            print("✅ Super Admin created successfully!")
            print("="*60)
            print(f"\n   Email: {email}")
            print(f"   Role:  SUPER_ADMIN")
            print("\n   You can now log in at the dashboard.")
            print("="*60 + "\n")
            
        except Exception as e:
            print(f"❌ Error creating user: {e}")
            return


if __name__ == "__main__":
    main()
