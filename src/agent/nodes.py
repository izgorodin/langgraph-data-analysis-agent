from __future__ import annotations

import json
import re
from typing import Dict

import sqlglot
from jinja2 import Template
from sqlglot import exp

from ..bq import get_schema, run_query
from ..config import settings
from ..llm import llm_completion
from .llm_integration import get_llm_integration
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
    try:
        rows = get_schema(list(ALLOWED))
    except Exception:  # noqa: BLE001
        # Degrade gracefully: minimal schema with no columns
        return {t: [] for t in ALLOWED}
    schema: Dict[str, list[str]] = {}
    for r in rows:
        schema.setdefault(r["table_name"], []).append(r["column_name"])
    return schema


# Node: plan


def plan_node(state: AgentState) -> AgentState:
    # Respect pre-populated plan_json from custom state
    if getattr(state, "plan_json", None):
        return state
    schema = _schema_map()

    # Option to use enhanced LLM integration
    if hasattr(state, "use_enhanced_llm") and state.use_enhanced_llm:
        try:
            llm_integration = get_llm_integration()
            plan = llm_integration.generate_plan_sync(state.question, schema)
            state.plan_json = plan
            return state
        except Exception:  # noqa: BLE001
            # Fallback to original implementation
            pass

    # Original implementation for backward compatibility
    prompt = PLAN_TEMPLATE.render(question=state.question, schema=schema)
    raw = llm_completion(prompt, system=PLAN_SYSTEM)
    try:
        plan = json.loads(raw.strip().strip("`"))
    except Exception:  # noqa: BLE001
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
    # Option to use enhanced LLM integration
    if hasattr(state, "use_enhanced_llm") and state.use_enhanced_llm:
        try:
            llm_integration = get_llm_integration()
            sql = llm_integration.generate_sql_sync(state.plan_json, list(ALLOWED))
            state.sql = sql
            return state
        except Exception:  # noqa: BLE001
            # Fallback to original implementation
            pass

    # Original implementation for backward compatibility
    prompt = SQL_TEMPLATE.render(
        plan_json=json.dumps(state.plan_json), allowed_tables=",".join(ALLOWED)
    )
    sql = llm_completion(prompt, system=SQL_SYSTEM)
    cleaned = (sql or "").strip().strip("`")
    # If the model returned JSON by mistake, fall back to a simple safe SELECT
    if cleaned.startswith("{"):
        first_table = next(iter(ALLOWED)) if ALLOWED else "orders"
        cleaned = f"SELECT * FROM {first_table} LIMIT 10"
    state.sql = cleaned
    return state


# Node: validate_sql


def validate_sql_node(state: AgentState) -> AgentState:
    """Enhanced SQL validation with comprehensive security checks."""

    # Pre-parsing security checks (run first to catch DML/DDL and malformed queries)
    try:
        _check_injection_patterns(state.sql)
        _check_multi_statement(state.sql)
        _validate_syntax_strictly(state.sql)  # Add strict syntax validation
    except Exception as e:  # noqa: BLE001
        state.error = str(e)
        return state

    # Parse SQL
    try:
        parsed = sqlglot.parse_one(state.sql, read="bigquery")
    except Exception as e:  # noqa: BLE001
        state.error = f"SQL parse error: {e}"
        return state

    # Handle empty/invalid parsed results
    if parsed is None:
        state.error = "Invalid or empty SQL query"
        return state

    # Policy: SELECT only (but allow UNION of SELECT statements)
    has_aggregation = False
    if isinstance(parsed, exp.Union):
        # UNION is acceptable if it contains only SELECT statements
        # Treat as complex query; no LIMIT injection
        has_aggregation = True
    elif not isinstance(parsed, exp.Select):
        state.error = "Only SELECT queries are allowed"
        return state

    # Policy: block non-allowed tables
    tables = {t.name for t in parsed.find_all(exp.Table)}

    # Filter out CTE names - they are virtual tables, not real tables
    cte_names = set()
    for cte in parsed.find_all(exp.CTE):
        if hasattr(cte, "alias") and cte.alias:
            cte_names.add(str(cte.alias))

    # Remove CTE names from table validation
    real_tables = tables - cte_names

    if not real_tables.issubset(ALLOWED):
        forbidden_tables = real_tables - ALLOWED
        state.error = f"Forbidden tables detected: {', '.join(forbidden_tables)} - potential security violation"
        return state

    # Enhanced aggregation detection for LIMIT injection (unless already set above)
    if not has_aggregation:
        has_aggregation = _has_aggregation(parsed)

    # Optional: LIMIT for non-aggregates
    if not has_aggregation:
        # enforce LIMIT 1000 if missing
        if not parsed.args.get("limit"):
            parsed.set("limit", exp.Limit(this=exp.Literal.number(1000)))
        state.sql = parsed.sql(dialect="bigquery")

    return state


def _validate_syntax_strictly(sql: str) -> None:
    """Pre-validate SQL syntax before sqlglot parsing to prevent auto-correction."""
    sql_upper = sql.upper().strip()

    # Check that query starts with SELECT or WITH (for CTEs)
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        raise ValueError("SQL parse error: Query must start with SELECT or WITH")

    # Check for incomplete SELECT statement
    if sql_upper == "SELECT" or sql_upper.endswith("SELECT"):
        raise ValueError("SQL parse error: Incomplete SELECT statement")

    # Check for "SELECT FROM" without column specification (malformed)
    if re.match(r"SELECT\s+FROM\s+\w+", sql_upper):
        raise ValueError("SQL parse error: Missing column specification after SELECT")

    # Check for missing FROM clause in simple cases
    if (
        "FROM" not in sql_upper
        and "SELECT" in sql_upper
        and not sql_upper.startswith("WITH")
    ):
        # Allow cases like SELECT 1, SELECT CURRENT_TIMESTAMP, etc.
        # But block cases like "SELECT * orders" (missing FROM)
        if re.search(r"SELECT\s+\*\s+\w+(?:\s|$)", sql, re.IGNORECASE):
            raise ValueError("SQL parse error: Missing FROM keyword")

    # Check for incomplete statements ending with keywords
    incomplete_endings = ["FROM", "WHERE", "GROUP", "ORDER", "HAVING", "LIMIT"]
    for ending in incomplete_endings:
        if sql_upper.rstrip().endswith(ending):
            raise ValueError(
                f"SQL parse error: Incomplete statement ending with {ending}"
            )

    # Check for incomplete FROM clause
    if re.search(r"\bFROM\s*$", sql, re.IGNORECASE):
        raise ValueError("SQL parse error: Incomplete FROM clause")


def _check_injection_patterns(sql: str) -> None:
    """Check for common SQL injection patterns."""
    sql_lower = sql.lower().strip()

    # Check for multi-statement indicators
    if ";" in sql and not sql.strip().endswith(";"):
        # Remove string literals to avoid false positives with semicolons in strings
        cleaned_sql = _remove_strings_and_comments(sql)
        if ";" in cleaned_sql and not cleaned_sql.strip().endswith(";"):
            raise ValueError(
                "Multi-statement SQL detected - potential injection attempt"
            )

    # Disallow comments which are often used in injections
    if "/*" in sql or "*/" in sql:
        raise ValueError(
            "Forbidden pattern '/*' detected - potential security violation"
        )
    if "--" in sql:
        raise ValueError(
            "Forbidden pattern '--' detected - potential security violation"
        )

    # DML/DDL disallowed (prefer policy message expected by tests)
    dml_ddl_patterns = [
        r"\bdrop\s+table\b",
        r"\bcreate\s+table\b",
        r"\balter\s+table\b",
        r"\btruncate\s+table\b",
        r"\binsert\s+into\b",
        r"\bupdate\s+\w+\s+set\b",
        r"\bdelete\s+from\b",
        r"\bmerge\s+\w+\s+using\b",
    ]
    for pattern in dml_ddl_patterns:
        if re.search(pattern, sql_lower):
            kw = re.search(pattern, sql_lower).group()
            raise ValueError(
                f"Only SELECT queries are allowed. Forbidden pattern '{kw}' detected - potential security violation"
            )

    # Other dangerous keywords used in injections
    injection_patterns = [
        r"\bgrant\s+",
        r"\brevoke\s+",
        r"\bexec\s*\(",
        r"\bexecute\s*\(",
        r"\bsp_\w+",
        r"\bxp_\w+",
        r"\binformation_schema\.",
        r"\bsys\.",
        r"\badmin_\w+",
        r"\bpassword\b",
        r"\bsecret\b",
    ]
    for pattern in injection_patterns:
        if re.search(pattern, sql_lower):
            match = re.search(pattern, sql_lower)
            kw = match.group()
            raise ValueError(
                f"Forbidden pattern '{kw}' detected - potential security violation"
            )


def _check_multi_statement(sql: str) -> None:
    """Check for multiple SQL statements."""
    # Remove string literals and comments to avoid false positives
    cleaned_sql = _remove_strings_and_comments(sql)

    # Count meaningful semicolons (not at the end)
    semicolons = cleaned_sql.count(";")
    if semicolons > 1 or (semicolons == 1 and not cleaned_sql.strip().endswith(";")):
        raise ValueError("Multi-statement SQL detected - potential injection attempt")


def _remove_strings_and_comments(sql: str) -> str:
    """Remove string literals and comments from SQL to avoid false positives."""
    # Remove single-quoted strings
    sql = re.sub(r"'(?:[^'\\]|\\.)*'", "''", sql)

    # Remove double-quoted strings
    sql = re.sub(r'"(?:[^"\\\\]|\\\\.)*"', '""', sql)

    # Remove single-line comments
    sql = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)

    # Remove multi-line comments
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)

    return sql


def _has_aggregation(parsed) -> bool:
    """Enhanced aggregation detection - only checks the outer query level."""

    # Check for GROUP BY at the top level
    if parsed.find(exp.Group):
        return True

    # Check for HAVING at the top level (implies aggregation)
    if parsed.find(exp.Having):
        return True

    # Check for DISTINCT at the top level
    if parsed.find(exp.Distinct):
        return True

    # Check for window functions at the top level
    if parsed.find(exp.Window):
        return True

    # For aggregation functions, we only check the SELECT clause of the outer query
    # to avoid false positives from subqueries
    if hasattr(parsed, "expressions") and parsed.expressions:
        for expr in parsed.expressions:
            # Check this expression and its immediate children for aggregation
            if _expression_has_aggregation(expr):
                return True

    return False


def _expression_has_aggregation(expr) -> bool:
    """Check if a single expression has aggregation functions (non-recursive for subqueries)."""
    # Check for specific aggregate function types
    agg_types = [exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max]
    for agg_type in agg_types:
        if expr.find(agg_type):
            return True

    # Check for aggregate functions by name, but only in direct children (not subqueries)
    for func in expr.find_all(exp.Anonymous):
        if hasattr(func, "this") and func.this:
            func_name = str(func.this).lower()
            if func_name in [
                "count",
                "sum",
                "avg",
                "min",
                "max",
                "stddev",
                "variance",
                "array_agg",
                "string_agg",
                "approx_count_distinct",
            ]:
                return True

    # Check for window functions in this expression
    if expr.find(exp.Window):
        return True

    # Check for DISTINCT in this expression
    if expr.find(exp.Distinct):
        return True

    return False


# Node: execute_sql


def execute_sql_node(state: AgentState) -> AgentState:
    try:
        df = run_query(state.sql)
    except Exception as e:  # noqa: BLE001
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
    # If an error already exists, do not attempt report generation
    if getattr(state, "error", None):
        return state
    # Option to use enhanced LLM integration
    if hasattr(state, "use_enhanced_llm") and state.use_enhanced_llm:
        try:
            llm_integration = get_llm_integration()
            report = llm_integration.generate_report_sync(
                state.question, state.plan_json, state.df_summary
            )
            state.report = report
            return state
        except Exception:  # noqa: BLE001
            # Fallback to original implementation
            pass

    # Original implementation for backward compatibility
    plan = json.dumps(state.plan_json, ensure_ascii=False)
    # Ensure JSON serializable summary (handle pandas timestamps etc.)
    summary = json.dumps(state.df_summary, ensure_ascii=False, default=str)[:30000]
    prompt = f"Question: {state.question}\nPLAN: {plan}\nDF SUMMARY (truncated): {summary}\nWrite a concise executive insight with numeric evidence and 1–2 next questions."
    text = llm_completion(prompt, system=REPORT_SYSTEM)
    state.report = text.strip()
    return state
