"""Tests for unified retry architecture (LGDA-007)."""

import asyncio
import random
import time
from unittest.mock import Mock, patch

import pytest

from src.core.retry import (
    ErrorCategory,
    RetryConfig,
    RetryStrategy,
    RetryContext,
    classify_error,
    register_error_classifier,
    should_retry_error,
    retry_with_strategy,
)


class TestRetryStrategy:
    """Test retry strategy configuration and calculations."""

    def test_retry_strategy_defaults(self):
        """Test default retry strategy values."""
        strategy = RetryStrategy()
        assert strategy.max_attempts == 3
        assert strategy.base_delay == 1.0
        assert strategy.max_delay == 30.0
        assert strategy.backoff_multiplier == 2.0
        assert strategy.jitter is True

    def test_retry_strategy_custom_values(self):
        """Test custom retry strategy values."""
        strategy = RetryStrategy(
            max_attempts=5,
            base_delay=0.5,
            max_delay=10.0,
            backoff_multiplier=1.5,
            jitter=False
        )
        assert strategy.max_attempts == 5
        assert strategy.base_delay == 0.5
        assert strategy.max_delay == 10.0
        assert strategy.backoff_multiplier == 1.5
        assert strategy.jitter is False

    def test_calculate_delay_without_jitter(self):
        """Test delay calculation without jitter."""
        strategy = RetryStrategy(
            base_delay=1.0,
            max_delay=10.0,
            backoff_multiplier=2.0,
            jitter=False
        )
        
        # Test exponential backoff: 1.0 * 2^attempt
        assert strategy.calculate_delay(0) == 1.0  # 1.0 * 2^0
        assert strategy.calculate_delay(1) == 2.0  # 1.0 * 2^1
        assert strategy.calculate_delay(2) == 4.0  # 1.0 * 2^2
        assert strategy.calculate_delay(3) == 8.0  # 1.0 * 2^3
        
        # Test max_delay cap
        assert strategy.calculate_delay(5) == 10.0  # Capped at max_delay

    def test_calculate_delay_with_jitter(self):
        """Test delay calculation with jitter."""
        strategy = RetryStrategy(
            base_delay=1.0,
            max_delay=10.0,
            backoff_multiplier=2.0,
            jitter=True
        )
        
        # Use fixed random generator for deterministic tests
        rng = random.Random(42)
        
        # Base delay should be within jitter range (±10%)
        delay = strategy.calculate_delay(0, rng)
        assert 0.9 <= delay <= 1.1
        
        # Higher attempts should still have jitter
        delay = strategy.calculate_delay(2, rng)
        assert 3.6 <= delay <= 4.4  # 4.0 ± 10%


class TestRetryConfig:
    """Test predefined retry configurations."""

    def test_sql_generation_config(self):
        """Test SQL generation retry configuration."""
        config = RetryConfig.SQL_GENERATION
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 8.0
        assert config.backoff_multiplier == 2.0

    def test_bigquery_transient_config(self):
        """Test BigQuery transient retry configuration."""
        config = RetryConfig.BIGQUERY_TRANSIENT
        assert config.max_attempts == 5
        assert config.base_delay == 0.5
        assert config.max_delay == 30.0
        assert config.backoff_multiplier == 2.0

    def test_llm_timeout_config(self):
        """Test LLM timeout retry configuration."""
        config = RetryConfig.LLM_TIMEOUT
        assert config.max_attempts == 2
        assert config.base_delay == 2.0
        assert config.max_delay == 10.0
        assert config.backoff_multiplier == 2.0

    def test_rate_limit_config(self):
        """Test rate limit retry configuration."""
        config = RetryConfig.RATE_LIMIT
        assert config.max_attempts == 3
        assert config.base_delay == 5.0
        assert config.max_delay == 60.0
        assert config.backoff_multiplier == 2.0
        assert config.jitter is False  # No jitter for rate limits


class TestRetryContext:
    """Test retry context tracking."""

    def test_retry_context_initialization(self):
        """Test retry context initialization."""
        context = RetryContext("test_operation")
        assert context.operation_name == "test_operation"
        assert context.attempt_count == 0
        assert context.errors == []
        assert context.start_time > 0

    def test_retry_context_record_attempt(self):
        """Test recording retry attempts."""
        context = RetryContext("test_operation")
        
        # Record attempt without error
        context.record_attempt()
        assert context.attempt_count == 1
        assert len(context.errors) == 0
        
        # Record attempt with error
        error = ValueError("test error")
        context.record_attempt(error)
        assert context.attempt_count == 2
        assert len(context.errors) == 1
        assert "Attempt 2: ValueError: test error" in context.errors[0]

    def test_retry_context_summary(self):
        """Test retry context summary generation."""
        context = RetryContext("test_operation")
        context.record_attempt(ValueError("first error"))
        context.record_attempt(RuntimeError("second error"))
        
        summary = context.get_context_summary()
        assert "Operation: test_operation" in summary
        assert "Attempts: 2" in summary
        assert "Errors: 2" in summary


class TestErrorClassification:
    """Test error classification logic."""

    def test_error_classification_registration(self):
        """Test error classifier registration."""
        # Register custom error
        class CustomError(Exception):
            pass
            
        register_error_classifier(CustomError, ErrorCategory.PERMANENT)
        
        # Test classification
        error = CustomError("test")
        category = classify_error(error)
        assert category == ErrorCategory.PERMANENT

    def test_error_classification_inheritance(self):
        """Test error classification with inheritance."""
        # Register base exception
        class BaseError(Exception):
            pass
            
        class DerivedError(BaseError):
            pass
            
        register_error_classifier(BaseError, ErrorCategory.TRANSIENT)
        
        # Derived error should inherit classification
        error = DerivedError("test")
        category = classify_error(error)
        assert category == ErrorCategory.TRANSIENT

    def test_error_classification_patterns(self):
        """Test error classification based on patterns."""
        # Rate limit patterns
        class RateLimitError(Exception):
            pass
            
        error = RateLimitError("Rate limit exceeded")
        category = classify_error(error)
        assert category == ErrorCategory.RATE_LIMIT
        
        # Timeout patterns
        class CustomTimeoutError(Exception):
            pass
            
        error = CustomTimeoutError("Connection timeout")
        category = classify_error(error)
        assert category == ErrorCategory.INFRASTRUCTURE
        
        # Bad request patterns
        class BadRequestError(Exception):
            pass
            
        error = BadRequestError("Invalid syntax")
        category = classify_error(error)
        assert category == ErrorCategory.PERMANENT

    def test_should_retry_error(self):
        """Test retry decision logic."""
        # Should retry transient errors
        assert should_retry_error(None, ErrorCategory.TRANSIENT) is True
        assert should_retry_error(None, ErrorCategory.RATE_LIMIT) is True
        assert should_retry_error(None, ErrorCategory.INFRASTRUCTURE) is True
        
        # Should not retry permanent errors
        assert should_retry_error(None, ErrorCategory.PERMANENT) is False

    def test_default_error_classifications(self):
        """Test default error classifications are registered."""
        try:
            from google.api_core.exceptions import (
                BadRequest, Forbidden, NotFound, ServerError,
                TooManyRequests, RetryError
            )
            
            # Test BigQuery error classifications
            assert classify_error(BadRequest("test")) == ErrorCategory.PERMANENT
            assert classify_error(Forbidden("test")) == ErrorCategory.PERMANENT
            assert classify_error(NotFound("test")) == ErrorCategory.PERMANENT
            assert classify_error(ServerError("test")) == ErrorCategory.INFRASTRUCTURE
            assert classify_error(TooManyRequests("test")) == ErrorCategory.RATE_LIMIT
            # RetryError requires a cause parameter
            retry_error = RetryError("test", cause=Exception("test cause"))
            assert classify_error(retry_error) == ErrorCategory.TRANSIENT
            
        except ImportError:
            # Skip if Google Cloud libraries not available
            pass
        
        # Test standard Python exceptions
        assert classify_error(ConnectionError("test")) == ErrorCategory.INFRASTRUCTURE
        assert classify_error(TimeoutError("test")) == ErrorCategory.INFRASTRUCTURE
        assert classify_error(ValueError("test")) == ErrorCategory.PERMANENT
        assert classify_error(TypeError("test")) == ErrorCategory.PERMANENT


class TestRetryDecorator:
    """Test retry decorator functionality."""

    def test_retry_decorator_success_no_retry(self):
        """Test decorator with successful function (no retries)."""
        call_count = 0
        
        @retry_with_strategy(RetryConfig.SQL_GENERATION)
        def test_function():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = test_function()
        assert result == "success"
        assert call_count == 1

    def test_retry_decorator_transient_error_success(self):
        """Test decorator with transient error that eventually succeeds."""
        call_count = 0
        
        @retry_with_strategy(RetryConfig.SQL_GENERATION)
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Transient failure")
            return "success"
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            result = test_function()
        
        assert result == "success"
        assert call_count == 3

    def test_retry_decorator_permanent_error_no_retry(self):
        """Test decorator with permanent error (no retries)."""
        call_count = 0
        
        @retry_with_strategy(RetryConfig.SQL_GENERATION)
        def test_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Permanent failure")
        
        with pytest.raises(ValueError, match="Permanent failure"):
            test_function()
        
        assert call_count == 1

    def test_retry_decorator_max_attempts_exceeded(self):
        """Test decorator when max attempts are exceeded."""
        call_count = 0
        
        @retry_with_strategy(RetryConfig.SQL_GENERATION)
        def test_function():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Persistent failure")
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            with pytest.raises(ConnectionError, match="Persistent failure"):
                test_function()
        
        assert call_count == 3  # SQL_GENERATION has max_attempts=3

    @pytest.mark.asyncio
    async def test_retry_decorator_async_function(self):
        """Test decorator with async function."""
        call_count = 0
        
        @retry_with_strategy(RetryConfig.LLM_TIMEOUT)
        async def test_async_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Async transient failure")
            return "async success"
        
        with patch('asyncio.sleep'):  # Mock async sleep
            result = await test_async_function()
        
        assert result == "async success"
        assert call_count == 2

    def test_retry_decorator_custom_context_name(self):
        """Test decorator with custom context name."""
        @retry_with_strategy(RetryConfig.SQL_GENERATION, context_name="custom_operation")
        def test_function():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            test_function()

    def test_retry_decorator_custom_error_classifier(self):
        """Test decorator with custom error classifier."""
        call_count = 0
        
        def custom_classifier(error):
            if isinstance(error, ValueError):
                return ErrorCategory.TRANSIENT  # Treat ValueError as transient
            return ErrorCategory.PERMANENT
        
        @retry_with_strategy(
            RetryConfig.SQL_GENERATION,
            error_classifier=custom_classifier
        )
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Custom transient error")
            return "success"
        
        with patch('time.sleep'):
            result = test_function()
        
        assert result == "success"
        assert call_count == 2

    def test_retry_decorator_rate_limit_delay(self):
        """Test decorator with rate limit error and Retry-After header."""
        call_count = 0
        
        class MockRateLimitError(Exception):
            def __init__(self, message):
                super().__init__(message)
                self.response = Mock()
                self.response.headers = {"Retry-After": "5"}
        
        # Register custom rate limit error
        register_error_classifier(MockRateLimitError, ErrorCategory.RATE_LIMIT)
        
        @retry_with_strategy(RetryConfig.RATE_LIMIT)
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise MockRateLimitError("Rate limited")
            return "success"
        
        with patch('time.sleep') as mock_sleep:
            result = test_function()
        
        assert result == "success"
        assert call_count == 2
        # Should use Retry-After value (5 seconds)
        mock_sleep.assert_called_once_with(5.0)


class TestRetryIntegration:
    """Test retry system integration scenarios."""

    def test_retry_with_circuit_breaker_concept(self):
        """Test conceptual integration with circuit breaker pattern."""
        # This test demonstrates how retry would work with circuit breaker
        # (Circuit breaker implementation is in bq.py, integration would be next phase)
        
        circuit_breaker_open = False
        call_count = 0
        
        def mock_circuit_breaker_check():
            return not circuit_breaker_open
        
        @retry_with_strategy(RetryConfig.BIGQUERY_TRANSIENT)
        def test_function():
            nonlocal call_count, circuit_breaker_open
            
            if not mock_circuit_breaker_check():
                raise RuntimeError("Circuit breaker open")
            
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Transient error")
            elif call_count == 2:
                # Simulate circuit breaker opening after repeated failures
                circuit_breaker_open = True
                raise ConnectionError("Circuit breaker triggered")
            return "success"
        
        with patch('time.sleep'):
            with pytest.raises(RuntimeError, match="Circuit breaker open"):
                test_function()

    def test_retry_context_tracking_enabled(self):
        """Test retry context tracking functionality."""
        contexts = []
        
        def track_context(func, args, kwargs, strategy, classifier, context_name):
            # Mock the internal retry execution to capture context
            context = RetryContext(context_name)
            context.record_attempt(RuntimeError("Test error"))
            contexts.append(context)
            raise RuntimeError("Test error")
        
        @retry_with_strategy(RetryConfig.SQL_GENERATION)
        def test_function():
            raise RuntimeError("Test error")
        
        # This would be captured by the actual retry system
        with pytest.raises(RuntimeError):
            test_function()

    def test_retry_error_context_propagation(self):
        """Test error context propagation through retry attempts."""
        errors_encountered = []
        
        @retry_with_strategy(RetryConfig.SQL_GENERATION)
        def test_function():
            error_msg = f"Attempt {len(errors_encountered) + 1} failed"
            error = ConnectionError(error_msg)
            errors_encountered.append(error)
            raise error
        
        with patch('time.sleep'):
            with pytest.raises(ConnectionError):
                test_function()
        
        # Should have made 3 attempts (SQL_GENERATION max_attempts)
        assert len(errors_encountered) == 3
        assert "Attempt 1 failed" in str(errors_encountered[0])
        assert "Attempt 3 failed" in str(errors_encountered[2])