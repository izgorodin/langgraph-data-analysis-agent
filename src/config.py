import base64
import json
import os
import warnings
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    # Auto-load .env early (dev convenience). Safe if not present.
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except ImportError:
    pass


# Legacy Settings class for backward compatibility
@dataclass
class Settings:

    google_api_key: str = field(default="")
    bq_project: str = field(default="")
    bq_location: str = field(default="US")
    dataset_id: str = field(default="bigquery-public-data.thelook_ecommerce")
    allowed_tables: tuple[str, ...] = field(
        default_factory=lambda: ("orders", "order_items", "products", "users")
    )
    max_bytes_billed: int = field(default=100000000)
    model_name: str = field(default="gemini-1.5-pro")
    aws_region: str = field(default="eu-west-1")
    bedrock_model_id: str = field(default="")

    def __post_init__(self) -> None:
        # Read dynamically from environment (supports tests using patch.dict)
        self.google_api_key = os.getenv("GOOGLE_API_KEY", "")
        self.bq_project = os.getenv("BIGQUERY_PROJECT", "")
        self.bq_location = os.getenv("BIGQUERY_LOCATION", "US")
        self.dataset_id = os.getenv(
            "DATASET_ID", "bigquery-public-data.thelook_ecommerce"
        )

        if "ALLOWED_TABLES" in os.environ:
            raw = os.getenv("ALLOWED_TABLES", "")
            self.allowed_tables = tuple(t.strip() for t in raw.split(","))
        else:
            self.allowed_tables = ("orders", "order_items", "products", "users")

        max_bytes_str = os.getenv("MAX_BYTES_BILLED", "100000000")
        try:
            self.max_bytes_billed = int(max_bytes_str)
        except ValueError as e:
            # Surface invalid configuration as ValueError (tests expect this)
            raise ValueError("MAX_BYTES_BILLED must be an integer") from e

        self.model_name = os.getenv("MODEL_NAME", "gemini-1.5-pro")
        self.aws_region = os.getenv("AWS_REGION", "eu-west-1")
        self.bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", "")


# New LGDA Configuration using Pydantic BaseSettings
class LGDAConfig(BaseSettings):
    """
    Main LGDA configuration using Pydantic BaseSettings.
    Supports both legacy and LGDA_* prefixed environment variables.
    """

    # Environment identification
    environment: str = Field(default="development", validation_alias="LGDA_ENVIRONMENT")
    debug: bool = Field(default=False, validation_alias="LGDA_DEBUG")
    log_level: str = Field(default="INFO", validation_alias="LGDA_LOG_LEVEL")

    # BigQuery configuration
    bigquery_project_id: str = Field(
        default="", validation_alias="LGDA_BIGQUERY_PROJECT_ID"
    )
    bigquery_dataset: str = Field(
        default="bigquery-public-data.thelook_ecommerce",
        validation_alias="LGDA_BIGQUERY_DATASET",
    )
    bigquery_location: str = Field(
        default="US", validation_alias="LGDA_BIGQUERY_LOCATION"
    )
    bigquery_credentials_path: Optional[str] = Field(
        default=None, validation_alias="LGDA_BIGQUERY_CREDENTIALS"
    )

    # LLM configuration
    llm_primary_provider: str = Field(
        default="gemini", validation_alias="LGDA_LLM_PRIMARY"
    )
    llm_fallback_provider: str = Field(
        default="bedrock", validation_alias="LGDA_LLM_FALLBACK"
    )
    gemini_api_key: Optional[str] = Field(
        default=None, validation_alias="LGDA_GEMINI_API_KEY"
    )
    gemini_project_id: Optional[str] = Field(
        default=None, validation_alias="LGDA_GEMINI_PROJECT_ID"
    )
    bedrock_region: str = Field(
        default="us-east-1", validation_alias="LGDA_BEDROCK_REGION"
    )

    # Security policies
    sql_max_limit: int = Field(default=1000, validation_alias="LGDA_SQL_MAX_LIMIT")
    allowed_tables: List[str] = Field(
        default_factory=lambda: ["orders", "order_items", "products", "users"],
        validation_alias=AliasChoices("LGDA_ALLOWED_TABLES", "ALLOWED_TABLES"),
    )

    def __init__(self, **kwargs):
        # Handle legacy environment variable mapping with warnings FIRST
        self._handle_legacy_env_vars()

        super().__init__(**kwargs)

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        allowed = ["development", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v

    @field_validator("allowed_tables", mode="before")
    @classmethod
    def parse_allowed_tables(cls, v):
        """Allow comma-separated string or JSON array for allowed_tables."""
        if v is None or v == "":
            return ["orders", "order_items", "products", "users"]
        if isinstance(v, list):
            return v
        if isinstance(v, tuple):
            return list(v)
        if isinstance(v, str):
            # Try JSON first
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except Exception:
                # Fallback to comma-separated parsing
                return [t.strip() for t in v.split(",") if t.strip()]
        raise ValueError("allowed_tables must be a list or comma-separated string")

    # (second __init__ removed; logic consolidated above)

    def _handle_legacy_env_vars(self):
        """Handle legacy environment variables with soft warnings."""
        legacy_mappings = {
            "GOOGLE_API_KEY": "LGDA_GEMINI_API_KEY",
            "BIGQUERY_PROJECT": "LGDA_BIGQUERY_PROJECT_ID",
            "BIGQUERY_LOCATION": "LGDA_BIGQUERY_LOCATION",
            "DATASET_ID": "LGDA_BIGQUERY_DATASET",
            "MAX_BYTES_BILLED": "LGDA_SQL_MAX_LIMIT",
            "AWS_REGION": "LGDA_BEDROCK_REGION",
            "ALLOWED_TABLES": "LGDA_ALLOWED_TABLES",
        }

        for legacy_var, new_var in legacy_mappings.items():
            if legacy_var in os.environ and new_var not in os.environ:
                # Set the new variable from legacy and warn
                if legacy_var == "ALLOWED_TABLES":
                    # Convert CSV to JSON list to satisfy pydantic-settings complex decoding
                    raw = os.environ[legacy_var]
                    if raw and not raw.strip().startswith("["):
                        tables = [t.strip() for t in raw.split(",") if t.strip()]
                        os.environ[new_var] = json.dumps(tables)
                    else:
                        os.environ[new_var] = raw
                else:
                    os.environ[new_var] = os.environ[legacy_var]
                warnings.warn(
                    f"Using legacy environment variable {legacy_var}. "
                    f"Please migrate to {new_var} for future compatibility.",
                    DeprecationWarning,
                    stacklevel=3,
                )

        # If new-style LGDA_ALLOWED_TABLES is present but CSV, normalize to JSON too
        if (
            val := os.environ.get("LGDA_ALLOWED_TABLES")
        ) and not val.strip().startswith("["):
            tables = [t.strip() for t in val.split(",") if t.strip()]
            os.environ["LGDA_ALLOWED_TABLES"] = json.dumps(tables)

    # Pydantic v2 config
    model_config = SettingsConfigDict(
        # Do not read .env directly here; tests patch env and expect isolation.
        env_file=None,
        case_sensitive=False,
        env_ignore_empty=True,
    )


# Preserve original class identity across reloads for test stability
if "LGDAConfig_ORIGINAL" not in globals():
    LGDAConfig_ORIGINAL = LGDAConfig


# Credential Manager for secure credential handling
class CredentialManager:
    """Secure credential management with multiple sources and masking."""

    def __init__(self, config: LGDAConfig):
        self.config = config
        self.secrets_cache = {}

    def get_bigquery_credentials(self) -> Union[str, dict, None]:
        """
        BigQuery credential resolution:
        1. Service account JSON from env var (base64 encoded)
        2. Service account file path
        3. Application Default Credentials
        """
        if creds_json := os.getenv("LGDA_BIGQUERY_CREDENTIALS_JSON"):
            try:
                return json.loads(base64.b64decode(creds_json))
            except (json.JSONDecodeError, ValueError) as e:
                warnings.warn(
                    f"Invalid base64 JSON in LGDA_BIGQUERY_CREDENTIALS_JSON: {e}"
                )
                return None

        if self.config.bigquery_credentials_path:
            return str(Path(self.config.bigquery_credentials_path).resolve())

        return None  # Use Application Default Credentials

    def get_gemini_credentials(self) -> dict:
        """Gemini API credentials."""
        creds = {}
        if self.config.gemini_api_key:
            creds["api_key"] = self.config.gemini_api_key
        if self.config.gemini_project_id:
            creds["project_id"] = self.config.gemini_project_id
        return creds

    def get_bedrock_credentials(self) -> dict:
        """AWS Bedrock credentials."""
        return {
            "region": self.config.bedrock_region,
            # AWS credentials typically come from environment or IAM roles
            "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
            "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "aws_session_token": os.getenv("AWS_SESSION_TOKEN"),
        }

    def mask_sensitive_data(self, data: dict) -> dict:
        """Masks sensitive data for logging."""
        sensitive_keys = ["api_key", "secret", "password", "token", "credentials"]
        masked = data.copy()
        for key in masked:
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                masked[key] = "***MASKED***"
        return masked


# Feature Flags
class FeatureFlag(Enum):
    """Available feature flags."""

    ENABLE_QUERY_CACHE = "enable_query_cache"
    ENABLE_COST_TRACKING = "enable_cost_tracking"
    ENABLE_ADVANCED_ANALYTICS = "enable_advanced_analytics"
    ENABLE_FALLBACK_LLM = "enable_fallback_llm"
    ENABLE_SQL_OPTIMIZATION = "enable_sql_optimization"
    ENABLE_PERFORMANCE_MONITORING = "enable_performance_monitoring"


# Environment Profiles
@dataclass
class EnvironmentProfile:
    """Environment-specific configuration overrides."""

    name: str
    config_overrides: Dict[str, Any]
    feature_flags: Dict[str, bool]
    performance_settings: Dict[str, Any]


# Environment profile definitions
ENVIRONMENT_PROFILES = {
    "development": EnvironmentProfile(
        name="development",
        config_overrides={
            "debug": True,
            "log_level": "DEBUG",
            "sql_max_limit": 100,  # Smaller limits for dev
        },
        feature_flags={
            "enable_query_cache": False,
            "enable_cost_tracking": False,
            "enable_performance_monitoring": False,
        },
        performance_settings={
            "query_timeout": 60,  # 1 minute for dev
            "retry_count": 1,
            "cache_ttl": 300,
        },
    ),
    "staging": EnvironmentProfile(
        name="staging",
        config_overrides={
            "debug": False,
            "log_level": "INFO",
            "sql_max_limit": 500,
        },
        feature_flags={
            "enable_query_cache": True,
            "enable_cost_tracking": True,
            "enable_performance_monitoring": True,
        },
        performance_settings={
            "query_timeout": 180,  # 3 minutes
            "retry_count": 2,
            "cache_ttl": 600,
        },
    ),
    "production": EnvironmentProfile(
        name="production",
        config_overrides={
            "debug": False,
            "log_level": "WARNING",
            "sql_max_limit": 1000,
        },
        feature_flags={
            "enable_query_cache": True,
            "enable_cost_tracking": True,
            "enable_performance_monitoring": True,
            "enable_fallback_llm": True,
        },
        performance_settings={
            "query_timeout": 300,  # 5 minutes
            "retry_count": 3,
            "cache_ttl": 1800,
        },
    ),
}


# Feature Flag Manager
class FeatureFlagManager:
    """Runtime feature flag evaluation."""

    def __init__(self, config: LGDAConfig, profile: EnvironmentProfile):
        self.config = config
        self.profile = profile
        self.custom_rules = {}

    def is_enabled(self, flag: FeatureFlag, context: dict = None) -> bool:
        """
        Feature flag evaluation with context:
        1. Check custom rules (A/B testing, user segments)
        2. Check environment profile
        3. Check global config
        4. Default to False
        """
        if custom_rule := self.custom_rules.get(flag):
            return custom_rule(context or {})

        return self.profile.feature_flags.get(flag.value, False)

    def add_custom_rule(self, flag: FeatureFlag, rule: Callable[[dict], bool]):
        """Add custom evaluation rule."""
        self.custom_rules[flag] = rule


# Performance Configuration
@dataclass
class PerformanceConfig:
    """Performance tuning parameters."""

    # BigQuery settings
    query_timeout: int = 300
    max_concurrent_queries: int = 5
    result_cache_ttl: int = 1800

    # LLM settings
    llm_timeout: int = 30
    llm_retry_count: int = 3
    llm_max_tokens: int = 2000

    # Memory management
    max_dataframe_rows: int = 10000
    max_memory_mb: int = 512

    # Caching
    enable_query_cache: bool = True
    cache_compression: bool = True

    @classmethod
    def for_environment(cls, environment: str) -> "PerformanceConfig":
        """Factory method for environment-specific performance config."""
        if environment == "development":
            return cls(
                query_timeout=60,
                max_concurrent_queries=2,
                max_dataframe_rows=1000,
                max_memory_mb=256,
            )
        elif environment == "production":
            return cls(
                query_timeout=300,
                max_concurrent_queries=10,
                max_dataframe_rows=50000,
                max_memory_mb=1024,
            )
        else:  # staging
            return cls()


# Configuration Factory
class ConfigFactory:
    """Central configuration factory."""

    @staticmethod
    def create_config() -> LGDAConfig:
        """Creates fully configured LGDA config."""
        # Use stable class alias to avoid isinstance mismatches after import reloads in tests
        ConfigCls = globals().get("LGDAConfig_ORIGINAL", LGDAConfig)
        base_config = ConfigCls()
        profile = ENVIRONMENT_PROFILES[base_config.environment]

        # Apply environment overrides
        for key, value in profile.config_overrides.items():
            setattr(base_config, key, value)

        return base_config

    @staticmethod
    def create_managers(config: LGDAConfig) -> tuple:
        """Creates all configuration managers."""
        profile = ENVIRONMENT_PROFILES[config.environment]

        credential_manager = CredentialManager(config)
        feature_manager = FeatureFlagManager(config, profile)
        performance_config = PerformanceConfig.for_environment(config.environment)

        return credential_manager, feature_manager, performance_config


# Maintain backward compatibility
settings = Settings()
