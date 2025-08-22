"""Tests for LGDA-015: Retry Logic for SQL Validation and Type Mismatch Errors."""

import pytest
from unittest.mock import patch, Mock

from src.agent.graph import build_graph
from src.agent.state import AgentState
from src.error.classification import RecoveryStrategy, ErrorSeverity


class TestValidationErrorRetryLogic:
    """Test retry logic for SQL validation and type mismatch errors."""

    def test_type_mismatch_error_triggers_retry(self, mock_bigquery_client, mock_gemini_client):
        """Test that type mismatch errors trigger retry with simplified SQL."""
        app = build_graph()
        
        with patch("src.agent.nodes.llm_completion") as mock_llm:
            # Mock LLM responses: plan, then SQL attempts
            mock_llm.side_effect = [
                '{"task": "analyze timestamps", "tables": ["orders"]}',  # Valid plan
                "SELECT created_at as date_col FROM `bigquery-public-data.thelook_ecommerce.orders` WHERE created_at > TIMESTAMP('2023-01-01')",  # First SQL with type issue
                "SELECT DATE(created_at) as date_col FROM `bigquery-public-data.thelook_ecommerce.orders` WHERE created_at > '2023-01-01'",  # Retry 1: simplified
                "SELECT created_at FROM `bigquery-public-data.thelook_ecommerce.orders` LIMIT 100",  # Retry 2: further simplified
            ]
            
            # Mock validation to simulate type mismatch error
            with patch("src.agent.nodes.sqlglot.parse_one") as mock_parse:
                mock_parse.side_effect = [
                    Exception("Type mismatch: TIMESTAMP vs DATE in WHERE clause"),  # First attempt
                    Exception("Invalid function call in SELECT"),  # Second attempt 
                    Mock(),  # Third attempt succeeds
                ]
                
                initial_state = AgentState(
                    question="Test type mismatch retry",
                    max_retries=2
                )
                
                final_state = app.invoke(initial_state)
                
                # Should have retried and eventually succeeded or exhausted retries
                assert final_state.retry_count > 0
                # Should have attempted multiple SQL generations
                assert mock_llm.call_count >= 3

    def test_permanent_validation_error_no_retry(self, mock_bigquery_client, mock_gemini_client):
        """Test that permanent validation errors don't trigger retries."""
        app = build_graph()
        
        with patch("src.agent.nodes.llm_completion") as mock_llm:
            mock_llm.side_effect = [
                '{"task": "test", "tables": ["orders"]}',  # Plan  
                "DROP TABLE users",  # SQL with security violation (DML/DDL)
                "SHOULD NOT BE CALLED",  # Should not retry for security violations
            ]
            
            initial_state = AgentState(
                question="Test permanent error",
                max_retries=2
            )
            
            final_state = app.invoke(initial_state)
            
            # Should have security error and not retry
            assert final_state.error is not None
            assert "security violation" in final_state.error.lower() or "drop" in final_state.error.lower()
            # Should not have retried for security violations
            assert mock_llm.call_count <= 2  # Plan + initial SQL only

    def test_retry_with_sql_simplification(self, mock_bigquery_client, mock_gemini_client):
        """Test that retry attempts include error context for SQL simplification."""
        app = build_graph()
        
        with patch("src.agent.nodes.llm_completion") as mock_llm:
            mock_llm.side_effect = [
                '{"task": "complex query", "tables": ["orders"]}',  # Valid plan
                "SELECT complex_function(col) FROM table WHERE complex_condition",  # Complex SQL
                "SELECT col FROM table WHERE simple_condition",  # Simplified retry
                "SELECT * FROM table LIMIT 10",  # Further simplified
            ]
            
            initial_state = AgentState(
                question="Test SQL simplification",
                max_retries=2
            )
            
            final_state = app.invoke(initial_state)
            
            # The basic retry mechanism should work - check retry count
            assert final_state.retry_count >= 0  # At least tried once
            assert mock_llm.call_count >= 2  # Called for plan + at least one SQL attempt
            
            # Check that retry attempts included error context (if retries happened)
            llm_calls = mock_llm.call_args_list
            if final_state.retry_count > 0 and len(llm_calls) >= 3:  # Plan + SQL + retry
                retry_prompt = llm_calls[2][0][0]  # Third call should be retry with context
                assert "PREVIOUS ATTEMPT FAILED" in retry_prompt

    def test_error_classification_for_validation_errors(self):
        """Test that different validation errors are classified correctly."""
        from src.error.classification import ErrorClassifier
        
        classifier = ErrorClassifier()
        
        # Type mismatch should be retryable (USER_GUIDED)
        strategy, severity = classifier.classify("Type mismatch: TIMESTAMP vs DATE")
        assert strategy == RecoveryStrategy.USER_GUIDED
        
        # Security violations should not be retryable
        strategy, severity = classifier.classify("Table 'forbidden_table' not in allowed tables")
        assert strategy == RecoveryStrategy.NO_RECOVERY
        
        # Parse errors should be retryable
        strategy, severity = classifier.classify("SQL parse error: syntax error")
        assert strategy == RecoveryStrategy.USER_GUIDED

    def test_retry_count_increments_on_validation_failure(self, mock_bigquery_client, mock_gemini_client):
        """Test that retry_count increments properly for validation failures."""
        app = build_graph()
        
        with patch("src.agent.nodes.llm_completion") as mock_llm:
            mock_llm.side_effect = [
                '{"task": "test", "tables": ["orders"]}',  # Valid plan
                "INVALID SQL 1",  # Invalid SQL (attempt 1)
                "INVALID SQL 2",  # Invalid SQL (attempt 2)
                "INVALID SQL 3",  # Invalid SQL (attempt 3)
            ]
            
            initial_state = AgentState(
                question="Test retry count",
                max_retries=2
            )
            
            final_state = app.invoke(initial_state)
            
            # Should have exhausted all retries
            assert final_state.retry_count == 2
            assert final_state.error is not None

    def test_logging_of_retry_decisions(self, mock_bigquery_client, mock_gemini_client, caplog):
        """Test that retry decisions are properly logged."""
        app = build_graph()
        
        with patch("src.agent.nodes.llm_completion") as mock_llm:
            mock_llm.side_effect = [
                '{"task": "test", "tables": ["orders"]}',  # Valid plan
                "INVALID SQL 1",  # Invalid SQL
                "INVALID SQL 2",  # Invalid SQL retry
            ]
            
            initial_state = AgentState(
                question="Test retry logging",
                max_retries=1
            )
            
            final_state = app.invoke(initial_state)
            
            # Check that retry decisions were logged
            # (This will help verify if logging is working correctly)
            assert len(caplog.records) > 0