"""Backward compatibility module for existing LLM functions.

This module maintains the original llm_completion and llm_fallback functions
while delegating to the new LLM provider infrastructure.
"""

from __future__ import annotations

# Expose underlying client for legacy tests that patch src.llm.genai
try:  # pragma: no cover
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # Will be patched in tests

# Import from new LLM infrastructure
from .llm import llm_completion, llm_fallback

# Re-export for backward compatibility
__all__ = ["llm_completion", "llm_fallback"]
