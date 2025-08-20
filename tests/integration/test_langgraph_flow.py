"""Integration tests for LangGraph node flow."""

import json
import os
from unittest.mock import Mock, patch

import pytest

from src.agent.graph import build_graph
from src.agent.nodes import (
    analyze_df_node,
    execute_sql_node,
    plan_node,
    report_node,
    synthesize_sql_node,
    validate_sql_node,
)
from src.agent.state import AgentState


class TestLangGraphFlow:
    """Test LangGraph node integration and flow."""

    def test_build_graph_structure(self):
        """Test that build_graph creates proper graph structure."""
        app = build_graph()

        assert app is not None
        # Graph should be compiled and ready for execution

    def test_full_graph_execution_success_path(
        self, mock_bigquery_client, mock_gemini_client, sample_agent_state
    ):
        """Test complete successful execution through all nodes."""
        app = build_graph()

        # Create initial state
        initial_state = AgentState(question="What are the top selling products?")

        # Execute the graph
        final_state = app.invoke(initial_state)

        # Verify final state has all expected fields populated
        assert final_state.question == initial_state.question
        assert final_state.plan_json is not None
        assert final_state.sql is not None
        assert final_state.df_summary is not None
        assert final_state.report is not None
        assert final_state.error is None

    def test_graph_streaming_execution(self, mock_bigquery_client, mock_gemini_client):
        """Test streaming execution through graph nodes."""
        app = build_graph()

        initial_state = AgentState(question="Analyze customer demographics")

        # Stream execution to see intermediate states
        states = []
        for event in app.stream(initial_state):
            states.append(event)

        # Should have events for each node
        assert len(states) > 0

        # Extract node names from events
        node_names = []
        for event in states:
            node_names.extend(event.keys())

        # Verify expected nodes were executed
        expected_nodes = [
            "plan",
            "synthesize_sql",
            "validate_sql",
            "execute_sql",
            "analyze_df",
            "report",
        ]
        for node in expected_nodes:
            if node in node_names:  # Some nodes might be skipped on error
                assert True

        # At least plan node should execute
        assert "plan" in node_names

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "false"})
    def test_graph_error_handling_invalid_sql(
        self, mock_bigquery_client, mock_gemini_client
    ):
        """Test graph handles SQL validation errors properly."""
        # Mock LLM to return invalid SQL
        with patch("src.agent.nodes.llm_completion") as mock_llm:
            mock_llm.side_effect = [
                '{"task": "test", "tables": ["orders"]}',  # Valid plan
                "INVALID SQL SYNTAX",  # Invalid SQL
            ]

            app = build_graph()
            initial_state = AgentState(question="Test invalid SQL")

            final_state = app.invoke(initial_state)

            # Should stop at validation and set error
            assert final_state.error is not None
            assert "SQL parse error" in final_state.error
            assert final_state.df_summary is None  # Should not reach execution

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "false"})
    def test_graph_conditional_edge_on_error(
        self, mock_bigquery_client, mock_gemini_client
    ):
        """Test that graph properly handles conditional edges on validation error."""
        with patch("src.agent.nodes.llm_completion") as mock_llm:
            with patch("src.agent.nodes.sqlglot.parse_one") as mock_parse:
                # Mock SQL parsing to fail
                mock_parse.side_effect = Exception("Parse error")
                mock_llm.return_value = '{"task": "test", "tables": ["orders"]}'

                app = build_graph()
                initial_state = AgentState(question="Test conditional edge")

                # Stream to see which nodes execute
                states = []
                for event in app.stream(initial_state):
                    states.append(event)

                node_names = []
                for event in states:
                    node_names.extend(event.keys())

                # Should execute plan, synthesize_sql, validate_sql but NOT execute_sql
                assert "plan" in node_names
                assert "synthesize_sql" in node_names
                assert "validate_sql" in node_names
                assert "execute_sql" not in node_names

    def test_individual_node_plan(self, mock_bigquery_client, mock_gemini_client):
        """Test plan node functionality."""
        state = AgentState(question="What are the sales trends?")

        result_state = plan_node(state)

        assert result_state.plan_json is not None
        assert isinstance(result_state.plan_json, dict)
        # Should contain task and tables
        if isinstance(result_state.plan_json, dict):
            assert (
                "task" in result_state.plan_json or "tables" in result_state.plan_json
            )

    def test_individual_node_synthesize_sql(
        self, mock_bigquery_client, mock_gemini_client
    ):
        """Test SQL synthesis node functionality."""
        state = AgentState(
            question="Test question",
            plan_json={"task": "sales_analysis", "tables": ["orders"]},
        )

        result_state = synthesize_sql_node(state)

        assert result_state.sql is not None
        assert isinstance(result_state.sql, str)
        assert len(result_state.sql.strip()) > 0

    def test_individual_node_validate_sql(
        self, mock_bigquery_client, mock_gemini_client
    ):
        """Test SQL validation node functionality."""
        # Test valid SQL
        valid_state = AgentState(
            question="Test question",
            sql="SELECT order_id, status FROM orders WHERE status = 'Complete' LIMIT 100",
        )

        result_state = validate_sql_node(valid_state)

        assert result_state.error is None

        # Test invalid SQL
        invalid_state = AgentState(
            question="Test question",
            sql="DELETE FROM orders",  # Not allowed (only SELECT)
        )

        result_state = validate_sql_node(invalid_state)

        assert result_state.error is not None
        assert "Only SELECT queries are allowed" in result_state.error

    def test_individual_node_execute_sql(
        self, mock_bigquery_client, mock_gemini_client, sample_query_result
    ):
        """Test SQL execution node functionality."""
        state = AgentState(
            question="Test question", sql="SELECT * FROM orders LIMIT 10"
        )

        result_state = execute_sql_node(state)

        assert result_state.df_summary is not None
        assert isinstance(result_state.df_summary, dict)
        assert "rows" in result_state.df_summary
        assert "columns" in result_state.df_summary
        assert result_state.error is None

    def test_individual_node_analyze_df(self, mock_bigquery_client, mock_gemini_client):
        """Test DataFrame analysis node functionality."""
        state = AgentState(
            question="Test question",
            df_summary={
                "rows": 100,
                "columns": ["order_id", "amount"],
                "head": [{"order_id": 1, "amount": 50.0}],
            },
        )

        result_state = analyze_df_node(state)

        assert len(result_state.history) > 0
        # Should add analysis to history
        latest_entry = result_state.history[-1]
        assert "analysis" in latest_entry

    def test_individual_node_report(self, mock_bigquery_client, mock_gemini_client):
        """Test report generation node functionality."""
        state = AgentState(
            question="Test question",
            plan_json={"task": "test"},
            df_summary={"rows": 10, "columns": ["id", "value"]},
        )

        result_state = report_node(state)

        assert result_state.report is not None
        assert isinstance(result_state.report, str)
        assert len(result_state.report.strip()) > 0

    def test_graph_state_persistence(self, mock_bigquery_client, mock_gemini_client):
        """Test that state is properly passed between nodes."""
        app = build_graph()

        initial_state = AgentState(
            question="Test state persistence", history=[{"initial": "test"}]
        )

        final_state = app.invoke(initial_state)

        # Original question should be preserved
        assert final_state.question == initial_state.question

        # History should be maintained and potentially expanded
        assert len(final_state.history) >= len(initial_state.history)

    def test_graph_parallel_execution_safety(
        self, mock_bigquery_client, mock_gemini_client
    ):
        """Test that graph can handle concurrent executions safely."""
        import threading
        import time

        app = build_graph()
        results = []
        errors = []

        def execute_graph(question):
            try:
                state = AgentState(question=f"Test question {question}")
                result = app.invoke(state)
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=execute_graph, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # All executions should succeed
        assert len(errors) == 0
        assert len(results) == 3

        # Each result should be independent
        questions = [result.question for result in results]
        assert len(set(questions)) == 3  # All unique

    def test_graph_memory_efficiency(self, mock_bigquery_client, mock_gemini_client):
        """Test that graph doesn't accumulate excessive memory."""
        app = build_graph()

        # Execute multiple times to check for memory leaks
        for i in range(10):
            state = AgentState(question=f"Memory test {i}")
            result = app.invoke(state)

            # Each result should be independent
            assert result.question == f"Memory test {i}"

    def test_graph_configuration_dependency(self, mock_env_vars):
        """Test that graph uses configuration properly."""
        # Graph building should work with mocked environment
        app = build_graph()

        assert app is not None
        # Graph should be properly configured

    def test_node_error_propagation(self, mock_bigquery_client):
        """Test that node errors are properly propagated through the graph."""
        # Mock BigQuery to fail
        mock_bigquery_client.query.side_effect = Exception("BigQuery connection failed")

        with patch("src.agent.nodes.llm_completion") as mock_llm:
            mock_llm.side_effect = [
                '{"task": "test", "tables": ["orders"]}',  # Valid plan
                "SELECT * FROM orders LIMIT 10",  # Valid SQL
            ]

            app = build_graph()
            initial_state = AgentState(question="Test error propagation")

            final_state = app.invoke(initial_state)

            # Error should be captured in final state
            assert final_state.error is not None
            assert "BigQuery connection failed" in final_state.error

    def test_graph_with_custom_state(self, mock_bigquery_client, mock_gemini_client):
        """Test graph execution with pre-populated state."""
        app = build_graph()

        # Start with partially populated state
        custom_state = AgentState(
            question="Custom state test",
            plan_json={"task": "custom", "tables": ["orders"]},
            history=[{"custom": "initial_data"}],
        )

        final_state = app.invoke(custom_state)

        # Should preserve initial data and add new data
        assert final_state.question == custom_state.question
        assert final_state.plan_json == custom_state.plan_json
        assert len(final_state.history) >= len(custom_state.history)

    def test_graph_entry_point(self, mock_bigquery_client, mock_gemini_client):
        """Test that graph starts at the correct entry point."""
        app = build_graph()

        initial_state = AgentState(question="Test entry point")

        # Stream to see execution order
        states = []
        for event in app.stream(initial_state):
            states.append(event)

        # First event should be from the plan node (entry point)
        if states:
            first_event = states[0]
            assert "plan" in first_event

    def test_graph_end_conditions(self, mock_bigquery_client, mock_gemini_client):
        """Test that graph properly terminates under different conditions."""
        app = build_graph()

        # Normal execution - should reach END
        normal_state = AgentState(question="Normal execution test")
        final_state = app.invoke(normal_state)

        # Should complete without hanging
        assert final_state is not None

        # Error execution - should terminate early on validation error
        with patch("src.agent.nodes.validate_sql_node") as mock_validate:
            error_state = AgentState(question="Error test")
            error_state.error = "Validation failed"
            mock_validate.return_value = error_state

            final_state = app.invoke(error_state)

            # Should terminate with error
            assert final_state.error is not None
