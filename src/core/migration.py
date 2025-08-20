"""Migration helpers for transitioning to unified retry architecture.

This module provides compatibility functions that allow gradual migration
from the existing bq.py retry system to the unified retry architecture.
"""

from __future__ import annotations

import os
from typing import Callable, Optional, TypeVar

from .retry import (
    ErrorCategory, 
    RetryConfig, 
    RetryStrategy, 
    classify_error,
    register_error_classifier,
    retry_with_strategy
)

T = TypeVar('T')


def is_unified_retry_enabled() -> bool:
    """Check if unified retry is enabled via environment variable."""
    return os.getenv("LGDA_USE_UNIFIED_RETRY", "true").lower() in ("true", "1", "yes")


# Feature flag for enabling unified retry migration
UNIFIED_RETRY_ENABLED = is_unified_retry_enabled()


def create_bigquery_compatible_strategy(
    max_attempts: int,
    base_delay_ms: int,
    jitter_ms: int
) -> RetryStrategy:
    """Create retry strategy compatible with existing BigQuery retry configuration."""
    return RetryStrategy(
        max_attempts=max_attempts,
        base_delay=base_delay_ms / 1000.0,  # Convert ms to seconds
        max_delay=30.0,  # Conservative max delay
        backoff_multiplier=2.0,
        jitter=True
    )


def bigquery_retry_decorator(
    max_attempts: int = 3,
    base_delay_ms: int = 100,
    jitter_ms: int = 50
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator that provides BigQuery-compatible retry behavior.
    
    This function serves as a bridge between the old bq.py retry system
    and the new unified retry architecture. It maintains the same interface
    while optionally using the unified system.
    """
    if is_unified_retry_enabled():
        # Use unified retry system
        strategy = create_bigquery_compatible_strategy(max_attempts, base_delay_ms, jitter_ms)
        return retry_with_strategy(strategy, context_name="bigquery_operation")
    else:
        # Fall back to original retry logic (would import from bq.py)
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            def wrapper(*args, **kwargs):
                # This would call the original _retry_with_backoff function
                # For now, just call the function directly (no retry)
                return func(*args, **kwargs)
            return wrapper
        return decorator


def register_bigquery_error_classifications() -> None:
    """Register BigQuery-specific error classifications for unified retry."""
    try:
        from google.api_core.exceptions import (
            BadRequest, Forbidden, NotFound, ServerError,
            TooManyRequests, RetryError
        )
        
        # These classifications match the existing bq.py logic
        register_error_classifier(BadRequest, ErrorCategory.PERMANENT)
        register_error_classifier(Forbidden, ErrorCategory.PERMANENT)
        register_error_classifier(NotFound, ErrorCategory.PERMANENT)
        register_error_classifier(ServerError, ErrorCategory.INFRASTRUCTURE)
        register_error_classifier(TooManyRequests, ErrorCategory.RATE_LIMIT)
        register_error_classifier(RetryError, ErrorCategory.TRANSIENT)
        
    except ImportError:
        # Google Cloud libraries not available, skip registration
        pass

    # Register custom BigQuery exceptions
    try:
        from ..bq_errors import (
            TransientQueryError, RateLimitExceededError, QueryTimeoutError
        )
        
        register_error_classifier(TransientQueryError, ErrorCategory.TRANSIENT)
        register_error_classifier(RateLimitExceededError, ErrorCategory.RATE_LIMIT)
        register_error_classifier(QueryTimeoutError, ErrorCategory.PERMANENT)  # Don't retry timeouts
        
    except ImportError:
        # bq_errors not available, skip
        pass


def get_bigquery_retry_strategy() -> RetryStrategy:
    """Get the appropriate retry strategy for BigQuery operations."""
    if is_unified_retry_enabled():
        return RetryConfig.BIGQUERY_TRANSIENT
    else:
        # Return a strategy that matches the legacy behavior
        return create_bigquery_compatible_strategy(
            max_attempts=3,
            base_delay_ms=100,
            jitter_ms=50
        )


def migrate_legacy_retry_function(
    legacy_func: Callable,
    retry_strategy: Optional[RetryStrategy] = None
) -> Callable:
    """Migrate a legacy retry function to use unified retry.
    
    This helper wraps existing functions that use the old retry mechanism
    and makes them use the new unified retry system when enabled.
    """
    if not is_unified_retry_enabled():
        return legacy_func
    
    strategy = retry_strategy or get_bigquery_retry_strategy()
    
    @retry_with_strategy(strategy)
    def unified_wrapper(*args, **kwargs):
        # Remove retry-specific arguments that are now handled by decorator
        filtered_kwargs = {
            k: v for k, v in kwargs.items() 
            if k not in ['max_attempts', 'random_gen']
        }
        return legacy_func(*args, **filtered_kwargs)
    
    return unified_wrapper


# Auto-register BigQuery error classifications when module is imported
register_bigquery_error_classifications()