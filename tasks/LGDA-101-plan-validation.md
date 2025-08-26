## LGDA-101 — Валидация JSON-плана LLM (plan node)

## Архитектурный контекст
Этот узел находится в `src/agent` и отвечает за преобразование естественноязычного запроса в структурированный план (JSON). Ошибки на этом этапе приводят к неверной генерации SQL и ложным отчётам.

## Цель задачи
Надёжно детектировать пустые/невалидные/неполные JSON-ответы от LLM и ввести deterministic поведение: логирование, retry или программный fallback.

## Детальный анализ
- Требуемая структура плана: поля `intent`, `tables`, `cohort_spec`, `date_range`, `metrics`.
- Поведение при ошибке: логировать raw ответ, возвращать ясную ошибку для мониторинга и запускать fallback при повторной ошибке.

## Критерии приемки
- Unit tests покрывают happy-path, empty-response и malformed-json.
- При пустом/невалидном JSON — node возвращает error code и raw ответ сохраняется в лог.

## Возможные сложности
- Разные версии LLM возвращают неконсистентный JSON (нужны retries и сохранение raw).
- Баланс между retry и быстрым fallback.

## Integration Points
- `src/agent/llm.py` (вызов LLM)
- `src/agent/nodes.py` (plan node)
- observability (логи/metrics)

## ADR / ссылки
- Ссылка на ADR: `docs/ADR/llm-plan-format.md` (если есть) — добавить ссылку или пометку.

## Performance
- Валидация должна быть лёгкой (строчные проверки + json schema), не добавлять существенной задержки.

## Deliverables
- `src/agent/plan_validation.py` (реализация проверки схемы плана + helper для логирования raw LLM ответов)
- `tests/unit/test_plan_validation.py` (unit: happy path, empty-response, malformed-json)

## Acceptance criteria
- Валидатор принимает корректный JSON по схеме и возвращает success.
- При пустом/мalformed JSON валидатор возвращает structured error и логирует raw LLM-ответ.
- Юнит-тесты проходят локально (`make test`).

## TDD plan
1. Написать тест на корректный JSON -> ожидать success.
2. Написать тест на пустой ответ -> ожидать structured error и запись в лог.
3. Реализовать минимальную функцию в `src/agent/plan_validation.py` и прогонять тесты до зелёного.

## Security
- План-валидатор не должен логировать секреты (API-keys, credentials). Любые raw-ответы LLM должны быть redacted/hashed для полей, которые выглядят как секреты.
- Если план приводит к генерации SQL, обеспечить read-only режим выполнения и whitelist таблиц; применять MAX_BYTES_BILLED ограничение при выполнении в BQ.
- Логи должны исключать PII; при необходимости сохранять только хеши/prompt_hash.

## Если раздел не применим
- Нет неприменимых разделов для этой задачи: все указанные секции актуальны.

