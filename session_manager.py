from typing import Dict, Optional, Any
import logging
import asyncio
from botbuilder.schema import ConversationReference

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        # pending elicitation futures: user_id -> Future
        self._pending_elicitations: Dict[str, asyncio.Future] = {}
        # conversation references for proactive messaging
        self._conversation_references: Dict[str, ConversationReference] = {}
        # user and company info
        self._user_info: Dict[str, Dict[str, Any]] = {}
        # last active user id for context propagation
        self._last_active_user: Optional[str] = None

    def create_session(self, user_id: str, session_data: Dict[str, Any]) -> None:
        logger.debug(f"Creating session for user_id: {user_id}")
        self.sessions[user_id] = session_data
        self._last_active_user = user_id

    def set_active_user(self, user_id: str) -> None:
        """Mark a user as the current active context owner."""
        self._last_active_user = user_id

    def get_active_user(self) -> Optional[str]:
        """Return the most recently active user id, if any."""
        return self._last_active_user

    def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Convenience getter for user-specific info stored alongside session."""
        info = self._user_info.get(user_id)
        if not info:
            return None
        # prefer nested 'user' key if structure is normalized
        return info.get("user") or info

    def get_company_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Convenience getter for company-specific info stored alongside session."""
        info = self._user_info.get(user_id)
        if not info:
            return None
        # prefer nested 'company' key if structure is normalized
        return info.get("company") or info

    def get_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        logger.debug(f"Retrieving session for user_id: {user_id}")
        return self.sessions.get(user_id)

    def delete_session(self, user_id: str) -> None:
        logger.debug(f"Deleting session for user_id: {user_id}")
        if user_id in self.sessions:
            del self.sessions[user_id]

    def update_session_info(self, user_id: str, info_data: Dict[str, Any]) -> None:
        """Update session with additional information like user and company details."""
        logger.debug(f"Updating session info for user_id: {user_id}")
        self._user_info[user_id] = info_data
        
    def get_session_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get additional session information like user and company details."""
        return self._user_info.get(user_id)

    def store_conversation_reference(self, user_id: str, conversation_reference: ConversationReference) -> None:
        """Store conversation reference for proactive messaging."""
        self._conversation_references[user_id] = conversation_reference
        
    def get_conversation_reference(self, user_id: str) -> Optional[ConversationReference]:
        """Get conversation reference for proactive messaging."""
        return self._conversation_references.get(user_id)
        
    def get_all_conversation_references(self) -> Dict[str, ConversationReference]:
        """Get all conversation references for proactive messaging."""
        return self._conversation_references

    # --- Elicitation support ------------------------------------------------
    def create_elicitation_request(self, user_id: str) -> asyncio.Future:
        """Create and return a Future that will be completed when user replies."""
        fut = asyncio.get_event_loop().create_future()
        self._pending_elicitations[user_id] = fut
        logger.debug("Created elicitation future for %s", user_id)
        return fut

    def has_pending_elicitation(self, user_id: str) -> bool:
        return user_id in self._pending_elicitations

    def resolve_elicitation(self, user_id: str, value: Any) -> None:
        fut = self._pending_elicitations.pop(user_id, None)
        if fut and not fut.done():
            fut.set_result(value)
            logger.debug("Resolved elicitation for %s", user_id)

    def cancel_elicitation(self, user_id: str) -> None:
        fut = self._pending_elicitations.pop(user_id, None)
        if fut and not fut.done():
            fut.cancel()
            logger.debug("Cancelled elicitation for %s", user_id)

    def get_any_active_user(self) -> Optional[str]:
        """Return any user id with an active session (best-effort)."""
        for uid in self.sessions.keys():
            return uid
        return None


# module-level singleton used across the app
session_manager = SessionManager()