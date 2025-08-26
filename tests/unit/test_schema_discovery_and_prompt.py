import pytest

from src.agent.nodes import synthesize_sql_node
from src.agent.schema import discover_schema
from src.agent.state import AgentState


def test_discover_schema_smoke(monkeypatch):
    # Mock get_schema and run_query via monkeypatching bq.get_schema indirectly
    called = {"get_schema": False, "run_query": False}

    def fake_get_schema(tables):
        called["get_schema"] = True
        return [{"table_name": t, "column_name": "id"} for t in tables]

    def fake_run_query(sql):
        called["run_query"] = True

        class FakeDF:
            def head(self, n):
                return self

            def to_dict(self, orient="records"):
                return [{"id": 1}]

        return FakeDF()

    import src.bq as bq_mod

    monkeypatch.setattr(bq_mod, "get_schema", fake_get_schema)
    monkeypatch.setattr(bq_mod, "run_query", fake_run_query)

    schema = discover_schema(["orders", "users"], sample_rows=1)
    assert "orders" in schema and "users" in schema
    assert schema["orders"]["columns"] == ["id"]
    assert schema["orders"]["sample"] == [{"id": 1}]


def test_synthesize_includes_compact_schema(monkeypatch):
    # Ensure synthesize_sql_node includes the compact schema string when schema_snapshot is present
    state = AgentState(question="Top products", plan_json={"tables": ["orders"]})

    # Monkeypatch discover_schema to return known snapshot
    from src.agent import schema as schema_mod

    monkeypatch.setattr(
        schema_mod,
        "discover_schema",
        lambda tables: {"orders": {"columns": ["order_id", "user_id"]}},
    )

    # Monkeypatch llm_completion to capture prompt
    captured = {}

    def fake_llm_completion(prompt, system=None):
        captured["prompt"] = prompt
        return "SELECT 1"

    import src.agent.nodes as nodes_mod

    monkeypatch.setattr(nodes_mod, "llm_completion", fake_llm_completion)

    # Ensure discovery node runs first in normal pipeline; call it here for unit test
    from src.agent.nodes import discover_schema_node

    state = discover_schema_node(state)
    out = synthesize_sql_node(state)
    assert state.schema_snapshot is not None
    assert "Tables & columns (sample): orders: order_id, user_id" in captured["prompt"]
    assert out.sql.strip().upper().startswith("SELECT")
