import json
from unittest.mock import Mock, patch

import pandas as pd

from src.agent.graph import build_graph
from src.agent.state import AgentState

# mimic fixtures
sample_schema_response = [
    {"table_name": "orders", "column_name": "order_id", "data_type": "INTEGER"},
    {"table_name": "orders", "column_name": "user_id", "data_type": "INTEGER"},
    {"table_name": "orders", "column_name": "created_at", "data_type": "TIMESTAMP"},
]

sample_query_result = pd.DataFrame(
    {
        "order_id": [1, 2, 3],
        "user_id": [10, 11, 12],
        "created_at": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
    }
)

# patch bigquery client
with patch("src.bq.bigquery.Client") as mock_client_class:
    mock_client = Mock()
    mock_client_class.return_value = mock_client
    mock_schema_job = Mock()
    mock_schema_job.result.return_value = sample_schema_response
    mock_data_job = Mock()
    mock_data_job.result.return_value.to_dataframe.return_value = sample_query_result

    def default_query_side_effect(sql, job_config=None):
        if "INFORMATION_SCHEMA" in sql:
            return mock_schema_job
        else:
            return mock_data_job

    mock_client.query = Mock(side_effect=default_query_side_effect)

    # patch genai
    with patch("src.llm.providers.gemini.genai") as mock_genai:
        mock_model = Mock()
        mock_response = Mock()

        def mock_generate_content(prompt):
            if "sql" in prompt.lower() or "select" in prompt.lower():
                mock_response.text = (
                    "SELECT order_id, user_id, created_at FROM orders LIMIT 10"
                )
            elif "plan" in prompt.lower() or "schema" in prompt.lower():
                mock_response.text = '{"task": "analysis", "tables": ["orders"]}'
            else:
                mock_response.text = "Report: everything looks ok"
            return mock_response

        mock_model.generate_content = Mock(side_effect=mock_generate_content)
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.configure = Mock()

        app = build_graph()
        initial_state = AgentState(question="What are the top selling products?")
        final_state = app.invoke(initial_state)
        # Inspect LLM report completion directly for debugging
        from src.llm import llm_completion

        plan = json.dumps(final_state.plan_json, ensure_ascii=False)
        summary = json.dumps(final_state.df_summary, ensure_ascii=False, default=str)[
            :30000
        ]
        prompt = (
            f"Question: {final_state.question}\n"
            f"PLAN: {plan}\n"
            f"DF SUMMARY (truncated): {summary}\n"
            "Write a concise executive insight with numeric evidence and 1–2 next questions."
        )
        print("LLM completion for report prompt:", repr(llm_completion(prompt)))
        print("FINAL STATE:", final_state.model_dump())
