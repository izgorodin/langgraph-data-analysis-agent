from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agent.nodes import (
    analyze_df_node,
    error_handler_node,
    execute_sql_node,
    plan_node,
    report_node,
    synthesize_sql_node,
    validate_sql_node,
)
from src.agent.state import AgentState


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("plan", plan_node)
    graph.add_node("synthesize_sql", synthesize_sql_node)
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("analyze_df", analyze_df_node)
    graph.add_node("report", report_node)
    graph.add_node("error_handler", error_handler_node)

    graph.set_entry_point("plan")

    graph.add_edge("plan", "synthesize_sql")
    graph.add_edge("synthesize_sql", "validate_sql")

    def on_valid(state: AgentState):
        """Enhanced retry logic with error classification and logging."""
        import logging
        from src.error.classification import ErrorClassifier, RecoveryStrategy
        
        logger = logging.getLogger(__name__)
        
        # Proceed when validation passed
        if state.error is None:
            return "execute_sql"
            
        # Classify the error to determine retry strategy
        classifier = ErrorClassifier()
        strategy, severity = classifier.classify(state.error)
        
        # Log the retry decision
        logger.info(
            "Validation error encountered, determining retry strategy",
            extra={
                "error": state.error,
                "strategy": strategy.value,
                "severity": severity.value,
                "retry_count": state.retry_count,
                "max_retries": state.max_retries,
                "node": "validate_sql"
            }
        )
        
        # Check if error is retryable and within retry limits
        is_retryable = strategy in {RecoveryStrategy.USER_GUIDED, RecoveryStrategy.IMMEDIATE_RETRY}
        within_retry_limit = state.retry_count < state.max_retries
        
        if is_retryable and within_retry_limit:
            logger.info(
                "Initiating retry for validation error",
                extra={
                    "retry_attempt": state.retry_count + 1,
                    "max_retries": state.max_retries,
                    "error_category": strategy.value,
                    "node": "validate_sql"
                }
            )
            return "synthesize_sql"
        else:
            # Log why retry was not attempted
            reason = "non-retryable error" if not is_retryable else "retry limit exceeded"
            logger.warning(
                "No retry attempted for validation error",
                extra={
                    "reason": reason,
                    "error": state.error,
                    "strategy": strategy.value,
                    "retry_count": state.retry_count,
                    "max_retries": state.max_retries,
                    "node": "validate_sql"
                }
            )
            return "error_handler"

    graph.add_conditional_edges(
        "validate_sql",
        on_valid,
        {"execute_sql": "execute_sql", "synthesize_sql": "synthesize_sql", "error_handler": "error_handler"},
    )

    def on_exec(state: AgentState):
        return "analyze_df" if state.error is None else "error_handler"

    graph.add_conditional_edges(
        "execute_sql", on_exec, {"analyze_df": "analyze_df", "error_handler": "error_handler"}
    )
    graph.add_edge("analyze_df", "report")
    graph.add_edge("report", END)
    graph.add_edge("error_handler", END)

    app = graph.compile()

    # Wrap to ensure invoke returns AgentState and stream yields JSON-safe dicts
    class _AppWrapper:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def invoke(self, state, *args, **kwargs):
            result = self._inner.invoke(state, *args, **kwargs)
            try:
                final_state = (
                    result if isinstance(result, AgentState) else AgentState(**result)
                )
                # LGDA-018: Ensure timing is initialized if not already done
                if hasattr(final_state, 'pipeline_start_time') and final_state.pipeline_start_time is None:
                    final_state.start_pipeline_timing()
                return final_state
            except Exception:
                return result

        def stream(self, state, *args, **kwargs):
            for event in self._inner.stream(state, *args, **kwargs):
                converted = {}
                for node, s in event.items():
                    if isinstance(s, AgentState):
                        converted[node] = s.model_dump()
                    else:
                        converted[node] = s
                yield converted

    return _AppWrapper(app)
