# LangGraph Data Analysis Agent (LGDA)

Production-ready data analysis agent using LangGraph, BigQuery, and Gemini/Bedrock LLMs.

## 🎯 Project Status

Currently in active development following TDD approach. See [tasks/](tasks/) directory for detailed task specifications.

## 🏗️ Architecture

- **Node-based LangGraph Flow**: `plan → synthesize_sql → validate_sql → execute_sql → analyze_df → report`
- **Security-First**: SQL injection prevention, table whitelisting, credential protection
- **Multi-LLM Strategy**: Gemini primary + Bedrock fallback with intelligent switching
- **Production Ready**: Robust error handling, monitoring, configuration managementh Data Analysis Agent (BigQuery + Gemini)

A CLI agent built with LangGraph that queries BigQuery’s public dataset `bigquery-public-data.thelook_ecommerce` and produces business insights.

## Features
- LangGraph pipeline: plan → synthesize_sql → validate_sql → execute_sql → analyze_df → report
- BigQuery with safeguards (SELECT-only, whitelisted tables, MAX_BYTES_BILLED, sqlglot)
- Schema-aware prompting via INFORMATION_SCHEMA
- Gemini (google-generativeai) as LLM backend
- CLI with verbose tracing (Rich JSON)

## Quickstart
1) Python 3.10+
2) Install deps
```bash
pip install -r requirements.txt
```
3) Auth to GCP (choose one)
```bash
# Application Default Credentials
gcloud auth application-default login
# or service account key
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```
4) Configure env
```bash
cp .env.example .env
# fill variables: BIGQUERY_PROJECT, GOOGLE_API_KEY, etc.
```
5) Run
```bash
python cli.py --model gemini-1.5-pro --verbose "Top 10 products by revenue in last 90 days"
```

## Diagram
See `diagrams/architecture.mmd` (Mermaid).

## Example prompts
- Segment customers by RFM and list top 3 segments with counts and revenue in the last 180 days.
- Monthly sales trend and seasonality by category; highlight months with >2σ deviation.
- Geographic revenue by country and top states; comment on seasonality.

## Notes
- Only SELECT queries against: orders, order_items, products, users.
- Limit enforced for non-aggregate queries; MAX_BYTES_BILLED set via env.
