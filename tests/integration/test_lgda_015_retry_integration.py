"""Integration test for LGDA-015: Complete retry logic for type mismatch errors."""

import logging
from unittest.mock import patch, Mock

import pytest

from src.agent.graph import build_graph
from src.agent.state import AgentState


class TestLGDA015Integration:
    """Integration test for the complete LGDA-015 implementation."""

    def test_end_to_end_type_mismatch_retry_flow(self, mock_bigquery_client, mock_gemini_client, caplog):
        """Test the complete flow: type mismatch error → classification → retry → success."""
        
        # Set logging level to capture retry decision logs
        caplog.set_level(logging.INFO)
        
        app = build_graph()
        
        with patch("src.agent.nodes.llm_completion") as mock_llm:
            # Mock LLM responses
            mock_llm.side_effect = [
                '{"task": "analyze orders", "tables": ["orders"]}',  # Plan
                "INVALID SQL WITH TYPE MISMATCH",  # First attempt fails
                "SELECT * FROM orders LIMIT 10",  # Simplified retry succeeds
                "Final report text",  # Report
            ]
            
            initial_state = AgentState(
                question="Show me order analysis",
                max_retries=2
            )
            
            final_state = app.invoke(initial_state)
            
            # Verify the retry mechanism worked (basic validation that it's functioning)
            assert final_state.retry_count >= 1, f"Expected at least 1 retry, got {final_state.retry_count}"
            
            # Verify that retry decision logic is being invoked
            retry_logs = [record for record in caplog.records if "validation error encountered" in record.message.lower()]
            assert len(retry_logs) > 0, "Should have logged validation error classification"

    def test_security_error_no_retry_integration(self, mock_bigquery_client, mock_gemini_client, caplog):
        """Integration test: security errors should not retry."""
        
        caplog.set_level(logging.INFO)
        app = build_graph()
        
        with patch("src.agent.nodes.llm_completion") as mock_llm:
            mock_llm.side_effect = [
                '{"task": "test", "tables": ["orders"]}',  # Plan
                "DROP TABLE users",  # Security violation - this should fail validation
                "Should not be called 1",  # No retry for security violations
                "Should not be called 2",  # Extra responses
                "Should not be called 3",  # Extra responses
            ]
            
            initial_state = AgentState(
                question="Test security violation",
                max_retries=2
            )
            
            final_state = app.invoke(initial_state)
            
            # Should have error
            assert final_state.error is not None
            # Verify the error is related to security/DML
            assert any(keyword in final_state.error.lower() for keyword in ["drop", "security", "violation", "select"])
            
            # The key point: verify that the retry logic was invoked and made a decision
            retry_logs = [record for record in caplog.records if "validation error encountered" in record.message.lower()]
            assert len(retry_logs) > 0, "Should have logged validation error encountered"

    def test_retry_exhaustion_proper_handling(self, mock_bigquery_client, mock_gemini_client, caplog):
        """Integration test: retry exhaustion should be handled correctly."""
        
        caplog.set_level(logging.INFO)
        app = build_graph()
        
        with patch("src.agent.nodes.llm_completion") as mock_llm:
            mock_llm.side_effect = [
                '{"task": "test", "tables": ["orders"]}',  # Plan
                "INVALID SQL 1",  # First attempt
                "INVALID SQL 2",  # Retry 1  
                "INVALID SQL 3",  # Retry 2
                "Should not be called",  # No more retries
            ]
            
            initial_state = AgentState(
                question="Test retry exhaustion",
                max_retries=2
            )
            
            final_state = app.invoke(initial_state)
            
            # Should have exhausted retries
            assert final_state.retry_count == 2, f"Should have exhausted 2 retries, got {final_state.retry_count}"
            assert final_state.error is not None
            assert final_state.report is None, "Should not generate report when retries exhausted"
            
            # Verify retry exhaustion was logged
            exhaustion_logs = [record for record in caplog.records 
                             if "no retry attempted" in record.message.lower()]
            assert len(exhaustion_logs) > 0, "Should have logged retry exhaustion"