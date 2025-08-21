"""Tests for LGDA-014: Strict No-Fabrication On Error Paths.

This module tests the fail-fast behavior that prevents report generation
when errors exist in the pipeline state.
"""

import os
import unittest.mock as mock
from unittest.mock import patch

import pytest

from src.agent.nodes import analyze_df_node, report_node
from src.agent.state import AgentState
from src.config import LGDAConfig


class TestNoFabricationOnError:
    """Test strict no-fabrication policy on error paths."""

    def test_analyze_df_node_fails_fast_on_error_strict_mode(self):
        """analyze_df_node should not generate content when error exists in strict mode."""
        # Setup state with error
        state = AgentState(
            question="test question",
            error="BigQuery execution failed: Table not found",
            df_summary={"rows": 100, "columns": ["col1", "col2"]},
        )

        # Ensure strict mode is enabled
        with patch.dict(os.environ, {"LGDA_STRICT_NO_FAKE_REPORT": "true"}):
            result = analyze_df_node(state)

        # Should not add any analysis content when error exists
        assert result.error == "BigQuery execution failed: Table not found"
        # Should not modify history when in error state
        assert result.history == []

    def test_analyze_df_node_continues_when_strict_mode_disabled(self):
        """analyze_df_node should continue when strict mode is disabled."""
        # Setup state with error
        state = AgentState(
            question="test question",
            error="Some error occurred",
            df_summary={"rows": 50, "columns": ["col1", "col2"]},
        )

        # Disable strict mode
        with patch.dict(os.environ, {"LGDA_STRICT_NO_FAKE_REPORT": "false"}):
            result = analyze_df_node(state)

        # Should generate analysis content despite error when strict mode disabled
        assert result.error == "Some error occurred"
        assert len(result.history) == 1
        assert "Result shape: 50 rows × 2 columns" in result.history[0]["analysis"]

    def test_analyze_df_node_normal_operation_no_error(self):
        """analyze_df_node should work normally when no error exists."""
        # Setup state without error
        state = AgentState(
            question="test question",
            df_summary={"rows": 25, "columns": ["name", "value", "date"]},
        )

        result = analyze_df_node(state)

        # Should generate normal analysis
        assert result.error is None
        assert len(result.history) == 1
        assert "Result shape: 25 rows × 3 columns" in result.history[0]["analysis"]

    def test_report_node_fails_fast_on_error_strict_mode(self):
        """report_node should not generate report when error exists in strict mode."""
        # Setup state with error
        state = AgentState(
            question="What is the revenue?",
            error="SQL validation failed: Invalid table name",
            plan_json={"table": "orders", "metrics": ["revenue"]},
            df_summary={"rows": 0, "columns": []},
        )

        # Ensure strict mode is enabled
        with patch.dict(os.environ, {"LGDA_STRICT_NO_FAKE_REPORT": "true"}):
            result = report_node(state)

        # Should not generate any report content
        assert result.error == "SQL validation failed: Invalid table name"
        assert result.report is None  # Critical: no fabricated report

    def test_report_node_continues_when_strict_mode_disabled(self):
        """report_node should attempt to generate report when strict mode is disabled."""
        # Setup state with error
        state = AgentState(
            question="What is the revenue?",
            error="Some error occurred",
            plan_json={"table": "orders", "metrics": ["revenue"]},
            df_summary={"rows": 0, "columns": []},
        )

        # Mock the LLM completion to avoid external calls
        with patch.dict(os.environ, {"LGDA_STRICT_NO_FAKE_REPORT": "false"}):
            with patch("src.agent.nodes.llm_completion", return_value="Mocked report"):
                result = report_node(state)

        # Should generate report despite error when strict mode disabled
        assert result.error == "Some error occurred"
        assert result.report == "Mocked report"

    def test_report_node_normal_operation_no_error(self):
        """report_node should work normally when no error exists."""
        # Setup state without error
        state = AgentState(
            question="What is the revenue?",
            plan_json={"table": "orders", "metrics": ["revenue"]},
            df_summary={
                "rows": 100,
                "columns": ["revenue"],
                "head": [{"revenue": 1000}],
            },
        )

        # Mock the LLM completion to avoid external calls
        with patch(
            "src.agent.nodes.llm_completion", return_value="Revenue analysis completed"
        ):
            result = report_node(state)

        # Should generate normal report
        assert result.error is None
        assert result.report == "Revenue analysis completed"

    def test_configuration_flag_default_value(self):
        """Test that strict_no_fake_report defaults to True."""
        config = LGDAConfig()
        assert hasattr(config, "strict_no_fake_report")
        assert config.strict_no_fake_report is True

    def test_configuration_flag_can_be_overridden(self):
        """Test that strict_no_fake_report can be configured via environment."""
        with patch.dict(os.environ, {"LGDA_STRICT_NO_FAKE_REPORT": "false"}):
            config = LGDAConfig()
            assert config.strict_no_fake_report is False

        with patch.dict(os.environ, {"LGDA_STRICT_NO_FAKE_REPORT": "true"}):
            config = LGDAConfig()
            assert config.strict_no_fake_report is True


class TestErrorClassificationIntegration:
    """Test integration with error classification for proper fail-fast behavior."""

    def test_different_error_types_all_trigger_fail_fast(self):
        """Different error types should all trigger fail-fast in strict mode."""
        error_scenarios = [
            "SQL validation failed: Forbidden table access",
            "BigQuery execution error: Query timeout",
            "SQL parsing error: Invalid syntax",
            "Table not found: users_private",
        ]

        for error_msg in error_scenarios:
            state = AgentState(
                question="test question",
                error=error_msg,
                df_summary={"rows": 10, "columns": ["col1"]},
            )

            with patch.dict(os.environ, {"LGDA_STRICT_NO_FAKE_REPORT": "true"}):
                analyze_result = analyze_df_node(state)
                report_result = report_node(state)

            # Both nodes should fail-fast
            assert analyze_result.error == error_msg
            assert analyze_result.history == []
            assert report_result.error == error_msg
            assert report_result.report is None


class TestFailFastLogging:
    """Test that fail-fast events are properly logged for observability."""

    @patch("src.agent.nodes.logger")
    def test_analyze_df_logs_fail_fast_marker(self, mock_logger):
        """analyze_df_node should log fail-fast marker when blocking execution."""
        state = AgentState(
            question="test question",
            error="Test error for logging",
            df_summary={"rows": 5, "columns": ["col1"]},
        )

        with patch.dict(os.environ, {"LGDA_STRICT_NO_FAKE_REPORT": "true"}):
            analyze_df_node(state)

        # Should log warning with fail-fast marker
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "fail-fast triggered" in call_args[0][0]
        assert call_args[1]["extra"]["fail_fast"] is True
        assert call_args[1]["extra"]["error_category"] == "PERMANENT"
        assert call_args[1]["extra"]["node"] == "analyze_df"

    @patch("src.agent.nodes.logger")
    def test_report_node_logs_fail_fast_marker(self, mock_logger):
        """report_node should log fail-fast marker when blocking report generation."""
        state = AgentState(
            question="test question",
            error="Test error for logging",
            plan_json={"table": "orders"},
            df_summary={"rows": 5, "columns": ["col1"]},
        )

        with patch.dict(os.environ, {"LGDA_STRICT_NO_FAKE_REPORT": "true"}):
            report_node(state)

        # Should log warning with fail-fast marker and fabrication_prevented flag
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "blocking report generation" in call_args[0][0]
        assert call_args[1]["extra"]["fail_fast"] is True
        assert call_args[1]["extra"]["error_category"] == "USER_GUIDED"
        assert call_args[1]["extra"]["node"] == "report"
        assert call_args[1]["extra"]["fabrication_prevented"] is True
