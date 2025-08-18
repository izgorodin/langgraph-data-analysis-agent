from __future__ import annotations

import json
from typing import Any, Dict

import pandas as pd
import sqlglot
from jinja2 import Template
from sqlglot import exp

from ..bq import get_schema, run_query
from ..config import settings
from ..llm import llm_completion
from .prompts import PLAN_SYSTEM, REPORT_SYSTEM, SQL_SYSTEM
from .state import AgentState

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
        plan = (
            json.loads(raw[start : end + 1])
            if start != -1 and end != -1
            else {"task": "ad-hoc", "tables": list(ALLOWED)}
        )
    state.plan_json = plan
    return state


# Node: synthesize_sql


def synthesize_sql_node(state: AgentState) -> AgentState:
    prompt = SQL_TEMPLATE.render(
        plan_json=json.dumps(state.plan_json), allowed_tables=",".join(ALLOWED)
    )
    sql = llm_completion(prompt, system=SQL_SYSTEM)
    state.sql = sql.strip().strip("`")
    return state


# Node: validate_sql


def validate_sql_node(state: AgentState) -> AgentState:
    """Enhanced SQL validation with comprehensive security checks."""
    
    # Pre-parsing security checks
    try:
        _check_injection_patterns(state.sql)
        _check_multi_statement(state.sql)
    except Exception as e:
        state.error = str(e)
        return state
    
    # Parse SQL
    try:
        parsed = sqlglot.parse_one(state.sql, read="bigquery")
    except Exception as e:
        state.error = f"SQL parse error: {e}"
        return state

    # Handle empty/invalid parsed results
    if parsed is None:
        state.error = "Invalid or empty SQL query"
        return state

    # Policy: SELECT only
    if not isinstance(parsed, exp.Select):
        state.error = "Only SELECT queries are allowed"
        return state

    # Policy: block non-allowed tables
    tables = {t.name for t in parsed.find_all(exp.Table)}
    
    # Filter out CTE names - they are virtual tables, not real tables
    cte_names = set()
    for cte in parsed.find_all(exp.CTE):
        if hasattr(cte, 'alias') and cte.alias:
            cte_names.add(str(cte.alias))
    
    # Remove CTE names from table validation
    real_tables = tables - cte_names
    
    if not real_tables.issubset(ALLOWED):
        state.error = f"Disallowed tables: {real_tables - ALLOWED}"
        return state

    # Enhanced aggregation detection for LIMIT injection
    has_aggregation = _has_aggregation(parsed)
    
    # Optional: LIMIT for non-aggregates
    if not has_aggregation:
        # enforce LIMIT 1000 if missing
        if not parsed.args.get("limit"):
            parsed.set("limit", exp.Limit(this=exp.Literal.number(1000)))
        state.sql = parsed.sql(dialect="bigquery")

    return state


def _check_injection_patterns(sql: str) -> None:
    """Check for common SQL injection patterns."""
    sql_lower = sql.lower().strip()
    
    # Check for multi-statement indicators
    if ';' in sql and not sql.strip().endswith(';'):
        # Remove string literals to avoid false positives with semicolons in strings
        cleaned_sql = _remove_strings_and_comments(sql)
        if ';' in cleaned_sql and not cleaned_sql.strip().endswith(';'):
            raise ValueError("Multi-statement SQL detected - potential injection attempt")
    
    # Check for comment-based injection patterns (but allow trailing comments)
    if '/*' in sql or '*/' in sql:
        raise ValueError("Multi-line comments not allowed - potential injection")
    
    # Check for single-line comments not at the end
    if '--' in sql:
        comment_pos = sql.find('--')
        # Allow comments only if they're at the end and not followed by more SQL
        remaining = sql[comment_pos + 2:].strip()
        if remaining and not remaining.startswith(' ') and remaining != '':
            # This is likely a comment with content that's not just a trailing comment
            pass  # Allow for now - trailing comments are common
    
    # Check for dangerous keywords - but be more precise to avoid false positives
    dangerous_patterns = [
        r'\bdrop\s+table\b',  # DROP TABLE
        r'\bcreate\s+table\b',  # CREATE TABLE  
        r'\balter\s+table\b',  # ALTER TABLE
        r'\btruncate\s+table\b',  # TRUNCATE TABLE
        r'\binsert\s+into\b',  # INSERT INTO
        r'\bupdate\s+\w+\s+set\b',  # UPDATE ... SET
        r'\bdelete\s+from\b',  # DELETE FROM
        r'\bmerge\s+\w+\s+using\b',  # MERGE ... USING
        r'\bgrant\s+',  # GRANT
        r'\brevoke\s+',  # REVOKE
        r'\bexec\s*\(',  # EXEC(
        r'\bexecute\s*\(',  # EXECUTE(
        r'\bsp_\w+',  # Stored procedures
        r'\bxp_\w+',  # Extended procedures
        r'\binformation_schema\.',  # Information schema access
        r'\bsys\.',  # System tables
        r'\badmin_\w+',  # Admin tables/functions
        r'\bpassword\b',  # Password field
        r'\bsecret\b',  # Secret field
    ]
    
    import re
    for pattern in dangerous_patterns:
        if re.search(pattern, sql_lower):
            match = re.search(pattern, sql_lower)
            raise ValueError(f"Forbidden pattern '{match.group()}' detected - potential security violation")


def _check_multi_statement(sql: str) -> None:
    """Check for multiple SQL statements."""
    # Remove string literals and comments to avoid false positives
    cleaned_sql = _remove_strings_and_comments(sql)
    
    # Count meaningful semicolons (not at the end)
    semicolons = cleaned_sql.count(';')
    if semicolons > 1 or (semicolons == 1 and not cleaned_sql.strip().endswith(';')):
        raise ValueError("Multiple SQL statements not allowed")


def _remove_strings_and_comments(sql: str) -> str:
    """Remove string literals and comments from SQL to avoid false positives."""
    import re
    
    # Remove single-quoted strings
    sql = re.sub(r"'(?:[^'\\]|\\.)*'", "''", sql)
    
    # Remove double-quoted strings
    sql = re.sub(r'"(?:[^"\\\\]|\\\\.)*"', '""', sql)
    
    # Remove single-line comments
    sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    
    # Remove multi-line comments
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    
    return sql


def _has_aggregation(parsed) -> bool:
    """Enhanced aggregation detection including window functions and DISTINCT."""
    # Check for GROUP BY
    if parsed.find(exp.Group):
        return True
    
    # Check for aggregate functions - look for specific function types
    for func in parsed.find_all(exp.Anonymous):
        if hasattr(func, 'this') and func.this:
            func_name = str(func.this).lower()
            if func_name in ['count', 'sum', 'avg', 'min', 'max', 'stddev', 'variance', 
                           'array_agg', 'string_agg', 'approx_count_distinct']:
                return True
    
    # Also check for Count, Sum, Avg, etc. expression types directly
    agg_types = [exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max]
    for agg_type in agg_types:
        if parsed.find(agg_type):
            return True
    
    # Check for window functions
    if parsed.find(exp.Window):
        return True
    
    # Check for DISTINCT
    if parsed.find(exp.Distinct):
        return True
    
    # Check for HAVING (implies aggregation)
    if parsed.find(exp.Having):
        return True
    
    return False


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
