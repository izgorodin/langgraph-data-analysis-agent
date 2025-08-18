# Бэклог задач

## Обязательные
- [ ] Завести `.env.example` и описать переменные окружения в README
- [ ] Синхронизировать `requirements.txt` с фактическими зависимостями из гайда (sqlglot, click, rich, jinja2, google-generativeai и пр.)
- [ ] Добавить модуль `src/` согласно гайду (config, bq, llm, agent/*, cli.py), если отсутствует
- [ ] Реализовать валидацию SQL через sqlglot (SELECT‑only, whitelist, LIMIT)
- [ ] Ограничить BigQuery `maximum_bytes_billed`, включить `use_query_cache`
- [ ] CLI: флаг `--verbose`, вывод промежуточных состояний
- [ ] Диаграмма в `diagrams/architecture.mmd` (Mermaid) + включить в README
- [ ] README с шагами запуска и примерами запросов

## Тесты и качество
- [ ] Мини‑смоук тест: запрос к BQ с `dry_run=True` (если внедрим) и генерация отчёта по фиктивному DF
- [ ] Линтер/форматтер (ruff/black) — по времени

## Улучшения (опционально)
- [ ] Кеширование схем и результатов
- [ ] Детальные KPI шаблоны для популярных задач
- [ ] Фолбэк на Bedrock
