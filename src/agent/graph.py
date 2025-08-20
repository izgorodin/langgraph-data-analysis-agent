from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agent.nodes import (
    analyze_df_node,
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
        # Legacy behavior: no retries at graph level
        return False
    
    # Only retry business logic errors, not infrastructure errors
    if state.error is None or state.last_error is None:
        return False
    
    # Respect retry limits
    if state.retry_count >= state.max_retries:
        return False
    
    # Only retry validation errors and LLM generation errors
    # Don't retry infrastructure errors (those are handled at lower levels)
    error_message = str(state.last_error).lower()
    
    # Retry SQL validation errors (business logic)
    if any(phrase in error_message for phrase in [
        "sql parse error", "forbidden tables", "invalid sql", 
        "syntax error", "missing column", "query must start"
    ]):
        return True
    
    # Retry LLM generation failures (business logic) - be more specific
    if any(phrase in error_message for phrase in [
        "llm completion", "model completion", "generation failed", 
        "llm timeout", "model timeout"
    ]):
        return True
    
    # Don't retry infrastructure errors (handled by lower-level retry)
    # These include: "connection error", "network timeout", "server error", etc.
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

    def on_valid(state: AgentState):
        # Proceed when validation passed
        if state.error is None:
            return "execute_sql"
        
        # Check if we should retry SQL generation with unified retry
        if _should_retry_sql_generation(state):
            state.retry_count += 1
            return "synthesize_sql"
        
        # Validation failed and no retry - end execution
        return END

    graph.add_conditional_edges(
        "validate_sql",
        on_valid,
        {"execute_sql": "execute_sql", "synthesize_sql": "synthesize_sql", END: END},
    )

    def on_exec(state: AgentState):
        return "analyze_df" if state.error is None else END

    graph.add_conditional_edges(
        "execute_sql", on_exec, {"analyze_df": "analyze_df", END: END}
    )
    graph.add_edge("analyze_df", "report")
    graph.add_edge("report", END)

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
