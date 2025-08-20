"""Tests for core error classes and functionality."""

from datetime import datetime
from unittest.mock import patch

import pytest

from src.error.core import (
    BigQueryExecutionError,
    ErrorRecovery,
    LGDAError,
    SqlGenerationError,
    TimeoutError,
)


class TestLGDAError:
    """Test base LGDA error class."""

    def test_lgda_error_creation(self):
        """Test basic LGDA error creation."""
        error = LGDAError(
            message="Test error", error_code="TEST_ERROR", context={"key": "value"}
        )

        assert error.message == "Test error"
        assert error.error_code == "TEST_ERROR"
        assert error.context == {"key": "value"}
        assert isinstance(error.timestamp, datetime)
        assert str(error) == "[TEST_ERROR] Test error"

    def test_lgda_error_without_context(self):
        """Test LGDA error creation without context."""
        error = LGDAError("Test error", "TEST_ERROR")

        assert error.context == {}
        assert error.message == "Test error"

    def test_lgda_error_to_dict(self):
        """Test error serialization to dictionary."""
        error = LGDAError("Test error", "TEST_ERROR", {"key": "value"})
        error_dict = error.to_dict()

        expected_keys = {"error_code", "message", "context", "timestamp", "type"}
        assert set(error_dict.keys()) == expected_keys
        assert error_dict["error_code"] == "TEST_ERROR"
        assert error_dict["message"] == "Test error"
        assert error_dict["context"] == {"key": "value"}
        assert error_dict["type"] == "LGDAError"


class TestSqlGenerationError:
    """Test SQL generation specific errors."""

    def test_sql_generation_error_creation(self):
        """Test SQL generation error creation."""
        error = SqlGenerationError(
            message="Invalid SQL syntax",
            context={"table": "users"},
            query_fragment="SELECT * FROM",
        )

        assert error.message == "Invalid SQL syntax"
        assert error.error_code == "SQL_GENERATION_ERROR"
        assert error.query_fragment == "SELECT * FROM"
        assert error.context == {"table": "users"}

    def test_sql_generation_error_without_query(self):
        """Test SQL generation error without query fragment."""
        error = SqlGenerationError("Invalid SQL")

        assert error.query_fragment is None
        assert error.context == {}


class TestBigQueryExecutionError:
    """Test BigQuery execution specific errors."""

    def test_bigquery_execution_error_creation(self):
        """Test BigQuery execution error creation."""
        error = BigQueryExecutionError(
            message="Query failed",
            context={"project": "test-project"},
            job_id="job_123",
            query="SELECT 1",
        )

        assert error.message == "Query failed"
        assert error.error_code == "BIGQUERY_EXECUTION_ERROR"
        assert error.job_id == "job_123"
        assert error.query == "SELECT 1"
        assert error.context == {"project": "test-project"}

    def test_bigquery_execution_error_minimal(self):
        """Test BigQuery execution error with minimal parameters."""
        error = BigQueryExecutionError("Query failed")

        assert error.job_id is None
        assert error.query is None
        assert error.context == {}


class TestTimeoutError:
    """Test timeout specific errors."""

    def test_timeout_error_creation(self):
        """Test timeout error creation."""
        error = TimeoutError(
            message="Operation timed out",
            context={"operation": "bigquery_query"},
            timeout_seconds=300,
            operation="bigquery_execution",
        )

        assert error.message == "Operation timed out"
        assert error.error_code == "OPERATION_TIMEOUT"
        assert error.timeout_seconds == 300
        assert error.operation == "bigquery_execution"
        assert error.context == {"operation": "bigquery_query"}

    def test_timeout_error_minimal(self):
        """Test timeout error with minimal parameters."""
        error = TimeoutError("Timeout")

        assert error.timeout_seconds is None
        assert error.operation is None
        assert error.context == {}


class TestErrorRecovery:
    """Test error recovery data structure."""

    def test_error_recovery_creation(self):
        """Test error recovery creation."""
        recovery = ErrorRecovery(
            strategy="immediate_retry",
            modified_input="modified_query",
            message="Retrying operation",
            retry_delay=1.0,
            max_retries=3,
            should_retry=True,
            user_message="Please wait...",
        )

        assert recovery.strategy == "immediate_retry"
        assert recovery.modified_input == "modified_query"
        assert recovery.message == "Retrying operation"
        assert recovery.retry_delay == 1.0
        assert recovery.max_retries == 3
        assert recovery.should_retry is True
        assert recovery.user_message == "Please wait..."

    def test_error_recovery_defaults(self):
        """Test error recovery with default values."""
        recovery = ErrorRecovery(strategy="no_retry")

        assert recovery.strategy == "no_retry"
        assert recovery.modified_input is None
        assert recovery.message == ""
        assert recovery.retry_delay == 0.0
        assert recovery.max_retries == 0
        assert recovery.should_retry is True
        assert recovery.user_message is None

    def test_error_recovery_to_dict(self):
        """Test error recovery serialization."""
        recovery = ErrorRecovery(
            strategy="immediate_retry",
            modified_input="modified_query",
            message="Retrying",
            retry_delay=1.0,
            max_retries=3,
            should_retry=True,
            user_message="Wait...",
        )

        recovery_dict = recovery.to_dict()

        expected_keys = {
            "strategy",
            "modified_input",
            "message",
            "retry_delay",
            "max_retries",
            "should_retry",
            "user_message",
        }
        assert set(recovery_dict.keys()) == expected_keys
        assert recovery_dict["strategy"] == "immediate_retry"
        assert recovery_dict["modified_input"] == "modified_query"
        assert recovery_dict["should_retry"] is True
