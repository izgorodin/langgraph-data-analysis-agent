"""Test plan validation functionality - TDD approach for LGDA-101."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agent.nodes import validate_plan_json
from src.agent.state import AgentState


class TestPlanValidation:
    """Test cases for plan validation - written first per TDD approach."""

    def test_valid_plan_passes_validation(self):
        """Happy path: valid plan should pass validation."""
        valid_plan = {
            "task": "Calculate cohort LTV analysis",
            "tables": ["orders", "order_items", "users"],
            "cohort_spec": {"date_column": "created_at", "cohort_period": "month"},
            "date_range": {"start": "2022-01-01", "end": "2023-12-31"},
            "metrics": ["SUM(sale_price)", "COUNT(DISTINCT user_id)"],
        }

        state = AgentState(question="Test question")
        result = validate_plan_json(valid_plan, state)

        assert result.is_valid is True
        assert result.error is None
        assert result.missing_fields == []

    def test_empty_plan_fails_validation(self):
        """Empty plan should fail with descriptive error."""
        empty_plan = {}

        state = AgentState(question="Test question")
        result = validate_plan_json(empty_plan, state)

        assert result.is_valid is False
        assert "required field" in result.error.lower()
        assert "task" in result.missing_fields

    def test_malformed_json_fails_validation(self):
        """Malformed JSON (None) should fail validation."""
        state = AgentState(question="Test question")
        result = validate_plan_json(None, state)

        assert result.is_valid is False
        assert "invalid plan" in result.error.lower()

    def test_plan_without_required_fields_fails(self):
        """Plan missing critical fields should fail validation."""
        incomplete_plan = {
            "task": "Some task"
            # missing tables, date_range, cohort_spec
        }

        state = AgentState(question="Test question")
        result = validate_plan_json(incomplete_plan, state)

        assert result.is_valid is False
        assert "tables" in result.missing_fields
        assert "date_range" in result.missing_fields

    def test_plan_with_invalid_tables_fails(self):
        """Plan with forbidden tables should fail validation."""
        invalid_plan = {
            "task": "Test task",
            "tables": ["orders", "forbidden_table"],
            "date_range": {"start": "2022-01-01", "end": "2023-12-31"},
        }

        state = AgentState(question="Test question")
        result = validate_plan_json(invalid_plan, state)

        assert result.is_valid is False
        assert "forbidden_table" in result.error

    def test_plan_without_cohort_spec_for_ltv_fails(self):
        """LTV-related questions should require cohort_spec."""
        plan_without_cohort = {
            "task": "Calculate LTV analysis",
            "tables": ["orders", "users"],
            "date_range": {"start": "2022-01-01", "end": "2023-12-31"},
            # missing cohort_spec for LTV question
        }

        state = AgentState(question="customer lifetime value analysis")
        result = validate_plan_json(plan_without_cohort, state)

        assert result.is_valid is False
        assert "cohort_spec" in result.missing_fields

    def test_plan_with_generic_task_fails(self):
        """Plans with generic 'ad-hoc' task should fail."""
        generic_plan = {
            "task": "ad-hoc",  # too generic
            "tables": ["orders"],
            "date_range": {"start": "2022-01-01", "end": "2023-12-31"},
        }

        state = AgentState(question="Test question")
        result = validate_plan_json(generic_plan, state)

        assert result.is_valid is False
        assert "ad-hoc" in result.error.lower()

    def test_raw_llm_output_logging(self):
        """Test that raw LLM output is logged for debugging."""
        state = AgentState(question="Test question")
        state.history = []

        # Mock LLM returning empty response
        with patch("src.agent.nodes.llm_completion", return_value=""):
            from src.agent.nodes import plan_node

            result_state = plan_node(state)

        # Check that raw output was logged
        raw_logs = [
            h
            for h in result_state.history
            if h.get("note") == "plan_raw_llm_output_initial"
        ]
        assert len(raw_logs) >= 1
