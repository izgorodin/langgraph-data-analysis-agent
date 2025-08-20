# LGDA-008: Configuration Management Consolidation

**Priority**: HIGH | **Type**: Infrastructure | **Parallel**: Can run with LGDA-007, LGDA-009

## Architectural Context
Based on **ADR-002** (Configuration Management), we need to eliminate hardcoded values scattered across multiple files and create a centralized, type-safe configuration system.

## Objective
Consolidate configuration management to eliminate hardcoded values, provide environment-specific overrides, and ensure type safety across the application.

## Detailed Analysis

### Current Problems
- **Scattered hardcoded values**: `max_tokens` in 3 different files (2000, 4000, 1000)
- **Inconsistent configuration**: Some use env vars, some hardcoded, some in settings
- **Type safety issues**: String/int confusion, missing validation
- **Test configuration**: Different paths for test vs production config

### Solution Architecture
```python
# src/config/unified.py
from pydantic_settings import BaseSettings
from typing import Dict, Any

class LLMConfig(BaseSettings):
    max_tokens: int = 4000
    temperature: float = 0.0
    timeout_seconds: int = 60
    retry_attempts: int = 3

    model_config = SettingsConfigDict(
        env_prefix="LGDA_LLM_",
        case_sensitive=False
    )

class BigQueryConfig(BaseSettings):
    project_id: str
    location: str = "US"
    max_bytes_billed: int = 100_000_000
    query_timeout: int = 300
    retry_attempts: int = 5

    model_config = SettingsConfigDict(
        env_prefix="LGDA_BQ_",
        case_sensitive=False
    )

class SecurityConfig(BaseSettings):
    max_sql_length: int = 10000
    allowed_tables: List[str] = ["orders", "order_items", "products", "users"]
    injection_patterns: List[str] = field(default_factory=lambda: ["--", "/*", "*/", ";"])

    model_config = SettingsConfigDict(
        env_prefix="LGDA_SECURITY_",
        case_sensitive=False
    )

@lru_cache()
def get_config() -> UnifiedConfig:
    """Cached configuration singleton"""
    return UnifiedConfig()
```

### Migration Strategy

1. **Phase 1: Core Configuration** (Day 1)
   - Create unified config classes
   - Migrate LLM token configurations
   - Preserve backward compatibility

2. **Phase 2: Component Integration** (Day 2)
   - Update `llm/compat.py` to use unified config
   - Update `bq.py` configuration
   - Update security validation settings

3. **Phase 3: Environment Support** (Day 3)
   - Environment-specific config files
   - Docker/k8s configuration support
   - Configuration validation and defaults

### Implementation Components

1. **Unified Configuration** (`src/config/unified.py`)
   - Type-safe Pydantic models
   - Environment variable support
   - Validation and defaults
   - Caching and performance

2. **Configuration Factory** (`src/config/factory.py`)
   - Environment detection
   - Profile-based configuration
   - Override mechanisms
   - Configuration testing utilities

3. **Migration Layer** (`src/config/compat.py`)
   - Backward compatibility
   - Gradual migration support
   - Deprecation warnings
   - Legacy configuration mapping

4. **Validation** (`src/config/validation.py`)
   - Configuration consistency checks
   - Environment-specific validation
   - Security constraint validation
   - Performance impact validation

### Dependencies
- **Independent**: Can run fully parallel with LGDA-007
- **Coordinates with**: LGDA-009 on error configuration
- **Enables**: LGDA-010 (test configuration), LGDA-011 (monitoring config)

## Acceptance Criteria

### Functional Requirements
- ✅ Single source of truth for all configuration
- ✅ Environment variable override support
- ✅ Type-safe configuration with validation
- ✅ Zero hardcoded values in business logic
- ✅ Test/dev/prod configuration profiles

### Performance Requirements
- ✅ Configuration loading < 10ms
- ✅ Memory overhead < 1MB
- ✅ No configuration drift during runtime
- ✅ Hot reload support for development

### Migration Requirements
- ✅ Zero breaking changes during migration
- ✅ Backward compatibility maintained
- ✅ Gradual rollout with feature flags
- ✅ All existing tests pass unchanged

### Integration Tests
```python
def test_llm_config_environment_override():
    """Environment variables properly override defaults"""

def test_bigquery_config_validation():
    """Invalid BigQuery config raises validation errors"""

def test_configuration_consistency_across_environments():
    """Dev/test/prod configs are consistent and valid"""

def test_backward_compatibility_legacy_config():
    """Legacy configuration paths continue to work"""
```

## Configuration Elimination Targets

### High Priority (Hardcoded Values)
- `max_tokens`: 2000/4000/1000 → unified LLM config
- `retry_attempts`: scattered values → unified retry config
- `timeout_seconds`: various timeouts → component-specific config
- `allowed_tables`: hardcoded list → security config

### Medium Priority (Environment Variables)
- API keys and credentials → secure credential management
- Database connection strings → environment profiles
- Feature flags → centralized feature flag system

### Low Priority (Magic Numbers)
- Buffer sizes, cache limits → performance config
- Validation thresholds → validation config
- UI timeouts and delays → UX config

## Rollback Plan
1. **Feature flag**: `LGDA_USE_UNIFIED_CONFIG=false`
2. **Phased rollback**: Component by component
3. **Monitoring**: Track configuration errors and performance
4. **Automatic detection**: Config validation failures trigger rollback

## Estimated Effort
**2-3 days** | **Files**: ~6 | **Tests**: ~12 new

## Parallel Execution Notes
- **Independent from LGDA-007**: Different files and concerns
- **Coordinates with LGDA-009**: Share error configuration interfaces
- **Enables LGDA-010**: Provides test configuration infrastructure
- **Can start immediately**: No blocking dependencies
