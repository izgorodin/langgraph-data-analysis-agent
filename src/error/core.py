"""Core error classes and data structures for LGDA error handling."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from dataclasses import dataclass


class LGDAError(Exception):
    """Base exception with error context for LGDA operations."""
    
    def __init__(
        self, 
        message: str, 
        error_code: str, 
        context: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.context = context or {}
        self.timestamp = datetime.now(timezone.utc)
        super().__init__(message)
    
    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging/monitoring."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "type": self.__class__.__name__
        }


class SqlGenerationError(LGDAError):
    """SQL generation specific errors."""
    
    def __init__(
        self, 
        message: str, 
        context: Optional[Dict[str, Any]] = None,
        query_fragment: Optional[str] = None
    ):
        super().__init__(message, "SQL_GENERATION_ERROR", context)
        self.query_fragment = query_fragment


class BigQueryExecutionError(LGDAError):
    """BigQuery execution errors."""
    
    def __init__(
        self, 
        message: str, 
        context: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None,
        query: Optional[str] = None
    ):
        super().__init__(message, "BIGQUERY_EXECUTION_ERROR", context)
        self.job_id = job_id 
        self.query = query


class TimeoutError(LGDAError):
    """Operation timeout errors."""
    
    def __init__(
        self, 
        message: str, 
        context: Optional[Dict[str, Any]] = None,
        timeout_seconds: Optional[int] = None,
        operation: Optional[str] = None
    ):
        super().__init__(message, "OPERATION_TIMEOUT", context)
        self.timeout_seconds = timeout_seconds
        self.operation = operation


@dataclass
class ErrorRecovery:
    """Data structure for error recovery information."""
    
    strategy: str
    modified_input: Optional[Any] = None
    message: str = ""
    retry_delay: float = 0.0
    max_retries: int = 0
    should_retry: bool = True
    user_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "strategy": self.strategy,
            "modified_input": self.modified_input,
            "message": self.message,
            "retry_delay": self.retry_delay,
            "max_retries": self.max_retries,
            "should_retry": self.should_retry,
            "user_message": self.user_message,
        }