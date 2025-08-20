"""Tests for error classification functionality."""

from unittest.mock import Mock

import pytest

from src.error.classification import ErrorClassifier, ErrorSeverity, RecoveryStrategy
from src.error.core import (
    BigQueryExecutionError,
    LGDAError,
    SqlGenerationError,
    TimeoutError,
)


class TestErrorClassifier:
    """Test error classification functionality."""

    @pytest.fixture
    def classifier(self):
        """Create error classifier instance."""
        return ErrorClassifier()

    def test_classifier_initialization(self, classifier):
        """Test classifier initialization."""
        assert classifier is not None
        assert hasattr(classifier, "_patterns")
        assert len(classifier._patterns) > 0

    # Test pattern-based classification
    def test_classify_timeout_error(self, classifier):
        """Test classification of timeout errors."""
        strategy, severity = classifier.classify("Connection timeout occurred")
        assert strategy == RecoveryStrategy.IMMEDIATE_RETRY
        assert severity == ErrorSeverity.MEDIUM

    def test_classify_rate_limit_error(self, classifier):
        """Test classification of rate limit errors."""
        strategy, severity = classifier.classify("Rate limit exceeded")
        assert strategy == RecoveryStrategy.EXPONENTIAL_BACKOFF
        assert severity == ErrorSeverity.MEDIUM

    def test_classify_bigquery_array_error(self, classifier):
        """Test classification of BigQuery Array null errors."""
        strategy, severity = classifier.classify("Array cannot have a null element")
        assert strategy == RecoveryStrategy.IMMEDIATE_RETRY
        assert severity == ErrorSeverity.MEDIUM

    def test_classify_permission_error(self, classifier):
        """Test classification of permission errors."""
        strategy, severity = classifier.classify("Permission denied")
        assert strategy == RecoveryStrategy.NO_RECOVERY
        assert severity == ErrorSeverity.CRITICAL

    def test_classify_syntax_error(self, classifier):
        """Test classification of SQL syntax errors."""
        strategy, severity = classifier.classify("Syntax error in SQL query")
        assert strategy == RecoveryStrategy.USER_GUIDED
        assert severity == ErrorSeverity.HIGH

    def test_classify_unknown_error(self, classifier):
        """Test classification of unknown errors."""
        strategy, severity = classifier.classify("Unknown strange error")
        assert strategy == RecoveryStrategy.USER_GUIDED
        assert severity == ErrorSeverity.MEDIUM

    # Test LGDA-specific error classification
    def test_classify_lgda_timeout_error(self, classifier):
        """Test classification of LGDA timeout errors."""
        error = TimeoutError("Operation timed out", timeout_seconds=300)
        strategy, severity = classifier.classify(error)
        assert strategy == RecoveryStrategy.EXPONENTIAL_BACKOFF
        assert severity == ErrorSeverity.MEDIUM

    def test_classify_lgda_sql_error(self, classifier):
        """Test classification of LGDA SQL generation errors."""
        error = SqlGenerationError("Failed to generate SQL")
        strategy, severity = classifier.classify(error)
        assert strategy == RecoveryStrategy.USER_GUIDED
        assert severity == ErrorSeverity.HIGH

    def test_classify_lgda_bigquery_error(self, classifier):
        """Test classification of LGDA BigQuery errors."""
        error = BigQueryExecutionError("Query execution failed")
        strategy, severity = classifier.classify(error)
        assert strategy == RecoveryStrategy.EXPONENTIAL_BACKOFF
        assert severity == ErrorSeverity.MEDIUM

    def test_classify_lgda_bigquery_array_error(self, classifier):
        """Test classification of LGDA BigQuery Array errors."""
        error = BigQueryExecutionError("Array cannot have a null element")
        strategy, severity = classifier.classify(error)
        assert strategy == RecoveryStrategy.IMMEDIATE_RETRY
        assert severity == ErrorSeverity.MEDIUM

    def test_classify_generic_lgda_error(self, classifier):
        """Test classification of generic LGDA errors."""
        error = LGDAError("Generic error", "GENERIC_ERROR")
        strategy, severity = classifier.classify(error)
        assert strategy == RecoveryStrategy.USER_GUIDED
        assert severity == ErrorSeverity.MEDIUM

    # Test transient error detection
    def test_is_transient_immediate_retry(self, classifier):
        """Test transient detection for immediate retry errors."""
        assert classifier.is_transient("timeout occurred") is True

    def test_is_transient_exponential_backoff(self, classifier):
        """Test transient detection for exponential backoff errors."""
        assert classifier.is_transient("rate limit exceeded") is True

    def test_is_transient_non_transient(self, classifier):
        """Test transient detection for non-transient errors."""
        assert classifier.is_transient("permission denied") is False
        assert classifier.is_transient("syntax error") is False

    # Test security error detection
    def test_is_security_error_permission_denied(self, classifier):
        """Test security error detection for permission denied."""
        assert classifier.is_security_error("Permission denied") is True

    def test_is_security_error_unauthorized(self, classifier):
        """Test security error detection for unauthorized."""
        assert classifier.is_security_error("Unauthorized access") is True

    def test_is_security_error_invalid_api_key(self, classifier):
        """Test security error detection for invalid API key."""
        assert classifier.is_security_error("Invalid API key") is True

    def test_is_security_error_non_security(self, classifier):
        """Test security error detection for non-security errors."""
        assert classifier.is_security_error("timeout occurred") is False
        assert classifier.is_security_error("syntax error") is False

    # Test user message generation
    def test_get_user_message_security_error(self, classifier):
        """Test user message for security errors."""
        message = classifier.get_user_message("Permission denied")
        assert "Access denied" in message
        assert "credentials" in message

    def test_get_user_message_array_error(self, classifier):
        """Test user message for BigQuery Array errors."""
        message = classifier.get_user_message("Array cannot have a null element")
        assert "Data processing issue" in message
        assert "fix" in message

    def test_get_user_message_timeout_error(self, classifier):
        """Test user message for timeout errors."""
        message = classifier.get_user_message("Connection timeout")
        assert "longer than expected" in message
        assert "Retrying" in message

    def test_get_user_message_rate_limit_error(self, classifier):
        """Test user message for rate limit errors."""
        message = classifier.get_user_message("Rate limit exceeded")
        assert "temporarily unavailable" in message
        assert "usage limits" in message

    def test_get_user_message_critical_error(self, classifier):
        """Test user message for critical errors."""
        # Create an error that gets classified as critical
        message = classifier.get_user_message("access denied")
        assert "Access denied" in message

    def test_get_user_message_high_severity_error(self, classifier):
        """Test user message for high severity errors."""
        message = classifier.get_user_message("Table not found")
        assert "Unable to complete" in message or "different approach" in message

    def test_get_user_message_default_error(self, classifier):
        """Test user message for default/unknown errors."""
        message = classifier.get_user_message("Some random error")
        assert "Temporary issue" in message or "automatically" in message


class TestErrorClassificationPatterns:
    """Test specific error classification patterns."""

    @pytest.fixture
    def classifier(self):
        """Create error classifier instance."""
        return ErrorClassifier()

    def test_network_error_patterns(self, classifier):
        """Test various network error patterns."""
        network_errors = [
            "connection reset by peer",
            "network timeout",
            "connection timeout occurred",
            "network error detected",
        ]

        for error in network_errors:
            strategy, severity = classifier.classify(error)
            assert strategy == RecoveryStrategy.IMMEDIATE_RETRY
            assert severity == ErrorSeverity.MEDIUM

    def test_quota_error_patterns(self, classifier):
        """Test various quota/rate limit patterns."""
        quota_errors = [
            "quota exceeded",
            "rate limit reached",
            "too many requests",
            "quota limit exceeded",
        ]

        for error in quota_errors:
            strategy, severity = classifier.classify(error)
            assert strategy == RecoveryStrategy.EXPONENTIAL_BACKOFF
            assert severity == ErrorSeverity.MEDIUM

    def test_bigquery_specific_patterns(self, classifier):
        """Test BigQuery specific error patterns."""
        # Array error should be immediate retry
        strategy, severity = classifier.classify("Array cannot have a null element")
        assert strategy == RecoveryStrategy.IMMEDIATE_RETRY

        # Table not found should be user guided (fixable by user)
        strategy, severity = classifier.classify("Table not found")
        assert strategy == RecoveryStrategy.USER_GUIDED

        # Dataset not found should be no recovery (system configuration issue)
        strategy, severity = classifier.classify("Dataset not found")
        assert strategy == RecoveryStrategy.NO_RECOVERY

    def test_security_patterns(self, classifier):
        """Test security-related error patterns."""
        security_errors = [
            "permission denied",
            "access denied",
            "unauthorized",
            "invalid api key",
            "authentication failed",
            "forbidden",
        ]

        for error in security_errors:
            assert classifier.is_security_error(error) is True
            strategy, severity = classifier.classify(error)
            assert strategy == RecoveryStrategy.NO_RECOVERY
            assert severity == ErrorSeverity.CRITICAL
