"""Structured logging with correlation for LGDA production observability.

Provides request correlation, context preservation, error details, and audit trail
capabilities for comprehensive logging in production environments.

Can be disabled via LGDA_DISABLE_OBSERVABILITY environment variable.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from contextvars import ContextVar

# Optional dependency on structlog for enhanced logging
try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False

logger = logging.getLogger(__name__)

# Context variables for request correlation
REQUEST_ID_CONTEXT: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
USER_ID_CONTEXT: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
SESSION_ID_CONTEXT: ContextVar[Optional[str]] = ContextVar('session_id', default=None)


class LGDALogger:
    """Production-grade structured logging for LGDA pipeline.
    
    Provides comprehensive logging with request correlation, context preservation,
    and graceful degradation when optional dependencies are not available.
    """
    
    def __init__(self, enabled: Optional[bool] = None):
        """Initialize structured logger.
        
        Args:
            enabled: Override default enabled state. If None, uses environment.
        """
        if enabled is None:
            # Check for disable flag
            self.enabled = not os.getenv("LGDA_DISABLE_OBSERVABILITY", "false").lower() == "true"
        else:
            self.enabled = enabled
            
        if not self.enabled:
            logger.info("LGDA structured logging disabled")
            return
            
        # Initialize structlog if available, otherwise use standard logging
        if STRUCTLOG_AVAILABLE:
            self.logger = structlog.get_logger()
        else:
            self.logger = logging.getLogger("lgda")
            
        logger.info("LGDA structured logging initialized")
    
    def _get_base_context(self) -> Dict[str, Any]:
        """Get base logging context with correlation IDs."""
        context = {
            "timestamp": datetime.utcnow().isoformat(),
            "component": "lgda",
        }
        
        # Add correlation IDs if available
        request_id = REQUEST_ID_CONTEXT.get()
        if request_id:
            context["request_id"] = request_id
            
        user_id = USER_ID_CONTEXT.get()
        if user_id:
            context["user_id"] = user_id
            
        session_id = SESSION_ID_CONTEXT.get()
        if session_id:
            context["session_id"] = session_id
            
        return context
    
    def _log_structured(self, level: str, event: str, **kwargs):
        """Log with structured format."""
        if not self.enabled:
            return
            
        try:
            context = self._get_base_context()
            context.update(kwargs)
            
            if STRUCTLOG_AVAILABLE:
                # Use structlog for rich structured logging
                log_method = getattr(self.logger, level.lower())
                log_method(event, **context)
            else:
                # Fallback to standard logging with JSON
                log_data = {"event": event, **context}
                numeric_level = getattr(logging, level.upper())
                self.logger.log(numeric_level, json.dumps(log_data))
                
        except Exception as e:
            # Fallback to basic logging if structured logging fails
            basic_logger = logging.getLogger("lgda.fallback")
            basic_logger.error(f"Structured logging failed: {e}, original event: {event}")
    
    def log_query_execution(self, question: str, sql: str, execution_time: float,
                          success: bool, error: Optional[str] = None,
                          bytes_processed: Optional[int] = None,
                          row_count: Optional[int] = None):
        """Log BigQuery execution with full context."""
        self._log_structured(
            "INFO",
            "query_executed",
            question=question,
            sql_length=len(sql),
            execution_time=execution_time,
            success=success,
            error=error,
            bytes_processed=bytes_processed,
            row_count=row_count
        )
    
    def log_llm_request(self, provider: str, model: str, prompt_length: int,
                       response_length: Optional[int] = None, 
                       success: bool = True, error: Optional[str] = None,
                       latency: Optional[float] = None):
        """Log LLM provider request details."""
        self._log_structured(
            "INFO",
            "llm_request",
            provider=provider,
            model=model,
            prompt_length=prompt_length,
            response_length=response_length,
            success=success,
            error=error,
            latency=latency
        )
    
    def log_pipeline_stage(self, stage: str, duration: float, 
                          input_size: Optional[int] = None,
                          output_size: Optional[int] = None,
                          success: bool = True, error: Optional[str] = None):
        """Log pipeline stage execution."""
        self._log_structured(
            "INFO",
            "pipeline_stage",
            stage=stage,
            duration=duration,
            input_size=input_size,
            output_size=output_size,
            success=success,
            error=error
        )
    
    def log_error_recovery(self, error_type: str, recovery_strategy: str, 
                          success: bool, attempt_count: int = 1,
                          error_details: Optional[str] = None):
        """Log error recovery attempts."""
        self._log_structured(
            "WARNING",
            "error_recovery_attempted",
            error_type=error_type,
            strategy=recovery_strategy,
            success=success,
            attempt_count=attempt_count,
            error_details=error_details
        )
    
    def log_security_event(self, event_type: str, details: Dict[str, Any],
                          severity: str = "INFO"):
        """Log security-related events."""
        self._log_structured(
            severity.upper(),
            "security_event", 
            event_type=event_type,
            **details
        )
    
    def log_business_metric(self, metric_name: str, value: float,
                           dimensions: Optional[Dict[str, str]] = None):
        """Log business metrics for analysis."""
        context = {
            "metric_name": metric_name,
            "value": value
        }
        if dimensions:
            context.update(dimensions)
            
        self._log_structured(
            "INFO",
            "business_metric",
            **context
        )
    
    def log_performance_metric(self, operation: str, duration: float,
                              resource_usage: Optional[Dict[str, Any]] = None):
        """Log performance metrics."""
        context = {
            "operation": operation,
            "duration": duration
        }
        if resource_usage:
            context.update(resource_usage)
            
        self._log_structured(
            "INFO", 
            "performance_metric",
            **context
        )
    
    def log_audit_trail(self, action: str, resource: str, user_id: Optional[str] = None,
                       details: Optional[Dict[str, Any]] = None):
        """Log audit trail for compliance."""
        context = {
            "action": action,
            "resource": resource,
            "user_id": user_id or USER_ID_CONTEXT.get()
        }
        if details:
            context.update(details)
            
        self._log_structured(
            "INFO",
            "audit_trail",
            **context
        )
    
    def log_configuration_change(self, component: str, old_value: Any, 
                                new_value: Any, changed_by: Optional[str] = None):
        """Log configuration changes."""
        self._log_structured(
            "INFO",
            "configuration_change",
            component=component,
            old_value=str(old_value),
            new_value=str(new_value),
            changed_by=changed_by
        )


class LoggingContext:
    """Context manager for setting logging correlation IDs."""
    
    def __init__(self, request_id: Optional[str] = None, 
                 user_id: Optional[str] = None,
                 session_id: Optional[str] = None):
        self.request_id = request_id or str(uuid.uuid4())
        self.user_id = user_id
        self.session_id = session_id
        self.tokens = []
        
    def __enter__(self):
        # Set context variables
        self.tokens.append(REQUEST_ID_CONTEXT.set(self.request_id))
        if self.user_id:
            self.tokens.append(USER_ID_CONTEXT.set(self.user_id))
        if self.session_id:
            self.tokens.append(SESSION_ID_CONTEXT.set(self.session_id))
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Reset context variables
        for token in reversed(self.tokens):
            try:
                token.var.set(token.old_value)
            except AttributeError:
                # Handle older Python versions
                pass


class TimedOperation:
    """Context manager for timing operations with automatic logging."""
    
    def __init__(self, logger: LGDALogger, operation: str, 
                 log_level: str = "INFO", **context):
        self.logger = logger
        self.operation = operation
        self.log_level = log_level
        self.context = context
        self.start_time = None
        
    def __enter__(self):
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            duration = time.time() - self.start_time
            success = exc_type is None
            error = str(exc_val) if exc_val else None
            
            self.logger.log_performance_metric(
                operation=self.operation,
                duration=duration,
                resource_usage={
                    "success": success,
                    "error": error,
                    **self.context
                }
            )


# Global logger instance for convenience
_global_logger: Optional[LGDALogger] = None


def get_logger() -> LGDALogger:
    """Get the global logger instance, initializing if needed."""
    global _global_logger
    if _global_logger is None:
        _global_logger = LGDALogger()
    return _global_logger


def set_request_context(request_id: Optional[str] = None,
                       user_id: Optional[str] = None,
                       session_id: Optional[str] = None) -> LoggingContext:
    """Set request correlation context."""
    return LoggingContext(request_id, user_id, session_id)


def disable_logging():
    """Disable structured logging globally."""
    global _global_logger
    _global_logger = LGDALogger(enabled=False)