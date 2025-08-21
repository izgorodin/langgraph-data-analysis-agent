"""Instrumented pipeline nodes for LGDA observability integration.

This module provides instrumented wrappers around existing pipeline nodes
to add comprehensive observability without modifying the core functionality.

The instrumented nodes can be used as drop-in replacements for the original
nodes, with observability being optional and configurable.
"""

import logging
import time
from functools import wraps
from typing import Any, Dict, Optional

from ..agent.nodes import (
    analyze_df_node as analyze_df,
    execute_sql_node as execute_sql,
    plan_node as plan,
    report_node as report,
    synthesize_sql_node as synthesize_sql,
    validate_sql_node as validate_sql,
)
from ..agent.state import AgentState
from .business_metrics import QueryComplexity, get_business_metrics
from .health import get_health_monitor
from .logging import TimedOperation, get_logger, set_request_context
from .metrics import MetricsContext, get_metrics
from .tracing import get_tracer

logger = logging.getLogger(__name__)


def instrument_node(node_name: str):
    """Decorator to instrument pipeline nodes with observability."""

    def decorator(func):
        @wraps(func)
        def wrapper(state: AgentState) -> AgentState:
            # Get observability components
            metrics = get_metrics()
            lgda_logger = get_logger()
            tracer = get_tracer()
            business_metrics = get_business_metrics()

            # Start tracing
            with tracer.trace_stage_execution(
                node_name, question=getattr(state, "question", "")
            ) as span:
                # Start timing
                start_time = time.time()

                # Set up logging context
                with set_request_context(
                    request_id=getattr(state, "request_id", None),
                    user_id=getattr(state, "user_id", None),
                    session_id=getattr(state, "session_id", None),
                ):
                    try:
                        # Execute the original node function (synchronous)
                        result = func(state)

                        # Calculate metrics
                        duration = time.time() - start_time

                        # LGDA-018: Record timing in state for aggregation
                        result.record_node_timing(node_name, duration)

                        # Record success metrics
                        metrics.record_pipeline_stage(node_name, duration)
                        business_metrics.track_pipeline_performance(
                            node_name, duration, True
                        )

                        # Log successful execution with timing
                        lgda_logger.log_pipeline_stage(
                            node_name,
                            duration,
                            input_size=_estimate_state_size(state),
                            output_size=_estimate_state_size(result),
                            success=True,
                        )

                        # Add span attributes
                        span.set_attribute("success", True)
                        span.set_attribute("duration_ms", int(duration * 1000))
                        span.set_attribute("output_size", _estimate_state_size(result))

                        return result

                    except Exception as e:
                        # Calculate metrics for failure
                        duration = time.time() - start_time
                        error_type = type(e).__name__

                        # LGDA-018: Record timing even for failed nodes
                        state.record_node_timing(node_name, duration)

                        # Record error metrics
                        metrics.record_pipeline_stage(node_name, duration, error_type)
                        business_metrics.track_pipeline_performance(
                            node_name, duration, False
                        )
                        business_metrics.track_error_patterns(
                            error_type, node_name, False
                        )

                        # Log error
                        lgda_logger.log_pipeline_stage(
                            node_name,
                            duration,
                            input_size=_estimate_state_size(state),
                            success=False,
                            error=str(e),
                        )

                        # Add span error info
                        span.record_exception(e)
                        span.set_attribute("success", False)
                        span.set_attribute("duration_ms", int(duration * 1000))
                        span.set_attribute("error_type", error_type)

                        # Re-raise the exception
                        raise

        return wrapper

    return decorator


def _estimate_state_size(state: AgentState) -> int:
    """Estimate the size of the agent state for metrics."""
    try:
        # Simple estimation based on string representation
        return len(str(state))
    except Exception:
        return 0


def _determine_query_complexity(question: str, sql: str = "") -> QueryComplexity:
    """Determine query complexity based on question and SQL."""
    # Simple heuristic based on question length and SQL complexity
    question_length = len(question)
    sql_length = len(sql)

    # Count complexity indicators
    complexity_indicators = 0
    if "join" in sql.lower():
        complexity_indicators += 1
    if "group by" in sql.lower():
        complexity_indicators += 1
    if "order by" in sql.lower():
        complexity_indicators += 1
    if "having" in sql.lower():
        complexity_indicators += 1
    if "window" in sql.lower() or "over(" in sql.lower():
        complexity_indicators += 1

    # Determine complexity
    if question_length < 50 and complexity_indicators == 0:
        return QueryComplexity.SIMPLE
    elif question_length < 100 and complexity_indicators <= 1:
        return QueryComplexity.MEDIUM
    elif question_length < 200 and complexity_indicators <= 3:
        return QueryComplexity.COMPLEX
    else:
        return QueryComplexity.VERY_COMPLEX


# Instrumented node functions
@instrument_node("plan")
def instrumented_plan(state: AgentState) -> AgentState:
    """Instrumented planning node."""
    lgda_logger = get_logger()
    business_metrics = get_business_metrics()

    # LGDA-018: Initialize pipeline timing at the start
    state.start_pipeline_timing()

    # Log the incoming question
    lgda_logger.log_audit_trail(
        "plan_request", "question", details={"question_preview": state.question[:100]}
    )

    # Determine complexity
    complexity = _determine_query_complexity(state.question)

    # Track user patterns
    business_metrics.track_user_patterns(
        question_category="analysis",  # Could be enhanced with NLP categorization
        complexity=complexity.value,
        user_id=getattr(state, "user_id", None),
        session_id=getattr(state, "session_id", None),
    )

    return plan(state)


@instrument_node("synthesize_sql")
def instrumented_synthesize_sql(state: AgentState) -> AgentState:
    """Instrumented SQL synthesis node."""
    lgda_logger = get_logger()

    # Log LLM request details
    lgda_logger.log_llm_request(
        provider="gemini",  # Could be dynamic based on config
        model="gemini-1.5-pro",  # Could be dynamic based on config
        prompt_length=len(state.plan_json.get("task", "")) if state.plan_json else 0,
    )

    return synthesize_sql(state)


@instrument_node("validate_sql")
def instrumented_validate_sql(state: AgentState) -> AgentState:
    """Instrumented SQL validation node."""
    lgda_logger = get_logger()

    # Log security validation
    lgda_logger.log_security_event(
        "sql_validation",
        details={
            "sql_length": len(state.sql) if state.sql else 0,
            "has_limit": "limit" in (state.sql or "").lower(),
        },
    )

    return validate_sql(state)


@instrument_node("execute_sql")
def instrumented_execute_sql(state: AgentState) -> AgentState:
    """Instrumented SQL execution node."""
    metrics = get_metrics()
    lgda_logger = get_logger()
    business_metrics = get_business_metrics()
    tracer = get_tracer()

    # Track BigQuery operation
    with tracer.trace_bigquery_operation(
        "execute_query", sql_length=len(state.sql) if state.sql else 0
    ) as span:

        result = execute_sql(state)

        # Extract execution details from result
        success = not bool(state.error)
        bytes_processed = getattr(state, "bytes_processed", None)
        execution_time = getattr(state, "execution_time", None)

        # Record BigQuery metrics
        metrics.record_query_execution(success, bytes_processed)

        # Log query execution
        lgda_logger.log_query_execution(
            question=state.question,
            sql=state.sql or "",
            execution_time=execution_time or 0,
            success=success,
            error=state.error,
            bytes_processed=bytes_processed,
            row_count=(
                len(state.df) if hasattr(state, "df") and state.df is not None else 0
            ),
        )

        # Track business metrics
        complexity = _determine_query_complexity(state.question, state.sql or "")
        business_metrics.track_query_success_rate(
            success=success,
            question=state.question,
            complexity=complexity,
            execution_time=execution_time,
            error_type=type(state.error).__name__ if state.error else None,
        )

        # Update span with execution details
        span.set_attribute("bytes_processed", bytes_processed or 0)
        span.set_attribute(
            "row_count",
            len(state.df) if hasattr(state, "df") and state.df is not None else 0,
        )

        return result


@instrument_node("analyze_df")
def instrumented_analyze_df(state: AgentState) -> AgentState:
    """Instrumented data analysis node."""
    lgda_logger = get_logger()

    # Log data analysis details
    if hasattr(state, "df") and state.df is not None:
        lgda_logger.log_performance_metric(
            operation="dataframe_analysis",
            duration=0,  # Will be updated by the timing wrapper
            resource_usage={
                "dataframe_rows": len(state.df),
                "dataframe_columns": len(state.df.columns),
                "memory_usage_mb": state.df.memory_usage(deep=True).sum() / 1024 / 1024,
            },
        )

    return analyze_df(state)


@instrument_node("report")
def instrumented_report(state: AgentState) -> AgentState:
    """Instrumented report generation node."""
    metrics = get_metrics()
    lgda_logger = get_logger()
    business_metrics = get_business_metrics()

    result = report(state)

    # Track insight generation
    if result.report:
        metrics.record_insight_generation(
            quality_score=0.8
        )  # Could be enhanced with quality assessment

        business_metrics.track_insight_quality(
            feedback_score=0.8,  # Could be enhanced with actual user feedback
            question=state.question,
            insight_length=len(result.report),
        )

        # Log report generation
        lgda_logger.log_business_metric(
            "insights_generated",
            1.0,
            dimensions={
                "report_length": str(len(result.report)),
                "has_summary": str(bool(getattr(state, "df_summary", None))),
            },
        )

    # LGDA-018: Generate and log final timing summary
    timing_summary = result.get_timing_summary()
    if timing_summary["node_count"] > 0:
        lgda_logger.log_performance_metric(
            operation="pipeline_execution",
            duration=timing_summary.get("total_duration", 0),
            resource_usage={
                "node_timings": timing_summary["pipeline_timing"],
                "total_nodes": timing_summary["node_count"],
                "overhead_percentage": timing_summary.get("overhead_percentage", 0),
            },
        )
        
        # Log summary for immediate visibility
        logger.info(f"Pipeline timing summary: {timing_summary}")

    return result


# Mapping of instrumented nodes for easy replacement
INSTRUMENTED_NODES = {
    "plan": instrumented_plan,
    "synthesize_sql": instrumented_synthesize_sql,
    "validate_sql": instrumented_validate_sql,
    "execute_sql": instrumented_execute_sql,
    "analyze_df": instrumented_analyze_df,
    "report": instrumented_report,
}


def get_instrumented_node(node_name: str):
    """Get an instrumented version of a pipeline node."""
    return INSTRUMENTED_NODES.get(node_name)


def enable_observability_for_graph(graph_config: Dict[str, Any]) -> Dict[str, Any]:
    """Enable observability for a LangGraph configuration.

    This function can be used to replace regular nodes with instrumented ones
    in a graph configuration.
    """
    # This would need to be implemented based on the actual graph structure
    # For now, return the config as-is
    return graph_config
