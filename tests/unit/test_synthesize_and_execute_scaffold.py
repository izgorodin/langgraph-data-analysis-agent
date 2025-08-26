import pytest

from src.agent import nodes
from src.agent.state import AgentState


class DummyConfig:
    def __init__(self):
        self.sql_scaffold_enabled = True
        self.strict_no_fake_report = True


def test_synthesize_scaffold_uses_schema_columns(monkeypatch):
    # Mock get_schema to return a small, realistic schema
    def fake_get_schema(tables):
        return [
            {"table_name": "orders", "column_name": "order_id"},
            {"table_name": "orders", "column_name": "created_at"},
            {"table_name": "order_items", "column_name": "order_id"},
            {"table_name": "order_items", "column_name": "sale_price"},
            {"table_name": "products", "column_name": "id"},
            {"table_name": "products", "column_name": "category"},
        ]

    monkeypatch.setattr(nodes, "get_schema", fake_get_schema)
    # Force llm_completion to return empty string to trigger scaffold fallback
    monkeypatch.setattr(nodes, "llm_completion", lambda *a, **k: "")
    # Ensure scaffolding is enabled in config
    monkeypatch.setattr(nodes, "LGDAConfig", lambda: DummyConfig())

    state = AgentState(question="test", plan_json={"tables": ["orders", "order_items"]})
    res = nodes.synthesize_sql_node(state)

    assert res.sql is not None and res.sql.strip() != ""
    # Scaffolded SQL uses LIMIT 10 per implementation
    assert "LIMIT 10" in res.sql
    # History should include scaffold note
    notes = [h.get("note") for h in res.history if isinstance(h, dict)]
    assert "sql_scaffold_fallback_enhanced" in notes
    # SQL should reference at least one known column from schema
    assert "order_id" in res.sql or "sale_price" in res.sql


def test_execute_detects_scaffold_error(monkeypatch):
    # Simulate BigQuery error that indicates missing column inside alias
    def fake_run_query(sql):
        raise Exception("Name iu not found inside p at [1:1]")

    monkeypatch.setattr(nodes, "run_query", fake_run_query)

    state = AgentState(question="q")
    state.sql = "SELECT 1"
    res = nodes.execute_sql_node(state)

    assert res.error is not None
    # History should contain scaffold_error_detected entry
    scaffold_notes = [
        h
        for h in res.history
        if isinstance(h, dict) and h.get("note") == "scaffold_error_detected"
    ]
    assert len(scaffold_notes) == 1
