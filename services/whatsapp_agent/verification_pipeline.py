"""
=============================================================================
SmartBursar - Verification Pipeline
=============================================================================
Main orchestrator for the Human-in-the-Loop payment verification.

Workflow:
1. Parent sends receipt → Bot sends "Processing..." → AI extracts data
2. Bot creates PENDING transaction → Forwards to Admin
3. Admin replies → AI classifies intent → Database updated → Parent notified
"""

import os
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple
import pathlib

RECEIPTS_DIR = pathlib.Path(__file__).parent.parent.parent / "receipts"
RECEIPTS_DIR.mkdir(exist_ok=True)

from sqlalchemy.orm import Session

from config.database import get_db_context
from models.school import School
from models.student import Student
from models.transaction import Transaction, TransactionStatus, PaymentMethod
from config.settings import generate_receipt_number

from .whatsapp_client import whatsapp_client
from .file_handler import file_handler
from services.ocr.groq_vision_extractor import groq_vision_extractor
from services.ocr.ocr_space_extractor import receipt_extractor  # Kept for text extraction only
from .admin_classifier import admin_classifier

logger = logging.getLogger(__name__)


class VerificationPipeline:
    """
    Orchestrates the full payment verification workflow.
    
    State is tracked via pending_verifications dict (in-memory for Phase 1).
    For production, this should be stored in Redis or the database.
    """
    
    def __init__(self):
        # In-memory state for pending verifications
        # Key: transaction_id, Value: {parent_phone, school_id, student_id, ...}
        self.pending_verifications: Dict[int, Dict[str, Any]] = {}
        
        # Reverse lookup: admin_phone -> list of pending transaction_ids
        self.admin_pending: Dict[str, list] = {}
        
        # Sync with DB on startup
        self._reload_state_from_db()
        
    def _reload_state_from_db(self):
        """Restore pending state from database on restart."""
        try:
            with get_db_context() as db:
                # Find any transaction that is not completed (universal search)
                COMPLETED_STATUSES = ['VERIFIED', 'REJECTED', 'CANCELLED', 'verified', 'rejected', 'cancelled']
                pending_txns = db.query(Transaction).filter(
                    ~Transaction.status.in_(COMPLETED_STATUSES)
                ).all()
                
                count = 0
                for txn in pending_txns:
                    # Get school phone (admin)
                    school = db.query(School).get(txn.school_id)
                    if not school:
                        continue
                        
                    admin_phone = school.phone
                    if not admin_phone.startswith("+"):
                        admin_phone = f"+{admin_phone}"
                    
                    # Reconstruct metadata (as best as possible)
                    student = db.query(Student).get(txn.student_id)
                    student_name = student.full_name if student else "Unknown"
                    parent_phone = student.parent_phone_primary if student else "Unknown"
                    
                    # Populate caches
                    self.pending_verifications[txn.id] = {
                        "amount": float(txn.amount),
                        "student_name": student_name,
                        "parent_phone": parent_phone,
                        "school_id": txn.school_id,
                        "receipt_url": txn.receipt_url,
                        "notes": txn.notes or ""
                    }
                    
                    if admin_phone not in self.admin_pending:
                        self.admin_pending[admin_phone] = []
                    
                    self.admin_pending[admin_phone].append(txn.id)
                    count += 1
                
                logger.info(f"PIPELINE: Reloaded {count} pending verifications from DB")
        except Exception as e:
            logger.error(f"PIPELINE: Failed to reload state from DB: {e}")
    
    # =========================================================================
    # Parent Flow: Receipt Submission
    # =========================================================================
    
    def process_parent_receipt(
        self,
        parent_phone: str,
        file_content: bytes,
        filename: str,
        school_id: int
    ) -> Dict[str, Any]:
        """
        Process a receipt using 3-Layer Verification Logic.
        """
        import hashlib
        
        try:
            logger.info(f"PIPELINE: Starting receipt processing for {parent_phone}")
            logger.info(f"PIPELINE: Filename={filename}, school_id={school_id}, content_size={len(file_content)}")
            
            # Step 0: Check for duplicate receipt
            file_hash = hashlib.sha256(file_content).hexdigest()
            logger.info(f"PIPELINE: File hash computed")
            
            with get_db_context() as db:
                existing = db.query(Transaction).filter(
                    Transaction.receipt_hash == file_hash
                ).first()
                
                if existing:
                    whatsapp_client.send_text(
                        parent_phone,
                        f"⚠️ Duplicate Receipt detected.\nRef: {existing.receipt_number}\nStatus: {existing.status}"
                    )
                    return {"success": False, "error": "Duplicate receipt"}
            
            # Step 1: Send Processing Feedback
            logger.info(f"PIPELINE: Sending 'Analyzing' message")
            whatsapp_client.send_text(parent_phone, "📄 Receipt received! Analyzing...")
            
            # Step 2: Save and Extract
            logger.info(f"PIPELINE: Saving file locally")
            file_path = file_handler.save_file_locally(file_content, filename)
            logger.info(f"PIPELINE: File saved to {file_path}")
            
            logger.info(f"PIPELINE: Preparing file for processing")
            prepared = file_handler.prepare_for_gemini(file_path)
            logger.info(f"PIPELINE: Prepared result type={prepared.get('type')}, error={prepared.get('error')}")
            
            if prepared.get("error"):
                logger.error(f"PIPELINE: Prepare error: {prepared['error']}")
                whatsapp_client.send_text(parent_phone, f"❌ File error: {prepared['error']}")
                return {"success": False, "error": prepared["error"]}
            
            logger.info(f"PIPELINE: Starting receipt extraction")
            
            # =============================================================
            # VISION-FIRST EXTRACTION
            # Primary: Groq Vision (sees the image directly)
            # Fallback: "Please resend" (NOT OCR — OCR caused name swaps)
            # =============================================================
            import asyncio
            
            if prepared["type"] == "file":
                # Send image directly to Groq Vision
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    extraction = loop.run_until_complete(
                        groq_vision_extractor.extract_from_file_async(prepared["content"])
                    )
                    loop.close()
                except Exception as async_err:
                    logger.error(f"ASYNC vision extraction failed: {async_err}")
                    # Fallback to sync if async fails
                    extraction = groq_vision_extractor.extract_from_file(prepared["content"])
            else:
                # Text-only content (e.g., DOCX) — use old text parser
                extraction = receipt_extractor.extract_from_text(prepared["content"])
            
            logger.info(f"PIPELINE: Extraction result: {extraction}")
                
            if extraction.get("error"):
                reason = extraction.get("reason", "Unknown error")
                user_msg = extraction.get("user_message", "")
                logger.error(f"PIPELINE: Extraction error: {reason}")
                
                if reason == "rate_limited" and user_msg:
                    # Rate limited — ask parent to resend later
                    whatsapp_client.send_text(parent_phone, user_msg)
                else:
                    whatsapp_client.send_text(
                        parent_phone, 
                        "❌ Could not read this receipt. Please resend a clearer image."
                    )
                return {"success": False, "error": reason}
            
            logger.info(f"PIPELINE: Extraction successful, proceeding to verification")
            
        except Exception as e:
            logger.error(f"PIPELINE CRASH: {e}")
            import traceback
            logger.error(traceback.format_exc())
            whatsapp_client.send_text(parent_phone, "❌ An error occurred processing your receipt. Please try again.")
            return {"success": False, "error": str(e)}

        # Step 3: 3-LAYER VERIFICATION LOGIC
        with get_db_context() as db:
            school = db.query(School).get(school_id)
            if not school:
                return {"success": False, "error": "School not found"}
            
            # Identify Student (Required)
            # Try to match student by Parent Name (Sender) or extraction regex?
            # For this Phase, we rely on Parent Phone -> Student Link in Gatekeeper.
            # But here we need to know WHICH student if they have multiple.
            # Strategy: If parent has 1 student, use it. If multiple, check if extraction has student name?
            # For simplicity: Use first student linked to this parent & school.
            
            # Re-query students for this parent+school
            student = self._find_student_by_parent_and_school(db, parent_phone, school_id)
            
            if not student:
                 whatsapp_client.send_text(parent_phone, "⚠️ Error: Student record not found.")
                 return {"success": False}
                 
            # --- SAFETY NET: Auto-correct sender/beneficiary swap ---
            # OCR sometimes labels Sender as Beneficiary (and vice versa)
            raw_beneficiary = extraction.get("beneficiary_name") or ""
            raw_sender = extraction.get("sender_name") or ""
            
            school_name_key = school.school_name.lower().split()[0]
            account_name_key = school.account_name.lower() if school.account_name else ""
            
            # Build list of ALL valid identifiers for this school
            valid_school_identifiers = set()
            # Add full school name (lowercase)
            valid_school_identifiers.add(school.school_name.lower().strip())
            # Add each word of school name (min 3 chars to avoid "the", "of", etc.)
            for word in school.school_name.lower().split():
                if len(word) >= 3:
                    valid_school_identifiers.add(word)
            # Add full account name if exists
            if school.account_name:
                valid_school_identifiers.add(school.account_name.lower().strip())
                # Add each word of account name
                for word in school.account_name.lower().split():
                    if len(word) >= 3:
                        valid_school_identifiers.add(word)
            
            logger.info(f"Valid School Identifiers: {valid_school_identifiers}")
            
            # Helper to check if text contains school identifier
            def has_school_identifier(text):
                text_lower = str(text).lower()
                for identifier in valid_school_identifiers:
                    if identifier in text_lower:
                        return True
                return False
            
            # --- POTENTIAL NAME SWAP DETECTION ---
            # OCR sometimes mislabels sender/beneficiary on OPay receipts.
            # Instead of auto-blocking, log a warning and forward to admin for manual review.
            sender_has_school = has_school_identifier(raw_sender)
            
            if sender_has_school:
                # DISABLED AUTO-BLOCK: Forward to admin for manual confirmation
                logger.warning(f"⚠️ POTENTIAL NAME SWAP: Sender '{raw_sender}' matches school identifiers. Forwarding to Admin for Manual Confirmation.")
                # Continue processing - admin will review and decide
            
            # ============================================================
            # SMART AUTO-VERIFICATION (Phase 2)
            # ============================================================
            # Clean receipts are auto-approved. Sketchy ones go to admin.
            # ============================================================
            
            extracted_amount = Decimal(str(extraction.get("amount", 0)))
            extracted_ref = extraction.get("reference") or None
            extracted_date_str = extraction.get("date") or None
            
            # ---- Confidence Checks ----
            flags = []  # Reasons to escalate to admin
            
            # Check 1: Beneficiary matches school name or account name
            beneficiary_has_school = has_school_identifier(raw_beneficiary)
            if not beneficiary_has_school:
                flags.append(f"⚠️ Beneficiary '{raw_beneficiary}' does not match school name")
                logger.warning(f"CONFIDENCE: Beneficiary mismatch — '{raw_beneficiary}' vs school identifiers")
            
            # Check 2: Sender name matches school (possible swap — always flag)
            if sender_has_school:
                flags.append(f"🔄 Sender '{raw_sender}' matches school name — possible swap")
            
            # Check 3: Date recency (within 7 days)
            if extracted_date_str:
                try:
                    from dateutil import parser as date_parser
                    receipt_date = date_parser.parse(extracted_date_str, dayfirst=True)
                    days_old = (datetime.now() - receipt_date).days
                    if days_old > 7:
                        flags.append(f"📅 Receipt is {days_old} days old (limit: 7 days)")
                        logger.warning(f"CONFIDENCE: Receipt date too old — {days_old} days")
                    elif days_old < 0:
                        flags.append(f"📅 Receipt date is in the future")
                except Exception as date_err:
                    logger.warning(f"CONFIDENCE: Could not parse date '{extracted_date_str}': {date_err}")
                    # Don't flag — unparseable date is not necessarily sketchy
            
            # Check 4: Duplicate reference check
            if extracted_ref:
                existing_txn = db.query(Transaction).filter(
                    Transaction.receipt_reference == extracted_ref
                ).first()
                
                if existing_txn:
                    # Check if it's the same parent or different
                    existing_student = existing_txn.student
                    if existing_student and existing_student.id == student.id:
                        # Same student, duplicate receipt — REJECT immediately
                        logger.warning(f"DUPLICATE: Reference '{extracted_ref}' already exists for student {student.full_name}")
                        whatsapp_client.send_text(
                            parent_phone,
                            f"⚠️ Duplicate Receipt Detected\n\n"
                            f"This receipt (Ref: {extracted_ref}) has already been submitted.\n"
                            f"If you believe this is an error, please contact the school office."
                        )
                        return {"success": False, "error": "Duplicate receipt"}
                    else:
                        # Different student — suspicious reuse
                        flags.append(f"🚨 Reference '{extracted_ref}' already used by another parent — Suspicious Reuse")
                        logger.warning(f"SUSPICIOUS: Reference '{extracted_ref}' reused by different parent")
            
            # Check 5: Amount sanity
            if extracted_amount <= 0:
                flags.append("💰 Amount is zero or negative")
            elif extracted_amount > Decimal("1000000"):
                flags.append(f"💰 Amount ₦{extracted_amount:,.2f} exceeds auto-approve limit (₦1,000,000)")
            
            # ---- DECISION: Auto-approve or escalate ----
            auto_approved = len(flags) == 0
            # Always create as PENDING — process_successful_payment handles VERIFIED transition
            status = TransactionStatus.PENDING
            
            logger.info(f"CONFIDENCE: {'AUTO-APPROVE ✅' if auto_approved else f'ESCALATE ❌ ({len(flags)} flags)'}")
            for flag in flags:
                logger.info(f"  FLAG: {flag}")
            
            # Build verification note
            if auto_approved:
                verification_note = (
                    f"✅ AUTO-VERIFIED\n"
                    f"Sender: {raw_sender or 'Unknown'}\n"
                    f"Recipient: {raw_beneficiary or 'Unknown'}"
                )
            else:
                verification_note = (
                    f"📋 MANUAL REVIEW REQUIRED\n"
                    f"Sender: {raw_sender or 'Unknown'}\n"
                    f"Recipient: {raw_beneficiary or 'Unknown'}\n"
                    f"Flags: {'; '.join(flags)}"
                )

            # Create Transaction
            balance_before = student.fees_total_due - student.amount_paid
            
            # Generate Receipt Number
            payment_count = db.query(Transaction).filter(Transaction.student_id == student.id).count() + 1
            receipt_num = generate_receipt_number(school.school_code, datetime.now().year, student.id, payment_count)
            
            transaction = Transaction(
                student_id=student.id,
                amount=extracted_amount,
                date=datetime.now(),
                method=PaymentMethod.BANK_TRANSFER,
                receipt_number=receipt_num,
                status=status,
                notes=json.dumps(extraction),
                proof_description=verification_note,
                receipt_hash=file_hash,
                receipt_reference=extracted_ref,
                balance_before=balance_before,
                balance_after=balance_before,  # Updated below if auto-approved
            )
            
            db.add(transaction)
            db.commit()
            
            # Step 4: Feedback based on decision
            if auto_approved:
                # ---- AUTO-APPROVED: Update balance, notify parent, quiet admin log ----
                from services.payments.payment_recorder import process_successful_payment
                
                process_successful_payment(
                    db,
                    transaction.id,
                    verified_by_id=None,  # System auto-verified
                    send_pdf=True
                )
                
                logger.info(f"✅ AUTO-VERIFIED: {student.full_name}, ₦{extracted_amount:,.2f}, Ref: {extracted_ref}")
                
                # Quiet admin notification (no action needed)
                admin_phone = self._get_admin_phone(school)
                if admin_phone:
                    whatsapp_client.send_text(
                        admin_phone,
                        f"✅ Auto-Verified Payment\n"
                        f"Student: {student.full_name}\n"
                        f"Amount: ₦{extracted_amount:,.2f}\n"
                        f"Sender: {raw_sender or 'Unknown'}\n"
                        f"Bank: {extraction.get('bank_name', 'Unknown')}\n"
                        f"Ref: {extracted_ref or 'N/A'}"
                    )

            else:
                # ---- ESCALATE: Send to admin for manual review ----
                whatsapp_client.send_text(
                    parent_phone,
                    f"📄 **Receipt Received**\n"
                    f"Amount: ₦{extracted_amount:,.2f}\n\n"
                    f"I've sent this to the Bursar for confirmation.\n"
                    f"You'll receive your receipt once approved!"
                )
                
                # Notify Admin with specific flags
                admin_phone = self._get_admin_phone(school)
                if admin_phone:
                    flag_text = "\n".join(flags)
                    
                    whatsapp_client.send_text(
                        admin_phone,
                        f"⚠️ **Admin Review Needed**\n"
                        f"Payment Verification Request\n\n"
                        f"Student: {student.full_name}\n"
                        f"Amount: ₦{extracted_amount:,.2f}\n"
                        f"Bank: {extraction.get('bank_name', 'Unknown')}\n"
                        f"Sender: {extraction.get('sender_name', 'Unknown')}\n"
                        f"Ref: {extracted_ref or 'N/A'}\n\n"
                        f"🔍 Flags:\n{flag_text}\n\n"
                        f"Reply 'Confirmed' to approve or 'Fake' to reject."
                    )
                    
                    # Forward the image to admin so they can see it
                    whatsapp_client.send_document(
                        admin_phone,
                        file_path,
                        filename="receipt_proof.jpg",
                        caption=f"📎 Proof of Payment"
                    )
                    
                    # Add to Pending List
                    self.pending_verifications[transaction.id] = {
                        "parent_phone": parent_phone,
                        "school_id": school_id,
                        "student_id": student.id,
                        "admin_phone": admin_phone,
                    }
                     # Add to admin's pending list
                    if admin_phone not in self.admin_pending:
                        self.admin_pending[admin_phone] = []
                    self.admin_pending[admin_phone].append(transaction.id)

            return {"success": True}
            
    def _find_student_by_parent_and_school(self, db, parent_phone, school_id):
        """
        Helper to find student by parent phone.
        Searches multiple formats: local (070...), international (+234...), clean (234...).
        """
        from utils.phone_validator import normalize_phone_for_lookup
        
        local_format, international_format = normalize_phone_for_lookup(parent_phone)
        raw_phone = parent_phone.strip()
        clean_international = raw_phone.replace("+", "").replace(" ", "").replace("-", "")  # 234... without +
        
        # DEBUG: Log all search candidates
        logger.info(f"DEBUG PHONE LOOKUP:")
        logger.info(f"  Raw: '{raw_phone}'")
        logger.info(f"  Local (070...): '{local_format}'")
        logger.info(f"  International (+234...): '{international_format}'")
        logger.info(f"  Clean International (234...): '{clean_international}'")
        logger.info(f"  School ID: {school_id}")
        
        # Attempt 1: Search with normalized formats (local + international with +)
        student = db.query(Student).filter(
            (Student.parent_phone_primary == local_format) |
            (Student.parent_phone_primary == international_format) |
            (Student.parent_phone_secondary == local_format) |
            (Student.parent_phone_secondary == international_format),
            Student.school_id == school_id
        ).first()
        
        if student:
            logger.info(f"DEBUG: FOUND '{student.full_name}' with normalized search")
            return student
        
        # Attempt 2: Clean international (234... without +) - THE KEY FIX
        logger.info(f"DEBUG: Trying clean_international: '{clean_international}'")
        student = db.query(Student).filter(
            (Student.parent_phone_primary == clean_international) |
            (Student.parent_phone_secondary == clean_international),
            Student.school_id == school_id
        ).first()
        
        if student:
            logger.info(f"DEBUG: FOUND '{student.full_name}' with clean_international search")
            return student
        
        # Attempt 3: Raw fallback
        logger.info(f"DEBUG: Trying raw: '{raw_phone}'")
        student = db.query(Student).filter(
            (Student.parent_phone_primary == raw_phone) |
            (Student.parent_phone_secondary == raw_phone),
            Student.school_id == school_id
        ).first()
        
        if student:
            logger.info(f"DEBUG: FOUND '{student.full_name}' with raw fallback")
            return student
        
        # DEBUG: Show sample students if all searches fail
        all_students = db.query(Student).filter(Student.school_id == school_id).limit(5).all()
        logger.info(f"DEBUG: No match. Sample students in school {school_id}:")
        for s in all_students:
            logger.info(f"  - {s.full_name}: primary='{s.parent_phone_primary}'")
        
        return None



    def retry_with_student_name(
        self,
        parent_phone: str,
        student_name: str,
        extraction_data: Dict[str, Any],
        file_path: str,
        school_id: int
    ) -> Dict[str, Any]:
        """
        Retry verification when parent provides student name manually.
        """
        with get_db_context() as db:
            # 1. Search for student by provided name (Fuzzy match)
            students = db.query(Student).filter(
                Student.school_id == school_id
            ).all()
            
            # Simple fuzzy matching
            target = student_name.lower()
            matched_student = None
            
            for student in students:
                full_name = student.full_name.lower()
                if target in full_name or full_name in target:
                    matched_student = student
                    break
            
            if not matched_student:
                return {"success": False, "error": "Student not found"}
            
            # 2. Proceed with transaction creation (Logic duplicated from process_parent_receipt - refactor ideal but copying for speed)
            amount = Decimal(str(extraction_data.get("amount", 0)))
            balance_before = matched_student.fees_total_due - matched_student.amount_paid
            balance_after = balance_before - amount
            
            # Generate receipt number
            payment_count = db.query(Transaction).filter(
                Transaction.student_id == matched_student.id
            ).count() + 1
            
            school = db.query(School).get(school_id)
            receipt_num = generate_receipt_number(
                school.school_code,
                datetime.now().year,
                matched_student.id,
                payment_count
            )
            
            transaction = Transaction(
                student_id=matched_student.id,
                amount=amount,
                date=datetime.now(),
                method=PaymentMethod.BANK_TRANSFER,
                receipt_number=receipt_num,
                status=TransactionStatus.PENDING,
                notes=json.dumps(extraction_data),
                proof_description=file_path,
                receipt_hash=f"RETRY_{datetime.now().timestamp()}", # Pseudo hash for retry
                balance_before=balance_before,
                balance_after=balance_after
            )
            
            db.add(transaction)
            db.commit()
            db.refresh(transaction)
            
            # 3. Forward to Admin
            admin_phone = self._get_admin_phone(school)
            if admin_phone:
                self._forward_to_admin(
                    admin_phone=admin_phone,
                    transaction=transaction,
                    extraction=extraction_data,
                    student=matched_student,
                    school=school,
                    file_path=file_path
                )
                
                # Track pending
                self.pending_verifications[transaction.id] = {
                    "parent_phone": parent_phone,
                    "school_id": school_id,
                    "student_id": matched_student.id,
                    "admin_phone": admin_phone,
                    "extraction": extraction_data,
                    "file_path": file_path
                }
                
                if admin_phone not in self.admin_pending:
                    self.admin_pending[admin_phone] = []
                self.admin_pending[admin_phone].append(transaction.id)
                
            # Notify parent
            whatsapp_client.send_text(
                parent_phone,
                f"✅ Payment of ₦{amount:,.2f} recorded for **{matched_student.full_name}**.\n\n"
                f"Reference: {receipt_num}\n"
                "Awaiting admin approval."
            )
            
            return {"success": True, "student_name": matched_student.full_name}
    
    # =========================================================================
    # Admin Flow: Verification Response
    # =========================================================================
    
    def process_admin_reply(
        self,
        admin_phone: str,
        reply_text: str
    ) -> Dict[str, Any]:
        """
        Process an admin's verification reply (STATELESS FIX).
        Instead of relying on in-memory state, we query the DB for the 
        latest PENDING transaction for this school.
        """
        with get_db_context() as db:
            # 1. Identify School(s) managed by this Admin
            # Normalize admin phone for lookup
            clean_admin = admin_phone.replace("+", "").replace(" ", "").replace("-", "")
            
            # Simple fuzzy lookup on phone or admin_whatsapp_number
            # Check primary phone
            school = db.query(School).filter(
                (School.phone.contains(clean_admin[-10:])) |
                (School.admin_whatsapp_number.contains(clean_admin[-10:]))
            ).first()
            
            if not school:
                logger.warning(f"Admin reply from {admin_phone} but no school found.")
                whatsapp_client.send_text(admin_phone, "🚫 Identity Error: I cannot find which school you manage.")
                return {"success": False, "error": "School not found"}
            
            # 2. Find OLDEST Pending Transaction (UNIVERSAL SEARCH)
            # Use order_by(asc) to ensure admins verify the oldest item first.
            # JOIN Student to filter by school_id (Transaction doesn't have school_id directly)
            # UNIVERSAL: Find ANY transaction that is NOT completed
            # Include BOTH uppercase (new) and lowercase (legacy) status values
            COMPLETED_STATUSES = [
                'VERIFIED', 'REJECTED', 'CANCELLED',  # New enum values (uppercase)
                'verified', 'rejected', 'cancelled',  # Legacy lowercase
            ]
            
            pending_txn = db.query(Transaction).join(Student).filter(
                Student.school_id == school.id,
                ~Transaction.status.in_(COMPLETED_STATUSES)  # Universal: anything NOT completed
            ).order_by(Transaction.created_at.asc()).first()
            
            if not pending_txn:
                whatsapp_client.send_text(
                    admin_phone,
                    "⚠️ You have no pending payments to verify.\n\n"
                    "If you already replied, the payment might be processed."
                )
                return {"success": False, "error": "No pending verifications"}
            
            # 3. Classify admin's intent
            intent = admin_classifier.classify(reply_text)
            logger.info(f"Admin Intent for Txn #{pending_txn.id}: {intent} (Text: {reply_text})")
            
            student = pending_txn.student if pending_txn.student else db.query(Student).get(pending_txn.student_id)
            
            # Helper to check remaining queue AND preview next transaction
            def check_remaining_queue():
                # Count remaining pending transactions
                remaining_count = db.query(Transaction).join(Student).filter(
                    Student.school_id == school.id,
                    ~Transaction.status.in_(COMPLETED_STATUSES),
                    Transaction.id != pending_txn.id
                ).count()
                
                if remaining_count == 0:
                    return "\n\n✅ You are all caught up! No pending payments."
                
                # Fetch the NEXT transaction in line (FIFO - oldest first)
                next_txn = db.query(Transaction).join(Student).filter(
                    Student.school_id == school.id,
                    ~Transaction.status.in_(COMPLETED_STATUSES),
                    Transaction.id != pending_txn.id
                ).order_by(Transaction.created_at.asc()).first()
                
                if next_txn and next_txn.student:
                    # Get sender name from notes (stored during OCR extraction)
                    sender_name = "Unknown"
                    if next_txn.notes:
                        # Try to extract sender from notes
                        for line in next_txn.notes.split("\n"):
                            if "Sender:" in line:
                                sender_name = line.replace("Sender:", "").strip()
                                break
                    
                    student_name = next_txn.student.full_name
                    amount = next_txn.amount
                    
                    return (
                        f"\n\n⚠️ **Queue Alert:** You have {remaining_count} more pending payment(s)."
                        f"\n\n👇 **Next Up:**"
                        f"\n👤 Sender: {sender_name}"
                        f"\n🎓 Student: {student_name}"
                        f"\n💰 Amount: ₦{amount:,.2f}"
                        f"\n\nReply 'Confirmed' or 'Fake' for this transaction."
                    )
                
                return f"\n\n⚠️ **Queue Alert:** You have {remaining_count} more pending payment(s).\nReply 'Confirmed' to approve the next one."

            # 4. ACTION
            if intent == "APPROVED":
                # Centralized processing (updates DB, generates PDF, sends WhatsApp)
                from services.payments.payment_recorder import process_successful_payment
                
                # Check for duplicate processing? process_successful_payment handles it?
                # It's idempotent if status is VERIFIED, but we are in pending_verification.
                
                process_successful_payment(
                    db, 
                    pending_txn.id, 
                    verified_by_id=None,
                    send_pdf=True
                )
                
                # Check queue AFTER processing (status changed to VERIFIED)
                queue_msg = check_remaining_queue()
                
                # Confirm to admin
                whatsapp_client.send_text(
                    admin_phone,
                    f"✅ Payment matches {student.full_name}!\n"
                    f"Balance Updated. Parent notified.{queue_msg}"
                )
                
                # Cleanup in-memory (optional, just to keep it clean)
                if pending_txn.id in self.pending_verifications:
                    del self.pending_verifications[pending_txn.id]
                
                return {"success": True, "status": "APPROVED"}
                
            elif intent == "REJECTED":
                # Reject logic
                from services.payments.payment_recorder import reject_payment
                
                reject_payment(db, pending_txn.id, school.id, rejected_by_id=None, reason="Admin rejected via WhatsApp")
                
                # Check queue AFTER processing
                queue_msg = check_remaining_queue()
                
                whatsapp_client.send_text(
                    admin_phone,
                    f"⛔ Payment REJECTED.\n"
                    f"Parent has been notified.{queue_msg}"
                )
                
                # Send polite rejection to parent
                whatsapp_client.send_text(
                    student.parent_phone_primary,
                    f"❌ Payment Verification Failed\n\n"
                    f"The receipt for ₦{pending_txn.amount:,.2f} was rejected.\n\n"
                    f"Please contact the school office if this is a mistake."
                )
                
                if pending_txn.id in self.pending_verifications:
                    del self.pending_verifications[pending_txn.id]
                    
                return {"success": True, "status": "REJECTED"}
                
            else:
                # Ambiguous
                whatsapp_client.send_text(
                    admin_phone,
                    "🤖 I didn't understand that.\n"
                    "Reply 'Confirmed' to approve or 'Fake' to reject."
                )
                return {"success": False, "error": "Ambiguous intent"}
        
        if intent == "UNKNOWN":
            whatsapp_client.send_text(
                admin_phone,
                "❓ I didn't understand your response.\n\n"
                "Reply 'Confirmed' to approve or 'Fake' to reject this payment."
            )
            return {"success": False, "error": "Unclear response"}
        
        # Update database with race condition protection
        with get_db_context() as db:
            # SECURITY: Use FOR UPDATE to lock row and check status
            transaction = db.query(Transaction).filter(
                Transaction.id == transaction_id,
                Transaction.status == TransactionStatus.PENDING  # Only if still pending
            ).with_for_update().first()
            
            if not transaction:
                # Already processed by another admin
                whatsapp_client.send_text(
                    admin_phone,
                    "⚠️ This payment was already processed by another admin."
                )
                return {"success": False, "error": "Already processed"}
            
            student = db.query(Student).filter(
                Student.id == transaction.student_id
            ).first()
            
            if intent == "APPROVED":
                from services.payments.payment_recorder import process_successful_payment
                
                # Centralized processing (updates DB, generates PDF, sends WhatsApp)
                process_successful_payment(
                    db, 
                    transaction.id, 
                    verified_by_id=None,
                    send_pdf=True
                )
                
                # Confirm to admin
                whatsapp_client.send_text(
                    admin_phone,
                    f"✅ Payment marked as VERIFIED.\n"
                    f"Student {student.full_name}'s balance updated."
                )
                
            else:  # REJECTED
                transaction.status = TransactionStatus.REJECTED
                db.commit()
                
                # Notify parent
                parent_phone = verification_data["parent_phone"]
                whatsapp_client.send_text(
                    parent_phone,
                    "❌ *Payment Not Verified*\n\n"
                    "The admin could not verify your payment.\n"
                    "Please contact the school directly for clarification."
                )
                
                # Confirm to admin
                whatsapp_client.send_text(
                    admin_phone,
                    "❌ Payment marked as REJECTED and flagged."
                )
            
            # Clean up pending state
            self.pending_verifications.pop(transaction_id, None)
            if transaction_id in self.admin_pending.get(admin_phone, []):
                self.admin_pending[admin_phone].remove(transaction_id)
            
            return {
                "success": True,
                "intent": intent,
                "transaction_id": transaction_id
            }
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _get_admin_phone(self, school: School) -> Optional[str]:
        """
        Get admin phone number for receipt notifications.
        
        Priority:
        1. admin_whatsapp_number column (Secretary/Admin)
        2. admin_phone in settings_config (legacy)
        3. school.phone (Owner fallback)
        """
        # Priority 1: Check admin_whatsapp_number column
        if hasattr(school, 'admin_whatsapp_number') and school.admin_whatsapp_number:
            return school.admin_whatsapp_number
        
        # Priority 2: Check settings_config (legacy)
        if school.settings_config:
            admin_phone = school.settings_config.get("admin_phone")
            if admin_phone:
                return admin_phone
        
        # Priority 3: Fallback to school owner phone
        return school.phone
    
    def _forward_to_admin(
        self,
        admin_phone: str,
        transaction: Transaction,
        extraction: Dict[str, Any],
        student: Student,
        school: School,
        file_path: str
    ):
        """Forward receipt and details to admin for verification."""
        message = (
            f"🔔 *New Payment Verification Required*\n\n"
            f"Student: {student.full_name}\n"
            f"Class: {student.class_level}\n"
            f"Amount: ₦{extraction.get('amount', 'Unknown'):,}\n"
            f"Date: {extraction.get('date', 'Unknown')}\n"
            f"Bank: {extraction.get('bank_name', 'Unknown')}\n"
            f"Sender: {extraction.get('sender_name', 'Unknown')}\n"
            f"Ref: {extraction.get('transaction_ref', 'Unknown')}\n\n"
            f"📎 Receipt attached\n\n"
            f"Reply 'Confirmed' to approve or 'Fake' to reject."
        )
        
        whatsapp_client.send_text(admin_phone, message)
        
        # TODO: Send the actual receipt image
        # This requires the file to be publicly accessible or use media upload
    
    def _find_student_by_parent(
        self,
        db: Session,
        school_id: int,
        sender_name: str
    ) -> Optional[Student]:
        """Try to find a student by parent/guardian name."""
        if not sender_name:
            return None
        
        # Simple search - look for matching parent name
        students = db.query(Student).filter(
            Student.school_id == school_id
        ).all()
        
        sender_lower = sender_name.lower()
        
        for student in students:
            if student.parent_name and sender_lower in student.parent_name.lower():
                return student
            if student.guardian_name and sender_lower in student.guardian_name.lower():
                return student
        
        return None


# Singleton instance
verification_pipeline = VerificationPipeline()
