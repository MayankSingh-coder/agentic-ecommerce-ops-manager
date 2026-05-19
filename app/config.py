import os
import sys

from dotenv import load_dotenv


if "pytest" not in sys.modules:
    load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./ecommerce_ops.db")
        self.llm_gateway_provider = os.getenv("LLM_GATEWAY_PROVIDER", "prompt")
        self.litellm_base_url = os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
        self.litellm_api_key = os.getenv("LITELLM_API_KEY", "")
        self.litellm_timeout_seconds = float(os.getenv("LITELLM_TIMEOUT_SECONDS", "30"))
        self.ecommerce_ops_api_key = os.getenv("ECOMMERCE_OPS_API_KEY", "")
        self.temporal_address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
        self.temporal_namespace = os.getenv("TEMPORAL_NAMESPACE", "default")
        self.temporal_task_queue = os.getenv("TEMPORAL_TASK_QUEUE", "ecommerce-ops-task-queue")


settings = Settings()
