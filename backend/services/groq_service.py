"""
GROQ SERVICE
============
LLM service for A.D.A with multi-key rotation
- Uses Groq API (Llama models)
- Multi-key fallback when rate limited
- Streaming support
- Integration with vector store for RAG
"""

import logging
import time
from typing import List, Optional, Iterator, Union, Dict, Any

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from config_ada import (
    GROQ_API_KEYS,
    GROQ_MODEL,
    ADA_SYSTEM_PROMPT,
    GENERAL_CHAT_ADDENDUM,
    REALTIME_CHAT_ADDENDUM,
)
from app.utils.key_rotation import get_next_key_pair

logger = logging.getLogger("ADA")

GROQ_REQUEST_TIMEOUT = 60

ALL_APIS_FAILED_MESSAGE = "I'm unable to process your request. All API services are temporarily unavailable."


class AllGroqApisFailedError(Exception):
    pass


def escape_curly_braces(text: str) -> str:
    if not text:
        return text
    return text.replace("{", "{{").replace("}", "}}")


def _is_rate_limit_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "tokens per day" in msg


def _mask_key(key: str) -> str:
    if not key or len(key) <= 12:
        return "***"
    return f"{key[:8]}...{key[-4:]}"


class GroqService:
    def __init__(self, vector_store_service=None):
        if not GROQ_API_KEYS:
            raise ValueError("No Groq API keys configured")
        
        self.llms = [
            ChatGroq(
                groq_api_key=key,
                model_name=GROQ_MODEL,
                temperature=0.5,
                request_timeout=GROQ_REQUEST_TIMEOUT,
            )
            for key in GROQ_API_KEYS
        ]
        self.vector_store_service = vector_store_service
        logger.info(f"[GROQ] Initialized with {len(GROQ_API_KEYS)} keys")
    
    def _build_prompt(
        self,
        question: str,
        chat_history: Optional[List[tuple]] = None,
        extra_context: str = "",
        mode: str = "general"
    ) -> tuple:
        """Build prompt with system message, context, and history"""
        
        # Get context from vector store
        context = ""
        if self.vector_store_service:
            context = self.vector_store_service.get_context(question, k=10)
        
        # Build system message
        system_msg = ADA_SYSTEM_PROMPT
        
        if extra_context:
            system_msg += f"\n\n{extra_context}"
        
        if context:
            system_msg += f"\n\nRelevant context:\n{escape_curly_braces(context)}"
        
        if mode == "realtime":
            system_msg += REALTIME_CHAT_ADDENDUM
        else:
            system_msg += GENERAL_CHAT_ADDENDUM
        
        # Build prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}"),
        ])
        
        # Convert history to LangChain messages
        messages = []
        if chat_history:
            for user_msg, ai_msg in chat_history:
                messages.append(HumanMessage(content=user_msg))
                messages.append(AIMessage(content=ai_msg))
        
        return prompt, messages
    
    def _invoke_llm(
        self,
        prompt: ChatPromptTemplate,
        messages: list,
        question: str,
        key_start_index: int = 0,
    ) -> str:
        """Call LLM with multi-key fallback"""
        n = len(self.llms)
        
        for j in range(n):
            i = (key_start_index + j) % n
            logger.info(f"[GROQ] Trying key #{i+1}/{n}")
            
            try:
                chain = prompt | self.llms[i]
                response = chain.invoke({"history": messages, "question": question})
                if i > 0:
                    logger.info(f"[GROQ] Fallback success with key #{i+1}")
                return response.content
            except Exception as e:
                logger.warning(f"[GROQ] Key #{i+1} failed: {str(e)[:100]}")
                if j < n - 1:
                    continue
                break
        
        raise AllGroqApisFailedError(ALL_APIS_FAILED_MESSAGE)
    
    def _stream_llm(
        self,
        prompt: ChatPromptTemplate,
        messages: list,
        question: str,
        key_start_index: int = 0,
    ) -> Iterator[str]:
        """Stream LLM response with multi-key fallback"""
        n = len(self.llms)
        
        for j in range(n):
            i = (key_start_index + j) % n
            logger.info(f"[GROQ] Streaming with key #{i+1}/{n}")
            
            try:
                chain = prompt | self.llms[i]
                stream_start = time.perf_counter()
                first_chunk_time = None
                chunk_count = 0
                
                for chunk in chain.stream({"history": messages, "question": question}):
                    content = ""
                    if hasattr(chunk, 'content'):
                        content = chunk.content or ""
                    elif isinstance(chunk, dict):
                        content = chunk.get("content", "") or ""
                    
                    if content:
                        if first_chunk_time is None:
                            first_chunk_time = time.perf_counter() - stream_start
                            logger.info(f"[GROQ] First token: {first_chunk_time:.3f}s")
                        chunk_count += 1
                        yield content
                
                total_time = time.perf_counter() - stream_start
                logger.info(f"[GROQ] Stream complete: {chunk_count} chunks in {total_time:.3f}s")
                return
                
            except Exception as e:
                logger.warning(f"[GROQ] Key #{i+1} stream failed: {str(e)[:100]}")
                if j < n - 1:
                    continue
                break
        
        raise AllGroqApisFailedError(ALL_APIS_FAILED_MESSAGE)
    
    def get_response(
        self,
        question: str,
        chat_history: Optional[List[tuple]] = None,
        extra_context: str = "",
        mode: str = "general",
        key_start_index: int = 0,
    ) -> str:
        """Get non-streaming response"""
        prompt, messages = self._build_prompt(
            question, chat_history, extra_context, mode
        )
        return self._invoke_llm(prompt, messages, question, key_start_index)
    
    def stream_response(
        self,
        question: str,
        chat_history: Optional[List[tuple]] = None,
        extra_context: str = "",
        mode: str = "general",
        key_start_index: int = 0,
    ) -> Iterator[Union[str, Dict]]:
        """Get streaming response"""
        prompt, messages = self._build_prompt(
            question, chat_history, extra_context, mode
        )
        
        # Yield context retrieval event
        yield {"_activity": "context_retrieved"}
        
        # Stream LLM response
        yield from self._stream_llm(prompt, messages, question, key_start_index)
