-- Edge cases and corner cases for SQL validation
-- These test boundary conditions and unusual but potentially valid queries

-- Empty query
;

-- Query with only whitespace
   
  

-- Query with only comments
-- This is just a comment

-- Multi-line comments only
/*
This is a multi-line comment
with no actual SQL
*/

-- Very long table alias
SELECT verylongtablealiasnamethatexceedsnormallimits.* FROM orders verylongtablealiasnamethatexceedsnormallimits;

-- Nested subqueries at maximum depth
SELECT * FROM (
    SELECT * FROM (
        SELECT * FROM (
            SELECT * FROM orders
        ) sub3
    ) sub2
) sub1;

-- Query with excessive whitespace
SELECT     *     FROM     orders     WHERE     status     =     'Complete'     ;

-- Mixed case keywords
sElEcT * fRoM oRdErS wHeRe StAtUs = 'Complete';

-- Table name same as SQL keyword
SELECT * FROM `order` o;  -- 'order' is a keyword

-- Column name same as SQL keyword
SELECT `select`, `from`, `where` FROM orders;

-- Unicode characters in strings
SELECT * FROM orders WHERE description = 'café résumé naïve';

-- Very long string literal
SELECT * FROM orders WHERE description = 'This is a very long string that exceeds normal length limits and might cause parsing issues in some SQL parsers or validation systems. It contains many words and characters that should be handled properly by any robust SQL validation system without causing errors or security vulnerabilities.';

-- String with escape characters
SELECT * FROM orders WHERE description = 'It\'s a "test" with \\ backslashes and \n newlines';

-- Numeric edge cases
SELECT * FROM orders WHERE price = 1.7976931348623157E+308;  -- Max double
SELECT * FROM orders WHERE quantity = 9223372036854775807;    -- Max long
SELECT * FROM orders WHERE rate = 0.0000000000000001;         -- Very small decimal

-- Date/time edge cases
SELECT * FROM orders WHERE created_at = '1000-01-01 00:00:00';  -- Minimum date
SELECT * FROM orders WHERE created_at = '9999-12-31 23:59:59';  -- Maximum date

-- Complex CASE statements
SELECT 
    CASE 
        WHEN status = 'Complete' THEN 'Finished'
        WHEN status = 'Processing' THEN 'In Progress'
        WHEN status = 'Cancelled' THEN 'Cancelled'
        ELSE 'Unknown'
    END as status_display
FROM orders;

-- Window functions with complex partitioning
SELECT 
    user_id,
    order_id,
    RANK() OVER (
        PARTITION BY user_id, EXTRACT(YEAR FROM created_at)
        ORDER BY created_at DESC, order_id ASC
    ) as user_year_rank
FROM orders;

-- Recursive CTE (if supported)
WITH RECURSIVE order_hierarchy AS (
    SELECT order_id, parent_order_id, 1 as level
    FROM orders 
    WHERE parent_order_id IS NULL
    
    UNION ALL
    
    SELECT o.order_id, o.parent_order_id, oh.level + 1
    FROM orders o
    JOIN order_hierarchy oh ON o.parent_order_id = oh.order_id
)
SELECT * FROM order_hierarchy;

-- Array operations (BigQuery specific)
SELECT 
    user_id,
    ARRAY[order_id, user_id, product_id] as id_array
FROM order_items;

-- STRUCT operations (BigQuery specific)
SELECT 
    STRUCT(user_id, order_id) as user_order,
    STRUCT(product_id as id, sale_price as price) as product_info
FROM order_items;

-- Geography functions (BigQuery specific)
SELECT 
    ST_GEOGPOINT(longitude, latitude) as location
FROM users
WHERE longitude IS NOT NULL AND latitude IS NOT NULL;

-- JSON operations (BigQuery specific)
SELECT 
    JSON_EXTRACT(metadata, '$.category') as category,
    JSON_EXTRACT_SCALAR(metadata, '$.name') as name
FROM products
WHERE metadata IS NOT NULL;

-- Cross join (potentially dangerous)
SELECT * FROM orders CROSS JOIN products;

-- Self join
SELECT 
    o1.order_id as order1,
    o2.order_id as order2
FROM orders o1
JOIN orders o2 ON o1.user_id = o2.user_id AND o1.order_id < o2.order_id;

-- Query with no FROM clause (should fail)
SELECT 1, 'test', NOW();

-- Empty string conditions
SELECT * FROM orders WHERE description = '';
SELECT * FROM orders WHERE description IS NULL;

-- Zero and negative numbers
SELECT * FROM orders WHERE quantity = 0;
SELECT * FROM orders WHERE quantity = -1;

-- Division by zero scenario
SELECT quantity / 0 FROM orders;

-- LIMIT with variables (should be parsed carefully)
SELECT * FROM orders LIMIT CAST('100' AS INTEGER);

-- OFFSET usage
SELECT * FROM orders LIMIT 100 OFFSET 50;

-- Complex EXISTS subquery
SELECT * FROM orders o 
WHERE EXISTS (
    SELECT 1 FROM order_items oi 
    WHERE oi.order_id = o.order_id 
    AND oi.sale_price > 100
);

-- Multiple CTEs
WITH 
expensive_items AS (
    SELECT * FROM order_items WHERE sale_price > 100
),
recent_orders AS (
    SELECT * FROM orders WHERE created_at > '2024-01-01'
)
SELECT * FROM recent_orders r
JOIN expensive_items e ON r.order_id = e.order_id;