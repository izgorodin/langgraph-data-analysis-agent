"""Tests for BigQuery unified retry migration (LGDA-007)."""

import os
from unittest.mock import patch, Mock

import pytest

from src.core.migration import (
    UNIFIED_RETRY_ENABLED,
    bigquery_retry_decorator,
    create_bigquery_compatible_strategy,
    get_bigquery_retry_strategy,
    migrate_legacy_retry_function,
)


class TestMigrationHelpers:
    """Test migration helper functions."""

    def test_create_bigquery_compatible_strategy(self):
        """Test creating BigQuery-compatible retry strategy."""
        strategy = create_bigquery_compatible_strategy(
            max_attempts=5,
            base_delay_ms=200,
            jitter_ms=100
        )
        
        assert strategy.max_attempts == 5
        assert strategy.base_delay == 0.2  # 200ms converted to seconds
        assert strategy.max_delay == 30.0
        assert strategy.backoff_multiplier == 2.0
        assert strategy.jitter is True

    def test_get_bigquery_retry_strategy(self):
        """Test getting BigQuery retry strategy."""
        strategy = get_bigquery_retry_strategy()
        
        # Should return either unified or legacy-compatible strategy
        assert strategy.max_attempts >= 1
        assert strategy.base_delay > 0
        assert strategy.max_delay > 0

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    def test_bigquery_retry_decorator_unified_enabled(self):
        """Test BigQuery retry decorator when unified retry is enabled."""
        call_count = 0
        
        @bigquery_retry_decorator(max_attempts=3)
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Test transient error")
            return "success"
        
        with patch('time.sleep'):  # Mock sleep for speed
            result = test_function()
        
        assert result == "success"
        assert call_count == 2

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "false"})
    def test_bigquery_retry_decorator_unified_disabled(self):
        """Test BigQuery retry decorator when unified retry is disabled."""
        call_count = 0
        
        @bigquery_retry_decorator(max_attempts=3)
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Test transient error")
            return "success"
        
        # With unified retry disabled, should fall back to legacy (no retry in this test)
        with pytest.raises(ConnectionError):
            test_function()
        
        assert call_count == 1  # Should only be called once, no retry

    def test_migrate_legacy_retry_function_enabled(self):
        """Test migrating legacy retry function when unified retry is enabled."""
        call_count = 0
        
        def legacy_function(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2 and 'cause_error' in kwargs:
                raise ConnectionError("Legacy transient error")
            return f"legacy_result_{call_count}"
        
        with patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"}):
            migrated_function = migrate_legacy_retry_function(legacy_function)
            
            with patch('time.sleep'):
                result = migrated_function(cause_error=True)
        
        assert result == "legacy_result_2"
        assert call_count == 2

    def test_migrate_legacy_retry_function_disabled(self):
        """Test migrating legacy retry function when unified retry is disabled."""
        call_count = 0
        
        def legacy_function(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return f"legacy_result_{call_count}"
        
        with patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "false"}):
            migrated_function = migrate_legacy_retry_function(legacy_function)
            result = migrated_function()
        
        # Should return original function unchanged
        assert result == "legacy_result_1"
        assert call_count == 1
        # The function should be the same (no wrapper when disabled)
        assert migrated_function is legacy_function


class TestBigQueryIntegration:
    """Test BigQuery integration with unified retry."""

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"})
    def test_run_query_with_unified_retry(self):
        """Test BigQuery run_query with unified retry enabled."""
        from src.bq import run_query
        from src.core.migration import is_unified_retry_enabled
        
        assert is_unified_retry_enabled() is True
        
        # Mock BigQuery client and operations
        with patch('src.bq.bq_client') as mock_client, \
             patch('src.bq._circuit_breaker') as mock_breaker:
            
            mock_breaker.can_execute.return_value = True
            mock_job = Mock()
            mock_job.result.return_value = Mock()
            mock_job.result.return_value.to_dataframe.return_value = "mock_dataframe"
            mock_client.return_value.query.return_value = mock_job
            
            result = run_query("SELECT 1", dry_run=False)
            
            assert result == "mock_dataframe"
            mock_client.assert_called_once()
            mock_breaker.record_success.assert_called_once()

    @patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "false"})  
    def test_run_query_with_legacy_retry(self):
        """Test BigQuery run_query with legacy retry enabled."""
        from src.bq import run_query
        from src.core.migration import is_unified_retry_enabled
        
        assert is_unified_retry_enabled() is False
        
        # Mock BigQuery client and operations
        with patch('src.bq.bq_client') as mock_client, \
             patch('src.bq._circuit_breaker') as mock_breaker:
            
            mock_breaker.can_execute.return_value = True
            mock_job = Mock()
            mock_job.result.return_value = Mock()
            mock_job.result.return_value.to_dataframe.return_value = "mock_dataframe"
            mock_client.return_value.query.return_value = mock_job
            
            result = run_query("SELECT 1", dry_run=False)
            
            assert result == "mock_dataframe"
            mock_client.assert_called_once()
            mock_breaker.record_success.assert_called_once()

    def test_error_classification_registration(self):
        """Test that BigQuery error classifications are properly registered."""
        from src.core.retry import classify_error, ErrorCategory
        
        try:
            from google.api_core.exceptions import (
                BadRequest, ServerError, TooManyRequests
            )
            
            # Test BigQuery error classifications
            assert classify_error(BadRequest("test")) == ErrorCategory.PERMANENT
            assert classify_error(ServerError("test")) == ErrorCategory.INFRASTRUCTURE  
            assert classify_error(TooManyRequests("test")) == ErrorCategory.RATE_LIMIT
            
        except ImportError:
            # Skip if Google Cloud libraries not available
            pytest.skip("Google Cloud libraries not available")

    def test_feature_flag_environment_variable(self):
        """Test that feature flag responds to environment variable."""
        from src.core.migration import is_unified_retry_enabled
        
        with patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "true"}):
            assert is_unified_retry_enabled() is True
        
        with patch.dict(os.environ, {"LGDA_USE_UNIFIED_RETRY": "false"}):
            assert is_unified_retry_enabled() is False