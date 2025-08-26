from src.agent.nodes import synthesize_sql_node
from src.agent.state import AgentState

s = AgentState()
s.question = "Test"
s.plan_json = {
    "task": "test",
    "tables": ["orders", "order_items", "products", "users"],
    "time_range": {"start": "2022-01-01", "end": "2022-12-31"},
}

s = synthesize_sql_node(s)
print("SQL:", s.sql)
print("HISTORY:", s.history)
