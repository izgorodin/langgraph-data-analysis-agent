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
