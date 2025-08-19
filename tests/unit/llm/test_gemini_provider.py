"""Tests for Gemini provider implementation."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.llm.models import (
    LLMContext,
    LLMProvider,
    LLMProviderError,
    LLMQuotaError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
)
from src.llm.providers.gemini import GeminiProvider


class TestGeminiProvider:
    """Test Gemini provider implementation."""

    def test_provider_initialization(self):
        """Test provider initialization."""
        provider = GeminiProvider()

        assert provider.provider_type == LLMProvider.GEMINI
        assert provider.use_vertex_ai is False
        assert provider.model_name == "gemini-1.5-pro"  # From config default
        assert provider._model is None

    def test_provider_initialization_with_vertex_ai(self):
        """Test provider initialization with Vertex AI."""
        provider = GeminiProvider(use_vertex_ai=True)

        assert provider.use_vertex_ai is True

    @patch("src.llm.providers.gemini.genai")
    def test_configure_client(self, mock_genai):
        """Test client configuration."""
        with patch("src.llm.providers.gemini.settings") as mock_settings:
            mock_settings.google_api_key = "test-key"

            provider = GeminiProvider()
            # Reset mock to test explicit call
            mock_genai.configure.reset_mock()
            provider._configure_client()

            mock_genai.configure.assert_called_once_with(api_key="test-key")

    @patch("src.llm.providers.gemini.genai")
    def test_get_model(self, mock_genai):
        """Test model instance creation."""
        mock_model = Mock()
        mock_genai.GenerativeModel.return_value = mock_model

        provider = GeminiProvider()
        model = provider._get_model()

        assert model == mock_model
        assert provider._model == mock_model
        mock_genai.GenerativeModel.assert_called_once_with(
            model_name="gemini-1.5-pro", safety_settings=provider.SAFETY_SETTINGS
        )

    @pytest.mark.asyncio
    @patch("src.llm.providers.gemini.genai")
    async def test_generate_text_success(self, mock_genai):
        """Test successful text generation."""
        # Mock response
        mock_response = Mock()
        mock_response.text = "Generated text response"

        # Mock model
        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        provider = GeminiProvider()
        request = LLMRequest(
            prompt="Test prompt",
            context=LLMContext.GENERAL,
            max_tokens=500,
            temperature=0.5,
        )

        response = await provider.generate_text(request)

        assert isinstance(response, LLMResponse)
        assert response.text == "Generated text response"
        assert response.provider == LLMProvider.GEMINI
        assert response.context == LLMContext.GENERAL
        assert response.token_count > 0
        assert response.estimated_cost > 0
        assert response.response_time > 0
        assert response.metadata["model"] == "gemini-1.5-pro"
        assert response.metadata["safety_settings"] == "enterprise"

    @pytest.mark.asyncio
    @patch("src.llm.providers.gemini.genai")
    async def test_generate_text_with_system_prompt(self, mock_genai):
        """Test text generation with system prompt."""
        mock_response = Mock()
        mock_response.text = "Generated text response"

        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        provider = GeminiProvider()
        request = LLMRequest(
            prompt="User prompt",
            system_prompt="System context",
            context=LLMContext.SQL_GENERATION,
        )

        response = await provider.generate_text(request)

        # Check that system prompt was included
        call_args = mock_model.generate_content.call_args[0][0]
        assert "System: System context" in call_args
        assert "User: User prompt" in call_args
        assert response.context == LLMContext.SQL_GENERATION

    @pytest.mark.asyncio
    @patch("src.llm.providers.gemini.genai")
    async def test_generate_text_quota_error(self, mock_genai):
        """Test quota error handling."""
        mock_model = Mock()
        mock_model.generate_content.side_effect = Exception("quota exceeded")
        mock_genai.GenerativeModel.return_value = mock_model

        provider = GeminiProvider()
        request = LLMRequest(prompt="Test prompt")

        with pytest.raises(LLMQuotaError) as exc_info:
            await provider.generate_text(request)

        assert "quota" in str(exc_info.value).lower()
        assert exc_info.value.provider == LLMProvider.GEMINI

    @pytest.mark.asyncio
    @patch("src.llm.providers.gemini.genai")
    async def test_generate_text_rate_limit_error(self, mock_genai):
        """Test rate limit error handling."""
        mock_model = Mock()
        mock_model.generate_content.side_effect = Exception("rate limit exceeded")
        mock_genai.GenerativeModel.return_value = mock_model

        provider = GeminiProvider()
        request = LLMRequest(prompt="Test prompt")

        with pytest.raises(LLMRateLimitError) as exc_info:
            await provider.generate_text(request)

        assert "rate" in str(exc_info.value).lower()
        assert exc_info.value.provider == LLMProvider.GEMINI

    @pytest.mark.asyncio
    @patch("src.llm.providers.gemini.genai")
    async def test_generate_text_general_error(self, mock_genai):
        """Test general error handling."""
        mock_model = Mock()
        mock_model.generate_content.side_effect = Exception("network error")
        mock_genai.GenerativeModel.return_value = mock_model

        provider = GeminiProvider()
        request = LLMRequest(prompt="Test prompt")

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.generate_text(request)

        assert "network error" in str(exc_info.value)
        assert exc_info.value.provider == LLMProvider.GEMINI

    def test_estimate_cost(self):
        """Test cost estimation."""
        provider = GeminiProvider()
        request = LLMRequest(
            prompt="Test prompt that is reasonably long", max_tokens=500
        )

        cost = provider.estimate_cost(request)

        assert cost > 0
        assert isinstance(cost, float)

    def test_estimate_cost_with_system_prompt(self):
        """Test cost estimation with system prompt."""
        provider = GeminiProvider()
        request = LLMRequest(
            prompt="Test prompt", system_prompt="System context", max_tokens=500
        )

        cost_with_system = provider.estimate_cost(request)

        request_without_system = LLMRequest(prompt="Test prompt", max_tokens=500)
        cost_without_system = provider.estimate_cost(request_without_system)

        assert cost_with_system > cost_without_system

    def test_get_token_count(self):
        """Test token counting."""
        provider = GeminiProvider()

        # Test various text lengths
        assert provider.get_token_count("") == 1  # Minimum 1 token
        assert provider.get_token_count("test") == 1  # 4 chars = 1 token
        assert provider.get_token_count("test text") == 2  # 9 chars = 2 tokens
        assert provider.get_token_count("a" * 20) == 5  # 20 chars = 5 tokens

    @patch("src.llm.providers.gemini.settings")
    def test_is_available_with_api_key(self, mock_settings):
        """Test availability check with API key."""
        mock_settings.google_api_key = "test-key"

        provider = GeminiProvider()
        assert provider.is_available()

    @patch("src.llm.providers.gemini.settings")
    def test_is_available_without_api_key(self, mock_settings):
        """Test availability check without API key."""
        mock_settings.google_api_key = None

        provider = GeminiProvider()
        assert not provider.is_available()

    def test_get_metrics(self):
        """Test metrics collection."""
        provider = GeminiProvider()
        provider._track_request()

        metrics = provider.get_metrics()

        assert metrics["provider"] == "gemini"
        assert metrics["model_name"] == "gemini-1.5-pro"
        assert metrics["vertex_ai"] is False
        assert metrics["safety_settings"] == "enterprise"
        assert metrics["request_count"] == 1
