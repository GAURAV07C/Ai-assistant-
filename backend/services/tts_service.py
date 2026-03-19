"""
TTS SERVICE
===========
Text-to-Speech using Microsoft Edge TTS
- Server-side generation
- Streaming support
- Multiple voice options
"""

import asyncio
import base64
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import edge_tts

from config_ada import TTS_VOICE, TTS_RATE

logger = logging.getLogger("ADA")

# Sentence splitting regex
_SPLIT_RE = re.compile(r"(?<=[.!?,;:])\s+")

# Thread pool for parallel TTS
_tts_pool = ThreadPoolExecutor(max_workers=4)


def split_sentences(text: str) -> tuple:
    """Split text into sentences"""
    parts = _SPLIT_RE.split(text)
    if len(parts) <= 1:
        return [], text
    
    sentences = [p.strip() for p in parts[:-1] if p.strip()]
    remaining = parts[-1].strip()
    
    return sentences, remaining


async def _generate_audio_async(text: str, voice: str, rate: str) -> bytes:
    """Generate MP3 audio from text"""
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    parts = []
    
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            parts.append(chunk["data"])
    
    return b"".join(parts)


def generate_audio(text: str, voice: str = None, rate: str = None) -> bytes:
    """Generate audio synchronously (runs in thread pool)"""
    voice = voice or TTS_VOICE
    rate = rate or TTS_RATE
    
    async def inner():
        return await _generate_audio_async(text, voice, rate)
    
    return asyncio.run(inner())


class TTSService:
    def __init__(self, voice: str = None, rate: str = None):
        self.voice = voice or TTS_VOICE
        self.rate = rate or TTS_RATE
        self.enabled = True
    
    def generate(self, text: str) -> Optional[str]:
        """Generate base64-encoded audio"""
        if not self.enabled:
            return None
        
        try:
            audio_bytes = generate_audio(text, self.voice, self.rate)
            if audio_bytes:
                return base64.b64encode(audio_bytes).decode("ascii")
        except Exception as e:
            logger.warning(f"[TTS] Generation failed: {e}")
        
        return None
    
    def generate_sentences(self, text: str) -> list:
        """Split text and generate audio for each sentence"""
        sentences, remaining = split_sentences(text)
        
        # Add remaining if substantial
        if remaining and len(remaining.split()) >= 3:
            sentences.append(remaining)
        elif remaining:
            # Append to last sentence
            if sentences:
                sentences[-1] += " " + remaining
        
        # Generate audio for each
        results = []
        for sent in sentences:
            audio_b64 = self.generate(sent)
            if audio_b64:
                results.append({
                    "sentence": sent,
                    "audio": audio_b64
                })
        
        return results
    
    async def stream_audio(self, text: str, callback):
        """
        Stream audio sentence by sentence
        
        Args:
            text: Full text to speak
            callback: Async function to call with (sentence, audio_b64)
        """
        results = self.generate_sentences(text)
        
        for item in results:
            await callback(item["sentence"], item["audio"])
