"""Tests for LangGraph unified retry integration (LGDA-007)."""

import os
from unittest.mock import patch, Mock

import pytest

from src.agent.graph import build_graph, _should_retry_sql_generation
from src.agent.nodes import _generate_sql_with_retry
from src.agent.state import AgentState


class TestLangGraphRetryIntegration:
    """Test LangGraph integration with unified retry."""

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    def test_should_retry_sql_generation_enabled(self):
        """Test retry logic when unified retry is enabled."""
        # Test SQL validation errors should retry
        state = AgentState(
            question="test",
            error="SQL parse error: invalid syntax",
            last_error="SQL parse error: invalid syntax",
            retry_count=0,
            max_retries=2
        )
        assert _should_retry_sql_generation(state) is True
        
        # Test forbidden tables error should retry
        state = AgentState(
            question="test", 
            error="Forbidden tables detected: bad_table",
            last_error="Forbidden tables detected: bad_table",
            retry_count=0,
            max_retries=2
        )
        assert _should_retry_sql_generation(state) is True
        
        # Test LLM errors should retry
        state = AgentState(
            question="test",
            error="LLM completion failed",
            last_error="LLM completion failed", 
            retry_count=0,
            max_retries=2
        )
        assert _should_retry_sql_generation(state) is True

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    def test_should_retry_sql_generation_limits(self):
        """Test retry limits are respected."""
        # Should not retry when max retries exceeded
        state = AgentState(
            question="test",
            error="SQL parse error: test",
            last_error="SQL parse error: test",
            retry_count=3,
            max_retries=2
        )
        assert _should_retry_sql_generation(state) is False
        
        # Should not retry when no error
        state = AgentState(
            question="test",
            error=None,
            last_error=None,
            retry_count=0,
            max_retries=2
        )
        assert _should_retry_sql_generation(state) is False

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "false"})
    def test_should_retry_sql_generation_disabled(self):
        """Test retry logic when unified retry is disabled."""
        state = AgentState(
            question="test",
            error="SQL parse error: test",
            last_error="SQL parse error: test",
            retry_count=0,
            max_retries=2
        )
        assert _should_retry_sql_generation(state) is False

    def test_infrastructure_errors_not_retried(self):
        """Test that infrastructure errors are not retried at graph level."""
        with patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"}):
            # Infrastructure errors should not be retried (handled at lower level)
            state = AgentState(
                question="test",
                error="Connection error: network timeout",
                last_error="Connection error: network timeout",
                retry_count=0,
                max_retries=2
            )
            assert _should_retry_sql_generation(state) is False
            
            state = AgentState(
                question="test",
                error="BigQuery execution failed: server error",
                last_error="BigQuery execution failed: server error",
                retry_count=0,
                max_retries=2
            )
            assert _should_retry_sql_generation(state) is False

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    def test_graph_retry_behavior(self):
        """Test graph conditional edges with retry logic."""
        from src.agent.graph import build_graph
        
        app = build_graph()
        
        # Test successful validation (no retry needed)
        state = AgentState(question="test", error=None)
        # Note: We can't easily test the full graph execution without mocking
        # many dependencies, but we can test the retry decision logic
        assert _should_retry_sql_generation(state) is False

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    @patch('src.agent.nodes.llm_completion')
    def test_generate_sql_with_retry_enabled(self, mock_llm):
        """Test SQL generation with unified retry enabled."""
        # Mock LLM to fail once then succeed
        mock_llm.side_effect = [
            Exception("LLM timeout"),
            "SELECT * FROM orders LIMIT 10"
        ]
        
        state = AgentState(
            question="test",
            plan_json={"task": "test", "tables": ["orders"]},
            retry_count=0,
            max_retries=2
        )
        
        with patch('time.sleep'):  # Mock sleep for speed
            sql = _generate_sql_with_retry(state)
        
        assert sql == "SELECT * FROM orders LIMIT 10"
        assert mock_llm.call_count == 2
        # When retry succeeds, no error is stored in state

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "false"})
    @patch('src.agent.nodes.llm_completion')
    def test_generate_sql_with_retry_disabled(self, mock_llm):
        """Test SQL generation with unified retry disabled."""
        # Mock LLM to fail
        mock_llm.side_effect = Exception("LLM timeout")
        
        state = AgentState(
            question="test",
            plan_json={"task": "test", "tables": ["orders"]},
            retry_count=0,
            max_retries=2
        )
        
        with pytest.raises(Exception, match="LLM timeout"):
            _generate_sql_with_retry(state)
        
        assert mock_llm.call_count == 1  # Should only be called once (no retry)

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    @patch('src.agent.nodes.llm_completion')
    def test_generate_sql_with_retry_context_propagation(self, mock_llm):
        """Test that error context is propagated through retries."""
        # Mock LLM to fail multiple times
        mock_llm.side_effect = [
            Exception("First failure"),
            Exception("Second failure"),
            "SELECT * FROM orders LIMIT 10"
        ]
        
        state = AgentState(
            question="test",
            plan_json={"task": "test", "tables": ["orders"]},
            retry_count=1,  # Start with existing retry count
            last_error="Previous error",
            max_retries=3
        )
        
        with patch('time.sleep'):  # Mock sleep for speed
            sql = _generate_sql_with_retry(state)
        
        assert sql == "SELECT * FROM orders LIMIT 10"
        assert mock_llm.call_count == 3
        # Verify that error context was passed in prompts
        call_args = [call[0][0] for call in mock_llm.call_args_list]
        assert any("PREVIOUS ATTEMPT FAILED" in arg for arg in call_args)

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    @patch('src.agent.nodes.llm_completion')
    def test_generate_sql_with_retry_max_attempts(self, mock_llm):
        """Test SQL generation respects max retry attempts."""
        # Mock LLM to always fail
        mock_llm.side_effect = Exception("Persistent failure")
        
        state = AgentState(
            question="test",
            plan_json={"task": "test", "tables": ["orders"]},
            retry_count=0,
            max_retries=2
        )
        
        with patch('time.sleep'):  # Mock sleep for speed
            with pytest.raises(Exception, match="Persistent failure"):
                _generate_sql_with_retry(state)
        
        # Should have made 3 attempts (initial + 3 retries for SQL_GENERATION strategy)
        assert mock_llm.call_count == 3

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    @patch('src.agent.nodes.llm_completion')
    def test_sql_generation_fallback_behavior(self, mock_llm):
        """Test SQL generation fallback behavior for malformed responses."""
        # Mock LLM to return JSON instead of SQL
        mock_llm.return_value = '{"task": "not sql"}'
        
        state = AgentState(
            question="test",
            plan_json={"task": "test", "tables": ["orders"]},
            retry_count=0,
            max_retries=2
        )
        
        sql = _generate_sql_with_retry(state)
        
        # Should fall back to safe SELECT using first table from plan
        assert sql == "SELECT * FROM orders LIMIT 10"
        assert mock_llm.call_count == 1

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    def test_error_classification_for_graph_retry(self):
        """Test that appropriate errors trigger graph-level retries."""
        # Business logic errors that should retry
        business_errors = [
            "SQL parse error: invalid syntax",
            "Forbidden tables detected: unauthorized_table",
            "Invalid SQL query",
            "Query must start with SELECT",
            "LLM completion failed",
            "Model timeout error",
            "LLM timeout occurred"
        ]
        
        for error in business_errors:
            state = AgentState(
                question="test",
                error=error,
                last_error=error,
                retry_count=0,
                max_retries=2
            )
            assert _should_retry_sql_generation(state) is True, f"Should retry error: {error}"
        
        # Infrastructure errors that should NOT retry at graph level
        infrastructure_errors = [
            "Connection error",
            "Network timeout", 
            "Server unavailable",
            "BigQuery server error",
            "Database connection failed",
            "Timeout during network operation"
        ]
        
        for error in infrastructure_errors:
            state = AgentState(
                question="test",
                error=error,
                last_error=error,
                retry_count=0,
                max_retries=2
            )
            assert _should_retry_sql_generation(state) is False, f"Should NOT retry error: {error}"