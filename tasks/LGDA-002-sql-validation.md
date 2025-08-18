# LGDA-002: SQL Validation Testing

## Архитектурный контекст

Основываясь на **ADR 003** (безопасность SQL) и диаграмме архитектуры, SQL валидация - критический узел безопасности:
- Узел `VALIDATE SQL` должен блокировать опасные запросы
- Интеграция с `sqlglot` для парсинга BigQuery диалекта
- Fallback path при невалидном SQL
- Принудительная вставка `LIMIT` для неагрегирующих запросов

## Цель задачи
Создать bulletproof SQL валидатор с 100% покрытием безопасности и корректности.

## Детальный анализ безопасности

### 1. SQL Injection Prevention
**Архитектурная роль**: Первая линия защиты от вредоносного SQL
**Подводные камни**:
- LLM может сгенерировать SQL injection атаки
- Комментарии в SQL могут скрывать вредоносный код
- Nested subqueries могут обходить простые фильтры
- Unicode и encoding attacks

**Тестовые сценарии атак**:
```python
def test_sql_injection_prevention():
    """Блокирует классические SQL injection паттерны"""
    malicious_queries = [
        "SELECT * FROM orders; DROP TABLE users; --",
        "SELECT * FROM orders WHERE 1=1 OR '1'='1'",
        "SELECT * FROM orders UNION SELECT password FROM admin_users",
        "SELECT * FROM orders /* comment */ DELETE FROM products",
    ]

def test_unicode_attack_prevention():
    """Блокирует Unicode-based attacks"""
    
def test_encoding_bypasses():
    """Блокирует попытки обхода через кодировки"""
```

### 2. Statement Type Validation  
**Компонент**: SELECT-only policy
**ADR связь**: **ADR 003** - "Разрешаем только SELECT"

**Подводные камни**:
- CTE (Common Table Expressions) могут содержать DML
- MERGE statements выглядят как SELECT но модифицируют данные
- Stored procedures calls через SELECT
- Dynamic SQL generation

**Критические тесты**:
```python
def test_select_only_enforcement():
    """Разрешает только SELECT statements"""
    
def test_dml_statement_blocking():
    """Блокирует INSERT, UPDATE, DELETE, MERGE"""
    forbidden_statements = [
        "INSERT INTO orders VALUES (1, 'test')",
        "UPDATE orders SET status = 'cancelled'", 
        "DELETE FROM orders WHERE id = 1",
        "MERGE orders USING staging ON orders.id = staging.id",
        "TRUNCATE TABLE orders",
        "CREATE TABLE test_table (id INT)",
        "DROP TABLE orders",
        "ALTER TABLE orders ADD COLUMN test_col STRING",
    ]

def test_ddl_statement_blocking():
    """Блокирует CREATE, DROP, ALTER"""

def test_cte_validation():
    """Валидирует CTE не содержат DML"""
    cte_query = """
    WITH recent_orders AS (
        SELECT * FROM orders WHERE created_at > '2023-01-01'
    )
    SELECT COUNT(*) FROM recent_orders
    """
```

### 3. Table Whitelist Enforcement
**Компонент**: Table access control  
**ADR связь**: **ADR 003** - "Белый список таблиц: orders, order_items, products, users"

**Подводные камни**:
- Table aliases могут обходить whitelist
- Schema qualified names (dataset.table)
- Information_schema access для reconnaissance
- Subqueries с запрещенными таблицами
- JOIN с external tables

**Критические тесты**:
```python
def test_table_whitelist_enforcement():
    """Разрешает только whitelisted таблицы"""
    allowed_tables = ['orders', 'order_items', 'products', 'users']
    
def test_forbidden_table_blocking():
    """Блокирует доступ к неразрешенным таблицам"""
    forbidden_queries = [
        "SELECT * FROM admin_users",
        "SELECT * FROM financial_data", 
        "SELECT * FROM `bigquery-public-data.other_dataset.table`",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM orders o JOIN admin_config ac ON o.id = ac.order_id",
    ]

def test_schema_qualified_names():
    """Корректно обрабатывает schema.table notation"""
    
def test_table_aliases_validation():
    """Валидирует aliases не обходят whitelist"""
    
def test_subquery_table_validation():
    """Проверяет таблицы в subqueries"""
```

### 4. LIMIT Injection Logic
**Компонент**: Auto-LIMIT для неагрегирующих запросов
**ADR связь**: **ADR 003** - "Принудительный LIMIT 1000"

**Подводные камни**:
- Определение агрегирующих vs неагрегирующих запросов
- WINDOW functions считаются агрегирующими?
- DISTINCT может быть агрегацией
- Subqueries с/без агрегации
- Performance impact от LIMIT

**Сложные случаи**:
```python
def test_aggregation_detection():
    """Корректно определяет агрегирующие запросы"""
    aggregating_queries = [
        "SELECT COUNT(*) FROM orders",
        "SELECT SUM(amount) FROM orders GROUP BY status", 
        "SELECT AVG(price) FROM products",
        "SELECT DISTINCT category FROM products",
        "SELECT COUNT(DISTINCT user_id) FROM orders",
    ]

def test_window_function_handling():
    """Обрабатывает WINDOW functions"""
    window_query = """
    SELECT 
        user_id,
        ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at) as row_num
    FROM orders
    """

def test_limit_injection():
    """Вставляет LIMIT в неагрегирующие запросы"""
    
def test_existing_limit_preservation():
    """Сохраняет существующий LIMIT если он меньше 1000"""
```

### 5. sqlglot Integration Challenges
**Компонент**: SQL parsing engine
**Технические подводные камни**:
- BigQuery диалект vs Standard SQL различия
- sqlglot может не поддерживать все BigQuery функции
- Parsing errors vs semantic errors
- Performance на больших SQL запросах

**Специфичные для BigQuery тесты**:
```python
def test_bigquery_dialect_parsing():
    """Корректно парсит BigQuery-специфичные конструкции"""
    bigquery_queries = [
        "SELECT DATE(created_at) FROM orders",
        "SELECT EXTRACT(YEAR FROM created_at) FROM orders",
        "SELECT REGEXP_EXTRACT(email, r'@(.+)') FROM users",
        "SELECT ARRAY_AGG(product_id) FROM order_items GROUP BY order_id",
        "SELECT * FROM UNNEST(['a', 'b', 'c']) as t",
    ]

def test_parsing_error_handling():
    """Обрабатывает ошибки парсинга"""
    
def test_semantic_validation():
    """Семантическая валидация после парсинга"""
```

## Архитектурная интеграция

### Integration с LangGraph Flow
```python
def validate_sql_node(state: AgentState) -> AgentState:
    """
    Входные данные: state.sql (сгенерированный LLM SQL)
    Валидация: security policies + correctness
    Выходные данные: 
        - state.sql (модифицированный с LIMIT)
        - state.error (если валидация провалилась)
    Переходы:
        - Success -> execute_sql_node  
        - Failure -> fallback_node
    """
```

### Error Handling Strategy
**Принцип**: Fail-safe, никогда не выполнять невалидный SQL

```python
class SQLValidationError(Exception):
    """Базовая ошибка валидации SQL"""
    
class SecurityViolationError(SQLValidationError):
    """Нарушение политик безопасности"""
    
class ParseError(SQLValidationError):
    """Ошибка парсинга SQL"""
    
class TableAccessError(SQLValidationError):
    """Доступ к запрещенной таблице"""
```

## Производительность и масштабируемость

### Performance Targets
- Валидация SQL < 100ms для 95% запросов
- Memory usage < 50MB для валидации
- CPU usage < 10% single core

### Caching Strategy
```python
@lru_cache(maxsize=1000)
def validate_sql_cached(sql_hash: str) -> ValidationResult:
    """Кеширование результатов валидации для идентичных запросов"""
```

## Структура тестов

```
tests/unit/sql_validation/
├── test_security_policies.py      # Injection prevention, statement types
├── test_table_whitelist.py        # Table access control
├── test_limit_injection.py        # Auto-LIMIT logic
├── test_sqlglot_integration.py    # Parser integration
├── test_error_handling.py         # Error scenarios
└── test_performance.py            # Performance benchmarks

tests/fixtures/sql_samples/
├── valid_queries.sql              # Допустимые запросы
├── malicious_queries.sql          # Вредоносные запросы  
├── edge_cases.sql                 # Граничные случаи
└── bigquery_specific.sql          # BigQuery-специфичные запросы
```

## Критерии приемки

- [ ] 100% блокировка DML/DDL statements
- [ ] 100% блокировка SQL injection паттернов
- [ ] Whitelist таблиц строго соблюдается
- [ ] LIMIT автоматически вставляется где нужно
- [ ] BigQuery диалект корректно парсится
- [ ] Performance targets достигнуты
- [ ] Error messages понятны пользователю
- [ ] Интеграция с LangGraph flow работает

## Возможные сложности

### 1. False Positives
**Проблема**: Валидные запросы блокируются
**Решение**: Extensive test suite с реальными бизнес-запросами

### 2. False Negatives  
**Проблема**: Вредоносные запросы проходят валидацию
**Решение**: Red team testing, penetration testing

### 3. BigQuery Dialect Evolution
**Проблема**: Новые функции BigQuery не поддерживаются sqlglot
**Решение**: Fallback to basic string validation, regular updates

### 4. Performance Degradation
**Проблема**: Сложные запросы парсятся медленно
**Решение**: Timeout limits, caching, query complexity limits

## Метрики безопасности

- Security test coverage: 100%
- Known attack patterns blocked: 100%
- False positive rate: < 1%
- False negative rate: 0%
- Validation latency: p95 < 100ms

## Integration Points

- **Зависит от**: LGDA-001 (test infrastructure)
- **Используется в**: LGDA-006 (LangGraph nodes), LGDA-010 (integration tests)
- **Критично для**: LGDA-012 (BigQuery production integration)
