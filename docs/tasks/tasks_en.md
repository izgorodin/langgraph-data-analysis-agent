# Execution Backlog (EN)

## Foundation
- [ ] Create `.env.example` with: GOOGLE_API_KEY, BIGQUERY_PROJECT, BIGQUERY_LOCATION, DATASET_ID, ALLOWED_TABLES, MAX_BYTES_BILLED, MODEL_NAME, (optional) AWS_REGION, BEDROCK_MODEL_ID
- [ ] Align `requirements.txt` with code (langgraph, pydantic, pandas, pyarrow, sqlglot, jinja2, rich, click, python-dotenv, google-cloud-bigquery, google-auth, google-generativeai)
- [ ] Add package structure under `src/` with modules: `config.py`, `bq.py`, `llm.py`, `agent/state.py`, `agent/prompts.py`, `agent/nodes.py`, `agent/graph.py`, and top-level `cli.py`

## BigQuery & Security
- [ ] Implement `bq_client()`, `get_schema()`, `run_query()` with `maximum_bytes_billed` and `use_query_cache`
- [ ] Enforce SELECT-only, whitelisted tables (orders, order_items, products, users)
- [ ] Use `sqlglot` to parse/validate SQL; add `LIMIT 1000` for non-aggregated selects

## LangGraph Pipeline
- [ ] Node `plan`: produce JSON plan (task, tables, time_range, dimensions, metrics, filters, grain), make it schema-aware
- [ ] Node `synthesize_sql`: generate BigQuery Standard SQL from plan using templates + LLM
- [ ] Node `validate_sql`: parse, enforce policies, rewrite LIMIT if needed
- [ ] Node `execute_sql`: run query in BigQuery, return DataFrame, handle errors
- [ ] Node `analyze_df`: summarize DataFrame (shape, head, describe)
- [ ] Node `report`: produce concise executive insight with numeric evidence and 1–2 next steps

## CLI & UX
- [ ] Click-based CLI: accept `question` arg, `--model` option, `--verbose` flag
- [ ] Verbose mode prints JSON for each node’s state via Rich
- [ ] README with quickstart, example prompts, and diagram

## Documentation & Diagrams
- [ ] ADRs for stack, graph architecture, SQL security, LLM provider/fallback, CLI/tracing, schema context
- [ ] Mermaid diagram `diagrams/architecture.mmd` and link in README

## Quality & Tests
- [ ] Smoke test flow: trivial query → SQL validated → BigQuery dry run (optional) → mocked DataFrame summary → report
- [ ] Basic error handling for SQL parse errors, BigQuery BadRequest, empty results
- [ ] Optional: add Ruff/Black configuration and pre-commit hooks

## Enhancements (Optional)
- [ ] Cache table schemas and/or results by question hash (with TTL)
- [ ] Deterministic KPI templates for common asks (e.g., top-N products, monthly trends)
- [ ] Bedrock fallback implementation using boto3
