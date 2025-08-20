"""Unified Retry Architecture for LGDA.

This module provides centralized retry logic that consolidates the dual retry
systems from bq.py and LangGraph, implementing ADR-001 specifications.

Key Features:
- Configurable retry strategies per operation type
- Error classification and context propagation 
- Circuit breaker integration
- Zero breaking changes to existing APIs
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional, Type, TypeVar, Union

from pydantic import BaseModel, Field


class ErrorCategory(Enum):
    """Error categorization for retry decisions."""
    
    TRANSIENT = "transient"         # Temporary failures, should retry
    PERMANENT = "permanent"         # Permanent failures, don't retry  
    RATE_LIMIT = "rate_limit"       # Rate limit errors, special backoff
    INFRASTRUCTURE = "infrastructure"  # Low-level infrastructure errors
    BUSINESS_LOGIC = "business_logic"  # High-level business logic errors


class RetryStrategy(BaseModel):
    """Configuration for retry behavior."""
    
    max_attempts: int = Field(default=3, ge=1, le=10)
    base_delay: float = Field(default=1.0, ge=0.1, le=60.0)
    max_delay: float = Field(default=30.0, ge=1.0, le=300.0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0, le=5.0)
    jitter: bool = Field(default=True)
    
    def calculate_delay(self, attempt: int, random_gen: Optional[random.Random] = None) -> float:
        """Calculate backoff delay with optional jitter."""
        if random_gen is None:
            random_gen = random
            
        # Exponential backoff: base_delay * (multiplier^attempt)
        exponential_delay = self.base_delay * (self.backoff_multiplier ** attempt)
        
        # Cap at max_delay
        delay = min(exponential_delay, self.max_delay)
        
        # Add jitter to avoid thundering herd
        if self.jitter:
            jitter_amount = delay * 0.1  # 10% jitter
            jitter_offset = random_gen.uniform(-jitter_amount, jitter_amount)
            delay = max(0.1, delay + jitter_offset)
            
        return delay


class RetryConfig:
    """Pre-configured retry strategies for different operation types."""
    
    # SQL generation retries - user-facing operations
    SQL_GENERATION = RetryStrategy(
        max_attempts=3, 
        base_delay=1.0, 
        max_delay=8.0,
        backoff_multiplier=2.0
    )
    
    # BigQuery transient errors - infrastructure level
    BIGQUERY_TRANSIENT = RetryStrategy(
        max_attempts=5,
        base_delay=0.5,
        max_delay=30.0, 
        backoff_multiplier=2.0
    )
    
    # LLM timeout errors - provider issues
    LLM_TIMEOUT = RetryStrategy(
        max_attempts=2,
        base_delay=2.0,
        max_delay=10.0,
        backoff_multiplier=2.0
    )
    
    # Rate limit handling - respect provider limits
    RATE_LIMIT = RetryStrategy(
        max_attempts=3,
        base_delay=5.0,
        max_delay=60.0,
        backoff_multiplier=2.0,
        jitter=False  # Use exact Retry-After if available
    )


class RetryContext:
    """Context tracking for retry attempts."""
    
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.attempt_count = 0
        self.errors: list[str] = []
        self.start_time = time.time()
        
    def record_attempt(self, error: Optional[Exception] = None) -> None:
        """Record a retry attempt."""
        self.attempt_count += 1
        if error:
            self.errors.append(f"Attempt {self.attempt_count}: {type(error).__name__}: {error}")
            
    def get_context_summary(self) -> str:
        """Get summary of retry context for debugging."""
        duration = time.time() - self.start_time
        return (
            f"Operation: {self.operation_name}, "
            f"Attempts: {self.attempt_count}, "
            f"Duration: {duration:.2f}s, "
            f"Errors: {len(self.errors)}"
        )


# Global registry for error classification functions
_ERROR_CLASSIFIERS: Dict[Type[Exception], ErrorCategory] = {}


def register_error_classifier(exception_type: Type[Exception], category: ErrorCategory) -> None:
    """Register error classification for retry decisions."""
    _ERROR_CLASSIFIERS[exception_type] = category


def classify_error(error: Exception) -> ErrorCategory:
    """Classify error to determine retry behavior."""
    error_type = type(error)
    
    # Special handling for ValueError - check message first before using default classification
    if error_type == ValueError:
        error_message = str(error).lower()
        # SQL validation errors should be business logic, not permanent
        if any(pattern in error_message for pattern in [
            'sql parse error', 'query must start', 'forbidden tables', 
            'invalid sql', 'syntax error', 'missing column'
        ]):
            return ErrorCategory.BUSINESS_LOGIC
        # For other ValueError types, use the default PERMANENT classification
        return ErrorCategory.PERMANENT
    
    # Check exact type match first
    if error_type in _ERROR_CLASSIFIERS:
        return _ERROR_CLASSIFIERS[error_type]
    
    # Check parent classes
    for exc_type, category in _ERROR_CLASSIFIERS.items():
        if isinstance(error, exc_type):
            return category
    
    # Default classification based on common patterns
    error_name = error_type.__name__.lower()
    error_message = str(error).lower()
    
    # Rate limit patterns
    if any(pattern in error_name for pattern in ['ratelimit', 'quota', 'throttle']):
        return ErrorCategory.RATE_LIMIT
    if any(pattern in error_message for pattern in ['rate limit', 'quota exceeded', 'too many requests']):
        return ErrorCategory.RATE_LIMIT
    
    # Infrastructure patterns  
    if any(pattern in error_name for pattern in ['timeout', 'connection', 'network', 'server']):
        return ErrorCategory.INFRASTRUCTURE
    if any(pattern in error_message for pattern in ['timeout', 'connection', 'network error']):
        return ErrorCategory.INFRASTRUCTURE
        
    # Permanent error patterns (more specific now)
    if any(pattern in error_name for pattern in ['badrequest', 'forbidden', 'notfound', 'unauthorized']):
        return ErrorCategory.PERMANENT
    if any(pattern in error_message for pattern in ['not found', 'access denied', 'authentication']):
        return ErrorCategory.PERMANENT
        
    # Default to transient for unknown errors
    return ErrorCategory.TRANSIENT


def should_retry_error(error: Exception, category: Optional[ErrorCategory] = None) -> bool:
    """Determine if error should be retried."""
    if category is None:
        category = classify_error(error)
    
    return category in {
        ErrorCategory.TRANSIENT, 
        ErrorCategory.RATE_LIMIT, 
        ErrorCategory.INFRASTRUCTURE,
        ErrorCategory.BUSINESS_LOGIC
    }


T = TypeVar('T')


def retry_with_strategy(
    strategy: RetryStrategy,
    *,
    error_classifier: Optional[Callable[[Exception], ErrorCategory]] = None,
    context_name: Optional[str] = None
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for applying retry strategy to functions."""
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            return _execute_with_retry(
                func, args, kwargs, strategy, error_classifier, context_name or func.__name__
            )
        
        @functools.wraps(func) 
        async def async_wrapper(*args, **kwargs) -> T:
            return await _execute_async_with_retry(
                func, args, kwargs, strategy, error_classifier, context_name or func.__name__
            )
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper
            
    return decorator


def _execute_with_retry(
    func: Callable[..., T],
    args: tuple,
    kwargs: dict,
    strategy: RetryStrategy,
    error_classifier: Optional[Callable[[Exception], ErrorCategory]],
    context_name: str
) -> T:
    """Execute function with retry logic."""
    context = RetryContext(context_name)
    classifier = error_classifier or classify_error
    
    last_exception = None
    
    for attempt in range(strategy.max_attempts):
        try:
            result = func(*args, **kwargs)
            if attempt > 0:
                logging.info(f"Retry succeeded for {context_name} after {attempt} attempts")
            return result
            
        except Exception as e:
            last_exception = e
            context.record_attempt(e)
            
            # Classify error to determine retry behavior
            category = classifier(e)
            
            # Don't retry permanent errors
            if not should_retry_error(e, category):
                logging.warning(f"Permanent error in {context_name}: {e}")
                raise e
            
            # For last attempt, raise the exception
            if attempt == strategy.max_attempts - 1:
                logging.error(f"Max retries exceeded for {context_name}: {context.get_context_summary()}")
                raise e
            
            # Calculate delay based on error category
            if category == ErrorCategory.RATE_LIMIT:
                delay = _get_rate_limit_delay(e, strategy, attempt)
            else:
                delay = strategy.calculate_delay(attempt)
            
            logging.warning(
                f"Attempt {attempt + 1} failed for {context_name} with {type(e).__name__}: {e}. "
                f"Retrying in {delay:.2f}s"
            )
            time.sleep(delay)
    
    # This should not be reached, but just in case
    raise last_exception or Exception(f"Retry logic failed unexpectedly for {context_name}")


async def _execute_async_with_retry(
    func: Callable[..., T],
    args: tuple,
    kwargs: dict,
    strategy: RetryStrategy,
    error_classifier: Optional[Callable[[Exception], ErrorCategory]],
    context_name: str
) -> T:
    """Execute async function with retry logic."""
    context = RetryContext(context_name)
    classifier = error_classifier or classify_error
    
    last_exception = None
    
    for attempt in range(strategy.max_attempts):
        try:
            result = await func(*args, **kwargs)
            if attempt > 0:
                logging.info(f"Async retry succeeded for {context_name} after {attempt} attempts")
            return result
            
        except Exception as e:
            last_exception = e
            context.record_attempt(e)
            
            # Classify error to determine retry behavior
            category = classifier(e)
            
            # Don't retry permanent errors
            if not should_retry_error(e, category):
                logging.warning(f"Permanent error in async {context_name}: {e}")
                raise e
            
            # For last attempt, raise the exception
            if attempt == strategy.max_attempts - 1:
                logging.error(f"Max async retries exceeded for {context_name}: {context.get_context_summary()}")
                raise e
            
            # Calculate delay based on error category
            if category == ErrorCategory.RATE_LIMIT:
                delay = _get_rate_limit_delay(e, strategy, attempt)
            else:
                delay = strategy.calculate_delay(attempt)
            
            logging.warning(
                f"Async attempt {attempt + 1} failed for {context_name} with {type(e).__name__}: {e}. "
                f"Retrying in {delay:.2f}s"
            )
            await asyncio.sleep(delay)
    
    # This should not be reached, but just in case
    raise last_exception or Exception(f"Async retry logic failed unexpectedly for {context_name}")


def _get_rate_limit_delay(error: Exception, strategy: RetryStrategy, attempt: int) -> float:
    """Get delay for rate limit errors, respecting Retry-After headers."""
    # Try to extract Retry-After header
    retry_after = None
    if hasattr(error, 'response') and error.response:
        retry_after_header = error.response.headers.get('Retry-After')
        if retry_after_header:
            try:
                retry_after = int(retry_after_header)
            except ValueError:
                pass
    
    # Use Retry-After if available, otherwise use strategy delay
    if retry_after:
        return min(retry_after, strategy.max_delay)
    else:
        return strategy.calculate_delay(attempt)


# Initialize default error classifications
def _register_default_classifications() -> None:
    """Register default error classifications for common exceptions."""
    try:
        # Google Cloud BigQuery exceptions
        from google.api_core.exceptions import (
            BadRequest, Forbidden, NotFound, ServerError, 
            TooManyRequests, RetryError
        )
        
        register_error_classifier(BadRequest, ErrorCategory.PERMANENT)
        register_error_classifier(Forbidden, ErrorCategory.PERMANENT) 
        register_error_classifier(NotFound, ErrorCategory.PERMANENT)
        register_error_classifier(ServerError, ErrorCategory.INFRASTRUCTURE)
        register_error_classifier(TooManyRequests, ErrorCategory.RATE_LIMIT)
        register_error_classifier(RetryError, ErrorCategory.TRANSIENT)
        
    except ImportError:
        # If Google Cloud libraries not available, skip registration
        pass
    
    # Standard Python exceptions
    register_error_classifier(ConnectionError, ErrorCategory.INFRASTRUCTURE)
    register_error_classifier(TimeoutError, ErrorCategory.INFRASTRUCTURE)
    register_error_classifier(ValueError, ErrorCategory.PERMANENT)
    register_error_classifier(TypeError, ErrorCategory.PERMANENT)


# Register default classifications on module import
_register_default_classifications()