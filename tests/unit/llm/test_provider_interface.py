"""Tests for LLM provider interface and models."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.llm.models import (
    BaseLLMProvider,
    LLMContext,
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
)


class TestLLMModels:
    """Test LLM model classes."""

    def test_llm_request_creation(self):
        """Test LLMRequest creation with defaults."""
        request = LLMRequest(prompt="Test prompt")

        assert request.prompt == "Test prompt"
        assert request.context == LLMContext.GENERAL
        assert request.max_tokens == 4000  # Updated to match unified config default
        assert request.temperature == 0.0
        assert request.system_prompt is None
        assert request.metadata is None

    def test_llm_request_with_parameters(self):
        """Test LLMRequest with custom parameters."""
        request = LLMRequest(
            prompt="Test prompt",
            context=LLMContext.SQL_GENERATION,
            max_tokens=500,
            temperature=0.5,
            system_prompt="System context",
            metadata={"test": "value"},
        )

        assert request.prompt == "Test prompt"
        assert request.context == LLMContext.SQL_GENERATION
        assert request.max_tokens == 500
        assert request.temperature == 0.5
        assert request.system_prompt == "System context"
        assert request.metadata == {"test": "value"}

    def test_llm_response_creation(self):
        """Test LLMResponse creation."""
        response = LLMResponse(
            text="Generated text",
            provider=LLMProvider.GEMINI,
            context=LLMContext.GENERAL,
        )

        assert response.text == "Generated text"
        assert response.provider == LLMProvider.GEMINI
        assert response.context == LLMContext.GENERAL
        assert response.token_count == 0
        assert response.estimated_cost == 0.0
        assert response.response_time == 0.0
        assert response.quality_score is None
        assert response.metadata == {}

    def test_llm_response_is_empty(self):
        """Test empty response detection."""
        empty_response = LLMResponse(
            text="", provider=LLMProvider.GEMINI, context=LLMContext.GENERAL
        )
        assert empty_response.is_empty

        whitespace_response = LLMResponse(
            text="   \n\t  ", provider=LLMProvider.GEMINI, context=LLMContext.GENERAL
        )
        assert whitespace_response.is_empty

        valid_response = LLMResponse(
            text="Valid content",
            provider=LLMProvider.GEMINI,
            context=LLMContext.GENERAL,
        )
        assert not valid_response.is_empty


class MockLLMProvider(BaseLLMProvider):
    """Mock provider for testing."""

    def __init__(self):
        super().__init__(LLMProvider.GEMINI)

    async def generate_text(self, request: LLMRequest, **kwargs) -> LLMResponse:
        return LLMResponse(
            text="Mock response",
            provider=self.provider_type,
            context=request.context,
            token_count=10,
            estimated_cost=0.01,
        )

    def estimate_cost(self, request: LLMRequest) -> float:
        return 0.01

    def get_token_count(self, text: str) -> int:
        return len(text) // 4


class TestBaseLLMProvider:
    """Test base LLM provider functionality."""

    def test_provider_creation(self):
        """Test provider creation."""
        provider = MockLLMProvider()

        assert provider.provider_type == LLMProvider.GEMINI
        assert provider._request_count == 0
        assert provider._last_request_time == 0.0

    @pytest.mark.asyncio
    async def test_provider_generate_text(self):
        """Test provider text generation."""
        provider = MockLLMProvider()
        request = LLMRequest(prompt="Test prompt")

        response = await provider.generate_text(request)

        assert response.text == "Mock response"
        assert response.provider == LLMProvider.GEMINI
        assert response.context == LLMContext.GENERAL
        assert response.token_count == 10
        assert response.estimated_cost == 0.01

    def test_provider_cost_estimation(self):
        """Test cost estimation."""
        provider = MockLLMProvider()
        request = LLMRequest(prompt="Test prompt")

        cost = provider.estimate_cost(request)
        assert cost == 0.01

    def test_provider_token_count(self):
        """Test token counting."""
        provider = MockLLMProvider()

        count = provider.get_token_count("Test text")
        assert count == 2  # 9 chars / 4 = 2

    def test_provider_availability(self):
        """Test provider availability check."""
        provider = MockLLMProvider()
        assert provider.is_available()

    def test_provider_metrics(self):
        """Test provider metrics."""
        provider = MockLLMProvider()
        provider._track_request()

        metrics = provider.get_metrics()

        assert metrics["provider"] == "gemini"
        assert metrics["request_count"] == 1
        assert metrics["last_request_time"] > 0
