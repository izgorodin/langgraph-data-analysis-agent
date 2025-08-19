"""LLM Integration Module.

This module provides a unified interface for multiple LLM providers
with intelligent fallback, cost tracking, and quality validation.
"""

from .models import LLMResponse, LLMProvider, LLMRequest
from .providers import GeminiProvider, BedrockProvider  
from .manager import LLMProviderManager
from .cost_tracker import CostTracker
from .validator import ResponseValidator

# Backward compatibility
from .compat import llm_completion, llm_fallback

__all__ = [
    "LLMResponse",
    "LLMProvider", 
    "LLMRequest",
    "GeminiProvider",
    "BedrockProvider",
    "LLMProviderManager",
    "CostTracker",
    "ResponseValidator",
    "llm_completion",
    "llm_fallback",
]