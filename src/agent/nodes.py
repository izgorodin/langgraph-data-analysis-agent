from __future__ import annotations

import json
import logging
import re
from typing import Dict

import sqlglot
from jinja2 import Template
from sqlglot import exp

from ..bq import get_schema, run_query
from ..config import LGDAConfig, settings
from ..llm import llm_completion
from . import schema as schema_mod
from .llm_integration import get_llm_integration
from .prompts import PLAN_SYSTEM, REPORT_SYSTEM, SQL_SYSTEM
from .state import AgentState

ALLOWED = set(settings.allowed_tables)
logger = logging.getLogger(__name__)


def _set_validation_error(state: AgentState, error_message: str) -> None:
    """Set error and update retry state for validation failures."""
    state.last_error = error_message
    state.error = error_message


PLAN_TEMPLATE = Template(
    """
Return a JSON object for this analysis request.
Question: {{ question }}
Tables & Columns\n{% for t, cols in schema.items() %}- {{t}}: {{ cols|join(', ') }}\n{% endfor %}

EXAMPLES:
For "What is the average order value?":
{"task": "Calculate average order value", "tables": ["orders", "order_items"], "metrics": ["AVG(order_total)"], "grain": "order_id"}

For "Top customers by revenue":
{"task": "Rank customers by total revenue", "tables": ["users", "orders", "order_items"], "dimensions": ["users.id", "users.email"], "metrics": ["SUM(sale_price)"], "grain": "user_id"}

For "Customer segments analysis":
{"task": "Analyze customer segments by demographics", "tables": ["users", "orders", "order_items"], "dimensions": ["users.country", "users.age"], "metrics": ["AVG(order_total)", "COUNT(order_id)"], "grain": "segment"}

JSON keys: task, tables, time_range, dimensions, metrics, filters, grain.
IMPORTANT: Always provide specific task description and relevant metrics!
    """
)

SQL_TEMPLATE = Template(
    """
Write a single BigQuery Standard SQL query for this PLAN. Follow these rules STRICTLY:

PLAN JSON: {{ plan_json }}
ALLOWED TABLES: {{ allowed_tables }} (no others!)

Requirements:
- Start with WITH (preferred) or SELECT. Do not include comments or Markdown. No code fences.
- Use fully qualified tables with dataset prefix: bigquery-public-data.thelook_ecommerce.TABLE_NAME
- Only reference tables from the ALLOWED list.
- Prefer explicit JOINs with clear ON conditions; alias tables and qualify columns.
- If time_range is present, apply it with safe date filters using DATE()/TIMESTAMP() as needed.
- Avoid SELECT *. Select only necessary columns with aliases.
- Produce a SINGLE statement; no semicolons other than an optional trailing one.
- If not an aggregation (no GROUP BY / DISTINCT / window), include LIMIT 1000.
- Output ONLY the SQL, nothing else.
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


# Node: discover_schema
def discover_schema_node(state: AgentState) -> AgentState:
    """Discover schema snapshot once and store in state for downstream nodes.

    This node runs before planning so the planner and synthesize nodes can use
    the same compact schema snapshot and avoid repeated blocking queries.
    """
    try:
        # Only attempt discovery if snapshot not already present
        if not getattr(state, "schema_snapshot", None):
            tbls = list(ALLOWED)
            # Discover without fetching sample rows by default to avoid blocking
            try:
                schema_snapshot = schema_mod.discover_schema(tbls, sample_rows=0)
            except TypeError:
                # Some tests or plugins may provide a discover_schema that accepts only tables
                schema_snapshot = schema_mod.discover_schema(tbls)
            state.schema_snapshot = schema_snapshot
            try:
                state.history.append(
                    {"note": "schema_snapshot_created", "tables": ",".join(tbls)}
                )
            except Exception:
                pass
    except Exception as e:  # noqa: BLE001
        try:
            state.history.append({"note": "schema_snapshot_failed", "error": str(e)})
        except Exception:
            pass
    return state


# Node: plan


def plan_node(state: AgentState) -> AgentState:
    # Respect pre-populated plan_json from custom state
    if getattr(state, "plan_json", None):
        return state
    # Ensure a schema_snapshot exists: try to run discovery inline if missing so planner has schema
    if not getattr(state, "schema_snapshot", None):
        try:
            # discover_schema_node is defined in this module above
            state = discover_schema_node(state)
        except Exception:
            # fallback silently; planner will use local _schema_map()
            pass

    # Prefer pre-computed schema_snapshot if available on state (from discover_schema_node)
    schema = getattr(state, "schema_snapshot", None) or _schema_map()

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

    # Original implementation with robust fallback for malformed JSON
    prompt = PLAN_TEMPLATE.render(question=state.question, schema=schema)
    raw = llm_completion(prompt, system=PLAN_SYSTEM) or ""

    def _strip_md_fences(text: str) -> str:
        t = text.strip()
        if t.startswith("```"):
            # remove leading fence with optional language
            t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
            # remove trailing fence
            t = re.sub(r"\n?```\s*$", "", t)
        return t.strip().strip("`")

    def _parse_plan_relaxed(text: str):
        # 1) try direct JSON
        try:
            return json.loads(text)
        except Exception:
            pass
        # 2) extract first {...last} block
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            # remove trailing commas like ,}\n or ,]\n
            candidate = re.sub(r",(\s*[}\]])", r"\1", candidate)
            try:
                return json.loads(candidate)
            except Exception:
                return None
        return None

    cleaned = _strip_md_fences(raw)
    plan = _parse_plan_relaxed(cleaned)
    if plan is None:
        # Minimal safe fallback plan using allowed tables
        # Try a single strict re-prompt to the LLM asking for valid JSON only
        try:
            state.history.append(
                {
                    "note": "plan_fallback_attempt",
                    "reason": "Initial plan parse failed; issuing single strict re-prompt to LLM",
                }
            )
            # Record raw initial LLM output
            try:
                raw_snippet = (raw or "").strip()[:3000]
                state.history.append(
                    {"note": "plan_raw_llm_output_initial", "raw": raw_snippet}
                )
            except Exception:
                pass

            strict_prompt = (
                "Please respond ONLY with a single valid JSON object describing the plan. "
                "Keys should include: task, tables (list), time_range (optional), metrics (optional). "
                "Do not include any explanation or surrounding text, code fences, or markdown.\n"
                + PLAN_TEMPLATE.render(question=state.question, schema=schema)
            )
            reraw = llm_completion(strict_prompt, system=PLAN_SYSTEM) or ""
            try:
                reraw_clean = _strip_md_fences(reraw)
                reparsed = _parse_plan_relaxed(reraw_clean)
            except Exception:
                reparsed = None

            if reparsed is not None:
                plan = reparsed
                try:
                    state.history.append({"note": "plan_reprompt_succeeded"})
                    # Record raw successful re-prompt output
                    state.history.append(
                        {
                            "note": "plan_raw_llm_output_reprompt",
                            "raw": (reraw or "").strip()[:3000],
                        }
                    )
                except Exception:
                    pass
            else:
                plan = {"task": "ad-hoc", "tables": list(ALLOWED)}
                try:
                    state.history.append(
                        {
                            "note": "plan_fallback_used",
                            "reason": "Invalid or malformed JSON from LLM even after re-prompt; used minimal plan",
                        }
                    )
                    state.history.append(
                        {
                            "note": "plan_raw_llm_output_reprompt",
                            "raw": (reraw or "").strip()[:3000],
                        }
                    )
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            # If something goes wrong while re-prompting, fall back safely
            plan = {"task": "ad-hoc", "tables": list(ALLOWED)}
            try:
                state.history.append(
                    {
                        "note": "plan_fallback_used",
                        "reason": "Error during re-prompt; used minimal plan",
                    }
                )
            except Exception:
                pass

    state.plan_json = plan
    return state


# Node: synthesize_sql


def _handle_retry_state(state: AgentState) -> None:
    """Update retry state if an error is present."""
    if state.error is not None:
        state.retry_count += 1
        state.last_error = state.error
        state.error = None  # Clear current error for retry


def synthesize_sql_node(state: AgentState) -> AgentState:
    """Generate SQL based on the plan."""
    # Handle retry state if needed
    _handle_retry_state(state)
    # If a previous corrected SQL exists (from autofix or LLM resynthesis), always prefer it so we
    # do not overwrite a known-good SQL with a newly scaffolded one.
    if getattr(state, "last_working_sql", None):
        try:
            state.sql = state.last_working_sql
            try:
                state.history.append(
                    {"note": "reuse_last_working_sql", "source": "last_working_sql"}
                )
            except Exception:
                pass
        except Exception:
            pass
        return state
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

    # Use schema snapshot provided by a prior discover_schema_node if available.
    # Fall back to a fast local schema map if not present to avoid blocking calls here.
    schema_snapshot = getattr(state, "schema_snapshot", None)
    if schema_snapshot:
        # convert schema_snapshot (table -> {columns: [...]}) to simple map table -> [cols]
        try:
            schema = {t: meta.get("columns", []) for t, meta in schema_snapshot.items()}
        except Exception:
            schema = _schema_map()
    else:
        # Do NOT perform discovery here; expect discover_schema_node to populate state.schema_snapshot
        # Fall back to a fast in-memory schema map to avoid blocking calls.
        schema = _schema_map()

    # Build prompt with error context for retry; include compact schema if present
    compact_schema_str = ""
    try:
        if getattr(state, "schema_snapshot", None):
            parts = []
            for t, meta in state.schema_snapshot.items():
                cols = meta.get("columns", [])[:8] if isinstance(meta, dict) else []
                parts.append(f"{t}: {', '.join(cols)}")
            compact_schema_str = "Tables & columns (sample): " + "; ".join(parts)
    except Exception:
        compact_schema_str = ""

    prompt = SQL_TEMPLATE.render(
        plan_json=json.dumps(state.plan_json), allowed_tables=",".join(ALLOWED)
    )
    if compact_schema_str:
        prompt = compact_schema_str + "\n\n" + prompt

    # Add error context if this is a retry
    if state.retry_count > 0 and state.last_error:
        prompt += f"\n\nPREVIOUS ATTEMPT FAILED WITH ERROR: {state.last_error}\nPlease fix the SQL and try again. Pay attention to column names and table joins."

    try:
        sql = llm_completion(prompt, system=SQL_SYSTEM)
        raw = (sql or "").strip()
    except Exception as e:  # noqa: BLE001
        # Mark an error so retry machinery can engage. Preserve any existing last_error
        prev_last = getattr(state, "last_error", None)
        err_msg = f"LLM error: {e}"
        # If there is already a last_error (likely from execute_sql), prefer preserving that
        if prev_last:
            state.error = prev_last
        else:
            state.error = err_msg
            state.last_error = state.error
        logger.warning(
            "LLM synthesize_sql failed, set state.error to trigger retry: %s", str(e)
        )
        # Record into history for diagnostics
        try:
            state.history.append({"note": "llm_synthesize_exception", "error": str(e)})
        except Exception:
            pass
        # Return early to allow pipeline retry handling
        return state

    # Remove Markdown code fences if present (```sql ... ``` or ``` ... ```)
    if raw.startswith("```"):
        # Strip leading fence with optional language
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        # Strip trailing fence
        raw = re.sub(r"\n?```\s*$", "", raw)

    cleaned = raw.strip().strip("`")

    # Remove common LLM prefixes
    if cleaned.lower().startswith("sql\n"):
        cleaned = cleaned[4:].strip()
    elif cleaned.lower().startswith("sql"):
        cleaned = cleaned[3:].strip()

    # If the model returned JSON by mistake, optionally fall back to a simple safe SELECT
    if cleaned.startswith("{"):
        config = LGDAConfig()
        if getattr(config, "sql_scaffold_enabled", False):
            first_table = next(iter(ALLOWED)) if ALLOWED else "orders"
            dataset = settings.dataset_id
            cleaned = f"SELECT * FROM `{dataset}.{first_table}` LIMIT 10"
            state.history.append(
                {
                    "note": "sql_scaffold_fallback_used",
                    "reason": "LLM returned JSON instead of SQL",
                    "table": first_table,
                }
            )
        else:
            cleaned = ""

    # If empty string after cleanup, optionally scaffold a minimal safe query.
    # Do NOT scaffold arbitrary non-empty invalid text; let validation catch errors and trigger retries.
    if not cleaned:
        config = "config" in locals() and config or LGDAConfig()
        strict_mode = getattr(LGDAConfig(), "strict_no_fake_report", True)
        # If strict mode is enabled, do not generate a scaffolding SQL that pretends to be real data
        if strict_mode:
            # Instead of silently blocking and returning no feedback, produce a structured
            # diagnostic payload that the report node can show to the user. This contains
            # suggested safe checks (non-fabricated) the operator can run to validate schema
            # and data presence, plus human-readable recommendations to fix the plan or
            # enable provisional scaffolding for debugging.
            try:
                state.history.append(
                    {
                        "note": "sql_scaffold_blocked_strict_mode",
                        "reason": "Strict no-fake-report enabled; refusing to scaffold SQL",
                    }
                )
            except Exception:
                pass

            # Build diagnostic: list planned tables, available schema columns, and safe checks
            plan_tables = []
            try:
                plan_tables = [t for t in (state.plan_json or {}).get("tables", [])]
            except Exception:
                plan_tables = []

            schema_snapshot = getattr(state, "schema_snapshot", None) or {}
            tables_info = {}
            for t in plan_tables:
                cols = (
                    schema_snapshot.get(t, {}).get("columns", [])
                    if isinstance(schema_snapshot, dict)
                    else []
                )
                tables_info[t] = cols

            # Suggested safe checks (non-mutating): counts and sample rows for each planned table
            dataset = settings.dataset_id
            suggested_checks = []
            for t in plan_tables:
                suggested_checks.append(
                    {
                        "check": f"count_{t}",
                        "sql": f"SELECT COUNT(1) AS cnt FROM `{dataset}.{t}` LIMIT 1",
                        "purpose": "Verify table contains rows",
                    }
                )
                suggested_checks.append(
                    {
                        "check": f"sample_{t}",
                        "sql": f"SELECT * FROM `{dataset}.{t}` LIMIT 5",
                        "purpose": "Inspect sample rows and column names",
                    }
                )

            diagnostic = {
                "reason": "Strict mode blocked scaffold to avoid fabricating results",
                "plan_tables": plan_tables,
                "tables_info": tables_info,
                "suggested_checks": suggested_checks,
                "next_steps": [
                    "Run the suggested checks to confirm available columns and data.",
                    "If columns are missing from schema, update plan or mappings so LLM can generate correct joins.",
                    "To allow provisional scaffolds for debugging, disable strict_no_fake_report and retry.",
                ],
            }

            try:
                state.diagnostic = diagnostic
            except Exception:
                pass

            # Set a clear error but keep diagnostic for report node
            state.error = "SQL scaffold blocked in strict_no_fake_report mode; diagnostic available in state.diagnostic"
            return state

        if getattr(config, "sql_scaffold_enabled", False):
            # try to use a table from the plan that is allowed
            plan_tables = []
            try:
                plan_tables = [t for t in (state.plan_json or {}).get("tables", [])]
            except Exception:  # noqa: BLE001
                plan_tables = []
            # Prefer a sensible primary table for scaffolding: orders > order_items > users > products
            preferred = ["orders", "order_items", "users", "products"]
            chosen = None
            for p in preferred:
                if p in plan_tables and p in ALLOWED:
                    chosen = p
                    break
            if not chosen:
                chosen = next((t for t in plan_tables if t in ALLOWED), None)
            if not chosen:
                chosen = next(iter(ALLOWED)) if ALLOWED else "orders"

            # Use schema (if available) to select a few columns, else use *
            schema = _schema_map()
            cols = schema.get(chosen, [])[:5]
            # Avoid referencing columns with table prefix unless we also alias the table in FROM.
            # For safety, select columns without a prefix.
            col_list = ", ".join(f"`{c}`" for c in cols) if cols else "*"
            dataset = settings.dataset_id
            # Enhanced scaffold: if plan requests multiple tables, try minimal safe JOINs and time_range
            plan = state.plan_json or {}
            time_where = ""
            try:
                tr = plan.get("time_range")
                if isinstance(tr, dict) and tr.get("start") and tr.get("end"):
                    start = tr.get("start")
                    end = tr.get("end")
                    # Use orders.created_at as safe time column
                    time_where = f"WHERE o.created_at BETWEEN '{start}' AND '{end}'"
            except Exception:  # noqa: BLE001
                time_where = ""

            # Build minimal FROM/JOINs based on requested tables - schema-aware to avoid alias/column mismatches
            def _qual(name):
                return f"`{dataset}.{name}`"

            # aliases map
            aliases = {
                "orders": "o",
                "order_items": "oi",
                "products": "p",
                "users": "u",
            }

            # We'll create an ordered list of included tables based on chosen and plan_tables
            included = []

            # Helper to add table if allowed and not already included
            def _add_table(name):
                if name in ALLOWED and name not in included and name in plan_tables:
                    included.append(name)

            # Seed with chosen
            if chosen in ALLOWED:
                included.append(chosen)

            # Prefer sensible expansion order to keep joins valid
            for t in ("orders", "order_items", "products", "users"):
                _add_table(t)

            # Build FROM clause using alias for chosen
            primary_alias = aliases.get(chosen, "t")
            from_clause = f"{_qual(chosen)} AS {primary_alias}"

            joins = []

            # Build safe joins based on which tables are included and their natural keys
            def _find_join_cols(table_a, table_b, schema):
                """Find best candidate join columns between two tables using schema heuristics.

                Returns tuple (col_a, col_b) or (None, None) if not found.
                Heuristics: exact matching column names, common fk patterns (table_a_id, table_b_id),
                or well-known pairs like order_id/order_id, user_id/user_id, product_id/product_id.
                """
                cols_a = schema.get(table_a, []) or []
                cols_b = schema.get(table_b, []) or []

                # Preferred explicit pairs
                preferred_pairs = [
                    ("order_id", "order_id"),
                    ("user_id", "user_id"),
                    ("product_id", "product_id"),
                    ("id", "id"),
                    ("product_id", "id"),
                    ("id", "product_id"),
                ]
                for a_col, b_col in preferred_pairs:
                    if a_col in cols_a and b_col in cols_b:
                        return a_col, b_col

                # Exact name intersection
                for c in cols_a:
                    if c in cols_b:
                        return c, c

                # FK style: {other_table}_id
                for c in cols_a:
                    if c.endswith("_id"):
                        base = c[:-3]
                        cand = base + "_id"
                        if cand in cols_b:
                            return c, cand

                # Fallback: try common candidates in each table
                common_candidates = [
                    "user_id",
                    "customer_id",
                    "order_id",
                    "product_id",
                    "id",
                    "sku",
                ]
                for cand in common_candidates:
                    if cand in cols_a and cand in cols_b:
                        return cand, cand

                return None, None

            if chosen == "orders":
                if "order_items" in included:
                    joins.append(
                        f"JOIN {_qual('order_items')} AS oi ON {primary_alias}.order_id = oi.order_id"
                    )
                if "products" in included and "order_items" in included:
                    # Determine product primary key in products table (common variants: 'id', 'product_id', 'sku')
                    prod_pk = None
                    prod_cols = schema.get("products", []) or []
                    for candidate in ("product_id", "id", "sku"):
                        if candidate in prod_cols:
                            prod_pk = candidate
                            break
                    if not prod_pk and prod_cols:
                        prod_pk = prod_cols[0]
                    # Prefer schema-driven matching between order_items and products
                    a_col, b_col = _find_join_cols("order_items", "products", schema)
                    if a_col and b_col:
                        joins.append(
                            f"JOIN {_qual('products')} AS p ON oi.{a_col} = p.{b_col}"
                        )
                    else:
                        joins.append(
                            f"JOIN {_qual('products')} AS p ON oi.product_id = p.{prod_pk}"
                        )
                if "users" in included:
                    # Schema-driven join between orders and users
                    a_col, b_col = _find_join_cols(chosen, "users", schema)
                    if a_col and b_col:
                        joins.append(
                            f"JOIN {_qual('users')} AS u ON {primary_alias}.{a_col} = u.{b_col}"
                        )
                    else:
                        joins.append(
                            f"JOIN {_qual('users')} AS u ON {primary_alias}.user_id = u.user_id"
                        )

            elif chosen == "order_items":
                if "orders" in included:
                    a_col, b_col = _find_join_cols("order_items", "orders", schema)
                    if a_col and b_col:
                        joins.append(
                            f"JOIN {_qual('orders')} AS o ON o.{b_col} = oi.{a_col}"
                        )
                    else:
                        joins.append(
                            f"JOIN {_qual('orders')} AS o ON o.order_id = oi.order_id"
                        )
                if "products" in included:
                    prod_pk = None
                    prod_cols = schema.get("products", []) or []
                    for candidate in ("product_id", "id", "sku"):
                        if candidate in prod_cols:
                            prod_pk = candidate
                            break
                    if not prod_pk and prod_cols:
                        prod_pk = prod_cols[0]
                    a_col, b_col = _find_join_cols("order_items", "products", schema)
                    if a_col and b_col:
                        joins.append(
                            f"JOIN {_qual('products')} AS p ON oi.{a_col} = p.{b_col}"
                        )
                    else:
                        joins.append(
                            f"JOIN {_qual('products')} AS p ON oi.product_id = p.{prod_pk}"
                        )
                # users via orders if orders included
                if "users" in included and "orders" in included:
                    a_col, b_col = _find_join_cols("orders", "users", schema)
                    if a_col and b_col:
                        joins.append(
                            f"JOIN {_qual('users')} AS u ON o.{a_col} = u.{b_col}"
                        )
                    else:
                        joins.append(
                            f"JOIN {_qual('users')} AS u ON o.user_id = u.user_id"
                        )

            elif chosen == "users":
                if "orders" in included:
                    a_col, b_col = _find_join_cols("orders", "users", schema)
                    if a_col and b_col:
                        joins.append(
                            f"JOIN {_qual('orders')} AS o ON o.{a_col} = u.{b_col}"
                        )
                    else:
                        joins.append(
                            f"JOIN {_qual('orders')} AS o ON o.user_id = u.user_id"
                        )
                    if "order_items" in included:
                        a_col, b_col = _find_join_cols("orders", "order_items", schema)
                        if a_col and b_col:
                            joins.append(
                                f"JOIN {_qual('order_items')} AS oi ON o.{a_col} = oi.{b_col}"
                            )
                        else:
                            joins.append(
                                f"JOIN {_qual('order_items')} AS oi ON o.order_id = oi.order_id"
                            )
                        if "products" in included:
                            a_col, b_col = _find_join_cols(
                                "order_items", "products", schema
                            )
                            if a_col and b_col:
                                joins.append(
                                    f"JOIN {_qual('products')} AS p ON oi.{a_col} = p.{b_col}"
                                )
                            else:
                                joins.append(
                                    f"JOIN {_qual('products')} AS p ON oi.product_id = p.product_id"
                                )

            elif chosen == "products":
                if "order_items" in included:
                    # Order_items -> products FK may reference products.id or products.product_id
                    prod_pk = None
                    prod_cols = schema.get("products", []) or []
                    for candidate in ("product_id", "id", "sku"):
                        if candidate in prod_cols:
                            prod_pk = candidate
                            break
                    if not prod_pk and prod_cols:
                        prod_pk = prod_cols[0]
                    a_col, b_col = _find_join_cols("order_items", "products", schema)
                    if a_col and b_col:
                        joins.append(
                            f"JOIN {_qual('order_items')} AS oi ON oi.{a_col} = p.{b_col}"
                        )
                    else:
                        joins.append(
                            f"JOIN {_qual('order_items')} AS oi ON oi.product_id = p.{prod_pk}"
                        )
                    if "orders" in included:
                        joins.append(
                            f"JOIN {_qual('orders')} AS o ON o.order_id = oi.order_id"
                        )
                        if "users" in included:
                            joins.append(
                                f"JOIN {_qual('users')} AS u ON o.user_id = u.user_id"
                            )

            # Compose select columns from available schemas, prefixed with correct aliases, and only if the column exists
            select_cols = []
            added = set()
            # prefer to include a few representative columns per included table
            for table in included:
                alias = aliases.get(table, table[:2])
                table_cols = schema.get(table, [])
                # pick up to 3 columns from schema for this table
                for c in (table_cols or [])[:3]:
                    qualified = f"{alias}.{c}"
                    if qualified not in added:
                        select_cols.append(qualified)
                        added.add(qualified)

            # Fallback: if no select columns were found (schema missing), use safe unqualified columns from chosen table or *
            if not select_cols:
                chosen_cols = schema.get(chosen, [])[:5]
                if chosen_cols:
                    for c in chosen_cols:
                        select_cols.append(f"{primary_alias}.{c}")
                else:
                    select_cols = ["*"]

            # Build final SQL
            join_sql = "\n".join(joins)
            cleaned = (
                "SELECT "
                + ", ".join(select_cols)
                + f"\nFROM {from_clause}\n"
                + (join_sql + "\n" if join_sql else "")
                + (time_where + "\n" if time_where else "")
                + "LIMIT 10"
            )

            state.history.append(
                {
                    "note": "sql_scaffold_fallback_enhanced",
                    "reason": "Empty SQL from LLM; generated enhanced schema-aware scaffold respecting plan (joins/time_range)",
                    "tables": (
                        ",".join(plan_tables)
                        if isinstance(plan_tables, list)
                        else str(plan_tables)
                    ),
                }
            )
    state.sql = cleaned
    return state


# Node: validate_sql


def validate_sql_node(state: AgentState) -> AgentState:
    """Enhanced SQL validation with comprehensive security checks."""

    # Guard: ensure we have SQL to validate. If previous node (synth) blocked scaffolding
    # due to strict mode or LLM returned no SQL, state.sql may be None. Fail-fast with
    # an explicit validation error to avoid NoneType attribute errors downstream.
    if not getattr(state, "sql", None):
        try:
            state.history.append(
                {
                    "note": "validate_sql_no_sql",
                    "reason": "No SQL found in state (synth blocked scaffolding or LLM returned no SQL)",
                }
            )
        except Exception:
            pass
        _set_validation_error(
            state,
            "No SQL to validate: previous node produced no SQL (possibly blocked by strict_no_fake_report).",
        )
        return state

    # Pre-parsing security checks (run first to catch DML/DDL and malformed queries)
    try:
        _check_injection_patterns(state.sql)
        _check_multi_statement(state.sql)
        _validate_syntax_strictly(state.sql)  # Add strict syntax validation
    except Exception as e:  # noqa: BLE001
        _set_validation_error(state, str(e))
        return state

    # Parse SQL
    try:
        parsed = sqlglot.parse_one(state.sql, read="bigquery")
    except Exception as e:  # noqa: BLE001
        _set_validation_error(state, f"SQL parse error: {e}")
        return state

    # Handle empty/invalid parsed results
    if parsed is None:
        _set_validation_error(state, "Invalid or empty SQL query")
        return state

    # Policy: SELECT only (but allow UNION of SELECT statements)
    has_aggregation = False
    if isinstance(parsed, exp.Union):
        # UNION is acceptable if it contains only SELECT statements
        # Treat as complex query; no LIMIT injection
        has_aggregation = True
    elif not isinstance(parsed, exp.Select):
        _set_validation_error(state, "Only SELECT queries are allowed")
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
        _set_validation_error(
            state,
            f"Forbidden tables detected: {', '.join(forbidden_tables)} - potential security violation",
        )
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
        msg = str(e)
        # Log execution error into history for debugging
        try:
            state.history.append({"note": "execute_error", "error": msg})
        except Exception:
            pass

        # Heuristic: if error looks like missing column on alias, it's likely scaffold issue
        m = re.search(
            r"Name\s+(?P<col>\w+)\s+not\s+found\s+inside\s+(?P<alias>\w+)", msg
        )
        if m:
            col = m.group("col")
            alias = m.group("alias")
            try:
                state.history.append(
                    {
                        "note": "scaffold_error_detected",
                        "col": col,
                        "alias": alias,
                        "message": msg,
                    }
                )
            except Exception:
                pass

            # Try a best-effort automatic SQL fix using schema_snapshot: replace alias.col with alias.<candidate>
            try:
                # parse alias->table mapping using sqlglot
                parsed = sqlglot.parse_one(state.sql, read="bigquery")
                alias_map = {}
                for t in parsed.find_all(exp.Table):
                    tbl_name = t.name
                    tbl_alias = None
                    if hasattr(t, "alias") and t.alias:
                        tbl_alias = str(t.alias)
                    # some Table nodes wrap with Identifier; fallback
                    if tbl_alias:
                        alias_map[tbl_alias] = tbl_name

                # find target table name for the alias
                target_table = alias_map.get(alias)
                candidate_col = None
                if target_table and getattr(state, "schema_snapshot", None):
                    cols = state.schema_snapshot.get(target_table, {}).get(
                        "columns", []
                    )
                    # prefer same name if exists, else common candidates
                    if col in cols:
                        candidate_col = col
                    else:
                        for candidate in ("product_id", "id", "sku"):
                            if candidate in cols:
                                candidate_col = candidate
                                break
                        if not candidate_col and cols:
                            candidate_col = cols[0]

                if candidate_col and candidate_col != col:
                    new_sql = re.sub(
                        rf"\b{alias}\.{col}\b", f"{alias}.{candidate_col}", state.sql
                    )
                    try:
                        state.history.append(
                            {
                                "note": "sql_autofix_attempt",
                                "alias": alias,
                                "from": col,
                                "to": candidate_col,
                            }
                        )
                    except Exception:
                        pass

                    # Try to run the fixed SQL once
                    try:
                        df = run_query(new_sql)
                        # success: update state.sql and proceed
                        state.sql = new_sql
                        # Persist working SQL so retries reuse it
                        try:
                            state.last_working_sql = new_sql
                            state.history.append(
                                {"note": "last_working_sql_set", "method": "autofix"}
                            )
                        except Exception:
                            pass
                        try:
                            state.history.append(
                                {"note": "sql_autofix_succeeded", "sql": new_sql[:2000]}
                            )
                        except Exception:
                            pass
                        # continue to summarization below
                    except Exception as e2:
                        # autofix attempt failed; record and try LLM resynthesis below
                        try:
                            state.history.append(
                                {"note": "sql_autofix_failed", "error": str(e2)}
                            )
                        except Exception:
                            pass
                        # fall through to attempt LLM re-synthesis
                else:
                    # No candidate found to autofix - will try LLM resynthesis
                    # Try a last-resort heuristic: if alias->table mapping failed, attempt to infer table name
                    # from the SQL text (look for FROM `...tablename` AS alias) and if schema shows 'id' column
                    # but not the original col, replace alias.col -> alias.id
                    try:
                        if getattr(state, "schema_snapshot", None):
                            # regex to find FROM `...table` AS alias or JOIN `...table` AS alias
                            pattern = rf"(?:FROM|JOIN)\s+`?\w+\.\w+\.(?P<table>\w+)`?\s+AS\s+{alias}\b"
                            m2 = re.search(pattern, state.sql, flags=re.IGNORECASE)
                            table_name = None
                            if m2:
                                table_name = m2.group("table")
                            if table_name:
                                cols = state.schema_snapshot.get(table_name, {}).get(
                                    "columns", []
                                )
                                if "id" in cols and col not in cols:
                                    new_sql = re.sub(
                                        rf"\b{alias}\.{col}\b", f"{alias}.id", state.sql
                                    )
                                    try:
                                        state.history.append(
                                            {
                                                "note": "sql_autofix_infer_id",
                                                "alias": alias,
                                                "from": col,
                                                "to": "id",
                                                "table": table_name,
                                            }
                                        )
                                    except Exception:
                                        pass
                                    try:
                                        df = run_query(new_sql)
                                        state.sql = new_sql
                                        state.last_working_sql = new_sql
                                        try:
                                            state.history.append(
                                                {
                                                    "note": "last_working_sql_set",
                                                    "method": "inferred_id_autofix",
                                                }
                                            )
                                        except Exception:
                                            pass
                                    except Exception:
                                        # if this heuristic fails, fall through to LLM resynth
                                        pass
                    except Exception:
                        pass
            except Exception:
                # If anything goes wrong during autofix attempt, preserve original error and fall through
                try:
                    state.history.append(
                        {"note": "sql_autofix_exception", "error": str(Exception)}
                    )
                except Exception:
                    pass
                # fall through to LLM resynthesis attempt

            # At this point, either autofix failed or no candidate was found; attempt LLM re-synthesis
            try:
                # Build compact schema string
                compact_schema = ""
                if getattr(state, "schema_snapshot", None):
                    parts = []
                    for t, meta in state.schema_snapshot.items():
                        cols = (
                            meta.get("columns", [])[:12]
                            if isinstance(meta, dict)
                            else []
                        )
                        parts.append(f"{t}: {', '.join(cols)}")
                    compact_schema = "Tables & columns: " + "; ".join(parts)

                resynth_prompt = (
                    f"BigQuery error: {msg}\n"
                    "Original SQL:\n"
                    f"{state.sql}\n\n"
                    "Schema snapshot (compact):\n"
                    f"{compact_schema}\n\n"
                    "Please return a single corrected BigQuery Standard SQL statement that fixes the error above."
                    " Output ONLY the SQL statement, no explanation, no fences."
                )
                try:
                    state.history.append(
                        {"note": "llm_resynth_attempt", "error": msg[:1000]}
                    )
                except Exception:
                    pass

                res_sql = llm_completion(resynth_prompt, system=SQL_SYSTEM)
                if not res_sql:
                    # LLM did not produce SQL
                    try:
                        state.history.append({"note": "llm_resynth_no_output"})
                    except Exception:
                        pass
                    state.error = msg
                    return state

                # Clean fences and code markers
                res = (res_sql or "").strip()
                if res.startswith("```"):
                    res = re.sub(r"^```[a-zA-Z]*\n?", "", res)
                    res = re.sub(r"\n?```\s*$", "", res)
                res = res.strip().strip("`")
                # Remove possible leading 'SQL' label
                if res.lower().startswith("sql\n"):
                    res = res[4:].strip()

                # Validate syntax with sqlglot
                try:
                    parsed = sqlglot.parse_one(res, read="bigquery")
                    if parsed is None:
                        raise ValueError("LLM returned invalid SQL")
                except Exception as e_parse:
                    try:
                        state.history.append(
                            {"note": "llm_resynth_parse_failed", "error": str(e_parse)}
                        )
                    except Exception:
                        pass
                    state.error = msg
                    return state

                # Try executing the resynthesized SQL once
                try:
                    df = run_query(res)
                    # success: update state.sql and persist working SQL
                    state.sql = res
                    try:
                        state.last_working_sql = res
                        state.history.append(
                            {"note": "last_working_sql_set", "method": "llm_resynth"}
                        )
                    except Exception:
                        pass
                    try:
                        state.history.append(
                            {"note": "llm_resynth_succeeded", "sql": res[:2000]}
                        )
                    except Exception:
                        pass
                    # continue to summarization below
                except Exception as e_run:
                    try:
                        state.history.append(
                            {"note": "llm_resynth_failed", "error": str(e_run)}
                        )
                    except Exception:
                        pass
                    state.error = msg
                    return state
            except Exception as e_any:
                try:
                    state.history.append(
                        {"note": "llm_resynth_exception", "error": str(e_any)}
                    )
                except Exception:
                    pass
                state.error = msg
                return state

        # Non-scaffold execution error: set state.error and stop
        # Final heuristic: if scaffold/autofix/llm resynth all failed, try a last-resort replacement
        # alias.col -> alias.id when schema snapshot indicates 'id' exists but original col does not.
        try:
            m_final = re.search(
                r"Name\s+(?P<col>\w+)\s+not\s+found\s+inside\s+(?P<alias>\w+)", msg
            )
            if m_final and getattr(state, "schema_snapshot", None):
                col = m_final.group("col")
                alias = m_final.group("alias")
                # Find table name for alias by scanning FROM/JOIN clauses
                pat = rf"(?:FROM|JOIN)\s+`?\w+\.\w+\.(?P<table>\w+)`?\s+AS\s+{alias}\b"
                m_tbl = re.search(pat, state.sql, flags=re.IGNORECASE)
                table_name = m_tbl.group("table") if m_tbl else None
                if table_name:
                    cols = state.schema_snapshot.get(table_name, {}).get("columns", [])
                    if "id" in cols and col not in cols:
                        new_sql = re.sub(
                            rf"\b{alias}\.{col}\b", f"{alias}.id", state.sql
                        )
                        try:
                            df = run_query(new_sql)
                            state.sql = new_sql
                            state.last_working_sql = new_sql
                            try:
                                state.history.append(
                                    {
                                        "note": "sql_autofix_inferred_id_final",
                                        "alias": alias,
                                        "from": col,
                                        "to": "id",
                                        "table": table_name,
                                    }
                                )
                            except Exception:
                                pass
                            # success
                            return state
                        except Exception:
                            # ignore failure and fall through to set error
                            pass
        except Exception:
            pass

        state.error = msg
        return state

    # Convert Timestamp columns to strings to avoid JSON serialization errors
    df_for_summary = df.copy()
    for col in df_for_summary.columns:
        if df_for_summary[col].dtype.name.startswith("datetime"):
            df_for_summary[col] = df_for_summary[col].astype(str)

    # summarize
    summary = {
        "rows": len(df),
        "columns": list(df.columns),
        "head": df_for_summary.head(10).to_dict(orient="records"),
        "describe": json.loads(df_for_summary.describe(include="all").to_json()),
    }
    state.df_summary = summary
    return state


# Node: analyze_df


def analyze_df_node(state: AgentState) -> AgentState:
    """Analyze DataFrame with strict error checking to prevent fabrication on error paths."""

    # Get configuration for strict mode (default: True)
    config = LGDAConfig()
    strict_mode = getattr(config, "strict_no_fake_report", True)

    # Strict fail-fast check: if error exists, do not generate any analysis content
    if state.error is not None:
        if strict_mode:
            logger.warning(
                "analyze_df_node: fail-fast triggered, error exists in state",
                extra={
                    "fail_fast": True,
                    "error_category": "PERMANENT",
                    "state_error": state.error,
                    "node": "analyze_df",
                },
            )
            return state
        else:
            logger.info(
                "analyze_df_node: continuing despite error (strict mode disabled)"
            )

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
    """Generate report with strict error checking to prevent fabrication on error paths."""

    # Get configuration for strict mode (default: True)
    config = LGDAConfig()
    strict_mode = getattr(config, "strict_no_fake_report", True)

    # Enhanced fail-fast check: if error exists, do not generate any report content
    if state.error is not None:
        if strict_mode:
            logger.warning(
                "report_node: fail-fast triggered, blocking report generation due to error",
                extra={
                    "fail_fast": True,
                    "error_category": "USER_GUIDED",
                    "state_error": state.error,
                    "node": "report",
                    "fabrication_prevented": True,
                },
            )
            # Do not set state.report - leave it None to indicate no report was generated
            return state
        else:
            logger.info("report_node: continuing despite error (strict mode disabled)")

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
    prompt = (
        f"Question: {state.question}\n"
        f"PLAN: {plan}\n"
        f"DF SUMMARY (truncated): {summary}\n"
        "Write a concise executive insight with numeric evidence and 1–2 next questions."
    )
    text = llm_completion(prompt, system=REPORT_SYSTEM)

    # If LLM returned empty/whitespace, provide a deterministic, non-fabricated fallback
    safe_text = (text or "").strip()
    if not safe_text:
        # Detect if SQL was scaffolded (data preview only)
        scaffolded = any(
            isinstance(h, dict)
            and h.get("note")
            in ("sql_scaffold_fallback_used", "sql_scaffold_fallback_enhanced")
            for h in getattr(state, "history", [])
        )

        # NEW: if strict mode is enabled and scaffold was used, block and return Insufficient Data
        if strict_mode and scaffolded:
            # Build an explicit insufficient-data response with sample and next steps
            sample = []
            cols = []
            try:
                if state.df_summary:
                    cols = state.df_summary.get("columns", [])
                    sample = state.df_summary.get("head", [])[:5]
            except Exception:  # noqa: BLE001
                pass

            parts = [
                "Insufficient data (strict mode): agent used a SQL scaffold and cannot produce an executive insight.",
            ]
            if cols:
                parts.append(f"Columns detected: {', '.join(cols[:8])}.")
            if sample:
                parts.append("Data sample:")
                # Represent sample as simple lines
                for r in sample:
                    parts.append(str(r))

            parts.append(
                "Next steps: ensure the LLM can produce a valid SQL query, include needed joins/aggregations, or disable strict mode to allow provisional insights."
            )

            state.report = "\n".join(parts)
            return state

        rows = None
        cols = None
        sample_cols = None
        try:
            if state.df_summary:
                rows = state.df_summary.get("rows")
                cols = state.df_summary.get("columns")
                sample_cols = (
                    ", ".join(map(str, cols[:8])) if isinstance(cols, list) else None
                )
        except Exception:  # noqa: BLE001
            pass

        # Build a short factual message without insights
        parts = []
        if scaffolded:
            parts.append(
                "Предупреждение: выполнен только безопасный предпросмотр данных (SQL‑заглушка), полноценный анализ не выполнялся."
            )
        else:
            parts.append(
                "Предупреждение: отчёт не сформирован LLM, показан только краткий статус выполнения."
            )

        if rows is not None and cols is not None:
            parts.append(f"Данные: {rows} строк, {len(cols)} колонок.")
            if sample_cols:
                parts.append(f"Пример колонок: {sample_cols}.")

        parts.append(
            "Что дальше: уточните формулировку запроса или повторите попытку; для полноценного ответа нужно корректное SQL с агрегациями по плану."
        )

        state.report = " \n".join(parts)
        return state

    state.report = safe_text
    return state


def error_handler_node(state: AgentState) -> AgentState:
    """Handle final error state when retries are exhausted."""
    logger.warning(
        "error_handler_node: All retries exhausted, preserving error state",
        extra={
            "retry_count": state.retry_count,
            "max_retries": state.max_retries,
            "error": state.error,
            "last_error": state.last_error,
            "node": "error_handler",
        },
    )

    # Ensure error is preserved in final state
    if state.error is None and state.last_error is not None:
        # Restore error from last_error if somehow lost
        state.error = state.last_error
        logger.warning(
            "error_handler_node: Restored error from last_error",
            extra={"restored_error": state.error},
        )

    return state
