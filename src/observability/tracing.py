"""Distributed tracing support for LGDA production observability.

Provides end-to-end visibility, performance profiling, dependency mapping,
and error correlation across distributed components.

Can be disabled via LGDA_DISABLE_OBSERVABILITY environment variable.
"""

import logging
import os
import time
import uuid
from typing import Any, Dict, Optional, Union

# OpenTelemetry is optional - graceful degradation if not available
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import Status, StatusCode

    try:
        from opentelemetry.exporter.jaeger.thrift import JaegerExporter

        JAEGER_AVAILABLE = True
    except ImportError:
        JAEGER_AVAILABLE = False
    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False

logger = logging.getLogger(__name__)


class LGDATracer:
    """Production-grade distributed tracing for LGDA pipeline.

    Provides comprehensive tracing with graceful degradation when OpenTelemetry
    is not available or when observability is disabled.
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        service_name: str = "lgda",
        jaeger_endpoint: Optional[str] = None,
    ):
        """Initialize distributed tracer.

        Args:
            enabled: Override default enabled state. If None, uses environment.
            service_name: Name of the service for tracing.
            jaeger_endpoint: Jaeger collector endpoint.
        """
        if enabled is None:
            # Check for disable flag
            self.enabled = (
                not os.getenv("LGDA_DISABLE_OBSERVABILITY", "false").lower() == "true"
            )
        else:
            self.enabled = enabled

        self.enabled = self.enabled and OPENTELEMETRY_AVAILABLE
        self.service_name = service_name

        if not self.enabled:
            logger.info("LGDA distributed tracing disabled")
            return

        try:
            self._initialize_tracing(jaeger_endpoint)
            logger.info("LGDA distributed tracing initialized")
        except Exception as e:
            logger.error(f"Failed to initialize tracing: {e}")
            self.enabled = False

    def _initialize_tracing(self, jaeger_endpoint: Optional[str]):
        """Initialize OpenTelemetry tracing."""
        # Set up tracer provider
        trace.set_tracer_provider(TracerProvider())
        self.tracer = trace.get_tracer(__name__, version="1.0.0")

        # Set up exporters
        tracer_provider = trace.get_tracer_provider()

        # Console exporter for development
        console_processor = BatchSpanProcessor(ConsoleSpanExporter())
        tracer_provider.add_span_processor(console_processor)

        # Jaeger exporter if available and configured
        if JAEGER_AVAILABLE and jaeger_endpoint:
            try:
                jaeger_exporter = JaegerExporter(
                    agent_host_name="localhost",
                    agent_port=14268,
                    collector_endpoint=jaeger_endpoint,
                )
                jaeger_processor = BatchSpanProcessor(jaeger_exporter)
                tracer_provider.add_span_processor(jaeger_processor)
                logger.info(f"Jaeger tracing configured: {jaeger_endpoint}")
            except Exception as e:
                logger.warning(f"Failed to configure Jaeger: {e}")

    def trace_pipeline_execution(self, question: str, **attributes):
        """Trace complete pipeline execution."""
        if not self.enabled:
            return NoOpSpan()

        try:
            span = self.tracer.start_span("lgda_pipeline")
            span.set_attribute("question", question)
            span.set_attribute("pipeline.version", "1.0")
            span.set_attribute("service.name", self.service_name)

            for key, value in attributes.items():
                span.set_attribute(key, str(value))

            return TracedOperation(span)
        except Exception as e:
            logger.error(f"Failed to start pipeline trace: {e}")
            return NoOpSpan()

    def trace_stage_execution(self, stage: str, parent_span=None, **attributes):
        """Trace individual pipeline stage execution."""
        if not self.enabled:
            return NoOpSpan()

        try:
            context = trace.set_span_in_context(parent_span) if parent_span else None
            span = self.tracer.start_span(f"lgda_stage_{stage}", context=context)
            span.set_attribute("stage.name", stage)

            for key, value in attributes.items():
                span.set_attribute(key, str(value))

            return TracedOperation(span)
        except Exception as e:
            logger.error(f"Failed to start stage trace: {e}")
            return NoOpSpan()

    def trace_llm_request(self, provider: str, model: str, **attributes):
        """Trace LLM provider requests."""
        if not self.enabled:
            return NoOpSpan()

        try:
            span = self.tracer.start_span("llm_request")
            span.set_attribute("llm.provider", provider)
            span.set_attribute("llm.model", model)

            for key, value in attributes.items():
                span.set_attribute(key, str(value))

            return TracedOperation(span)
        except Exception as e:
            logger.error(f"Failed to start LLM trace: {e}")
            return NoOpSpan()

    def trace_bigquery_operation(self, operation: str, **attributes):
        """Trace BigQuery operations."""
        if not self.enabled:
            return NoOpSpan()

        try:
            span = self.tracer.start_span("bigquery_operation")
            span.set_attribute("bigquery.operation", operation)

            for key, value in attributes.items():
                span.set_attribute(key, str(value))

            return TracedOperation(span)
        except Exception as e:
            logger.error(f"Failed to start BigQuery trace: {e}")
            return NoOpSpan()

    def trace_custom_operation(self, operation_name: str, **attributes):
        """Trace custom operations."""
        if not self.enabled:
            return NoOpSpan()

        try:
            span = self.tracer.start_span(operation_name)

            for key, value in attributes.items():
                span.set_attribute(key, str(value))

            return TracedOperation(span)
        except Exception as e:
            logger.error(f"Failed to start custom trace: {e}")
            return NoOpSpan()


class TracedOperation:
    """Context manager for traced operations with automatic span management."""

    def __init__(self, span):
        self.span = span
        self.start_time = time.time()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            # Record timing
            duration = time.time() - self.start_time
            self.span.set_attribute("duration_ms", int(duration * 1000))

            # Record error information if present
            if exc_type:
                self.span.set_status(Status(StatusCode.ERROR, str(exc_val)))
                self.span.set_attribute("error.type", exc_type.__name__)
                self.span.set_attribute("error.message", str(exc_val))
            else:
                self.span.set_status(Status(StatusCode.OK))

            self.span.end()
        except Exception as e:
            logger.error(f"Failed to end span: {e}")

    def set_attribute(self, key: str, value: Union[str, int, float, bool]):
        """Set span attribute."""
        try:
            self.span.set_attribute(key, value)
        except Exception as e:
            logger.error(f"Failed to set span attribute: {e}")

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Add event to span."""
        try:
            self.span.add_event(name, attributes or {})
        except Exception as e:
            logger.error(f"Failed to add span event: {e}")

    def record_exception(self, exception: Exception):
        """Record exception in span."""
        try:
            self.span.record_exception(exception)
        except Exception as e:
            logger.error(f"Failed to record exception: {e}")


class NoOpSpan:
    """No-operation span for when tracing is disabled."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def set_attribute(self, key: str, value: Union[str, int, float, bool]):
        pass

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        pass

    def record_exception(self, exception: Exception):
        pass


class TraceContext:
    """Context manager for trace correlation across operations."""

    def __init__(self, operation_name: str, tracer: LGDATracer):
        self.operation_name = operation_name
        self.tracer = tracer
        self.trace_id = str(uuid.uuid4())
        self.span = None

    def __enter__(self):
        self.span = self.tracer.trace_custom_operation(
            self.operation_name, trace_id=self.trace_id
        )
        return self.span.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            return self.span.__exit__(exc_type, exc_val, exc_tb)


# Global tracer instance for convenience
_global_tracer: Optional[LGDATracer] = None


def get_tracer() -> LGDATracer:
    """Get the global tracer instance, initializing if needed."""
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = LGDATracer()
    return _global_tracer


def trace_operation(operation_name: str, **attributes):
    """Decorator for tracing operations."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.trace_custom_operation(operation_name, **attributes) as span:
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("success", True)
                    return result
                except Exception as e:
                    span.record_exception(e)
                    raise

        return wrapper

    return decorator


def disable_tracing():
    """Disable distributed tracing globally."""
    global _global_tracer
    _global_tracer = LGDATracer(enabled=False)
