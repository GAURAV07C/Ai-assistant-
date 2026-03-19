"""
ASTRO-STYLE CHAT INTEGRATION
=============================
Add to A.D.A backend for:
- Groq LLM with multi-key rotation
- Web search (Tavily)
- Learning database (FAISS RAG)
- Session persistence
- TTS voice output
"""

import logging
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import json
import asyncio

# Import our new services
from config_ada import (
    GROQ_API_KEYS,
    TAVILY_API_KEY,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    MAX_CHAT_HISTORY_TURNS,
    TTS_VOICE,
    TTS_RATE,
)

logger = logging.getLogger("ADA")

# Global services (initialized in lifespan)
vector_store_service = None
groq_service = None
chat_service = None
tts_service = None
web_search_service = None


async def init_astro_services():
    """Initialize ASTRO-style services"""
    global vector_store_service, groq_service, chat_service, tts_service, web_search_service
    
    logger.info("[ASTRO] Initializing services...")
    
    # Vector Store
    try:
        from services.vector_store import VectorStoreService
        vector_store_service = VectorStoreService()
        vector_store_service.create_vector_store()
        logger.info("[ASTRO] Vector store ready")
    except Exception as e:
        logger.error(f"[ASTRO] Vector store init failed: {e}")
    
    # Groq Service
    try:
        from services.groq_service import GroqService
        groq_service = GroqService(vector_store_service)
        logger.info(f"[ASTRO] Groq service ready ({len(GROQ_API_KEYS)} keys)")
    except Exception as e:
        logger.error(f"[ASTRO] Groq service init failed: {e}")
    
    # Web Search
    try:
        from services.web_search import WebSearchService
        web_search_service = WebSearchService()
        logger.info(f"[ASTRO] Web search: {'enabled' if web_search_service.is_enabled() else 'disabled'}")
    except Exception as e:
        logger.error(f"[ASTRO] Web search init failed: {e}")
    
    # Chat Service
    try:
        from services.chat_service import ChatService
        chat_service = ChatService(groq_service, web_search_service)
        logger.info("[ASTRO] Chat service ready")
    except Exception as e:
        logger.error(f"[ASTRO] Chat service init failed: {e}")
    
    # TTS Service
    try:
        from services.tts_service import TTSService
        tts_service = TTSService()
        logger.info(f"[ASTRO] TTS ready (voice: {TTS_VOICE})")
    except Exception as e:
        logger.error(f"[ASTRO] TTS init failed: {e}")
    
    logger.info("[ASTRO] All services initialized!")


def setup_astro_routes(app: FastAPI):
    """Add ASTRO-style routes to FastAPI app"""
    
    # ==================== CHAT ENDPOINTS ====================
    
    @app.post("/chat/stream")
    async def chat_stream(message: str, session_id: Optional[str] = None, mode: str = "general"):
        """Stream chat response with Groq"""
        if not chat_service:
            raise HTTPException(status_code=503, detail="Chat service not initialized")
        
        if not GROQ_API_KEYS:
            raise HTTPException(status_code=503, detail="No Groq API key configured")
        
        # Get or create session
        session_id = chat_service.get_or_create_session(session_id)
        
        async def generate():
            # Send session_id first
            yield f"data: {json.dumps({'session_id': session_id, 'chunk': '', 'done': False})}\n\n"
            
            # Process message
            try:
                for chunk in chat_service.process_message(session_id, message, mode=mode):
                    if isinstance(chunk, dict):
                        yield f"data: {json.dumps(chunk)}\n\n"
                    else:
                        yield f"data: {json.dumps({'chunk': chunk, 'done': False})}\n\n"
                
                # Done
                yield f"data: {json.dumps({'chunk': '', 'done': True, 'session_id': session_id})}\n\n"
                
            except Exception as e:
                logger.error(f"[CHAT] Error: {e}")
                yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"}
        )
    
    @app.post("/chat/stream/tts")
    async def chat_stream_tts(message: str, session_id: Optional[str] = None, mode: str = "general"):
        """Stream chat response with inline TTS"""
        if not chat_service or not tts_service:
            raise HTTPException(status_code=503, detail="Chat/TTS service not initialized")
        
        session_id = chat_service.get_or_create_session(session_id)
        full_response = ""
        
        async def generate():
            nonlocal full_response
            
            # Send session_id first
            yield f"data: {json.dumps({'session_id': session_id, 'chunk': '', 'done': False})}\n\n"
            
            # Accumulate response for TTS
            response_buffer = ""
            
            try:
                for chunk in chat_service.process_message(session_id, message, mode=mode):
                    if isinstance(chunk, dict):
                        yield f"data: {json.dumps(chunk)}\n\n"
                    else:
                        full_response += chunk
                        response_buffer += chunk
                        yield f"data: {json.dumps({'chunk': chunk, 'done': False})}\n\n"
                        
                        # Check for sentence completion and generate TTS
                        if tts_service and any(p in response_buffer for p in '.!?'):
                            sentences, response_buffer = split_for_tts(response_buffer)
                            for sent in sentences:
                                audio_b64 = tts_service.generate(sent)
                                if audio_b64:
                                    yield f"data: {json.dumps({'audio': audio_b64, 'sentence': sent})}\n\n"
                
                # Flush remaining for TTS
                if response_buffer.strip() and tts_service:
                    audio_b64 = tts_service.generate(response_buffer.strip())
                    if audio_b64:
                        yield f"data: {json.dumps({'audio': audio_b64, 'sentence': response_buffer.strip()})}\n\n"
                
                # Done
                yield f"data: {json.dumps({'chunk': '', 'done': True, 'session_id': session_id})}\n\n"
                
            except Exception as e:
                logger.error(f"[CHAT+TTS] Error: {e}")
                yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"}
        )
    
    @app.get("/chat/history/{session_id}")
    async def get_chat_history(session_id: str):
        """Get chat history for a session"""
        if not chat_service:
            raise HTTPException(status_code=503, detail="Chat service not initialized")
        
        history = chat_service.get_history(session_id)
        return {"session_id": session_id, "messages": history}
    
    # ==================== TTS ENDPOINTS ====================
    
    @app.post("/tts")
    async def text_to_speech(text: str, voice: Optional[str] = None, rate: Optional[str] = None):
        """Generate TTS audio"""
        if not tts_service:
            raise HTTPException(status_code=503, detail="TTS service not initialized")
        
        audio_b64 = tts_service.generate(text)
        
        if not audio_b64:
            raise HTTPException(status_code=500, detail="TTS generation failed")
        
        return {"audio": audio_b64, "text": text}
    
    # ==================== VECTOR STORE ENDPOINTS ====================
    
    @app.post("/learn")
    async def add_learning_data(content: str, source: str = "manual"):
        """Add new learning data"""
        if not vector_store_service:
            raise HTTPException(status_code=503, detail="Vector store not initialized")
        
        vector_store_service.add_learning_data(content, source)
        
        return {"status": "success", "message": f"Added learning data from {source}"}
    
    @app.get("/learn/context")
    async def get_context(query: str, k: int = 10):
        """Get relevant context for a query"""
        if not vector_store_service:
            raise HTTPException(status_code=503, detail="Vector store not initialized")
        
        context = vector_store_service.get_context(query, k=k)
        
        return {"query": query, "context": context, "chunks_retrieved": k}
    
    # ==================== SEARCH ENDPOINTS ====================
    
    @app.get("/search")
    async def web_search(query: str):
        """Web search using Tavily"""
        if not web_search_service:
            raise HTTPException(status_code=503, detail="Search service not initialized")
        
        if not web_search_service.is_enabled():
            raise HTTPException(status_code=503, detail="Web search not configured (need TAVILY_API_KEY)")
        
        results = web_search_service.search(query)
        return results
    
    # ==================== HEALTH CHECK ====================
    
    @app.get("/health/astro")
    async def astro_health():
        """Check ASTRO services health"""
        return {
            "vector_store": vector_store_service is not None,
            "groq_service": groq_service is not None,
            "chat_service": chat_service is not None,
            "tts_service": tts_service is not None,
            "web_search": web_search_service is not None and web_search_service.is_enabled(),
            "groq_keys": len(GROQ_API_KEYS),
        }


def split_for_tts(text: str) -> tuple:
    """Split accumulated text for TTS"""
    import re
    split_re = re.compile(r"(?<=[.!?,;:])\s+")
    parts = split_re.split(text)
    
    if len(parts) <= 1:
        return [], text
    
    sentences = [p.strip() for p in parts[:-1] if p.strip()]
    remaining = parts[-1].strip()
    
    return sentences, remaining


logger.info("[ASTRO] Routes configured")
