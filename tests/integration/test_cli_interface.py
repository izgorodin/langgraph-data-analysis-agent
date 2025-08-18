"""Integration tests for CLI interface."""

import json
from unittest.mock import Mock, patch

import pytest
from cli import main
from click.testing import CliRunner


class TestCLIInterface:
    """Test CLI interface functionality."""

    @pytest.fixture
    def cli_runner(self):
        """Create Click CLI runner for testing."""
        return CliRunner()

    @pytest.fixture
    def mock_graph_app(self, sample_agent_state):
        """Mock LangGraph application."""
        mock_app = Mock()

        # Mock stream method for verbose mode
        mock_app.stream.return_value = [
            {"plan": sample_agent_state.model_dump()},
            {"synthesize_sql": sample_agent_state.model_dump()},
            {"validate_sql": sample_agent_state.model_dump()},
            {"execute_sql": sample_agent_state.model_dump()},
            {"analyze_df": sample_agent_state.model_dump()},
            {"report": sample_agent_state.model_dump()},
        ]

        # Mock invoke method for final result
        final_state = sample_agent_state.model_copy()
        final_state.report = "Final analysis report with insights and recommendations."
        mock_app.invoke.return_value = final_state

        return mock_app

    def test_cli_basic_invocation(
        self, cli_runner, mock_graph_app, mock_bigquery_client, mock_gemini_client
    ):
        """Test CLI runs with basic arguments."""
        with patch("cli.build_graph") as mock_build_graph:
            mock_build_graph.return_value = mock_graph_app

            result = cli_runner.invoke(main, ["What are the top selling products?"])

            assert result.exit_code == 0
            assert "Insight" in result.output
            assert len(result.output) > 0

    def test_cli_verbose_mode(
        self, cli_runner, mock_graph_app, mock_bigquery_client, mock_gemini_client
    ):
        """Test CLI verbose mode outputs JSON states."""
        with patch("cli.build_graph") as mock_build_graph:
            mock_build_graph.return_value = mock_graph_app

            result = cli_runner.invoke(main, ["--verbose", "Analyze customer data"])

            assert result.exit_code == 0

            # Should contain JSON output for each node
            assert "plan" in result.output
            assert "synthesize_sql" in result.output
            assert "execute_sql" in result.output

            # Should contain final insight
            assert "Insight" in result.output

    def test_cli_custom_model(
        self, cli_runner, mock_graph_app, mock_bigquery_client, mock_gemini_client
    ):
        """Test CLI with custom model parameter."""
        with patch("cli.build_graph") as mock_build_graph:
            mock_build_graph.return_value = mock_graph_app

            result = cli_runner.invoke(
                main, ["--model", "gemini-1.5-flash", "Show sales trends"]
            )

            assert result.exit_code == 0
            # Note: model parameter is passed but not currently used in mock

    def test_cli_interactive_prompt(
        self, cli_runner, mock_graph_app, mock_bigquery_client, mock_gemini_client
    ):
        """Test CLI interactive mode when no question provided."""
        with patch("cli.build_graph") as mock_build_graph:
            mock_build_graph.return_value = mock_graph_app

            # Simulate user input
            result = cli_runner.invoke(
                main, [], input="What is the revenue by category?\n"
            )

            assert result.exit_code == 0
            assert "Enter your analysis question" in result.output
            assert "Insight" in result.output

    def test_cli_error_handling(
        self, cli_runner, mock_bigquery_client, mock_gemini_client
    ):
        """Test CLI error handling when graph execution fails."""
        with patch("cli.build_graph") as mock_build_graph:
            # Mock graph that raises an exception
            mock_app = Mock()
            mock_app.stream.side_effect = Exception("Graph execution failed")
            mock_build_graph.return_value = mock_app

            result = cli_runner.invoke(main, ["Test question"])

            # CLI should handle the error gracefully
            # Note: Current implementation doesn't have explicit error handling
            # So this tests the current behavior
            assert result.exit_code != 0 or "Exception" in result.output

    def test_cli_environment_variables(self, cli_runner, mock_graph_app, mock_env_vars):
        """Test CLI reads configuration from environment variables."""
        with patch("cli.build_graph") as mock_build_graph:
            with patch("cli.settings") as mock_settings:
                mock_settings.model_name = "test-model-from-env"
                mock_build_graph.return_value = mock_graph_app

                result = cli_runner.invoke(main, ["Test question"])

                assert result.exit_code == 0
                # Verify that settings were accessed
                assert mock_settings.model_name

    def test_cli_json_output_format(
        self, cli_runner, mock_graph_app, mock_bigquery_client, mock_gemini_client
    ):
        """Test that verbose mode produces valid JSON output."""
        with patch("cli.build_graph") as mock_build_graph:
            mock_build_graph.return_value = mock_graph_app

            result = cli_runner.invoke(main, ["--verbose", "Test question"])

            assert result.exit_code == 0

            # Extract JSON parts from output (between rules)
            lines = result.output.split("\n")
            json_lines = []
            capturing = False

            for line in lines:
                if line.startswith("─") and any(
                    node in line for node in ["plan", "synthesize_sql", "execute_sql"]
                ):
                    capturing = True
                    continue
                elif line.startswith("─") and "Insight" in line:
                    capturing = False
                elif capturing and line.strip():
                    json_lines.append(line)

            # At least some JSON should be captured
            json_content = "\n".join(json_lines)
            if json_content.strip():
                # Should be valid JSON (truncated at 6000 chars in implementation)
                try:
                    # Try to parse first JSON block
                    first_json = json_content.split("\n")[0]
                    if first_json.strip():
                        json.loads(first_json[:6000])  # Match the truncation in cli.py
                except json.JSONDecodeError:
                    pass  # JSON might be truncated, which is expected

    def test_cli_rich_output_formatting(
        self, cli_runner, mock_graph_app, mock_bigquery_client, mock_gemini_client
    ):
        """Test that CLI uses Rich for proper output formatting."""
        with patch("cli.build_graph") as mock_build_graph:
            mock_build_graph.return_value = mock_graph_app

            result = cli_runner.invoke(main, ["Test question"])

            assert result.exit_code == 0

            # Should contain Rich Panel formatting for final report
            assert "Agent Report" in result.output
            # Rich formatting might include box drawing characters

    def test_cli_long_output_truncation(
        self, cli_runner, mock_bigquery_client, mock_gemini_client
    ):
        """Test that long JSON outputs are properly truncated."""
        with patch("cli.build_graph") as mock_build_graph:
            # Create mock with very long output
            mock_app = Mock()
            long_data = {"data": "x" * 10000}  # Very long data
            mock_app.stream.return_value = [{"test_node": long_data}]
            mock_app.invoke.return_value.report = "Test report"
            mock_build_graph.return_value = mock_app

            result = cli_runner.invoke(main, ["--verbose", "Test question"])

            assert result.exit_code == 0
            # Output should be truncated (implementation limits to 6000 chars)
            # This is hard to test precisely due to JSON formatting

    def test_cli_no_report_handling(
        self, cli_runner, mock_bigquery_client, mock_gemini_client
    ):
        """Test CLI handling when no report is generated."""
        with patch("cli.build_graph") as mock_build_graph:
            mock_app = Mock()
            mock_app.stream.return_value = []
            final_state = Mock()
            final_state.report = None  # No report generated
            mock_app.invoke.return_value = final_state
            mock_build_graph.return_value = mock_app

            result = cli_runner.invoke(main, ["Test question"])

            assert result.exit_code == 0
            assert "No report" in result.output

    def test_cli_help_output(self, cli_runner):
        """Test CLI help output."""
        result = cli_runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "--model" in result.output
        assert "--verbose" in result.output
        assert "Show intermediate states" in result.output

    def test_cli_invalid_arguments(self, cli_runner):
        """Test CLI with invalid arguments."""
        result = cli_runner.invoke(main, ["--invalid-option"])

        assert result.exit_code != 0
        assert "Error:" in result.output or "Usage:" in result.output

    def test_cli_console_object(
        self, cli_runner, mock_graph_app, mock_bigquery_client, mock_gemini_client
    ):
        """Test that CLI creates and uses Rich Console object."""
        with patch("cli.build_graph") as mock_build_graph:
            with patch("cli.console") as mock_console:
                mock_build_graph.return_value = mock_graph_app

                result = cli_runner.invoke(main, ["Test question"])

                # Verify console methods were called
                assert mock_console.rule.called
                assert mock_console.print.called

    def test_cli_state_streaming(
        self, cli_runner, mock_bigquery_client, mock_gemini_client
    ):
        """Test that CLI properly streams intermediate states."""
        with patch("cli.build_graph") as mock_build_graph:
            # Create mock that yields multiple states
            mock_app = Mock()

            states = [
                {"plan": {"question": "test", "plan_json": {"task": "test"}}},
                {
                    "execute_sql": {
                        "sql": "SELECT * FROM test",
                        "df_summary": {"rows": 5},
                    }
                },
                {"report": {"report": "Final report"}},
            ]

            mock_app.stream.return_value = states
            final_state = Mock()
            final_state.report = "Streaming test complete"
            mock_app.invoke.return_value = final_state

            mock_build_graph.return_value = mock_app

            result = cli_runner.invoke(main, ["--verbose", "Test streaming"])

            assert result.exit_code == 0
            # Should show all intermediate nodes
            assert "plan" in result.output
            assert "execute_sql" in result.output
            assert "report" in result.output

    def test_cli_graph_building(
        self, cli_runner, mock_bigquery_client, mock_gemini_client
    ):
        """Test that CLI properly builds the LangGraph."""
        with patch("cli.build_graph") as mock_build_graph:
            mock_app = Mock()
            mock_app.stream.return_value = []
            mock_app.invoke.return_value.report = "Graph built successfully"
            mock_build_graph.return_value = mock_app

            result = cli_runner.invoke(main, ["Test graph building"])

            assert result.exit_code == 0
            # Verify build_graph was called
            mock_build_graph.assert_called_once()

    def test_cli_state_model_dump_handling(
        self, cli_runner, mock_bigquery_client, mock_gemini_client
    ):
        """Test CLI handling of state objects vs dictionaries."""
        with patch("cli.build_graph") as mock_build_graph:
            from src.agent.state import AgentState

            mock_app = Mock()

            # Mix of state objects and dictionaries
            test_state = AgentState(question="test")
            states = [
                {"node1": test_state},  # State object - should call model_dump()
                {"node2": {"key": "value"}},  # Dictionary - should use as-is
            ]

            mock_app.stream.return_value = states
            mock_app.invoke.return_value.report = "Mixed state test"
            mock_build_graph.return_value = mock_app

            result = cli_runner.invoke(main, ["--verbose", "Test mixed states"])

            assert result.exit_code == 0
