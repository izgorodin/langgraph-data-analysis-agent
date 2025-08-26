## LGDA-103 — Programmatic fallback planner (deterministic SQL template)

## Архитектурный контекст
Fallback planner вызывается когда LLM не вернул валидный план. Он должен гарантированно генерировать SQL, удовлетворяющий семантике анализа (кохорты, LTV, фильтры по датам).

## Цель задачи
Реализовать детерминистичный генератор SQL для стандартного сценария cohort-LTV, параметризуемый годами, window, exclusions.

## Детальный анализ
- Шаблон должен принимать параметры: dataset.table names, years (2022-2023), window_days (180), excluded user filters.
- Возвращаемый SQL должен быть совместим с `validate_sql_semantic` и безопасен (read-only, MAX_BYTES_BILLED enforced).

## Критерии приемки
- Integration test: при симуляции пустого LLM ответ возвращается fallback SQL и проходит семантическую проверку.

## Возможные сложности
- Поддержка разных схем таблиц (разные названия колонок) — предусмотреть адаптеры на основе snapshot schema.

## Integration Points
- `src/agent/plan` node
- `src/agent/validate_sql` node
- `src/bq.py` (политики биллинга)

## ADR / ссылки
- Ссылка на ADR: `docs/ADR/fallback-planner.md` (рекомендуется создать).

## Security
- Fallback SQL должен быть read-only и применять лимиты (MAX_BYTES_BILLED) и таблицы-вайтлист.

## Performance
- Генерация шаблона — быстрый локальный шаг; при исполнении SQL соблюдать cost guards.

## Deliverables
- `src/agent/fallback_planner.py` (детерминированный генератор SQL для cohort-LTV с параметрами)
- `tests/integration/test_fallback_planner.py` (интеграционный тест: генерируем SQL -> validate_sql -> execute (mock) -> ожидаем DataFrame нужной формы)

## Acceptance criteria
- Сгенерированный SQL соответствует шаблону (есть cohort, date window, exclusions) и проходит `validate_sql_semantic`.
- SQL помечен read-only и содержит MAX_BYTES_BILLED ограничение.
- Интеграционный тест проходит.

## TDD plan
1. Написать интеграционный тест, который ожидает валидный SQL (структура + параметры).
2. Реализовать генератор SQL с параметрами (years, window_days, exclusions).
3. Прогнать тесты и скорректировать шаблон по результатам.

## Если раздел не применим
- Разделы применимы.

