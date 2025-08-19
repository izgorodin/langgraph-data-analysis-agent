from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import (
    analyze_df_node,
    execute_sql_node,
    plan_node,
    report_node,
    synthesize_sql_node,
    validate_sql_node,
)
from .state import AgentState


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
        return "execute_sql" if state.error is None else END

    graph.add_conditional_edges(
        "validate_sql", on_valid, {"execute_sql": "execute_sql", END: END}
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
