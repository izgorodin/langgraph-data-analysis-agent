"""Utilities for creating mocks and test helpers."""

import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock

import google.generativeai as genai
import pandas as pd
from google.api_core.exceptions import BadRequest, Forbidden, NotFound
from google.cloud import bigquery

from src.agent.state import AgentState


class MockBigQueryHelper:
    """Helper class for creating BigQuery mocks."""

    @staticmethod
    def create_client_mock(
        schema_data: List[Dict] = None, query_results: pd.DataFrame = None
    ):
        """Create a mock BigQuery client with configurable responses."""
        mock_client = Mock(spec=bigquery.Client)

        # Mock schema query responses
        if schema_data:
            mock_schema_job = Mock()
            mock_schema_job.result.return_value = schema_data
        else:
            mock_schema_job = Mock()
            mock_schema_job.result.return_value = []

        # Mock data query responses
        if query_results is not None:
            mock_data_job = Mock()
            mock_data_job.result.return_value.to_dataframe.return_value = query_results
        else:
            mock_data_job = Mock()
            mock_data_job.result.return_value.to_dataframe.return_value = pd.DataFrame()

        def mock_query(sql, job_config=None):
            if "INFORMATION_SCHEMA" in sql:
                return mock_schema_job
            else:
                return mock_data_job

        mock_client.query = mock_query
        return mock_client

    @staticmethod
    def create_error_client(
        error_type: str = "BadRequest", message: str = "Test error"
    ):
        """Create a mock BigQuery client that raises errors."""
        mock_client = Mock(spec=bigquery.Client)

        if error_type == "BadRequest":
            error = BadRequest(message)
        elif error_type == "Forbidden":
            error = Forbidden(message)
        elif error_type == "NotFound":
            error = NotFound(message)
        else:
            error = Exception(message)

        mock_client.query.side_effect = error
        return mock_client

    @staticmethod
    def create_job_config_mock(**kwargs):
        """Create a mock BigQuery job configuration."""
        mock_config = Mock(spec=bigquery.QueryJobConfig)
        for key, value in kwargs.items():
            setattr(mock_config, key, value)
        return mock_config


class MockGeminiHelper:
    """Helper class for creating Gemini LLM mocks."""

    @staticmethod
    def create_client_mock(responses: Dict[str, str] = None):
        """Create a mock Gemini client with configurable responses."""
        mock_genai = Mock()
        mock_model = Mock()
        mock_response = Mock()

        default_responses = {
            "plan": '{"task": "analysis", "tables": ["orders"], "metrics": ["count"]}',
            "sql": "SELECT COUNT(*) FROM orders WHERE status = 'Complete' LIMIT 1000",
            "report": "Analysis shows 100 completed orders with strong performance indicators.",
        }

        if responses:
            default_responses.update(responses)

        def mock_generate_content(prompt):
            # Determine response type based on prompt content
            prompt_lower = prompt.lower()
            if any(keyword in prompt_lower for keyword in ["plan", "schema", "task"]):
                mock_response.text = default_responses["plan"]
            elif any(keyword in prompt_lower for keyword in ["sql", "select", "query"]):
                mock_response.text = default_responses["sql"]
            else:
                mock_response.text = default_responses["report"]
            return mock_response

        mock_model.generate_content = mock_generate_content
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.configure = Mock()

        return mock_genai

    @staticmethod
    def create_error_client(error_message: str = "LLM API Error"):
        """Create a mock Gemini client that raises errors."""
        mock_genai = Mock()
        mock_model = Mock()
        mock_model.generate_content.side_effect = Exception(error_message)
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.configure = Mock()
        return mock_genai

    @staticmethod
    def create_response_sequence(responses: List[str]):
        """Create a mock that returns responses in sequence."""
        mock_genai = Mock()
        mock_model = Mock()

        response_iter = iter(responses)

        def mock_generate_content(prompt):
            mock_response = Mock()
            try:
                mock_response.text = next(response_iter)
            except StopIteration:
                mock_response.text = responses[-1]  # Return last response if exhausted
            return mock_response

        mock_model.generate_content = mock_generate_content
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.configure = Mock()

        return mock_genai


class StateTestHelper:
    """Helper class for creating and manipulating AgentState objects."""

    @staticmethod
    def create_minimal_state(question: str = "Test question") -> AgentState:
        """Create a minimal AgentState for testing."""
        return AgentState(question=question)

    @staticmethod
    def create_complete_state(
        question: str = "Complete test question",
        plan: Dict[str, Any] = None,
        sql: str = None,
        df_summary: Dict[str, Any] = None,
        report: str = None,
        error: str = None,
        history: List[Dict[str, str]] = None,
    ) -> AgentState:
        """Create a complete AgentState with all fields populated."""
        if plan is None:
            plan = {"task": "test_analysis", "tables": ["orders"]}

        if sql is None:
            sql = "SELECT * FROM orders LIMIT 10"

        if df_summary is None:
            df_summary = {
                "rows": 10,
                "columns": ["order_id", "status"],
                "head": [{"order_id": 1, "status": "Complete"}],
                "describe": {"order_id": {"count": 10, "mean": 5.5}},
            }

        if report is None:
            report = "Test analysis complete with 10 orders processed."

        if history is None:
            history = [{"step": "plan", "status": "complete"}]

        return AgentState(
            question=question,
            plan_json=plan,
            sql=sql,
            df_summary=df_summary,
            report=report,
            error=error,
            history=history,
        )

    @staticmethod
    def create_error_state(
        question: str = "Error test", error: str = "Test error"
    ) -> AgentState:
        """Create an AgentState with an error condition."""
        return AgentState(question=question, error=error)

    @staticmethod
    def assert_state_progression(
        initial: AgentState, final: AgentState, expected_fields: List[str]
    ):
        """Assert that state has progressed with expected fields populated."""
        # Question should be preserved
        assert final.question == initial.question

        # Expected fields should be populated
        for field in expected_fields:
            assert (
                getattr(final, field) is not None
            ), f"Field {field} should be populated"

        # History should be maintained or expanded
        assert len(final.history) >= len(initial.history)

    @staticmethod
    def compare_states(
        state1: AgentState, state2: AgentState, ignore_fields: List[str] = None
    ) -> bool:
        """Compare two AgentState objects, optionally ignoring certain fields."""
        if ignore_fields is None:
            ignore_fields = []

        state1_dict = state1.model_dump()
        state2_dict = state2.model_dump()

        for field in ignore_fields:
            state1_dict.pop(field, None)
            state2_dict.pop(field, None)

        return state1_dict == state2_dict


class DataFrameTestHelper:
    """Helper class for creating test DataFrames."""

    @staticmethod
    def create_orders_dataframe(num_rows: int = 10) -> pd.DataFrame:
        """Create a realistic orders DataFrame for testing."""
        from datetime import datetime, timedelta

        import numpy as np

        return pd.DataFrame(
            {
                "order_id": range(1, num_rows + 1),
                "user_id": np.random.randint(1000, 2000, num_rows),
                "status": np.random.choice(
                    ["Complete", "Processing", "Cancelled", "Shipped"],
                    num_rows,
                    p=[0.6, 0.2, 0.1, 0.1],
                ),
                "created_at": pd.date_range(
                    start=datetime.now() - timedelta(days=30),
                    periods=num_rows,
                    freq="h",
                ),
                "total_amount": np.round(np.random.uniform(20.0, 500.0, num_rows), 2),
            }
        )

    @staticmethod
    def create_products_dataframe(num_rows: int = 20) -> pd.DataFrame:
        """Create a realistic products DataFrame for testing."""
        import numpy as np

        categories = ["Electronics", "Clothing", "Home", "Sports", "Books"]
        brands = ["Brand A", "Brand B", "Brand C", "Brand D", "Brand E"]

        return pd.DataFrame(
            {
                "id": range(1, num_rows + 1),
                "name": [f"Product {i}" for i in range(1, num_rows + 1)],
                "category": np.random.choice(categories, num_rows),
                "brand": np.random.choice(brands, num_rows),
                "retail_price": np.round(np.random.uniform(10.0, 1000.0, num_rows), 2),
                "cost": np.round(np.random.uniform(5.0, 500.0, num_rows), 2),
            }
        )

    @staticmethod
    def create_summary_from_dataframe(df: pd.DataFrame) -> Dict[str, Any]:
        """Create a realistic df_summary from a DataFrame."""
        return {
            "rows": len(df),
            "columns": list(df.columns),
            "head": df.head(10).to_dict(orient="records"),
            "describe": json.loads(df.describe(include="all").to_json()),
        }


class GraphTestHelper:
    """Helper class for testing LangGraph functionality."""

    @staticmethod
    def create_mock_graph_app(states_sequence: List[Dict[str, Any]] = None):
        """Create a mock LangGraph application."""
        mock_app = Mock()

        if states_sequence is None:
            # Default sequence
            states_sequence = [
                {"plan": {"question": "test", "plan_json": {"task": "test"}}},
                {"execute_sql": {"sql": "SELECT 1", "df_summary": {"rows": 1}}},
                {"report": {"report": "Test complete"}},
            ]

        mock_app.stream.return_value = states_sequence

        # Create final state
        final_state = AgentState(
            question="Test question",
            plan_json={"task": "test"},
            sql="SELECT 1",
            df_summary={"rows": 1},
            report="Mock execution complete",
        )
        mock_app.invoke.return_value = final_state

        return mock_app

    @staticmethod
    def extract_node_sequence(stream_events: List[Dict[str, Any]]) -> List[str]:
        """Extract the sequence of nodes from stream events."""
        nodes = []
        for event in stream_events:
            nodes.extend(event.keys())
        return nodes

    @staticmethod
    def assert_node_execution_order(
        events: List[Dict[str, Any]], expected_order: List[str]
    ):
        """Assert that nodes executed in expected order."""
        actual_order = GraphTestHelper.extract_node_sequence(events)

        # Check that expected nodes appear in order (allowing for additional nodes)
        expected_index = 0
        for node in actual_order:
            if (
                expected_index < len(expected_order)
                and node == expected_order[expected_index]
            ):
                expected_index += 1

        assert expected_index == len(
            expected_order
        ), f"Expected order {expected_order}, got {actual_order}"


class TestDataFactory:
    """Factory for creating various test data objects."""

    @staticmethod
    def create_realistic_schema() -> List[Dict[str, str]]:
        """Create realistic BigQuery schema data."""
        return [
            {"table_name": "orders", "column_name": "order_id", "data_type": "INTEGER"},
            {"table_name": "orders", "column_name": "user_id", "data_type": "INTEGER"},
            {"table_name": "orders", "column_name": "status", "data_type": "STRING"},
            {
                "table_name": "orders",
                "column_name": "created_at",
                "data_type": "TIMESTAMP",
            },
            {"table_name": "products", "column_name": "id", "data_type": "INTEGER"},
            {"table_name": "products", "column_name": "name", "data_type": "STRING"},
            {"table_name": "products", "column_name": "price", "data_type": "FLOAT"},
        ]

    @staticmethod
    def create_llm_responses() -> Dict[str, str]:
        """Create realistic LLM response examples."""
        return {
            "plan": '{"task": "sales_analysis", "tables": ["orders", "products"], "metrics": ["revenue", "count"], "time_range": "last_30_days"}',
            "sql": "SELECT p.name, COUNT(o.order_id) as order_count, SUM(p.price * oi.quantity) as revenue FROM orders o JOIN order_items oi ON o.order_id = oi.order_id JOIN products p ON oi.product_id = p.id WHERE o.status = 'Complete' AND o.created_at >= CURRENT_DATE() - INTERVAL 30 DAY GROUP BY p.id, p.name ORDER BY revenue DESC LIMIT 1000",
            "report": "Sales Analysis Summary:\n\nKey Findings:\n- Total Revenue: $125,450 from 1,247 orders\n- Top Product: 'Premium Widget' with $25,680 revenue\n- Average Order Value: $100.52\n- Order Completion Rate: 94.2%\n\nTrends:\n- 15% increase in sales vs. previous period\n- Electronics category leads with 42% of revenue\n- Weekend sales are 23% higher than weekdays\n\nRecommendations:\n1. Increase inventory for top-performing products\n2. Investigate 5.8% incomplete orders\n3. Expand Electronics category marketing\n\nNext Steps:\n1. Analyze customer segments driving growth\n2. Review supply chain for top products",
        }

    @staticmethod
    def create_test_environment() -> Dict[str, str]:
        """Create complete test environment configuration."""
        return {
            "GOOGLE_API_KEY": "test-google-api-key-12345",
            "BIGQUERY_PROJECT": "test-analytics-project",
            "BIGQUERY_LOCATION": "US",
            "DATASET_ID": "test-project.ecommerce_data",
            "ALLOWED_TABLES": "orders,order_items,products,users,inventory",
            "MAX_BYTES_BILLED": "250000000",
            "MODEL_NAME": "gemini-1.5-pro",
            "AWS_REGION": "us-west-2",
            "BEDROCK_MODEL_ID": "anthropic.claude-v2",
        }
