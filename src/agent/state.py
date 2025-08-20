from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentState(BaseModel):
    question: str
    plan_json: Optional[Dict[str, Any]] = None
    sql: Optional[str] = None
    df_summary: Optional[Dict[str, Any]] = None
    report: Optional[str] = None
    error: Optional[str] = None
    history: List[Dict[str, str]] = Field(default_factory=list)

    # Retry mechanism
    retry_count: int = 0
    max_retries: int = 2
    last_error: Optional[str] = None

    # SQL validation flag
    sql_validated: bool = False
