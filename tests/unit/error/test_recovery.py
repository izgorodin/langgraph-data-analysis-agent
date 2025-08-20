"""Tests for recovery engine functionality."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock

from src.error.recovery import (
    RecoveryEngine,
    get_recovery_engine,
    set_recovery_engine
)
from src.error.classification import ErrorClassifier, RecoveryStrategy, ErrorSeverity
from src.error.core import (
    ErrorRecovery,
    LGDAError,
    SqlGenerationError,
    BigQueryExecutionError,
    TimeoutError
)


class TestRecoveryEngine:
    """Test recovery engine functionality."""
    
    @pytest.fixture
    def engine(self):
        """Create recovery engine instance."""
        return RecoveryEngine()
    
    @pytest.fixture
    def mock_classifier(self):
        """Create mock error classifier."""
        classifier = Mock(spec=ErrorClassifier)
        return classifier
    
    def test_recovery_engine_initialization(self, engine):
        """Test recovery engine initialization."""
        assert engine.classifier is not None
        assert isinstance(engine.classifier, ErrorClassifier)
        assert engine._retry_counts == {}
    
    def test_recovery_engine_with_custom_classifier(self, mock_classifier):
        """Test recovery engine with custom classifier."""
        engine = RecoveryEngine(classifier=mock_classifier)
        assert engine.classifier is mock_classifier
    
    @pytest.mark.asyncio
    async def test_handle_error_immediate_retry(self, engine):
        """Test error handling with immediate retry strategy."""
        error = Exception("timeout occurred")
        context = {"operation_id": "test_op"}
        
        recovery = await engine.handle_error(error, context=context)
        
        assert recovery.strategy == "immediate_retry"
        assert recovery.should_retry is True
        assert recovery.retry_delay == 0.1
        assert recovery.max_retries > 0
        assert "Retrying immediately" in recovery.message
    
    @pytest.mark.asyncio
    async def test_handle_error_exponential_backoff(self, engine):
        """Test error handling with exponential backoff strategy."""
        error = Exception("rate limit exceeded")
        context = {"operation_id": "test_op"}
        
        recovery = await engine.handle_error(error, context=context)
        
        assert recovery.strategy == "exponential_backoff"
        assert recovery.should_retry is True
        assert recovery.retry_delay >= 1.0
        assert recovery.max_retries > 0
        assert "backoff" in recovery.message
    
    @pytest.mark.asyncio
    async def test_handle_error_graceful_degradation(self, engine):
        """Test error handling with graceful degradation strategy."""
        error = Exception("model not found")
        context = {"operation_id": "test_op"}
        
        recovery = await engine.handle_error(error, context=context)
        
        assert recovery.strategy in ["model_fallback", "cached_fallback"]
        assert recovery.should_retry is True
        assert recovery.modified_input is not None
    
    @pytest.mark.asyncio
    async def test_handle_error_user_guided(self, engine):
        """Test error handling with user guided strategy."""
        error = Exception("syntax error in query")
        context = {"operation_id": "test_op"}
        
        recovery = await engine.handle_error(error, context=context)
        
        assert recovery.strategy in ["user_clarification", "general_user_guidance"]
        assert recovery.should_retry is False
        assert recovery.user_message is not None
    
    @pytest.mark.asyncio
    async def test_handle_error_no_recovery(self, engine):
        """Test error handling with no recovery strategy."""
        error = Exception("permission denied")
        context = {"operation_id": "test_op"}
        
        recovery = await engine.handle_error(error, context=context)
        
        assert recovery.strategy == "no_recovery"
        assert recovery.should_retry is False
        assert recovery.user_message is not None
    
    @pytest.mark.asyncio
    async def test_immediate_retry_exhaustion(self, engine):
        """Test immediate retry exhaustion after max attempts."""
        error = Exception("timeout occurred")
        context = {"operation_id": "exhaustion_test"}
        
        # Simulate multiple retries
        for i in range(4):  # Max retries is 3
            recovery = await engine.handle_error(error, context=context)
            if i < 3:
                assert recovery.should_retry is True
            else:
                assert recovery.should_retry is False
                assert "exhausted" in recovery.strategy
    
    @pytest.mark.asyncio
    async def test_exponential_backoff_delay_progression(self, engine):
        """Test exponential backoff delay progression."""
        error = Exception("rate limit exceeded")
        context = {"operation_id": "backoff_test"}
        
        delays = []
        for i in range(3):
            recovery = await engine.handle_error(error, context=context)
            delays.append(recovery.retry_delay)
        
        # Delays should increase exponentially: 1, 2, 4
        assert delays[0] == 1.0
        assert delays[1] == 2.0
        assert delays[2] == 4.0
    
    @pytest.mark.asyncio
    async def test_bigquery_array_error_handling(self, engine):
        """Test specific BigQuery Array error handling."""
        error = BigQueryExecutionError(
            "Array cannot have a null element",
            query="SELECT ARRAY[1, NULL, 3] as arr"
        )
        context = {"operation_id": "array_test"}
        
        recovery = await engine.handle_error(error, context=context)
        
        assert recovery.strategy == "immediate_retry"
        assert recovery.modified_input is not None
        assert "IGNORE NULLS" in recovery.modified_input or "IS NOT NULL" in recovery.modified_input
    
    @pytest.mark.asyncio
    async def test_graceful_degradation_model_fallback(self, engine):
        """Test graceful degradation with model fallback."""
        error = Exception("model unavailable")
        context = {"operation_id": "model_test"}
        
        recovery = await engine.handle_error(error, context=context)
        
        assert recovery.strategy == "model_fallback"
        assert recovery.modified_input == {"fallback_model": True}
        assert "alternative model" in recovery.message
    
    @pytest.mark.asyncio
    async def test_graceful_degradation_resource_limits(self, engine):
        """Test graceful degradation with resource limits."""
        error = Exception("out of memory")
        context = {"operation_id": "memory_test"}
        
        recovery = await engine.handle_error(error, context=context)
        
        assert recovery.strategy == "simplified_processing"
        assert recovery.modified_input["simplified"] is True
        assert "chunk_size" in recovery.modified_input
        assert "resource usage" in recovery.message
    
    @pytest.mark.asyncio
    async def test_user_guided_sql_error(self, engine):
        """Test user guided recovery for SQL errors."""
        error = Exception("SQL syntax error")
        context = {"operation_id": "sql_test"}
        
        recovery = await engine.handle_error(error, context=context)
        
        assert recovery.strategy == "user_clarification"
        assert recovery.should_retry is False
        assert "rephrase" in recovery.user_message
    
    @pytest.mark.asyncio
    async def test_user_guided_schema_error(self, engine):
        """Test user guided recovery for schema errors."""
        error = Exception("table not found")
        context = {"operation_id": "schema_test"}
        
        recovery = await engine.handle_error(error, context=context)
        
        assert recovery.strategy == "schema_guidance"
        assert recovery.should_retry is False
        assert "table or column" in recovery.user_message
    
    def test_retry_count_tracking(self, engine):
        """Test retry count tracking functionality."""
        assert engine.get_retry_count("test_op") == 0
        
        # Simulate retries
        engine._retry_counts["test_op"] = 3
        assert engine.get_retry_count("test_op") == 3
        
        # Reset retry count
        engine.reset_retry_count("test_op")
        assert engine.get_retry_count("test_op") == 0
    
    def test_bigquery_array_query_modification(self, engine):
        """Test BigQuery Array query modification logic."""
        error = BigQueryExecutionError(
            "Array cannot have a null element",
            query="SELECT ARRAY_AGG(value) FROM table"
        )
        
        modified_query = engine._handle_bigquery_array_error(error)
        assert modified_query is not None
        assert "IGNORE NULLS" in modified_query
    
    def test_bigquery_array_query_modification_no_array_error(self, engine):
        """Test query modification when not an array error."""
        error = BigQueryExecutionError(
            "Different error",
            query="SELECT * FROM table"
        )
        
        modified_query = engine._handle_bigquery_array_error(error)
        assert modified_query is None
    
    def test_bigquery_array_query_modification_no_query(self, engine):
        """Test query modification when no query is provided."""
        error = BigQueryExecutionError("Array cannot have a null element")
        
        modified_query = engine._handle_bigquery_array_error(error)
        assert modified_query is None


class TestRecoveryEngineWithSpecificErrors:
    """Test recovery engine with specific LGDA error types."""
    
    @pytest.fixture
    def engine(self):
        """Create recovery engine instance."""
        return RecoveryEngine()
    
    @pytest.mark.asyncio
    async def test_handle_timeout_error(self, engine):
        """Test handling of TimeoutError."""
        error = TimeoutError("Operation timed out", timeout_seconds=300)
        context = {"operation_id": "timeout_test"}
        
        recovery = await engine.handle_error(error, context=context)
        
        assert recovery.strategy == "exponential_backoff"
        assert recovery.should_retry is True
    
    @pytest.mark.asyncio
    async def test_handle_sql_generation_error(self, engine):
        """Test handling of SqlGenerationError."""
        error = SqlGenerationError("Failed to generate SQL")
        context = {"operation_id": "sql_gen_test"}
        
        recovery = await engine.handle_error(error, context=context)
        
        assert recovery.strategy in ["user_clarification", "general_user_guidance"]
        assert recovery.should_retry is False
    
    @pytest.mark.asyncio
    async def test_handle_bigquery_execution_error(self, engine):
        """Test handling of BigQueryExecutionError."""
        error = BigQueryExecutionError("Query failed")
        context = {"operation_id": "bq_test"}
        
        recovery = await engine.handle_error(error, context=context)
        
        assert recovery.strategy == "exponential_backoff"
        assert recovery.should_retry is True
    
    @pytest.mark.asyncio
    async def test_handle_generic_lgda_error(self, engine):
        """Test handling of generic LGDAError."""
        error = LGDAError("Generic error", "GENERIC_ERROR")
        context = {"operation_id": "generic_test"}
        
        recovery = await engine.handle_error(error, context=context)
        
        assert recovery.strategy in ["general_user_guidance", "user_guided"]
        # Could be either retry or no retry depending on classification


class TestGlobalRecoveryEngine:
    """Test global recovery engine functions."""
    
    def test_get_recovery_engine_singleton(self):
        """Test that get_recovery_engine returns singleton."""
        engine1 = get_recovery_engine()
        engine2 = get_recovery_engine()
        assert engine1 is engine2
    
    def test_set_recovery_engine(self):
        """Test setting custom recovery engine."""
        original_engine = get_recovery_engine()
        custom_classifier = Mock(spec=ErrorClassifier)
        custom_engine = RecoveryEngine(classifier=custom_classifier)
        
        set_recovery_engine(custom_engine)
        current_engine = get_recovery_engine()
        
        assert current_engine is custom_engine
        assert current_engine.classifier is custom_classifier
        
        # Reset to original for other tests
        set_recovery_engine(original_engine)


class TestRecoveryEngineIntegration:
    """Integration tests for recovery engine."""
    
    @pytest.fixture
    def engine(self):
        """Create recovery engine instance."""
        return RecoveryEngine()
    
    @pytest.mark.asyncio
    async def test_full_recovery_cycle_with_success(self, engine):
        """Test full recovery cycle that succeeds."""
        error = Exception("timeout occurred")
        context = {"operation_id": "full_cycle_test"}
        
        # First attempt
        recovery1 = await engine.handle_error(error, context=context)
        assert recovery1.should_retry is True
        assert recovery1.strategy == "immediate_retry"
        
        # Simulate successful retry - reset count
        engine.reset_retry_count("full_cycle_test")
        
        # Verify count is reset
        assert engine.get_retry_count("full_cycle_test") == 0
    
    @pytest.mark.asyncio
    async def test_escalation_from_immediate_to_backoff(self, engine):
        """Test escalation from immediate retry to backoff."""
        timeout_error = Exception("timeout occurred")
        rate_limit_error = Exception("rate limit exceeded")
        context = {"operation_id": "escalation_test"}
        
        # Start with immediate retry error
        recovery1 = await engine.handle_error(timeout_error, context=context)
        assert recovery1.strategy == "immediate_retry"
        
        # Switch to rate limit error (should use backoff)
        context["operation_id"] = "escalation_test_2"  # Different operation
        recovery2 = await engine.handle_error(rate_limit_error, context=context)
        assert recovery2.strategy == "exponential_backoff"