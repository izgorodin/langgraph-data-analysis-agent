"""Backward compatibility layer for existing LLM functions."""

from __future__ import annotations

import asyncio
from typing import Optional

from .models import LLMContext, LLMRequest
from .manager import get_default_manager


def llm_completion(
    prompt: str, 
    system: Optional[str] = None, 
    model: Optional[str] = None
) -> str:
    """
    Backward-compatible llm_completion function.
    
    Maintains the same signature as the original implementation
    while using the new LLM provider infrastructure underneath.
    """
    # Create request with backward-compatible defaults
    request = LLMRequest(
        prompt=prompt,
        context=LLMContext.GENERAL,
        system_prompt=system,
        max_tokens=1000,
        temperature=0.0,
        metadata={"model": model} if model else None
    )
    
    # Get the default manager and execute synchronously
    manager = get_default_manager()
    
    try:
        # Run async function in sync context
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # Create new event loop if none exists
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        response = loop.run_until_complete(
            manager.generate_with_fallback(request)
        )
        return response.text
    except Exception:
        # Fallback to empty string for backward compatibility
        return ""


def llm_fallback(prompt: str, system: Optional[str] = None) -> str:
    """
    Backward-compatible llm_fallback function.
    
    Forces use of fallback provider if available.
    """
    request = LLMRequest(
        prompt=prompt,
        context=LLMContext.GENERAL,
        system_prompt=system,
        max_tokens=1000,
        temperature=0.0
    )
    
    manager = get_default_manager()
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        # Force fallback provider usage
        response = loop.run_until_complete(
            manager.generate_with_fallback_only(request)
        )
        return response.text
    except Exception:
        return ""