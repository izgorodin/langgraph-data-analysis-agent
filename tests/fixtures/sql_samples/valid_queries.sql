-- Valid SELECT queries that should pass validation
-- These represent legitimate business queries

-- Basic SELECT with LIMIT
SELECT * FROM orders LIMIT 100;

-- JOIN query with aggregation
SELECT 
    o.status,
    COUNT(*) as order_count,
    SUM(oi.sale_price) as revenue
FROM orders o 
JOIN order_items oi ON o.order_id = oi.order_id 
GROUP BY o.status;

-- Time-based filtering
SELECT 
    DATE(created_at) as order_date,
    COUNT(*) as daily_orders
FROM orders 
WHERE created_at >= '2024-01-01'
GROUP BY DATE(created_at)
ORDER BY order_date;

-- Complex joins with multiple tables
SELECT 
    p.name as product_name,
    p.category,
    SUM(oi.sale_price) as revenue,
    COUNT(DISTINCT o.user_id) as unique_customers
FROM products p
JOIN order_items oi ON p.id = oi.product_id
JOIN orders o ON oi.order_id = o.order_id
WHERE o.status = 'Complete'
GROUP BY p.name, p.category
ORDER BY revenue DESC;

-- Window functions
SELECT 
    user_id,
    order_id,
    created_at,
    ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at) as order_sequence
FROM orders;

-- CTE with aggregation
WITH monthly_sales AS (
    SELECT 
        EXTRACT(YEAR FROM created_at) as year,
        EXTRACT(MONTH FROM created_at) as month,
        SUM(sale_price) as monthly_revenue
    FROM order_items
    GROUP BY EXTRACT(YEAR FROM created_at), EXTRACT(MONTH FROM created_at)
)
SELECT 
    year,
    month,
    monthly_revenue,
    LAG(monthly_revenue) OVER (ORDER BY year, month) as prev_month_revenue
FROM monthly_sales
ORDER BY year, month;

-- DISTINCT query (should be treated as aggregation)
SELECT DISTINCT category FROM products;

-- BigQuery specific functions
SELECT 
    email,
    REGEXP_EXTRACT(email, r'@(.+)') as domain
FROM users
WHERE email IS NOT NULL;

-- Array aggregation (BigQuery specific)
SELECT 
    o.user_id,
    ARRAY_AGG(p.name) as purchased_products
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.id
GROUP BY o.user_id;

-- UNNEST operation (BigQuery specific)
SELECT * FROM UNNEST(['orders', 'products', 'users']) as table_name;