"""Backward compatibility layer for existing LLM functions."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .models import LLMContext, LLMRequest
from .manager import get_default_manager

logger = logging.getLogger(__name__)


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
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, we need to create a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, manager.generate_with_fallback(request))
                    response = future.result()
            else:
                response = loop.run_until_complete(
                    manager.generate_with_fallback(request)
                )
        except RuntimeError:
            # Create new event loop if none exists
            response = asyncio.run(manager.generate_with_fallback(request))
        
        return response.text
    except Exception as e:
        logger.warning(f"LLM completion failed: {e}")
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
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, manager.generate_with_fallback_only(request))
                    response = future.result()
            else:
                response = loop.run_until_complete(
                    manager.generate_with_fallback_only(request)
                )
        except RuntimeError:
            response = asyncio.run(manager.generate_with_fallback_only(request))
        
        return response.text
    except Exception as e:
        logger.warning(f"LLM fallback failed: {e}")
        return ""