
# LGDA-001: Test Infrastructure Setup

## Архитектурный контекст

Основываясь на **ADR 002** (узловой граф) и **ADR 005** (CLI и трассировка), тестовая инфраструктура должна поддерживать:
- Изолированное тестирование каждого узла LangGraph
- Мокирование внешних зависимостей (BigQuery, Gemini)
- Трассировку промежуточных состояний
- CLI тестирование с захватом вывода

## Цель задачи
Создать фундаментальную тестовую инфраструктуру для TDD разработки с полным покрытием архитектурных компонентов.

## Детальный анализ компонентов

### 1. LangGraph State Testing
**Компонент**: `AgentState` (src/agent/state.py)
**Архитектурная роль**: Центральное состояние, передаваемое между узлами
**Подводные камни**:
- Pydantic модель может не сериализоваться корректно в тестах
- Состояние мутируется узлами - нужна изоляция между тестами
- История чата может накапливаться и влиять на производительность тестов

**Тестовые сценарии**:
```python
def test_agent_state_initialization():
    """Базовое создание состояния с валидными данными"""

def test_agent_state_serialization():
    """Состояние корректно сериализуется/десериализуется"""

def test_agent_state_history_management():
    """История чата ограничена и управляется корректно"""

def test_agent_state_error_propagation():
    """Ошибки корректно сохраняются в состоянии"""
```

### 2. BigQuery Client Mocking
**Компонент**: `bq_client()`, `get_schema()`, `run_query()` (src/bq.py)
**Архитектурная роль**: Интерфейс к внешнему хранилищу данных
**ADR связь**: **ADR 003** (безопасность SQL), **ADR 006** (схемы)

**Подводные камни**:
- Google Cloud Auth в тестах - нужно полное мокирование
- Schema responses должны имитировать реальную структуру INFORMATION_SCHEMA
- Dry-run режим BigQuery для валидации без выполнения
- Rate limiting и квоты BigQuery в тестах

**Критические моки**:
```python
@pytest.fixture
def mock_bigquery_client():
    """Мок BigQuery клиента с реалистичными ответами"""

@pytest.fixture  
def sample_schema_response():
    """Реалистичная схема таблиц thelook_ecommerce"""

@pytest.fixture
def mock_query_job():
    """Мок job с результатами запроса и метриками"""
```

**Тестовые данные**:
- Схемы для tables: orders, order_items, products, users
- Различные типы данных: STRING, INTEGER, TIMESTAMP, FLOAT
- Ошибки: BadRequest, AuthenticationError, QuotaExceeded

### 3. LLM (Gemini) Mocking  
**Компонент**: `llm_completion()` (src/llm.py)
**Архитектурная роль**: Генерация планов, SQL, отчетов
**ADR связь**: **ADR 004** (LLM провайдер и фолбэк)

**Подводные камни**:
- Gemini API responses непредсказуемы - нужны детерминированные моки
- Rate limiting и токен лимиты
- Разные типы ответов: JSON планы, SQL запросы, текстовые отчеты
- Fallback логика на Bedrock

**Критические моки**:
```python
@pytest.fixture
def mock_gemini_client():
    """Мок Gemini с предсказуемыми ответами"""

@pytest.fixture
def sample_plan_response():
    """Валидный JSON план для тестирования"""

@pytest.fixture  
def sample_sql_response():
    """Корректный BigQuery SQL"""

@pytest.fixture
def sample_report_response():
    """Бизнес-инсайт для тестирования"""
```

### 4. CLI Testing Infrastructure
**Компонент**: CLI interface (cli.py)
**Архитектурная роль**: Пользовательский интерфейс
**ADR связь**: **ADR 005** (CLI и трассировка)

**Подводные камни**:
- Click тестирование требует специального CliRunner
- Rich вывод может ломать тесты (ANSI коды)
- Verbose режим создает много вывода
- Интерактивные промпты в тестах

**Тестовые сценарии**:
```python
def test_cli_basic_invocation():
    """CLI запускается с базовыми аргументами"""

def test_cli_verbose_mode():
    """Verbose режим выводит JSON состояния"""

def test_cli_error_handling():
    """CLI корректно обрабатывает ошибки"""

def test_cli_environment_variables():
    """CLI читает конфигурацию из .env"""
```

## Структура тестов

```
tests/
├── conftest.py                 # Общие fixtures и конфигурация
├── fixtures/
│   ├── sample_schemas.json     # Схемы BigQuery таблиц
│   ├── sample_responses.json   # LLM ответы для тестирования  
│   ├── sample_dataframes.pkl   # Pandas DataFrames
│   └── sample_configs.yaml     # Конфигурации для тестов
├── unit/
│   ├── test_agent_state.py     # Тестирование состояния
│   ├── test_bq_client.py       # BigQuery клиент (моки)
│   ├── test_llm_client.py      # LLM клиент (моки)
│   └── test_config.py          # Конфигурация и настройки
├── integration/
│   ├── test_cli_interface.py   # CLI тестирование
│   └── test_langgraph_flow.py  # Интеграция узлов
└── utils/
    ├── mock_helpers.py         # Утилиты для создания моков
    └── test_data_generators.py # Генераторы тестовых данных
```

## Критические зависимости

```python
# requirements-test.txt
pytest>=7.4.0
pytest-mock>=3.11.1  
pytest-cov>=4.1.0
pytest-asyncio>=0.21.1
responses>=0.23.3      # HTTP мокирование
freezegun>=1.2.2       # Мокирование времени
factory-boy>=3.3.0     # Фабрики тестовых данных
```

## Возможные сложности и решения

### 1. Асинхронность в LangGraph
**Проблема**: LangGraph может использовать async/await
**Решение**: pytest-asyncio для тестирования async кода

### 2. Глобальное состояние
**Проблема**: Глобальные переменные (например, _bq_client) могут загрязнять тесты
**Решение**: Fixtures с очисткой после каждого теста

### 3. Внешние API в CI/CD
**Проблема**: Тесты не должны делать реальные API вызовы
**Решение**: Полное мокирование с проверкой через environment variables

### 4. Производительность тестов
**Проблема**: Большие объемы тестовых данных замедляют тесты
**Решение**: Ленивая загрузка fixtures, кеширование

## Критерии приемки

- [ ] pytest обнаруживает и запускает все тесты
- [ ] Coverage report показывает покрытие тестов
- [ ] Все внешние зависимости (BigQuery, Gemini) полностью замокированы
- [ ] CLI тесты работают без реальных API ключей
- [ ] Тесты выполняются < 30 секунд
- [ ] Нет случайных падений (flaky tests)
- [ ] Структура тестов соответствует архитектуре проекта

## Метрики успеха

- Время выполнения тестов: < 30 секунд
- Test coverage: > 80% для новых компонентов
- Количество flaky tests: 0
- Время настройки для нового разработчика: < 10 минут

## Integration Points

- **Зависит от**: Нет прямых зависимостей (базовая инфраструктура)
- **Используется в**: Все последующие задачи (LGDA-002 through LGDA-015)
- **Критично для**: LGDA-006 (LangGraph nodes), LGDA-010 (integration tests), LGDA-012 (production deployment)

## Следующие задачи

После LGDA-001 можно перейти к:
- **LGDA-002**: SQL Validation Testing (зависит от BigQuery моков)
- **LGDA-005**: CLI Testing Framework (зависит от общей инфраструктуры)
