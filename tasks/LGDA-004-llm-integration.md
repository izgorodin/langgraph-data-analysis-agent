# LGDA-004: LLM Integration & Fallback

## Архитектурный контекст

Основываясь на **ADR 002** (LLM выбор) и **ADR 004** (fallback стратегия), LLM интеграция обеспечивает:
- Primary: Google Gemini (через Vertex AI или API)
- Fallback: AWS Bedrock (Claude, если Gemini недоступен)
- Unified interface для всех LLM providers
- Роль в LangGraph: plan generation, SQL synthesis, result analysis

## Цель задачи
Создать bulletproof LLM интеграцию с seamless failover, cost optimization и enterprise-grade reliability.

## Детальный анализ архитектуры

### 1. Provider Abstraction Layer
**Компонент**: Unified LLM interface
**Паттерн**: Strategy pattern с provider-agnostic API

**Архитектурные подводные камни**:
- Различия в API между providers (Gemini vs Bedrock)
- Token counting inconsistencies
- Response format variations  
- Rate limiting policies различаются
- Cost models отличаются (per-token vs per-request)

**Unified Interface**:
```python
from abc import ABC, abstractmethod
from typing import Protocol

class LLMProvider(Protocol):
    """Unified interface для всех LLM providers"""
    
    async def generate_text(
        self, 
        prompt: str, 
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs
    ) -> LLMResponse:
        """Асинхронная генерация текста"""
    
    def estimate_cost(self, prompt: str, max_tokens: int) -> float:
        """Оценка стоимости запроса"""
    
    def get_token_count(self, text: str) -> int:
        """Подсчет токенов"""

def test_provider_interface_compliance():
    """Все providers соответствуют unified interface"""
    
def test_response_format_normalization():
    """Response format одинаковый для всех providers"""
    
def test_token_counting_consistency():
    """Token counting работает для всех providers"""
```

### 2. Gemini Primary Provider
**Компонент**: Google Gemini integration
**ADR связь**: **ADR 002** - "Gemini как primary LLM"

**Gemini-специфичные особенности**:
- Vertex AI vs Direct API access
- Safety settings configuration
- Function calling capabilities
- Multimodal input support (будущее расширение)
- Grounding с Google Search (опционально)

**Technical Challenges**:
```python
class GeminiProvider:
    """Google Gemini provider implementation"""
    
    def __init__(self, use_vertex_ai: bool = True):
        self.use_vertex_ai = use_vertex_ai
        self.safety_settings = self._get_safety_config()
    
    def _get_safety_config(self):
        """Настройка safety filters для корпоративного использования"""
        return {
            'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_MEDIUM_AND_ABOVE',
            'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_MEDIUM_AND_ABOVE',
            'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_MEDIUM_AND_ABOVE',
            'HARM_CATEGORY_HARASSMENT': 'BLOCK_MEDIUM_AND_ABOVE',
        }

def test_vertex_ai_authentication():
    """Аутентификация через Vertex AI"""
    
def test_direct_api_fallback():
    """Fallback на Direct API если Vertex AI недоступен"""
    
def test_safety_filter_configuration():
    """Safety filters корректно настроены"""
    
def test_gemini_specific_features():
    """Тестирует Gemini-специфичные возможности"""
```

### 3. Bedrock Fallback Provider  
**Компонент**: AWS Bedrock integration
**ADR связь**: **ADR 004** - "Fallback стратегия"

**Bedrock Integration Challenges**:
- Claude model selection (Claude-3 Haiku vs Sonnet vs Opus)
- AWS credential management отличается от Google
- Different pricing model
- Request/response format mapping
- Regional availability

**Fallback Strategy**:
```python
class BedrockProvider:
    """AWS Bedrock provider implementation"""
    
    CLAUDE_MODELS = {
        'fast': 'anthropic.claude-3-haiku-20240307-v1:0',
        'balanced': 'anthropic.claude-3-sonnet-20240229-v1:0', 
        'best': 'anthropic.claude-3-opus-20240229-v1:0',
    }
    
    def __init__(self, model_tier: str = 'balanced'):
        self.model_id = self.CLAUDE_MODELS[model_tier]
        self.aws_session = self._create_session()

def test_aws_credential_management():
    """AWS credentials management"""
    
def test_claude_model_selection():
    """Выбор оптимальной Claude model"""
    
def test_bedrock_response_mapping():
    """Mapping Bedrock responses к unified format"""
    
def test_regional_availability():
    """Handles regional Bedrock availability"""
```

### 4. Intelligent Fallback Logic
**Компонент**: Provider selection & switching
**Принцип**: Cost-aware, performance-optimized failover

**Fallback Triggers**:
1. **Primary unavailable** - network, service errors
2. **Rate limiting** - quota exhaustion, throttling
3. **Quality degradation** - poor response quality
4. **Cost optimization** - budget thresholds
5. **Performance issues** - high latency

**Switching Logic**:
```python
class LLMProviderManager:
    """Интеллектуальное управление LLM providers"""
    
    def __init__(self):
        self.primary = GeminiProvider()
        self.fallback = BedrockProvider()
        self.circuit_breaker = CircuitBreaker()
        self.cost_tracker = CostTracker()
    
    async def generate_with_fallback(
        self, 
        prompt: str, 
        context: str = "data_analysis"
    ) -> LLMResponse:
        """
        Smart provider selection:
        1. Check circuit breaker state
        2. Evaluate cost constraints  
        3. Try primary provider
        4. Fallback if needed
        5. Update metrics
        """

def test_automatic_failover():
    """Автоматический переход на fallback"""
    
def test_circuit_breaker_behavior():
    """Circuit breaker предотвращает cascade failures"""
    
def test_cost_aware_switching():
    """Переключение based on cost thresholds"""
    
def test_health_check_recovery():
    """Возврат к primary когда он восстановился"""
```

### 5. Prompt Engineering & Context Management
**Компонент**: Domain-specific prompt optimization
**ADR связь**: Integration с LangGraph nodes

**Prompt Templates per Node Type**:
```python
PROMPT_TEMPLATES = {
    'plan_analysis': """
    Analyze this business question for data analysis:
    Question: {user_question}
    Available tables: {table_schemas}
    
    Create a step-by-step analysis plan focusing on:
    1. Key metrics to calculate
    2. Relevant data sources
    3. Expected insights
    """,
    
    'sql_generation': """
    Generate BigQuery SQL for this analysis:
    Plan: {analysis_plan}
    Schema: {table_schema}
    
    Requirements:
    - Use only SELECT statements
    - Include appropriate JOINs
    - Add helpful column aliases
    - Optimize for performance
    """,
    
    'result_analysis': """
    Analyze these data results:
    Query: {sql_query}
    Results: {dataframe_summary}
    Original question: {user_question}
    
    Provide insights including:
    1. Key findings
    2. Trends and patterns
    3. Business implications
    """
}

def test_prompt_template_effectiveness():
    """Prompt templates генерируют качественные responses"""
    
def test_context_size_management():
    """Context не превышает token limits"""
    
def test_prompt_injection_prevention():
    """Защита от prompt injection атак"""
```

### 6. Response Quality & Validation
**Компонент**: LLM output validation
**Цель**: Обеспечить consistent, high-quality outputs

**Quality Metrics**:
- SQL syntax correctness
- Business logic relevance  
- Response completeness
- Factual accuracy
- Format compliance

**Validation Pipeline**:
```python
class ResponseValidator:
    """Валидация LLM responses"""
    
    def validate_sql_response(self, response: str, context: str) -> ValidationResult:
        """
        Валидирует SQL generation responses:
        1. Extractable SQL query
        2. Syntax validity
        3. Schema compliance
        4. Security compliance
        """
    
    def validate_analysis_response(self, response: str, context: str) -> ValidationResult:
        """
        Валидирует analysis responses:
        1. Structured format
        2. Relevant insights
        3. Factual consistency
        4. Completeness
        """

def test_sql_extraction_accuracy():
    """Корректно извлекает SQL из LLM response"""
    
def test_analysis_quality_metrics():
    """Analysis responses соответствуют quality standards"""
    
def test_hallucination_detection():
    """Обнаруживает factual hallucinations"""
```

## Архитектурная интеграция

### LangGraph Node Integration
```python
async def plan_analysis_node(state: AgentState) -> AgentState:
    """
    LLM Node для analysis planning
    """
    llm_manager = LLMProviderManager()
    
    prompt = PROMPT_TEMPLATES['plan_analysis'].format(
        user_question=state.user_question,
        table_schemas=state.schema_context
    )
    
    response = await llm_manager.generate_with_fallback(
        prompt=prompt,
        context="planning"
    )
    
    # Validate and extract plan
    plan = extract_analysis_plan(response.text)
    
    return state.update(analysis_plan=plan)

async def synthesize_sql_node(state: AgentState) -> AgentState:
    """LLM Node для SQL generation"""
    
async def analyze_results_node(state: AgentState) -> AgentState:
    """LLM Node для result analysis"""
```

### Cost Management Integration
```python
class CostTracker:
    """Отслеживание LLM costs"""
    
    def __init__(self, daily_budget: float = 50.0):
        self.daily_budget = daily_budget
        self.current_spend = 0.0
        self.cost_per_provider = {}
    
    def can_afford_request(self, provider: str, estimated_cost: float) -> bool:
        """Проверяет budget constraints"""
        
    def track_request_cost(self, provider: str, actual_cost: float):
        """Tracks actual spending"""

def test_budget_enforcement():
    """Budget limits строго соблюдаются"""
    
def test_cost_optimization():
    """Выбор cost-effective provider когда возможно"""
```

## Performance & Reliability

### Performance Targets
- Response time: p95 < 3 seconds
- Failover time: < 500ms
- Uptime: 99.5% (учитывая external dependencies)
- Token efficiency: > 90% useful tokens

### Monitoring & Alerting
```python
class LLMMetrics:
    """LLM performance metrics"""
    response_time: float
    token_usage: int
    cost: float
    provider_used: str
    quality_score: float
    error_rate: float

def test_metrics_collection():
    """Собирает comprehensive metrics"""
    
def test_alerting_on_degradation():
    """Alerts при quality/performance degradation"""
```

## Структура тестов

```
tests/unit/llm/
├── test_provider_interface.py     # Unified interface
├── test_gemini_provider.py        # Gemini-specific tests  
├── test_bedrock_provider.py       # Bedrock-specific tests
├── test_fallback_logic.py         # Failover scenarios
├── test_prompt_engineering.py     # Prompt templates
├── test_response_validation.py    # Output quality
├── test_cost_management.py        # Budget tracking
└── test_performance.py            # Performance benchmarks

tests/integration/llm/
├── test_real_llm_calls.py         # Actual API calls
├── test_failover_scenarios.py     # End-to-end failover
├── test_long_conversations.py     # Extended interactions
└── test_cost_tracking.py          # Real cost tracking

tests/fixtures/llm/
├── prompt_examples.json           # Sample prompts
├── expected_responses.json        # Expected outputs
└── quality_benchmarks.json       # Quality baselines
```

## Критерии приемки

- [ ] Gemini primary provider работает надежно
- [ ] Bedrock fallback активируется автоматически
- [ ] Response quality соответствует benchmarks
- [ ] Cost tracking accurate в пределах 5%
- [ ] Failover time < 500ms
- [ ] Prompt injection protection работает
- [ ] Token usage optimized (< 10% waste)
- [ ] Integration с LangGraph nodes seamless

## Возможные сложности

### 1. Provider API Changes
**Проблема**: Google/AWS меняют APIs без notice
**Решение**: Version pinning, extensive integration tests, monitoring

### 2. Quality Consistency
**Проблема**: Разные providers дают разные quality responses
**Решение**: Response normalization, quality scoring, provider-specific tuning

### 3. Cost Explosion  
**Проблема**: Unexpected high token usage, premium model costs
**Решение**: Hard budget limits, cost estimation, usage monitoring

### 4. Latency Variability
**Проблема**: LLM response times непредсказуемы
**Решение**: Timeout handling, async processing, response caching

## Метрики качества

- SQL generation accuracy: > 95%
- Analysis relevance score: > 4.0/5.0
- Hallucination rate: < 5%
- Cost efficiency: < $0.10 per analysis
- Provider availability: 99%+ combined
- Response format compliance: 100%

## Integration Points

- **Зависит от**: LGDA-001 (test infrastructure)
- **Используется в**: LGDA-006 (LangGraph nodes), LGDA-008 (analysis generation)
- **Критично для**: LGDA-010 (integration tests), LGDA-014 (production monitoring)
