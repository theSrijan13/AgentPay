import asyncio
import unittest
from unittest.mock import patch

from app.elastic_service import ElasticTelemetry
from app.main import public_config


class ElasticTelemetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_fallback_stores_and_searches_events_without_elastic(self):
        telemetry = ElasticTelemetry()
        with patch.object(telemetry, "client", None):
            await telemetry.record("basket_validated", "Basket total checked", {"total": "20.00"})
            await telemetry.record("catalog_search", "Channel3 search completed", {"source": "channel3"})
            result = await telemetry.search("basket", 10)
        self.assertEqual(result["source"], "memory")
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["event_type"], "basket_validated")

    async def test_memory_history_is_bounded(self):
        telemetry = ElasticTelemetry()
        for i in range(510):
            await telemetry.record("test_event", f"event {i}")
        self.assertEqual(len(telemetry.memory_events), 500)

    async def test_missing_elastic_settings_report_configuration_guidance(self):
        telemetry = ElasticTelemetry()
        with patch("app.elastic_service.settings.elasticsearch_url", ""), \
             patch("app.elastic_service.settings.elastic_api_key", ""):
            await telemetry.start()
            status = telemetry.status()
        self.assertFalse(status["configured"])
        self.assertIn("ELASTICSEARCH_URL", status["message"])

    def test_public_config_exposes_client_id_but_never_secret(self):
        from app.config import settings
        with patch.object(settings, "paypal_client_id", "public-client-id"), \
             patch.object(settings, "paypal_client_secret", "private-secret"), \
             patch.object(settings, "channel3_api_key", "channel3-private-key"):
            data = public_config()
        self.assertEqual(data["paypal_client_id"], "public-client-id")
        self.assertNotIn("paypal_client_secret", data)
        self.assertNotIn("private-secret", repr(data))
        self.assertNotIn("channel3-private-key", repr(data))

    def test_authentication_errors_are_actionable_without_echoing_secrets(self):
        class FakeMeta:
            status = 401
        class AuthenticationError(Exception):
            meta = FakeMeta()
        hint = ElasticTelemetry._safe_error_hint(AuthenticationError("sensitive"))
        self.assertIn("API key", hint)
        self.assertNotIn("sensitive", hint)


if __name__ == "__main__":
    unittest.main()
