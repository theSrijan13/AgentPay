# from typing import Any
# import base64
# import httpx
# from .config import settings

# class PayPalError(RuntimeError):
#     pass

# async def _access_token(client: httpx.AsyncClient) -> str:
#     if not settings.paypal_client_id or not settings.paypal_client_secret:
#         raise PayPalError("PayPal Sandbox credentials are not configured. Add them to backend/.env and restart FastAPI.")
#     raw = f"{settings.paypal_client_id}:{settings.paypal_client_secret}".encode()
#     basic = base64.b64encode(raw).decode()
#     response = await client.post(
#         f"{settings.paypal_base_url}/v1/oauth2/token",
#         headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
#         data={"grant_type": "client_credentials"},
#     )
#     response.raise_for_status()
#     return response.json()["access_token"]

# async def create_order(total_major_units: str, items: list[dict[str, Any]], currency: str = "USD", request_id: str | None = None) -> dict[str, Any]:
#     """Create a PayPal Checkout order in Sandbox using server-validated prices."""
#     async with httpx.AsyncClient(timeout=20) as client:
#         token = await _access_token(client)
#         headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
#         if request_id:
#             headers["PayPal-Request-Id"] = request_id
#         payload_items = [
#             {
#                 "name": str(item["name"])[:127],
#                 "quantity": str(item["quantity"]),
#                 "unit_amount": {"currency_code": currency, "value": f"{float(item['unit_price']):.2f}"},
#             }
#             for item in items
#         ]
#         response = await client.post(
#             f"{settings.paypal_base_url}/v2/checkout/orders",
#             headers=headers,
#             json={
#                 "intent": "CAPTURE",
#                 "purchase_units": [{
#                     "description": "AgentPay demo basket",
#                     "amount": {
#                         "currency_code": currency,
#                         "value": total_major_units,
#                         "breakdown": {"item_total": {"currency_code": currency, "value": total_major_units}},
#                     },
#                     "items": payload_items,
#                 }],
#                 "application_context": {"brand_name": "AgentPay", "user_action": "PAY_NOW"},
#             },
#         )
#         response.raise_for_status()
#         return response.json()

# async def capture_order(order_id: str, request_id: str | None = None) -> dict[str, Any]:
#     async with httpx.AsyncClient(timeout=20) as client:
#         token = await _access_token(client)
#         headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
#         if request_id:
#             headers["PayPal-Request-Id"] = request_id
#         response = await client.post(
#             f"{settings.paypal_base_url}/v2/checkout/orders/{order_id}/capture",
#             headers=headers,
#             json={},
#         )
#         response.raise_for_status()
#         return response.json()

from typing import Any
import base64
import httpx
from .config import settings

class PayPalError(RuntimeError):
    pass

async def _access_token(client: httpx.AsyncClient) -> str:
    if not settings.paypal_client_id or not settings.paypal_client_secret:
        raise PayPalError("PayPal Sandbox credentials are not configured. Add them to backend/.env and restart FastAPI.")
    raw = f"{settings.paypal_client_id}:{settings.paypal_client_secret}".encode()
    basic = base64.b64encode(raw).decode()
    response = await client.post(
        f"{settings.paypal_base_url}/v1/oauth2/token",
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials"},
    )
    response.raise_for_status()
    return response.json()["access_token"]

async def create_order(total_major_units: str, items: list[dict[str, Any]], currency: str = "USD", request_id: str | None = None) -> dict[str, Any]:
    """Create a PayPal Checkout order in Sandbox using server-validated prices."""
    async with httpx.AsyncClient(timeout=20) as client:
        token = await _access_token(client)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        payload_items = [
            {
                "name": str(item["name"])[:127],
                "quantity": str(item["quantity"]),
                "unit_amount": {"currency_code": currency, "value": f"{float(item['unit_price']):.2f}"},
            }
            for item in items
        ]
        response = await client.post(
            f"{settings.paypal_base_url}/v2/checkout/orders",
            headers=headers,
            json={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "description": "AgentPay demo basket",
                    "amount": {
                        "currency_code": currency,
                        "value": total_major_units,
                        "breakdown": {"item_total": {"currency_code": currency, "value": total_major_units}},
                    },
                    "items": payload_items,
                }],
                "application_context": {"brand_name": "AgentPay", "user_action": "PAY_NOW"},
            },
        )
        response.raise_for_status()
        return response.json()

async def capture_order(order_id: str, request_id: str | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        token = await _access_token(client)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        response = await client.post(
            f"{settings.paypal_base_url}/v2/checkout/orders/{order_id}/capture",
            headers=headers,
            json={},
        )
        response.raise_for_status()
        return response.json()


async def refund_capture(
    capture_id: str,
    amount_major_units: str | None = None,
    currency: str = "USD",
    note_to_payer: str = "AgentPay Sandbox refund",
    request_id: str | None = None,
) -> dict[str, Any]:
    """Refund a captured payment. Omitting amount requests a full refund."""
    async with httpx.AsyncClient(timeout=25) as client:
        token = await _access_token(client)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        payload: dict[str, Any] = {}
        if amount_major_units is not None:
            payload["amount"] = {"value": amount_major_units, "currency_code": currency}
            payload["note_to_payer"] = (note_to_payer or "AgentPay Sandbox refund")[:200]
        response = await client.post(
            f"{settings.paypal_base_url}/v2/payments/captures/{capture_id}/refund",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()


async def get_refund(refund_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        token = await _access_token(client)
        response = await client.get(
            f"{settings.paypal_base_url}/v2/payments/refunds/{refund_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        response.raise_for_status()
        return response.json()


async def verify_webhook_signature(headers_in: dict[str, str], event: dict[str, Any]) -> bool:
    """Use PayPal's verification endpoint; do not trust unverified webhook bodies."""
    if not settings.paypal_webhook_id.strip():
        raise PayPalError("PAYPAL_WEBHOOK_ID is not configured. Add the webhook ID from your PayPal Sandbox app.")
    required = {
        "transmission_id": headers_in.get("paypal-transmission-id"),
        "transmission_time": headers_in.get("paypal-transmission-time"),
        "transmission_sig": headers_in.get("paypal-transmission-sig"),
        "cert_url": headers_in.get("paypal-cert-url"),
        "auth_algo": headers_in.get("paypal-auth-algo"),
    }
    if any(not value for value in required.values()):
        return False
    async with httpx.AsyncClient(timeout=20) as client:
        token = await _access_token(client)
        response = await client.post(
            f"{settings.paypal_base_url}/v1/notifications/verify-webhook-signature",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                **required,
                "webhook_id": settings.paypal_webhook_id.strip(),
                "webhook_event": event,
            },
        )
        response.raise_for_status()
        return response.json().get("verification_status") == "SUCCESS"
