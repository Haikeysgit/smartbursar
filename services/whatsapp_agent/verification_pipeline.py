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

from sqlalchemy.orm import Session

from config.database import get_db_context
from models.school import School
from models.student import Student
from models.transaction import Transaction, TransactionStatus, PaymentMethod
from config.settings import generate_receipt_number

from .whatsapp_client import whatsapp_client
from .file_handler import file_handler
from .receipt_extractor import receipt_extractor
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
        school_id: int,
        student_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process a receipt submitted by a parent.
        
        Args:
            parent_phone: Parent's WhatsApp number
            file_content: Raw file bytes
            filename: Original filename
            school_id: School ID
            student_id: Optional student ID (if known)
        
        Returns:
            Processing result dict
        """
        import hashlib
        
        # Step 0: Check for duplicate receipt (SECURITY)
        file_hash = hashlib.sha256(file_content).hexdigest()
        
        with get_db_context() as db:
            existing = db.query(Transaction).filter(
                Transaction.receipt_hash == file_hash
            ).first()
            
            if existing:
                whatsapp_client.send_text(
                    parent_phone,
                    f"⚠️ This receipt has already been submitted.\n\n"
                    f"Receipt #: {existing.receipt_number}\n"
                    f"Status: {existing.status}\n\n"
                    "Please contact the school if you believe this is an error."
                )
                return {"success": False, "error": "Duplicate receipt", "existing_receipt": existing.receipt_number}
        
        # Step 1: Send immediate "Processing" feedback
        whatsapp_client.send_text(
            parent_phone,
            "📄 Receipt received! 🧾 Analyzing payment details, please wait..."
        )
        
        # Step 2: Save file locally
        file_path = file_handler.save_file_locally(file_content, filename)
        
        # Step 3: Prepare for Gemini
        prepared = file_handler.prepare_for_gemini(file_path)
        
        if prepared.get("error"):
            whatsapp_client.send_text(
                parent_phone,
                f"❌ Sorry, I couldn't process this file: {prepared['error']}"
            )
            return {"success": False, "error": prepared["error"]}
        
        # Step 4: Extract payment details with AI
        if prepared["type"] == "file":
            extraction = receipt_extractor.extract_from_file(prepared["content"])
        else:
            extraction = receipt_extractor.extract_from_text(prepared["content"])
        
        if extraction.get("error"):
            reason = extraction.get("reason", "Unknown error")
            whatsapp_client.send_text(
                parent_phone,
                f"❌ Could not extract payment details: {reason}\n\nPlease send a clearer image of your receipt."
            )
            return {"success": False, "error": reason}
        
        # Step 5: Create PENDING transaction in database
        with get_db_context() as db:
            school = db.query(School).filter(School.id == school_id).first()
            if not school:
                return {"success": False, "error": "School not found"}
            
            # Find student if not provided (try to match by sender name)
            if not student_id:
                student = self._find_student_by_parent(
                    db, school_id, extraction.get("sender_name", "")
                )
                if student:
                    student_id = student.id
            
            if not student_id:
                # Cannot process without knowing the student
                whatsapp_client.send_text(
                    parent_phone,
                    "⚠️ Payment extracted, but we couldn't identify the student.\n"
                    "Please contact the school admin directly."
                )
                return {"success": False, "error": "Student not identified"}
            
            student = db.query(Student).filter(Student.id == student_id).first()
            
            # Create transaction
            amount = Decimal(str(extraction.get("amount", 0)))
            balance_before = student.fees_total_due - student.amount_paid
            balance_after = balance_before - amount
            
            # Generate receipt number
            payment_count = db.query(Transaction).filter(
                Transaction.student_id == student_id
            ).count() + 1
            receipt_num = generate_receipt_number(
                school.school_code,
                datetime.now().year,
                student_id,
                payment_count
            )
            
            transaction = Transaction(
                student_id=student_id,
                amount=amount,
                date=datetime.now(),
                method=PaymentMethod.BANK_TRANSFER,
                receipt_number=receipt_num,
                status=TransactionStatus.PENDING,
                notes=json.dumps(extraction),  # Store AI extraction
                proof_description=file_path,
                receipt_hash=file_hash,  # SECURITY: For duplicate detection
                balance_before=balance_before,
                balance_after=balance_after
            )
            
            db.add(transaction)
            db.commit()
            db.refresh(transaction)
            
            # Step 6: Forward to Admin
            admin_phone = self._get_admin_phone(school)
            
            if admin_phone:
                self._forward_to_admin(
                    admin_phone=admin_phone,
                    transaction=transaction,
                    extraction=extraction,
                    student=student,
                    school=school,
                    file_path=file_path
                )
                
                # Track pending verification
                self.pending_verifications[transaction.id] = {
                    "parent_phone": parent_phone,
                    "school_id": school_id,
                    "student_id": student_id,
                    "admin_phone": admin_phone,
                    "extraction": extraction,
                    "file_path": file_path
                }
                
                # Add to admin's pending list
                if admin_phone not in self.admin_pending:
                    self.admin_pending[admin_phone] = []
                self.admin_pending[admin_phone].append(transaction.id)
            
            # Notify parent
            whatsapp_client.send_text(
                parent_phone,
                f"✅ Payment of ₦{amount:,.2f} submitted for verification.\n\n"
                f"Student: {student.full_name}\n"
                f"Reference: {receipt_num}\n\n"
                "You'll receive confirmation once the admin verifies this payment."
            )
            
            return {
                "success": True,
                "transaction_id": transaction.id,
                "receipt_number": receipt_num
            }
    
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
