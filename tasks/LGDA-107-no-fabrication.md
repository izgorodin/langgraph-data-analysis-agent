## LGDA-107 — Guardrails: prevent fabricated reports on LLM failure

## Архитектурный контекст
На уровне reporting pipeline должен гарантировать наличие доказательств (evidence) — таблицы/метрик — перед генерацией повествовательного отчёта LLM. Это уменьшает риск фабрикации и повышает доверие к итогам.

## Цель задачи
Добавить явный guardrail: если evidence отсутствует или недостаточно, pipeline возвращает structured error и не запрашивает у LLM генерацию интерпретаций.

## Детальный анализ
- Evidence: non-empty df_summary с ожидаемыми колонками и key_metrics (MAU, LTV, ARPU) с ненулевыми значениями.
- Поведение: при отсутствии evidence report node возвращает {status: "no-evidence", message: "Insufficient data for analysis"}.

## Критерии приемки
- Unit tests: valid evidence -> report generated; missing evidence -> explicit error and no LLM call.

## Возможные сложности
- Определение порога достаточности evidence (н-р, 1 строка vs 0 строк).

## Integration Points
- `src/agent/reporting.py`
- `src/agent/analyze_df.py`

## ADR / ссылки
- Рекомендуется добавить ADR `docs/ADR/no-fabrication.md` описывающий policy.

## Performance
- Проверки evidence — O(1) структурные проверки, не влияют на производительность.

## Deliverables
- Код в `src/agent/reporting.py`.
- Unit tests: `tests/unit/test_reporting_no_fabrication.py`.

## Оценка и приоритет
- Оценка: 4h
- Приоритет: Высокий
## LGDA-107 — Guardrails: prevent fabricated reports on LLM failure

Цель
- Гарантировать, что при отсутствии доказательной статистики pipeline не возвращает сгенерированный/фабрикованный отчёт.

Deliverables
- Обновление `src/agent/reporting.py` с флагом `report.must_include_evidence` и проверкой доказательств (exists: df_summary, key_metrics).
- Unit tests: `tests/unit/test_reporting_no_fabrication.py`.

Acceptance criteria
- Если итоговый отчёт не содержит доказательств (таблицы, метрики), вернётся явное сообщение об ошибке, а не сочинённый текст.

TDD план
- Тесты: case where only a DF with wrong shape exists -> pipeline returns explicit error message.

Оценка: 4h
Приоритет: Высокий
