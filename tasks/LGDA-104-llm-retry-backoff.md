## LGDA-104 — LLM retry & backoff + empty-response strategy

## Архитектурный контекст
LLM-интеграция в `src/agent/llm.py` должна иметь единый retry-паттерн и детект пустых/невалидных ответов.

## Цель задачи
Реализовать устойчивую политику повторных попыток с backoff и явную стратегию обработки пустых ответов.

## Детальный анализ
- Retry на transient HTTP errors (429, 5xx) с экспоненциальным backoff и jitter.
- Empty body: 1 immediate retry, затем переключение на fallback planner и логирование.

## Критерии приемки
- Unit tests проверяют поведение при 429 и при пустом ответе; метрики (retry_count) эмитятся в логи.

## Возможные сложности
- Настройка таймаутов и пределы retries.

## Integration Points
- `src/agent/llm.py`, observability/metrics

## ADR / ссылки
- ADR: `docs/ADR/llm-retry.md` (если нет — указать в задаче как deliverable).

## Performance
- Retry policy не должен приводить к долгому ожиданию в интерактивных запусках; использовать конфигурируемые лимиты.

## Deliverables
- `src/agent/llm_retry.py` (retry wrapper с экспоненциальным backoff и jitter)
- `tests/unit/test_llm_retry.py` (unit: 429/5xx handling, empty body behavior)

## Acceptance criteria
- Retry с экспоненциальным backoff и jitter применяется для transient errors (429, 5xx).
- При пустом теле происходит 1 immediate retry, затем fallback planner вызывается и это логируется.
- Метрики retry_count логируются в observability.

## TDD plan
1. Написать тест для поведения при 429/5xx (эмулировать ответы).
2. Написать тест для пустого тела -> ожидаем fallback вызов.
3. Реализовать обёртку и убедиться, что тесты зелёные.

## Если раздел не применим
- Разделы применимы.

