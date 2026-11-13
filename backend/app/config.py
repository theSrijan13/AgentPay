from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    app_env: str = "development"
    frontend_origin: str = "http://localhost:5173"

    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_webhook_id: str = ""
    paypal_mcp_enabled: bool = True

    agentpay_admin_token: str = ""
    agentpay_db_path: str = "agentpay.db"

    channel3_api_key: str = ""
    channel3_base_url: str = "https://api.trychannel3.com/v1"
    channel3_search_mode: str = "agentic"

    elasticsearch_url: str = ""
    elastic_api_key: str = ""
    elastic_index_prefix: str = "agentpay"

    paypal_subscriptions_client_id: str = ""
    paypal_subscriptions_secret: str = ""
    paypal_subscriptions_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_subscriptions_plan_id: str = ""

    zapier_webhook_url: str = ""

    model_config = SettingsConfigDict(
        env_file=(str(ENV_PATH), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
