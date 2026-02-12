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
        # =================================================================
        # FULL AI MODE: Let Groq handle ALL conversations naturally
        # =================================================================
        logger.info(f"Routing '{text}' to Groq AI for natural language processing")
        
        from services.llm.groq_client import groq_client
        
        # Prepare rich context for AI
        students = context.get("students", [])
        schools = context.get("schools", [])
        
        student_data = students[0] if students else {}
        school_data = schools[0] if schools else {}
        
        # Build detailed context
        ai_context = {
            "student_name": student_data.get("full_name", "Student"),
            "class_level": student_data.get("class_level", ""),
            "school_name": school_data.get("school_name", "School"),
            "amount_due": f"N{student_data.get('balance', 0):,.2f}",
            "fees_total": f"N{student_data.get('fees_total_due', 0):,.2f}",
            "amount_paid": f"N{student_data.get('amount_paid', 0):,.2f}",
            "payment_status": student_data.get("payment_status", "UNKNOWN"),
            "due_date": str(student_data.get("due_date", "Unknown")),
            "days_until_due": student_data.get("days_until_due", 0),
            "bank_name": school_data.get("bank_name", "Unknown"),
            "account_number": school_data.get("account_number", "Unknown"),
            "account_name": school_data.get("account_name", "Unknown")
        }
        
        # Add instruction to AI based on intent hints
        portal_status = "Available" if school_data.get("portal_url") else "Not available (Pay via Bank Transfer only)"
        
        # ---- Build school bank details for the prompt ----
        db_bank_name = school_data.get('bank_name', 'Contact Admin')
        db_account_number = school_data.get('account_number', 'Contact Admin')
        db_account_name = school_data.get('account_name', 'Contact Admin')
        
        system_instruction = f"""You are the official assistant for {school_data.get('school_name', 'The School')}.
Use ONLY the following verified data to answer questions:

[OFFICIAL PAYMENT DETAILS - FROM DATABASE]
- Bank Name: {db_bank_name}
- Account Number: {db_account_number}
- Account Name: {db_account_name}
- Portal: {portal_status}

[STRICT RULES]
1. If asked for account/bank details, output EXACTLY the bank name, account number, and account name listed above. Do not change, rephrase, or guess alternatives.
2. NEVER invent, guess, or generate bank names, account numbers, account names, or URLs that are NOT listed above. This is CRITICAL.
3. If any of the above details show "Contact Admin" or are missing, say: "Please contact the school admin for bank details." Do NOT make up an alternative.
4. Do NOT mention any bank name other than "{db_bank_name}".
5. Do NOT generate any account number other than "{db_account_number}".

The parent just said: "{text}"

Student Info: {student_data.get('full_name', 'Student')} ({student_data.get('class_level', '')})
Payment Status: {student_data.get('payment_status', 'UNKNOWN')}
Outstanding Balance: N{student_data.get('balance', 0):,.2f}

If they ask about:
- FEES/STATUS/BALANCE: Tell them the status clearly
- PAYMENT/BANK/ACCOUNT: Give them the EXACT official payment details above
- COMPLAINTS/HELP: Direct them to school admin
- GREETING: Welcome them warmly

Respond naturally and helpfully. Keep it concise (2-3 sentences max)."""
        
        # Generate AI response with Groq
        if groq_client.is_active:
             ai_reply = groq_client.generate_message(ai_context, tone="helpful", custom_prompt=system_instruction)
             if ai_reply:
                 # POST-PROCESSING GUARD: Check for hallucinated bank details
                 ai_reply = self._guard_bank_details(ai_reply, db_bank_name, db_account_number, db_account_name)
                 return "AI_RESPONSE", ai_reply
        else:
             logger.warning("Groq Client inactive (missing key). Falling back.")
        
        # Ultimate fallback if AI completely fails
        return "SEND_GREETING", f"👋 Hi {sender_name}, my automated brain is offline momentarily. Please contact the school admin."
        


    def _guard_bank_details(self, ai_reply: str, db_bank: str, db_account: str, db_name: str) -> str:
        """
        Post-processing guard: If AI response contains account numbers
        that don't match the DB, append the correct details.
        """
        import re
        
        # Skip guard if DB details are missing
        if db_account in ("Contact Admin", "Unknown", ""):
            return ai_reply
        
        # Look for any 10-digit number in the response (Nigerian account numbers)
        account_pattern = re.findall(r'\b\d{10}\b', ai_reply)
        
        for found_number in account_pattern:
            if found_number != db_account:
                logger.warning(
                    f"⚠️ HALLUCINATION DETECTED: AI generated account '{found_number}' "
                    f"but DB has '{db_account}'. Replacing response."
                )
                # Replace the hallucinated response with DB-sourced details
                return (
                    f"Here are the official payment details:\n\n"
                    f"🏦 Bank: {db_bank}\n"
                    f"📄 Account Number: {db_account}\n"
                    f"👤 Account Name: {db_name}\n\n"
                    f"Please use these details for your transfer."
                )
        
        return ai_reply

    def safe_analyze_intent(self, text, sender, context, name):
        """Wrapper to prevent silence on crash."""
        try:
            return self.analyze_intent(text, sender, context, name)
        except Exception as e:
            logger.error(f"CRASH in conversation manager: {e}")
            return "ERROR_RESCUE", "⚠️ System Error: I encountered a problem checking your data. Please contact Admin."

# Singleton
conversation_manager = BotConversationManager()
