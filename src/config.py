import os
from dataclasses import dataclass, field


@dataclass
class Settings:

    google_api_key: str = field(default="")
    bq_project: str = field(default="")
    bq_location: str = field(default="US")
    dataset_id: str = field(default="bigquery-public-data.thelook_ecommerce")
    allowed_tables: tuple[str, ...] = field(
        default_factory=lambda: ("orders", "order_items", "products", "users")
    max_bytes_billed: int = field(default=100000000)
    model_name: str = field(default="gemini-1.5-pro")
    aws_region: str = field(default="eu-west-1")
    bedrock_model_id: str = field(default="")

    def __post_init__(self) -> None:
        # Read dynamically from environment (supports tests using patch.dict)
        self.google_api_key = os.getenv("GOOGLE_API_KEY", "")
        self.bq_project = os.getenv("BIGQUERY_PROJECT", "")
        self.bq_location = os.getenv("BIGQUERY_LOCATION", "US")
        self.dataset_id = os.getenv(
            "DATASET_ID", "bigquery-public-data.thelook_ecommerce"
        )

        if "ALLOWED_TABLES" in os.environ:
            raw = os.getenv("ALLOWED_TABLES", "")
            self.allowed_tables = tuple(t.strip() for t in raw.split(","))
        else:
            self.allowed_tables = ("orders", "order_items", "products", "users")

        max_bytes_str = os.getenv("MAX_BYTES_BILLED", "100000000")
        try:
            self.max_bytes_billed = int(max_bytes_str)
        except ValueError as e:
            # Surface invalid configuration as ValueError (tests expect this)
            raise ValueError("MAX_BYTES_BILLED must be an integer") from e

        self.model_name = os.getenv("MODEL_NAME", "gemini-1.5-pro")
        self.aws_region = os.getenv("AWS_REGION", "eu-west-1")
        self.bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", "")


settings = Settings()
