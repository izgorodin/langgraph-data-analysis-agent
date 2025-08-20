from __future__ import annotations

import base64
import json
import logging
import os
import random
import threading
import time
from typing import Dict, List, Optional

from google.api_core.exceptions import (
    BadRequest,
    Forbidden,
    NotFound,
    RetryError,
    ServerError,
    TooManyRequests,
)
from google.cloud import bigquery

from .bq_errors import QueryTimeoutError, RateLimitExceededError, TransientQueryError
from .bq_metrics import MetricsCollector, QueryMetrics
from .config import settings
from .core.migration import (
    is_unified_retry_enabled,
    bigquery_retry_decorator,
    get_bigquery_retry_strategy,
    migrate_legacy_retry_function
)


# Feature flag configuration with environment variables
def _get_env_bool(key: str, default: bool) -> bool:
    """Get boolean value from environment variable."""
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def _get_env_int(key: str, default: int) -> int:
    """Get integer value from environment variable."""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _get_env_float(key: str, default: float) -> float:
    """Get float value from environment variable."""
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


# Feature flags for LGDA-006
RETRY_ENABLED = _get_env_bool("LGDA_BQ_RETRY_ENABLED", True)
RETRY_MAX_ATTEMPTS = _get_env_int("LGDA_BQ_RETRY_MAX_ATTEMPTS", 3)
RETRY_BASE_DELAY_MS = _get_env_int("LGDA_BQ_RETRY_BASE_DELAY_MS", 100)
RETRY_JITTER_MS = _get_env_int("LGDA_BQ_RETRY_JITTER_MS", 50)
TIMEOUT_SEC = _get_env_int("LGDA_BQ_TIMEOUT_SEC", 30)
BREAKER_ENABLED = _get_env_bool("LGDA_BQ_BREAKER_ENABLED", True)
BREAKER_FAILURES = _get_env_int("LGDA_BQ_BREAKER_FAILURES", 5)
BREAKER_WINDOW_SEC = _get_env_int("LGDA_BQ_BREAKER_WINDOW_SEC", 60)
BREAKER_COOLDOWN_SEC = _get_env_int("LGDA_BQ_BREAKER_COOLDOWN_SEC", 20)
METRICS_ENABLED = _get_env_bool("LGDA_BQ_METRICS_ENABLED", True)


class CircuitBreaker:
    """Circuit breaker for BigQuery operations."""

    def __init__(
        self,
        failure_threshold: int = BREAKER_FAILURES,
        window_seconds: int = BREAKER_WINDOW_SEC,
        cooldown_seconds: int = BREAKER_COOLDOWN_SEC,
    ):
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.failures = 0
        self.last_failure_time = 0.0
        self.state = "closed"  # closed, open, half-open
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        if not BREAKER_ENABLED:
            return True

        with self._lock:
            current_time = time.time()

            if self.state == "closed":
                return True
            elif self.state == "open":
                if current_time - self.last_failure_time > self.cooldown_seconds:
                    self.state = "half-open"
                    return True
                return False
            else:  # half-open
                return True

    def record_success(self) -> None:
        """Record successful execution."""
        if not BREAKER_ENABLED:
            return

        with self._lock:
            self.failures = 0
            self.state = "closed"

    def record_failure(self) -> None:
        """Record failed execution."""
        if not BREAKER_ENABLED:
            return

        with self._lock:
            current_time = time.time()

            # Reset counter if window has passed
            if current_time - self.last_failure_time > self.window_seconds:
                self.failures = 0

            self.failures += 1
            self.last_failure_time = current_time

            if self.failures >= self.failure_threshold:
                self.state = "open"

    def get_state(self) -> str:
        """Get current breaker state."""
        return self.state


# Global circuit breaker instance
_circuit_breaker = CircuitBreaker()

# Thread-safe client initialization
_bq_client: Optional[bigquery.Client] = None
_client_lock = threading.Lock()


def _resolve_bq_credentials():
    """Resolve BigQuery credentials from env per LGDA-005.

    Priority:
    1) BIGQUERY_CREDENTIALS_JSON (base64-encoded service account JSON)
    2) GOOGLE_APPLICATION_CREDENTIALS (file path)
    3) ADC (default)
    Returns tuple (credentials, project) suitable for bigquery.Client kwargs.
    """
    creds = None
    project = settings.bq_project or None

    b64_json = os.getenv("BIGQUERY_CREDENTIALS_JSON")
    if b64_json:
        try:
            from google.oauth2 import service_account  # type: ignore

            data = json.loads(base64.b64decode(b64_json).decode("utf-8"))
            creds = service_account.Credentials.from_service_account_info(data)
            project = project or data.get("project_id")
            return creds, project
        except Exception:
            # fall through to other methods
            pass

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and os.path.exists(cred_path):
        try:
            from google.oauth2 import service_account  # type: ignore

            creds = service_account.Credentials.from_service_account_file(cred_path)
            # project may be None; BQ SDK can infer from creds
            return creds, project
        except Exception:
            pass

    return None, project


def bq_client() -> bigquery.Client:
    """
    Get BigQuery client with thread-safe initialization and authentication fallback.

    Implements multi-level authentication:
    1. Environment-based credentials (production)
    2. Application Default Credentials (development)
    3. Automatic retry on auth failures
    """
    global _bq_client

    # Double-checked locking pattern for thread safety
    if _bq_client is None:
        with _client_lock:
            if _bq_client is None:  # Check again inside the lock
                try:
                    creds, project = _resolve_bq_credentials()
                    # Try to create client with current configuration
                    client_kwargs = {
                        "project": project,  # None allows auto-detection
                        "location": settings.bq_location,
                    }
                    if creds is not None:
                        client_kwargs["credentials"] = creds
                    _bq_client = bigquery.Client(**client_kwargs)
                    logging.info(
                        f"BigQuery client initialized for project: {settings.bq_project}"
                    )
                except Exception as e:
                    logging.error(f"Failed to initialize BigQuery client: {e}")
                    # Try fallback with Application Default Credentials
                    try:
                        _bq_client = bigquery.Client(location=settings.bq_location)
                        logging.info(
                            "BigQuery client initialized with default credentials"
                        )
                    except Exception as fallback_error:
                        logging.error(
                            f"BigQuery client fallback failed: {fallback_error}"
                        )
                        raise RuntimeError(
                            f"Cannot initialize BigQuery client: {fallback_error}"
                        ) from e
    return _bq_client


# nosec B608: SCHEMA_QUERY is a static template with parameter binding via
# QueryJobConfig; dataset comes from settings and not user input
SCHEMA_QUERY = (
    """
SELECT table_name, column_name, data_type
FROM `{}.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name IN UNNEST(@tables)
ORDER BY table_name, ordinal_position
"""
).format(settings.dataset_id)


def _calculate_backoff_delay(
    attempt: int,
    base_delay_ms: int = RETRY_BASE_DELAY_MS,
    jitter_ms: int = RETRY_JITTER_MS,
    random_gen: Optional[random.Random] = None,
) -> float:
    """Calculate exponential backoff delay with jitter."""
    if random_gen is None:
        random_gen = random

    # Exponential backoff: 2^attempt * base_delay
    exponential_delay = (2**attempt) * base_delay_ms

    # Add jitter to avoid thundering herd
    jitter = random_gen.randint(0, jitter_ms)

    total_delay_ms = exponential_delay + jitter
    return total_delay_ms / 1000.0  # Convert to seconds


def _is_transient_error(error: Exception) -> bool:
    """Check if error is transient and should be retried."""
    return isinstance(error, (ServerError, RetryError))


def _is_rate_limit_error(error: Exception) -> bool:
    """Check if error is a rate limit error."""
    return isinstance(error, TooManyRequests)


def _is_permanent_error(error: Exception) -> bool:
    """Check if error is permanent and should not be retried."""
    return isinstance(error, (BadRequest, Forbidden, NotFound))


def _get_retry_after(error: Exception) -> Optional[int]:
    """Extract Retry-After header value from rate limit error."""
    if hasattr(error, "response") and error.response:
        retry_after = error.response.headers.get("Retry-After")
        if retry_after:
            try:
                return int(retry_after)
            except ValueError:
                pass
    return None


def _retry_with_backoff(
    func,
    *args,
    max_attempts: int = RETRY_MAX_ATTEMPTS,
    random_gen: Optional[random.Random] = None,
    **kwargs,
):
    """Retry function with exponential backoff and jitter."""
    if not RETRY_ENABLED:
        return func(*args, **kwargs)

    last_exception = None

    for attempt in range(max_attempts):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            # Don't retry permanent errors
            if _is_permanent_error(e):
                raise e

            # For the last attempt, raise the exception
            if attempt == max_attempts - 1:
                if _is_transient_error(e):
                    raise TransientQueryError(
                        f"Query failed after {max_attempts} attempts: {e}", e
                    )
                elif _is_rate_limit_error(e):
                    retry_after = _get_retry_after(e)
                    raise RateLimitExceededError(
                        f"Rate limit exceeded: {e}", retry_after
                    )
                else:
                    raise e

            # Calculate delay
            if _is_rate_limit_error(e):
                # Respect Retry-After header if present
                retry_after = _get_retry_after(e)
                if retry_after:
                    delay = retry_after
                else:
                    delay = _calculate_backoff_delay(
                        attempt, 1000, 500, random_gen
                    )  # Longer delay for rate limits
            else:
                delay = _calculate_backoff_delay(attempt, random_gen=random_gen)

            logging.warning(
                f"Attempt {attempt + 1} failed with {type(e).__name__}: {e}. Retrying in {delay:.2f}s"
            )
            time.sleep(delay)

    # This should not be reached, but just in case
    raise last_exception or Exception("Retry logic failed unexpectedly")


def get_schema(tables: List[str]) -> List[Dict]:
    client = bq_client()
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("tables", "STRING", tables)],
        maximum_bytes_billed=settings.max_bytes_billed,
    )
    rows = client.query(SCHEMA_QUERY, job_config=job_config).result()
    return [dict(r) for r in rows]


def get_circuit_breaker_status() -> Dict[str, any]:
    """Get current circuit breaker status for monitoring."""
    return {
        "state": _circuit_breaker.get_state(),
        "failures": _circuit_breaker.failures,
        "last_failure_time": _circuit_breaker.last_failure_time,
        "enabled": BREAKER_ENABLED,
    }


def reset_circuit_breaker() -> None:
    """Reset circuit breaker state (for testing/recovery)."""
    global _circuit_breaker
    _circuit_breaker = CircuitBreaker()


# Global metrics storage for last query
_last_query_metrics: Optional[QueryMetrics] = None


def get_last_query_metrics() -> Optional[QueryMetrics]:
    """Get metrics from the last executed query."""
    return _last_query_metrics


def _store_query_metrics(metrics: QueryMetrics) -> None:
    """Store metrics for external access."""
    global _last_query_metrics
    _last_query_metrics = metrics


def run_query(
    sql: str, dry_run: bool = False, timeout: Optional[int] = None
) -> Optional[object]:
    """
    Execute BigQuery SQL with comprehensive error handling, retry logic, and circuit breaker.

    Args:
        sql: SQL query to execute
        dry_run: If True, validate query without execution
        timeout: Query timeout in seconds (default: from env LGDA_BQ_TIMEOUT_SEC)

    Returns:
        pandas.DataFrame with query results or None for dry_run

    Raises:
        ValueError: For SQL syntax errors
        Forbidden: For authentication/permission errors
        NotFound: For missing tables/datasets
        QueryTimeoutError: For query timeouts
        RateLimitExceededError: For rate limit errors
        TransientQueryError: For transient errors after retries
        Exception: For other BigQuery errors
    """
    # Check circuit breaker
    if not _circuit_breaker.can_execute():
        raise TransientQueryError("Circuit breaker is open - too many recent failures")

    metrics_collector = MetricsCollector() if METRICS_ENABLED else None
    if metrics_collector:
        metrics_collector.start_timer()

    effective_timeout = timeout or TIMEOUT_SEC
    retry_count = 0

    def _execute_query_attempt():
        nonlocal retry_count

        client = bq_client()
        job_config = bigquery.QueryJobConfig(
            maximum_bytes_billed=settings.max_bytes_billed,
            dry_run=dry_run,
            use_query_cache=True,
            job_timeout_ms=effective_timeout * 1000,  # Convert to milliseconds
        )

        try:
            job = client.query(sql, job_config=job_config)

            if dry_run:
                # For dry run, collect metrics and return None
                if metrics_collector and METRICS_ENABLED:
                    metrics = metrics_collector.create_metrics(
                        job_id=job.job_id if hasattr(job, "job_id") else None,
                        bytes_processed=getattr(job, "total_bytes_processed", None),
                        retries=retry_count,
                        breaker_state=_circuit_breaker.get_state(),
                    )
                    metrics.log_structured()
                    _store_query_metrics(metrics)
                return None

            # Wait for job completion with timeout handling
            try:
                result = job.result(timeout=effective_timeout)
            except Exception as e:
                # Check if it's a timeout and try to cancel the job
                if "timeout" in str(e).lower():
                    try:
                        if hasattr(job, "cancel"):
                            job.cancel()
                            logging.info(
                                f"Cancelled BigQuery job {getattr(job, 'job_id', 'unknown')} due to timeout"
                            )
                    except Exception as cancel_error:
                        logging.warning(
                            f"Failed to cancel job {getattr(job, 'job_id', 'unknown')}: {cancel_error}"
                        )
                    raise QueryTimeoutError(
                        f"Query timeout after {effective_timeout}s",
                        getattr(job, "job_id", None),
                    )
                raise e

            # Collect metrics
            if metrics_collector and METRICS_ENABLED:
                metrics = metrics_collector.create_metrics(
                    job_id=getattr(job, "job_id", None),
                    bytes_processed=getattr(job, "total_bytes_processed", None),
                    bytes_billed=getattr(job, "total_bytes_billed", None),
                    cache_hit=getattr(job, "cache_hit", False) or False,
                    row_count=getattr(job, "num_dml_affected_rows", 0) or 0,
                    retries=retry_count,
                    breaker_state=_circuit_breaker.get_state(),
                )
                metrics.log_structured()
                _store_query_metrics(metrics)

            # Record success for circuit breaker
            _circuit_breaker.record_success()

            # Convert to DataFrame with BigQuery Storage for large results
            if hasattr(result, "to_dataframe"):
                return result.to_dataframe(create_bqstorage_client=True)
            else:
                # For testing with mocks that don't have to_dataframe
                return result

        except BadRequest as e:
            # SQL syntax or validation errors - don't retry
            _circuit_breaker.record_failure()
            raise ValueError(f"BigQuery error: {e}")
        except (Forbidden, NotFound) as e:
            # Auth/permission and not found errors - don't retry but don't count as circuit breaker failure
            raise e
        except TooManyRequests as e:
            # Rate limit errors - retry with backoff
            _circuit_breaker.record_failure()
            retry_count += 1
            raise e
        except (ServerError, RetryError) as e:
            # Server errors - retry with exponential backoff
            _circuit_breaker.record_failure()
            retry_count += 1
            raise e
        except QueryTimeoutError as e:
            # Timeout errors - don't retry but count as failure
            _circuit_breaker.record_failure()
            raise e
        except Exception as e:
            # Catch-all for other errors
            _circuit_breaker.record_failure()
            if "timeout" in str(e).lower():
                raise QueryTimeoutError(f"Query timeout: {e}")
            # For testing, don't transform generic exceptions into TransientQueryError if they're not actually transient
            raise Exception(f"BigQuery execution failed: {e}")

    # Choose retry mechanism based on unified retry flag
    if is_unified_retry_enabled():
        # Use unified retry system
        strategy = get_bigquery_retry_strategy()
        from .core.retry import retry_with_strategy
        
        @retry_with_strategy(strategy, context_name="bigquery_query")
        def unified_retry_wrapper():
            return _execute_query_attempt()
        
        try:
            return unified_retry_wrapper()
        except Exception as e:
            # Final fallback to record circuit breaker failure if not already done
            if not isinstance(e, (ValueError, Forbidden, NotFound)):
                _circuit_breaker.record_failure()
            raise e
    else:
        # Use legacy retry system
        try:
            return _retry_with_backoff(_execute_query_attempt)
        except Exception as e:
            # Final fallback to record circuit breaker failure if not already done
            if not isinstance(e, (ValueError, Forbidden, NotFound)):
                _circuit_breaker.record_failure()
            raise e
