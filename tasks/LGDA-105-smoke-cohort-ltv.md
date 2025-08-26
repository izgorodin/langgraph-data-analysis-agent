## LGDA-105 — Smoke test harness для cohort-LTV flow

- Создать тестовый хаб для быстрого прогонки пайплайна на небольшом fixture и проверки итоговой формы (cohort_month, product_category, ltv_180, mau, d30_retention, arpu).
- Fixture: `tests/fixtures/cohort_ltv_sample.csv` (маленький набор данных).

- Pipeline на fixture возвращает DataFrame с нужными столбцами и простыми числовыми assert'ами (напр., суммарный LTV совпадает с ожидаемым).

## LGDA-105 — Smoke test harness для cohort-LTV flow

## Архитектурный контекст
Smoke test интегрируется в pipeline `plan -> synthesize_sql -> validate_sql -> execute_sql -> analyze_df` и служит быстрым сигналом регрессий для аналитических запросов.

## Цель задачи
Обеспечить repeatable fixture и интеграционный тест, который валидирует форму и ключевые метрики для cohort-LTV анализа.

## Детальный анализ
- Fixture должен покрывать: first_order_date распределённый по месяцам 2022-2023, возвраты (returned_at), скидки (sale_price vs retail_price), несколько product_category.
- Тест проверяет наличие колонок: `cohort_month, product_category, ltv_180, mau, d30_retention, arpu` и несколько контрольных сумм.

## Критерии приемки
- Тест проходит локально и в CI; возвращаемый DF содержит обязательные колонки и контрольные суммы совпадают с ожидаемыми в fixture.

## Возможные сложности
- Нужен простой mapper для соответствия имен колонок в fixture и production schema.

## Integration Points
- `src/agent/analyze_df.py` (или эквивалент)
- `tests/integration/test_cohort_ltv_pipeline.py`

## ADR / ссылки
- Тестовая стратегия и fixture описываются в `docs/tests.md` (или добавить при необходимости).

## Performance
- Fixture и тесты должны выполняться быстро (<5s) для CI-разработки.

## Deliverables
- `tests/fixtures/cohort_ltv_sample.csv` (fixture)
- `tests/integration/test_cohort_ltv_pipeline.py` (smoke test for pipeline)

## Acceptance criteria
- Smoke test прогоняется в CI и проверяет, что pipeline возвращает DataFrame с колонками `cohort_month, product_category, ltv_180, mau, d30_retention, arpu`.
- Тест стабильный и выполняется <5s в CI окружении.

## TDD plan
1. Создать fixture CSV с контролируемыми значениями.
2. Написать интеграционный тест, который подставляет fixture и проверяет агрегаты.
3. Инструментировать pipeline для поддержки локального запуска на fixture.

## Security
- Фикстуры не должны содержать реальных PII или продакшн-credentials; использовать синтетические данные.
- Тесты/Smoke-run должны выполнять только read-only запросы; при интеграционных запусках применять MAX_BYTES_BILLED и whitelist таблиц.
- Не логировать чувствительные поля; если сохраняется пример результата, маскировать/хешировать PII.

## Если раздел не применим
- Все разделы применимы для smoke-test задачи.

## Оценка и приоритет
- Оценка: 1 day
- Приоритет: Высокий
- Сначала создать fixture и тест, ожидающий fail. Реализовать минимальную pipeline логику или использовать fallback SQL для прохождения теста.

Оценка: 1 day
Приоритет: Высокий
