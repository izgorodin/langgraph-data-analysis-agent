from __future__ import annotations

from typing import Dict, List

import src.bq as bq_mod


def discover_schema(tables: List[str], sample_rows: int = 0) -> Dict[str, object]:
    """Fetch column lists for tables and a tiny sample of rows for context.

    Returns a dict mapping table -> {columns: [...], sample: [row, ...]}
    """
    schema_rows = bq_mod.get_schema(tables)
    schema: Dict[str, dict] = {}
    for r in schema_rows:
        t = r["table_name"]
        schema.setdefault(t, {"columns": []})
        schema[t]["columns"].append(r["column_name"])

    # Optionally fetch a tiny sample for each table (best-effort). Disabled by default
    if sample_rows and sample_rows > 0:
        for t in list(schema.keys()):
            try:
                ds = "bigquery-public-data.thelook_ecommerce"
                sql = f"SELECT * FROM `{ds}.{t}` LIMIT {sample_rows}"
                df = bq_mod.run_query(sql)
                # convert to simple list of dicts
                sample = df.head(sample_rows).to_dict(orient="records")
                schema[t]["sample"] = sample
            except Exception:
                schema[t]["sample"] = []
    else:
        for t in list(schema.keys()):
            schema[t]["sample"] = []

    return schema
