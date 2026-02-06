"""
Data Patch: Update Newmans School account_name
Run with: python scripts/patch_newmans_school.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.database import get_db_context
from models.school import School


def patch_newmans_school():
    with get_db_context() as db:
        school = db.query(School).filter(
            School.school_name.ilike("%newmans%")
        ).first()
        
        if not school:
            print("ERROR: Newmans School not found!")
            return False
        
        old_value = school.account_name
        new_value = "IMISIOLUWA FAITH OBASEKI"
        
        print(f"Found: {school.school_name} (ID: {school.id})")
        print(f"Old account_name: '{old_value}'")
        print(f"New account_name: '{new_value}'")
        
        school.account_name = new_value
        db.commit()
        
        print("\n✅ SUCCESS: account_name updated!")
        return True


if __name__ == "__main__":
    patch_newmans_school()
