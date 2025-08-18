-- BigQuery-specific SQL constructs and functions
-- These test BigQuery dialect support in sqlglot

-- Date and time functions
SELECT 
    DATE(created_at) as order_date,
    DATETIME(created_at) as order_datetime,
    TIMESTAMP(created_at) as order_timestamp
FROM orders;

-- EXTRACT function variations
SELECT 
    EXTRACT(YEAR FROM created_at) as year,
    EXTRACT(MONTH FROM created_at) as month,
    EXTRACT(DAY FROM created_at) as day,
    EXTRACT(HOUR FROM created_at) as hour,
    EXTRACT(DAYOFWEEK FROM created_at) as day_of_week,
    EXTRACT(DAYOFYEAR FROM created_at) as day_of_year
FROM orders;

-- PARSE_DATE and FORMAT_DATE
SELECT 
    PARSE_DATE('%Y-%m-%d', '2024-01-01') as parsed_date,
    FORMAT_DATE('%B %d, %Y', DATE(created_at)) as formatted_date
FROM orders;

-- Regular expressions
SELECT 
    email,
    REGEXP_EXTRACT(email, r'([^@]+)') as username,
    REGEXP_EXTRACT(email, r'@(.+)') as domain,
    REGEXP_CONTAINS(email, r'gmail\.com') as is_gmail
FROM users;

-- String functions
SELECT 
    CONCAT(first_name, ' ', last_name) as full_name,
    UPPER(email) as email_upper,
    LOWER(email) as email_lower,
    LENGTH(email) as email_length,
    SUBSTR(email, 1, 5) as email_prefix,
    TRIM(first_name) as trimmed_name,
    REPLACE(email, '@', '_at_') as email_safe
FROM users;

-- Array functions
SELECT 
    order_id,
    ARRAY_AGG(product_id) as product_ids,
    ARRAY_AGG(DISTINCT product_id) as unique_product_ids,
    ARRAY_LENGTH(ARRAY_AGG(product_id)) as product_count
FROM order_items 
GROUP BY order_id;

-- UNNEST with arrays
SELECT 
    product_category,
    product_name
FROM UNNEST(['Electronics', 'Clothing', 'Books']) as product_category
CROSS JOIN UNNEST(['Phone', 'Laptop', 'Shirt', 'Novel']) as product_name;

-- STRUCT operations
SELECT 
    order_id,
    STRUCT(
        user_id as id,
        status as order_status,
        created_at as order_date
    ) as order_info
FROM orders;

-- JSON functions
SELECT 
    order_id,
    TO_JSON_STRING(STRUCT(user_id, status, created_at)) as order_json,
    JSON_EXTRACT('{"status": "complete", "items": 5}', '$.status') as json_status
FROM orders;

-- Mathematical functions
SELECT 
    sale_price,
    ROUND(sale_price, 2) as rounded_price,
    CEIL(sale_price) as ceiling_price,
    FLOOR(sale_price) as floor_price,
    ABS(sale_price - 50) as price_diff,
    SQRT(sale_price) as sqrt_price,
    POW(sale_price, 2) as squared_price
FROM order_items;

-- Statistical functions
SELECT 
    product_id,
    COUNT(*) as sale_count,
    AVG(sale_price) as avg_price,
    STDDEV(sale_price) as price_stddev,
    VARIANCE(sale_price) as price_variance,
    PERCENTILE_CONT(sale_price, 0.5) OVER (PARTITION BY product_id) as median_price
FROM order_items
GROUP BY product_id;

-- Window functions with frames
SELECT 
    order_id,
    created_at,
    LAG(created_at, 1) OVER (ORDER BY created_at) as prev_order_time,
    LEAD(created_at, 1) OVER (ORDER BY created_at) as next_order_time,
    FIRST_VALUE(order_id) OVER (ORDER BY created_at ROWS UNBOUNDED PRECEDING) as first_order,
    LAST_VALUE(order_id) OVER (ORDER BY created_at ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as last_order
FROM orders;

-- QUALIFY clause (BigQuery specific)
SELECT 
    user_id,
    order_id,
    created_at,
    ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC) as rn
FROM orders
QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC) = 1;

-- Pivot operations
SELECT *
FROM (
    SELECT 
        category,
        EXTRACT(MONTH FROM oi.created_at) as month,
        sale_price
    FROM products p
    JOIN order_items oi ON p.id = oi.product_id
) 
PIVOT (
    SUM(sale_price) as revenue
    FOR month IN (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
);

-- Geography functions
SELECT 
    user_id,
    ST_GEOGPOINT(longitude, latitude) as location,
    ST_DISTANCE(
        ST_GEOGPOINT(longitude, latitude), 
        ST_GEOGPOINT(-74.006, 40.7128)  -- NYC coordinates
    ) as distance_to_nyc
FROM users
WHERE longitude IS NOT NULL AND latitude IS NOT NULL;

-- Hash functions
SELECT 
    email,
    MD5(email) as email_md5,
    SHA1(email) as email_sha1,
    SHA256(email) as email_sha256,
    SHA512(email) as email_sha512
FROM users;

-- Conditional expressions
SELECT 
    order_id,
    status,
    CASE status
        WHEN 'Complete' THEN 1
        WHEN 'Processing' THEN 0.5
        ELSE 0
    END as status_score,
    IF(status = 'Complete', 'Done', 'Pending') as simple_status,
    IFNULL(shipped_at, created_at) as effective_ship_date,
    COALESCE(delivered_at, shipped_at, created_at) as latest_date
FROM orders;

-- TABLESAMPLE (BigQuery specific)
SELECT * 
FROM orders TABLESAMPLE SYSTEM (10 PERCENT);

-- WITH OFFSET for arrays
SELECT 
    value,
    offset_position
FROM UNNEST(['a', 'b', 'c', 'd']) as value WITH OFFSET as offset_position;

-- Safe navigation for nested data
SELECT 
    order_id,
    SAFE.PARSE_JSON(metadata).category as category,
    SAFE_CAST(metadata AS JSON) as metadata_json
FROM orders
WHERE metadata IS NOT NULL;

-- Analytic functions with groups
SELECT 
    user_id,
    order_id,
    created_at,
    COUNT(*) OVER (PARTITION BY user_id) as user_total_orders,
    DENSE_RANK() OVER (PARTITION BY user_id ORDER BY created_at) as order_rank,
    CUME_DIST() OVER (PARTITION BY user_id ORDER BY created_at) as cumulative_dist
FROM orders;

-- Approximate aggregation functions
SELECT 
    status,
    APPROX_COUNT_DISTINCT(user_id) as approx_unique_users,
    APPROX_QUANTILES(EXTRACT(HOUR FROM created_at), 4) as hour_quartiles
FROM orders
GROUP BY status;

-- TIME and DATETIME operations
SELECT 
    TIME(created_at) as order_time,
    DATETIME_ADD(created_at, INTERVAL 30 DAY) as delivery_estimate,
    DATETIME_DIFF(delivered_at, created_at, HOUR) as delivery_hours,
    DATETIME_TRUNC(created_at, MONTH) as order_month
FROM orders;