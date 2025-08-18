from __future__ import annotations
from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import (
    plan_node,
    synthesize_sql_node,
    validate_sql_node,
    execute_sql_node,
    analyze_df_node,
    report_node,
)


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

    graph.add_conditional_edges("validate_sql", on_valid, {"execute_sql": "execute_sql", END: END})
    graph.add_edge("execute_sql", "analyze_df")
    graph.add_edge("analyze_df", "report")
    graph.add_edge("report", END)

    app = graph.compile()
    return app
