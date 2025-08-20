"""Core LLM models and interfaces."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    GEMINI = "gemini"
    BEDROCK = "bedrock"
    NVIDIA = "nvidia"


class LLMContext(str, Enum):
    """LLM usage contexts for optimization."""

    PLANNING = "planning"
    SQL_GENERATION = "sql_generation"
    ANALYSIS = "analysis"
    GENERAL = "general"


@dataclass
class LLMRequest:
    """Request data for LLM generation."""

    prompt: str
    context: LLMContext = LLMContext.GENERAL
    max_tokens: int = 1000  # Default; callers can override using PerformanceConfig
    temperature: float = 0.0
    system_prompt: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class LLMResponse(BaseModel):
    """Unified LLM response model."""

    text: str
    provider: LLMProvider
    context: LLMContext
    token_count: int = 0
    estimated_cost: float = 0.0
    response_time: float = 0.0
    quality_score: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """Check if response is empty or whitespace only."""
        return not self.text or self.text.isspace()


class LLMError(Exception):
    """Base exception for LLM operations."""

    def __init__(self, message: str, provider: Optional[LLMProvider] = None):
        super().__init__(message)
        self.provider = provider


class LLMProviderError(LLMError):
    """Provider-specific errors."""

    pass


class LLMRateLimitError(LLMError):
    """Rate limiting errors."""

    pass


class LLMQuotaError(LLMError):
    """Quota/budget exceeded errors."""

    pass


@runtime_checkable
class LLMProviderProtocol(Protocol):
    """Unified interface for all LLM providers."""

    provider_type: LLMProvider

    async def generate_text(self, request: LLMRequest, **kwargs) -> LLMResponse:
        """Generate text using the provider."""
        ...

    def estimate_cost(self, request: LLMRequest) -> float:
        """Estimate cost for the request."""
        ...

    def get_token_count(self, text: str) -> int:
        """Get token count for text."""
        ...

    def is_available(self) -> bool:
        """Check if provider is currently available."""
        ...


class BaseLLMProvider(ABC):
    """Base class for LLM providers."""

    def __init__(self, provider_type: LLMProvider):
        self.provider_type = provider_type
        self._last_request_time = 0.0
        self._request_count = 0

    @abstractmethod
    async def generate_text(self, request: LLMRequest, **kwargs) -> LLMResponse:
        """Generate text using the provider."""
        pass

    @abstractmethod
    def estimate_cost(self, request: LLMRequest) -> float:
        """Estimate cost for the request."""
        pass

    @abstractmethod
    def get_token_count(self, text: str) -> int:
        """Get token count for text."""
        pass

    def is_available(self) -> bool:
        """Check if provider is currently available."""
        return True  # Default implementation

    def _track_request(self) -> None:
        """Track request for metrics."""
        self._last_request_time = time.time()
        self._request_count += 1

    def get_metrics(self) -> Dict[str, Any]:
        """Get provider metrics."""
        return {
            "provider": self.provider_type.value,
            "request_count": self._request_count,
            "last_request_time": self._last_request_time,
        }
