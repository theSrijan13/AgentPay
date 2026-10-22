from typing import Any

# Demo data only. All prices are USD because INR is not listed among PayPal's
# standard supported Checkout currencies. These are illustrative, not live prices.
PRODUCTS: list[dict[str, Any]] = [
    {"id": "headphones-01", "name": "Wave ANC Headphones", "category": "headphones", "price": 59.99, "currency": "USD", "rating": 4.5, "review_count": 820, "stock": 12, "features": ["active noise cancellation", "30-hour battery", "USB-C"]},
    {"id": "headphones-02", "name": "StudioLite Wireless Headphones", "category": "headphones", "price": 39.99, "currency": "USD", "rating": 4.2, "review_count": 510, "stock": 8, "features": ["40-hour battery", "foldable", "USB-C"]},
    {"id": "keyboard-01", "name": "KeyPro Wireless Keyboard", "category": "keyboard", "price": 29.99, "currency": "USD", "rating": 4.4, "review_count": 360, "stock": 15, "features": ["wireless", "compact", "multi-device"]},
    {"id": "mouse-01", "name": "ErgoClick Wireless Mouse", "category": "mouse", "price": 17.99, "currency": "USD", "rating": 4.6, "review_count": 640, "stock": 20, "features": ["ergonomic", "wireless", "adjustable DPI"]},
    {"id": "stand-01", "name": "FlexRise Laptop Stand", "category": "accessories", "price": 14.99, "currency": "USD", "rating": 4.3, "review_count": 275, "stock": 18, "features": ["adjustable", "aluminium", "foldable"]},
    {"id": "webcam-01", "name": "ClearMeet HD Webcam", "category": "webcam", "price": 24.99, "currency": "USD", "rating": 4.1, "review_count": 190, "stock": 7, "features": ["1080p", "privacy cover", "USB"]},
]

PRODUCT_BY_ID: dict[str, dict[str, Any]] = {product["id"]: product for product in PRODUCTS}


def remember_channel3_products(products: list[dict[str, Any]]) -> None:
    """Cache Channel3 results server-side so validation never trusts browser prices."""
    for product in products:
        if product.get("id") and product.get("source") == "channel3":
            PRODUCT_BY_ID[product["id"]] = product


def search_products(query: str = "", max_price: float | None = None) -> list[dict[str, Any]]:
    terms = [term.lower() for term in query.split() if len(term) > 2]
    results = []
    for product in PRODUCTS:
        haystack = " ".join([product["name"], product["category"], *product["features"]]).lower()
        if terms and not any(term in haystack for term in terms):
            continue
        if max_price is not None and product["price"] > max_price:
            continue
        results.append(product)
    return sorted(results, key=lambda p: (p["rating"], p["review_count"]), reverse=True)
