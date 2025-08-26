## LGDA-102 — Семантическая валидация SQL (validate_sql расширение)

## Архитектурный контекст
`validate_sql` сейчас проверяет синтаксис и политики безопасности. Нужно расширить проверки на семантику, чтобы гарантировать выполнение бизнес-логики (кохорт/временные окна/агрегации).

## Цель задачи
Реализовать дополнительный шаг валидации SQL, который выявляет отсутствие обязательных бизнес-компонентов в запросе.

## Детальный анализ
- Корректность определяется наличием: фильтра по датам (например, WHERE created_at BETWEEN ...), вычисления first_order_date/first_order_month, window для LTV (например, date BETWEEN first_order AND first_order + INTERVAL 180 DAY), агрегатов.
- Инструменты: `sqlglot` для AST анализа; fallback на regex для простых эвристик.

## Критерии приемки
- Unit tests: положительный и несколько негативных кейсов (missing date filter, missing cohort logic, suspicious full-table-scan).
- В случае несоответствия — возвращать детальную ошибку и рекомендованный fix.

## Возможные сложности
- False positives при сложных динамических SQL.
- Точность при разных синтаксисах SQL и моделях генерации.

## Integration Points
- `src/agent/validate_sql` node
- `src/agent/fallback_planner.py` (вызов при провале)

## ADR / ссылки
- Ссылка на ADR: `docs/ADR/sql-validation.md` (если есть).

## Security
- Любые SQL-валидации не должны раскрывать секреты. Проверки должны быть read-only и не выполнять SQL.

## Performance
- Анализ AST должна быть парой миллисекунд на средних по размеру строк запросах.

## Deliverables
- `src/agent/validate_sql_semantic.py` (AST + heuristics для выявления пропущенных фильтров/кохортной логики)
- `tests/unit/test_validate_sql_semantic.py` (unit: missing date filter, missing cohort logic, suspicious full-table-scan)

## Acceptance criteria
- Валидатор обнаруживает отсутствие фильтра по дате/кохортной логики и возвращает понятный error с remediation hint.
- False-positive rate минимален (отслеживается через метрики тестовой выборки).
- Тесты проходят локально (`make test`).

## TDD plan
1. Написать юнит-тесты для кейсов: missing date filter, missing cohort aggregation, large-scan pattern.
2. Реализовать проверку через `sqlglot` AST + регексы как fallback.
3. Запустить тесты и отладить ложные срабатывания на примерах.

## Если раздел не применим
- Разделы применимы.

