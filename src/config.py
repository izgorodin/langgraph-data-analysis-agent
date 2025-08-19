import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    # Note: values come from environment variables; no hardcoded secrets used.
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    bq_project: str = os.getenv("BIGQUERY_PROJECT", "")
    bq_location: str = os.getenv("BIGQUERY_LOCATION", "US")
    dataset_id: str = os.getenv("DATASET_ID", "bigquery-public-data.thelook_ecommerce")
    allowed_tables: tuple[str, ...] = tuple(
        t.strip()
        for t in os.getenv("ALLOWED_TABLES", "orders,order_items,products,users").split(
            ","
        )
    )
    max_bytes_billed: int = int(os.getenv("MAX_BYTES_BILLED", "100000000"))
    model_name: str = os.getenv("MODEL_NAME", "gemini-1.5-pro")
    aws_region: str = os.getenv("AWS_REGION", "eu-west-1")
    bedrock_model_id: str = os.getenv("BEDROCK_MODEL_ID", "")


settings = Settings()
