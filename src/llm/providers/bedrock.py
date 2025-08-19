"""AWS Bedrock provider implementation."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from ...config import settings
from ..models import (
    BaseLLMProvider,
    LLMProvider,
    LLMProviderError,
    LLMQuotaError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
)


class BedrockProvider(BaseLLMProvider):
    """AWS Bedrock provider implementation."""

    # Claude model configurations
    CLAUDE_MODELS = {
        "fast": "anthropic.claude-3-haiku-20240307-v1:0",
        "balanced": "anthropic.claude-3-sonnet-20240229-v1:0",
        "best": "anthropic.claude-3-opus-20240229-v1:0",
    }

    # Token cost estimates (per 1K tokens) for Claude-3
    TOKEN_COSTS = {
        "haiku": {"input": 0.00025, "output": 0.00125},
        "sonnet": {"input": 0.003, "output": 0.015},
        "opus": {"input": 0.015, "output": 0.075},
    }

    def __init__(self, model_tier: str = "balanced"):
        super().__init__(LLMProvider.BEDROCK)
        self.model_tier = model_tier
        self.model_id = self.CLAUDE_MODELS[model_tier]
        self._client = None
        self._configure_client()

    def _configure_client(self) -> None:
        """Configure Bedrock client."""
        try:
            import boto3

            self._client = boto3.client(
                "bedrock-runtime", region_name=settings.aws_region or "us-east-1"
            )
        except ImportError:
            # boto3 not available
            self._client = None
        except Exception:
            # AWS credentials not configured
            self._client = None

    async def generate_text(self, request: LLMRequest, **kwargs) -> LLMResponse:
        """Generate text using Bedrock Claude."""
        if not self._client:
            raise LLMProviderError("Bedrock client not available", self.provider_type)

        start_time = time.time()
        self._track_request()

        try:
            # Prepare Claude-specific prompt format
            if request.system_prompt:
                prompt = f"System: {request.system_prompt}\n\nHuman: {request.prompt}\n\nAssistant:"
            else:
                prompt = f"Human: {request.prompt}\n\nAssistant:"

            # Prepare request body for Claude
            body = {
                "prompt": prompt,
                "max_tokens_to_sample": request.max_tokens,
                "temperature": request.temperature,
                "stop_sequences": ["\n\nHuman:"],
            }

            # Make API call
            import json

            response = self._client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )

            # Parse response
            response_body = json.loads(response["body"].read())
            text = response_body.get("completion", "").strip()

            response_time = time.time() - start_time

            # Calculate metrics
            token_count = self.get_token_count(prompt + text)
            estimated_cost = self.estimate_cost(request)

            return LLMResponse(
                text=text,
                provider=self.provider_type,
                context=request.context,
                token_count=token_count,
                estimated_cost=estimated_cost,
                response_time=response_time,
                metadata={
                    "model_id": self.model_id,
                    "model_tier": self.model_tier,
                    "aws_region": settings.aws_region,
                    **kwargs,
                },
            )

        except Exception as e:
            # Map exceptions to appropriate LLM errors
            error_msg = str(e).lower()

            if "throttling" in error_msg or "quota" in error_msg:
                raise LLMQuotaError(f"Bedrock quota exceeded: {e}", self.provider_type)
            elif "rate" in error_msg or "limit" in error_msg:
                raise LLMRateLimitError(f"Bedrock rate limit: {e}", self.provider_type)
            else:
                raise LLMProviderError(f"Bedrock error: {e}", self.provider_type)

    def estimate_cost(self, request: LLMRequest) -> float:
        """Estimate cost for the request."""
        # Get cost model based on tier
        tier_key = (
            self.model_tier.replace("balanced", "sonnet")
            .replace("best", "opus")
            .replace("fast", "haiku")
        )
        costs = self.TOKEN_COSTS.get(tier_key, self.TOKEN_COSTS["sonnet"])

        # Estimate input tokens
        input_tokens = self.get_token_count(request.prompt)
        if request.system_prompt:
            input_tokens += self.get_token_count(request.system_prompt)

        # Estimate output tokens
        output_tokens = min(request.max_tokens, 1000)

        # Calculate cost
        input_cost = (input_tokens / 1000) * costs["input"]
        output_cost = (output_tokens / 1000) * costs["output"]

        return input_cost + output_cost

    def get_token_count(self, text: str) -> int:
        """Get token count for text."""
        # Claude tokenization is similar to GPT - roughly 4 chars per token
        return max(1, len(text) // 4)

    def is_available(self) -> bool:
        """Check if Bedrock is available."""
        try:
            if not self._client:
                return False

            # Could add more sophisticated health checks here
            # For now, just check if client exists
            return True

        except Exception:
            return False

    def get_metrics(self) -> Dict[str, Any]:
        """Get provider-specific metrics."""
        base_metrics = super().get_metrics()
        return {
            **base_metrics,
            "model_id": self.model_id,
            "model_tier": self.model_tier,
            "aws_region": settings.aws_region,
            "client_available": self._client is not None,
        }
