# LGDA-005: Configuration Management

## Архитектурный контекст

Основываясь на всех ADR и архитектурной диаграмме, конфигурация управляет:
- Environment-specific settings (dev/staging/production)
- External service credentials (BigQuery, Gemini, Bedrock)
- Feature flags и business rules
- Performance tuning parameters
- Security policies

## Цель задачи
Создать robust configuration system с 12-factor app principles, secure credential management и environment-aware behavior.

## Детальный анализ архитектуры

### 1. 12-Factor App Configuration
**Принцип**: Configuration через environment variables
**ADR связь**: Все ADR зависят от правильной конфигурации

**Configuration Hierarchy**:
```
1. Environment variables (highest priority)
2. .env files (development)  
3. Config files (defaults)
4. Hard-coded defaults (fallback)
```

**Подводные камни**:
- Secret leakage в logs/error messages
- Environment variable naming conflicts
- Type conversion errors (string → int/bool)
- Missing required configuration
- Development vs production пути

**Core Configuration Structure**:
```python
from pydantic import BaseSettings, Field, validator
from typing import Optional, List
import os

class LGDAConfig(BaseSettings):
    """
    Главная конфигурация LGDA agent
    Использует Pydantic для validation и type safety
    """
    
    # Environment identification
    environment: str = Field(default="development", env="LGDA_ENVIRONMENT")
    debug: bool = Field(default=False, env="LGDA_DEBUG")
    log_level: str = Field(default="INFO", env="LGDA_LOG_LEVEL")
    
    # BigQuery configuration
    bigquery_project_id: str = Field(..., env="LGDA_BIGQUERY_PROJECT_ID")
    bigquery_dataset: str = Field(
        default="bigquery-public-data.thelook_ecommerce", 
        env="LGDA_BIGQUERY_DATASET"
    )
    bigquery_location: str = Field(default="US", env="LGDA_BIGQUERY_LOCATION")
    bigquery_credentials_path: Optional[str] = Field(None, env="LGDA_BIGQUERY_CREDENTIALS")
    
    # LLM configuration  
    llm_primary_provider: str = Field(default="gemini", env="LGDA_LLM_PRIMARY")
    llm_fallback_provider: str = Field(default="bedrock", env="LGDA_LLM_FALLBACK")
    gemini_api_key: Optional[str] = Field(None, env="LGDA_GEMINI_API_KEY")
    gemini_project_id: Optional[str] = Field(None, env="LGDA_GEMINI_PROJECT_ID")
    bedrock_region: str = Field(default="us-east-1", env="LGDA_BEDROCK_REGION")
    
    # Security policies
    sql_max_limit: int = Field(default=1000, env="LGDA_SQL_MAX_LIMIT")
    allowed_tables: List[str] = Field(
        default=["orders", "order_items", "products", "users"],
        env="LGDA_ALLOWED_TABLES"
    )
    
    @validator('environment')
    def validate_environment(cls, v):
        allowed = ['development', 'staging', 'production']
        if v not in allowed:
            raise ValueError(f'environment must be one of {allowed}')
        return v
    
    @validator('log_level')  
    def validate_log_level(cls, v):
        allowed = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v not in allowed:
            raise ValueError(f'log_level must be one of {allowed}')
        return v
    
    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = False

def test_config_validation():
    """Валидирует configuration constraints"""
    
def test_environment_variable_override():
    """Environment variables override defaults"""
    
def test_missing_required_config():
    """Raises error для missing required config"""
    
def test_type_conversion():
    """Корректно конвертирует types из environment variables"""
```

### 2. Secure Credential Management
**Компонент**: Sensitive data protection
**Критично**: Prevents credential leakage

**Credential Sources Priority**:
1. **Environment variables** (production)
2. **Secret management services** (AWS Secrets Manager, Google Secret Manager)
3. **Local credential files** (development only)
4. **Application Default Credentials** (Google Cloud)

**Security Measures**:
```python
from typing import Union
import json
import base64
from pathlib import Path

class CredentialManager:
    """Secure credential management"""
    
    def __init__(self, config: LGDAConfig):
        self.config = config
        self.secrets_cache = {}
    
    def get_bigquery_credentials(self) -> Union[str, dict]:
        """
        BigQuery credential resolution:
        1. Service account JSON from env var (base64 encoded)
        2. Service account file path
        3. Application Default Credentials
        """
        if creds_json := os.getenv('LGDA_BIGQUERY_CREDENTIALS_JSON'):
            return json.loads(base64.b64decode(creds_json))
        
        if self.config.bigquery_credentials_path:
            return str(Path(self.config.bigquery_credentials_path).resolve())
        
        return None  # Use Application Default Credentials
    
    def get_gemini_credentials(self) -> dict:
        """Gemini API credentials"""
        
    def get_bedrock_credentials(self) -> dict:
        """AWS Bedrock credentials"""
    
    def mask_sensitive_data(self, data: dict) -> dict:
        """Masks sensitive data для logging"""
        sensitive_keys = ['api_key', 'secret', 'password', 'token', 'credentials']
        masked = data.copy()
        for key in masked:
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                masked[key] = "***MASKED***"
        return masked

def test_credential_masking():
    """Sensitive data замаскирована в logs"""
    
def test_credential_source_priority():
    """Использует правильный credential source"""
    
def test_credential_validation():
    """Валидирует credential format"""
    
def test_no_credential_leakage():
    """Credentials не появляются в error messages"""
```

### 3. Environment-Specific Configuration
**Компонент**: Multi-environment support
**Паттерн**: Environment-based configuration profiles

**Environment Profiles**:
```python
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class EnvironmentProfile:
    """Environment-specific configuration overrides"""
    name: str
    config_overrides: Dict[str, Any]
    feature_flags: Dict[str, bool]
    performance_settings: Dict[str, Any]

ENVIRONMENT_PROFILES = {
    'development': EnvironmentProfile(
        name='development',
        config_overrides={
            'debug': True,
            'log_level': 'DEBUG',
            'sql_max_limit': 100,  # Smaller limits for dev
        },
        feature_flags={
            'enable_query_cache': False,
            'enable_cost_tracking': False,
            'enable_performance_monitoring': False,
        },
        performance_settings={
            'query_timeout': 60,  # 1 minute for dev
            'retry_count': 1,
            'cache_ttl': 300,
        }
    ),
    
    'staging': EnvironmentProfile(
        name='staging', 
        config_overrides={
            'debug': False,
            'log_level': 'INFO',
            'sql_max_limit': 500,
        },
        feature_flags={
            'enable_query_cache': True,
            'enable_cost_tracking': True,
            'enable_performance_monitoring': True,
        },
        performance_settings={
            'query_timeout': 180,  # 3 minutes
            'retry_count': 2,
            'cache_ttl': 600,
        }
    ),
    
    'production': EnvironmentProfile(
        name='production',
        config_overrides={
            'debug': False,
            'log_level': 'WARNING',
            'sql_max_limit': 1000,
        },
        feature_flags={
            'enable_query_cache': True,
            'enable_cost_tracking': True,
            'enable_performance_monitoring': True,
            'enable_fallback_llm': True,
        },
        performance_settings={
            'query_timeout': 300,  # 5 minutes
            'retry_count': 3,
            'cache_ttl': 1800,
        }
    )
}

def test_environment_profile_loading():
    """Корректно загружает environment profiles"""
    
def test_profile_override_precedence():
    """Profile overrides применяются правильно"""
    
def test_feature_flag_evaluation():
    """Feature flags work correctly"""
```

### 4. Feature Flags & Business Rules
**Компонент**: Runtime behavior control
**Цель**: Безопасное rolling out новых features

**Feature Flag System**:
```python
from enum import Enum
from typing import Callable, Any

class FeatureFlag(Enum):
    """Available feature flags"""
    ENABLE_QUERY_CACHE = "enable_query_cache"
    ENABLE_COST_TRACKING = "enable_cost_tracking"
    ENABLE_ADVANCED_ANALYTICS = "enable_advanced_analytics"
    ENABLE_FALLBACK_LLM = "enable_fallback_llm"
    ENABLE_SQL_OPTIMIZATION = "enable_sql_optimization"
    ENABLE_PERFORMANCE_MONITORING = "enable_performance_monitoring"

class FeatureFlagManager:
    """Runtime feature flag evaluation"""
    
    def __init__(self, config: LGDAConfig, profile: EnvironmentProfile):
        self.config = config
        self.profile = profile
        self.custom_rules = {}
    
    def is_enabled(self, flag: FeatureFlag, context: dict = None) -> bool:
        """
        Feature flag evaluation с context:
        1. Check custom rules (A/B testing, user segments)
        2. Check environment profile
        3. Check global config
        4. Default to False
        """
        if custom_rule := self.custom_rules.get(flag):
            return custom_rule(context or {})
        
        return self.profile.feature_flags.get(flag.value, False)
    
    def add_custom_rule(self, flag: FeatureFlag, rule: Callable[[dict], bool]):
        """Добавляет custom evaluation rule"""
        self.custom_rules[flag] = rule

def test_feature_flag_evaluation():
    """Feature flags evaluate correctly"""
    
def test_custom_rule_precedence():
    """Custom rules override profile settings"""
    
def test_context_dependent_flags():
    """Context влияет на flag evaluation"""
```

### 5. Performance Tuning Configuration
**Компонент**: Runtime performance optimization
**ADR связь**: Все performance-related settings

**Performance Configuration**:
```python
@dataclass
class PerformanceConfig:
    """Performance tuning parameters"""
    
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
    def for_environment(cls, environment: str) -> 'PerformanceConfig':
        """Factory method для environment-specific performance config"""
        if environment == 'development':
            return cls(
                query_timeout=60,
                max_concurrent_queries=2,
                max_dataframe_rows=1000,
                max_memory_mb=256,
            )
        elif environment == 'production':
            return cls(
                query_timeout=300,
                max_concurrent_queries=10, 
                max_dataframe_rows=50000,
                max_memory_mb=1024,
            )
        else:  # staging
            return cls()

def test_performance_config_scaling():
    """Performance settings scale по environment"""
    
def test_resource_limit_enforcement():
    """Resource limits строго соблюдаются"""
```

## Архитектурная интеграция

### Configuration Factory Pattern
```python
class ConfigFactory:
    """Central configuration factory"""
    
    @staticmethod
    def create_config() -> LGDAConfig:
        """Creates fully configured LGDA config"""
        base_config = LGDAConfig()
        profile = ENVIRONMENT_PROFILES[base_config.environment]
        
        # Apply environment overrides
        for key, value in profile.config_overrides.items():
            setattr(base_config, key, value)
        
        return base_config
    
    @staticmethod
    def create_managers(config: LGDAConfig) -> tuple:
        """Creates all configuration managers"""
        profile = ENVIRONMENT_PROFILES[config.environment]
        
        credential_manager = CredentialManager(config)
        feature_manager = FeatureFlagManager(config, profile)
        performance_config = PerformanceConfig.for_environment(config.environment)
        
        return credential_manager, feature_manager, performance_config

def test_config_factory_integration():
    """Config factory создает consistent configuration"""
    
def test_manager_coordination():
    """All managers работают together"""
```

### Dependency Injection Integration
```python
from typing import Protocol

class ConfigProvider(Protocol):
    """Configuration provider interface для DI"""
    
    def get_config(self) -> LGDAConfig:
        """Returns main configuration"""
    
    def get_credentials(self, service: str) -> dict:
        """Returns service credentials"""
    
    def is_feature_enabled(self, flag: FeatureFlag) -> bool:
        """Checks feature flag"""

# Usage в LangGraph nodes
async def synthesize_sql_node(
    state: AgentState,
    config_provider: ConfigProvider
) -> AgentState:
    """SQL synthesis node с configuration injection"""
    
    if config_provider.is_feature_enabled(FeatureFlag.ENABLE_SQL_OPTIMIZATION):
        # Use advanced SQL optimization
        pass
    
    max_limit = config_provider.get_config().sql_max_limit
    # Apply limit to generated SQL
```

## Configuration Validation & Testing

### Schema Validation
```python
def test_config_schema_compliance():
    """Configuration соответствует expected schema"""
    
def test_required_field_validation():
    """Required fields validation работает"""
    
def test_type_safety():
    """Type annotations enforced"""

def test_constraint_validation():
    """Business constraints validated"""
```

### Environment Testing
```python
def test_all_environments_valid():
    """Все environments загружаются successfully"""
    
def test_environment_isolation():
    """Environment configurations isolated"""
    
def test_production_security():
    """Production configuration secure"""
```

## Структура тестов

```
tests/unit/config/
├── test_base_config.py           # Core configuration
├── test_credential_management.py # Credential handling
├── test_environment_profiles.py  # Environment-specific config
├── test_feature_flags.py         # Feature flag system
├── test_performance_config.py    # Performance settings
├── test_validation.py            # Configuration validation
└── test_factory.py               # Configuration factory

tests/integration/config/
├── test_real_credentials.py      # Real credential loading
├── test_environment_switching.py # Environment transitions
└── test_config_persistence.py    # Configuration persistence

tests/fixtures/config/
├── test_environments/            # Test environment configs
├── sample_credentials/           # Sample credential files
└── config_scenarios.json        # Test scenarios
```

## Критерии приемки

- [ ] Все environments (dev/staging/production) загружаются корректно
- [ ] Sensitive data никогда не логируется
- [ ] Environment variables override defaults
- [ ] Feature flags работают runtime
- [ ] Performance configs применяются правильно
- [ ] Credential loading работает для всех sources
- [ ] Configuration validation catches все errors
- [ ] Integration с всеми components seamless

## Возможные сложности

### 1. Environment Variable Conflicts
**Проблема**: Naming collisions, inconsistent naming
**Решение**: Prefixed naming convention (LGDA_*), documentation

### 2. Credential Security
**Проблема**: Accidental credential exposure
**Решение**: Masking, security scanning, access controls

### 3. Configuration Drift
**Проблема**: Environments дрейфуют apart
**Решение**: Configuration as code, validation tests, monitoring

### 4. Performance Impact
**Проблема**: Configuration loading латency
**Решение**: Caching, lazy loading, pre-validation

## Метрики конфигурации

- Configuration load time: < 100ms
- Credential resolution time: < 50ms
- Feature flag evaluation: < 1ms
- Configuration validation: 100% error detection
- Secret masking coverage: 100%
- Environment parity: 95%+ identical behavior

## Integration Points

- **Зависит от**: LGDA-001 (test infrastructure)
- **Используется в**: Все components (LGDA-003, LGDA-004, LGDA-006, etc.)
- **Критично для**: LGDA-012 (production deployment), LGDA-014 (monitoring)
