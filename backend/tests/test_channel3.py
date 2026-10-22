import asyncio
import unittest
from unittest.mock import patch

from app.channel3 import _map_products, _image_url


class Channel3MappingTests(unittest.TestCase):
    def test_chooses_lowest_in_stock_usd_offer_below_budget(self):
        sample = [{
            "id": "product-1", "title": "Wireless Headphones",
            "brands": [{"name": "Example Brand"}],
            "images": [{"url": "https://images.example.test/headphones.jpg", "cleaned_url": None}],
            "category": {"title": "Headphones"},
            "key_features": ["Bluetooth", "Noise cancelling"],
            "offers": [
                {"domain": "expensive.example", "url": "https://buy.trychannel3.com/expensive", "availability": "InStock", "price": {"amount": 79.00, "currency": "USD"}},
                {"domain": "cheap.example", "url": "https://buy.trychannel3.com/cheap", "availability": "InStock", "price": {"amount": 49.99, "currency": "USD"}},
                {"domain": "gb.example", "url": "https://buy.trychannel3.com/gb", "availability": "InStock", "price": {"amount": 35.00, "currency": "GBP"}},
                {"domain": "oos.example", "url": "https://buy.trychannel3.com/oos", "availability": "OutOfStock", "price": {"amount": 25.00, "currency": "USD"}},
            ],
        }]
        result = _map_products(sample, 50)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["price"], 49.99)
        self.assertEqual(result[0]["currency"], "USD")
        self.assertEqual(result[0]["merchant"], "cheap.example")
        self.assertEqual(result[0]["source"], "channel3")
        self.assertEqual(result[0]["image_url"], "https://images.example.test/headphones.jpg")

    def test_omits_non_usd_and_out_of_budget_offers(self):
        sample = [{"id": "product-2", "title": "Something", "offers": [
            {"domain": "uk.example", "url": "https://buy.trychannel3.com/uk", "availability": "InStock", "price": {"amount": 15, "currency": "GBP"}},
            {"domain": "us.example", "url": "https://buy.trychannel3.com/us", "availability": "InStock", "price": {"amount": 100, "currency": "USD"}},
        ]}]
        self.assertEqual(_map_products(sample, 50), [])

    def test_keeps_multiple_eligible_offers_for_comparison(self):
        product = {"id": "compare-1", "title": "Comparison Headphones", "images": [], "offers": [
            {"domain": "store-a.example", "url": "https://buy.trychannel3.com/a", "availability": "InStock", "price": {"price": 79.00, "currency": "USD"}},
            {"domain": "store-b.example", "url": "https://buy.trychannel3.com/b", "availability": "InStock", "price": {"price": 59.00, "currency": "USD"}},
            {"domain": "store-c.example", "url": "https://buy.trychannel3.com/c", "availability": "OutOfStock", "price": {"price": 29.00, "currency": "USD"}},
        ]}
        result = _map_products([product], 80)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["price"], 59.0)
        self.assertEqual(len(result[0]["offers"]), 2)
        self.assertEqual(result[0]["offers"][0]["merchant"], "store-b.example")

    def test_prefers_cleaned_main_or_hero_image(self):
        product = {"images": [
            {"url": "https://img.example/lifestyle.jpg", "shot_type": "lifestyle"},
            {"url": "https://img.example/hero.jpg", "shot_type": "hero", "cleaned_url": "https://img.example/hero-clean.jpg", "is_main_image": True},
        ]}
        self.assertEqual(_image_url(product), "https://img.example/hero-clean.jpg")


class Channel3RequestTests(unittest.TestCase):
    def test_search_requests_agentic_mode_and_anonymous_attribution_without_locale_body_fields(self):
        from app import channel3
        sample_product = {"id": "mode-test", "title": "Agentic Search Product", "images": [], "offers": [{
            "domain": "store.example", "url": "https://buy.trychannel3.com/test", "availability": "InStock", "price": {"price": 42.5, "currency": "USD"},
        }]}
        captured = {}

        class FakeResponse:
            def raise_for_status(self): pass
            def json(self): return {"products": [sample_product]}

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def post(self, url, headers, json):
                captured.update(url=url, headers=headers, json=json)
                return FakeResponse()

        with patch.object(channel3.settings, "channel3_api_key", "test-key"), \
             patch.object(channel3.settings, "channel3_search_mode", "agentic"), \
             patch.object(channel3.httpx, "AsyncClient", FakeAsyncClient):
            channel3._SEARCH_CACHE.clear()
            products = asyncio.run(channel3.search_channel3("wireless headphones under $80", 80))
        self.assertEqual(len(products), 1)
        self.assertEqual(captured["url"], "https://api.trychannel3.com/v1/search")
        self.assertEqual(captured["headers"]["x-api-key"], "test-key")
        self.assertEqual(captured["headers"]["x-user-id"], "agentpay-demo-user")
        self.assertEqual(captured["json"]["config"]["mode"], "agentic")
        self.assertNotIn("currency", captured["json"])
        self.assertNotIn("country", captured["json"])
        self.assertNotIn("language", captured["json"])
        self.assertEqual(captured["json"]["filters"]["availability"], ["InStock"])

    def test_conversational_turn_parses_product_cards_and_saves_conversation_id(self):
        from app import channel3
        product = {"id": "chat-product", "title": "Chat Result Headphones", "images": [], "offers": [{
            "domain": "store.example", "url": "https://buy.trychannel3.com/chat", "availability": "InStock", "price": {"amount": 40, "currency": "USD"},
        }]}
        captured = {}
        payload = {"conversation_id": "conv_test_123", "message": {"role": "assistant", "parts": [
            {"type": "text", "text": "Here are two options."},
            {"type": "tool", "tool_name": "search_products", "output": {"products": [product]}},
        ]}, "usage": {"credits_charged": 2, "searches_run": 1}}

        class FakeResponse:
            def raise_for_status(self): pass
            def json(self): return payload

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def post(self, url, headers, json):
                captured.update(url=url, headers=headers, json=json)
                return FakeResponse()

        with patch.object(channel3.settings, "channel3_api_key", "test-key"), \
             patch.object(channel3.httpx, "AsyncClient", FakeAsyncClient):
            result = asyncio.run(channel3.conversational_turn("show cheaper headphones", max_price=80, user_id="agentpay-test"))
        self.assertEqual(captured["url"], "https://api.trychannel3.com/v1/conversations")
        self.assertEqual(captured["headers"]["x-user-id"], "agentpay-test")
        self.assertEqual(captured["json"]["stream"], False)
        self.assertEqual(captured["json"]["config"]["mode"], "agentic")
        self.assertEqual(result["conversation_id"], "conv_test_123")
        self.assertEqual(result["text"], "Here are two options.")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["usage"]["credits_charged"], 2)


if __name__ == "__main__":
    unittest.main()
