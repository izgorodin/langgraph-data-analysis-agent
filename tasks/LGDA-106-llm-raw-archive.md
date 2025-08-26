## LGDA-106 — Capture & persist raw LLM responses + observability

Цель

Deliverables

Acceptance criteria

TDD план

Оценка: 3h
Приоритет: Средний
## LGDA-106 — Capture & persist raw LLM responses + observability

## Архитектурный контекст
Архивирование raw LLM-ответов важно для post-mortem и детектирования причин пустых/невалидных ответов. Хранить в локальном/облачном хранилище, верифицируемо.

## Цель задачи
Реализовать persist-слой для raw LLM responses с минимальной мета-информацией: model, prompt_hash, timestamp, response_text.

## Детальный анализ
- Формат: JSON-файлы с именем по timestamp+hash или append в ротационный лог.
- Интерфейс: `archive_response(metadata: dict, raw_response: str)`.

## Критерии приемки
- Unit test подтверждает создание файла и корректность полей (model, prompt_hash, timestamp).

## Возможные сложности
- Управление объёмом логов; предусмотреть ротацию/удаление старых записей.

## Integration Points
- `src/agent/llm.py` (в точке получения ответа)
- observability stack/metrics

## ADR / ссылки
- Ссылка на ADR: `docs/ADR/observability.md` (если есть).

## Performance
- Архивирование должно быть быстрым и неблокирующим; можно писать асинхронно.

## Deliverables
- `src/observability/llm_archive.py` (функция `archive_response(metadata, raw_response)`)
- `tests/unit/test_llm_archive.py`

## Acceptance criteria
- Raw responses сохраняются в локальный append-only лог/ротационный каталог с полями: model, prompt_hash, timestamp, response_text.
- Unit-тесты подтверждают формат и консистентность записей.

## TDD plan
1. Написать unit-тест на создание/чтение записи архива.
2. Реализовать функцию `archive_response` и сохранить в JSON-lines файл с ротацией по размеру/дню.
3. Прогнать тесты и подтвердить поведение.

## Если раздел не применим
- Все секции применимы.
