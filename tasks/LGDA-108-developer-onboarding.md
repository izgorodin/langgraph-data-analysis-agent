## LGDA-108 — Developer guide и TDD checklist для джуниор-разработчика

## Архитектурный контекст
Документ должен помогать новым разработчикам быстро включаться в workflow проекта, соблюдать TDD и стандарты PR/CI.

## Цель задачи
Подготовить пошаговый guide: поднятие `.venv`, запуск тестов, запуск локального pipeline на fixture, PR шаблон и чеклист для TDD.

## Детальный анализ
- Включить команды для macOS/zsh, описание структуры репозитория и ссылки на ключевые модули (`src/agent`, `src/bq`).
- Пример рабочего цикла: написать тест -> make test -> implement -> make format -> make lint -> commit -> PR.

## Критерии приемки
- Документ воспроизводим: новый dev может выполнить `make test` и пройти полный цикл PR по шаблону.

## Возможные сложности
- Различия окружений dev; указать минимальные версии Python/пакетов.

## Integration Points
- Makefile, CI config, `pyproject.toml`.

## ADR / ссылки
- Ссылка на `DEVELOPMENT_INSTRUCTIONS.md` для дополнений.

## Performance
- Документ не влияет на runtime.

## Deliverables
- `tasks/LGDA-108-developer-onboarding.md` с инструкциями и PR-template.

## Оценка и приоритет
- Оценка: 4h
- Приоритет: Средний
## LGDA-108 — Developer guide и TDD checklist для джуниор-разработчика

Цель
- Обеспечить простой и проверяемый набор инструкций для джуниор-разработчика, чтобы он мог выполнять задачи с TDD-подходом.

Deliverables
- `tasks/LGDA-108-developer-onboarding.md` с пошаговыми инструкциями: как поднять `.venv`, запустить тесты, запустить локальный pipeline на fixture, PR-template.
- Пример: walkthrough для LGDA-101 (создать тест -> запустить -> реализовать -> рефактор).

Acceptance criteria
- Документ понятен: новый dev может выполнить `make test` и пройти полный цикл PR по шаблону.

Оценка: 4h
Приоритет: Средний
