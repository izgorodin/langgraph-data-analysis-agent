# LGDA-006: Доработка BigQuery-клиента (ретраи, метрики, таймауты, circuit breaker)

LGDA-006

## Архитектурный контекст
Опираясь на ADR 001 (выбор BigQuery), ADR 003 (безопасность SQL) и ADR 004 (LLM fallback), существующий клиент BigQuery обеспечивает базовую функциональность. Для production-grade надёжности нужны доработки по устойчивости и наблюдаемости.

## Цель задачи
Усилить BigQuery-клиент: добавить управляемые ретраи с backoff и jitter, отмену job при таймауте, метрики выполнения, потокобезопасную инициализацию клиента и минимальный circuit breaker. Сохранить совместимость с текущими тестами.

## Детальный анализ
- Retry/Backoff: различать transient (ServerError, RetryError), rate limit (TooManyRequests), permanent (BadRequest/Forbidden/NotFound). Экспоненциальный backoff с jitter, чтение Retry-After при наличии.
- Timeout & Cancellation: при истечении таймаута вызывать job.cancel() и поднимать специализированное исключение.
- Метрики (QueryMetrics): execution_time, bytes_processed, bytes_billed, cache_hit, job_id, row_count. Возвращать через отдельный API или геттер; structured logging.
- Потокобезопасность: lock при ленивой инициализации singleton-клиента.
- Circuit breaker: счётчик сбоев по окну времени и короткая пауза/fast-fail при превышении порога.
- Dry-run: возвращать оценочные bytes_processed в метриках.
- BQ Storage usage: опциональный порог включения create_bqstorage_client=True.
- Исключения: ввести QueryTimeoutError, RateLimitExceededError, TransientQueryError и унифицированное маппирование.

## Критерии приемки
- Ретраи и backoff корректно отрабатывают для transient/rate-limit; permanent не ретраятся.
- Таймаут приводит к job.cancel() и генерации QueryTimeoutError.
- Метрики доступны из внешнего кода и логируются в структурированном виде.
- Синглтон-клиент потокобезопасен под конкурентной инициализацией.
- Circuit breaker активируется при сериях сбоев (покрыт тестами) и снимается после окна восстановления.
- Dry-run возвращает оценку bytes_processed.
- Все текущие тесты остаются зелёными; добавленные unit-тесты на ретраи/таймаут/метрики/брейкер — зелёные.

## Возможные сложности
- Точная классификация ошибок API, корректный учёт Retry-After.
- Нестабильные тесты из-за времени/случайности jitter — использовать детерминированный jitter в тестах.
- Совместимость с существующим публичным API.

## Integration Points
- Связан с LGDA-003 (BigQuery client) и LGDA-006/007 (выполнение запросов в узлах графа и pandas-анализ).
- Влияет на узел execute_sql_node (src/agent/nodes.py) через контракты ошибок/метрик.

## Производительность и наблюдаемость
- Цели: p50 < 1s для маленьких запросов, p95 < 5s; контролируемые ретраи без избыточных задержек.
- Structured logs содержат job_id, elapsed, bytes_processed, cache_hit; метрики пригодны для алертинга.

## Тестовая стратегия
- Unit: тесты на retry/backoff, таймаут+cancel, метрики, потокобезопасность, circuit breaker, dry-run метрики, нормализацию исключений.
- Интеграционные мок-тесты (без реального BQ) на корректную последовательность вызовов и сбор метрик.

## Параллельная разработка и избежание конфликтов с LGDA-005

Чтобы выполнять LGDA-006 параллельно с LGDA-005 (рефакторинг конфигурации), придерживаемся следующих правил:

- Объём изменений:
	- Код: ограничиваемся файлами `src/bq.py` (+ при необходимости новые файлы: `src/bq_errors.py`, `src/bq_metrics.py`).
	- Тесты: добавляем новые в `tests/unit/test_bq_*.py` без правок существующих тестов (кроме явно необходимых стабов/фикстур).
	- CLI/граф/конфиг: не изменяем в рамках LGDA-006; интеграция метрик/флагов — отдельно после мержа LGDA-005.

- Стабильность публичного API на время задачи:
	- Сигнатуры существующих функций (например, `bq_client()`, `run_query(sql: str, ...) -> pd.DataFrame`) не меняем.
	- Новое поведение включаем через необязательные параметры с безопасными значениями по умолчанию и/или фича-флаги из env.
	- Новые исключения наследуем от общего базового (`BigQueryError` или локальный базовый класс) и маппим внутри `run_query` без изменения контрактов вызова.

- Фича-флаги и переменные окружения (временно, до LGDA-005 BaseSettings):
	- `LGDA_BQ_RETRY_ENABLED` (default: `true`)
	- `LGDA_BQ_RETRY_MAX_ATTEMPTS` (default: `3`)
	- `LGDA_BQ_RETRY_BASE_DELAY_MS` (default: `100`)
	- `LGDA_BQ_RETRY_JITTER_MS` (default: `50`)
	- `LGDA_BQ_TIMEOUT_SEC` (default: `30`)
	- `LGDA_BQ_BREAKER_ENABLED` (default: `true`)
	- `LGDA_BQ_BREAKER_FAILURES` (default: `5`)
	- `LGDA_BQ_BREAKER_WINDOW_SEC` (default: `60`)
	- `LGDA_BQ_BREAKER_COOLDOWN_SEC` (default: `20`)
	- `LGDA_BQ_METRICS_ENABLED` (default: `true`)

- Метрики и логирование:
	- Возвращаемые метрики предоставляем через отдельную структуру `QueryMetrics` и/или callback/геттер, не меняя возврат DataFrame.
	- Structured logs только добавляем (ключи: `job_id`, `elapsed_ms`, `bytes_processed`, `cache_hit`, `retries`, `breaker_state`).

- Детерминизм тестов:
	- В тестах инжектируем генератор случайностей/сид для jitter, мокируем время/таймеры/clock для breaker.

- Ветвление и PR-гигиена:
	- Ветка: `feature/lgda-006-bq-hardening` от `main`.
	- Без правок `src/config.py` в этом PR — интеграция с Pydantic Settings выполнится отдельно в LGDA-005.
	- После мержа LGDA-005 сделать короткий follow-up PR, перенеся чтение фич-флагов на новый Settings-слой (без изменения логики).

## Него цели (в рамках LGDA-006)
- Миграция на Pydantic BaseSettings и DI — остаётся в LGDA-005.
- Переписывание CLI или узлов графа под метрики — follow-up после мержа LGDA-005.
- Изменение сигнатур публичных функций BigQuery-клиента.
