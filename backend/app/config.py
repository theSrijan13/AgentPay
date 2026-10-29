

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    frontend_origin: str = "http://localhost:5173"

    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_webhook_id: str = ""
    paypal_mcp_enabled: bool = True
    # Protect operator-only refund/MCP/retry actions. Enter this value in the UI per session; do not expose it via Vite env.
    agentpay_admin_token: str = ""
    agentpay_db_path: str = "agentpay.db"

    channel3_api_key: str = ""
    channel3_base_url: str = "https://api.trychannel3.com/v1"
    channel3_search_mode: str = "agentic"

    # Optional Elastic Cloud / Elasticsearch telemetry. App remains usable without it.
    elasticsearch_url: str = ""
    elastic_api_key: str = ""
    elastic_index_prefix: str = "agentpay"

    # Optional post-purchase Zapier Catch Hook. Keep the URL server-side.
    zapier_webhook_url: str = "https://hooks.zapier.com/hooks/catch/29249023/49bffr0/"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


settings = Settings()
