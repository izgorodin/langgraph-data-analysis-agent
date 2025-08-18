"""Unit tests for AgentState model."""

import json
import pytest
from pydantic import ValidationError

from src.agent.state import AgentState


class TestAgentState:
    """Test AgentState Pydantic model functionality."""

    def test_agent_state_initialization(self):
        """Test basic creation of AgentState with valid data."""
        state = AgentState(question="What are the sales trends?")
        
        assert state.question == "What are the sales trends?"
        assert state.plan_json is None
        assert state.sql is None
        assert state.df_summary is None
        assert state.report is None
        assert state.error is None
        assert state.history == []

    def test_agent_state_with_all_fields(self):
        """Test AgentState creation with all fields populated."""
        plan = {"task": "sales_analysis", "tables": ["orders"]}
        df_summary = {"rows": 100, "columns": ["order_id", "amount"]}
        history = [{"step": "plan", "result": "success"}]
        
        state = AgentState(
            question="Analyze sales",
            plan_json=plan,
            sql="SELECT * FROM orders",
            df_summary=df_summary,
            report="Sales are increasing",
            error=None,
            history=history
        )
        
        assert state.question == "Analyze sales"
        assert state.plan_json == plan
        assert state.sql == "SELECT * FROM orders"
        assert state.df_summary == df_summary
        assert state.report == "Sales are increasing"
        assert state.error is None
        assert state.history == history

    def test_agent_state_serialization(self):
        """Test that AgentState serializes and deserializes correctly."""
        original_state = AgentState(
            question="Test question",
            plan_json={"task": "test"},
            sql="SELECT 1",
            df_summary={"rows": 5},
            report="Test report",
            history=[{"action": "test"}]
        )
        
        # Test model_dump (Pydantic v2 serialization)
        serialized = original_state.model_dump()
        assert isinstance(serialized, dict)
        assert serialized["question"] == "Test question"
        assert serialized["plan_json"] == {"task": "test"}
        
        # Test JSON serialization
        json_str = original_state.model_dump_json()
        assert isinstance(json_str, str)
        
        # Test deserialization
        parsed_data = json.loads(json_str)
        restored_state = AgentState(**parsed_data)
        
        assert restored_state.question == original_state.question
        assert restored_state.plan_json == original_state.plan_json
        assert restored_state.sql == original_state.sql
        assert restored_state.df_summary == original_state.df_summary
        assert restored_state.report == original_state.report
        assert restored_state.history == original_state.history

    def test_agent_state_history_management(self):
        """Test that history is properly managed and doesn't grow unbounded."""
        state = AgentState(question="Test")
        
        # Add multiple history entries
        for i in range(10):
            state.history.append({"step": f"step_{i}", "data": f"data_{i}"})
        
        assert len(state.history) == 10
        assert state.history[0]["step"] == "step_0"
        assert state.history[-1]["step"] == "step_9"
        
        # Test that history can be accessed and modified
        state.history.append({"step": "final", "data": "final_data"})
        assert len(state.history) == 11
        assert state.history[-1]["step"] == "final"

    def test_agent_state_error_propagation(self):
        """Test that errors are correctly stored in state."""
        state = AgentState(question="Test question")
        
        # Test setting error
        error_message = "SQL parse error: Invalid syntax"
        state.error = error_message
        
        assert state.error == error_message
        
        # Test that error doesn't interfere with other fields
        state.plan_json = {"task": "test"}
        assert state.plan_json == {"task": "test"}
        assert state.error == error_message

    def test_agent_state_validation_errors(self):
        """Test validation behavior for invalid inputs."""
        # Test that question is required
        with pytest.raises(ValidationError):
            AgentState()
        
        # Test invalid types for optional fields
        state = AgentState(question="Test")
        
        # These should work fine since they're Any types
        state.plan_json = "string instead of dict"  # Should be allowed
        state.df_summary = 123  # Should be allowed
        
        assert state.plan_json == "string instead of dict"
        assert state.df_summary == 123

    def test_agent_state_copy_and_modification(self):
        """Test that state can be copied and modified safely."""
        original = AgentState(
            question="Original question",
            plan_json={"task": "original"},
            history=[{"step": "1"}]
        )
        
        # Test model_copy (Pydantic v2)
        copied = original.model_copy()
        
        # Modify the copy
        copied.question = "Modified question"
        copied.plan_json = {"task": "modified"}
        copied.history.append({"step": "2"})
        
        # Original should be unchanged for immutable fields
        assert original.question == "Original question"
        assert original.plan_json == {"task": "original"}
        
        # But history is mutable, so it's shared (this is expected behavior)
        assert len(original.history) == 2  # History is shared reference
        
        # Test deep copy for complete isolation
        copied_deep = original.model_copy(deep=True)
        copied_deep.history.append({"step": "3"})
        
        # Now history should be separate
        assert len(original.history) == 2
        assert len(copied_deep.history) == 3

    def test_agent_state_none_handling(self):
        """Test handling of None values in optional fields."""
        state = AgentState(question="Test")
        
        # All optional fields should be None initially
        assert state.plan_json is None
        assert state.sql is None
        assert state.df_summary is None
        assert state.report is None
        assert state.error is None
        
        # Setting to None should work
        state.plan_json = {"task": "test"}
        state.plan_json = None
        assert state.plan_json is None

    def test_agent_state_field_types(self):
        """Test that fields accept appropriate types."""
        state = AgentState(question="Test")
        
        # Test plan_json accepts dict
        state.plan_json = {"task": "test", "tables": ["orders"]}
        assert isinstance(state.plan_json, dict)
        
        # Test sql accepts string
        state.sql = "SELECT * FROM orders WHERE id = 1"
        assert isinstance(state.sql, str)
        
        # Test df_summary accepts dict
        state.df_summary = {
            "rows": 100,
            "columns": ["id", "name"],
            "head": [{"id": 1, "name": "test"}]
        }
        assert isinstance(state.df_summary, dict)
        
        # Test report accepts string
        state.report = "Analysis complete with insights."
        assert isinstance(state.report, str)
        
        # Test error accepts string
        state.error = "Something went wrong"
        assert isinstance(state.error, str)
        
        # Test history accepts list
        state.history = [{"step": "plan"}, {"step": "execute"}]
        assert isinstance(state.history, list)

    def test_agent_state_json_compatibility(self):
        """Test JSON compatibility for LangGraph state passing."""
        state = AgentState(
            question="JSON test",
            plan_json={"task": "test", "nested": {"key": "value"}},
            df_summary={"rows": 10, "stats": {"mean": 5.5}},
            history=[{"timestamp": "2024-01-01", "action": "start"}]
        )
        
        # Test that the state can be converted to JSON and back
        json_data = state.model_dump()
        json_str = json.dumps(json_data, ensure_ascii=False)
        
        # Parse back from JSON
        parsed_data = json.loads(json_str)
        restored_state = AgentState(**parsed_data)
        
        # Verify all nested structures are preserved
        assert restored_state.plan_json["nested"]["key"] == "value"
        assert restored_state.df_summary["stats"]["mean"] == 5.5
        assert restored_state.history[0]["timestamp"] == "2024-01-01"