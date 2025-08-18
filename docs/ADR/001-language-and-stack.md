# ADR 001 — Язык и стек

Дата: 2025-08-18

## Статус
Принято

## Контекст
Задание требует построить кастомного агента на Python с использованием LangGraph, а источником данных выступает BigQuery. LLM предпочтительно Gemini.

## Решение
- Бэкенд: Python 3.10+
- Фреймворк: LangGraph
- Хранилище: Google BigQuery (`bigquery-public-data.thelook_ecommerce`)
- LLM: Google Gemini через библиотеку `google-generativeai`
- Вспомогательные: pandas, sqlglot, click, rich, python-dotenv

## Последствия
- Лёгкая интеграция с BigQuery и Gemini
- Богатая экосистема для анализа данных
- Минимальная зависимость от внешних сервисов, кроме GCP/Google AI
