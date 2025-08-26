# LangGraph Data Analysis Agent (LGDA)

Production-ready data analysis agent using LangGraph, BigQuery, and Gemini/Bedrock LLMs.

## 🎯 Project Status

Currently in active development following TDD approach. See [tasks/](tasks/) directory for detailed task specifications.

## 🏗️ Architecture

- **Node-based LangGraph Flow**: `plan → synthesize_sql → validate_sql → execute_sql → analyze_df → report`
- **Security-First**: SQL injection prevention, table whitelisting, credential protection
- **Multi-LLM Strategy**: Gemini primary + Bedrock fallback with intelligent switching
- **Production Ready**: Robust error handling, monitoring, configuration management

A CLI agent built with a LangGraph-style pipeline that queries BigQuery’s public dataset `bigquery-public-data.thelook_ecommerce` and produces business insights.

## Features
- LangGraph pipeline: plan → synthesize_sql → validate_sql → execute_sql → analyze_df → report
- BigQuery with safeguards (SELECT-only, whitelisted tables, MAX_BYTES_BILLED, sqlglot)
- Schema-aware prompting via INFORMATION_SCHEMA
- Gemini (google-generativeai) as LLM backend
- CLI with verbose tracing (Rich JSON)

## 🚀 One-liner
Run one command and get a business-ready insight (example):

```bash
.venv/bin/python cli.py --model openai/gpt-oss-120b --verbose "Top 10 products by revenue in last 90 days"
```

## Quickstart (3 steps)
1) Install
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
2) Auth & configure
```bash
# GCP ADC or service account
gcloud auth application-default login
cp .env.example .env
# edit .env to set LGDA_* or legacy vars
```
3) Run
```bash
.venv/bin/python cli.py --model gemini-1.5-pro --verbose "Monthly sales trend by category for 2023"
```

## What to expect (`--verbose`)
The pipeline runs node-by-node and prints each stage when `--verbose` is used:

- `plan` — schema-aware JSON plan (task, tables, metrics)
- `synthesize_sql` — LLM-generated SQL (or scaffold fallback note)
- `validate_sql` — sqlglot validation, LIMIT injection, table whitelist checks
- `execute_sql` — BigQuery execution and `QueryMetrics` (bytes processed, execution_time)
- `analyze_df` — lightweight deterministic analysis of the result set
- `report` — final executive insight (blocked in strict mode if insufficient data)

## Diagram
See `diagrams/architecture.mmd` (Mermaid). A rendered `diagrams/architecture.png` or `svg` is included in the repo for quick viewing.

## Example prompts
- Segment customers by RFM and list top 3 segments with counts and revenue in the last 180 days.
- Monthly sales trend and seasonality by category; highlight months with >2σ deviation.
- Geographic revenue by country and top states; comment on seasonality.

## Notes
- Only SELECT queries are allowed; permitted tables: `orders`, `order_items`, `products`, `users`.
- Non-aggregate queries are auto-limited; set `LGDA_SQL_MAX_LIMIT` (or `MAX_BYTES_BILLED`) to control cost.

## Strict mode (no hallucinations)
Set `LGDA_STRICT_NO_FAKE_REPORT=true` (or `LGDA_STRICT_NO_FAKE_REPORT=1`) to block the agent from producing narrative insights when:

- the LLM returned empty or malformed SQL and a scaffold fallback was used (`sql_scaffold_fallback_used`),
- or when `state.error` is present (validation / execution failure).

In strict mode the `report` node will print an explicit `Insufficient data (strict mode)` message, a small data sample (up to 5 rows), and recommended next steps.

If you prefer provisional insights based on scaffolds, set `LGDA_STRICT_NO_FAKE_REPORT=false`.

## Backends
Supported LLM backends and quick notes:

| Provider | Example model / env | Strengths | Notes |
|---|---|---|---|
| Gemini | `gemini-1.5-pro` (LGDA_GEMINI_API_KEY) | Best for high-quality reasoning; may rate-limit on heavy usage | Consider fallback to OSS or Bedrock on 429s |
| OSS (OpenAI-compatible) | `openai/gpt-oss-120b` (OPENAI_BASE_URL / OPENAI_API_KEY) | Cost-effective local/hosted options | Use `--model openai/gpt-oss-120b` to override |
| Bedrock | `bedrock/*` (AWS creds + LGDA_BEDROCK_REGION) | Enterprise-compatible; good throughput | Requires AWS credentials / region |

Switch via CLI: `--model provider/model` (eg `--model openai/gpt-oss-120b` or `--model gemini-1.5-pro`).
