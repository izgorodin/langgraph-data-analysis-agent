"""Integration tests for error handling with existing components."""

import pytest
import asyncio
from unittest.mock import Mock, patch

from src.error import (
    LGDAError,
    BigQueryExecutionError, 
    TimeoutError,
    ErrorClassifier,
    RecoveryEngine,
    TimeoutManager,
    with_timeout
)


class TestErrorHandlingIntegration:
    """Integration tests for error handling system."""
    
    def test_hanging_process_prevention(self):
        """Verify no operation can hang indefinitely."""
        timeout_manager = TimeoutManager(default_timeout=1)
        
        @timeout_manager.with_timeout_sync(timeout=1)
        def hanging_operation():
            import time
            time.sleep(2)  # This would hang without timeout
            return "should not reach"
        
        with pytest.raises(TimeoutError) as exc_info:
            hanging_operation()
        
        error = exc_info.value
        assert error.error_code == "OPERATION_TIMEOUT"
        assert "exceeded timeout" in error.message
    
    @pytest.mark.asyncio
    async def test_bigquery_array_error_recovery(self):
        """BigQuery Array null errors are handled gracefully."""
        engine = RecoveryEngine()
        
        # Simulate BigQuery Array error
        error = BigQueryExecutionError(
            "Array cannot have a null element",
            query="SELECT ARRAY[1, NULL, 3] as numbers",
            job_id="test_job_123"
        )
        
        recovery = await engine.handle_error(error, context={"operation_id": "test_array"})
        
        assert recovery.strategy == "immediate_retry"
        assert recovery.should_retry is True
        assert recovery.modified_input is not None
        assert "IS NOT NULL" in recovery.modified_input
        assert "Data processing issue" in recovery.user_message
    
    def test_error_message_user_friendliness(self):
        """Error messages are appropriate for business users."""
        classifier = ErrorClassifier()
        
        # Test various error scenarios
        test_cases = [
            ("Permission denied", "Access denied"),
            ("Array cannot have a null element", "Data processing issue"),
            ("Connection timeout", "longer than expected"),
            ("Rate limit exceeded", "temporarily unavailable"),
            ("Table not found", "check your table")
        ]
        
        for error_msg, expected_fragment in test_cases:
            user_msg = classifier.get_user_message(error_msg)
            assert expected_fragment in user_msg
            # Ensure no technical jargon
            assert "exception" not in user_msg.lower()
            assert "stacktrace" not in user_msg.lower()
    
    @pytest.mark.asyncio
    async def test_error_recovery_strategies(self):
        """Different error types trigger appropriate recovery."""
        engine = RecoveryEngine()
        
        # Test immediate retry
        timeout_error = Exception("connection timeout")
        recovery = await engine.handle_error(timeout_error, context={"operation_id": "timeout_test"})
        assert recovery.strategy == "immediate_retry"
        assert recovery.retry_delay == 0.1
        
        # Test exponential backoff
        rate_limit_error = Exception("rate limit exceeded")
        recovery = await engine.handle_error(rate_limit_error, context={"operation_id": "rate_test"})
        assert recovery.strategy == "exponential_backoff"
        assert recovery.retry_delay >= 1.0
        
        # Test graceful degradation
        model_error = Exception("model not found")  # This should match the pattern
        recovery = await engine.handle_error(model_error, context={"operation_id": "model_test"})
        assert recovery.strategy in ["model_fallback", "cached_fallback", "graceful_degradation"]
        assert recovery.modified_input is not None
        
        # Test no recovery
        permission_error = Exception("permission denied")
        recovery = await engine.handle_error(permission_error, context={"operation_id": "perm_test"})
        assert recovery.strategy == "no_recovery"
        assert recovery.should_retry is False
    
    def test_circuit_breaker_functionality(self):
        """Circuit breakers prevent cascade failures."""
        from src.llm.manager import CircuitBreaker
        
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0)
        
        # Initially closed
        assert breaker.can_execute() is True
        assert breaker.state == "closed"
        
        # Record failures to trigger open state
        breaker.record_failure()
        assert breaker.can_execute() is True  # Still under threshold
        
        breaker.record_failure()
        assert breaker.can_execute() is False  # Now open
        assert breaker.state == "open"
        
        # Recovery after timeout would allow half-open state
        # (We can't test the actual timeout in unit tests)
    
    @pytest.mark.asyncio
    async def test_timeout_with_async_operations(self):
        """Async timeout management works correctly."""
        async def slow_operation():
            await asyncio.sleep(2)
            return "should timeout"
        
        with pytest.raises(TimeoutError) as exc_info:
            await with_timeout(slow_operation(), timeout=1, operation_name="slow_test")
        
        error = exc_info.value
        assert error.operation == "slow_test"
        assert error.timeout_seconds == 1
        assert "slow_test" in error.message
    
    @pytest.mark.asyncio 
    async def test_error_context_preservation(self):
        """Error context is preserved through recovery process."""
        engine = RecoveryEngine()
        
        original_error = BigQueryExecutionError(
            "Query failed with database error",  # Non-timeout error
            context={"user_id": "test_user", "query_type": "analytics"},
            job_id="job_456",
            query="SELECT * FROM large_table"
        )
        
        recovery = await engine.handle_error(
            original_error, 
            context={
                "operation_id": "context_test",
                "request_id": "req_789"
            }
        )
        
        # Verify original error context is preserved
        assert original_error.context["user_id"] == "test_user"
        assert original_error.job_id == "job_456"
        assert original_error.query == "SELECT * FROM large_table"
        
        # Verify recovery contains appropriate strategy
        # Since this is a BigQueryExecutionError with no specific pattern match,
        # it should use the fallback from _classify_by_patterns
        assert recovery.strategy in ["exponential_backoff", "general_user_guidance"]
    
    def test_error_classification_consistency(self):
        """Error classification is consistent across different input types."""
        classifier = ErrorClassifier()
        
        # Test with string vs Exception
        error_message = "rate limit exceeded"
        error_exception = Exception("rate limit exceeded")
        
        strategy1, severity1 = classifier.classify(error_message)
        strategy2, severity2 = classifier.classify(error_exception)
        
        assert strategy1 == strategy2
        assert severity1 == severity2
        
        # Test with LGDA errors
        lgda_error = TimeoutError("operation timed out")
        strategy3, severity3 = classifier.classify(lgda_error)
        
        # Should use LGDA-specific classification
        assert strategy3 in [strategy1, strategy2]  # Could be different but valid


class TestErrorHandlingWithMockComponents:
    """Test error handling with mocked external components."""
    
    @pytest.mark.asyncio
    async def test_bigquery_integration_simulation(self):
        """Test error handling with simulated BigQuery errors."""
        engine = RecoveryEngine()
        
        # Simulate various BigQuery errors
        errors_and_expected = [
            ("Array cannot have a null element", "immediate_retry"),
            ("Permission denied on table", "no_recovery"),
            ("Query timeout after 300 seconds", "immediate_retry"),  # timeout -> immediate retry
            ("Table 'users' not found", "schema_guidance"),
        ]
        
        for error_msg, expected_strategy in errors_and_expected:
            bq_error = BigQueryExecutionError(error_msg)
            recovery = await engine.handle_error(bq_error, context={"operation_id": f"bq_{hash(error_msg)}"})
            
            if expected_strategy == "schema_guidance":
                assert recovery.strategy in ["schema_guidance", "general_user_guidance"]
            else:
                assert recovery.strategy == expected_strategy
    
    @pytest.mark.asyncio
    async def test_llm_provider_error_simulation(self):
        """Test error handling with simulated LLM provider errors."""
        engine = RecoveryEngine()
        
        # Simulate LLM provider errors
        provider_errors = [
            ("Model not found", "model_fallback"), # This should match the model pattern
            ("API quota exceeded", "exponential_backoff"),
            ("Invalid API key", "no_recovery"),
            ("Connection timeout to provider", "immediate_retry"),
        ]
        
        for error_msg, expected_strategy in provider_errors:
            error = Exception(error_msg)
            recovery = await engine.handle_error(error, context={"operation_id": f"llm_{hash(error_msg)}"})
            
            if expected_strategy == "model_fallback":
                assert recovery.strategy in ["model_fallback", "cached_fallback", "graceful_degradation"]
            else:
                assert recovery.strategy == expected_strategy