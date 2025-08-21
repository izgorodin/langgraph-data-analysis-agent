"""Error classification and recovery strategy mapping."""

from __future__ import annotations

import re
from enum import Enum
from typing import Union

from .core import LGDAError


class ErrorSeverity(Enum):
    """Error severity levels."""

    LOW = "low"  # Minor issues, degraded functionality
    MEDIUM = "medium"  # Significant issues, partial functionality loss
    HIGH = "high"  # Critical issues, major functionality loss
    CRITICAL = "critical"  # System failure, complete functionality loss


class RecoveryStrategy(Enum):
    """Recovery strategy types."""

    IMMEDIATE_RETRY = "immediate_retry"  # < 1 second
    EXPONENTIAL_BACKOFF = "exponential_backoff"  # 1-10 seconds
    GRACEFUL_DEGRADATION = "graceful_degradation"  # Use fallback/cache
    USER_GUIDED = "user_guided"  # > 10 seconds, ask user
    NO_RECOVERY = "no_recovery"  # Permanent failure


class ErrorClassifier:
    """Classifies errors and maps them to recovery strategies."""

    def __init__(self):
        # Error pattern mapping for classification
        self._patterns = [
            # Security errors - no recovery (check first, more specific)
            (
                r"permission.*denied|access.*denied|unauthorized|invalid.*api.*key|authentication.*failed|forbidden",
                RecoveryStrategy.NO_RECOVERY,
                ErrorSeverity.CRITICAL,
            ),
            # Network/timeout errors - immediate retry
            (
                r"timeout|connection.*reset|network.*error",
                RecoveryStrategy.IMMEDIATE_RETRY,
                ErrorSeverity.MEDIUM,
            ),
            (
                r"rate.*limit|quota.*exceeded|too.*many.*requests",
                RecoveryStrategy.EXPONENTIAL_BACKOFF,
                ErrorSeverity.MEDIUM,
            ),
            # BigQuery specific errors
            (
                r"Array cannot have a null element",
                RecoveryStrategy.IMMEDIATE_RETRY,
                ErrorSeverity.MEDIUM,
            ),
            (r"dataset.*not.*found", RecoveryStrategy.NO_RECOVERY, ErrorSeverity.HIGH),
            # LLM provider errors
            (
                r"model.*not.*found|model.*unavailable",
                RecoveryStrategy.GRACEFUL_DEGRADATION,
                ErrorSeverity.HIGH,
            ),
            # SQL and schema errors - user guided (retryable with simplification)
            (
                r"syntax.*error|invalid.*sql|parse.*error",
                RecoveryStrategy.USER_GUIDED,
                ErrorSeverity.HIGH,
            ),
            (
                r"type.*mismatch|timestamp.*vs.*date|data.*type.*mismatch",
                RecoveryStrategy.USER_GUIDED,
                ErrorSeverity.MEDIUM,
            ),
            (
                r"table.*not.*found|column.*not.*found",
                RecoveryStrategy.USER_GUIDED,
                ErrorSeverity.MEDIUM,
            ),
            # Security violations - permanent (non-retryable)
            (
                r"forbidden.*table|not.*in.*allowed.*tables|security.*violation",
                RecoveryStrategy.NO_RECOVERY,
                ErrorSeverity.CRITICAL,
            ),
            # System errors
            (
                r"out.*of.*memory|disk.*full",
                RecoveryStrategy.GRACEFUL_DEGRADATION,
                ErrorSeverity.HIGH,
            ),
            (
                r"internal.*server.*error",
                RecoveryStrategy.EXPONENTIAL_BACKOFF,
                ErrorSeverity.MEDIUM,
            ),
        ]

    def classify(
        self, error: Union[Exception, str]
    ) -> tuple[RecoveryStrategy, ErrorSeverity]:
        """
        Classify an error and return appropriate recovery strategy and severity.

        Args:
            error: Exception instance or error message string

        Returns:
            Tuple of (RecoveryStrategy, ErrorSeverity)
        """
        # Pattern matching on error message
        error_message = str(error).lower()

        # Check error type first for known LGDA errors
        if isinstance(error, LGDAError):
            return self._classify_lgda_error(error)

        # Pattern matching on error message
        for pattern, strategy, severity in self._patterns:
            if re.search(pattern, error_message, re.IGNORECASE):
                return strategy, severity

        # Default classification for unknown errors
        return RecoveryStrategy.USER_GUIDED, ErrorSeverity.MEDIUM

    def _classify_lgda_error(
        self, error: LGDAError
    ) -> tuple[RecoveryStrategy, ErrorSeverity]:
        """Classify LGDA-specific errors."""
        from .core import BigQueryExecutionError, SqlGenerationError, TimeoutError

        if isinstance(error, TimeoutError):
            return RecoveryStrategy.EXPONENTIAL_BACKOFF, ErrorSeverity.MEDIUM
        elif isinstance(error, SqlGenerationError):
            return RecoveryStrategy.USER_GUIDED, ErrorSeverity.HIGH
        elif isinstance(error, BigQueryExecutionError):
            # Check specific BigQuery error patterns first
            if "Array cannot have a null element" in error.message:
                return RecoveryStrategy.IMMEDIATE_RETRY, ErrorSeverity.MEDIUM
            # For other BigQuery execution errors, use pattern-based classification first
            result = self._classify_by_patterns(error.message)
            # Only override to exponential backoff if no specific pattern was matched
            # (i.e., only for generic execution failures, not schema/permission errors)
            if result == (RecoveryStrategy.USER_GUIDED, ErrorSeverity.MEDIUM):
                # Check if this is a schema/permission issue that should stay USER_GUIDED
                error_lower = error.message.lower()
                schema_patterns = [
                    "not found",
                    "does not exist",
                    "syntax error",
                    "invalid",
                ]
                if any(pattern in error_lower for pattern in schema_patterns):
                    return result  # Keep USER_GUIDED for schema issues
                # For other generic execution errors, use exponential backoff
                return RecoveryStrategy.EXPONENTIAL_BACKOFF, ErrorSeverity.MEDIUM
            return result

        return RecoveryStrategy.USER_GUIDED, ErrorSeverity.MEDIUM

    def _classify_by_patterns(
        self, error_message: str
    ) -> tuple[RecoveryStrategy, ErrorSeverity]:
        """Classify error by pattern matching."""
        error_message = error_message.lower()

        # Pattern matching on error message
        for pattern, strategy, severity in self._patterns:
            if re.search(pattern, error_message, re.IGNORECASE):
                return strategy, severity

        # Default classification
        return RecoveryStrategy.USER_GUIDED, ErrorSeverity.MEDIUM

    def is_transient(self, error: Union[Exception, str]) -> bool:
        """
        Determine if an error is transient (likely to succeed on retry).

        Args:
            error: Exception instance or error message

        Returns:
            True if error is likely transient
        """
        strategy, _ = self.classify(error)
        return strategy in {
            RecoveryStrategy.IMMEDIATE_RETRY,
            RecoveryStrategy.EXPONENTIAL_BACKOFF,
        }

    def is_security_error(self, error: Union[Exception, str]) -> bool:
        """
        Determine if an error is security-related (should not be retried).

        Args:
            error: Exception instance or error message

        Returns:
            True if error is security-related
        """
        error_message = str(error).lower()
        security_patterns = [
            r"permission.*denied",
            r"access.*denied",
            r"unauthorized",
            r"invalid.*api.*key",
            r"authentication.*failed",
            r"forbidden",
        ]

        return any(
            re.search(pattern, error_message, re.IGNORECASE)
            for pattern in security_patterns
        )

    def get_user_message(self, error: Union[Exception, str]) -> str:
        """
        Generate user-friendly error message.

        Args:
            error: Exception instance or error message

        Returns:
            User-friendly error message
        """
        strategy, severity = self.classify(error)
        error_message = str(error)

        if self.is_security_error(error):
            return "Access denied. Please check your permissions and credentials."

        if "Array cannot have a null element" in error_message:
            return "Data processing issue detected. Automatically applying fix..."

        if "timeout" in error_message.lower():
            return "Operation took longer than expected. Retrying..."

        if "rate limit" in error_message.lower() or "quota" in error_message.lower():
            return "Service temporarily unavailable due to usage limits. Retrying shortly..."

        if (
            "table not found" in error_message.lower()
            or "column not found" in error_message.lower()
        ):
            return (
                "Unable to complete request. Please check your table or column names."
            )

        if severity == ErrorSeverity.CRITICAL:
            return "Critical system error. Please contact support."
        elif severity == ErrorSeverity.HIGH:
            return "Unable to complete request. Please try a different approach."
        else:
            return "Temporary issue encountered. Retrying automatically..."
