"""
=============================================================================
SmartBursar - Conversation Manager
=============================================================================
Manages conversation state and flow for the WhatsApp bot.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Conversation States
STATE_IDLE = "IDLE"
STATE_WAITING_FOR_RECEIPT = "WAITING_FOR_RECEIPT"
STATE_IDENTIFYING_STUDENT = "IDENTIFYING_STUDENT"

class BotConversationManager:
    """
    Tracks state for each user to enable multi-turn conversations.
    """
    
    def __init__(self):
        # In-memory session store
        # Key: phone_number, Value: { state, last_interaction, context }
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.session_timeout = timedelta(minutes=15) # Reset state after 15 mins
    
    def get_user_state(self, phone_number: str) -> str:
        """Get current state for a user."""
        self._clean_expired_sessions()
        session = self.sessions.get(phone_number)
        if not session:
            return STATE_IDLE
        return session.get("state", STATE_IDLE)
    
    def update_user_state(self, phone_number: str, new_state: str, context_update: Optional[Dict] = None):
        """Update user state and context."""
        if phone_number not in self.sessions:
            self.sessions[phone_number] = {
                "state": new_state,
                "last_interaction": datetime.now(),
                "context": {}
            }
        else:
            self.sessions[phone_number]["state"] = new_state
            self.sessions[phone_number]["last_interaction"] = datetime.now()
        
        if context_update:
            self.sessions[phone_number]["context"].update(context_update)
            
    def get_context(self, phone_number: str) -> Dict[str, Any]:
        """Get stored context data for user."""
        session = self.sessions.get(phone_number)
        return session.get("context", {}) if session else {}

    def clear_session(self, phone_number: str):
        """Reset user session to IDLE."""
        if phone_number in self.sessions:
            del self.sessions[phone_number]

    def _clean_expired_sessions(self):
        """Remove sessions older than timeout."""
        now = datetime.now()
        expired = []
        for phone, data in self.sessions.items():
            if now - data["last_interaction"] > self.session_timeout:
                expired.append(phone)
        for phone in expired:
            del self.sessions[phone]

    def handle_incoming_text(self, text: str, phone_number: str) -> Tuple[str, Optional[str]]:
        """
        Determine next action based on text and current state.
        Returns: (Action, Reply_Message)
        """
        state = self.get_user_state(phone_number)
        text_lower = text.lower().strip()
        
        # --- GLOBAL COMMANDS ---
        if text_lower in ["hi", "hello", "menu", "start", "restart"]:
            self.clear_session(phone_number)
            return "SEND_MENU", None
            
        if text_lower in ["status", "balance", "check"]:
            return "check_status", "To check your status, please tell me the **Student's Name**."

        # --- STATE: IDLE ---
        if state == STATE_IDLE:
            if any(word in text_lower for word in ["paid", "pay", "payment", "transfer"]):
                self.update_user_state(phone_number, STATE_WAITING_FOR_RECEIPT)
                return "ASK_RECEIPT", "Great! Please **send the receipt** (Image or PDF) now."
            
            # Check if it looks like a student name search from IDLE (quick check)
            if len(text.split()) >= 2 and len(text) > 5:
                 # Assume they might be typing a name.
                 # In a real app we'd check DB for fuzzy match here, 
                 # but for now let's guide them.
                 return "UNKNOWN", "I didn't catch that. Type **'Paid'** to verify a payment, or **'Menu'** to start over."
            
            return "UNKNOWN", "👋 Welcome to SmartBursar!\n\nI can help you verify payments.\n\nReply with:\n- **'Paid'** if you want to submit a receipt.\n- **'Status'** to check fee balance."

        # --- STATE: WAITING_FOR_RECEIPT ---
        if state == STATE_WAITING_FOR_RECEIPT:
            # If they send text instead of image
            return "REMIND_RECEIPT", "I'm listening 👂. Please upload the **Receipt Image** or PDF so I can verify it."

        # --- STATE: IDENTIFYING_STUDENT ---
        if state == STATE_IDENTIFYING_STUDENT:
            # User is replying with the student name manually
            return "PROCESS_STUDENT_NAME", None # Caller should handle logic to lookup student name

        return "UNKNOWN", "Type **'Menu'** to restart."

# Singleton
conversation_manager = BotConversationManager()
