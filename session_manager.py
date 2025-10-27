from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SessionManager:
    """In-memory session management for user state and conversation context."""

    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.conversation_references: Dict[str, Any] = {}

    def create_session(self, user_id: str) -> Dict[str, Any]:
        """Create a new session for a user."""
        if user_id not in self.sessions:
            self.sessions[user_id] = {
                "user_id": user_id,
                "authenticated": False,
                "session_cookie": None,
                "user_info": None,
                "company_info": None,
                "accessible_sites": None,
                "conversation_history": [],
                "created_at": datetime.now(datetime.timezone.utc).isoformat(),
                "last_activity": datetime.now(datetime.timezone.utc).isoformat()
            }
            logger.info(f"Created new session for user: {user_id}")
        return self.sessions[user_id]

    def get_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a user's session."""
        session = self.sessions.get(user_id)
        if session:
            session["last_activity"] = datetime.now(datetime.timezone.utc).isoformat()
        return session

    def update_session(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update a user's session with new data."""
        if user_id not in self.sessions:
            self.create_session(user_id)

        self.sessions[user_id].update(updates)
        self.sessions[user_id]["last_activity"] = datetime.now(datetime.timezone.utc).isoformat()
        logger.info(f"Updated session for user: {user_id}")
        return self.sessions[user_id]

    def delete_session(self, user_id: str) -> bool:
        """Delete a user's session."""
        if user_id in self.sessions:
            del self.sessions[user_id]
            logger.info(f"Deleted session for user: {user_id}")
            return True
        return False

    def is_authenticated(self, user_id: str) -> bool:
        """Check if a user is authenticated."""
        session = self.get_session(user_id)
        return session.get("authenticated", False) if session else False

    def set_authenticated(self, user_id: str, authenticated: bool, user_info: Optional[Dict] = None, company_info: Optional[Dict] = None):
        """Set authentication status and related info."""
        updates = {"authenticated": authenticated}
        if user_info:
            updates["user_info"] = user_info
        if company_info:
            updates["company_info"] = company_info
        self.update_session(user_id, updates)
        logger.info(f"Set authentication for user {user_id}: {authenticated}")

    def add_to_history(self, user_id: str, role: str, content: str):
        """Add a message to conversation history."""
        session = self.get_session(user_id)
        if not session:
            session = self.create_session(user_id)

        history = session.get("conversation_history", [])
        history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(datetime.timezone.utc).isoformat()
        })

        # Keep only last 30 messages to prevent token overflow
        if len(history) > 30:
            history = history[-30:]

        self.update_session(user_id, {"conversation_history": history})

    def get_conversation_history(self, user_id: str) -> List[Dict[str, str]]:
        """Get conversation history for context."""
        session = self.get_session(user_id)
        if not session:
            return []

        history = session.get("conversation_history", [])
        # Return in format expected by agents SDK
        return [{"role": msg["role"], "content": msg["content"]} for msg in history]

    def clear_history(self, user_id: str):
        """Clear conversation history."""
        self.update_session(user_id, {"conversation_history": []})
        logger.info(f"Cleared conversation history for user: {user_id}")

    def store_conversation_reference(self, user_id: str, reference: Any):
        """Store conversation reference for proactive messaging."""
        self.conversation_references[user_id] = reference
        logger.info(f"Stored conversation reference for user: {user_id}")

    def get_conversation_reference(self, user_id: str) -> Optional[Any]:
        """Get stored conversation reference."""
        return self.conversation_references.get(user_id)

    def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user info from session."""
        session = self.get_session(user_id)
        return session.get("user_info") if session else None

    def get_company_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get company info from session."""
        session = self.get_session(user_id)
        return session.get("company_info") if session else None

    def get_accessible_sites(self, user_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get accessible sites from session."""
        session = self.get_session(user_id)
        return session.get("accessible_sites") if session else None

    def set_accessible_sites(self, user_id: str, sites: List[Dict[str, Any]]):
        """Store accessible sites in session."""
        self.update_session(user_id, {"accessible_sites": sites})

    def get_active_users(self) -> List[str]:
        """Get list of all active user IDs."""
        return list(self.sessions.keys())

    def get_session_count(self) -> int:
        """Get total number of active sessions."""
        return len(self.sessions)
