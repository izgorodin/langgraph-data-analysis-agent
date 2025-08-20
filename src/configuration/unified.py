"""Unified configuration management for LGDA components.

This module provides centralized, type-safe configuration classes for all
LGDA components, eliminating hardcoded values and providing
environment-specific overrides while maintaining backward compatibility.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    """Centralized LLM configuration."""

    # Token configuration - consolidates scattered max_tokens values
    max_tokens_planning: int = Field(default=800, ge=100, le=8000)
    max_tokens_sql_generation: int = Field(default=1200, ge=100, le=8000)
    max_tokens_analysis: int = Field(default=1000, ge=100, le=8000)
    max_tokens_general: int = Field(default=4000, ge=100, le=8000)

    # Temperature settings by context
    temperature_planning: float = Field(default=0.1, ge=0.0, le=2.0)
    temperature_sql_generation: float = Field(default=0.0, ge=0.0, le=2.0)
    temperature_analysis: float = Field(default=0.2, ge=0.0, le=2.0)
    temperature_general: float = Field(default=0.0, ge=0.0, le=2.0)

    # Provider configuration
    primary_provider: str = Field(default="gemini")
    fallback_provider: str = Field(default="bedrock")

    # Request timeout and retry configuration
    request_timeout: int = Field(default=30, ge=5, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay: float = Field(default=1.0, ge=0.1, le=10.0)

    model_config = SettingsConfigDict(
        env_prefix="LGDA_LLM_", case_sensitive=False
    )

    def get_max_tokens_for_context(self, context: str) -> int:
        """Get max tokens for specific LLM context."""
        context_mapping = {
            "planning": self.max_tokens_planning,
            "sql_generation": self.max_tokens_sql_generation,
            "analysis": self.max_tokens_analysis,
            "general": self.max_tokens_general,
        }
        return context_mapping.get(context.lower(), self.max_tokens_general)

    def get_temperature_for_context(self, context: str) -> float:
        """Get temperature for specific LLM context."""
        context_mapping = {
            "planning": self.temperature_planning,
            "sql_generation": self.temperature_sql_generation,
            "analysis": self.temperature_analysis,
            "general": self.temperature_general,
        }
        return context_mapping.get(context.lower(), self.temperature_general)


class BigQueryConfig(BaseSettings):
    """Centralized BigQuery configuration."""

    # Connection settings
    project_id: str = Field(default="")
    location: str = Field(default="US")
    dataset_id: str = Field(default="bigquery-public-data.thelook_ecommerce")
    credentials_path: Optional[str] = Field(default=None)

    # Query execution settings
    max_bytes_billed: int = Field(default=100_000_000, ge=1000)
    query_timeout: int = Field(default=300, ge=30, le=3600)
    job_timeout: int = Field(default=300, ge=30, le=3600)

    # Retry configuration
    max_retries: int = Field(default=5, ge=1, le=20)
    retry_delay: float = Field(default=2.0, ge=0.5, le=10.0)

    # Performance settings
    max_concurrent_queries: int = Field(default=5, ge=1, le=20)
    result_cache_ttl: int = Field(default=1800, ge=60, le=86400)

    model_config = SettingsConfigDict(
        env_prefix="LGDA_BQ_", case_sensitive=False
    )


class SecurityConfig(BaseSettings):
    """Centralized security configuration."""

    # SQL validation settings
    max_sql_length: int = Field(default=10000, ge=100, le=100000)
    allowed_tables: List[str] = Field(
        default_factory=lambda: ["orders", "order_items", "products", "users"]
    )

    # SQL injection prevention patterns
    injection_patterns: List[str] = Field(
        default_factory=lambda: [
            "--",
            "/*",
            "*/",
            ";",
            "DROP",
            "DELETE",
            "TRUNCATE",
            "UPDATE",
        ]
    )

    # Query result limits
    max_result_rows: int = Field(default=10000, ge=100, le=1000000)
    default_query_limit: int = Field(default=1000, ge=10, le=10000)

    # Validation timeouts
    validation_timeout: int = Field(default=5, ge=1, le=30)

    model_config = SettingsConfigDict(
        env_prefix="LGDA_SECURITY_", case_sensitive=False
    )


class PerformanceConfig(BaseSettings):
    """Centralized performance configuration."""

    # Memory management
    max_dataframe_rows: int = Field(default=10000, ge=100, le=1000000)
    max_memory_mb: int = Field(default=512, ge=64, le=4096)

    # Caching settings
    enable_query_cache: bool = Field(default=True)
    cache_ttl: int = Field(default=1800, ge=60, le=86400)
    cache_compression: bool = Field(default=True)

    # Request timeouts
    default_timeout: int = Field(default=30, ge=5, le=600)
    long_running_timeout: int = Field(default=300, ge=30, le=3600)

    model_config = SettingsConfigDict(
        env_prefix="LGDA_PERFORMANCE_", case_sensitive=False
    )


class UnifiedConfig(BaseModel):
    """Unified configuration containing all component configurations."""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    bigquery: BigQueryConfig = Field(default_factory=BigQueryConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)

    # Environment and debug settings
    environment: str = Field(default="development")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # Feature flags
    enable_fallback_llm: bool = Field(default=True)
    enable_cost_tracking: bool = Field(default=True)
    enable_performance_monitoring: bool = Field(default=True)

    class Config:
        """Pydantic configuration."""

        validate_assignment = True
        extra = "forbid"

    @classmethod
    def create_for_environment(cls, environment: str) -> "UnifiedConfig":
        """Create configuration optimized for specific environment."""
        config = cls(environment=environment)

        if environment == "development":
            config.debug = True
            config.log_level = "DEBUG"
            config.security.default_query_limit = 100
            config.performance.max_dataframe_rows = 1000
            config.performance.enable_query_cache = False
            config.llm.request_timeout = 60
            config.bigquery.query_timeout = 60

        elif environment == "production":
            config.debug = False
            config.log_level = "WARNING"
            config.security.default_query_limit = 1000
            config.performance.max_dataframe_rows = 50000
            config.performance.enable_query_cache = True
            config.llm.request_timeout = 30
            config.bigquery.query_timeout = 300

        return config


@lru_cache(maxsize=1)
def get_unified_config() -> UnifiedConfig:
    """Get cached unified configuration instance."""
    return UnifiedConfig()


# Backward compatibility function for existing code
def get_llm_config() -> LLMConfig:
    """Get LLM configuration."""
    return get_unified_config().llm


def get_bigquery_config() -> BigQueryConfig:
    """Get BigQuery configuration."""
    return get_unified_config().bigquery


def get_security_config() -> SecurityConfig:
    """Get Security configuration."""
    return get_unified_config().security


def get_performance_config() -> PerformanceConfig:
    """Get Performance configuration."""
    return get_unified_config().performance
