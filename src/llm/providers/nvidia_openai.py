"""NVIDIA OpenAI-compatible provider implementation (chat.completions API)."""

from __future__ import annotations

import time

try:  # pragma: no cover - optional dependency
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # mocked in tests or optional

import os

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


class NvidiaOpenAIProvider(BaseLLMProvider):
    """Provider using OpenAI-compatible chat.completions endpoint (NVIDIA)."""

    # rough token cost placeholder; can be tuned per model
    TOKEN_COSTS = {"default": {"input": 0.0, "output": 0.0}}

    def __init__(self):
        super().__init__(LLMProvider("nvidia"))
        # Read from env to avoid coupling tests to presence of extra fields
        self.base_url = os.getenv(
            "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
        )
        self.api_key = os.getenv("NVIDIA_API_KEY", "")
        self.model_name = os.getenv("NVIDIA_MODEL", "openai/gpt-oss-120b")
        self._client = None
        self._configure()

    def _configure(self) -> None:
        if OpenAI is not None:
            try:
                self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
            except Exception:
                self._client = None

    async def generate_text(self, request: LLMRequest, **kwargs) -> LLMResponse:
        if self._client is None:
            raise LLMProviderError(
                "NVIDIA OpenAI client not available", self.provider_type
            )

        start = time.time()
        self._track_request()

        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        try:
            completion = self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=False,
            )

            # Extract text similarly to OpenAI responses
            text = ""
            try:
                if getattr(completion, "choices", None):
                    text = completion.choices[0].message.content or ""
            except Exception:
                # Fallback for slightly different response shapes
                text = getattr(completion, "text", "") or ""

            elapsed = time.time() - start
            token_count = self.get_token_count(
                (request.system_prompt or "") + request.prompt + text
            )
            estimated_cost = self.estimate_cost(request)

            return LLMResponse(
                text=text,
                provider=self.provider_type,
                context=request.context,
                token_count=token_count,
                estimated_cost=estimated_cost,
                response_time=elapsed,
                metadata={
                    "model": self.model_name,
                    "base_url": self.base_url,
                    **kwargs,
                },
            )
        except Exception as e:  # Map common error categories
            msg = str(e).lower()
            if "rate" in msg or "limit" in msg:
                raise LLMRateLimitError(f"NVIDIA rate limit: {e}", self.provider_type)
            if "quota" in msg or "billing" in msg:
                raise LLMQuotaError(f"NVIDIA quota: {e}", self.provider_type)
            raise LLMProviderError(f"NVIDIA error: {e}", self.provider_type)

    def estimate_cost(self, request: LLMRequest) -> float:
        costs = self.TOKEN_COSTS["default"]
        input_tokens = self.get_token_count(
            (request.system_prompt or "") + request.prompt
        )
        output_tokens = min(request.max_tokens, 1000)
        return (input_tokens / 1000) * costs["input"] + (output_tokens / 1000) * costs[
            "output"
        ]

    def get_token_count(self, text: str) -> int:
        return max(1, len(text) // 4)

    def is_available(self) -> bool:
        return bool(self.api_key and self.base_url)
