"""
WEB SEARCH SERVICE
==================
Tavily-powered web search for A.D.A
- Fast AI-optimized search
- Query extraction from conversational text
- Source attribution in results
"""

import logging
from typing import Dict, Any, Optional, List

from config_ada import TAVILY_API_KEY

logger = logging.getLogger("ADA")

# Lazy import to avoid error if not installed
_tavily_client = None


def _get_tavily_client():
    global _tavily_client
    if _tavily_client is None:
        if not TAVILY_API_KEY:
            logger.warning("[TAVILY] No API key configured")
            return None
        try:
            from tavily import TavilyClient
            _tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
        except Exception as e:
            logger.error(f"[TAVILY] Failed to initialize: {e}")
            return None
    return _tavily_client


class WebSearchService:
    def __init__(self):
        self.client = _get_tavily_client()
        self.enabled = bool(TAVILY_API_KEY and self.client)
    
    def is_enabled(self) -> bool:
        return self.enabled
    
    def extract_query(self, user_message: str, chat_history: List[tuple] = None) -> str:
        """
        Extract clean search query from conversational text
        Example: "tell me about that website" -> actual topic
        """
        # Simple extraction - use the message as-is for now
        # Can be enhanced with LLM-based extraction
        query = user_message.strip()
        
        # Remove common conversational prefixes
        prefixes = [
            "can you ", "could you ", "please ", "what about ", 
            "tell me about ", "find ", "search for ", "look up "
        ]
        
        for prefix in prefixes:
            if query.lower().startswith(prefix):
                query = query[len(prefix):]
                break
        
        return query.strip()
    
    def search(
        self, 
        query: str, 
        max_results: int = 7,
        include_answer: bool = True
    ) -> Dict[str, Any]:
        """
        Perform web search and return formatted results
        
        Returns:
            {
                "answer": "AI synthesized answer",
                "results": [
                    {"title": "...", "url": "...", "content": "...", "score": 0.9},
                    ...
                ],
                "query": "actual query used"
            }
        """
        if not self.enabled:
            logger.warning("[TAVILY] Search not enabled - no API key")
            return {"answer": "", "results": [], "query": query}
        
        try:
            logger.info(f"[TAVILY] Searching: {query}")
            
            results = self.client.search(
                query=query,
                max_results=max_results,
                include_answer=include_answer,
                include_raw_content=False
            )
            
            formatted_results = {
                "answer": results.get("answer", ""),
                "results": [],
                "query": query
            }
            
            for result in results.get("results", []):
                formatted_results["results"].append({
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "content": result.get("content", "")[:500],  # Truncate
                    "score": result.get("score", 0)
                })
            
            logger.info(f"[TAVILY] Found {len(formatted_results['results'])} results")
            return formatted_results
            
        except Exception as e:
            logger.error(f"[TAVILY] Search error: {e}")
            return {"answer": "", "results": [], "query": query, "error": str(e)}
    
    def format_for_prompt(self, search_results: Dict[str, Any]) -> str:
        """Format search results as context for LLM"""
        parts = []
        
        if search_results.get("answer"):
            parts.append(f"Web Search Answer:\n{search_results['answer']}")
        
        if search_results.get("results"):
            parts.append("\nSources:")
            for i, r in enumerate(search_results["results"][:5], 1):
                parts.append(f"{i}. {r['title']}")
                parts.append(f"   URL: {r['url']}")
                if r.get('content'):
                    parts.append(f"   Content: {r['content'][:200]}...")
        
        return "\n".join(parts)
