"""
Run expected SQL queries against bigquery-public-data.thelook_ecommerce using project's run_query helper.
This script prints short summaries (row counts + head) for each query.
"""

import os
import sys
from pprint import pprint

# Ensure repository root is on sys.path so `from src...` imports work when running this script
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.bq import run_query  # noqa: E402  (import after sys.path modification is intentional)

# NOTE: these queries assume common column names in thelook_ecommerce dataset.
# Adjust column names if your schema differs.

DATASET = "bigquery-public-data.thelook_ecommerce"

# 1) Cohort LTV by product category over 180 days
SQL_COHORT_LTV = f"""
WITH first_order AS (
  SELECT
    user_id,
    MIN(DATE(orders.created_at)) AS first_order_date
  FROM `{DATASET}.orders` AS orders
  GROUP BY user_id
),
cohort_users AS (
  SELECT user_id, first_order_date, FORMAT_DATE('%Y-%m', first_order_date) AS cohort_month
  FROM first_order
  WHERE first_order_date BETWEEN DATE('2022-01-01') AND DATE('2023-12-31')
),
-- revenue per order_item: dataset uses `sale_price` as line amount; no quantity/discount columns in this schema
item_revenue AS (
  SELECT
    order_id,
    product_id,
    COALESCE(sale_price, 0) AS net_revenue
  FROM `{DATASET}.order_items`
),
orders_with_users AS (
  SELECT o.order_id, o.user_id, DATE(o.created_at) AS order_date
  FROM `{DATASET}.orders` AS o
),
-- join to get events within 180 days of each user's first order
events AS (
  SELECT
    cu.user_id,
    cu.cohort_month,
  ir.product_id,
    pr.category AS product_category,
    ow.order_date,
    TIMESTAMP_DIFF(TIMESTAMP(ow.order_date), TIMESTAMP(cu.first_order_date), DAY) AS days_from_cohort,
  ir.net_revenue AS net_revenue
  FROM cohort_users AS cu
  JOIN orders_with_users AS ow ON cu.user_id = ow.user_id
  JOIN item_revenue AS ir ON ir.order_id = ow.order_id
  LEFT JOIN `{DATASET}.products` AS pr ON pr.id = ir.product_id
  WHERE TIMESTAMP_DIFF(TIMESTAMP(ow.order_date), TIMESTAMP(cu.first_order_date), DAY) BETWEEN 0 AND 180
),
cohort_category_ltv AS (
  SELECT
    cohort_month,
    COALESCE(product_category, 'UNKNOWN') AS category,
    SUM(net_revenue) AS total_revenue,
    COUNT(DISTINCT user_id) AS users_in_cohort,
    SUM(net_revenue)/NULLIF(COUNT(DISTINCT user_id),0) AS avg_ltv_per_user
  FROM events
  GROUP BY cohort_month, category
)
SELECT * FROM cohort_category_ltv ORDER BY cohort_month, category LIMIT 500
"""

# 2) Top-5 cohorts by average LTV (across categories)
SQL_TOP5_COHORTS = f"""
WITH first_order AS (
  SELECT user_id, MIN(DATE(created_at)) AS first_order_date
  FROM `{DATASET}.orders`
  GROUP BY user_id
),
cohort_users AS (
  SELECT user_id, FORMAT_DATE('%Y-%m', first_order_date) AS cohort_month, first_order_date
  FROM first_order
  WHERE first_order_date BETWEEN DATE('2022-01-01') AND DATE('2023-12-31')
),
events AS (
  SELECT
    cu.cohort_month,
    o.user_id,
    COALESCE(oi.sale_price,0) AS net_revenue
  FROM cohort_users cu
  JOIN `{DATASET}.orders` o ON o.user_id = cu.user_id
  JOIN `{DATASET}.order_items` oi ON oi.order_id = o.order_id
  WHERE DATE(o.created_at) BETWEEN cu.first_order_date AND DATE_ADD(cu.first_order_date, INTERVAL 180 DAY)
),
cohort_agg AS (
  SELECT
    cohort_month,
    SUM(net_revenue) AS total_revenue,
    COUNT(DISTINCT user_id) AS total_users,
    SUM(net_revenue)/NULLIF(COUNT(DISTINCT user_id),0) AS avg_ltv
  FROM events
  GROUP BY cohort_month
)
SELECT cohort_month, total_revenue, total_users, avg_ltv
FROM cohort_agg
ORDER BY avg_ltv DESC
LIMIT 5
"""

# 3) Monthly trend: MAU, D30 retention, ARPU for cohorts (example for overall monthly trend)
SQL_MONTHLY_METRICS = f"""
WITH orders AS (
  SELECT user_id, DATE(created_at) AS order_date
  FROM `{DATASET}.orders`
),
monthly_active AS (
  SELECT FORMAT_DATE('%Y-%m', order_date) AS month, COUNT(DISTINCT user_id) AS mau
  FROM orders
  GROUP BY month
),
-- D30 retention approximation: users active in month M and again within 30 days after
user_month AS (
  SELECT user_id, FORMAT_DATE('%Y-%m', order_date) AS month, MIN(order_date) AS first_activity_in_month
  FROM orders
  GROUP BY user_id, FORMAT_DATE('%Y-%m', order_date)
),
retained AS (
  SELECT
    um.month,
    COUNT(DISTINCT um.user_id) AS cohort_users,
    COUNT(DISTINCT CASE WHEN o2.order_date BETWEEN DATE_ADD(um.first_activity_in_month, INTERVAL 1 DAY) AND DATE_ADD(um.first_activity_in_month, INTERVAL 30 DAY) THEN um.user_id END) AS d30_retained
  FROM user_month um
  LEFT JOIN orders o2 ON o2.user_id = um.user_id
  GROUP BY um.month
),
-- ARPU: total revenue in month / MAU
monthly_revenue AS (
  SELECT FORMAT_DATE('%Y-%m', DATE(o.created_at)) AS month, SUM(COALESCE(oi.sale_price,0)) AS revenue
  FROM `{DATASET}.orders` o
  JOIN `{DATASET}.order_items` oi USING(order_id)
  GROUP BY month
)
SELECT
  m.month,
  m.mau,
  r.d30_retained,
  SAFE_DIVIDE(mr.revenue, m.mau) AS arpu
FROM monthly_active m
LEFT JOIN retained r USING(month)
LEFT JOIN monthly_revenue mr USING(month)
ORDER BY month DESC
LIMIT 24
"""

QUERIES = [
    ("Cohort LTV by category (180 days)", SQL_COHORT_LTV),
    ("Top-5 cohorts by avg LTV (180 days)", SQL_TOP5_COHORTS),
    ("Monthly metrics (MAU, D30 retention, ARPU)", SQL_MONTHLY_METRICS),
]

if __name__ == "__main__":
    for title, sql in QUERIES:
        print("\n" + "=" * 80)
        print(title)
        print("-" * 80)
        try:
            df = run_query(sql)
            print("rows:", len(df))
            print("columns:", list(df.columns))
            pprint(df.head(5).to_dict(orient="records"))
        except Exception as e:
            print("ERROR running query:", e)
