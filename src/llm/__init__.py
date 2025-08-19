"""LLM Integration Module.

This module provides a unified interface for multiple LLM providers
with intelligent fallback, cost tracking, and quality validation.
"""

# Expose genai symbol for legacy tests that patch src.llm.genai
try:  # pragma: no cover
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # Will be patched in tests

# Backward compatibility and main exports
from .compat import llm_completion, llm_fallback
from .cost_tracker import CostTracker
from .manager import LLMProviderManager
from .models import LLMContext, LLMProvider, LLMRequest, LLMResponse
from .providers import BedrockProvider, GeminiProvider
from .validator import ResponseValidator

__all__ = [
    "LLMResponse",
    "LLMProvider",
    "LLMRequest",
    "LLMContext",
    "GeminiProvider",
    "BedrockProvider",
    "LLMProviderManager",
    "CostTracker",
    "ResponseValidator",
    "llm_completion",
    "llm_fallback",
    "genai",
]
