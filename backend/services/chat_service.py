"""
CHAT SERVICE
============
Session management for A.D.A
- Create/load chat sessions
- Persist to JSON files
- Manage conversation history
- Support streaming and non-streaming
"""

import json
import logging
import time
import uuid
import threading
from pathlib import Path
from typing import List, Optional, Dict, Iterator, Any, Union

from config_ada import CHATS_DATA_DIR, MAX_CHAT_HISTORY_TURNS
from app.models import ChatMessage
from app.utils.key_rotation import get_next_key_pair

logger = logging.getLogger("ADA")

SAVE_EVERY_N_CHUNKS = 5


class ChatSession:
    """In-memory chat session"""
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages: List[ChatMessage] = []
        self.created_at = time.time()
        self.updated_at = time.time()


class ChatService:
    def __init__(self, groq_service, web_search_service=None):
        self.groq_service = groq_service
        self.web_search_service = web_search_service
        self.sessions: Dict[str, ChatSession] = {}
        self._save_lock = threading.Lock()
    
    # ==================== SESSION MANAGEMENT ====================
    
    def validate_session_id(self, session_id: str) -> bool:
        """Security check for session ID"""
        if not session_id or not session_id.strip():
            return False
        if "\0" in session_id:
            return False
        if ".." in session_id or "/" in session_id or "\\" in session_id:
            return False
        if len(session_id) > 255:
            return False
        return True
    
    def load_session(self, session_id: str) -> Optional[ChatSession]:
        """Load session from JSON file"""
        safe_id = session_id.replace("-", "").replace(" ", "_")
        filepath = CHATS_DATA_DIR / f"chat_{safe_id}.json"
        
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            session = ChatSession(session_id)
            for msg in data.get("messages", []):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    session.messages.append(ChatMessage(role=role, content=content))
            
            logger.info(f"[CHAT] Loaded session {session_id[:12]} with {len(session.messages)} messages")
            return session
            
        except Exception as e:
            logger.warning(f"[CHAT] Failed to load session: {e}")
            return None
    
    def save_session(self, session: ChatSession, log_timing: bool = True):
        """Save session to JSON file"""
        safe_id = session.session_id.replace("-", "").replace(" ", "_")
        filepath = CHATS_DATA_DIR / f"chat_{safe_id}.json"
        
        data = {
            "session_id": session.session_id,
            "messages": [
                {"role": m.role, "content": m.content}
                for m in session.messages
            ]
        }
        
        try:
            with self._save_lock:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[CHAT] Failed to save session: {e}")
    
    def get_or_create_session(self, session_id: Optional[str] = None) -> str:
        """Get existing session or create new one"""
        if not session_id:
            # Generate new UUID
            session_id = str(uuid.uuid4())
            session = ChatSession(session_id)
            self.sessions[session_id] = session
            logger.info(f"[CHAT] Created new session: {session_id[:12]}")
            return session_id
        
        # Validate
        if not self.validate_session_id(session_id):
            raise ValueError(f"Invalid session_id: {session_id}")
        
        # Check memory first
        if session_id in self.sessions:
            return session_id
        
        # Try loading from disk
        session = self.load_session(session_id)
        if session:
            self.sessions[session_id] = session
            return session_id
        
        # Create new
        session = ChatSession(session_id)
        self.sessions[session_id] = session
        return session_id
    
    # ==================== HISTORY FORMATTING ====================
    
    def format_history(self, session_id: str, exclude_last: bool = False) -> List[tuple]:
        """Format message history as (user, assistant) tuples"""
        if session_id not in self.sessions:
            return []
        
        messages = self.sessions[session_id].messages
        
        if exclude_last and messages:
            messages = messages[:-1]
        
        history = []
        i = 0
        while i < len(messages) - 1:
            if messages[i].role == "user" and messages[i+1].role == "assistant":
                history.append((messages[i].content, messages[i+1].content))
                i += 2
            else:
                i += 1
        
        # Trim to max history
        if len(history) > MAX_CHAT_HISTORY_TURNS:
            history = history[-MAX_CHAT_HISTORY_TURNS:]
        
        return history
    
    def add_message(self, session_id: str, role: str, content: str):
        """Add message to session"""
        if session_id not in self.sessions:
            self.sessions[session_id] = ChatSession(session_id)
        
        self.sessions[session_id].messages.append(ChatMessage(role=role, content=content))
        self.sessions[session_id].updated_at = time.time()
    
    # ==================== CHAT PROCESSING ====================
    
    def process_message(
        self,
        session_id: str,
        message: str,
        mode: str = "general",  # "general" or "realtime"
        use_tts: bool = False
    ) -> Iterator[Union[str, Dict]]:
        """Process chat message with streaming"""
        
        # Add user message
        self.add_message(session_id, "user", message)
        self.add_message(session_id, "assistant", "")  # Placeholder
        
        # Get history
        history = self.format_history(session_id, exclude_last=True)
        
        # Get API key index
        _, chat_idx = get_next_key_pair(len([1]), need_brain=False)
        
        # Prepare context
        extra_context = ""
        search_results = None
        
        # If realtime mode, do web search first
        if mode == "realtime" and self.web_search_service and self.web_search_service.is_enabled():
            query = self.web_search_service.extract_query(message, history)
            search_results = self.web_search_service.search(query)
            extra_context = self.web_search_service.format_for_prompt(search_results)
            
            yield {"_activity": "search_complete", "query": query, "results_count": len(search_results.get("results", []))}
        
        yield {"_activity": "processing", "mode": mode}
        
        # Stream response
        session = self.sessions[session_id]
        response_text = ""
        chunk_count = 0
        
        for chunk in self.groq_service.stream_response(
            message, history, extra_context, mode, chat_idx
        ):
            if isinstance(chunk, dict):
                yield chunk
                continue
            
            if chunk:
                response_text += chunk
                session.messages[-1].content = response_text
                chunk_count += 1
                
                # Periodic save
                if chunk_count % SAVE_EVERY_N_CHUNKS == 0:
                    self.save_session(session, log_timing=False)
                
                yield chunk
        
        # Final save
        self.save_session(session)
        
        logger.info(f"[CHAT] Session {session_id[:12]}: {chunk_count} chunks, {len(response_text)} chars")
        
        # Yield search results for UI
        if search_results and mode == "realtime":
            yield {"_search_results": search_results}
    
    def get_history(self, session_id: str) -> List[Dict]:
        """Get session history for frontend"""
        if session_id not in self.sessions:
            return []
        
        return [
            {"role": m.role, "content": m.content}
            for m in self.sessions[session_id].messages
        ]
