# Example: Product Trend (EN)

Command (EN):

```
LGDA_STRICT_NO_FAKE_REPORT=true LGDA_BQ_TIMEOUT_SEC=120 .venv/bin/python cli.py "Product sales trend by category (monthly) for 2023; highlight top 3 categories by YoY growth and compute 30-day rolling ARPU." --model gemini-1.5-pro --verbose --timeout 180
```

---

Verbose log (abridged):

## plan
{"task": "Monthly product trend by category", "tables": ["orders","order_items","products"], "time_range": ["2023-01-01","2023-12-31"], "metrics": ["monthly_revenue","ARPU_30d"]}

## synthesize_sql
LLM produced SQL (validated):
```
WITH item_rev AS (
  SELECT oi.product_id, DATE_TRUNC(o.created_at, MONTH) AS month, SUM(oi.sale_price * oi.quantity - oi.refund_amount) AS revenue, COUNT(DISTINCT o.user_id) AS mau
  FROM `bigquery-public-data.thelook_ecommerce.orders` o
  JOIN `bigquery-public-data.thelook_ecommerce.order_items` oi ON o.order_id = oi.order_id
  WHERE o.created_at BETWEEN '2023-01-01' AND '2023-12-31'
  GROUP BY product_id, month
)
SELECT p.category, month, SUM(revenue) AS category_revenue, SUM(mau) AS category_mau
FROM item_rev ir
JOIN `bigquery-public-data.thelook_ecommerce.products` p ON ir.product_id = p.product_id
GROUP BY category, month
ORDER BY month
LIMIT 1000
```

## validate_sql
Validation passed (SELECT-only, allowed tables)

## execute_sql
QueryMetrics:
- execution_time: 1.12s
- bytes_processed: 12,345,678
- bytes_billed: 12,582,912
- cache_hit: false

DF summary: rows=120, cols=4

## analyze_df
Result shape: 120 rows × 4 columns

## report
LLM report (truncated):
"Top categories by YoY growth: Accessories (+34%), Shoes (+21%), Apparel (+18%). Notable spike in June driven by Shoes due to a promotional campaign. Recommendations: investigate campaign attribution, consider inventory reallocation to Shoes for Q4."

---

QueryMetrics block and full verbose logs are available in the example file for reproducibility.
