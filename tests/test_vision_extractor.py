"""
=============================================================================
SmartBursar - Vision Extractor Test
=============================================================================
Tests the Groq Vision extractor against sample receipt images.

Usage:
    cd "c:\\Users\\user\\Documents\\school automation"
    python -m tests.test_vision_extractor
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from services.ocr.groq_vision_extractor import GroqVisionExtractor

# Receipt files to test (skip 470 — it's an admin WhatsApp message, not a receipt)
RECEIPTS_DIR = project_root / "receipts"
TEST_FILES = [
    ("Screenshot (469).png", "OPay", "FAROUK AYODEJI OBAYANJU", "IMISIOLUWA FAITH OBASEKI"),
    ("Screenshot (471).png", "Spenda", "Farouk Obayanju", "IMISIOLUWA FAITH OBASEKI"),
    ("Screenshot (473).png", "Access Bank", "JOSH2FUNNY ENTERTAINMENTS", "JOHN CHIBUEZE ANIOBODO"),
    ("Screenshot (474).png", "UBA", "HAZZAN ABIODUN ABDULATEEF", None),
]


def test_all_receipts():
    extractor = GroqVisionExtractor()
    
    if not extractor.api_key:
        print("❌ GROQ_API_KEY not set. Cannot run tests.")
        return
    
    print("=" * 70)
    print("GROQ VISION EXTRACTOR TEST")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    for filename, bank, expected_sender, expected_beneficiary in TEST_FILES:
        filepath = str(RECEIPTS_DIR / filename)
        
        if not os.path.exists(filepath):
            print(f"\n⚠️ SKIP: {filename} not found")
            continue
        
        print(f"\n{'-' * 70}")
        print(f"Testing: {filename} ({bank})")
        print(f"   Expected Sender:      {expected_sender}")
        print(f"   Expected Beneficiary: {expected_beneficiary}")
        print(f"{'-' * 70}")
        
        result = extractor.extract_from_file(filepath)
        
        if result.get("error"):
            print(f"   ❌ ERROR: {result.get('reason', 'Unknown')}")
            failed += 1
            continue
        
        actual_sender = result.get("sender_name", "None")
        actual_beneficiary = result.get("beneficiary_name", "None")
        actual_amount = result.get("amount", "None")
        actual_bank = result.get("bank_name", "None")
        actual_date = result.get("date", "None")
        actual_ref = result.get("reference", "None")
        
        print(f"   📊 RESULTS:")
        print(f"   Sender:      {actual_sender}")
        print(f"   Beneficiary: {actual_beneficiary}")
        print(f"   Amount:      {actual_amount}")
        print(f"   Bank:        {actual_bank}")
        print(f"   Date:        {actual_date}")
        print(f"   Reference:   {actual_ref}")
        
        # Check if sender matches (case-insensitive fuzzy match)
        sender_match = False
        if actual_sender and expected_sender:
            # Check if key parts of the name match
            expected_parts = expected_sender.lower().split()
            actual_lower = str(actual_sender).lower()
            sender_match = any(part in actual_lower for part in expected_parts[:2])
        
        beneficiary_match = True  # Default pass if no expected value
        if expected_beneficiary:
            if actual_beneficiary:
                expected_parts = expected_beneficiary.lower().split()
                actual_lower = str(actual_beneficiary).lower()
                beneficiary_match = any(part in actual_lower for part in expected_parts[:2])
            else:
                beneficiary_match = False
        
        if sender_match and beneficiary_match:
            print(f"   ✅ PASS")
            passed += 1
        else:
            if not sender_match:
                print(f"   ❌ FAIL: Sender mismatch")
            if not beneficiary_match:
                print(f"   ❌ FAIL: Beneficiary mismatch")
            failed += 1
    
    print(f"\n{'=' * 70}")
    print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    test_all_receipts()
