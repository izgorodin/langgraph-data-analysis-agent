"""Custom BigQuery error classes for LGDA-006."""

from __future__ import annotations


class BigQueryError(Exception):
    """Base exception for BigQuery-related errors."""

    pass


class QueryTimeoutError(BigQueryError):
    """Raised when a BigQuery job times out."""

    def __init__(self, message: str, job_id: str | None = None) -> None:
        super().__init__(message)
        self.job_id = job_id


class RateLimitExceededError(BigQueryError):
    """Raised when BigQuery API rate limits are exceeded."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class TransientQueryError(BigQueryError):
    """Raised for transient BigQuery errors that should be retried."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error
