from __future__ import annotations

import time
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

    # Pipeline timing information for LGDA-018
    pipeline_timing: Dict[str, float] = Field(default_factory=dict)
    pipeline_start_time: Optional[float] = None

    def start_pipeline_timing(self) -> None:
        """Mark the start of pipeline execution for timing."""
        self.pipeline_start_time = time.time()
        self.pipeline_timing.clear()

    def record_node_timing(self, node_name: str, duration: float) -> None:
        """Record timing for a specific pipeline node."""
        self.pipeline_timing[node_name] = duration

    def get_total_pipeline_duration(self) -> Optional[float]:
        """Get total pipeline duration if timing was started."""
        if self.pipeline_start_time is None:
            return None
        return time.time() - self.pipeline_start_time

    def get_timing_summary(self) -> Dict[str, Any]:
        """Generate a comprehensive timing summary."""
        total_duration = self.get_total_pipeline_duration()
        node_total = sum(self.pipeline_timing.values())
        
        summary = {
            "pipeline_timing": self.pipeline_timing.copy(),
            "total_duration": total_duration,
            "node_duration_total": node_total,
            "overhead_duration": total_duration - node_total if total_duration else None,
            "node_count": len(self.pipeline_timing)
        }
        
        # Add percentage breakdown if we have total duration
        if total_duration and total_duration > 0:
            summary["node_percentages"] = {
                node: (duration / total_duration) * 100 
                for node, duration in self.pipeline_timing.items()
            }
            summary["overhead_percentage"] = (
                (summary["overhead_duration"] / total_duration) * 100 
                if summary["overhead_duration"] else 0
            )
        
        return summary
