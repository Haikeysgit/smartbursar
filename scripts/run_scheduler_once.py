"""
=============================================================================
PROJECT ATLAS - Run Scheduler Once
=============================================================================
Manually trigger one cycle of the reminder scheduler.

Useful for:
    - Testing the scheduler logic
    - Running ad-hoc reminder cycles
    - Debugging message generation

Usage:
    python scripts/run_scheduler_once.py
"""

# Add parent directory to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.database import get_db_context
from services.scheduler.reminder_engine import run_reminder_cycle


def main():
    """Run one scheduler cycle."""
    
    print("="*60)
    print("PROJECT ATLAS - Manual Scheduler Run")
    print("="*60)
    print("\nStarting reminder cycle...\n")
    
    with get_db_context() as db:
        stats = run_reminder_cycle(db)
    
    print("\n" + "="*60)
    print("CYCLE COMPLETE")
    print("="*60)
    print(f"\nStats:")
    print(f"  Schools processed: {stats['schools_processed']}")
    print(f"  Students checked: {stats['students_checked']}")
    print(f"  Reminders sent: {stats['reminders_sent']}")
    print(f"  Errors: {stats['errors']}")
    print(f"  Skipped (rate limit): {stats['skipped_rate_limit']}")
    print("\n" + "="*60)


if __name__ == "__main__":
    main()
