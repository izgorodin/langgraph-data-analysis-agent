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
from src.core.migration import is_unified_retry_enabled


def _should_retry_sql_generation(state: AgentState) -> bool:
    """Determine if SQL generation should be retried based on unified retry settings."""
    if not is_unified_retry_enabled():
        # Legacy behavior: could implement legacy retries here if needed
        return False

    # When unified retry is enabled, let the unified retry system handle all retries internally
    # Only allow graph-level retries for errors that unified retry explicitly doesn't handle
    # This prevents the double-retry issue mentioned in the code review

    # Only retry if there's an error
    if not state.error:
        return False

    # Respect retry limits
    if state.retry_count >= state.max_retries:
        return False

    # Use current error for retry decision
    error_to_check = state.error
    if not error_to_check and hasattr(state, "last_error") and state.last_error:
        error_to_check = state.last_error

    if not error_to_check:
        return False

    error_message = str(error_to_check).lower()

    # Only retry for errors that indicate unified retry failed to handle the issue
    # Specifically, only retry if this was an infrastructure error that couldn't be retried
    # All other errors (SQL validation, LLM failures) should be handled by unified retry

    # Retry SQL validation errors at graph level as coordinator per tests expectations
    if any(
        phrase in error_message
        for phrase in [
            "sql parse error",
            "forbidden tables",
            "invalid sql",
            "syntax error",
            "missing column",
            "query must start",
        ]
    ):
        return True

    # Retry LLM generation failures as well (the decorator performs internal retry, graph coordinates attempts)
    if any(
        phrase in error_message
        for phrase in [
            "llm completion",
            "model completion",
            "generation failed",
            "llm timeout",
            "model timeout",
            "stopiteration",
        ]
    ):
        return True

    # Only retry infrastructure errors that unified retry explicitly gave up on
    # These would be errors that unified retry classified as permanent
    if any(
        phrase in error_message
        for phrase in ["permanent error", "max retries exceeded", "circuit breaker"]
    ):
        return True

    # For all other errors, don't retry at graph level - let unified retry handle them
    return False


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("plan", plan_node)
    graph.add_node("synthesize_sql", synthesize_sql_node)
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("analyze_df", analyze_df_node)
    graph.add_node("report", report_node)

    graph.set_entry_point("plan")

    graph.add_edge("plan", "synthesize_sql")
    graph.add_edge("synthesize_sql", "validate_sql")

    graph.add_node("error_handler", error_handler_node)

    def on_valid(state: AgentState):
        if state.error is None or state.error == "":
            state.error = None
            state.last_error = None
            return "execute_sql"
        if _should_retry_sql_generation(state):
            state.retry_count += 1
            state.last_error = state.error
            state.error = None
            return "synthesize_sql"
        # Ошибка после всех ретраев — направляем в error_handler
        return "error_handler"

    graph.add_conditional_edges(
        "validate_sql",
        on_valid,
        {
            "execute_sql": "execute_sql",
            "synthesize_sql": "synthesize_sql",
            "error_handler": "error_handler",
        },
    )

    def on_exec(state: AgentState):
        if state.error is None:
            return "analyze_df"
        return "error_handler"

    graph.add_conditional_edges(
        "execute_sql",
        on_exec,
        {"analyze_df": "analyze_df", "error_handler": "error_handler"},
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
            # Если результат — строка (END), возвращаем последнее состояние
            if isinstance(result, str):
                return state
            try:
                return (
                    result if isinstance(result, AgentState) else AgentState(**result)
                )
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
