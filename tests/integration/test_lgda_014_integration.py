"""Integration tests for LGDA-014: Strict No-Fabrication On Error Paths.

Tests the complete pipeline behavior to ensure no fabricated reports
are generated when errors occur in validate_sql/execute_sql/analyze_df stages.
"""

import os
from unittest.mock import patch

import pytest

from src.agent.nodes import analyze_df_node, report_node
from src.agent.state import AgentState


class TestIntegrationNoFabricationOnError:
    """Integration tests for strict no-fabrication policy."""

    def test_analyze_and_report_nodes_chain_with_error(self):
        """Test that analyze_df and report nodes both fail-fast when error exists."""
        # Setup state with error (simulating failed execute_sql)
        state = AgentState(
            question="What is the total revenue?",
            error="BigQuery execution error: Query timeout after 30 seconds",
            sql="SELECT SUM(revenue) FROM orders",
            plan_json={"table": "orders", "metrics": ["revenue"]},
        )

        with patch.dict(os.environ, {"LGDA_STRICT_NO_FAKE_REPORT": "true"}):
            # Process through analyze_df_node
            state_after_analyze = analyze_df_node(state)

            # Process through report_node
            final_state = report_node(state_after_analyze)

        # Both nodes should fail-fast and not generate content
        assert (
            final_state.error
            == "BigQuery execution error: Query timeout after 30 seconds"
        )
        assert final_state.history == []  # No analysis generated
        assert final_state.report is None  # No report generated

    def test_normal_flow_without_error(self):
        """Test normal processing when no error exists."""
        # Setup state without error
        state = AgentState(
            question="What is the total revenue?",
            sql="SELECT SUM(revenue) FROM orders",
            plan_json={"table": "orders", "metrics": ["revenue"]},
            df_summary={
                "rows": 1,
                "columns": ["total_revenue"],
                "head": [{"total_revenue": 50000}],
            },
        )

        with patch(
            "src.agent.nodes.llm_completion", return_value="Total revenue is $50,000"
        ):
            # Process through analyze_df_node
            state_after_analyze = analyze_df_node(state)

            # Process through report_node
            final_state = report_node(state_after_analyze)

        # Should process normally and generate content
        assert final_state.error is None
        assert len(final_state.history) == 1  # Analysis was generated
        assert "Result shape: 1 rows × 1 columns" in final_state.history[0]["analysis"]
        assert final_state.report == "Total revenue is $50,000"

    def test_error_types_all_trigger_fail_fast(self):
        """Test different error types all trigger fail-fast behavior."""
        error_scenarios = [
            ("SQL validation failed: Forbidden table access", "validation_error"),
            ("BigQuery execution error: Permission denied", "execution_error"),
            ("Query timeout: Operation exceeded 30 seconds", "timeout_error"),
        ]

        for error_message, error_type in error_scenarios:
            state = AgentState(
                question="test question",
                error=error_message,
                df_summary={"rows": 10, "columns": ["col1"]},
            )

            with patch.dict(os.environ, {"LGDA_STRICT_NO_FAKE_REPORT": "true"}):
                analyze_result = analyze_df_node(state)
                report_result = report_node(analyze_result)

            # Both should maintain error and not generate content
            assert analyze_result.error == error_message, f"Failed for {error_type}"
            assert analyze_result.history == [], f"Analysis generated for {error_type}"
            assert report_result.error == error_message, f"Failed for {error_type}"
            assert report_result.report is None, f"Report generated for {error_type}"

    def test_strict_mode_configuration_behavior(self):
        """Test behavior difference between strict mode enabled and disabled."""
        state_with_error = AgentState(
            question="test question",
            error="Test error for configuration test",
            df_summary={"rows": 5, "columns": ["col1"]},
            plan_json={"table": "orders"},
        )

        # Test with strict mode enabled (default)
        with patch.dict(os.environ, {"LGDA_STRICT_NO_FAKE_REPORT": "true"}):
            strict_result = report_node(state_with_error.model_copy())

        # Test with strict mode disabled
        with patch.dict(os.environ, {"LGDA_STRICT_NO_FAKE_REPORT": "false"}):
            with patch(
                "src.agent.nodes.llm_completion",
                return_value="Test report despite error",
            ):
                permissive_result = report_node(state_with_error.model_copy())

        # Strict mode should not generate report
        assert strict_result.report is None

        # Permissive mode should generate report
        assert permissive_result.report == "Test report despite error"


class TestFailFastObservability:
    """Test observability and logging of fail-fast events."""

    @patch("src.agent.nodes.logger")
    def test_fail_fast_events_are_logged(self, mock_logger):
        """Test that fail-fast events generate proper log entries for monitoring."""
        # Setup state with error
        state = AgentState(
            question="test question",
            error="BigQuery execution failed",
            df_summary={"rows": 10, "columns": ["col1"]},
        )

        with patch.dict(os.environ, {"LGDA_STRICT_NO_FAKE_REPORT": "true"}):
            # Trigger both nodes
            analyze_df_node(state)
            report_node(state)

        # Should have logged fail-fast events
        assert mock_logger.warning.call_count == 2

        # Check analyze_df log
        analyze_call = mock_logger.warning.call_args_list[0]
        assert "fail-fast triggered" in analyze_call[0][0]
        assert analyze_call[1]["extra"]["fail_fast"] is True
        assert analyze_call[1]["extra"]["node"] == "analyze_df"

        # Check report log
        report_call = mock_logger.warning.call_args_list[1]
        assert "blocking report generation" in report_call[0][0]
        assert report_call[1]["extra"]["fail_fast"] is True
        assert report_call[1]["extra"]["node"] == "report"
        assert report_call[1]["extra"]["fabrication_prevented"] is True

    def test_no_logging_when_no_error(self):
        """Test that no fail-fast logging occurs during normal operation."""
        # Setup state without error
        state = AgentState(
            question="test question",
            df_summary={"rows": 5, "columns": ["col1"]},
            plan_json={"table": "orders"},
        )

        with (
            patch("src.agent.nodes.logger") as mock_logger,
            patch("src.agent.nodes.llm_completion", return_value="Normal report"),
        ):

            analyze_df_node(state)
            report_node(state)

        # Should not have any fail-fast warning logs
        warning_calls = [
            call
            for call in mock_logger.warning.call_args_list
            if "fail-fast" in call[0][0]
        ]
        assert len(warning_calls) == 0
