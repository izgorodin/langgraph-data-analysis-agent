"""LLM Provider Manager with intelligent fallback logic."""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from .cost_tracker import CostTracker
from .models import (
    LLMError,
    LLMProvider,
    LLMProviderError,
    LLMQuotaError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
)
from .providers import BedrockProvider, GeminiProvider
from .validator import ResponseValidator


class CircuitBreaker:
    """Circuit breaker for provider health management."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 300.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "closed"  # closed, open, half-open
    
    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        if self.state == "closed":
            return True
        elif self.state == "open":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half-open"
                return True
            return False
        else:  # half-open
            return True
    
    def record_success(self) -> None:
        """Record successful execution."""
        self.failure_count = 0
        self.state = "closed"
    
    def record_failure(self) -> None:
        """Record failed execution."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"


class LLMProviderManager:
    """Manages multiple LLM providers with intelligent fallback."""
    
    def __init__(
        self,
        primary_provider: Optional[GeminiProvider] = None,
        fallback_provider: Optional[BedrockProvider] = None,
        cost_tracker: Optional[CostTracker] = None,
        validator: Optional[ResponseValidator] = None
    ):
        self.primary = primary_provider or GeminiProvider()
        self.fallback = fallback_provider or BedrockProvider()
        self.cost_tracker = cost_tracker or CostTracker()
        self.validator = validator or ResponseValidator()
        
        # Circuit breakers for each provider
        self.primary_circuit = CircuitBreaker()
        self.fallback_circuit = CircuitBreaker()
        
        self._metrics = {
            "requests_total": 0,
            "requests_primary": 0,
            "requests_fallback": 0,
            "failures_primary": 0,
            "failures_fallback": 0,
            "cost_saved_by_fallback": 0.0,
        }
    
    async def generate_with_fallback(self, request: LLMRequest) -> LLMResponse:
        """
        Generate text with intelligent fallback logic.
        
        Smart provider selection:
        1. Check circuit breaker state
        2. Evaluate cost constraints  
        3. Try primary provider
        4. Fallback if needed
        5. Update metrics
        """
        self._metrics["requests_total"] += 1
        
        # Check budget constraints
        primary_cost = self.primary.estimate_cost(request)
        fallback_cost = self.fallback.estimate_cost(request)
        
        if not self.cost_tracker.can_afford_request(self.primary.provider_type, primary_cost):
            if self.cost_tracker.can_afford_request(self.fallback.provider_type, fallback_cost):
                # Use fallback due to budget constraints
                return await self._try_fallback_provider(request, reason="budget")
            else:
                raise LLMQuotaError("Insufficient budget for request")
        
        # Try primary provider first
        if self.primary_circuit.can_execute() and self.primary.is_available():
            try:
                response = await self._try_primary_provider(request)
                self.primary_circuit.record_success()
                return response
            except (LLMRateLimitError, LLMQuotaError) as e:
                # Immediately try fallback for rate limits and quota
                self.primary_circuit.record_failure()
                return await self._try_fallback_provider(request, reason=str(e))
            except LLMProviderError as e:
                # Record failure and try fallback
                self.primary_circuit.record_failure()
                self._metrics["failures_primary"] += 1
                return await self._try_fallback_provider(request, reason=str(e))
        
        # Primary not available, try fallback
        return await self._try_fallback_provider(request, reason="primary_unavailable")
    
    async def generate_with_fallback_only(self, request: LLMRequest) -> LLMResponse:
        """Force use of fallback provider only."""
        return await self._try_fallback_provider(request, reason="forced_fallback")
    
    async def _try_primary_provider(self, request: LLMRequest) -> LLMResponse:
        """Try primary provider."""
        self._metrics["requests_primary"] += 1
        
        # Check cost before proceeding
        estimated_cost = self.primary.estimate_cost(request)
        if not self.cost_tracker.can_afford_request(self.primary.provider_type, estimated_cost):
            raise LLMQuotaError("Insufficient budget for primary provider")
        
        response = await self.primary.generate_text(request)
        
        # Validate response
        validation = self.validator.validate_response(response, context=str(request.context))
        if not validation.is_valid:
            raise LLMProviderError(f"Response validation failed: {validation.issues}")
        
        response.quality_score = validation.quality_score
        
        # Track actual cost
        self.cost_tracker.track_request_cost(self.primary.provider_type, response.estimated_cost)
        
        return response
    
    async def _try_fallback_provider(self, request: LLMRequest, reason: str) -> LLMResponse:
        """Try fallback provider."""
        if not self.fallback_circuit.can_execute() or not self.fallback.is_available():
            raise LLMProviderError("Fallback provider unavailable")
        
        self._metrics["requests_fallback"] += 1
        
        try:
            # Check cost for fallback
            estimated_cost = self.fallback.estimate_cost(request)
            if not self.cost_tracker.can_afford_request(self.fallback.provider_type, estimated_cost):
                raise LLMQuotaError("Insufficient budget for fallback provider")
            
            response = await self.fallback.generate_text(request)
            
            # Validate response
            validation = self.validator.validate_response(response, context=str(request.context))
            if not validation.is_valid:
                raise LLMProviderError(f"Fallback response validation failed: {validation.issues}")
            
            response.quality_score = validation.quality_score
            response.metadata["fallback_reason"] = reason
            
            # Track cost savings
            primary_cost = self.primary.estimate_cost(request)
            cost_saved = max(0, primary_cost - response.estimated_cost)
            self._metrics["cost_saved_by_fallback"] += cost_saved
            
            # Track actual cost
            self.cost_tracker.track_request_cost(self.fallback.provider_type, response.estimated_cost)
            
            self.fallback_circuit.record_success()
            return response
            
        except Exception as e:
            self.fallback_circuit.record_failure()
            self._metrics["failures_fallback"] += 1
            
            if isinstance(e, LLMError):
                raise
            else:
                raise LLMProviderError(f"Fallback provider failed: {e}")
    
    def get_provider_health(self) -> dict:
        """Get health status of providers."""
        return {
            "primary": {
                "available": self.primary.is_available(),
                "circuit_state": self.primary_circuit.state,
                "failure_count": self.primary_circuit.failure_count,
                "provider_type": self.primary.provider_type.value,
            },
            "fallback": {
                "available": self.fallback.is_available(),
                "circuit_state": self.fallback_circuit.state,
                "failure_count": self.fallback_circuit.failure_count,
                "provider_type": self.fallback.provider_type.value,
            }
        }
    
    def get_metrics(self) -> dict:
        """Get comprehensive metrics."""
        return {
            **self._metrics,
            "cost_tracker": self.cost_tracker.get_usage_stats(),
            "provider_health": self.get_provider_health(),
            "primary_metrics": self.primary.get_metrics(),
            "fallback_metrics": self.fallback.get_metrics(),
        }
    
    def reset_circuit_breakers(self) -> None:
        """Reset circuit breakers (for recovery testing)."""
        self.primary_circuit = CircuitBreaker()
        self.fallback_circuit = CircuitBreaker()


# Global default manager instance
_default_manager: Optional[LLMProviderManager] = None


def get_default_manager() -> LLMProviderManager:
    """Get or create the default LLM provider manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = LLMProviderManager()
    return _default_manager


def set_default_manager(manager: LLMProviderManager) -> None:
    """Set the default LLM provider manager."""
    global _default_manager
    _default_manager = manager