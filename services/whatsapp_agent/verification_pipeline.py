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
from services.ocr.ocr_space_extractor import receipt_extractor
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
            
            logger.info(f"PIPELINE: Starting OCR extraction")
            if prepared["type"] == "file":
                extraction = receipt_extractor.extract_from_file(prepared["content"])
            else:
                extraction = receipt_extractor.extract_from_text(prepared["content"])
            
            logger.info(f"PIPELINE: Extraction result: {extraction}")
                
            if extraction.get("error"):
                reason = extraction.get("reason", "Unknown error")
                logger.error(f"PIPELINE: Extraction error: {reason}")
                whatsapp_client.send_text(parent_phone, f"❌ Unreadable receipt: {reason}. Please send a clearer image.")
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
                 
            # --- LAYER 1: PERFECT MATCH (Beneficiary) ---
            # school_name vs extracted['beneficiary_name'] AND extracted['sender_name'] (sometimes sender/receiver swapped in OCR)
            # Also check school.account_name!
            
            raw_beneficiary = extraction.get("beneficiary_name") or ""
            raw_sender = extraction.get("sender_name") or ""  # Sometimes OCR swaps them
            
            extracted_beneficiary = str(raw_beneficiary).lower()
            extracted_sender = str(raw_sender).lower()
            
            school_name_key = school.school_name.lower().split()[0]
            account_name_key = school.account_name.lower() if school.account_name else ""
            
            is_perfect_match = False
            
            # Check 1: School Name in Beneficiary
            if school_name_key in extracted_beneficiary:
                is_perfect_match = True
                
            # Check 2: Account Name in Beneficiary (Robust check)
            elif account_name_key and account_name_key in extracted_beneficiary:
                is_perfect_match = True
            
            # REMOVED: Check 3 (Sender Match) - This caused outgoing transfers to verify!
            # We strictly only care if the School is the BENEFICIARY.
                
            # --- LAYER 2: CONTEXT MATCH (Amount + Parent) ---
            # Parent is already valid (Gatekeeper). Check Amount.
            extracted_amount = Decimal(str(extraction.get("amount", 0)))
            outstanding = student.fees_total_due - student.amount_paid
            
            # Allow slight variance or exact match? Exact match or matches outstanding.
            # "Does extracted_amount match student_outstanding_balance (approximate)?"
            is_context_match = False
            if abs(extracted_amount - outstanding) < 1000: # 1000 naira tolerance? Or exact?
                 is_context_match = True
            
            # --- DECISION ---
            status = TransactionStatus.PENDING # Default: Layer 3 (Manual)
            auto_approved = False
            
            if is_perfect_match:
                status = TransactionStatus.VERIFIED
                auto_approved = True
                verification_note = "Auto-Approved: Beneficiary Match"
            elif is_context_match:
                status = TransactionStatus.VERIFIED
                auto_approved = True
                verification_note = "Auto-Approved: Context Match (Amount)"
            else:
                verification_note = "Manual Review: Yellow Flag"

            # Create Transaction
            balance_before = student.fees_total_due - student.amount_paid
            
            # Update balance if auto-approved
            if auto_approved:
                student.amount_paid += extracted_amount
            
            balance_after = student.fees_total_due - student.amount_paid # Recalculate
            
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
                balance_before=balance_before,
                balance_after=balance_after
            )
            
            if auto_approved:
                transaction.verified_at = datetime.now()
                # Bot acts as verifier? Or System? Leave verified_by_id null.
            
            db.add(transaction)
            db.commit()
            
            # Step 4: Feedback
            # Step 4: Feedback
            if auto_approved:
                # Generate PDF Receipt
                try:
                    from services.payments.receipt_generator import create_receipt_from_transaction, save_receipt_to_file
                    
                    receipt_data = create_receipt_from_transaction(transaction, student, school)
                    pdf_filename = f"receipt_{receipt_num}.pdf"
                    pdf_path = RECEIPTS_DIR / pdf_filename  # Make sure RECEIPTS_DIR is imported/available
                    
                    save_receipt_to_file(receipt_data, pdf_path)
                    logger.info(f"Generated receipt PDF: {pdf_path}")
                    
                    whatsapp_client.send_text(
                        parent_phone,
                        f"✅ **Payment Verified!**\n\n"
                        f"Amount: ₦{extracted_amount:,.2f}\n"
                        f"Student: {student.full_name}\n"
                        f"New Balance: ₦{transaction.balance_after:,.2f}"
                    )
                    

                    # Construct Public URL
                    from config.settings import settings
                    app_url = settings.APP_URL.rstrip("/")
                    pdf_url = f"{app_url}/receipts/{pdf_filename}"
                    
                    whatsapp_client.send_document(
                        parent_phone,
                        pdf_url,
                        filename=pdf_filename,
                        caption=f"🧾 Receipt {receipt_num}"
                    )
                    
                except Exception as e:
                    logger.error(f"Failed to generate receipt PDF: {e}")
                    whatsapp_client.send_text(
                        parent_phone,
                        f"✅ **Payment Verified!**\n\n"
                        f"Amount: ₦{extracted_amount:,.2f}\n"
                        f"Receipt: {receipt_num}\n"
                        f"(PDF receipt generation failed, but payment is recorded)"
                    )

            else:
                # Layer 3 Feedback (Manual Review Needed)
                whatsapp_client.send_text(
                    parent_phone,
                    f"📄 **Receipt Received**\n"
                    f"Amount: ₦{extracted_amount:,.2f}\n\n"
                    f"There was a slight mismatch in the details, so I've sent this to the Bursar for manual confirmation.\n"
                    f"You'll receive your receipt once approved!"
                )
                
                # Notify Admin
                admin_phone = self._get_admin_phone(school)
                if admin_phone:
                    # Clearer Admin Message
                    whatsapp_client.send_text(
                        admin_phone,
                        f"👮‍♂️ **Admin Action Needed**\n"
                        f"Payment Verification Request\n\n"
                        f"Student: {student.full_name}\n"
                        f"Amount: ₦{extracted_amount:,.2f}\n"
                        f"Bank: {extraction.get('bank_name', 'Unknown')}\n"
                        f"Sender: {extraction.get('sender_name', 'Unknown')}\n\n"
                        f"Reply 'Confirmed' to approve or 'Fake' to reject."
                    )
                    
                    # Forward the image to admin so they can see it
                    whatsapp_client.send_document(
                        admin_phone,
                        file_path,
                        filename="receipt_proof.jpg",
                        caption="📎 Proof of Payment"
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
        Uses phone normalization to match both local (07...) and international (+234...) formats.
        """
        from utils.phone_validator import normalize_phone_for_lookup
        
        local_format, international_format = normalize_phone_for_lookup(parent_phone)
        
        # Try all possible formats
        return db.query(Student).filter(
            (Student.parent_phone_primary == local_format) |
            (Student.parent_phone_primary == international_format) |
            (Student.parent_phone_secondary == local_format) |
            (Student.parent_phone_secondary == international_format),
            Student.school_id == school_id
        ).first()



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
        Process an admin's verification reply.
        
        Args:
            admin_phone: Admin's WhatsApp number
            reply_text: Admin's reply text
        
        Returns:
            Processing result dict
        """
        # Check if this admin has pending verifications
        pending_ids = self.admin_pending.get(admin_phone, [])
        
        if not pending_ids:
            return {"success": False, "error": "No pending verifications for this admin"}
        
        # Get the most recent pending transaction
        transaction_id = pending_ids[-1]
        verification_data = self.pending_verifications.get(transaction_id)
        
        if not verification_data:
            return {"success": False, "error": "Verification data not found"}
        
        # Classify admin's intent
        intent = admin_classifier.classify(reply_text)
        
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
                # Update transaction
                transaction.status = TransactionStatus.VERIFIED
                transaction.verified_at = datetime.now()
                
                # Update student's paid amount
                student.amount_paid += transaction.amount
                
                db.commit()
                
                # Notify parent
                parent_phone = verification_data["parent_phone"]
                whatsapp_client.send_text(
                    parent_phone,
                    f"✅ *Payment Verified!*\n\n"
                    f"Amount: ₦{transaction.amount:,.2f}\n"
                    f"Receipt: {transaction.receipt_number}\n"
                    f"New Balance: ₦{(student.fees_total_due - student.amount_paid):,.2f}\n\n"
                    "Thank you for your payment!"
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
