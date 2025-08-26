from __future__ import annotations

import time

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

    # Timing wrapper to record per-node durations (LGDA-018 visibility in CLI)
    def _timed(node_fn, name):
        def _wrapped(state: AgentState):
            # Initialize pipeline timing once
            if state.pipeline_start_time is None:
                state.start_pipeline_timing()
            t0 = time.time()
            try:
                return node_fn(state)
            finally:
                duration = time.time() - t0
                try:
                    state.record_node_timing(name, duration)
                except Exception:
                    # Timing should never break the pipeline
                    pass

        return _wrapped

    graph.add_node("plan", _timed(plan_node, "plan"))
    graph.add_node("synthesize_sql", _timed(synthesize_sql_node, "synthesize_sql"))
    graph.add_node("validate_sql", _timed(validate_sql_node, "validate_sql"))
    graph.add_node("execute_sql", _timed(execute_sql_node, "execute_sql"))
    graph.add_node("analyze_df", _timed(analyze_df_node, "analyze_df"))
    graph.add_node("report", _timed(report_node, "report"))
    graph.add_node("error_handler", _timed(error_handler_node, "error_handler"))

    graph.set_entry_point("plan")

    graph.add_edge("plan", "synthesize_sql")
    graph.add_edge("synthesize_sql", "validate_sql")

    def on_valid(state: AgentState):
        # Proceed when validation passed
        if state.error is None:
            return "execute_sql"

        # Validation failed - check if we can retry
        if state.retry_count < state.max_retries:
            # Go back to synthesize_sql for retry
            return "synthesize_sql"
        else:
            # Retries exhausted - go to error handler
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
        # No error -> proceed to analysis
        if state.error is None:
            return "analyze_df"
        # If execute failed and we still have retries, go back to synthesize_sql
        if getattr(state, "retry_count", 0) < getattr(state, "max_retries", 0):
            return "synthesize_sql"
        # Otherwise handle the error
        return "error_handler"

    graph.add_conditional_edges(
        "execute_sql",
        on_exec,
        {
            "analyze_df": "analyze_df",
            "synthesize_sql": "synthesize_sql",
            "error_handler": "error_handler",
        },
    )

    # normal flow: analyze_df -> report -> END
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
                if (
                    hasattr(final_state, "pipeline_start_time")
                    and final_state.pipeline_start_time is None
                ):
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
