"""Tests for cost tracking functionality."""

import time
from unittest.mock import patch

import pytest

from src.llm.cost_tracker import CostTracker
from src.llm.models import LLMContext, LLMProvider, LLMRequest


class TestCostTracker:
    """Test cost tracking functionality."""

    def test_cost_tracker_initialization(self):
        """Test cost tracker initialization with defaults."""
        tracker = CostTracker()

        assert tracker.daily_budget == 50.0
        assert tracker.current_spend == 0.0
        assert tracker.cost_per_provider == {}
        assert tracker.request_count == {}
        assert tracker.last_reset > 0

    def test_cost_tracker_custom_budget(self):
        """Test cost tracker with custom budget."""
        tracker = CostTracker(daily_budget=100.0)

        assert tracker.daily_budget == 100.0
        assert tracker.get_remaining_budget() == 100.0

    def test_can_afford_request_within_budget(self):
        """Test request affordability within budget."""
        tracker = CostTracker(daily_budget=10.0)

        assert tracker.can_afford_request(LLMProvider.GEMINI, 5.0)
        assert tracker.can_afford_request(LLMProvider.BEDROCK, 9.99)

    def test_can_afford_request_exceeds_budget(self):
        """Test request affordability exceeding budget."""
        tracker = CostTracker(daily_budget=10.0)

        assert not tracker.can_afford_request(LLMProvider.GEMINI, 15.0)
        assert not tracker.can_afford_request(LLMProvider.BEDROCK, 10.01)

    def test_track_request_cost(self):
        """Test tracking request costs."""
        tracker = CostTracker(daily_budget=50.0)

        tracker.track_request_cost(LLMProvider.GEMINI, 2.5)
        tracker.track_request_cost(LLMProvider.BEDROCK, 1.5)
        tracker.track_request_cost(LLMProvider.GEMINI, 3.0)

        assert tracker.current_spend == 7.0
        assert tracker.cost_per_provider[LLMProvider.GEMINI] == 5.5
        assert tracker.cost_per_provider[LLMProvider.BEDROCK] == 1.5
        assert tracker.request_count[LLMProvider.GEMINI] == 2
        assert tracker.request_count[LLMProvider.BEDROCK] == 1

    def test_get_remaining_budget(self):
        """Test remaining budget calculation."""
        tracker = CostTracker(daily_budget=20.0)

        assert tracker.get_remaining_budget() == 20.0

        tracker.track_request_cost(LLMProvider.GEMINI, 7.5)
        assert tracker.get_remaining_budget() == 12.5

        tracker.track_request_cost(LLMProvider.BEDROCK, 5.0)
        assert tracker.get_remaining_budget() == 7.5

    def test_get_cost_breakdown(self):
        """Test cost breakdown by provider."""
        tracker = CostTracker()

        tracker.track_request_cost(LLMProvider.GEMINI, 10.0)
        tracker.track_request_cost(LLMProvider.BEDROCK, 5.0)
        tracker.track_request_cost(LLMProvider.GEMINI, 3.0)

        breakdown = tracker.get_cost_breakdown()

        assert breakdown == {"gemini": 13.0, "bedrock": 5.0}

    def test_get_usage_stats(self):
        """Test comprehensive usage statistics."""
        tracker = CostTracker(daily_budget=25.0)

        tracker.track_request_cost(LLMProvider.GEMINI, 10.0)
        tracker.track_request_cost(LLMProvider.BEDROCK, 5.0)

        stats = tracker.get_usage_stats()

        assert stats["daily_budget"] == 25.0
        assert stats["current_spend"] == 15.0
        assert stats["remaining_budget"] == 10.0
        assert stats["budget_utilization"] == 60.0
        assert stats["cost_by_provider"]["gemini"] == 10.0
        assert stats["cost_by_provider"]["bedrock"] == 5.0
        assert stats["requests_by_provider"]["gemini"] == 1
        assert stats["requests_by_provider"]["bedrock"] == 1
        assert stats["last_reset"] > 0

    def test_is_budget_exceeded(self):
        """Test budget exceeded detection."""
        tracker = CostTracker(daily_budget=10.0)

        assert not tracker.is_budget_exceeded()

        tracker.track_request_cost(LLMProvider.GEMINI, 5.0)
        assert not tracker.is_budget_exceeded()

        tracker.track_request_cost(LLMProvider.BEDROCK, 5.0)
        assert tracker.is_budget_exceeded()

        tracker.track_request_cost(LLMProvider.GEMINI, 1.0)
        assert tracker.is_budget_exceeded()

    def test_get_cost_efficiency(self):
        """Test cost efficiency calculation."""
        tracker = CostTracker()

        # No requests yet
        assert tracker.get_cost_efficiency(LLMProvider.GEMINI) is None

        # Single request
        tracker.track_request_cost(LLMProvider.GEMINI, 5.0)
        assert tracker.get_cost_efficiency(LLMProvider.GEMINI) == 5.0

        # Multiple requests
        tracker.track_request_cost(LLMProvider.GEMINI, 3.0)
        assert tracker.get_cost_efficiency(LLMProvider.GEMINI) == 4.0  # (5+3)/2

        # Different provider
        tracker.track_request_cost(LLMProvider.BEDROCK, 2.0)
        assert tracker.get_cost_efficiency(LLMProvider.BEDROCK) == 2.0

    @patch("time.time")
    def test_daily_reset(self, mock_time):
        """Test daily reset functionality."""
        # Start at timestamp 0
        mock_time.return_value = 0
        tracker = CostTracker(daily_budget=50.0)

        # Add some spending
        tracker.track_request_cost(LLMProvider.GEMINI, 25.0)
        assert tracker.current_spend == 25.0

        # Move time forward 24+ hours (86400+ seconds)
        mock_time.return_value = 86401

        # Reset should happen automatically on next call
        tracker._reset_if_needed()

        assert tracker.current_spend == 0.0
        assert tracker.cost_per_provider == {}
        assert tracker.request_count == {}
        assert tracker.last_reset == 86401

    def test_can_afford_with_accumulated_costs(self):
        """Test affordability check with accumulated costs."""
        tracker = CostTracker(daily_budget=10.0)

        # Spend most of budget
        tracker.track_request_cost(LLMProvider.GEMINI, 8.0)

        # Should be able to afford small request
        assert tracker.can_afford_request(LLMProvider.BEDROCK, 1.5)

        # Should not be able to afford large request
        assert not tracker.can_afford_request(LLMProvider.BEDROCK, 3.0)
