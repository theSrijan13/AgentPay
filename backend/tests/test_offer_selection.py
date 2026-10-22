import unittest
from app.catalog import PRODUCT_BY_ID
from app.main import select_offer
from app.schemas import SelectOfferRequest


class OfferSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_selects_server_cached_channel3_offer_without_trusting_client_price(self):
        test_id = "test-channel3-product-offer-selection"
        PRODUCT_BY_ID[test_id] = {
            "id": test_id,
            "channel3_product_id": "prod_test_123",
            "name": "Test headphones",
            "category": "headphones",
            "price": 99.0,
            "currency": "USD",
            "source": "channel3",
            "availability": "InStock",
            "features": [],
            "offers": [
                {"merchant": "retailer-a.example", "price": 99.0, "currency": "USD", "availability": "InStock", "condition": "new", "url": "https://retailer-a.example/item"},
                {"merchant": "retailer-b.example", "price": 79.0, "currency": "USD", "availability": "InStock", "condition": "new", "url": "https://retailer-b.example/item"},
            ],
        }
        try:
            result = await select_offer(SelectOfferRequest(product_id=test_id, merchant="retailer-b.example"))
            chosen = result["product"]
            self.assertEqual(chosen["merchant"], "retailer-b.example")
            self.assertEqual(chosen["price"], 79.0)
            self.assertEqual(chosen["offer_url"], "https://retailer-b.example/item")
            self.assertEqual(PRODUCT_BY_ID[chosen["id"]]["price"], 79.0)
        finally:
            PRODUCT_BY_ID.pop(test_id, None)
            PRODUCT_BY_ID.pop("channel3-prod_test_123-" + __import__("hashlib").sha1(b"retailer-b.example").hexdigest()[:8], None)

    async def test_demo_product_remains_selectable(self):
        result = await select_offer(SelectOfferRequest(product_id="headphones-01", merchant="AgentPay demo catalog"))
        self.assertEqual(result["source"], "demo")
        self.assertEqual(result["product"]["id"], "headphones-01")


if __name__ == "__main__":
    unittest.main()
