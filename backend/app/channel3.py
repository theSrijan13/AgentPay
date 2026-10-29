# """Channel3 product discovery integration.

# Channel3 is used for discovery and retailer offer links. AgentPay's PayPal flow is a
# Sandbox demo transaction; it does not purchase/fulfil goods at the retailer.
# """
# from __future__ import annotations

# import hashlib
# import time
# from typing import Any

# import httpx
# from .config import settings
# from .catalog import remember_channel3_products

# _CACHE_TTL_SECONDS = 300
# _SEARCH_CACHE: dict[tuple[str, float | None, int], tuple[float, list[dict[str, Any]]]] = {}

# class Channel3NotConfigured(RuntimeError):
#     pass

# class Channel3SearchError(RuntimeError):
#     pass

# def _price_fields(offer: dict[str, Any]) -> tuple[float | None, str | None]:
#     price = offer.get("price")
#     if isinstance(price, dict):
#         amount = price.get("amount", price.get("price", price.get("value")))
#         currency = price.get("currency") or offer.get("currency")
#     else:
#         amount = price if price is not None else offer.get("amount", offer.get("value"))
#         currency = offer.get("currency")
#     try:
#         amount = float(amount)
#     except (TypeError, ValueError):
#         return None, str(currency).upper() if currency else None
#     return amount, str(currency).upper() if currency else None

# def _image_url(product: dict[str, Any]) -> str | None:
#     """Prefer a main/hero image, and use cleaned_url for consistent product cards."""
#     images = product.get("images") or []
#     if isinstance(images, list):
#         candidates = [image for image in images if isinstance(image, dict)]
#         candidates.sort(key=lambda image: (
#             not bool(image.get("is_main_image")),
#             image.get("shot_type") != "hero",
#             not bool(image.get("cleaned_url")),
#         ))
#         for image in candidates:
#             value = image.get("cleaned_url") or image.get("url")
#             if isinstance(value, str) and value.startswith("https://"):
#                 return value
#         for image in images:
#             if isinstance(image, str) and image.startswith("https://"):
#                 return image
#     value = product.get("image_url") or product.get("image")
#     return value if isinstance(value, str) and value.startswith("https://") else None

# def _brand_name(product: dict[str, Any]) -> str | None:
#     brands = product.get("brands") or []
#     if isinstance(brands, list) and brands:
#         first = brands[0]
#         if isinstance(first, dict):
#             return first.get("name")
#         if isinstance(first, str):
#             return first
#     brand = product.get("brand")
#     return brand.get("name") if isinstance(brand, dict) else brand if isinstance(brand, str) else None

# def _category_name(product: dict[str, Any]) -> str:
#     category = product.get("category")
#     if isinstance(category, dict):
#         return str(category.get("title") or category.get("slug") or "product")
#     return str(category or "product")

# def _map_products(raw_products: list[dict[str, Any]], max_price: float | None) -> list[dict[str, Any]]:
#     mapped: list[dict[str, Any]] = []
#     for raw in raw_products:
#         offers = raw.get("offers") or []
#         eligible_offers: list[dict[str, Any]] = []
#         for offer in offers:
#             if not isinstance(offer, dict):
#                 continue
#             amount, currency = _price_fields(offer)
#             url = offer.get("url")
#             availability = offer.get("availability")
#             # The AgentPay payment demo currently uses USD. Do not convert currencies
#             # implicitly or treat sold-out offers as purchasable.
#             if amount is None or currency != "USD" or amount <= 0:
#                 continue
#             if availability != "InStock":
#                 continue
#             if max_price is not None and amount > max_price:
#                 continue
#             if not isinstance(url, str) or not url.startswith("https://"):
#                 continue
#             eligible_offers.append({
#                 "merchant": str(offer.get("domain") or "Retailer"),
#                 "price": round(amount, 2),
#                 "currency": currency,
#                 "availability": availability,
#                 "condition": offer.get("condition") or "unknown",
#                 "url": url,
#             })
#         if not eligible_offers:
#             continue
#         eligible_offers.sort(key=lambda offer: offer["price"])
#         offer = eligible_offers[0]
#         product_source_id = str(raw.get("id") or raw.get("product_id") or "")
#         if not product_source_id:
#             continue
#         domain = str(offer.get("merchant") or "retailer").lower()
#         suffix = hashlib.sha1(domain.encode("utf-8")).hexdigest()[:8]
#         item_id = f"channel3-{product_source_id}-{suffix}"
#         features = raw.get("key_features") or raw.get("features") or []
#         if not isinstance(features, list):
#             features = []
#         mapped.append({
#             "id": item_id,
#             "channel3_product_id": product_source_id,
#             "name": str(raw.get("title") or raw.get("name") or "Untitled product"),
#             "category": _category_name(raw),
#             "brand": _brand_name(raw),
#             "price": offer["price"],
#             "currency": "USD",
#             "rating": None,
#             "review_count": None,
#             # Channel3 reports availability, not precise inventory quantity.
#             "stock": None,
#             "availability": "InStock",
#             "features": [str(v) for v in features[:5]],
#             "description": raw.get("description"),
#             "image_url": _image_url(raw),
#             "offer_url": offer["url"],
#             "merchant": offer["merchant"],
#             "offers": eligible_offers,
#             "source": "channel3",
#         })
#     return mapped


# async def refresh_channel3_offer(product: dict[str, Any]) -> dict[str, Any]:
#     """Refresh a selected product's retailer offer before basket validation/payment.

#     Channel3's product-detail endpoint is used to refresh offer price and availability.
#     The selected merchant is retained; if that offer has disappeared or is no longer
#     in stock, AgentPay asks the shopper to search again instead of silently switching.
#     """
#     if not settings.channel3_api_key.strip():
#         raise Channel3NotConfigured("CHANNEL3_API_KEY is not set")
#     channel3_id = product.get("channel3_product_id")
#     if not channel3_id:
#         return product
#     url = f"{settings.channel3_base_url.rstrip('/')}/products/{channel3_id}"
#     try:
#         async with httpx.AsyncClient(timeout=20) as client:
#             response = await client.get(
#                 url,
#                 headers={"x-api-key": settings.channel3_api_key, "x-user-id": "agentpay-demo-user"},
#                 params={"country": "US", "language": "en", "currency": "USD"},
#             )
#             response.raise_for_status()
#             raw = response.json()
#     except httpx.HTTPStatusError as exc:
#         if exc.response.status_code in (401, 403):
#             raise Channel3SearchError("Channel3 rejected the API key while refreshing an offer.") from exc
#         if exc.response.status_code == 404:
#             raise Channel3SearchError("The selected product is no longer available in Channel3. Search again.") from exc
#         raise Channel3SearchError(f"Channel3 product refresh returned HTTP {exc.response.status_code}.") from exc
#     except httpx.RequestError as exc:
#         raise Channel3SearchError("Could not refresh the retailer offer from Channel3. Check the connection and retry.") from exc
#     except ValueError as exc:
#         raise Channel3SearchError("Channel3 returned unreadable product details.") from exc

#     if isinstance(raw, dict) and isinstance(raw.get("product"), dict):
#         raw = raw["product"]
#     if not isinstance(raw, dict):
#         raise Channel3SearchError("Channel3 returned an unexpected product-detail response.")

#     wanted_merchant = str(product.get("merchant") or "").lower()
#     fresh_offers: list[dict[str, Any]] = []
#     chosen: dict[str, Any] | None = None
#     for offer in raw.get("offers") or []:
#         if not isinstance(offer, dict):
#             continue
#         amount, currency = _price_fields(offer)
#         offer_url = offer.get("url")
#         availability = offer.get("availability")
#         domain = str(offer.get("domain") or "Retailer")
#         if amount is None or currency != "USD" or amount <= 0 or not isinstance(offer_url, str) or not offer_url.startswith("https://"):
#             continue
#         if availability == "InStock":
#             fresh_offers.append({
#                 "merchant": domain,
#                 "price": round(amount, 2),
#                 "currency": currency,
#                 "availability": availability,
#                 "condition": offer.get("condition") or "unknown",
#                 "url": offer_url,
#             })
#         if domain.lower() == wanted_merchant and availability == "InStock" and currency == "USD":
#             chosen = {
#                 "price": round(amount, 2),
#                 "currency": currency,
#                 "offer_url": offer_url,
#                 "merchant": domain,
#             }

#     if chosen is None:
#         raise Channel3SearchError("The selected retailer offer is no longer in stock or no longer has a USD price. Search again before checkout.")
#     fresh_offers.sort(key=lambda offer: offer["price"])
#     updated = {**product, **chosen, "availability": "InStock", "offers": fresh_offers}
#     remember_channel3_products([updated])
#     return updated


# async def search_channel3(query: str, max_price: float | None = None, limit: int = 12) -> list[dict[str, Any]]:
#     if not settings.channel3_api_key.strip():
#         raise Channel3NotConfigured("CHANNEL3_API_KEY is not set")

#     clean_query = " ".join(query.split()) or "wireless headphones keyboards mice laptop stands webcams"
#     cache_key = (clean_query.lower(), round(max_price, 2) if max_price is not None else None, limit)
#     cached = _SEARCH_CACHE.get(cache_key)
#     if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
#         return cached[1]

#     filters: dict[str, Any] = {"availability": ["InStock"]}
#     if max_price is not None:
#         filters["price"] = {"max_price": max_price}
#     payload = {
#         "query": clean_query,
#         "filters": filters,
#         "limit": max(1, min(limit, 20)),
#         # The live REST endpoint currently rejects locale fields at the top-level
#         # with HTTP 422 for this integration. Channel3's default locale is en/US/USD,
#         # which matches AgentPay's Sandbox demo. Keep agentic mode inside config.
#         "config": {"mode": settings.channel3_search_mode},
#     }
#     url = f"{settings.channel3_base_url.rstrip('/')}/search"
#     try:
#         async with httpx.AsyncClient(timeout=20) as client:
#             response = await client.post(
#                 url,
#                 headers={"x-api-key": settings.channel3_api_key, "x-user-id": "agentpay-demo-user", "content-type": "application/json"},
#                 json=payload,
#             )
#             response.raise_for_status()
#             body = response.json()
#     except httpx.HTTPStatusError as exc:
#         if exc.response.status_code in (401, 403):
#             raise Channel3SearchError("Channel3 rejected the API key. Check CHANNEL3_API_KEY.") from exc
#         detail_summary = ""
#         # Surface safe schema details (field path + message) without echoing inputs,
#         # which could contain private data. This helps diagnose future API changes.
#         try:
#             error_body = exc.response.json()
#             details = error_body.get("detail") if isinstance(error_body, dict) else None
#             if isinstance(details, list):
#                 parts = []
#                 for item in details[:5]:
#                     if not isinstance(item, dict):
#                         continue
#                     location = ".".join(str(bit) for bit in item.get("loc", []))
#                     message = str(item.get("msg") or "request rejected")
#                     parts.append(f"{location}: {message}" if location else message)
#                 if parts:
#                     detail_summary = " Details: " + "; ".join(parts)
#         except (ValueError, TypeError):
#             pass
#         raise Channel3SearchError(
#             f"Channel3 search returned HTTP {exc.response.status_code}.{detail_summary}"
#         ) from exc
#     except httpx.RequestError as exc:
#         raise Channel3SearchError("Could not reach Channel3. Check network access and try again.") from exc
#     except ValueError as exc:
#         raise Channel3SearchError("Channel3 returned an unreadable response.") from exc

#     raw_products = body.get("products") if isinstance(body, dict) else None
#     if not isinstance(raw_products, list):
#         raw_products = body.get("results", []) if isinstance(body, dict) else []
#     products = _map_products([item for item in raw_products if isinstance(item, dict)], max_price)
#     if products:
#         remember_channel3_products(products)
#     _SEARCH_CACHE[cache_key] = (time.monotonic(), products)
#     return products


# async def conversational_turn(
#     message: str,
#     conversation_id: str | None = None,
#     max_price: float | None = None,
#     user_id: str = "agentpay-demo-user",
# ) -> dict[str, Any]:
#     """Run one non-streaming Channel3 Conversational Agent turn.

#     The vendor key remains on the server. Channel3's response may contain text plus
#     structured product cards embedded in tool parts; both are normalized here.
#     """
#     if not settings.channel3_api_key.strip():
#         raise Channel3NotConfigured("CHANNEL3_API_KEY is not set")

#     filters: dict[str, Any] = {"availability": ["InStock"]}
#     if max_price is not None:
#         filters["price"] = {"max_price": max_price}

#     payload: dict[str, Any] = {
#         "message": {"role": "user", "parts": [{"type": "text", "text": message.strip()}]},
#         "filters": filters,
#         "config": {"mode": settings.channel3_search_mode},
#         "stream": False,
#     }
#     if conversation_id:
#         payload["conversation_id"] = conversation_id

#     url = f"{settings.channel3_base_url.rstrip('/')}/conversations"
#     try:
#         async with httpx.AsyncClient(timeout=45) as client:
#             response = await client.post(
#                 url,
#                 headers={
#                     "x-api-key": settings.channel3_api_key,
#                     "x-user-id": (user_id or "agentpay-demo-user")[:100],
#                     "content-type": "application/json",
#                 },
#                 json=payload,
#             )
#             response.raise_for_status()
#             body = response.json()
#     except httpx.HTTPStatusError as exc:
#         if exc.response.status_code in (401, 403):
#             raise Channel3SearchError("Channel3 rejected the API key for Conversational Agent. Check CHANNEL3_API_KEY.") from exc
#         summary = ""
#         try:
#             error_body = exc.response.json()
#             if isinstance(error_body, dict):
#                 err = error_body.get("error")
#                 if isinstance(err, dict):
#                     summary = str(err.get("message") or err.get("code") or "")[:300]
#                 elif isinstance(error_body.get("detail"), str):
#                     summary = error_body["detail"][:300]
#         except (ValueError, TypeError):
#             pass
#         suffix = f" Details: {summary}" if summary else ""
#         raise Channel3SearchError(f"Channel3 Conversational Agent returned HTTP {exc.response.status_code}.{suffix}") from exc
#     except httpx.RequestError as exc:
#         raise Channel3SearchError("Could not reach Channel3 Conversational Agent. Check network access and retry.") from exc
#     except ValueError as exc:
#         raise Channel3SearchError("Channel3 Conversational Agent returned an unreadable response.") from exc

#     if not isinstance(body, dict):
#         raise Channel3SearchError("Channel3 Conversational Agent returned an unexpected response.")

#     raw_message = body.get("message")
#     if not isinstance(raw_message, dict):
#         raw_message = body.get("assistant_message") if isinstance(body.get("assistant_message"), dict) else {}
#     # Be tolerant of TurnResult wrappers while keeping the documented top-level
#     # JSON response as the preferred shape.
#     if not raw_message and isinstance(body.get("turn"), dict):
#         nested_turn = body["turn"]
#         raw_message = nested_turn.get("message") if isinstance(nested_turn.get("message"), dict) else {}
#     parts = raw_message.get("parts") if isinstance(raw_message, dict) else []
#     assistant_text: list[str] = []
#     raw_products: list[dict[str, Any]] = []
#     if isinstance(parts, list):
#         for part in parts:
#             if not isinstance(part, dict):
#                 continue
#             if part.get("type") == "text" and isinstance(part.get("text"), str):
#                 assistant_text.append(part["text"])
#             output = part.get("output")
#             if isinstance(output, dict):
#                 cards = output.get("products")
#                 if isinstance(cards, list):
#                     raw_products.extend(item for item in cards if isinstance(item, dict))
#                 things = output.get("things")
#                 if isinstance(things, list):
#                     for thing in things:
#                         if isinstance(thing, dict) and isinstance(thing.get("matches"), list):
#                             raw_products.extend(item for item in thing["matches"] if isinstance(item, dict))

#     # A few API responses may include products at the root level as well.
#     root_products = body.get("products")
#     if isinstance(root_products, list):
#         raw_products.extend(item for item in root_products if isinstance(item, dict))
#     # Deduplicate products by their canonical Channel3 product id.
#     deduped: dict[str, dict[str, Any]] = {}
#     for product in raw_products:
#         product_id = str(product.get("id") or product.get("product_id") or "")
#         if product_id:
#             deduped[product_id] = product
#     mapped = _map_products(list(deduped.values()), max_price)
#     if mapped:
#         remember_channel3_products(mapped)

#     conversation = body.get("conversation") if isinstance(body.get("conversation"), dict) else {}
#     turn = body.get("turn") if isinstance(body.get("turn"), dict) else {}
#     conversation_id_value = (
#         body.get("conversation_id") or conversation.get("id") or turn.get("conversation_id")
#     )
#     if not conversation_id_value and isinstance(body.get("id"), str) and body["id"].startswith("conv_"):
#         conversation_id_value = body["id"]
#     # Never mistake a turn ID or message ID for a conversation ID.
#     if isinstance(conversation_id_value, str) and not conversation_id_value.startswith("conv_"):
#         conversation_id_value = None

#     usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
#     return {
#         "conversation_id": conversation_id_value if isinstance(conversation_id_value, str) else None,
#         "text": "\n".join(piece.strip() for piece in assistant_text if piece.strip()),
#         "items": mapped,
#         "usage": {
#             "credits_charged": usage.get("credits_charged"),
#             "searches_run": usage.get("searches_run"),
#         },
#     }

"""Channel3 product discovery integration.

Channel3 is used for discovery and retailer offer links. AgentPay's PayPal flow is a
Sandbox demo transaction; it does not purchase/fulfil goods at the retailer.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

import httpx
from .config import settings
from .catalog import remember_channel3_products

_CACHE_TTL_SECONDS = 300
_SEARCH_CACHE: dict[tuple[str, float | None, int], tuple[float, list[dict[str, Any]]]] = {}

class Channel3NotConfigured(RuntimeError):
    pass

class Channel3SearchError(RuntimeError):
    pass

def _price_fields(offer: dict[str, Any]) -> tuple[float | None, str | None]:
    price = offer.get("price")
    if isinstance(price, dict):
        amount = price.get("amount", price.get("price", price.get("value")))
        currency = price.get("currency") or offer.get("currency")
    else:
        amount = price if price is not None else offer.get("amount", offer.get("value"))
        currency = offer.get("currency")
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return None, str(currency).upper() if currency else None
    return amount, str(currency).upper() if currency else None

def _image_url(product: dict[str, Any]) -> str | None:
    """Prefer a main/hero image, and use cleaned_url for consistent product cards."""
    images = product.get("images") or []
    if isinstance(images, list):
        candidates = [image for image in images if isinstance(image, dict)]
        candidates.sort(key=lambda image: (
            not bool(image.get("is_main_image")),
            image.get("shot_type") != "hero",
            not bool(image.get("cleaned_url")),
        ))
        for image in candidates:
            value = image.get("cleaned_url") or image.get("url")
            if isinstance(value, str) and value.startswith("https://"):
                return value
        for image in images:
            if isinstance(image, str) and image.startswith("https://"):
                return image
    value = product.get("image_url") or product.get("image")
    return value if isinstance(value, str) and value.startswith("https://") else None

def _brand_name(product: dict[str, Any]) -> str | None:
    brands = product.get("brands") or []
    if isinstance(brands, list) and brands:
        first = brands[0]
        if isinstance(first, dict):
            return first.get("name")
        if isinstance(first, str):
            return first
    brand = product.get("brand")
    return brand.get("name") if isinstance(brand, dict) else brand if isinstance(brand, str) else None

def _category_name(product: dict[str, Any]) -> str:
    category = product.get("category")
    if isinstance(category, dict):
        return str(category.get("title") or category.get("slug") or "product")
    return str(category or "product")

def _map_products(raw_products: list[dict[str, Any]], max_price: float | None) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for raw in raw_products:
        offers = raw.get("offers") or []
        eligible_offers: list[dict[str, Any]] = []
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            amount, currency = _price_fields(offer)
            url = offer.get("url")
            availability = offer.get("availability")
            # The AgentPay payment demo currently uses USD. Do not convert currencies
            # implicitly or treat sold-out offers as purchasable.
            if amount is None or currency != "USD" or amount <= 0:
                continue
            if availability != "InStock":
                continue
            if max_price is not None and amount > max_price:
                continue
            if not isinstance(url, str) or not url.startswith("https://"):
                continue
            eligible_offers.append({
                "merchant": str(offer.get("domain") or "Retailer"),
                "price": round(amount, 2),
                "currency": currency,
                "availability": availability,
                "condition": offer.get("condition") or "unknown",
                "url": url,
            })
        if not eligible_offers:
            continue
        eligible_offers.sort(key=lambda offer: offer["price"])
        offer = eligible_offers[0]
        product_source_id = str(raw.get("id") or raw.get("product_id") or "")
        if not product_source_id:
            continue
        domain = str(offer.get("merchant") or "retailer").lower()
        suffix = hashlib.sha1(domain.encode("utf-8")).hexdigest()[:8]
        item_id = f"channel3-{product_source_id}-{suffix}"
        features = raw.get("key_features") or raw.get("features") or []
        if not isinstance(features, list):
            features = []
        mapped.append({
            "id": item_id,
            "channel3_product_id": product_source_id,
            "name": str(raw.get("title") or raw.get("name") or "Untitled product"),
            "category": _category_name(raw),
            "brand": _brand_name(raw),
            "price": offer["price"],
            "currency": "USD",
            "rating": None,
            "review_count": None,
            # Channel3 reports availability, not precise inventory quantity.
            "stock": None,
            "availability": "InStock",
            "features": [str(v) for v in features[:5]],
            "description": raw.get("description"),
            "image_url": _image_url(raw),
            "offer_url": offer["url"],
            "merchant": offer["merchant"],
            "offers": eligible_offers,
            "source": "channel3",
        })
    return mapped


async def refresh_channel3_offer(product: dict[str, Any]) -> dict[str, Any]:
    """Refresh a selected product's retailer offer before basket validation/payment.

    Channel3's product-detail endpoint is used to refresh offer price and availability.
    The selected merchant is retained; if that offer has disappeared or is no longer
    in stock, AgentPay asks the shopper to search again instead of silently switching.
    """
    if not settings.channel3_api_key.strip():
        raise Channel3NotConfigured("CHANNEL3_API_KEY is not set")
    channel3_id = product.get("channel3_product_id")
    if not channel3_id:
        return product
    url = f"{settings.channel3_base_url.rstrip('/')}/products/{channel3_id}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                url,
                headers={"x-api-key": settings.channel3_api_key, "x-user-id": "agentpay-demo-user"},
                params={"country": "US", "language": "en", "currency": "USD"},
            )
            response.raise_for_status()
            raw = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise Channel3SearchError("Channel3 rejected the API key while refreshing an offer.") from exc
        if exc.response.status_code == 404:
            raise Channel3SearchError("The selected product is no longer available in Channel3. Search again.") from exc
        raise Channel3SearchError(f"Channel3 product refresh returned HTTP {exc.response.status_code}.") from exc
    except httpx.RequestError as exc:
        raise Channel3SearchError("Could not refresh the retailer offer from Channel3. Check the connection and retry.") from exc
    except ValueError as exc:
        raise Channel3SearchError("Channel3 returned unreadable product details.") from exc

    if isinstance(raw, dict) and isinstance(raw.get("product"), dict):
        raw = raw["product"]
    if not isinstance(raw, dict):
        raise Channel3SearchError("Channel3 returned an unexpected product-detail response.")

    wanted_merchant = str(product.get("merchant") or "").lower()
    fresh_offers: list[dict[str, Any]] = []
    chosen: dict[str, Any] | None = None
    for offer in raw.get("offers") or []:
        if not isinstance(offer, dict):
            continue
        amount, currency = _price_fields(offer)
        offer_url = offer.get("url")
        availability = offer.get("availability")
        domain = str(offer.get("domain") or "Retailer")
        if amount is None or currency != "USD" or amount <= 0 or not isinstance(offer_url, str) or not offer_url.startswith("https://"):
            continue
        if availability == "InStock":
            fresh_offers.append({
                "merchant": domain,
                "price": round(amount, 2),
                "currency": currency,
                "availability": availability,
                "condition": offer.get("condition") or "unknown",
                "url": offer_url,
            })
        if domain.lower() == wanted_merchant and availability == "InStock" and currency == "USD":
            chosen = {
                "price": round(amount, 2),
                "currency": currency,
                "offer_url": offer_url,
                "merchant": domain,
            }

    if chosen is None:
        raise Channel3SearchError("The selected retailer offer is no longer in stock or no longer has a USD price. Search again before checkout.")
    fresh_offers.sort(key=lambda offer: offer["price"])
    updated = {**product, **chosen, "availability": "InStock", "offers": fresh_offers}
    remember_channel3_products([updated])
    return updated


async def search_channel3(query: str, max_price: float | None = None, limit: int = 12) -> list[dict[str, Any]]:
    if not settings.channel3_api_key.strip():
        raise Channel3NotConfigured("CHANNEL3_API_KEY is not set")

    clean_query = " ".join(query.split()) or "wireless headphones keyboards mice laptop stands webcams"
    cache_key = (clean_query.lower(), round(max_price, 2) if max_price is not None else None, limit)
    cached = _SEARCH_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    filters: dict[str, Any] = {"availability": ["InStock"]}
    if max_price is not None:
        filters["price"] = {"max_price": max_price}
    payload = {
        "query": clean_query,
        "filters": filters,
        "limit": max(1, min(limit, 20)),
        # The live REST endpoint currently rejects locale fields at the top-level
        # with HTTP 422 for this integration. Channel3's default locale is en/US/USD,
        # which matches AgentPay's Sandbox demo. Keep agentic mode inside config.
        "config": {"mode": settings.channel3_search_mode},
    }
    url = f"{settings.channel3_base_url.rstrip('/')}/search"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                url,
                headers={"x-api-key": settings.channel3_api_key, "x-user-id": "agentpay-demo-user", "content-type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise Channel3SearchError("Channel3 rejected the API key. Check CHANNEL3_API_KEY.") from exc
        detail_summary = ""
        # Surface safe schema details (field path + message) without echoing inputs,
        # which could contain private data. This helps diagnose future API changes.
        try:
            error_body = exc.response.json()
            details = error_body.get("detail") if isinstance(error_body, dict) else None
            if isinstance(details, list):
                parts = []
                for item in details[:5]:
                    if not isinstance(item, dict):
                        continue
                    location = ".".join(str(bit) for bit in item.get("loc", []))
                    message = str(item.get("msg") or "request rejected")
                    parts.append(f"{location}: {message}" if location else message)
                if parts:
                    detail_summary = " Details: " + "; ".join(parts)
        except (ValueError, TypeError):
            pass
        raise Channel3SearchError(
            f"Channel3 search returned HTTP {exc.response.status_code}.{detail_summary}"
        ) from exc
    except httpx.RequestError as exc:
        raise Channel3SearchError("Could not reach Channel3. Check network access and try again.") from exc
    except ValueError as exc:
        raise Channel3SearchError("Channel3 returned an unreadable response.") from exc

    raw_products = body.get("products") if isinstance(body, dict) else None
    if not isinstance(raw_products, list):
        raw_products = body.get("results", []) if isinstance(body, dict) else []
    products = _map_products([item for item in raw_products if isinstance(item, dict)], max_price)
    if products:
        remember_channel3_products(products)
    _SEARCH_CACHE[cache_key] = (time.monotonic(), products)
    return products


async def search_channel3_image(
    base64_image: str,
    max_price: float | None = None,
    limit: int = 12,
    user_id: str = "agentpay-demo-user",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Find products in a shopper-uploaded image using Channel3 image endpoints.

    For multi-item scene images, try Channel3's experimental object-detection endpoint
    first; fall back to single-image visual search if that endpoint is unavailable.
    """
    if not settings.channel3_api_key.strip():
        raise Channel3NotConfigured("CHANNEL3_API_KEY is not set")
    clean_b64 = base64_image.strip()
    if not clean_b64 or len(clean_b64) > 11_200_000:
        raise Channel3SearchError("The uploaded image is empty or exceeds the 8 MB limit.")
    filters: dict[str, Any] = {"availability": ["InStock"]}
    if max_price is not None:
        filters["price"] = {"max_price": max_price}
    headers = {
        "x-api-key": settings.channel3_api_key,
        "x-user-id": (user_id or "agentpay-demo-user")[:100],
        "content-type": "application/json",
    }
    endpoints = ("experimental/find-products-in-image", "image-search")
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=45) as client:
        for endpoint in endpoints:
            try:
                response = await client.post(
                    f"{settings.channel3_base_url.rstrip('/')}/{endpoint}",
                    headers=headers,
                    json={"base64_image": clean_b64, "filters": filters, "limit": max(1, min(limit, 12))},
                )
                if response.status_code in (404, 422) and endpoint != endpoints[-1]:
                    last_error = Channel3SearchError(f"Channel3 {endpoint} returned HTTP {response.status_code}; trying regular image search.")
                    continue
                if response.status_code in (401, 403):
                    raise Channel3SearchError("Channel3 rejected the API key for image search. Check CHANNEL3_API_KEY.")
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict):
                    raise Channel3SearchError("Channel3 image search returned an unexpected response.")
                raw_products: list[dict[str, Any]] = []
                things_value = body.get("things")
                if not isinstance(things_value, list):
                    output = body.get("output") if isinstance(body.get("output"), dict) else {}
                    things_value = output.get("things") if isinstance(output.get("things"), list) else []
                detected: list[str] = []
                for thing in things_value if isinstance(things_value, list) else []:
                    if not isinstance(thing, dict):
                        continue
                    label = str(thing.get("thing") or thing.get("label") or "").strip()
                    if label and label not in detected:
                        detected.append(label[:80])
                    matches = thing.get("matches")
                    if isinstance(matches, list):
                        raw_products.extend(v for v in matches if isinstance(v, dict))
                products_value = body.get("products")
                if not isinstance(products_value, list):
                    products_value = body.get("results", [])
                if isinstance(products_value, list):
                    raw_products.extend(v for v in products_value if isinstance(v, dict))
                # Some image-search responses wrap the main result object.
                if not raw_products and isinstance(body.get("result"), dict):
                    nested = body["result"]
                    values = nested.get("products") or nested.get("matches") or []
                    if isinstance(values, list):
                        raw_products.extend(v for v in values if isinstance(v, dict))
                unique: dict[str, dict[str, Any]] = {}
                for product in raw_products:
                    product_id = str(product.get("id") or product.get("product_id") or "")
                    if product_id:
                        unique[product_id] = product
                mapped = _map_products(list(unique.values()), max_price)
                if mapped:
                    remember_channel3_products(mapped)
                    return mapped, detected
                if endpoint != endpoints[-1]:
                    last_error = Channel3SearchError(f"Channel3 {endpoint} returned no eligible matches; trying regular image search.")
                    continue
                return [], detected
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if endpoint != endpoints[-1] and exc.response.status_code in (404, 422, 501):
                    continue
                if exc.response.status_code in (401, 403):
                    raise Channel3SearchError("Channel3 rejected the API key for image search. Check CHANNEL3_API_KEY.") from exc
                raise Channel3SearchError(f"Channel3 image search returned HTTP {exc.response.status_code}.") from exc
            except httpx.RequestError as exc:
                last_error = exc
                if endpoint != endpoints[-1]:
                    continue
                raise Channel3SearchError("Could not reach Channel3 image search. Check the connection and retry.") from exc
            except ValueError as exc:
                raise Channel3SearchError("Channel3 returned an unreadable image-search response.") from exc
    if last_error:
        raise Channel3SearchError(f"Channel3 image search failed: {type(last_error).__name__}.") from last_error
    return [], []


async def conversational_turn(
    message: str,
    conversation_id: str | None = None,
    max_price: float | None = None,
    user_id: str = "agentpay-demo-user",
    image_data_url: str | None = None,
) -> dict[str, Any]:
    """Run one non-streaming Channel3 Conversational Agent turn.

    The vendor key remains on the server. Channel3's response may contain text plus
    structured product cards embedded in tool parts; both are normalized here.
    """
    if not settings.channel3_api_key.strip():
        raise Channel3NotConfigured("CHANNEL3_API_KEY is not set")

    filters: dict[str, Any] = {"availability": ["InStock"]}
    if max_price is not None:
        filters["price"] = {"max_price": max_price}

    message_parts: list[dict[str, Any]] = [{"type": "text", "text": message.strip() or "Find products in this image."}]
    if image_data_url:
        message_parts.append({"type": "image", "url": image_data_url})
    payload: dict[str, Any] = {
        "message": {"role": "user", "parts": message_parts},
        "filters": filters,
        "config": {"mode": settings.channel3_search_mode},
        "stream": False,
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id

    url = f"{settings.channel3_base_url.rstrip('/')}/conversations"
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                url,
                headers={
                    "x-api-key": settings.channel3_api_key,
                    "x-user-id": (user_id or "agentpay-demo-user")[:100],
                    "content-type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise Channel3SearchError("Channel3 rejected the API key for Conversational Agent. Check CHANNEL3_API_KEY.") from exc
        summary = ""
        try:
            error_body = exc.response.json()
            if isinstance(error_body, dict):
                err = error_body.get("error")
                if isinstance(err, dict):
                    summary = str(err.get("message") or err.get("code") or "")[:300]
                elif isinstance(error_body.get("detail"), str):
                    summary = error_body["detail"][:300]
        except (ValueError, TypeError):
            pass
        suffix = f" Details: {summary}" if summary else ""
        raise Channel3SearchError(f"Channel3 Conversational Agent returned HTTP {exc.response.status_code}.{suffix}") from exc
    except httpx.RequestError as exc:
        raise Channel3SearchError("Could not reach Channel3 Conversational Agent. Check network access and retry.") from exc
    except ValueError as exc:
        raise Channel3SearchError("Channel3 Conversational Agent returned an unreadable response.") from exc

    if not isinstance(body, dict):
        raise Channel3SearchError("Channel3 Conversational Agent returned an unexpected response.")

    raw_message = body.get("message")
    if not isinstance(raw_message, dict):
        raw_message = body.get("assistant_message") if isinstance(body.get("assistant_message"), dict) else {}
    # Be tolerant of TurnResult wrappers while keeping the documented top-level
    # JSON response as the preferred shape.
    if not raw_message and isinstance(body.get("turn"), dict):
        nested_turn = body["turn"]
        raw_message = nested_turn.get("message") if isinstance(nested_turn.get("message"), dict) else {}
    parts = raw_message.get("parts") if isinstance(raw_message, dict) else []
    assistant_text: list[str] = []
    raw_products: list[dict[str, Any]] = []
    if isinstance(parts, list):
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                assistant_text.append(part["text"])
            output = part.get("output")
            if isinstance(output, dict):
                cards = output.get("products")
                if isinstance(cards, list):
                    raw_products.extend(item for item in cards if isinstance(item, dict))
                things = output.get("things")
                if isinstance(things, list):
                    for thing in things:
                        if isinstance(thing, dict) and isinstance(thing.get("matches"), list):
                            raw_products.extend(item for item in thing["matches"] if isinstance(item, dict))

    # A few API responses may include products at the root level as well.
    root_products = body.get("products")
    if isinstance(root_products, list):
        raw_products.extend(item for item in root_products if isinstance(item, dict))
    # Deduplicate products by their canonical Channel3 product id.
    deduped: dict[str, dict[str, Any]] = {}
    for product in raw_products:
        product_id = str(product.get("id") or product.get("product_id") or "")
        if product_id:
            deduped[product_id] = product
    mapped = _map_products(list(deduped.values()), max_price)
    if mapped:
        remember_channel3_products(mapped)

    conversation = body.get("conversation") if isinstance(body.get("conversation"), dict) else {}
    turn = body.get("turn") if isinstance(body.get("turn"), dict) else {}
    conversation_id_value = (
        body.get("conversation_id") or conversation.get("id") or turn.get("conversation_id")
    )
    if not conversation_id_value and isinstance(body.get("id"), str) and body["id"].startswith("conv_"):
        conversation_id_value = body["id"]
    # Never mistake a turn ID or message ID for a conversation ID.
    if isinstance(conversation_id_value, str) and not conversation_id_value.startswith("conv_"):
        conversation_id_value = None

    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    return {
        "conversation_id": conversation_id_value if isinstance(conversation_id_value, str) else None,
        "text": "\n".join(piece.strip() for piece in assistant_text if piece.strip()),
        "items": mapped,
        "usage": {
            "credits_charged": usage.get("credits_charged"),
            "searches_run": usage.get("searches_run"),
        },
    }
