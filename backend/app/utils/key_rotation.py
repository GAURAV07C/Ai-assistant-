"""
KEY ROTATION UTILITY
=====================
Multi-Groq API key rotation
- Brain and chat use different keys
- Automatic fallback on rate limit
- Round-robin across available keys
"""

import threading

# Global counter for rotation
_counter = 0
_counter_lock = threading.Lock()


def get_next_key_pair(num_keys: int, need_brain: bool = False) -> tuple:
    """
    Get next pair of key indices for brain and chat
    
    Args:
        num_keys: Total number of API keys available
        need_brain: If True, return two different keys (brain + chat)
    
    Returns:
        (brain_index, chat_index) - indices into the keys array
    
    Example with 3 keys:
        Request 1: brain=0, chat=1
        Request 2: brain=1, chat=2
        Request 3: brain=2, chat=0
    """
    global _counter
    
    if num_keys == 0:
        return (0, 0)
    
    if num_keys == 1 or not need_brain:
        # Single key or no brain needed - use same key
        with _counter_lock:
            _counter += 1
            idx = _counter % num_keys
            return (idx, idx)
    
    # Multiple keys - brain and chat should differ
    with _counter_lock:
        _counter += 1
        brain_idx = _counter % num_keys
        chat_idx = (brain_idx + 1) % num_keys
        return (brain_idx, chat_idx)


def reset_counter():
    """Reset the rotation counter (useful for testing)"""
    global _counter
    with _counter_lock:
        _counter = 0
