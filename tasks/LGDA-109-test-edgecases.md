## LGDA-109 — Tests: edge cases для validate_sql и plan node

## Архитектурный контекст
Тесты покрывают критичные edge-cases для узлов планирования и валидации SQL, чтобы предотвратить регрессии при изменениях LLM или схемы данных.

## Цель задачи
Добавить unit tests для случаев: отсутствующие колонки, неоднозначные join'ы, timezone issues и несоответствие структуры плана.

## Детальный анализ
- Сценарии: missing columns в schema snapshot, некорректные типы колонок, пустой LLM plan, ambiguous join keys и timezone offsets для дат.

## Критерии приемки
- Набор тестов обнаруживает регрессии и выполняется в CI; CI падает при регрессии.

## Возможные сложности
- Тесты должны быть детерминистичными; использовать фикстуры и мок-объекты.

## Integration Points
- `tests/unit/` и `tests/integration/`

## ADR / ссылки
- Ссылка на тестовую стратегию в `docs/tests.md`.

## Performance
- Unit tests должны быть быстрыми (<1s по каждому).

## Deliverables
- `tests/unit/test_validate_edgecases.py`
- `tests/unit/test_plan_node_edgecases.py`

## Оценка и приоритет
- Оценка: 6h
- Приоритет: Средний
## LGDA-109 — Tests: edge cases для validate_sql и plan node

Цель
- Покрыть unit tests для критичных edge-cases: отсутствующие колонки, неоднозначные join'ы, timezone issues.

Deliverables
- `tests/unit/test_validate_edgecases.py`
- `tests/unit/test_plan_node_edgecases.py`

Acceptance criteria
- Тесты воспроизводят известные проблемы и защищают код от регрессий.

TDD план
- Сначала написать тесты, затем поправить реализацию в `src/agent`/`src/bq`.

Оценка: 6h
Приоритет: Средний

## Security
- Все тестовые данные должны быть синтетическими и не содержать PII/секретов.
- Unit/integration тесты не должны поднимать реальные credentials в CI; использовать mocks и тестовые секреты, безопасно хранимые в CI.
- Если тесты проверяют SQL, выполнять их в read-only режиме и с MAX_BYTES_BILLED ограничением при необходимости.

## Если раздел не применим
- Раздел применим: безопасность данных важна для тестов, поэтому секция релевантна.
