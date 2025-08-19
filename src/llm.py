"""Backward compatibility module for existing LLM functions.

This module maintains the original llm_completion and llm_fallback functions
while delegating to the new LLM provider infrastructure.
"""

from __future__ import annotations

from typing import Optional

# Import from new LLM infrastructure
from .llm import llm_completion, llm_fallback

# Re-export for backward compatibility
__all__ = ["llm_completion", "llm_fallback"]
