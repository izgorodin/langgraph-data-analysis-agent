"""Cost tracking for LLM usage."""

from __future__ import annotations

import time
from typing import Dict, Optional

from .models import LLMProvider, LLMRequest


class CostTracker:
    """Tracks LLM costs and enforces budget limits."""
    
    def __init__(self, daily_budget: float = 50.0):
        self.daily_budget = daily_budget
        self.current_spend = 0.0
        self.cost_per_provider: Dict[LLMProvider, float] = {}
        self.request_count: Dict[LLMProvider, int] = {}
        self.last_reset = time.time()
        self._reset_if_needed()
    
    def _reset_if_needed(self) -> None:
        """Reset daily counters if needed."""
        current_time = time.time()
        # Reset if more than 24 hours have passed
        if current_time - self.last_reset > 86400:  # 24 hours in seconds
            self.current_spend = 0.0
            self.cost_per_provider.clear()
            self.request_count.clear()
            self.last_reset = current_time
    
    def can_afford_request(self, provider: LLMProvider, estimated_cost: float) -> bool:
        """Check if request is within budget constraints."""
        self._reset_if_needed()
        return (self.current_spend + estimated_cost) <= self.daily_budget
    
    def track_request_cost(self, provider: LLMProvider, actual_cost: float) -> None:
        """Track actual spending for a request."""
        self._reset_if_needed()
        
        self.current_spend += actual_cost
        self.cost_per_provider[provider] = self.cost_per_provider.get(provider, 0.0) + actual_cost
        self.request_count[provider] = self.request_count.get(provider, 0) + 1
    
    def get_remaining_budget(self) -> float:
        """Get remaining budget for the day."""
        self._reset_if_needed()
        return max(0.0, self.daily_budget - self.current_spend)
    
    def get_cost_breakdown(self) -> Dict[str, float]:
        """Get cost breakdown by provider."""
        self._reset_if_needed()
        return {
            provider.value: cost 
            for provider, cost in self.cost_per_provider.items()
        }
    
    def get_usage_stats(self) -> Dict[str, any]:
        """Get comprehensive usage statistics."""
        self._reset_if_needed()
        return {
            "daily_budget": self.daily_budget,
            "current_spend": self.current_spend,
            "remaining_budget": self.get_remaining_budget(),
            "budget_utilization": (self.current_spend / self.daily_budget) * 100,
            "cost_by_provider": self.get_cost_breakdown(),
            "requests_by_provider": {
                provider.value: count 
                for provider, count in self.request_count.items()
            },
            "last_reset": self.last_reset,
        }
    
    def is_budget_exceeded(self) -> bool:
        """Check if budget is exceeded."""
        self._reset_if_needed()
        return self.current_spend >= self.daily_budget
    
    def get_cost_efficiency(self, provider: LLMProvider) -> Optional[float]:
        """Get cost per request for a provider."""
        self._reset_if_needed()
        
        if provider not in self.request_count or self.request_count[provider] == 0:
            return None
        
        total_cost = self.cost_per_provider.get(provider, 0.0)
        request_count = self.request_count[provider]
        
        return total_cost / request_count