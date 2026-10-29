# from __future__ import annotations

# from contextlib import asynccontextmanager
# from decimal import Decimal, ROUND_HALF_UP
# import hashlib
# import re
# import uuid
# from typing import Any

# import httpx
# from fastapi import FastAPI, HTTPException, Query
# from fastapi.middleware.cors import CORSMiddleware

# from .catalog import PRODUCT_BY_ID, search_products
# from .channel3 import (
#     Channel3NotConfigured,
#     Channel3SearchError,
#     conversational_turn,
#     refresh_channel3_offer,
#     search_channel3,
# )
# from .config import settings
# from .elastic_service import ElasticTelemetry
# from .paypal import PayPalError, capture_order, create_order
# from .schemas import (
#     Channel3ChatRequest,
#     CreateOrderRequest,
#     PlanRequest,
#     SelectOfferRequest,
#     ValidateCartRequest,
# )

# telemetry = ElasticTelemetry()
# # Prototype-only memory order state; use durable storage for deployment with multiple instances.
# PAYMENT_ORDERS: dict[str, dict[str, Any]] = {}
# EVENTS: list[dict[str, Any]] = []


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     await telemetry.start()
#     yield
#     await telemetry.close()


# app = FastAPI(title="AgentPay API", version="0.6.0", lifespan=lifespan)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[settings.frontend_origin],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# async def track_event(
#     event_type: str,
#     message: str,
#     details: dict[str, Any] | None = None,
# ) -> dict[str, Any]:
#     """Record a privacy-conscious event locally and in Elastic when configured."""
#     details = details or {}
#     event = await telemetry.record(event_type, message, details)
#     order_id = details.get("order_id")
#     EVENTS.append({
#         "type": event_type,
#         "event_type": event_type,
#         "message": message,
#         "order_id": order_id,
#         "timestamp": event["timestamp"],
#         "details": details,
#     })
#     if len(EVENTS) > 1000:
#         del EVENTS[:-1000]
#     return event


# @app.get("/")
# def root():
#     return {"service": "agentpay-api", "docs": "/docs", "health": "/api/health"}


# @app.get("/api/health")
# def health():
#     return {"status": "ok", "service": "agentpay-api", "version": "0.6.0"}


# @app.get("/api/public-config")
# def public_config():
#     """Return only public browser configuration. Never expose the PayPal secret."""
#     return {
#         "paypal_client_id": settings.paypal_client_id.strip() or None,
#         "paypal_sandbox_configured": bool(settings.paypal_client_id.strip() and settings.paypal_client_secret.strip()),
#         "channel3_configured": bool(settings.channel3_api_key.strip()),
#         "elastic_configured": telemetry.configured,
#     }


# def extract_usd_budget(prompt: str) -> float | None:
#     """Extract an explicitly stated budget without misreading rupees as USD."""
#     budget_context = re.search(r"\b(under|below|within|budget|less than)\b", prompt, re.I)
#     if not budget_context:
#         return None
#     if re.search(r"₹|\bINR\b|\brupees?\b|\bRs\.?\s*", prompt, re.I):
#         raise HTTPException(
#             status_code=422,
#             detail="AgentPay's PayPal Sandbox demo is USD-only. Please express the budget in USD, for example: 'under $80'.",
#         )
#     matches = list(re.finditer(
#         r"(?:under|below|within|budget(?:\s+(?:of|is))?|less than)\s*(?:USD\s*|\$)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
#         prompt,
#         re.I,
#     ))
#     if not matches:
#         return None
#     # Prefer the last explicit budget in combined/follow-up prompts (e.g. initial
#     # $80 request followed by "show alternatives under $50").
#     try:
#         return float(matches[-1].group(1).replace(",", ""))
#     except ValueError:
#         return None


# def _demo_query_from_prompt(prompt: str) -> str:
#     lower = prompt.lower()
#     for term in ("headphone", "keyboard", "mouse", "webcam", "stand"):
#         if term in lower:
#             return term
#     return ""


# @app.get("/api/agent/search")
# async def search(q: str = "", max_price: float | None = Query(default=None, gt=0)):
#     """Search Channel3 when configured; otherwise use the labelled demo catalog."""
#     query = q.strip() or "wireless headphones keyboards ergonomic mice laptop stands webcams"
#     try:
#         products = await search_channel3(query, max_price, limit=12)
#         if products:
#             await track_event("catalog_search", "Channel3 product search completed.", {
#                 "source": "channel3", "result_count": len(products), "query_length": len(query), "budget": max_price,
#             })
#             return {"items": products, "source": "channel3", "message": "Live product results from Channel3."}
#         products = search_products(q, max_price)
#         await track_event("catalog_search", "Channel3 returned no eligible offers; using demo catalog.", {
#             "source": "demo", "result_count": len(products), "query_length": len(query),
#         })
#         return {"items": products, "source": "demo", "message": "Channel3 returned no matching in-stock USD offers; showing the demo catalog."}
#     except (Channel3NotConfigured, Channel3SearchError) as exc:
#         products = search_products(q, max_price)
#         await track_event("catalog_search_fallback", "Channel3 search failed; using demo catalog.", {
#             "source": "demo", "result_count": len(products), "error_type": type(exc).__name__,
#         })
#         return {"items": products, "source": "demo", "message": f"Using demo catalog. {str(exc)}"}


# @app.post("/api/agent/plan")
# async def plan(request: PlanRequest):
#     """Use Channel3 native agentic search for complex natural-language shopping requests."""
#     prompt = request.prompt.strip()
#     max_price = extract_usd_budget(prompt)
#     try:
#         candidates = await search_channel3(prompt, max_price, limit=12)
#         if candidates:
#             await track_event("agent_plan_created", "Channel3 agentic search generated a shopping plan.", {
#                 "source": "channel3", "result_count": len(candidates), "budget": max_price, "currency": "USD",
#             })
#             return {
#                 "mode": "channel3_agentic_search",
#                 "source": "channel3",
#                 "message": f"Channel3 found {len(candidates)} live product matches. Retailer prices and availability may change; offers will be refreshed before payment.",
#                 "items": candidates,
#                 "constraints": {"query": prompt, "max_price": max_price, "currency": "USD"},
#                 "events": [{"type": "channel3_search", "message": "Searched live in-stock USD offers."}],
#             }
#         fallback_reason = "Channel3 returned no matching in-stock USD offers."
#     except Channel3NotConfigured:
#         fallback_reason = "Channel3 API key is not configured."
#     except Channel3SearchError as exc:
#         fallback_reason = str(exc)

#     candidates = search_products(_demo_query_from_prompt(prompt), max_price)
#     await track_event("agent_plan_fallback", "Agent plan used the demo catalog.", {
#         "source": "demo", "result_count": len(candidates), "error_summary": fallback_reason[:250],
#     })
#     return {
#         "mode": "demo_planner",
#         "source": "demo",
#         "message": f"Using the local demo catalog. {fallback_reason}",
#         "items": candidates[:12],
#         "constraints": {"query": _demo_query_from_prompt(prompt), "max_price": max_price, "currency": "USD"},
#         "events": [{"type": "plan_created", "message": "Filtered the local demo catalog; Channel3 did not provide this result."}],
#     }


# @app.post("/api/agent/chat")
# async def agent_chat(request: Channel3ChatRequest):
#     """Continue a Channel3 Conversational Agent session and return structured product cards."""
#     try:
#         # Extract a more specific budget from the current turn when the shopper
#         # tightens constraints (e.g. "show options under $50"). Otherwise preserve
#         # the existing budget across contextual follow-up turns.
#         parsed_budget = extract_usd_budget(request.message)
#         effective_budget = parsed_budget if parsed_budget is not None else request.budget
#         result = await conversational_turn(
#             message=request.message,
#             conversation_id=request.conversation_id,
#             max_price=effective_budget,
#             user_id=request.user_id,
#         )
#     except Channel3NotConfigured as exc:
#         await track_event("conversation_unavailable", "Channel3 Conversational Agent is not configured.", {"reason": "missing_key"})
#         raise HTTPException(status_code=503, detail="Channel3 Conversational Agent is not configured. Add CHANNEL3_API_KEY to backend/.env and restart FastAPI.") from exc
#     except Channel3SearchError as exc:
#         await track_event("conversation_error", "Channel3 Conversational Agent request failed.", {"error_type": type(exc).__name__})
#         raise HTTPException(status_code=502, detail=str(exc)) from exc

#     await track_event("conversation_turn", "Channel3 Conversational Agent completed a turn.", {
#         "source": "channel3", "result_count": len(result.get("items", [])),
#         "has_conversation_id": bool(result.get("conversation_id")),
#         "credits_charged": result.get("usage", {}).get("credits_charged"),
#     })
#     if not result.get("conversation_id"):
#         await track_event("conversation_missing_id", "Channel3 completed a turn without a conversation ID.", {
#             "result_count": len(result.get("items", [])),
#         })
#         raise HTTPException(status_code=502, detail="Channel3 returned a turn without a conversation ID, so contextual follow-ups cannot be continued. Please retry.")
#     return {
#         "source": "channel3",
#         "constraints": {"max_price": effective_budget, "currency": "USD"},
#         **result,
#     }


# @app.post("/api/catalog/select-offer")
# async def select_offer(request: SelectOfferRequest):
#     """Select a server-cached offer; ignore client-supplied price and URL values."""
#     product = PRODUCT_BY_ID.get(request.product_id)
#     if product is None:
#         raise HTTPException(status_code=404, detail="Product is no longer in the server catalog. Search again.")
#     if product.get("source") != "channel3":
#         return {"product": product, "source": "demo"}

#     wanted_merchant = request.merchant.strip().casefold()
#     chosen = next((offer for offer in (product.get("offers") or [])
#                    if str(offer.get("merchant", "")).casefold() == wanted_merchant
#                    and offer.get("availability") == "InStock"
#                    and offer.get("currency") == "USD"
#                    and isinstance(offer.get("url"), str)
#                    and offer["url"].startswith("https://")), None)
#     if chosen is None:
#         raise HTTPException(status_code=409, detail="That retailer offer is no longer available in the current results. Search again.")

#     channel3_product_id = str(product.get("channel3_product_id") or "")
#     suffix = hashlib.sha1(str(chosen["merchant"]).lower().encode("utf-8")).hexdigest()[:8]
#     selected_id = f"channel3-{channel3_product_id}-{suffix}"
#     selected_product = {
#         **product,
#         "id": selected_id,
#         "price": float(chosen["price"]),
#         "currency": "USD",
#         "merchant": chosen["merchant"],
#         "offer_url": chosen["url"],
#         "availability": "InStock",
#     }
#     PRODUCT_BY_ID[selected_id] = selected_product
#     await track_event("offer_selected", "Shopper selected a retailer offer for the basket.", {
#         "source": "channel3", "product_id": channel3_product_id,
#         "merchant": str(chosen["merchant"])[:120], "price": float(chosen["price"]), "currency": "USD",
#     })
#     return {"product": selected_product, "source": "channel3"}


# async def refresh_cart_offers(items) -> None:
#     """Refresh selected live offers before validating totals or creating payment."""
#     refreshed_ids: set[str] = set()
#     for item in items:
#         product = PRODUCT_BY_ID.get(item.product_id)
#         if product is None:
#             raise HTTPException(status_code=400, detail=f"Unknown product: {item.product_id}")
#         if product.get("source") == "channel3" and product["id"] not in refreshed_ids:
#             try:
#                 PRODUCT_BY_ID[item.product_id] = await refresh_channel3_offer(product)
#             except Channel3NotConfigured as exc:
#                 raise HTTPException(status_code=503, detail="Channel3 is required to refresh this live offer. Configure CHANNEL3_API_KEY and retry.") from exc
#             except Channel3SearchError as exc:
#                 raise HTTPException(status_code=409, detail=str(exc)) from exc
#             refreshed_ids.add(item.product_id)


# def validate_items(items, budget=None):
#     normalized = []
#     total = Decimal("0.00")
#     for item in items:
#         product = PRODUCT_BY_ID.get(item.product_id)
#         if not product:
#             raise HTTPException(status_code=400, detail=f"Unknown product: {item.product_id}")
#         stock = product.get("stock")
#         if stock is not None and item.quantity > stock:
#             raise HTTPException(status_code=400, detail=f"Insufficient stock for {product['name']}")
#         if product.get("source") == "channel3" and product.get("availability") != "InStock":
#             raise HTTPException(status_code=400, detail=f"{product['name']} is no longer marked in stock. Search again before checkout.")
#         if product.get("currency", "USD") != "USD":
#             raise HTTPException(status_code=400, detail="AgentPay Sandbox checkout currently supports USD catalog offers only.")
#         unit_price = Decimal(str(product["price"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
#         line_total = unit_price * item.quantity
#         total += line_total
#         normalized.append({
#             "product_id": product["id"], "name": product["name"],
#             "quantity": item.quantity, "unit_price": f"{unit_price:.2f}",
#             "line_total": f"{line_total:.2f}", "currency": product["currency"],
#             "offer_url": product.get("offer_url"), "merchant": product.get("merchant"),
#         })
#     total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
#     if budget is not None and total > Decimal(str(budget)):
#         raise HTTPException(status_code=400, detail=f"Basket exceeds the ${budget:.2f} budget.")
#     return normalized, total


# @app.post("/api/cart/validate")
# async def validate_cart(request: ValidateCartRequest):
#     await refresh_cart_offers(request.items)
#     items, total = validate_items(request.items, request.budget)
#     await track_event("basket_validated", "Server validated basket prices, currency, availability, and budget.", {
#         "item_count": len(items), "total": f"{total:.2f}", "currency": "USD",
#     })
#     return {"items": items, "total": f"{total:.2f}", "currency": "USD", "valid": True}


# @app.post("/api/payments/create-order")
# async def payments_create_order(request: CreateOrderRequest):
#     await refresh_cart_offers(request.items)
#     items, total = validate_items(request.items, request.budget)
#     if request.expected_total is not None and abs(total - Decimal(str(request.expected_total))) > Decimal("0.009"):
#         await track_event("basket_price_changed", "Payment creation stopped because the basket total changed after validation.", {
#             "expected_total": str(request.expected_total), "current_total": f"{total:.2f}",
#         })
#         raise HTTPException(status_code=409, detail="A live retailer price changed since basket validation. Review the refreshed total and validate the basket again before payment.")
#     if total <= 0:
#         raise HTTPException(status_code=400, detail="Order total must be greater than zero.")
#     request_id = str(uuid.uuid4())
#     try:
#         result = await create_order(f"{total:.2f}", items, currency="USD", request_id=request_id)
#     except PayPalError as exc:
#         await track_event("paypal_order_error", "PayPal Sandbox order creation was not available.", {"error_type": type(exc).__name__})
#         raise HTTPException(status_code=503, detail=str(exc)) from exc
#     except httpx.HTTPStatusError as exc:
#         await track_event("paypal_order_error", "PayPal Sandbox rejected the order request.", {"http_status": exc.response.status_code})
#         raise HTTPException(status_code=502, detail=f"PayPal Sandbox returned HTTP {exc.response.status_code}. Check Sandbox app credentials and account configuration.") from exc
#     except httpx.RequestError as exc:
#         await track_event("paypal_order_error", "Could not reach PayPal Sandbox to create an order.", {"error_type": type(exc).__name__})
#         raise HTTPException(status_code=502, detail="Could not reach PayPal Sandbox. Check your internet connection and try again.") from exc

#     order_id = result.get("id")
#     if not order_id:
#         raise HTTPException(status_code=502, detail="PayPal did not return an order ID.")
#     PAYMENT_ORDERS[order_id] = {
#         "status": "CREATED", "items": items, "total": f"{total:.2f}",
#         "currency": "USD", "create_response": result, "capture_response": None,
#         "capture_request_id": str(uuid.uuid4()),
#     }
#     await track_event("paypal_order_created", "PayPal Sandbox order created from server-validated basket.", {
#         "order_id": order_id, "status": result.get("status", "CREATED"), "total": f"{total:.2f}", "currency": "USD",
#     })
#     return {"orderID": order_id, "status": result.get("status", "CREATED"), "total": f"{total:.2f}", "currency": "USD"}


# @app.post("/api/payments/capture/{order_id}")
# async def payments_capture(order_id: str):
#     record = PAYMENT_ORDERS.get(order_id)
#     if record is None:
#         raise HTTPException(status_code=404, detail="Unknown AgentPay order. Create an order through AgentPay before capturing it.")
#     if record["status"] == "COMPLETED" and record["capture_response"]:
#         return record["capture_response"]
#     try:
#         result = await capture_order(order_id, request_id=record["capture_request_id"])
#     except PayPalError as exc:
#         await track_event("paypal_capture_error", "PayPal capture could not be executed.", {"order_id": order_id, "error_type": type(exc).__name__})
#         raise HTTPException(status_code=503, detail=str(exc)) from exc
#     except httpx.HTTPStatusError as exc:
#         await track_event("paypal_capture_error", "PayPal returned an HTTP error during capture.", {"order_id": order_id, "http_status": exc.response.status_code})
#         raise HTTPException(status_code=502, detail=f"PayPal capture returned HTTP {exc.response.status_code}. The payment may need review in Sandbox.") from exc
#     except httpx.RequestError as exc:
#         await track_event("paypal_capture_error", "Capture status could not be verified due to a network error.", {"order_id": order_id, "error_type": type(exc).__name__})
#         raise HTTPException(status_code=502, detail="Could not verify capture with PayPal Sandbox. Check the order status before retrying.") from exc

#     captures = []
#     for purchase_unit in result.get("purchase_units", []):
#         captures.extend(purchase_unit.get("payments", {}).get("captures", []))
#     if result.get("status") != "COMPLETED" or not captures or any(item.get("status") != "COMPLETED" for item in captures):
#         await track_event("paypal_capture_not_completed", "PayPal did not confirm a completed capture.", {"order_id": order_id, "status": result.get("status")})
#         raise HTTPException(status_code=409, detail="PayPal has not confirmed a completed capture. Do not treat this order as paid.")

#     record["status"] = "COMPLETED"
#     record["capture_response"] = result
#     record["capture_id"] = captures[0].get("id")
#     await track_event("paypal_capture_completed", "PayPal confirmed the capture as COMPLETED.", {
#         "order_id": order_id, "capture_id": record["capture_id"], "status": "COMPLETED", "total": record["total"], "currency": "USD",
#     })
#     return result


# @app.get("/api/orders/{order_id}")
# def get_order(order_id: str):
#     record = PAYMENT_ORDERS.get(order_id)
#     if record is None:
#         raise HTTPException(status_code=404, detail="Order not found in this AgentPay server session.")
#     return {"order_id": order_id, "status": record["status"], "items": record["items"], "total": record["total"], "currency": record["currency"], "capture_id": record.get("capture_id")}


# @app.get("/api/orders/{order_id}/events")
# def order_events(order_id: str):
#     return {"order_id": order_id, "events": [event for event in EVENTS if event.get("order_id") == order_id]}


# @app.post("/api/observability/reconnect")
# async def observability_reconnect():
#     """Retry Elastic connectivity using the settings loaded at backend startup."""
#     await telemetry.reconnect()
#     await track_event("elastic_reconnect_check", "Elastic connectivity was checked from the dashboard.", {
#         "connected": telemetry.connected,
#         "configured": telemetry.configured,
#     })
#     return telemetry.status()


# @app.get("/api/observability/status")
# async def observability_status():
#     status = telemetry.status()
#     status["channel3_configured"] = bool(settings.channel3_api_key.strip())
#     status["paypal_sandbox_configured"] = bool(settings.paypal_client_id.strip() and settings.paypal_client_secret.strip())
#     return status


# @app.get("/api/observability/events")
# async def observability_events(q: str = Query(default="", max_length=120), limit: int = Query(default=25, ge=1, le=100)):
#     return await telemetry.search(q, limit)


from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal, ROUND_HALF_UP
import base64
import binascii
import hashlib
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .catalog import PRODUCT_BY_ID, search_products
from .channel3 import (
    Channel3NotConfigured,
    Channel3SearchError,
    conversational_turn,
    refresh_channel3_offer,
    search_channel3,
    search_channel3_image,
)
from .config import settings
from .elastic_service import ElasticTelemetry
from .automation_service import automation_status, dispatch_purchase_completed
from .paypal import PayPalError, capture_order, create_order, get_refund, refund_capture, verify_webhook_signature
from .paypal_mcp import call_read_only_tool, configured as paypal_mcp_configured, list_read_only_tools, status as paypal_mcp_status
from .state_store import load_payment_orders, record_webhook_once, save_payment_order
from .schemas import (
    Channel3ChatRequest,
    CreateOrderRequest,
    PlanRequest,
    SelectOfferRequest,
    ValidateCartRequest,
    PhotoSearchRequest,
    RefundRequest,
    PayPalMcpCallRequest,
)

telemetry = ElasticTelemetry()
# Payment/refund metadata is persisted in SQLite; use a managed transactional database for multi-instance deployment.
PAYMENT_ORDERS: dict[str, dict[str, Any]] = load_payment_orders()
EVENTS: list[dict[str, Any]] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    await telemetry.start()
    yield
    await telemetry.close()


app = FastAPI(title="AgentPay API", version="0.7.0", lifespan=lifespan)
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
    return {"status": "ok", "service": "agentpay-api", "version": "0.7.0"}


@app.get("/api/public-config")
def public_config():
    """Return only public browser configuration. Never expose the PayPal secret."""
    return {
        "paypal_client_id": settings.paypal_client_id.strip() or None,
        "paypal_sandbox_configured": bool(settings.paypal_client_id.strip() and settings.paypal_client_secret.strip()),
        "channel3_configured": bool(settings.channel3_api_key.strip()),
        "elastic_configured": telemetry.configured,
        "admin_actions_configured": bool(settings.agentpay_admin_token.strip()),
    }



def require_admin_token(request: Request) -> None:
    """Protect refunds, MCP access, and operator-triggered retries.

    The UI asks the local operator to enter this token per browser session; it is
    never embedded in Vite build-time environment variables or returned by an API.
    """
    expected = settings.agentpay_admin_token.strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Operator actions are disabled. Set AGENTPAY_ADMIN_TOKEN in backend/.env and restart FastAPI.",
        )
    supplied = request.headers.get("x-agentpay-admin-token", "").strip()
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="A valid AgentPay operator token is required for this action.")


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


@app.post("/api/agent/photo")
async def agent_photo_search(request: PhotoSearchRequest):
    """Find products from an uploaded photo and start a contextual Channel3 session."""
    data_url = request.image_data_url.strip()
    match = re.fullmatch(r"data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\s]+)", data_url, flags=re.IGNORECASE)
    if not match:
        raise HTTPException(status_code=422, detail="Upload a valid JPEG, PNG, or WebP image.")
    mime = match.group(1).lower()
    encoded = re.sub(r"\s+", "", match.group(2))
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="The uploaded image could not be decoded.") from exc
    if not image_bytes or len(image_bytes) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Images must be non-empty and 8 MB or smaller.")
    signatures = {
        "image/jpeg": image_bytes.startswith(b"\xff\xd8\xff"),
        "image/png": image_bytes.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": len(image_bytes) >= 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP",
    }
    if not signatures.get(mime, False):
        raise HTTPException(status_code=422, detail="The selected file does not match its declared image format.")

    prompt = request.prompt.strip() or "Identify the product categories in this image and find relevant products."
    parsed_budget = request.max_price if request.max_price is not None else extract_usd_budget(prompt)
    result: dict[str, Any] = {"conversation_id": None, "text": "", "items": []}
    detected: list[str] = []
    try:
        result = await conversational_turn(
            message=prompt, conversation_id=None, max_price=parsed_budget,
            user_id=request.user_id, image_data_url=data_url,
        )
        items = result.get("items", []) if isinstance(result, dict) else []
        if not items:
            # Some Channel3 agent responses describe the image in text without product cards.
            # Use the documented image-search endpoints as a catalog-result fallback.
            items, detected = await search_channel3_image(
                encoded, max_price=parsed_budget, limit=12, user_id=request.user_id,
            )
    except Channel3NotConfigured as exc:
        raise HTTPException(status_code=503, detail="Photo shopping requires CHANNEL3_API_KEY in backend/.env.") from exc
    except Channel3SearchError as conversation_exc:
        # A vendor conversational endpoint failure should not prevent the dedicated
        # image-search API from working. A conversation ID is returned only if one exists.
        try:
            items, detected = await search_channel3_image(
                encoded, max_price=parsed_budget, limit=12, user_id=request.user_id,
            )
            result = {"conversation_id": None, "text": "Image search completed. Follow-up context may require a new text conversation.", "items": items}
        except Channel3NotConfigured as exc:
            raise HTTPException(status_code=503, detail="Photo shopping requires CHANNEL3_API_KEY in backend/.env.") from exc
        except Channel3SearchError as image_exc:
            raise HTTPException(status_code=502, detail=f"Channel3 photo search failed. Conversation: {conversation_exc}. Image search: {image_exc}") from image_exc

    await track_event("photo_shopping_search", "Channel3 photo-based product discovery completed.", {
        "source": "channel3", "result_count": len(items), "image_bytes": len(image_bytes),
        "mime_type": mime, "budget": parsed_budget, "detected_object_count": len(detected),
        "has_conversation_id": bool(result.get("conversation_id")),
    })
    return {
        "source": "channel3", "items": items, "detected_objects": detected,
        "conversation_id": result.get("conversation_id"), "text": result.get("text", ""),
        "constraints": {"max_price": parsed_budget, "currency": "USD"},
        "message": (f"Found {len(items)} live product matches from the uploaded photo." if items
                    else "The image was processed, but no eligible in-stock USD matches were returned. Try a clearer image or a more specific prompt."),
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
        "capture_request_id": str(uuid.uuid4()), "capture_id": None,
        "refunds": [], "refunded_total": "0.00", "refund_status": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_payment_order(order_id, PAYMENT_ORDERS[order_id])
    await track_event("paypal_order_created", "PayPal Sandbox order created from server-validated basket.", {
        "order_id": order_id, "status": result.get("status", "CREATED"), "total": f"{total:.2f}", "currency": "USD",
    })
    return {"orderID": order_id, "status": result.get("status", "CREATED"), "total": f"{total:.2f}", "currency": "USD"}


@app.post("/api/payments/capture/{order_id}")
async def payments_capture(order_id: str):
    record = PAYMENT_ORDERS.get(order_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown AgentPay order. Create an order through AgentPay before capturing it.")
    if record["status"] in {"COMPLETED", "PARTIALLY_REFUNDED", "REFUNDED"}:
        if record.get("capture_response"):
            return record["capture_response"]
        # Reconstruct the minimal verified capture shape from our own persisted state.
        return {
            "id": order_id, "status": "COMPLETED",
            "purchase_units": [{"payments": {"captures": [{
                "id": record.get("capture_id"), "status": "COMPLETED",
                "amount": {"value": record["total"], "currency_code": record["currency"]},
            }]}}],
        }
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
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_payment_order(order_id, record)
    await track_event("paypal_capture_completed", "PayPal confirmed the capture as COMPLETED.", {
        "order_id": order_id, "capture_id": record["capture_id"], "status": "COMPLETED", "total": record["total"], "currency": "USD",
    })
    run = await dispatch_purchase_completed(order_id, record)
    await track_event("post_purchase_automation", "Post-purchase workflow ran after verified Sandbox capture.", {
        "order_id": order_id, "status": run.get("status"), "mode": "zapier_webhook" if settings.zapier_webhook_url.strip() else "preview_only",
    })
    return result


@app.get("/api/orders/{order_id}")
def get_order(order_id: str, request: Request):
    require_admin_token(request)
    record = PAYMENT_ORDERS.get(order_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Order not found in this AgentPay server session.")
    return {"order_id": order_id, "status": record["status"], "items": record["items"], "total": record["total"], "currency": record["currency"], "capture_id": record.get("capture_id"), "refunded_total": record.get("refunded_total", "0.00"), "refund_status": record.get("refund_status"), "refunds": record.get("refunds", [])}


@app.get("/api/payments/history")
def payments_history(request: Request, limit: int = Query(default=20, ge=1, le=100)):
    require_admin_token(request)
    rows = []
    for order_id, record in PAYMENT_ORDERS.items():
        rows.append({
            "order_id": order_id, "status": record.get("status"), "total": record.get("total"),
            "currency": record.get("currency", "USD"), "capture_id": record.get("capture_id"),
            "refunded_total": record.get("refunded_total", "0.00"),
            "refund_status": record.get("refund_status"), "updated_at": record.get("updated_at"),
        })
    rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return {"orders": rows[:limit]}


@app.post("/api/payments/refund/{order_id}")
async def payments_refund(order_id: str, request: RefundRequest, http_request: Request):
    require_admin_token(http_request)
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Explicit confirmation is required before a refund can be sent to PayPal.")
    record = PAYMENT_ORDERS.get(order_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Order not found in AgentPay's payment history.")
    capture_id = record.get("capture_id")
    if not capture_id or record.get("status") not in {"COMPLETED", "PARTIALLY_REFUNDED", "REFUNDED"}:
        raise HTTPException(status_code=409, detail="Only a verified completed capture can be refunded.")

    total = Decimal(str(record.get("total", "0.00"))).quantize(Decimal("0.01"))
    refunded_total = Decimal(str(record.get("refunded_total", "0.00"))).quantize(Decimal("0.01"))
    remaining = (total - refunded_total).quantize(Decimal("0.01"))
    if remaining <= 0 or record.get("status") == "REFUNDED":
        raise HTTPException(status_code=409, detail="This payment has already been fully refunded.")
    amount = remaining if request.amount is None else Decimal(str(request.amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0 or amount > remaining:
        raise HTTPException(status_code=400, detail=f"Refund must be greater than zero and cannot exceed the remaining refundable amount of ${remaining:.2f}.")

    # Reuse a pending idempotency key if the previous call timed out after PayPal may
    # have processed it. Only the same amount can be retried while pending.
    pending = next((item for item in record.get("refunds", []) if item.get("status") == "REQUEST_PENDING"), None)
    unresolved = next((item for item in record.get("refunds", []) if item.get("status") == "PENDING"), None)
    if unresolved:
        raise HTTPException(status_code=409, detail="A PayPal refund is pending. Check its refund ID status before requesting another refund.")
    if pending:
        if Decimal(str(pending.get("requested_amount", "0.00"))) != amount:
            raise HTTPException(status_code=409, detail="A previous refund is still awaiting verification. Retry the same amount/status check before submitting another amount.")
        request_id = pending["request_id"]
        refund_entry = pending
    else:
        request_id = str(uuid.uuid4())
        refund_entry = {
            "request_id": request_id, "requested_amount": f"{amount:.2f}",
            "note_to_payer": request.note_to_payer[:200], "status": "REQUEST_PENDING",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        record.setdefault("refunds", []).append(refund_entry)
        record["refund_status"] = "REQUEST_PENDING"
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_payment_order(order_id, record)

    try:
        is_full_refund = amount == remaining and refunded_total == Decimal("0.00")
        result = await refund_capture(
            capture_id=capture_id,
            amount_major_units=None if is_full_refund else f"{amount:.2f}",
            currency=record.get("currency", "USD"), note_to_payer=request.note_to_payer, request_id=request_id,
        )
    except PayPalError as exc:
        await track_event("paypal_refund_error", "PayPal refund request could not be executed.", {"order_id": order_id, "error_type": type(exc).__name__})
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        # Preserve REQUEST_PENDING and request_id. A retry of the same amount uses
        # PayPal-Request-Id so an ambiguous network result is not double-refunded.
        await track_event("paypal_refund_error", "PayPal rejected the refund request.", {"order_id": order_id, "http_status": exc.response.status_code})
        raise HTTPException(status_code=502, detail=f"PayPal refund returned HTTP {exc.response.status_code}. The request is retained for safe retry with the same idempotency key.") from exc
    except httpx.RequestError as exc:
        await track_event("paypal_refund_uncertain", "Refund result could not be verified; keeping the request pending for safe retry.", {"order_id": order_id, "error_type": type(exc).__name__})
        raise HTTPException(status_code=502, detail="PayPal's refund result could not be verified. Retry the same amount to reuse the idempotency key; do not create a different refund request.") from exc

    refund_id = result.get("id")
    status_value = str(result.get("status") or "PENDING").upper()
    amount_data = result.get("amount") if isinstance(result.get("amount"), dict) else {}
    try:
        settled_amount = Decimal(str(amount_data.get("value"))) if amount_data.get("value") is not None else amount
    except Exception:
        settled_amount = amount
    refund_entry.update({
        "refund_id": refund_id, "status": status_value,
        "amount": f"{settled_amount:.2f}", "currency": amount_data.get("currency_code") or record.get("currency", "USD"),
        "note_to_payer": request.note_to_payer[:200],
    })
    if status_value == "COMPLETED":
        # Avoid double-counting if PayPal returns the same refund after a retry.
        if not refund_entry.get("counted_toward_total"):
            refunded_total += settled_amount
            refund_entry["counted_toward_total"] = True
        record["refunded_total"] = f"{min(refunded_total, total):.2f}"
        record["status"] = "REFUNDED" if refunded_total >= total else "PARTIALLY_REFUNDED"
    record["refund_status"] = status_value
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_payment_order(order_id, record)
    await track_event("paypal_refund_completed" if status_value == "COMPLETED" else "paypal_refund_status", "PayPal refund result recorded.", {
        "order_id": order_id, "refund_id": refund_id, "status": status_value,
        "amount": f"{settled_amount:.2f}", "currency": record.get("currency", "USD"),
    })
    return {
        "order_id": order_id, "refund_id": refund_id, "status": status_value,
        "amount": f"{settled_amount:.2f}", "currency": record.get("currency", "USD"),
        "payment_status": record.get("status"), "refund_status": status_value,
        "refunded_total": record.get("refunded_total", "0.00"), "remaining_refundable": f"{max(Decimal('0.00'), total - Decimal(str(record.get('refunded_total', '0.00')))):.2f}",
    }


@app.get("/api/payments/refunds/{refund_id}")
async def payments_refund_status(refund_id: str, request: Request):
    require_admin_token(request)
    owner = next(((order_id, record, entry) for order_id, record in PAYMENT_ORDERS.items() for entry in record.get("refunds", []) if entry.get("refund_id") == refund_id), None)
    if owner is None:
        raise HTTPException(status_code=404, detail="Refund ID is not present in AgentPay's recorded refund history.")
    order_id, record, entry = owner
    try:
        result = await get_refund(refund_id)
    except PayPalError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"PayPal refund status returned HTTP {exc.response.status_code}.") from exc
    status_value = str(result.get("status") or entry.get("status") or "PENDING").upper()
    amount_data = result.get("amount") if isinstance(result.get("amount"), dict) else {}
    entry["status"] = status_value
    if status_value == "COMPLETED" and not entry.get("counted_toward_total"):
        refund_amount = Decimal(str(amount_data.get("value") or entry.get("requested_amount", "0.00")))
        total = Decimal(str(record.get("total", "0.00")))
        refunded = Decimal(str(record.get("refunded_total", "0.00"))) + refund_amount
        record["refunded_total"] = f"{min(refunded, total):.2f}"
        record["status"] = "REFUNDED" if refunded >= total else "PARTIALLY_REFUNDED"
        entry["counted_toward_total"] = True
        entry["amount"] = f"{refund_amount:.2f}"
    record["refund_status"] = status_value
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_payment_order(order_id, record)
    await track_event("paypal_refund_status_checked", "PayPal refund status refreshed.", {"order_id": order_id, "refund_id": refund_id, "status": status_value})
    return {"order_id": order_id, "refund_id": refund_id, "status": status_value, "amount": amount_data, "refunded_total": record.get("refunded_total", "0.00")}


@app.get("/api/orders/{order_id}/events")
def order_events(order_id: str, request: Request):
    require_admin_token(request)
    return {"order_id": order_id, "events": [event for event in EVENTS if event.get("order_id") == order_id]}


@app.post("/api/paypal/webhook")
async def paypal_webhook(request: Request):
    """Receive PayPal event notifications and verify them with PayPal before use.

    Configure this route as an HTTPS webhook in the PayPal Developer Dashboard.
    Localhost cannot receive PayPal webhooks directly without a public HTTPS tunnel.
    """
    try:
        event = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Webhook body must be valid JSON.") from exc
    if not isinstance(event, dict) or not event.get("id") or not event.get("event_type"):
        raise HTTPException(status_code=400, detail="Webhook event ID and event_type are required.")
    try:
        verified = await verify_webhook_signature(dict(request.headers), event)
    except PayPalError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"PayPal webhook verification returned HTTP {exc.response.status_code}.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Could not verify this PayPal webhook. Retry delivery.") from exc
    if not verified:
        await track_event("paypal_webhook_verification_failed", "Rejected an unverified PayPal webhook.", {"event_type": event.get("event_type")})
        raise HTTPException(status_code=400, detail="PayPal webhook signature verification failed.")

    event_id = str(event["id"])
    event_type = str(event["event_type"])
    if not record_webhook_once(event_id, event_type):
        return {"received": True, "duplicate": True}
    resource = event.get("resource") if isinstance(event.get("resource"), dict) else {}
    related = resource.get("supplementary_data", {}).get("related_ids", {}) if isinstance(resource.get("supplementary_data"), dict) else {}
    capture_id = resource.get("id") if event_type.startswith("PAYMENT.CAPTURE.") else related.get("capture_id")
    order_id_from_event = related.get("order_id") or resource.get("custom_id")
    matched_order_id = None
    matched_record = None
    for known_order_id, known_record in PAYMENT_ORDERS.items():
        if (order_id_from_event and known_order_id == str(order_id_from_event)) or (capture_id and known_record.get("capture_id") == str(capture_id)):
            matched_order_id, matched_record = known_order_id, known_record
            break
    if matched_record is not None:
        if event_type == "PAYMENT.CAPTURE.COMPLETED":
            matched_record["status"] = "COMPLETED"
            matched_record["capture_id"] = resource.get("id") or matched_record.get("capture_id")
            matched_record["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_payment_order(matched_order_id, matched_record)
            run = await dispatch_purchase_completed(matched_order_id, matched_record)
            await track_event("post_purchase_automation", "Verified PayPal webhook triggered post-purchase workflow.", {"order_id": matched_order_id, "status": run.get("status")})
        elif event_type == "PAYMENT.CAPTURE.REFUNDED":
            # PayPal's CAPTURE.REFUNDED webhook resource is capture-oriented; do not
            # blindly add resource.amount to a total already updated by our refund API.
            # A full-refund capture status is safe to reconcile; partial amounts are
            # reconciled through the recorded refund ID/status endpoint.
            capture_state = str(resource.get("status") or "").upper()
            matched_record["refund_status"] = "WEBHOOK_RECEIVED"
            if capture_state == "REFUNDED":
                matched_record["refunded_total"] = str(matched_record.get("total", "0.00"))
                matched_record["status"] = "REFUNDED"
                matched_record["refund_status"] = "COMPLETED"
            matched_record["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_payment_order(matched_order_id, matched_record)
        elif event_type == "PAYMENT.CAPTURE.DENIED":
            matched_record["refund_status"] = "CAPTURE_DENIED"
            matched_record["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_payment_order(matched_order_id, matched_record)
    await track_event("paypal_webhook_received", "Verified PayPal webhook received.", {
        "event_id": event_id, "event_type": event_type, "matched_order": bool(matched_order_id),
    })
    return {"received": True, "duplicate": False, "matched_order": matched_order_id}


@app.get("/api/automation/status")
def get_automation_status():
    return automation_status()


@app.post("/api/automation/retry/{order_id}")
async def retry_post_purchase_automation(order_id: str, request: Request):
    """Explicit operator retry for an unsuccessful/preview post-capture event."""
    require_admin_token(request)
    record = PAYMENT_ORDERS.get(order_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Order not found in AgentPay payment history.")
    if not record.get("capture_id") or record.get("status") not in {"COMPLETED", "PARTIALLY_REFUNDED", "REFUNDED"}:
        raise HTTPException(status_code=409, detail="Post-purchase notifications require a verified captured payment.")
    try:
        run = await dispatch_purchase_completed(order_id, record, allow_retry=True)
    except Exception as exc:
        await track_event("post_purchase_retry_error", "Operator retry of post-purchase automation failed.", {"order_id": order_id, "error_type": type(exc).__name__})
        raise HTTPException(status_code=502, detail="Post-purchase automation retry failed. Check the workflow status and server logs.") from exc
    await track_event("post_purchase_automation_retry", "Operator retried a post-purchase event.", {"order_id": order_id, "status": run.get("status")})
    return run


@app.get("/api/paypal-mcp/status")
def get_paypal_mcp_status():
    return paypal_mcp_status()


@app.get("/api/paypal-mcp/tools")
async def get_paypal_mcp_tools(request: Request):
    require_admin_token(request)
    current = paypal_mcp_status()
    if not current["configured"]:
        raise HTTPException(status_code=503, detail=current["message"])
    try:
        tools = await list_read_only_tools()
    except Exception as exc:
        await track_event("paypal_mcp_error", "Could not discover PayPal MCP tools.", {"error_type": type(exc).__name__})
        raise HTTPException(status_code=502, detail=f"PayPal MCP tool discovery failed ({type(exc).__name__}). Check Node.js/npm and MCP package connectivity.") from exc
    await track_event("paypal_mcp_tools_discovered", "PayPal MCP read-only tools discovered.", {"tool_count": len(tools)})
    return {"tools": tools, "count": len(tools), "mode": "sandbox_read_only"}


@app.post("/api/paypal-mcp/call")
async def call_paypal_mcp(request: PayPalMcpCallRequest, http_request: Request):
    require_admin_token(http_request)
    current = paypal_mcp_status()
    if not current["configured"]:
        raise HTTPException(status_code=503, detail=current["message"])
    try:
        result = await call_read_only_tool(request.tool_name, request.arguments)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await track_event("paypal_mcp_tool_error", "PayPal MCP tool invocation failed.", {"tool_name": request.tool_name[:100], "error_type": type(exc).__name__})
        raise HTTPException(status_code=502, detail=f"PayPal MCP tool invocation failed ({type(exc).__name__}).") from exc
    await track_event("paypal_mcp_tool_called", "Read-only PayPal MCP tool was called.", {"tool_name": request.tool_name[:100], "is_error": result.get("isError", False)})
    return result


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
    status["paypal_mcp_configured"] = paypal_mcp_configured()
    status["automation_configured"] = bool(settings.zapier_webhook_url.strip())
    status["admin_actions_configured"] = bool(settings.agentpay_admin_token.strip())
    return status


@app.get("/api/observability/events")
async def observability_events(q: str = Query(default="", max_length=120), limit: int = Query(default=25, ge=1, le=100)):
    return await telemetry.search(q, limit)
