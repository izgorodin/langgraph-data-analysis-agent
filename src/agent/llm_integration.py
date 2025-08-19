"""Enhanced LLM integration for LangGraph nodes.

This module provides improved LLM integration that leverages the new
provider infrastructure with context awareness, fallback, and validation.
"""

from __future__ import annotations

import asyncio
import json
from typing import Dict, List

from ..llm import LLMProviderManager
from ..llm.manager import get_default_manager
from ..llm.models import LLMContext, LLMRequest
from .prompts import PLAN_SYSTEM, REPORT_SYSTEM, SQL_SYSTEM
from .state import AgentState


class LLMNodeIntegration:
    """Enhanced LLM integration for agent nodes."""

    def __init__(self, manager: LLMProviderManager = None):
        self.manager = manager or get_default_manager()

    async def generate_plan(self, question: str, schema: Dict[str, List[str]]) -> Dict:
        """Generate analysis plan using LLM with proper context."""
        # Create context-aware prompt
        schema_text = "\n".join(
            [f"- {table}: {', '.join(cols)}" for table, cols in schema.items()]
        )

        prompt = f"""
        Return a JSON object for this analysis request.
        Question: {question}
        Tables & Columns
        {schema_text}
        JSON keys: task, tables, time_range, dimensions, metrics, filters, grain.
        """

        request = LLMRequest(
            prompt=prompt,
            context=LLMContext.PLANNING,
            system_prompt=PLAN_SYSTEM,
            temperature=0.1,
            max_tokens=800,
        )

        response = await self.manager.generate_with_fallback(request)

        # Parse JSON with error handling
        try:
            plan = json.loads(response.text.strip().strip("`"))
            return plan
        except Exception:
            # Attempt to extract JSON
            start = response.text.find("{")
            end = response.text.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(response.text[start : end + 1])
                except Exception:
                    pass

            # Fallback plan
            return {
                "task": "ad-hoc analysis",
                "tables": ["orders", "order_items", "products", "users"],
            }

    async def generate_sql(self, plan_json: Dict, allowed_tables: List[str]) -> str:
        """Generate SQL using LLM with proper context."""
        prompt = f"""
        Write a BigQuery Standard SQL SELECT for this PLAN:
        PLAN: {json.dumps(plan_json)}
        Only use these tables: {', '.join(allowed_tables)}
        Prefer safe, explicit JOINs; qualify columns with table aliases; include WHERE for time_range if present.
        Limit to 1000 rows unless aggregation is performed.
        """

        request = LLMRequest(
            prompt=prompt,
            context=LLMContext.SQL_GENERATION,
            system_prompt=SQL_SYSTEM,
            temperature=0.0,  # Deterministic for SQL
            max_tokens=1200,
        )

        response = await self.manager.generate_with_fallback(request)

        # Clean up SQL response
        sql = response.text.strip().strip("`")

        # Remove any markdown SQL blocks
        if sql.startswith("sql\n"):
            sql = sql[4:]
        elif sql.startswith("```sql"):
            sql = sql[6:]
            if sql.endswith("```"):
                sql = sql[:-3]

        return sql.strip()

    async def generate_report(
        self, question: str, plan_json: Dict, df_summary: Dict
    ) -> str:
        """Generate analysis report using LLM with proper context."""
        plan_text = json.dumps(plan_json, ensure_ascii=False)
        summary_text = json.dumps(df_summary, ensure_ascii=False)[
            :20000
        ]  # Truncate for token limits

        prompt = f"""
        Question: {question}
        PLAN: {plan_text}
        DF SUMMARY: {summary_text}

        Write a concise executive insight with numeric evidence and 1–2 next questions.
        Focus on key findings, trends, and actionable business insights.
        """

        request = LLMRequest(
            prompt=prompt,
            context=LLMContext.ANALYSIS,
            system_prompt=REPORT_SYSTEM,
            temperature=0.2,  # Slightly creative for insights
            max_tokens=1000,
        )

        response = await self.manager.generate_with_fallback(request)
        return response.text.strip()

    def generate_plan_sync(self, question: str, schema: Dict[str, List[str]]) -> Dict:
        """Synchronous wrapper for plan generation."""
        return asyncio.run(self.generate_plan(question, schema))

    def generate_sql_sync(self, plan_json: Dict, allowed_tables: List[str]) -> str:
        """Synchronous wrapper for SQL generation."""
        return asyncio.run(self.generate_sql(plan_json, allowed_tables))

    def generate_report_sync(
        self, question: str, plan_json: Dict, df_summary: Dict
    ) -> str:
        """Synchronous wrapper for report generation."""
        return asyncio.run(self.generate_report(question, plan_json, df_summary))


# Global instance for use in nodes
_llm_integration = LLMNodeIntegration()


def get_llm_integration() -> LLMNodeIntegration:
    """Get the global LLM integration instance."""
    return _llm_integration


def set_llm_integration(integration: LLMNodeIntegration) -> None:
    """Set the global LLM integration instance (for testing)."""
    global _llm_integration
    _llm_integration = integration
