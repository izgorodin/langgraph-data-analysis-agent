-- Malicious SQL queries that should be blocked
-- These represent various SQL injection and attack patterns

-- Classic SQL injection with semicolon
SELECT * FROM orders; DROP TABLE users; --

-- Comment-based injection
SELECT * FROM orders /* malicious comment */ DELETE FROM products; --

-- Union-based injection
SELECT * FROM orders UNION SELECT password FROM admin_users

-- Boolean-based injection
SELECT * FROM orders WHERE 1=1 OR '1'='1'

-- Stacked queries injection
SELECT * FROM orders; INSERT INTO admin_users VALUES ('hacker', 'password')

-- Time-based blind injection
SELECT * FROM orders WHERE (SELECT CASE WHEN (1=1) THEN SLEEP(10) ELSE 0 END)

-- Error-based injection
SELECT * FROM orders WHERE 1=CONVERT(int, (SELECT @@version))

-- Hex encoding injection
SELECT * FROM orders WHERE name = 0x61646d696e

-- Unicode injection
SELECT * FROM orders WHERE name = NCHAR(0x0061)

-- Second-order injection via stored data
SELECT * FROM orders WHERE description = 'test''; DROP TABLE users; --'

-- Subquery injection
SELECT * FROM orders WHERE id IN (SELECT id FROM admin_data)

-- HAVING clause injection
SELECT COUNT(*) FROM orders HAVING 1=1; DROP TABLE products

-- ORDER BY injection
SELECT * FROM orders ORDER BY (SELECT password FROM admin_users)

-- INTO OUTFILE injection (MySQL specific but should be blocked)
SELECT * FROM orders INTO OUTFILE '/etc/passwd'

-- LOAD DATA injection
LOAD DATA INFILE '/etc/passwd' INTO TABLE orders

-- XPath injection (XML-based)
SELECT * FROM orders WHERE ExtractValue(1, 'version()') > 0

-- Function-based injection
SELECT * FROM orders WHERE SUBSTRING(version(),1,1) = '5'

-- Concatenation-based injection
SELECT * FROM orders WHERE name = '' + (SELECT password FROM admin_users) + ''

-- CASE statement injection
SELECT * FROM orders WHERE CASE WHEN (1=1) THEN id ELSE (SELECT password FROM admin_users) END = 1

-- Nested comment injection
SELECT * FROM orders /*! UNION SELECT password FROM admin_users */

-- Encoded comment injection
SELECT * FROM orders %2F%2A UNION SELECT password FROM admin_users %2A%2F

-- Double encoding injection
SELECT * FROM orders %252F%252A UNION SELECT password FROM admin_users %252A%252F

-- Whitespace evasion
SELECT/**/username,password/**/FROM/**/admin_users

-- Tab and newline evasion
SELECT	username,
password	FROM
admin_users

-- Alternative quote marks
SELECT * FROM orders WHERE name = `admin`

-- Scientific notation injection
SELECT * FROM orders WHERE id = 1e1 UNION SELECT password FROM admin_users

-- Null byte injection
SELECT * FROM orders WHERE name = 'admin%00' UNION SELECT password FROM admin_users

-- Cross-database queries (should be blocked)
SELECT * FROM information_schema.tables

-- System table access
SELECT * FROM sys.databases

-- BigQuery specific injection attempts
SELECT * FROM `project.dataset.secret_table`

-- Regex injection for BigQuery
SELECT * FROM orders WHERE REGEXP_CONTAINS(description, '.*; DROP TABLE users.*')

-- JSON injection for BigQuery
SELECT JSON_EXTRACT(metadata, '$.password') FROM orders