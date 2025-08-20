"""Business metrics tracking for LGDA production observability.

Provides business intelligence metrics including user behavior tracking,
query success analysis, cost efficiency measurement, and product optimization insights.

Can be disabled via LGDA_DISABLE_OBSERVABILITY environment variable.
"""

import os
import time
from typing import Dict, Optional, List, Any
from enum import Enum
from dataclasses import dataclass, field
import logging
import json

logger = logging.getLogger(__name__)


class QueryComplexity(Enum):
    """Query complexity categories for analysis."""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


class InsightQuality(Enum):
    """Insight quality categories."""
    HIGH = "high"
    MEDIUM = "medium" 
    LOW = "low"
    POOR = "poor"


@dataclass
class BusinessMetric:
    """A business metric data point."""
    metric_name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    dimensions: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/analysis."""
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "timestamp": self.timestamp,
            "dimensions": self.dimensions,
            "metadata": self.metadata
        }


class BusinessMetrics:
    """Production-grade business metrics tracking for LGDA.
    
    Tracks user behavior, query patterns, success rates, cost efficiency,
    and provides insights for product optimization.
    """
    
    def __init__(self, enabled: Optional[bool] = None):
        """Initialize business metrics tracking.
        
        Args:
            enabled: Override default enabled state. If None, uses environment.
        """
        if enabled is None:
            # Check for disable flag
            self.enabled = not os.getenv("LGDA_DISABLE_OBSERVABILITY", "false").lower() == "true"
        else:
            self.enabled = enabled
            
        self.metrics_buffer: List[BusinessMetric] = []
        self.session_data: Dict[str, Dict[str, Any]] = {}
        
        if not self.enabled:
            logger.info("LGDA business metrics tracking disabled")
            return
            
        logger.info("LGDA business metrics tracking initialized")
    
    def _record_metric(self, metric_name: str, value: float, 
                      dimensions: Optional[Dict[str, str]] = None,
                      metadata: Optional[Dict[str, Any]] = None):
        """Record a business metric."""
        if not self.enabled:
            return
            
        try:
            metric = BusinessMetric(
                metric_name=metric_name,
                value=value,
                dimensions=dimensions or {},
                metadata=metadata or {}
            )
            self.metrics_buffer.append(metric)
            
            # Log for immediate visibility
            logger.info(f"Business metric: {metric_name}={value}, dimensions={dimensions}")
            
        except Exception as e:
            logger.error(f"Failed to record business metric {metric_name}: {e}")
    
    def track_query_success_rate(self, success: bool, question: str = "", 
                               complexity: Optional[QueryComplexity] = None,
                               execution_time: Optional[float] = None,
                               error_type: Optional[str] = None):
        """Track successful vs failed query executions."""
        self._record_metric(
            "query_success_rate",
            1.0 if success else 0.0,
            dimensions={
                "success": str(success).lower(),
                "complexity": complexity.value if complexity else "unknown",
                "error_type": error_type or "none"
            },
            metadata={
                "question_length": len(question),
                "execution_time": execution_time,
                "question_preview": question[:100] if question else ""
            }
        )
    
    def track_insight_quality(self, feedback_score: float, question: str = "",
                            insight_length: Optional[int] = None,
                            user_rating: Optional[int] = None):
        """Track user satisfaction with generated insights."""
        # Categorize quality
        if feedback_score >= 0.8:
            quality = InsightQuality.HIGH
        elif feedback_score >= 0.6:
            quality = InsightQuality.MEDIUM
        elif feedback_score >= 0.4:
            quality = InsightQuality.LOW
        else:
            quality = InsightQuality.POOR
            
        self._record_metric(
            "insight_quality_score",
            feedback_score,
            dimensions={
                "quality_category": quality.value,
                "user_rating": str(user_rating) if user_rating else "none"
            },
            metadata={
                "question_length": len(question),
                "insight_length": insight_length,
                "question_preview": question[:100] if question else ""
            }
        )
    
    def track_resource_efficiency(self, query_cost: float, insight_value: float,
                                bytes_processed: Optional[int] = None,
                                execution_time: Optional[float] = None):
        """Track cost efficiency of analysis."""
        # Calculate efficiency ratio (value per dollar spent)
        efficiency_ratio = insight_value / max(query_cost, 0.001)  # Avoid division by zero
        
        self._record_metric(
            "resource_efficiency",
            efficiency_ratio,
            dimensions={
                "cost_category": self._categorize_cost(query_cost),
                "value_category": self._categorize_value(insight_value)
            },
            metadata={
                "query_cost": query_cost,
                "insight_value": insight_value,
                "bytes_processed": bytes_processed,
                "execution_time": execution_time
            }
        )
        
        # Also track raw cost and value separately
        self._record_metric("query_cost", query_cost)
        self._record_metric("insight_value", insight_value)
    
    def track_user_patterns(self, question_category: str, complexity: str,
                          user_id: Optional[str] = None,
                          session_id: Optional[str] = None,
                          repeat_question: bool = False):
        """Track usage patterns for product optimization."""
        self._record_metric(
            "user_engagement",
            1.0,
            dimensions={
                "question_category": question_category,
                "complexity": complexity,
                "repeat_question": str(repeat_question).lower(),
                "user_type": "returning" if user_id else "anonymous"
            },
            metadata={
                "user_id": user_id,
                "session_id": session_id
            }
        )
        
        # Track session data
        if session_id:
            if session_id not in self.session_data:
                self.session_data[session_id] = {
                    "start_time": time.time(),
                    "question_count": 0,
                    "categories": set(),
                    "complexity_levels": set()
                }
            
            session = self.session_data[session_id]
            session["question_count"] += 1
            session["categories"].add(question_category)
            session["complexity_levels"].add(complexity)
    
    def track_pipeline_performance(self, stage: str, duration: float,
                                 success: bool, memory_usage: Optional[int] = None):
        """Track pipeline stage performance metrics."""
        self._record_metric(
            "pipeline_performance",
            duration,
            dimensions={
                "stage": stage,
                "success": str(success).lower(),
                "performance_category": self._categorize_performance(duration)
            },
            metadata={
                "memory_usage": memory_usage
            }
        )
    
    def track_error_patterns(self, error_type: str, stage: str,
                           recovery_successful: bool,
                           error_frequency: Optional[int] = None):
        """Track error patterns for system improvement."""
        self._record_metric(
            "error_patterns",
            1.0,
            dimensions={
                "error_type": error_type,
                "stage": stage,
                "recovery_successful": str(recovery_successful).lower()
            },
            metadata={
                "error_frequency": error_frequency
            }
        )
    
    def track_feature_usage(self, feature: str, usage_context: str,
                          success: bool, user_satisfaction: Optional[float] = None):
        """Track feature adoption and satisfaction."""
        self._record_metric(
            "feature_usage",
            1.0,
            dimensions={
                "feature": feature,
                "context": usage_context,
                "success": str(success).lower(),
                "satisfaction_level": self._categorize_satisfaction(user_satisfaction) if user_satisfaction else "unknown"
            },
            metadata={
                "satisfaction_score": user_satisfaction
            }
        )
    
    def track_business_kpi(self, kpi_name: str, value: float,
                         target_value: Optional[float] = None,
                         dimensions: Optional[Dict[str, str]] = None):
        """Track custom business KPIs."""
        metadata = {}
        if target_value is not None:
            metadata["target_value"] = target_value
            metadata["target_achievement"] = value / target_value if target_value > 0 else 0
            
        self._record_metric(
            f"business_kpi_{kpi_name}",
            value,
            dimensions=dimensions,
            metadata=metadata
        )
    
    def get_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get summary of user session metrics."""
        if not self.enabled or session_id not in self.session_data:
            return None
            
        session = self.session_data[session_id]
        current_time = time.time()
        
        return {
            "session_id": session_id,
            "duration_minutes": (current_time - session["start_time"]) / 60,
            "question_count": session["question_count"],
            "unique_categories": len(session["categories"]),
            "complexity_range": list(session["complexity_levels"]),
            "questions_per_minute": session["question_count"] / max((current_time - session["start_time"]) / 60, 0.1)
        }
    
    def get_metrics_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get summary of business metrics for the specified time period."""
        if not self.enabled:
            return {"enabled": False}
            
        cutoff_time = time.time() - (hours * 3600)
        recent_metrics = [m for m in self.metrics_buffer if m.timestamp >= cutoff_time]
        
        if not recent_metrics:
            return {"enabled": True, "metrics_count": 0, "hours": hours}
        
        # Calculate summary statistics
        summary = {
            "enabled": True,
            "hours": hours,
            "metrics_count": len(recent_metrics),
            "metrics_by_type": {},
            "success_rates": {},
            "performance_summary": {}
        }
        
        # Group metrics by type
        by_type = {}
        for metric in recent_metrics:
            metric_type = metric.metric_name
            if metric_type not in by_type:
                by_type[metric_type] = []
            by_type[metric_type].append(metric)
        
        # Calculate statistics for each metric type
        for metric_type, metrics in by_type.items():
            values = [m.value for m in metrics]
            summary["metrics_by_type"][metric_type] = {
                "count": len(values),
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values)
            }
        
        return summary
    
    def _categorize_cost(self, cost: float) -> str:
        """Categorize query cost."""
        if cost < 0.01:
            return "low"
        elif cost < 0.10:
            return "medium"
        elif cost < 1.00:
            return "high"
        else:
            return "very_high"
    
    def _categorize_value(self, value: float) -> str:
        """Categorize insight value."""
        if value < 0.3:
            return "low"
        elif value < 0.6:
            return "medium"
        elif value < 0.8:
            return "high"
        else:
            return "very_high"
    
    def _categorize_performance(self, duration: float) -> str:
        """Categorize performance based on duration."""
        if duration < 5:
            return "fast"
        elif duration < 15:
            return "medium"
        elif duration < 60:
            return "slow"
        else:
            return "very_slow"
    
    def _categorize_satisfaction(self, satisfaction: float) -> str:
        """Categorize user satisfaction."""
        if satisfaction >= 0.8:
            return "high"
        elif satisfaction >= 0.6:
            return "medium"
        elif satisfaction >= 0.4:
            return "low"
        else:
            return "very_low"
    
    def export_metrics(self, format: str = "json") -> str:
        """Export metrics for external analysis."""
        if not self.enabled:
            return "{}"
            
        if format == "json":
            return json.dumps([m.to_dict() for m in self.metrics_buffer], indent=2)
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def clear_metrics_buffer(self, older_than_hours: int = 24):
        """Clear old metrics from buffer to manage memory."""
        if not self.enabled:
            return
            
        cutoff_time = time.time() - (older_than_hours * 3600)
        self.metrics_buffer = [m for m in self.metrics_buffer if m.timestamp >= cutoff_time]
        
        # Also clean up old session data
        self.session_data = {
            sid: sdata for sid, sdata in self.session_data.items()
            if sdata["start_time"] >= cutoff_time
        }


# Global business metrics instance for convenience
_global_business_metrics: Optional[BusinessMetrics] = None


def get_business_metrics() -> BusinessMetrics:
    """Get the global business metrics instance, initializing if needed."""
    global _global_business_metrics
    if _global_business_metrics is None:
        _global_business_metrics = BusinessMetrics()
    return _global_business_metrics


def disable_business_metrics():
    """Disable business metrics tracking globally."""
    global _global_business_metrics
    _global_business_metrics = BusinessMetrics(enabled=False)