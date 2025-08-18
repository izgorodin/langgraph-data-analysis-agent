import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    google_api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    bq_project: str = field(default_factory=lambda: os.getenv("BIGQUERY_PROJECT", ""))
    bq_location: str = field(default_factory=lambda: os.getenv("BIGQUERY_LOCATION", "US"))
    dataset_id: str = field(default_factory=lambda: os.getenv("DATASET_ID", "bigquery-public-data.thelook_ecommerce"))
    allowed_tables: tuple[str, ...] = field(default_factory=lambda: tuple(t.strip() for t in os.getenv("ALLOWED_TABLES", "orders,order_items,products,users").split(",")))
    max_bytes_billed: int = field(default_factory=lambda: int(os.getenv("MAX_BYTES_BILLED", "100000000")))
    model_name: str = field(default_factory=lambda: os.getenv("MODEL_NAME", "gemini-1.5-pro"))
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "eu-west-1"))
    bedrock_model_id: str = field(default_factory=lambda: os.getenv("BEDROCK_MODEL_ID", ""))

settings = Settings()
