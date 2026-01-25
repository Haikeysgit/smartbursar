"""
=============================================================================
SmartBursar - Conversation Manager
=============================================================================
Manages user intent and generates contextual responses.
"""

import logging
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger(__name__)

class BotConversationManager:
    """
    Analyzes text to determine intent and generates responses based on user context.
    """
    
    def analyze_intent(self, text: str, sender_phone: str, context: Dict[str, Any], sender_name: str) -> Tuple[str, Optional[str]]:
        """
        Analyze incoming text to determine intent.
        
        Intents:
        1. WANT_TO_PAY: "Pay", "Transfer", "Account"
        2. STATUS_CHECK: "Status", "Balance", "Owing"
        3. GREETING: "Hello", "Hi", "Thanks"
        4. COMPLAINT: "Help", "Support", "Complaint"
        """
        text_lower = text.lower().strip()
        logger.info(f"Analyzing Intent: raw='{text}', processed='{text_lower}'")
        
        # 0. DEBUG / GOD MODE
        if "paul" in text_lower:
             return "DEBUG_PAUL", "I heard 'Paul'. Use 'Status' to check debt or 'Pay' for account details."
        
        # 1. WANT TO PAY
        if any(word in text_lower for word in ["pay", "transfer", "account", "bank", "send money"]):
            # Get school bank details from context
            schools = context.get("schools", [])
            if not schools:
                 return "ERROR", "I cannot find school bank details for your profile. Please contact Admin."
            
            # If multi-school, we should technically ask which one. 
            # For this MVP, we list ALL linked schools' accounts.
            
            response = "🏦 *School Account Details*\n\n"
            for school in schools:
                response += (
                    f"🏫 *{school.school_name}*\n"
                    f"Bank: {school.bank_name}\n"
                    f"Account: {school.account_number}\n"
                    f"Name: {school.account_name}\n\n"
                )
            
            response += "Please make a transfer and *send me the receipt* (Image/PDF) here to verify."
            return "SEND_BANK_DETAILS", response

        # 2. STATUS CHECK
        if any(word in text_lower for word in ["status", "balance", "owe", "debt", "owing"]):
            students = context.get("students", [])
            if not students:
                 return "ERROR", "I cannot find any students linked to your number."
            
            response = "📊 *Fee Status Report*\n\n"
            total_debt = 0
            
            for student in students:
                # Handle Dictionary Access (Safe serialization from webhook)
                # student is now a dict, not an ORM object
                full_name = student.get("full_name", "Student")
                class_level = student.get("class_level", "")
                payment_status = student.get("payment_status", "UNKNOWN")
                
                due = float(student.get("fees_total_due", 0))
                paid = float(student.get("amount_paid", 0))
                balance = due - paid
                
                status_emoji = "✅" if balance <= 0 else "🔴" 
                
                response += (
                    f"👤 *{full_name}* ({class_level})\n"
                    f"Status: {status_emoji} {payment_status}\n"
                    f"Outstanding: ₦{balance:,.2f}\n\n"
                )
            
            if total_debt > 0:
                response += f"💰 *Total to Pay: ₦{total_debt:,.2f}*\nType 'Pay' to get account details."
            else:
                response += "🎉 You are fully paid up! Thank you."
                
            return "SEND_STATUS", response

        # 3. COMPLAINT / SUPPORT
        if any(word in text_lower for word in ["help", "support", "complaint", "error", "issue", "fake"]):
            # Provide admin contact
            schools = context.get("schools", [])
            admin_contact = "the school office"
            if schools:
                # Use first school's phone
                admin_contact = f"https://wa.me/{schools[0].phone.replace('+', '')}"
            
            return "SEND_SUPPORT", f"📞 For support or complaints, please contact the School Admin here: {admin_contact}"

        # 4. AI-POWERED RESPONSE (Gemini) - TEMPORARILY DISABLED
        # logger.info(f"Analyzed intent for '{text}': Fallback to AI.")
        # from services.llm.gemini_client import gemini_client
        # ... (AI Code commented out for stability) ...
             
        # 5. STATIC FALLBACK (Reliable)
        logger.info(f"Analyzed intent for '{text}': Fallback to GREETING.")
        response = (
            f"👋 Welcome, *{sender_name}*.\n\n"
            "• *Upload a Receipt* to verify payment.\n"
            "• Type *'Status'* to check debt.\n"
            "• Type *'Pay'* for account details."
        )
        return "SEND_GREETING", response

    def safe_analyze_intent(self, text, sender, context, name):
        """Wrapper to prevent silence on crash."""
        try:
            return self.analyze_intent(text, sender, context, name)
        except Exception as e:
            logger.error(f"CRASH in conversation manager: {e}")
            return "ERROR_RESCUE", "⚠️ System Error: I encountered a problem checking your data. Please contact Admin."

# Singleton
conversation_manager = BotConversationManager()
