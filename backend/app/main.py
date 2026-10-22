from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import re
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .catalog import PRODUCT_BY_ID, search_products
from .channel3 import (
    Channel3NotConfigured,
    Channel3SearchError,
    conversational_turn,
    refresh_channel3_offer,
    search_channel3,
)
from .config import settings
from .elastic_service import ElasticTelemetry
from .paypal import PayPalError, capture_order, create_order
from .schemas import (
    Channel3ChatRequest,
    CreateOrderRequest,
    PlanRequest,
    SelectOfferRequest,
    ValidateCartRequest,
)

telemetry = ElasticTelemetry()
# Prototype-only memory order state; use durable storage for deployment with multiple instances.
PAYMENT_ORDERS: dict[str, dict[str, Any]] = {}
EVENTS: list[dict[str, Any]] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    await telemetry.start()
    yield
    await telemetry.close()


app = FastAPI(title="AgentPay API", version="0.6.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def track_event(
    event_type: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a privacy-conscious event locally and in Elastic when configured."""
    details = details or {}
    event = await telemetry.record(event_type, message, details)
    order_id = details.get("order_id")
    EVENTS.append({
        "type": event_type,
        "event_type": event_type,
        "message": message,
        "order_id": order_id,
        "timestamp": event["timestamp"],
        "details": details,
    })
    if len(EVENTS) > 1000:
        del EVENTS[:-1000]
    return event


@app.get("/")
def root():
    return {"service": "agentpay-api", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "agentpay-api", "version": "0.6.0"}


@app.get("/api/public-config")
def public_config():
    """Return only public browser configuration. Never expose the PayPal secret."""
    return {
        "paypal_client_id": settings.paypal_client_id.strip() or None,
        "paypal_sandbox_configured": bool(settings.paypal_client_id.strip() and settings.paypal_client_secret.strip()),
        "channel3_configured": bool(settings.channel3_api_key.strip()),
        "elastic_configured": telemetry.configured,
    }


def extract_usd_budget(prompt: str) -> float | None:
    """Extract an explicitly stated budget without misreading rupees as USD."""
    budget_context = re.search(r"\b(under|below|within|budget|less than)\b", prompt, re.I)
    if not budget_context:
        return None
    if re.search(r"₹|\bINR\b|\brupees?\b|\bRs\.?\s*", prompt, re.I):
        raise HTTPException(
            status_code=422,
            detail="AgentPay's PayPal Sandbox demo is USD-only. Please express the budget in USD, for example: 'under $80'.",
        )
    matches = list(re.finditer(
        r"(?:under|below|within|budget(?:\s+(?:of|is))?|less than)\s*(?:USD\s*|\$)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        prompt,
        re.I,
    ))
    if not matches:
        return None
    # Prefer the last explicit budget in combined/follow-up prompts (e.g. initial
    # $80 request followed by "show alternatives under $50").
    try:
        return float(matches[-1].group(1).replace(",", ""))
    except ValueError:
        return None


def _demo_query_from_prompt(prompt: str) -> str:
    lower = prompt.lower()
    for term in ("headphone", "keyboard", "mouse", "webcam", "stand"):
        if term in lower:
            return term
    return ""


@app.get("/api/agent/search")
async def search(q: str = "", max_price: float | None = Query(default=None, gt=0)):
    """Search Channel3 when configured; otherwise use the labelled demo catalog."""
    query = q.strip() or "wireless headphones keyboards ergonomic mice laptop stands webcams"
    try:
        products = await search_channel3(query, max_price, limit=12)
        if products:
            await track_event("catalog_search", "Channel3 product search completed.", {
                "source": "channel3", "result_count": len(products), "query_length": len(query), "budget": max_price,
            })
            return {"items": products, "source": "channel3", "message": "Live product results from Channel3."}
        products = search_products(q, max_price)
        await track_event("catalog_search", "Channel3 returned no eligible offers; using demo catalog.", {
            "source": "demo", "result_count": len(products), "query_length": len(query),
        })
        return {"items": products, "source": "demo", "message": "Channel3 returned no matching in-stock USD offers; showing the demo catalog."}
    except (Channel3NotConfigured, Channel3SearchError) as exc:
        products = search_products(q, max_price)
        await track_event("catalog_search_fallback", "Channel3 search failed; using demo catalog.", {
            "source": "demo", "result_count": len(products), "error_type": type(exc).__name__,
        })
        return {"items": products, "source": "demo", "message": f"Using demo catalog. {str(exc)}"}


@app.post("/api/agent/plan")
async def plan(request: PlanRequest):
    """Use Channel3 native agentic search for complex natural-language shopping requests."""
    prompt = request.prompt.strip()
    max_price = extract_usd_budget(prompt)
    try:
        candidates = await search_channel3(prompt, max_price, limit=12)
        if candidates:
            await track_event("agent_plan_created", "Channel3 agentic search generated a shopping plan.", {
                "source": "channel3", "result_count": len(candidates), "budget": max_price, "currency": "USD",
            })
            return {
                "mode": "channel3_agentic_search",
                "source": "channel3",
                "message": f"Channel3 found {len(candidates)} live product matches. Retailer prices and availability may change; offers will be refreshed before payment.",
                "items": candidates,
                "constraints": {"query": prompt, "max_price": max_price, "currency": "USD"},
                "events": [{"type": "channel3_search", "message": "Searched live in-stock USD offers."}],
            }
        fallback_reason = "Channel3 returned no matching in-stock USD offers."
    except Channel3NotConfigured:
        fallback_reason = "Channel3 API key is not configured."
    except Channel3SearchError as exc:
        fallback_reason = str(exc)

    candidates = search_products(_demo_query_from_prompt(prompt), max_price)
    await track_event("agent_plan_fallback", "Agent plan used the demo catalog.", {
        "source": "demo", "result_count": len(candidates), "error_summary": fallback_reason[:250],
    })
    return {
        "mode": "demo_planner",
        "source": "demo",
        "message": f"Using the local demo catalog. {fallback_reason}",
        "items": candidates[:12],
        "constraints": {"query": _demo_query_from_prompt(prompt), "max_price": max_price, "currency": "USD"},
        "events": [{"type": "plan_created", "message": "Filtered the local demo catalog; Channel3 did not provide this result."}],
    }


@app.post("/api/agent/chat")
async def agent_chat(request: Channel3ChatRequest):
    """Continue a Channel3 Conversational Agent session and return structured product cards."""
    try:
        # Extract a more specific budget from the current turn when the shopper
        # tightens constraints (e.g. "show options under $50"). Otherwise preserve
        # the existing budget across contextual follow-up turns.
        parsed_budget = extract_usd_budget(request.message)
        effective_budget = parsed_budget if parsed_budget is not None else request.budget
        result = await conversational_turn(
            message=request.message,
            conversation_id=request.conversation_id,
            max_price=effective_budget,
            user_id=request.user_id,
        )
    except Channel3NotConfigured as exc:
        await track_event("conversation_unavailable", "Channel3 Conversational Agent is not configured.", {"reason": "missing_key"})
        raise HTTPException(status_code=503, detail="Channel3 Conversational Agent is not configured. Add CHANNEL3_API_KEY to backend/.env and restart FastAPI.") from exc
    except Channel3SearchError as exc:
        await track_event("conversation_error", "Channel3 Conversational Agent request failed.", {"error_type": type(exc).__name__})
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await track_event("conversation_turn", "Channel3 Conversational Agent completed a turn.", {
        "source": "channel3", "result_count": len(result.get("items", [])),
        "has_conversation_id": bool(result.get("conversation_id")),
        "credits_charged": result.get("usage", {}).get("credits_charged"),
    })
    if not result.get("conversation_id"):
        await track_event("conversation_missing_id", "Channel3 completed a turn without a conversation ID.", {
            "result_count": len(result.get("items", [])),
        })
        raise HTTPException(status_code=502, detail="Channel3 returned a turn without a conversation ID, so contextual follow-ups cannot be continued. Please retry.")
    return {
        "source": "channel3",
        "constraints": {"max_price": effective_budget, "currency": "USD"},
        **result,
    }


@app.post("/api/catalog/select-offer")
async def select_offer(request: SelectOfferRequest):
    """Select a server-cached offer; ignore client-supplied price and URL values."""
    product = PRODUCT_BY_ID.get(request.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product is no longer in the server catalog. Search again.")
    if product.get("source") != "channel3":
        return {"product": product, "source": "demo"}

    wanted_merchant = request.merchant.strip().casefold()
    chosen = next((offer for offer in (product.get("offers") or [])
                   if str(offer.get("merchant", "")).casefold() == wanted_merchant
                   and offer.get("availability") == "InStock"
                   and offer.get("currency") == "USD"
                   and isinstance(offer.get("url"), str)
                   and offer["url"].startswith("https://")), None)
    if chosen is None:
        raise HTTPException(status_code=409, detail="That retailer offer is no longer available in the current results. Search again.")

    channel3_product_id = str(product.get("channel3_product_id") or "")
    suffix = hashlib.sha1(str(chosen["merchant"]).lower().encode("utf-8")).hexdigest()[:8]
    selected_id = f"channel3-{channel3_product_id}-{suffix}"
    selected_product = {
        **product,
        "id": selected_id,
        "price": float(chosen["price"]),
        "currency": "USD",
        "merchant": chosen["merchant"],
        "offer_url": chosen["url"],
        "availability": "InStock",
    }
    PRODUCT_BY_ID[selected_id] = selected_product
    await track_event("offer_selected", "Shopper selected a retailer offer for the basket.", {
        "source": "channel3", "product_id": channel3_product_id,
        "merchant": str(chosen["merchant"])[:120], "price": float(chosen["price"]), "currency": "USD",
    })
    return {"product": selected_product, "source": "channel3"}


async def refresh_cart_offers(items) -> None:
    """Refresh selected live offers before validating totals or creating payment."""
    refreshed_ids: set[str] = set()
    for item in items:
        product = PRODUCT_BY_ID.get(item.product_id)
        if product is None:
            raise HTTPException(status_code=400, detail=f"Unknown product: {item.product_id}")
        if product.get("source") == "channel3" and product["id"] not in refreshed_ids:
            try:
                PRODUCT_BY_ID[item.product_id] = await refresh_channel3_offer(product)
            except Channel3NotConfigured as exc:
                raise HTTPException(status_code=503, detail="Channel3 is required to refresh this live offer. Configure CHANNEL3_API_KEY and retry.") from exc
            except Channel3SearchError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            refreshed_ids.add(item.product_id)


def validate_items(items, budget=None):
    normalized = []
    total = Decimal("0.00")
    for item in items:
        product = PRODUCT_BY_ID.get(item.product_id)
        if not product:
            raise HTTPException(status_code=400, detail=f"Unknown product: {item.product_id}")
        stock = product.get("stock")
        if stock is not None and item.quantity > stock:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {product['name']}")
        if product.get("source") == "channel3" and product.get("availability") != "InStock":
            raise HTTPException(status_code=400, detail=f"{product['name']} is no longer marked in stock. Search again before checkout.")
        if product.get("currency", "USD") != "USD":
            raise HTTPException(status_code=400, detail="AgentPay Sandbox checkout currently supports USD catalog offers only.")
        unit_price = Decimal(str(product["price"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        line_total = unit_price * item.quantity
        total += line_total
        normalized.append({
            "product_id": product["id"], "name": product["name"],
            "quantity": item.quantity, "unit_price": f"{unit_price:.2f}",
            "line_total": f"{line_total:.2f}", "currency": product["currency"],
            "offer_url": product.get("offer_url"), "merchant": product.get("merchant"),
        })
    total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if budget is not None and total > Decimal(str(budget)):
        raise HTTPException(status_code=400, detail=f"Basket exceeds the ${budget:.2f} budget.")
    return normalized, total


@app.post("/api/cart/validate")
async def validate_cart(request: ValidateCartRequest):
    await refresh_cart_offers(request.items)
    items, total = validate_items(request.items, request.budget)
    await track_event("basket_validated", "Server validated basket prices, currency, availability, and budget.", {
        "item_count": len(items), "total": f"{total:.2f}", "currency": "USD",
    })
    return {"items": items, "total": f"{total:.2f}", "currency": "USD", "valid": True}


@app.post("/api/payments/create-order")
async def payments_create_order(request: CreateOrderRequest):
    await refresh_cart_offers(request.items)
    items, total = validate_items(request.items, request.budget)
    if request.expected_total is not None and abs(total - Decimal(str(request.expected_total))) > Decimal("0.009"):
        await track_event("basket_price_changed", "Payment creation stopped because the basket total changed after validation.", {
            "expected_total": str(request.expected_total), "current_total": f"{total:.2f}",
        })
        raise HTTPException(status_code=409, detail="A live retailer price changed since basket validation. Review the refreshed total and validate the basket again before payment.")
    if total <= 0:
        raise HTTPException(status_code=400, detail="Order total must be greater than zero.")
    request_id = str(uuid.uuid4())
    try:
        result = await create_order(f"{total:.2f}", items, currency="USD", request_id=request_id)
    except PayPalError as exc:
        await track_event("paypal_order_error", "PayPal Sandbox order creation was not available.", {"error_type": type(exc).__name__})
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        await track_event("paypal_order_error", "PayPal Sandbox rejected the order request.", {"http_status": exc.response.status_code})
        raise HTTPException(status_code=502, detail=f"PayPal Sandbox returned HTTP {exc.response.status_code}. Check Sandbox app credentials and account configuration.") from exc
    except httpx.RequestError as exc:
        await track_event("paypal_order_error", "Could not reach PayPal Sandbox to create an order.", {"error_type": type(exc).__name__})
        raise HTTPException(status_code=502, detail="Could not reach PayPal Sandbox. Check your internet connection and try again.") from exc

    order_id = result.get("id")
    if not order_id:
        raise HTTPException(status_code=502, detail="PayPal did not return an order ID.")
    PAYMENT_ORDERS[order_id] = {
        "status": "CREATED", "items": items, "total": f"{total:.2f}",
        "currency": "USD", "create_response": result, "capture_response": None,
        "capture_request_id": str(uuid.uuid4()),
    }
    await track_event("paypal_order_created", "PayPal Sandbox order created from server-validated basket.", {
        "order_id": order_id, "status": result.get("status", "CREATED"), "total": f"{total:.2f}", "currency": "USD",
    })
    return {"orderID": order_id, "status": result.get("status", "CREATED"), "total": f"{total:.2f}", "currency": "USD"}


@app.post("/api/payments/capture/{order_id}")
async def payments_capture(order_id: str):
    record = PAYMENT_ORDERS.get(order_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown AgentPay order. Create an order through AgentPay before capturing it.")
    if record["status"] == "COMPLETED" and record["capture_response"]:
        return record["capture_response"]
    try:
        result = await capture_order(order_id, request_id=record["capture_request_id"])
    except PayPalError as exc:
        await track_event("paypal_capture_error", "PayPal capture could not be executed.", {"order_id": order_id, "error_type": type(exc).__name__})
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        await track_event("paypal_capture_error", "PayPal returned an HTTP error during capture.", {"order_id": order_id, "http_status": exc.response.status_code})
        raise HTTPException(status_code=502, detail=f"PayPal capture returned HTTP {exc.response.status_code}. The payment may need review in Sandbox.") from exc
    except httpx.RequestError as exc:
        await track_event("paypal_capture_error", "Capture status could not be verified due to a network error.", {"order_id": order_id, "error_type": type(exc).__name__})
        raise HTTPException(status_code=502, detail="Could not verify capture with PayPal Sandbox. Check the order status before retrying.") from exc

    captures = []
    for purchase_unit in result.get("purchase_units", []):
        captures.extend(purchase_unit.get("payments", {}).get("captures", []))
    if result.get("status") != "COMPLETED" or not captures or any(item.get("status") != "COMPLETED" for item in captures):
        await track_event("paypal_capture_not_completed", "PayPal did not confirm a completed capture.", {"order_id": order_id, "status": result.get("status")})
        raise HTTPException(status_code=409, detail="PayPal has not confirmed a completed capture. Do not treat this order as paid.")

    record["status"] = "COMPLETED"
    record["capture_response"] = result
    record["capture_id"] = captures[0].get("id")
    await track_event("paypal_capture_completed", "PayPal confirmed the capture as COMPLETED.", {
        "order_id": order_id, "capture_id": record["capture_id"], "status": "COMPLETED", "total": record["total"], "currency": "USD",
    })
    return result


@app.get("/api/orders/{order_id}")
def get_order(order_id: str):
    record = PAYMENT_ORDERS.get(order_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Order not found in this AgentPay server session.")
    return {"order_id": order_id, "status": record["status"], "items": record["items"], "total": record["total"], "currency": record["currency"], "capture_id": record.get("capture_id")}


@app.get("/api/orders/{order_id}/events")
def order_events(order_id: str):
    return {"order_id": order_id, "events": [event for event in EVENTS if event.get("order_id") == order_id]}


@app.post("/api/observability/reconnect")
async def observability_reconnect():
    """Retry Elastic connectivity using the settings loaded at backend startup."""
    await telemetry.reconnect()
    await track_event("elastic_reconnect_check", "Elastic connectivity was checked from the dashboard.", {
        "connected": telemetry.connected,
        "configured": telemetry.configured,
    })
    return telemetry.status()


@app.get("/api/observability/status")
async def observability_status():
    status = telemetry.status()
    status["channel3_configured"] = bool(settings.channel3_api_key.strip())
    status["paypal_sandbox_configured"] = bool(settings.paypal_client_id.strip() and settings.paypal_client_secret.strip())
    return status


@app.get("/api/observability/events")
async def observability_events(q: str = Query(default="", max_length=120), limit: int = Query(default=25, ge=1, le=100)):
    return await telemetry.search(q, limit)
