# ADR-002: Configuration Management Patterns

**Status**: Proposed
**Date**: 2025-01-20
**Context**: Technical debt resolution - eliminate scattered hardcoded values

## Context and Problem Statement

Configuration values are scattered across multiple files, creating maintenance overhead and configuration drift:

**Current Scattered Configuration**:
```python
# Token limits in 3 different files
src/config.py:       llm_max_tokens: int = 4000
src/llm/compat.py:   max_tokens=4000
src/llm/models.py:   max_tokens: int = 4000

# Model names in multiple locations
cli.py:              default_model = "meta/llama-3.1-405b-instruct"
src/config.py:       model_name: str = "gemini-1.5-pro"
src/llm/compat.py:   model parameter override logic

# SQL templates hardcoded in business logic
src/agent/nodes.py:  cleaned = f"SELECT * FROM {first_table} LIMIT 10"
src/agent/prompts.py: EXACT SCHEMA REFERENCE hardcoded
```

**Problems**:
- Configuration drift when updating values
- Inconsistent defaults across components
- Difficult to manage environment-specific settings
- Testing complexity with multiple config sources

## Decision Drivers

- **Single Source of Truth**: All configuration in one place
- **Environment Flexibility**: Easy dev/staging/prod differences
- **Type Safety**: Validation and error detection
- **Maintainability**: Simple to update and test

## Considered Options

### Option 1: Environment Variables Only
**Pros**: Simple, 12-factor app compliant
**Cons**: No validation, type safety, or defaults

### Option 2: Config Files with Environment Overrides
**Pros**: Good defaults, environment flexibility
**Cons**: Complex precedence rules

### Option 3: Pydantic Settings with Smart Defaults (CHOSEN)
**Pros**: Type safety, validation, clear precedence
**Cons**: Learning curve for Pydantic patterns

## Decision

**Implement centralized Pydantic-based configuration with environment precedence**:

1. **Single Configuration Source**: All values in `src/config.py`
2. **Type Validation**: Pydantic models with proper types
3. **Environment Precedence**: ENV vars override defaults
4. **Component Access**: Dependency injection pattern

## Implementation Plan

### Step 1: Unified Configuration Schema
```python
# src/config.py - Enhanced with all configuration
class LLMConfig(BaseModel):
    """Centralized LLM configuration"""
    # Token configuration
    max_tokens: int = Field(default=4000, ge=100, le=32000)
    default_model: str = Field(default="meta/llama-3.1-405b-instruct")

    # Provider-specific settings
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1")
    gemini_model_name: str = Field(default="gemini-1.5-pro")

    # Retry configuration (from ADR-001)
    max_workflow_retries: int = Field(default=3, ge=0, le=10)
    max_infrastructure_retries: int = Field(default=5, ge=1, le=20)

class BigQueryConfig(BaseModel):
    """Centralized BigQuery configuration"""
    project_id: str = Field(default="")
    dataset_id: str = Field(default="bigquery-public-data.thelook_ecommerce")
    location: str = Field(default="US")
    max_bytes_billed: int = Field(default=100_000_000, ge=1000)

    # SQL generation templates
    fallback_query_template: str = Field(default="SELECT * FROM {table} LIMIT 10")
    schema_query_timeout: int = Field(default=30, ge=5, le=300)

class CLIConfig(BaseModel):
    """CLI-specific configuration"""
    progress_indicators: bool = Field(default=True)
    verbose_errors: bool = Field(default=False)
    output_format: str = Field(default="rich", regex="^(rich|json|plain)$")
```

### Step 2: Dependency Injection Pattern
```python
# src/config.py - Centralized access
@dataclass
class ConfigManager:
    """Centralized configuration management"""
    llm: LLMConfig
    bigquery: BigQueryConfig
    cli: CLIConfig

    @classmethod
    def from_environment(cls) -> "ConfigManager":
        """Load configuration with environment precedence"""
        return cls(
            llm=LLMConfig(),
            bigquery=BigQueryConfig(),
            cli=CLIConfig()
        )

    def get_llm_max_tokens(self) -> int:
        """Single source for token limits"""
        return self.llm.max_tokens

# Global configuration instance
config = ConfigManager.from_environment()
```

### Step 3: Remove Hardcoded Values
```python
# src/llm/compat.py - Use centralized config
from src.config import config

def llm_completion(prompt: str, **kwargs) -> str:
    # Remove hardcoded max_tokens=4000
    max_tokens = kwargs.get("max_tokens", config.get_llm_max_tokens())
    # ... rest of implementation

# src/llm/models.py - Use centralized config
class LLMRequest(BaseModel):
    max_tokens: int = Field(default_factory=lambda: config.get_llm_max_tokens())

# src/agent/nodes.py - Use template from config
def synthesize_sql_node(state: AgentState) -> AgentState:
    if not state.sql.strip():
        # Remove hardcoded fallback
        template = config.bigquery.fallback_query_template
        first_table = next(iter(ALLOWED)) if ALLOWED else "orders"
        state.sql = template.format(table=first_table)
```

### Step 4: Environment Variable Mapping
```python
# .env.example - Clear environment precedence
# LLM Configuration
LGDA_LLM_MAX_TOKENS=4000
LGDA_LLM_DEFAULT_MODEL=meta/llama-3.1-405b-instruct
LGDA_LLM_MAX_WORKFLOW_RETRIES=3

# BigQuery Configuration
LGDA_BIGQUERY_PROJECT_ID=gen-lang-client-0996219185
LGDA_BIGQUERY_DATASET_ID=bigquery-public-data.thelook_ecommerce
LGDA_BIGQUERY_MAX_BYTES_BILLED=100000000

# CLI Configuration
LGDA_CLI_PROGRESS_INDICATORS=true
LGDA_CLI_VERBOSE_ERRORS=false
```

### Step 5: Configuration Testing
```python
# tests/unit/test_configuration.py
def test_default_configuration():
    """Test that default configuration is valid"""
    config = ConfigManager.from_environment()
    assert config.llm.max_tokens >= 100
    assert config.bigquery.max_bytes_billed > 0

def test_environment_override():
    """Test environment variable precedence"""
    with patch.dict(os.environ, {"LGDA_LLM_MAX_TOKENS": "8000"}):
        config = ConfigManager.from_environment()
        assert config.llm.max_tokens == 8000

def test_configuration_validation():
    """Test invalid configuration is rejected"""
    with pytest.raises(ValidationError):
        LLMConfig(max_tokens=-100)  # Should fail validation
```

## Expected Benefits

### Maintainability
- Single location for all configuration changes
- Type safety prevents configuration errors
- Clear environment variable precedence

### Testing
- Easy to override configuration in tests
- Validation ensures configuration correctness
- No more hardcoded values in business logic

### Deployment
- Environment-specific configuration without code changes
- Clear documentation of all configurable values
- Validation prevents deployment with invalid config

## Consequences

### Positive
- Elimination of configuration drift
- Type safety and validation
- Easier environment management
- Clear configuration documentation

### Negative
- Migration effort to update all hardcoded references
- Need to understand Pydantic patterns
- Slightly more complex configuration loading

### Migration Strategy
1. **Phase 1**: Create unified configuration schema
2. **Phase 2**: Update one component at a time (LLM → BigQuery → CLI)
3. **Phase 3**: Remove old hardcoded values
4. **Phase 4**: Add configuration validation tests

## Validation Plan

### Configuration Tests
- [ ] All default values are valid
- [ ] Environment variable precedence works correctly
- [ ] Invalid configuration is properly rejected
- [ ] All components use centralized configuration

### Integration Tests
- [ ] Token limits correctly applied across all LLM calls
- [ ] BigQuery settings properly configured
- [ ] CLI configuration affects behavior as expected

### Migration Validation
- [ ] No hardcoded values remain in business logic
- [ ] All configuration sources point to single location
- [ ] Environment-specific configuration works correctly

## Related ADRs
- ADR-001: Unified Retry Architecture (retry configuration)
- ADR-004: CLI Error Handling (CLI configuration)
- ADR-005: Provider Interface Standardization (provider configuration)

---
*This ADR eliminates scattered configuration as identified in architecture analysis.*
