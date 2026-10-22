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
