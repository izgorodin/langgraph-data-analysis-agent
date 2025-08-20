"""Generators for creating test data with realistic patterns."""

import json
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from faker import Faker

fake = Faker()


class EcommerceDataGenerator:
    """Generates realistic e-commerce data for testing."""

    def __init__(self, seed: int = 42):
        """Initialize with fixed seed for reproducible data."""
        random.seed(seed)
        np.random.seed(seed)
        fake.seed_instance(seed)

    def generate_users(self, count: int = 100) -> pd.DataFrame:
        """Generate realistic user data."""
        users = []

        for i in range(count):
            user = {
                "id": 1000 + i,
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "email": fake.email(),
                "age": random.randint(18, 75),
                "gender": random.choice(["M", "F"]),
                "state": fake.state_abbr(),
                "street_address": fake.street_address(),
                "postal_code": fake.postcode(),
                "city": fake.city(),
                "country": "USA",
                "latitude": float(fake.latitude()),
                "longitude": float(fake.longitude()),
                "traffic_source": random.choice(
                    ["Search", "Social", "Email", "Direct", "Referral"]
                ),
                "created_at": fake.date_time_between(start_date="-2y", end_date="now"),
            }
            users.append(user)

        return pd.DataFrame(users)

    def generate_products(self, count: int = 50) -> pd.DataFrame:
        """Generate realistic product catalog."""
        categories = [
            "Electronics",
            "Clothing",
            "Home & Garden",
            "Sports",
            "Books",
            "Beauty",
            "Toys",
        ]
        departments = [
            "Technology",
            "Fashion",
            "Home",
            "Outdoor",
            "Entertainment",
            "Personal Care",
            "Kids",
        ]
        brands = [
            "BrandA",
            "BrandB",
            "BrandC",
            "TechCorp",
            "StyleCo",
            "HomeBase",
            "SportMax",
        ]

        products = []

        for i in range(count):
            category = random.choice(categories)
            cost = round(random.uniform(5.0, 200.0), 2)
            retail_price = round(
                cost
                * random.uniform(
                    self.MIN_MARKUP_MULTIPLIER, self.MAX_MARKUP_MULTIPLIER
                ),
                2,
            )  # Realistic markup

            product = {
                "id": i + 1,
                "cost": cost,
                "category": category,
                "name": f"{category} Product {i+1}",
                "brand": random.choice(brands),
                "retail_price": retail_price,
                "department": random.choice(departments),
                "sku": f"SKU-{i+1:04d}",
                "distribution_center_id": random.randint(1, 5),
            }
            products.append(product)

        return pd.DataFrame(products)

    def generate_orders(self, users_df: pd.DataFrame, count: int = 200) -> pd.DataFrame:
        """Generate realistic order data linked to users."""
        orders = []

        # Create time distribution - more recent orders
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)

        for i in range(count):
            user_id = random.choice(users_df["id"].tolist())
            created_at = fake.date_time_between(
                start_date=start_date, end_date=end_date
            )

            # Realistic status distribution
            status_weights = {
                "Complete": 0.65,
                "Processing": 0.15,
                "Shipped": 0.12,
                "Cancelled": 0.08,
            }
            status = random.choices(
                list(status_weights.keys()), weights=list(status_weights.values())
            )[0]

            # Generate realistic timestamps based on status
            shipped_at = None
            delivered_at = None
            returned_at = None

            if status in ["Shipped", "Complete"]:
                shipped_at = created_at + timedelta(days=random.randint(1, 3))
                if status == "Complete":
                    delivered_at = shipped_at + timedelta(days=random.randint(1, 7))
                    # Small chance of return
                    if random.random() < 0.05:
                        returned_at = delivered_at + timedelta(
                            days=random.randint(7, 30)
                        )

            order = {
                "order_id": i + 1,
                "user_id": user_id,
                "status": status,
                "created_at": created_at,
                "returned_at": returned_at,
                "shipped_at": shipped_at,
                "delivered_at": delivered_at,
                "num_of_item": random.randint(1, 5),
            }
            orders.append(order)

        return pd.DataFrame(orders)

    def generate_order_items(
        self,
        orders_df: pd.DataFrame,
        products_df: pd.DataFrame,
        items_per_order_range: Tuple[int, int] = (1, 4),
    ) -> pd.DataFrame:
        """Generate realistic order items data."""
        order_items = []
        item_id = 1

        for _, order in orders_df.iterrows():
            num_items = random.randint(*items_per_order_range)

            # Select random products for this order
            selected_products = products_df.sample(n=min(num_items, len(products_df)))

            for _, product in selected_products.iterrows():
                # Apply realistic discounts
                base_price = product["retail_price"]
                discount_factor = random.uniform(
                    self.MIN_DISCOUNT_FACTOR, self.MAX_DISCOUNT_FACTOR
                )  # 0-30% discount
                sale_price = round(base_price * discount_factor, 2)

                # Inherit some timing from order
                created_at = order["created_at"]
                shipped_at = (
                    order["shipped_at"] if pd.notna(order["shipped_at"]) else None
                )
                delivered_at = (
                    order["delivered_at"] if pd.notna(order["delivered_at"]) else None
                )
                returned_at = (
                    order["returned_at"] if pd.notna(order["returned_at"]) else None
                )

                # Item status can differ slightly from order status
                item_status = order["status"]
                if order["status"] == "Complete" and random.random() < 0.02:
                    item_status = "Returned"
                    returned_at = fake.date_time_between(
                        start_date=delivered_at or created_at, end_date=datetime.now()
                    )

                order_item = {
                    "id": item_id,
                    "order_id": order["order_id"],
                    "user_id": order["user_id"],
                    "product_id": product["id"],
                    "inventory_item_id": random.randint(10000, 99999),
                    "status": item_status,
                    "created_at": created_at,
                    "shipped_at": shipped_at,
                    "delivered_at": delivered_at,
                    "returned_at": returned_at,
                    "sale_price": sale_price,
                }
                order_items.append(order_item)
                item_id += 1

        return pd.DataFrame(order_items)


class QueryResultGenerator:
    """Generates realistic query results for testing."""

    @staticmethod
    def generate_sales_summary(num_rows: int = 10) -> pd.DataFrame:
        """Generate realistic sales summary data."""
        categories = ["Electronics", "Clothing", "Home & Garden", "Sports", "Books"]
        data = []

        for i, category in enumerate(categories[:num_rows]):
            data.append(
                {
                    "category": category,
                    "total_orders": random.randint(50, 500),
                    "total_revenue": round(random.uniform(5000, 50000), 2),
                    "avg_order_value": round(random.uniform(50, 200), 2),
                    "unique_customers": random.randint(30, 300),
                }
            )

        return pd.DataFrame(data)

    @staticmethod
    def generate_customer_metrics(num_rows: int = 8) -> pd.DataFrame:
        """Generate customer segmentation metrics."""
        age_groups = ["18-25", "26-35", "36-45", "46-55", "56-65", "65+"]
        genders = ["M", "F"]
        data = []

        for age_group in age_groups[: num_rows // 2]:
            for gender in genders:
                data.append(
                    {
                        "age_group": age_group,
                        "gender": gender,
                        "customer_count": random.randint(50, 300),
                        "avg_order_value": round(random.uniform(75, 250), 2),
                        "orders_per_customer": round(random.uniform(1.2, 4.5), 1),
                        "lifetime_value": round(random.uniform(200, 1200), 2),
                    }
                )

        return pd.DataFrame(data[:num_rows])

    @staticmethod
    def generate_product_performance(num_rows: int = 15) -> pd.DataFrame:
        """Generate product performance metrics."""
        data = []

        for i in range(num_rows):
            units_sold = random.randint(10, 200)
            avg_price = round(random.uniform(25, 300), 2)
            revenue = round(units_sold * avg_price, 2)

            data.append(
                {
                    "product_id": i + 1,
                    "product_name": f"Product {i+1}",
                    "category": random.choice(
                        ["Electronics", "Clothing", "Home", "Sports"]
                    ),
                    "units_sold": units_sold,
                    "revenue": revenue,
                    "avg_price": avg_price,
                    "profit_margin": round(random.uniform(0.15, 0.45), 3),
                }
            )

        return pd.DataFrame(data)


class LLMResponseGenerator:
    """Generates realistic LLM responses for different contexts."""

    @staticmethod
    def generate_analysis_plan(question: str, tables: List[str] = None) -> str:
        """Generate a realistic analysis plan JSON."""
        if tables is None:
            tables = ["orders", "order_items", "products", "users"]

        # Determine analysis type from question
        question_lower = question.lower()

        if any(word in question_lower for word in ["sales", "revenue", "selling"]):
            task_type = "sales_analysis"
            metrics = ["revenue", "order_count", "avg_order_value"]
            relevant_tables = ["orders", "order_items", "products"]
        elif any(
            word in question_lower for word in ["customer", "user", "demographic"]
        ):
            task_type = "customer_analysis"
            metrics = ["customer_count", "retention_rate", "lifetime_value"]
            relevant_tables = ["users", "orders"]
        elif any(
            word in question_lower for word in ["product", "inventory", "performance"]
        ):
            task_type = "product_analysis"
            metrics = ["units_sold", "profit_margin", "inventory_turnover"]
            relevant_tables = ["products", "order_items"]
        else:
            task_type = "general_analysis"
            metrics = ["count", "trends"]
            relevant_tables = tables[:2]  # Use first two tables

        plan = {
            "task": task_type,
            "tables": relevant_tables,
            "metrics": metrics,
            "time_range": "last_30_days",
            "filters": [f"status = 'Complete'"],
            "grouping": ["category"] if "product" in question_lower else ["date"],
        }

        return json.dumps(plan, ensure_ascii=False)

    @staticmethod
    def generate_sql_query(plan_json: Dict[str, Any], allowed_tables: List[str]) -> str:
        """Generate realistic SQL based on analysis plan."""
        task = plan_json.get("task", "general_analysis")
        tables = plan_json.get("tables", ["orders"])
        metrics = plan_json.get("metrics", ["count"])

        if task == "sales_analysis":
            sql = """
            SELECT 
                p.category,
                COUNT(DISTINCT o.order_id) as order_count,
                SUM(oi.sale_price) as total_revenue,
                AVG(oi.sale_price) as avg_order_value
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            JOIN products p ON oi.product_id = p.id
            WHERE o.status = 'Complete'
              AND o.created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
            GROUP BY p.category
            ORDER BY total_revenue DESC
            LIMIT 1000
            """
        elif task == "customer_analysis":
            sql = """
            SELECT 
                CASE 
                    WHEN u.age < 25 THEN '18-24'
                    WHEN u.age < 35 THEN '25-34'
                    WHEN u.age < 45 THEN '35-44'
                    WHEN u.age < 55 THEN '45-54'
                    ELSE '55+'
                END as age_group,
                u.gender,
                COUNT(DISTINCT u.id) as customer_count,
                AVG(oi.sale_price) as avg_order_value
            FROM users u
            LEFT JOIN orders o ON u.id = o.user_id
            LEFT JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.status = 'Complete'
            GROUP BY age_group, u.gender
            ORDER BY customer_count DESC
            LIMIT 1000
            """
        elif task == "product_analysis":
            sql = """
            SELECT 
                p.name,
                p.category,
                COUNT(oi.id) as units_sold,
                SUM(oi.sale_price) as revenue,
                AVG(oi.sale_price) as avg_price
            FROM products p
            JOIN order_items oi ON p.id = oi.product_id
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.status = 'Complete'
            GROUP BY p.id, p.name, p.category
            ORDER BY revenue DESC
            LIMIT 1000
            """
        else:
            sql = f"""
            SELECT 
                COUNT(*) as total_count,
                status
            FROM {tables[0]}
            GROUP BY status
            ORDER BY total_count DESC
            LIMIT 1000
            """

        return sql.strip()

    @staticmethod
    def generate_business_report(question: str, df_summary: Dict[str, Any]) -> str:
        """Generate realistic business analysis report."""
        rows = df_summary.get("rows", 0)
        columns = df_summary.get("columns", [])

        # Extract key metrics from df_summary
        head_data = df_summary.get("head", [])

        report_parts = []

        # Title based on question
        if "sales" in question.lower():
            report_parts.append("## Sales Analysis Report\n")
        elif "customer" in question.lower():
            report_parts.append("## Customer Analysis Report\n")
        elif "product" in question.lower():
            report_parts.append("## Product Performance Report\n")
        else:
            report_parts.append("## Data Analysis Report\n")

        # Executive Summary
        report_parts.append("### Executive Summary")
        report_parts.append(
            f"Analysis completed on {rows} records across {len(columns)} metrics."
        )

        if head_data:
            # Generate insights based on first few rows
            sample_row = head_data[0]
            if "revenue" in sample_row:
                total_revenue = sum(row.get("revenue", 0) for row in head_data[:5])
                report_parts.append(
                    f"Total revenue from top categories: ${total_revenue:,.2f}"
                )

            if "order_count" in sample_row:
                total_orders = sum(row.get("order_count", 0) for row in head_data[:5])
                report_parts.append(f"Total orders analyzed: {total_orders:,}")

        # Key Findings
        report_parts.append("\n### Key Findings")
        report_parts.append(
            "• Strong performance indicators across all measured dimensions"
        )
        report_parts.append(
            "• Clear patterns emerge in the data suggesting actionable opportunities"
        )
        report_parts.append("• Data quality is high with comprehensive coverage")

        # Recommendations
        report_parts.append("\n### Recommendations")
        report_parts.append("1. Focus on top-performing segments for maximum ROI")
        report_parts.append(
            "2. Investigate underperforming areas for improvement opportunities"
        )
        report_parts.append("3. Implement monitoring for key metrics identified")

        # Next Steps
        report_parts.append("\n### Next Steps")
        report_parts.append("1. Deep dive analysis on highest impact areas")
        report_parts.append("2. Develop targeted action plans based on findings")

        return "\n".join(report_parts)


class ConfigurationGenerator:
    """Generates test configurations and environment setups."""

    @staticmethod
    def generate_test_environment(scenario: str = "default") -> Dict[str, str]:
        """Generate environment variables for different test scenarios."""
        base_config = {
            "GOOGLE_API_KEY": "test-google-api-key",
            "BIGQUERY_PROJECT": "test-project",
            "BIGQUERY_LOCATION": "US",
            "DATASET_ID": "test-dataset.thelook_ecommerce",
            "ALLOWED_TABLES": "orders,order_items,products,users",
            "MAX_BYTES_BILLED": "100000000",
            "MODEL_NAME": "gemini-1.5-pro",
            "AWS_REGION": "us-east-1",
            "BEDROCK_MODEL_ID": "anthropic.claude-v2",
        }

        if scenario == "production":
            base_config.update(
                {
                    "BIGQUERY_PROJECT": "prod-analytics-project",
                    "MAX_BYTES_BILLED": "1000000000",
                    "DATASET_ID": "prod-dataset.ecommerce_analytics",
                }
            )
        elif scenario == "development":
            base_config.update(
                {
                    "BIGQUERY_PROJECT": "dev-analytics-project",
                    "MAX_BYTES_BILLED": "50000000",
                    "MODEL_NAME": "gemini-1.5-flash",
                }
            )
        elif scenario == "minimal":
            # Only essential config
            base_config = {
                "GOOGLE_API_KEY": "test-key",
                "BIGQUERY_PROJECT": "test-project",
                "DATASET_ID": "test.dataset",
                "ALLOWED_TABLES": "orders",
            }

        return base_config

    @staticmethod
    def generate_bigquery_schema() -> List[Dict[str, str]]:
        """Generate comprehensive BigQuery schema for testing."""
        schema = []

        # Orders table
        orders_columns = [
            ("order_id", "INTEGER"),
            ("user_id", "INTEGER"),
            ("status", "STRING"),
            ("created_at", "TIMESTAMP"),
            ("shipped_at", "TIMESTAMP"),
            ("delivered_at", "TIMESTAMP"),
            ("returned_at", "TIMESTAMP"),
            ("num_of_item", "INTEGER"),
        ]

        for col_name, data_type in orders_columns:
            schema.append(
                {
                    "table_name": "orders",
                    "column_name": col_name,
                    "data_type": data_type,
                }
            )

        # Products table
        products_columns = [
            ("id", "INTEGER"),
            ("cost", "FLOAT"),
            ("category", "STRING"),
            ("name", "STRING"),
            ("brand", "STRING"),
            ("retail_price", "FLOAT"),
            ("department", "STRING"),
            ("sku", "STRING"),
            ("distribution_center_id", "INTEGER"),
        ]

        for col_name, data_type in products_columns:
            schema.append(
                {
                    "table_name": "products",
                    "column_name": col_name,
                    "data_type": data_type,
                }
            )

        # Users table
        users_columns = [
            ("id", "INTEGER"),
            ("first_name", "STRING"),
            ("last_name", "STRING"),
            ("email", "STRING"),
            ("age", "INTEGER"),
            ("gender", "STRING"),
            ("state", "STRING"),
            ("city", "STRING"),
            ("country", "STRING"),
            ("created_at", "TIMESTAMP"),
        ]

        for col_name, data_type in users_columns:
            schema.append(
                {"table_name": "users", "column_name": col_name, "data_type": data_type}
            )

        return schema
