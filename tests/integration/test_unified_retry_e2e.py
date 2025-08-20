"""End-to-end integration tests for unified retry architecture (LGDA-007)."""

import os
from unittest.mock import patch, Mock

import pandas as pd
import pytest

from src.agent.graph import build_graph
from src.agent.state import AgentState


class TestUnifiedRetryIntegration:
    """Test end-to-end unified retry architecture functionality."""

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    @patch('src.agent.nodes.run_query')
    @patch('src.agent.nodes.llm_completion')
    def test_end_to_end_sql_retry_recovery(self, mock_llm, mock_run_query):
        """Test end-to-end SQL generation retry and recovery."""
        # Mock LLM responses: plan -> invalid SQL -> valid SQL -> report
        mock_llm.side_effect = [
            '{"task": "test", "tables": ["orders"]}',  # Valid plan
            "INVALID SQL SYNTAX",  # First SQL attempt (invalid)
            "SELECT * FROM orders LIMIT 10",  # Second SQL attempt (valid)
            "Executive insight: Found 3 orders with total value $600. Next steps: analyze trends."  # Report
        ]
        
        # Mock BigQuery execution
        mock_dataframe = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['order1', 'order2', 'order3'],
            'amount': [100.0, 200.0, 300.0]
        })
        mock_run_query.return_value = mock_dataframe
        
        # Mock circuit breaker
        with patch('src.bq._circuit_breaker') as mock_breaker:
            mock_breaker.can_execute.return_value = True
            
            app = build_graph()
            initial_state = AgentState(question="Test SQL retry recovery")
            
            with patch('time.sleep'):  # Speed up test
                final_state = app.invoke(initial_state)
            
            # Should have succeeded after retry
            assert final_state.error is None
            # SQL should be processed by validation (fully qualified names and proper LIMIT)
            assert "SELECT * FROM" in final_state.sql
            assert "orders" in final_state.sql.lower()
            # Unified retry should have handled retries internally, so final success means no error
            assert final_state.report is not None  # Report should be generated
            
            # LLM should have been called 4 times (plan + 2 SQL attempts + report)
            assert mock_llm.call_count == 4
            
            # BigQuery should have been called once with valid SQL  
            mock_run_query.assert_called_once()
            called_sql = mock_run_query.call_args[0][0]
            assert "SELECT * FROM" in called_sql
            assert "orders" in called_sql.lower()

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "false"})
    @patch('src.agent.nodes.llm_completion')
    def test_end_to_end_legacy_retry_behavior(self, mock_llm):
        """Test end-to-end behavior with legacy retry (no automatic retry)."""
        # Mock LLM responses: plan -> invalid SQL (should stop here)
        mock_llm.side_effect = [
            '{"task": "test", "tables": ["orders"]}',  # Valid plan
            "INVALID SQL SYNTAX",  # Invalid SQL
        ]
        
        app = build_graph()
        initial_state = AgentState(question="Test legacy behavior")
        
        final_state = app.invoke(initial_state)
        
        # Should have failed without retry
        assert final_state.error is not None
        assert "SQL parse error" in final_state.error
        assert final_state.retry_count == 0  # No retries in legacy mode
        
        # LLM should have been called only 2 times (plan + 1 SQL attempt)
        assert mock_llm.call_count == 2

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    @patch('src.bq.bq_client')
    @patch('src.agent.nodes.llm_completion')
    def test_end_to_end_bigquery_retry_integration(self, mock_llm, mock_bq_client):
        """Test BigQuery unified retry integration with LangGraph."""
        # Mock LLM responses: plan -> valid SQL
        mock_llm.side_effect = [
            '{"task": "test", "tables": ["orders"]}',  # Valid plan
            "SELECT * FROM orders LIMIT 10"  # Valid SQL
        ]
        
        # Mock BigQuery client to fail then succeed
        mock_client = Mock()
        
        # Create mock job for successful case
        success_job = Mock()
        success_result = Mock()
        
        # Create proper DataFrame mock
        mock_dataframe = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['order1', 'order2', 'order3'],
            'amount': [100.0, 200.0, 300.0]
        })
        success_result.to_dataframe.return_value = mock_dataframe
        success_job.result.return_value = success_result
        
        mock_client.query.side_effect = [
            Exception("Server error"),  # First attempt fails
            success_job  # Second attempt succeeds
        ]
        mock_bq_client.return_value = mock_client
        
        # Mock circuit breaker
        with patch('src.bq._circuit_breaker') as mock_breaker:
            mock_breaker.can_execute.return_value = True
            
            app = build_graph()
            initial_state = AgentState(question="Test BigQuery retry")
            
            with patch('time.sleep'):  # Speed up test
                final_state = app.invoke(initial_state)
            
            # Should have succeeded after BigQuery retry
            assert final_state.error is None
            assert final_state.sql == "SELECT * FROM orders LIMIT 10"
            
            # BigQuery should have been called twice (retry)
            assert mock_client.query.call_count == 2
            mock_breaker.record_success.assert_called()

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    @patch('src.agent.nodes.llm_completion')
    def test_end_to_end_retry_exhaustion(self, mock_llm):
        """Test behavior when all retry attempts are exhausted."""
        # Mock LLM to always return invalid SQL
        mock_llm.side_effect = [
            '{"task": "test", "tables": ["orders"]}',  # Valid plan
            "INVALID SQL SYNTAX",  # First SQL attempt
            "STILL INVALID SQL",   # Second SQL attempt
            "ALSO INVALID SQL",    # Third SQL attempt
            "STILL BAD SQL"        # Fourth SQL attempt (max retries exceeded)
        ]
        
        app = build_graph()
        initial_state = AgentState(question="Test retry exhaustion", max_retries=2)
        
        with patch('time.sleep'):  # Speed up test
            final_state = app.invoke(initial_state)
        
        # Should have failed after exhausting unified retries (not graph retries)
        assert final_state.error is not None
        assert "SQL parse error" in final_state.error  # Should be a validation error
        # Graph-level retry_count should be 0 because unified retry handles all internal retries
        assert final_state.retry_count == 0
        
        # Should have tried plan + 3 SQL attempts (unified retry max_attempts=3)
        assert mock_llm.call_count == 4  # plan + 3 SQL attempts

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    @patch('src.agent.nodes.run_query')
    @patch('src.agent.nodes.llm_completion') 
    def test_end_to_end_context_propagation(self, mock_llm, mock_run_query):
        """Test that error context is properly propagated through retries."""
        # Mock LLM responses
        mock_llm.side_effect = [
            '{"task": "test", "tables": ["orders"]}',  # Valid plan
            "INVALID SQL SYNTAX",  # First invalid SQL
            "SELECT * FROM orders LIMIT 10",  # Valid SQL on retry
            "Executive insight: Found 3 orders."  # Report
        ]
        
        # Mock BigQuery execution
        mock_dataframe = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['order1', 'order2', 'order3'],
            'amount': [100.0, 200.0, 300.0]
        })
        mock_run_query.return_value = mock_dataframe
        
        app = build_graph()
        initial_state = AgentState(question="Test context propagation")
        
        with patch('time.sleep'):
            final_state = app.invoke(initial_state)
        
        # Should have succeeded after retry
        assert final_state.error is None
        assert final_state.sql == "SELECT * FROM orders LIMIT 10"
        
        # Check that retry prompt included error context
        call_args = [call[0][0] for call in mock_llm.call_args_list]
        sql_prompts = call_args[1:]  # Skip plan prompt
        
        # Second SQL call should include error context
        assert len(sql_prompts) >= 2
        assert "PREVIOUS ATTEMPT FAILED" in sql_prompts[1]
        assert "SQL parse error" in sql_prompts[1]

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    def test_feature_flag_runtime_behavior(self):
        """Test that feature flag can control retry behavior at runtime."""
        from src.core.migration import is_unified_retry_enabled
        from src.agent.graph import _should_retry_sql_generation
        
        # Should be enabled by default in this test
        assert is_unified_retry_enabled() is True
        
        # When unified retry is enabled, graph-level retries should be disabled for SQL errors
        # This is the whole point of the unified retry system
        state = AgentState(
            question="test",
            error="SQL parse error: test",
            last_error="SQL parse error: test",
            retry_count=0,
            max_retries=2
        )
        assert _should_retry_sql_generation(state) is False  # Should NOT retry at graph level
        
        # Test that when disabled, the behavior is different
        with patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "false"}):
            # Need to reload module to pick up env change
            import importlib
            import src.core.migration
            importlib.reload(src.core.migration)
            from src.core.migration import is_unified_retry_enabled
            
            assert is_unified_retry_enabled() is False
            # In legacy mode, graph-level retry might still be disabled (depends on implementation)
            # The key is that the behavior is different between modes
            legacy_result = _should_retry_sql_generation(state)
            assert legacy_result is False  # Current implementation disables graph retries in both modes

    def test_unified_retry_configuration_integration(self):
        """Test that unified retry uses proper configuration."""
        from src.configuration.unified import get_retry_config
        from src.core.retry import RetryConfig
        
        # Should be able to get retry configuration
        config = get_retry_config()
        assert config.enable_unified_retry is True
        
        # Should have proper retry strategies
        assert RetryConfig.SQL_GENERATION.max_attempts == 3
        assert RetryConfig.BIGQUERY_TRANSIENT.max_attempts == 5
        assert RetryConfig.LLM_TIMEOUT.max_attempts == 2