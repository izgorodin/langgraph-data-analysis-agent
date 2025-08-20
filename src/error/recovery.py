"""Recovery engine implementing different recovery strategies."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Callable, Dict, List, Optional, Union
import time

from .core import ErrorRecovery, LGDAError, BigQueryExecutionError
from .classification import ErrorClassifier, RecoveryStrategy, ErrorSeverity


class RecoveryEngine:
    """Engine for executing error recovery strategies."""
    
    def __init__(self, classifier: Optional[ErrorClassifier] = None):
        """
        Initialize recovery engine.
        
        Args:
            classifier: Error classifier instance
        """
        self.classifier = classifier or ErrorClassifier()
        self._retry_counts: Dict[str, int] = {}
        
    async def handle_error(
        self,
        error: Exception,
        operation: Optional[Callable] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> ErrorRecovery:
        """
        Handle error and determine recovery action.
        
        Args:
            error: Exception that occurred
            operation: Original operation that failed
            context: Additional context for recovery
            
        Returns:
            ErrorRecovery with recommended action
        """
        strategy, severity = self.classifier.classify(error)
        context = context or {}
        
        # Get operation identifier for retry tracking
        op_id = context.get('operation_id', str(operation) if operation else 'unknown')
        
        # Apply recovery strategy
        if strategy == RecoveryStrategy.IMMEDIATE_RETRY:
            return await self._immediate_retry_recovery(error, op_id, context)
        elif strategy == RecoveryStrategy.EXPONENTIAL_BACKOFF:
            return await self._exponential_backoff_recovery(error, op_id, context)
        elif strategy == RecoveryStrategy.GRACEFUL_DEGRADATION:
            return await self._graceful_degradation_recovery(error, op_id, context)
        elif strategy == RecoveryStrategy.USER_GUIDED:
            return await self._user_guided_recovery(error, op_id, context)
        else:  # NO_RECOVERY
            return await self._no_recovery(error, op_id, context)
    
    async def _immediate_retry_recovery(
        self, 
        error: Exception, 
        op_id: str, 
        context: Dict[str, Any]
    ) -> ErrorRecovery:
        """Handle immediate retry recovery (< 1 second)."""
        retry_count = self._retry_counts.get(op_id, 0)
        max_retries = 3
        
        if retry_count >= max_retries:
            return ErrorRecovery(
                strategy="immediate_retry_exhausted",
                should_retry=False,
                message=f"Immediate retry failed after {max_retries} attempts",
                user_message="Unable to complete operation after multiple attempts"
            )
        
        # Handle specific error types
        modified_input = None
        if isinstance(error, BigQueryExecutionError):
            modified_input = self._handle_bigquery_array_error(error)
        
        self._retry_counts[op_id] = retry_count + 1
        
        return ErrorRecovery(
            strategy="immediate_retry",
            modified_input=modified_input,
            retry_delay=0.1,  # 100ms delay
            max_retries=max_retries - retry_count,
            should_retry=True,
            message=f"Retrying immediately (attempt {retry_count + 1}/{max_retries})",
            user_message=self.classifier.get_user_message(error)
        )
    
    async def _exponential_backoff_recovery(
        self, 
        error: Exception, 
        op_id: str, 
        context: Dict[str, Any]
    ) -> ErrorRecovery:
        """Handle exponential backoff recovery (1-10 seconds)."""
        retry_count = self._retry_counts.get(op_id, 0)
        max_retries = 5
        
        if retry_count >= max_retries:
            return ErrorRecovery(
                strategy="exponential_backoff_exhausted",
                should_retry=False,
                message=f"Exponential backoff failed after {max_retries} attempts",
                user_message="Service temporarily unavailable. Please try again later."
            )
        
        # Calculate exponential backoff delay: 2^retry_count seconds, max 10s
        delay = min(2 ** retry_count, 10)
        
        self._retry_counts[op_id] = retry_count + 1
        
        return ErrorRecovery(
            strategy="exponential_backoff",
            retry_delay=delay,
            max_retries=max_retries - retry_count,
            should_retry=True,
            message=f"Retrying with backoff in {delay}s (attempt {retry_count + 1}/{max_retries})",
            user_message=self.classifier.get_user_message(error)
        )
    
    async def _graceful_degradation_recovery(
        self, 
        error: Exception, 
        op_id: str, 
        context: Dict[str, Any]
    ) -> ErrorRecovery:
        """Handle graceful degradation recovery."""
        # Determine degradation strategy based on error and context
        if "model" in str(error).lower():
            return ErrorRecovery(
                strategy="model_fallback",
                modified_input={"fallback_model": True},
                should_retry=True,
                message="Falling back to alternative model",
                user_message="Using alternative approach for your request..."
            )
        
        if "memory" in str(error).lower() or "resource" in str(error).lower():
            return ErrorRecovery(
                strategy="simplified_processing",
                modified_input={"simplified": True, "chunk_size": 100},
                should_retry=True,
                message="Simplifying processing to reduce resource usage",
                user_message="Processing request with reduced complexity..."
            )
        
        # Default degradation
        return ErrorRecovery(
            strategy="cached_fallback",
            modified_input={"use_cache": True},
            should_retry=True,
            message="Using cached results where available",
            user_message="Providing best available results..."
        )
    
    async def _user_guided_recovery(
        self, 
        error: Exception, 
        op_id: str, 
        context: Dict[str, Any]
    ) -> ErrorRecovery:
        """Handle user-guided recovery (> 10 seconds)."""
        error_msg = str(error)
        
        if "syntax" in error_msg.lower() or "sql" in error_msg.lower():
            return ErrorRecovery(
                strategy="user_clarification",
                should_retry=False,
                message="SQL syntax error requires user clarification",
                user_message="Please rephrase your question or provide more specific details."
            )
        
        if "table" in error_msg.lower() or "column" in error_msg.lower():
            return ErrorRecovery(
                strategy="schema_guidance",
                should_retry=False,
                message="Schema-related error needs user guidance",
                user_message="Please check the table or column names in your query."
            )
        
        return ErrorRecovery(
            strategy="general_user_guidance",
            should_retry=False,
            message="Complex error requiring user intervention",
            user_message="Unable to process request automatically. Please try a different approach."
        )
    
    async def _no_recovery(
        self, 
        error: Exception, 
        op_id: str, 
        context: Dict[str, Any]
    ) -> ErrorRecovery:
        """Handle non-recoverable errors."""
        return ErrorRecovery(
            strategy="no_recovery",
            should_retry=False,
            message="Error is not recoverable",
            user_message=self.classifier.get_user_message(error)
        )
    
    def _handle_bigquery_array_error(self, error: BigQueryExecutionError) -> Optional[str]:
        """
        Handle BigQuery Array null element errors by modifying the query.
        
        Args:
            error: BigQuery execution error
            
        Returns:
            Modified query string or None
        """
        if "Array cannot have a null element" not in error.message:
            return None
        
        if not error.query:
            return None
        
        # Add null handling to array operations
        query = error.query
        
        # Common patterns to fix
        patterns = [
            # ARRAY[...] constructor with potential nulls
            (r'ARRAY\s*\[\s*([^\]]+)\s*\]', r'ARRAY(SELECT x FROM UNNEST([\1]) AS x WHERE x IS NOT NULL)'),
            # ARRAY(...) constructor with potential nulls
            (r'ARRAY\s*\(\s*([^)]+)\s*\)', r'ARRAY(SELECT x FROM UNNEST([\1]) AS x WHERE x IS NOT NULL)'),
            # ARRAY_AGG with potential nulls
            (r'ARRAY_AGG\s*\(\s*([^)]+)\s*\)', r'ARRAY_AGG(\1 IGNORE NULLS)'),
        ]
        
        modified_query = query
        for pattern, replacement in patterns:
            modified_query = re.sub(pattern, replacement, modified_query, flags=re.IGNORECASE)
        
        return modified_query if modified_query != query else None
    
    def reset_retry_count(self, op_id: str) -> None:
        """Reset retry count for an operation."""
        self._retry_counts.pop(op_id, None)
    
    def get_retry_count(self, op_id: str) -> int:
        """Get current retry count for an operation."""
        return self._retry_counts.get(op_id, 0)


# Global recovery engine instance
_default_recovery_engine: Optional[RecoveryEngine] = None


def get_recovery_engine() -> RecoveryEngine:
    """Get or create the default recovery engine."""
    global _default_recovery_engine
    if _default_recovery_engine is None:
        _default_recovery_engine = RecoveryEngine()
    return _default_recovery_engine


def set_recovery_engine(engine: RecoveryEngine) -> None:
    """Set the default recovery engine."""
    global _default_recovery_engine
    _default_recovery_engine = engine