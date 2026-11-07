# from pydantic_settings import BaseSettings, SettingsConfigDict


# class Settings(BaseSettings):
#     app_env: str = "development"
#     frontend_origin: str = "http://localhost:5173"

#     paypal_client_id: str = "AVP0O6IlOgvZzX1z1XSJb9hLVbXU7V7TP-dDc_Z8P-38rVj6MsVaDikCYM4RMViBWJ1Ge0mXoYi69sOj"
#     paypal_client_secret: str = "EENC2vp3TC4K0NUjzmKWfSqRUNdpPLHGunQTtV93PnfVYJHR3ORLu626M9881u0FWg3MdMzK2DSJGup-"
#     paypal_base_url: str = "https://api-m.sandbox.paypal.com"

#     channel3_api_key: str = "NkoGy9ogyY5LsFiBkcFsA3jlGzpszogX8RlH7s0c"
#     channel3_base_url: str = "https://api.trychannel3.com/v1"
#     channel3_search_mode: str = "agentic"

#     # Optional Elastic Cloud / Elasticsearch telemetry. App remains usable without it.
#     elasticsearch_url: str = "https://my-elasticsearch-project-ae51df.es.us-central1.gcp.elastic.cloud:443"
#     elastic_api_key: str = "ZG5sM1ZLRUIxOGxvcFFkYjRBY0g6dHB3aXlTUURDY001aXFYbFNGWXcyUQ=="
#     elastic_index_prefix: str = "agentpay"

#     model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


# settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    
    frontend_origin: str = "http://localhost:5173"

    paypal_client_id: str = "AVP0O6IlOgvZzX1z1XSJb9hLVbXU7V7TP-dDc_Z8P-38rVj6MsVaDikCYM4RMViBWJ1Ge0mXoYi69sOj"
    paypal_client_secret: str = "EENC2vp3TC4K0NUjzmKWfSqRUNdpPLHGunQTtV93PnfVYJHR3ORLu626M9881u0FWg3MdMzK2DSJGup-"
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_webhook_id: str = "1EX284995M6017103"
    paypal_mcp_enabled: bool = True
    # Protect operator-only refund/MCP/retry actions. Enter this value in the UI per session; do not expose it via Vite env.
    agentpay_admin_token: str = "db9564baea7c375df8781732c0961a59d91991480814c69b8a418db39d9910b8"
    agentpay_db_path: str = "agentpay.db"

    channel3_api_key: str = "NkoGy9ogyY5LsFiBkcFsA3jlGzpszogX8RlH7s0c"
    channel3_base_url: str = "https://api.trychannel3.com/v1"
    channel3_search_mode: str = "agentic"

    # Optional Elastic Cloud / Elasticsearch telemetry. App remains usable without it.
    elasticsearch_url: str = "https://my-elasticsearch-project-ae51df.es.us-central1.gcp.elastic.cloud:443"
    elastic_api_key: str = "ZG5sM1ZLRUIxOGxvcFFkYjRBY0g6dHB3aXlTUURDY001aXFYbFNGWXcyUQ=="
    elastic_index_prefix: str = "agentpay"

    paypal_subscriptions_client_id: str="BAAKfmJV-ZHa0dYDytcHMrfRw1k-uYpp8v4z2_zx0iBRjjIuy_lYnpGrZYogasr6-qroV8fl1blhiEliTg"
    paypal_subscriptions_secret: str="EN7JEsVSjfreiruAUsJ-Vpuzzged8y5xgdCJoHLXwGeSTcBzat4ZSHsYy_ddfcSwBtbASALEMbVvs2Q_"
    paypal_subscriptions_base_url: str="https://api-m.sandbox.paypal.com"
    # Optional post-purchase Zapier Catch Hook. Keep the URL server-side.
    zapier_webhook_url: str = "https://hooks.zapier.com/hooks/catch/29249023/49bffr0/"
    paypal_subscriptions_plan_id: str = "P-68K945220B872840LMU2C4GA"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    


settings = Settings()