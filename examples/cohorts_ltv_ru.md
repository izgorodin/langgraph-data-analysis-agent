# Пример: когортный LTV (RU)

Запрос (RUS):

```
LGDA_STRICT_NO_FAKE_REPORT=true LGDA_BQ_TIMEOUT_SEC=120 .venv/bin/python cli.py "Сегментируй клиентов по когорте первого заказа (месяц) за 2022-2023, посчитай LTV за 180 дней по категориям продуктов с учётом возвратов и скидок; исключи тестовые/подозрительные аккаунты; построй топ-5 когорт по среднему LTV и тренд по месяцам с MAU, D30 retention и ARPU; верни краткий отчёт и таблицу метрик." --model openai/gpt-oss-120b --verbose --timeout 180
```

---

Ниже вырезан полный лог --verbose (сокращён для README):

## plan
{"task": "Cohort LTV 180d by product category", "tables": ["orders", "order_items", "products", "users"], "time_range": ["2022-01-01","2023-12-31"], "metrics": ["LTV_180d","MAU","D30_retention","ARPU"]}

## synthesize_sql
Note: LLM returned empty; sql_scaffold_fallback_used
Generated scaffold SQL:
```
SELECT `order_id`, `user_id`, `status`, `created_at`, `total_price`
FROM `bigquery-public-data.thelook_ecommerce.orders`
LIMIT 10
```

## validate_sql
Validation passed. LIMIT enforced.

## execute_sql
QueryMetrics:
- execution_time: 0.96s
- bytes_processed: 4,661,782
- bytes_billed: 10,485,760
- cache_hit: false

DF summary (rows=10, cols=5)

## analyze_df
Result shape: 10 rows × 5 columns

## report
Insufficient data (strict mode): agent used a SQL scaffold and cannot produce an executive insight.
Columns detected: order_id, user_id, status, created_at, total_price.
Data sample:
{"order_id": "O123", "user_id": "U456", "status": "completed", "created_at": "2022-03-01T12:00:00", "total_price": 59.99}
{"order_id": "O124", "user_id": "U789", "status": "returned", "created_at": "2022-03-02T08:10:00", "total_price": -59.99}

Next steps: ensure the LLM can produce a valid SQL query, include needed joins/aggregations, or disable strict mode to allow provisional insights.

---

Это пример реального запуска с флагом strict; он показывает поведение "stop and explain" при скаффолде.
