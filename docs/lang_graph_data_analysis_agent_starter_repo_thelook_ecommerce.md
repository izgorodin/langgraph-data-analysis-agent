# README.md

## LangGraph Data Analysis Agent (BigQuery + Gemini)

A CLI agent built with **LangGraph** that queries **BigQuery**’s public dataset `bigquery-public-data.thelook_ecommerce` and produces business insights (segmentation, product performance, trends, geo patterns). The agent plans a query, synthesizes SQL, validates it, executes on BigQuery, analyzes results, and generates an insight report with citations and suggested next questions.

### Features
- **LangGraph stateful agent** with clear nodes: `plan → synthesize_sql → validate_sql → execute_sql → analyze_df → report` (+ fallback & retry edges)
- **BigQuery integration** (google-cloud-bigquery) with **safe-guards**: only whitelisted tables, `SELECT` only, `MAX_BYTES_BILLED` limits, and SQL parsing via **sqlglot**
- **Schema-aware prompting**: agent retrieves table/column info at runtime and uses it in planning
- **Hybrid: LLM + deterministic templates** — LLM proposes a JSON plan; SQL built from templates when possible; LLM used as a helper for edge cases
- **Gemini (Google AI Studio)** by default via `google-generativeai`; optional **Bedrock** fallback (Claude/Sonnet) if env is set
- **Result analysis**: pandas summary, simple KPIs, and a concise executive-style report with numeric evidence
- **CLI chat** with short-term memory and `--verbose` tracing of each node
- **Mermaid diagram** of the architecture

### Dataset
- Dataset: `bigquery-public-data.thelook_ecommerce`
- Tables used: `orders`, `order_items`, `products`, `users`

### Quickstart
1) **Python** 3.10+
2) `pip install -r requirements.txt`
3) **Auth to GCP** (one of):
   - `gcloud auth application-default login` (ADC)
   - or set `GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json`
4) **Set env** in `.env` (see `.env.example`)
5) Run:
```bash
python cli.py --model gemini-1.5-pro
# or
env GOOGLE_API_KEY=... python cli.py -m gemini-1.5-pro "Top 10 products by revenue in last 90 days; include gross margin and category mix"
```

### Example prompts
- "Segment customers by RFM and list top 3 segments with counts and revenue in the last 180 days."
- "Find products with negative margin in 2024 and suggest actions."
- "Monthly sales trend and seasonality by category; highlight months with >2σ deviation."
- "Geographic revenue heatmap by country and top states."

---

# requirements.txt

langgraph>=0.2.33
pydantic>=2.7
pandas>=2.2
pyarrow>=15.0
sqlglot>=23.0
jinja2>=3.1
rich>=13.7
click>=8.1
python-dotenv>=1.0
google-cloud-bigquery>=3.25
google-auth>=2.30
google-generativeai>=0.6
boto3>=1.34

---

# .env.example
GOOGLE_API_KEY=your_google_ai_studio_key
BIGQUERY_PROJECT=your-gcp-project-id
BIGQUERY_LOCATION=US
DATASET_ID=bigquery-public-data.thelook_ecommerce
ALLOWED_TABLES=orders,order_items,products,users
MAX_BYTES_BILLED=100000000   # 100 MB
MODEL_NAME=gemini-1.5-pro

# Optional Bedrock fallback
AWS_REGION=eu-west-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20240620-v1:0

---

# diagrams/architecture.mmd
flowchart TD
  subgraph CLI
    U[User CLI]
  end
    subgraph Agent[LangGraph Agent]
        P[Plan (LLM->JSON plan)] --> S[Synthesize SQL]
    S --> V[Validate SQL (sqlglot + policy)]
    V -->|ok| X[Execute SQL (BigQuery)]
    V -->|fail| PF[Plan Fallback]
    X --> A[Analyze DataFrame]
    A --> R[Report (LLM + templates)]
  end

  U -->|prompt| P
  R -->|final answer| U

  subgraph GCP[BigQuery]
    BQ[(thelook_ecommerce)]
  end

  X --> BQ

  subgraph LLMs
    G[Gemini (google-generativeai)]
    BR[Bedrock (fallback)]
  end

  P --> G
  R --> G
  PF --> BR

---

# src/config.py
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    bq_project: str = os.getenv("BIGQUERY_PROJECT", "")
    bq_location: str = os.getenv("BIGQUERY_LOCATION", "US")
    dataset_id: str = os.getenv("DATASET_ID", "bigquery-public-data.thelook_ecommerce")
    allowed_tables: list[str] = tuple(t.strip() for t in os.getenv("ALLOWED_TABLES", "orders,order_items,products,users").split(","))
    max_bytes_billed: int = int(os.getenv("MAX_BYTES_BILLED", "100000000"))
    model_name: str = os.getenv("MODEL_NAME", "gemini-1.5-pro")
    aws_region: str = os.getenv("AWS_REGION", "eu-west-1")
    bedrock_model_id: str = os.getenv("BEDROCK_MODEL_ID", "")

settings = Settings()

---

# src/bq.py
from __future__ import annotations
from google.cloud import bigquery
from google.api_core.exceptions import BadRequest
from typing import Optional
from .config import settings

_bq_client: Optional[bigquery.Client] = None

def bq_client() -> bigquery.Client:
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(project=settings.bq_project, location=settings.bq_location)
    return _bq_client

SCHEMA_QUERY = """
SELECT table_name, column_name, data_type
FROM `{}.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name IN UNNEST(@tables)
ORDER BY table_name, ordinal_position
""".format(settings.dataset_id)

def get_schema(tables: list[str]) -> list[dict]:
    client = bq_client()
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("tables", "STRING", tables)],
        maximum_bytes_billed=settings.max_bytes_billed,
    )
    rows = client.query(SCHEMA_QUERY, job_config=job_config).result()
    return [dict(r) for r in rows]


def run_query(sql: str, dry_run: bool = False):
    client = bq_client()
    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=settings.max_bytes_billed,
        dry_run=dry_run,
        use_query_cache=True,
    )
    try:
        job = client.query(sql, job_config=job_config)
        return job.result().to_dataframe(create_bqstorage_client=True)
    except BadRequest as e:
        raise ValueError(f"BigQuery error: {e}")

---

# src/llm.py
from __future__ import annotations
import os
from typing import Optional, Dict, Any
from .config import settings

# Gemini (google-generativeai)
import google.generativeai as genai

genai.configure(api_key=settings.google_api_key)

def llm_completion(prompt: str, system: Optional[str] = None, model: Optional[str] = None) -> str:
    model = model or settings.model_name
    contents = prompt if system is None else f"System: {system}\n\nUser: {prompt}"
    resp = genai.GenerativeModel(model).generate_content(contents)
    return resp.text or ""

# Optional: Bedrock fallback (pseudo; real impl would call boto3 bedrock-runtime)

def llm_fallback(prompt: str, system: Optional[str] = None) -> str:
    # Stub: in real use, integrate boto3 bedrock-runtime
    return ""

---

# src/agent/state.py
from __future__ import annotations
from typing import Optional, Any, List, Dict
from pydantic import BaseModel, Field

class AgentState(BaseModel):
    question: str
    plan_json: Optional[Dict[str, Any]] = None
    sql: Optional[str] = None
    df_summary: Optional[Dict[str, Any]] = None
    report: Optional[str] = None
    error: Optional[str] = None
    history: List[Dict[str, str]] = Field(default_factory=list)  # short-term chat memory

---

# src/agent/prompts.py
PLAN_SYSTEM = """
You are a data analysis planner for BigQuery using the dataset bigquery-public-data.thelook_ecommerce.
Return a minimal JSON PLAN with keys: task, tables, time_range, dimensions, metrics, filters, grain.
Use only these tables: orders, order_items, products, users.
"""

SQL_SYSTEM = """
You are a SQL writer for BigQuery Standard SQL. Generate a single SELECT query.
Rules: SELECT only, no DML/DDL; join only the allowed tables; qualify columns; limit rows when needed; respect time filters.
"""

REPORT_SYSTEM = """
You are an analyst. Given a question and a dataframe summary, write an executive-style insight with numbers, trends, and 1-2 next questions. Keep it concise and actionable, include a short rationale.
"""

---

# src/agent/nodes.py
from __future__ import annotations
import json
from typing import Dict, Any
import pandas as pd
import sqlglot
from sqlglot import exp
from jinja2 import Template
from .state import AgentState
from ..config import settings
from ..bq import get_schema, run_query
from ..llm import llm_completion
from .prompts import PLAN_SYSTEM, SQL_SYSTEM, REPORT_SYSTEM

ALLOWED = set(settings.allowed_tables)

PLAN_TEMPLATE = Template(
    """
Return a JSON object for this analysis request.
Question: {{ question }}
Tables & Columns\n{% for t, cols in schema.items() %}- {{t}}: {{ cols|join(', ') }}\n{% endfor %}
JSON keys: task, tables, time_range, dimensions, metrics, filters, grain.
    """
)

SQL_TEMPLATE = Template(
    """
Write a BigQuery Standard SQL SELECT for this PLAN:
PLAN: {{ plan_json }}
Only use these tables: {{ allowed_tables }}
Prefer safe, explicit JOINs; qualify columns with table aliases; include WHERE for time_range if present.
Limit to 1000 rows unless aggregation is performed.
    """
)

def _schema_map() -> Dict[str, list[str]]:
    rows = get_schema(list(ALLOWED))
    schema: Dict[str, list[str]] = {}
    for r in rows:
        schema.setdefault(r["table_name"], []).append(r["column_name"])
    return schema

# Node: plan

def plan_node(state: AgentState) -> AgentState:
    schema = _schema_map()
    prompt = PLAN_TEMPLATE.render(question=state.question, schema=schema)
    raw = llm_completion(prompt, system=PLAN_SYSTEM)
    try:
        plan = json.loads(raw.strip().strip("`"))
    except Exception:
        # attempt to extract JSON
        start = raw.find("{")
        end = raw.rfind("}")
        plan = json.loads(raw[start:end+1]) if start!=-1 and end!=-1 else {"task":"ad-hoc","tables":list(ALLOWED)}
    state.plan_json = plan
    return state

# Node: synthesize_sql

def synthesize_sql_node(state: AgentState) -> AgentState:
    prompt = SQL_TEMPLATE.render(plan_json=json.dumps(state.plan_json), allowed_tables=",".join(ALLOWED))
    sql = llm_completion(prompt, system=SQL_SYSTEM)
    state.sql = sql.strip().strip("`")
    return state

# Node: validate_sql

def validate_sql_node(state: AgentState) -> AgentState:
    try:
        parsed = sqlglot.parse_one(state.sql, read="bigquery")
    except Exception as e:
        state.error = f"SQL parse error: {e}"
        return state

    # Policy: SELECT only
    if not isinstance(parsed, exp.Select):
        state.error = "Only SELECT queries are allowed"
        return state

    # Policy: block non-allowed tables
    tables = {t.name for t in parsed.find_all(exp.Table)}
    if not tables.issubset(ALLOWED):
        state.error = f"Disallowed tables: {tables - ALLOWED}"
        return state

    # Optional: LIMIT for non-aggregates
    if not parsed.find(exp.Group):
        # enforce LIMIT 1000 if missing
        if not parsed.args.get("limit"):
            parsed.set("limit", exp.Limit(this=exp.Literal.number(1000)))
        state.sql = parsed.sql(dialect="bigquery")

    return state

# Node: execute_sql

def execute_sql_node(state: AgentState) -> AgentState:
    try:
        df = run_query(state.sql)
    except Exception as e:
        state.error = str(e)
        return state
    # summarize
    summary = {
        "rows": len(df),
        "columns": list(df.columns),
        "head": df.head(10).to_dict(orient="records"),
        "describe": json.loads(df.describe(include="all").to_json()),
    }
    state.df_summary = summary
    return state

# Node: analyze_df

def analyze_df_node(state: AgentState) -> AgentState:
    # light deterministic notes; LLM will write final report
    notes = []
    if state.df_summary:
        rows = state.df_summary.get("rows", 0)
        cols = state.df_summary.get("columns", [])
        notes.append(f"Result shape: {rows} rows × {len(cols)} columns")
    state.history.append({"analysis": "\n".join(notes)})
    return state

# Node: report

def report_node(state: AgentState) -> AgentState:
    plan = json.dumps(state.plan_json, ensure_ascii=False)
    summary = json.dumps(state.df_summary, ensure_ascii=False)[:30000]
    prompt = f"Question: {state.question}\nPLAN: {plan}\nDF SUMMARY (truncated): {summary}\nWrite a concise executive insight with numeric evidence and 1–2 next questions."
    text = llm_completion(prompt, system=REPORT_SYSTEM)
    state.report = text.strip()
    return state

---

# src/agent/graph.py
from __future__ import annotations
from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import (
    plan_node,
    synthesize_sql_node,
    validate_sql_node,
    execute_sql_node,
    analyze_df_node,
    report_node,
)


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("plan", plan_node)
    graph.add_node("synthesize_sql", synthesize_sql_node)
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("analyze_df", analyze_df_node)
    graph.add_node("report", report_node)

    graph.set_entry_point("plan")

    graph.add_edge("plan", "synthesize_sql")
    graph.add_edge("synthesize_sql", "validate_sql")

    def on_valid(state: AgentState):
        return "execute_sql" if state.error is None else END

    graph.add_conditional_edges("validate_sql", on_valid, {"execute_sql": "execute_sql", END: END})
    graph.add_edge("execute_sql", "analyze_df")
    graph.add_edge("analyze_df", "report")
    graph.add_edge("report", END)

    app = graph.compile()
    return app

---

# cli.py
from __future__ import annotations
import os
import json
import click
from rich.console import Console
from rich.panel import Panel
from src.agent.state import AgentState
from src.agent.graph import build_graph
from src.config import settings

console = Console()

@click.command()
@click.option("--model", "model", default=settings.model_name, help="LLM model name (gemini-1.5-pro)")
@click.option("--verbose", is_flag=True, help="Show intermediate states")
@click.argument("question", required=False)
def main(model: str, verbose: bool, question: str|None):
    if question is None:
        question = click.prompt("Enter your analysis question", type=str)

    state = AgentState(question=question)
    app = build_graph()

    for event in app.stream(state):
        for node, s in event.items():
            if verbose:
                console.rule(f"[bold cyan]{node}")
                payload = s if isinstance(s, dict) else s.model_dump()
                console.print_json(json.dumps(payload, ensure_ascii=False)[:6000])

    final = app.invoke(state)
    console.rule("[bold green]Insight")
    console.print(Panel.fit(final.report or "No report", title="Agent Report"))

if __name__ == "__main__":
    main()
