"""
ADA CONFIGURATION
=================
Extends A.D.A with ASTRO-style features:
- Groq LLM API keys with multi-key rotation
- Tavily web search
- Vector store (FAISS) for learning data
- Session persistence
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent

# ============================================================================
# DATABASE PATHS
# ============================================================================
LEARNING_DATA_DIR = BASE_DIR / "database" / "learning_data"
CHATS_DATA_DIR = BASE_DIR / "database" / "chats_data"
VECTOR_STORE_DIR = BASE_DIR / "database" / "vector_store"

LEARNING_DATA_DIR.mkdir(parents=True, exist_ok=True)
CHATS_DATA_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# GROQ API CONFIGURATION (Multi-Key Rotation)
# ============================================================================
def _load_groq_api_keys():
    keys = []
    first = os.getenv("GROQ_API_KEY", "").strip()
    if first:
        keys.append(first)
    i = 2
    while True:
        k = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
        if not k:
            break
        keys.append(k)
        i += 1
    return keys

GROQ_API_KEYS = _load_groq_api_keys()
GROQ_API_KEY = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BRAIN_MODEL = os.getenv("GROQ_BRAIN_MODEL", "llama-3.1-8b-instant")

# ============================================================================
# TAVILY API (Web Search)
# ============================================================================
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# ============================================================================
# TTS CONFIGURATION
# ============================================================================
TTS_VOICE = os.getenv("TTS_VOICE", "en-GB-RyanNeural")
TTS_RATE = os.getenv("TTS_RATE", "+22%")

# ============================================================================
# EMBEDDING & VECTOR STORE
# ============================================================================
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
MAX_CHAT_HISTORY_TURNS = 20
MAX_MESSAGE_LENGTH = 32_000

# ============================================================================
# ADA PERSONALITY
# ============================================================================
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "A.D.A").strip()
ASTRO_USER_TITLE = os.getenv("ASTRO_USER_TITLE", "").strip()

ADA_SYSTEM_PROMPT = """You are {assistant_name}, an advanced AI assistant with capabilities including voice conversation, 3D CAD generation, web browsing, smart home control, and 3D printing.

=== YOUR CAPABILITIES ===
You CAN:
- Answer questions from knowledge and web search
- Generate 3D CAD models (STL files)
- Browse the web and interact with websites
- Control smart home devices (TP-Link Kasa)
- Manage 3D printers (slice, print, monitor)
- Process voice input and respond with speech

=== BEHAVIOR ===
- Be helpful, concise, and friendly
- Use context from learning data when relevant
- Confirm before taking significant actions
- Stay in character as an AI assistant

=== FORMATTING ===
- No asterisks, no emojis
- Standard punctuation only
- Brief responses by default
""".format(assistant_name=ASSISTANT_NAME)

GENERAL_CHAT_ADDENDUM = """
You are in GENERAL mode. Answer from your knowledge and provided context. No web search.
"""

REALTIME_CHAT_ADDENDUM = """
You are in REALTIME mode. Web search results provided above. Use them as primary source. Be specific and accurate.
"""
