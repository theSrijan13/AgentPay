"""Read-only PayPal Subscriptions API integration for AgentPay Milestone 1."""
from __future__ import annotations
import uuid
import re
from typing import Any

import httpx

from .config import settings
from .paypal import PayPalError, _subscriptions_access_token

_ALLOWED_STATUSES = {
    "APPROVAL_PENDING", "APPROVED", "ACTIVE", "SUSPENDED", "CANCELLED", "EXPIRED"
}
_SUBSCRIPTION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,50}$")


def validate_status(status: str | None) -> str | None:
    if status is None or not status.strip():
        return None
    value = status.strip().upper()
    if value not in _ALLOWED_STATUSES:
        allowed = ", ".join(sorted(_ALLOWED_STATUSES))
        raise ValueError(f"Unsupported subscription status. Choose one of: {allowed}.")
    return value


def validate_subscription_id(subscription_id: str) -> str:
    value = subscription_id.strip()
    if not _SUBSCRIPTION_ID_RE.fullmatch(value):
        raise ValueError("Invalid PayPal subscription ID format.")
    return value


def _money(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    amount = value.get("value")
    currency = value.get("currency_code")
    if amount is None or currency is None:
        return None
    return {"value": str(amount), "currency_code": str(currency)}


def _name(subscriber: Any) -> str | None:
    if not isinstance(subscriber, dict):
        return None
    name = subscriber.get("name")
    if not isinstance(name, dict):
        return None
    parts = [str(name.get(key, "")).strip() for key in ("given_name", "surname")]
    full = " ".join(part for part in parts if part)
    return full or None


def _subscriber_summary(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {}
    if value.get("email_address"):
        result["email_address"] = str(value["email_address"])
    customer_name = _name(value)
    if customer_name:
        result["name"] = customer_name
    # Deliberately omit payment-source, card, phone, and shipping-address details.
    return result or None


def _billing_summary(value: Any, include_failed: bool = False) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {}
    if value.get("next_billing_time"):
        result["next_billing_time"] = value["next_billing_time"]
    if value.get("final_payment_time"):
        result["final_payment_time"] = value["final_payment_time"]
    if value.get("failed_payments_count") is not None:
        result["failed_payments_count"] = value["failed_payments_count"]
    outstanding = _money(value.get("outstanding_balance"))
    if outstanding:
        result["outstanding_balance"] = outstanding
    last_payment = value.get("last_payment")
    if isinstance(last_payment, dict):
        last = {}
        amount = _money(last_payment.get("amount"))
        if amount:
            last["amount"] = amount
        if last_payment.get("time"):
            last["time"] = last_payment["time"]
        if last:
            result["last_payment"] = last
    if include_failed:
        failed = value.get("last_failed_payment")
        if isinstance(failed, dict):
            item: dict[str, Any] = {}
            amount = _money(failed.get("amount"))
            if amount:
                item["amount"] = amount
            for key in ("time", "reason_code", "next_payment_retry_time"):
                if failed.get(key):
                    item[key] = failed[key]
            if item:
                result["last_failed_payment"] = item
    return result or None


async def create_paypal_subscription() -> dict[str, Any]:
    """
    Create a subscription using AgentPay's configured PayPal plan.

    The plan ID is controlled by the backend, not supplied by the browser.
    The buyer must still approve the subscription through PayPal.
    """
    plan_id = settings.paypal_subscriptions_plan_id.strip()

    if not plan_id:
        raise PayPalError(
            "Subscription plan is not configured. "
            "Set PAYPAL_SUBSCRIPTIONS_PLAN_ID in backend/.env."
        )

    if not re.fullmatch(r"P-[A-Z0-9]{20,30}", plan_id):
        raise PayPalError("The configured PayPal subscription plan ID is invalid.")

    async with httpx.AsyncClient(timeout=25) as client:
        token = await _subscriptions_access_token(client)

        response = await client.post(
            f"{settings.paypal_subscriptions_base_url.rstrip('/')}"
            "/v1/billing/subscriptions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": str(uuid.uuid4()),
            },
            json={
                "plan_id": plan_id,
                "application_context": {
                    "brand_name": "AgentPay",
                    "locale": "en-US",
                    "shipping_preference": "NO_SHIPPING",
                    "user_action": "SUBSCRIBE_NOW",
                },
            },
        )

        response.raise_for_status()
        payload = response.json()

    subscription_id = payload.get("id")

    if not subscription_id:
        raise PayPalError(
            "PayPal did not return a subscription ID."
        )

    return {
        "id": subscription_id,
        "subscriptionId": subscription_id,
        "status": payload.get("status", "APPROVAL_PENDING"),
        "plan_id": payload.get("plan_id"),
    }


async def verify_paypal_subscription(
    subscription_id: str,
) -> dict[str, Any]:
    """
    Verify the subscription directly against PayPal.

    The browser's approval callback is not trusted by itself.
    The subscription must belong to AgentPay's configured plan and
    PayPal must report it as approved or active.
    """
    safe_id = validate_subscription_id(subscription_id)

    expected_plan_id = settings.paypal_subscriptions_plan_id.strip()

    if not expected_plan_id:
        raise PayPalError("PayPal subscription plan is not configured.")

    subscription = await get_paypal_subscription(safe_id)

    actual_plan_id = subscription.get("plan_id")
    status = str(subscription.get("status") or "").upper()

    if actual_plan_id != expected_plan_id:
        raise ValueError(
            "This subscription does not belong to the configured AgentPay plan."
        )

    if status not in {"APPROVED", "ACTIVE"}:
        raise ValueError(
            f"PayPal has not confirmed an approved subscription. "
            f"Current status: {status or 'UNKNOWN'}."
        )

    return {
        "id": safe_id,
        "status": status,
        "plan_id": actual_plan_id,
        "verified": True,
    }

def normalize_subscription(value: Any, include_plan: bool = False) -> dict[str, Any]:
    """Return only business-relevant fields; never forward stored card/address data."""
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key in ("id", "status", "plan_id", "start_time", "create_time", "update_time", "status_update_time", "status_change_note", "quantity"):
        if value.get(key) is not None:
            result[key] = value[key]
    subscriber = _subscriber_summary(value.get("subscriber"))
    if subscriber:
        result["subscriber"] = subscriber
    billing = _billing_summary(value.get("billing_info"), include_failed=include_plan)
    if billing:
        result["billing_info"] = billing
    if include_plan:
        plan = value.get("plan")
        if isinstance(plan, dict):
            safe_plan: dict[str, Any] = {}
            for key in ("id", "name", "description", "product_id"):
                if plan.get(key) is not None:
                    safe_plan[key] = plan[key]
            cycles = plan.get("billing_cycles")
            if isinstance(cycles, list):
                safe_cycles = []
                for cycle in cycles:
                    if not isinstance(cycle, dict):
                        continue
                    safe_cycle: dict[str, Any] = {}
                    for key in ("tenure_type", "sequence", "total_cycles"):
                        if cycle.get(key) is not None:
                            safe_cycle[key] = cycle[key]
                    frequency = cycle.get("frequency")
                    if isinstance(frequency, dict):
                        safe_cycle["frequency"] = {
                            key: frequency[key] for key in ("interval_unit", "interval_count") if frequency.get(key) is not None
                        }
                    pricing = cycle.get("pricing_scheme")
                    if isinstance(pricing, dict):
                        fixed_price = _money(pricing.get("fixed_price"))
                        if fixed_price:
                            safe_cycle["fixed_price"] = fixed_price
                    if safe_cycle:
                        safe_cycles.append(safe_cycle)
                if safe_cycles:
                    safe_plan["billing_cycles"] = safe_cycles
            if safe_plan:
                result["plan"] = safe_plan
    return result


async def list_paypal_subscriptions(page: int = 1, page_size: int = 20, status: str | None = None) -> dict[str, Any]:
    """List subscriptions for the configured PayPal merchant account."""
    status_value = validate_status(status)
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if status_value:
        params["statuses"] = status_value

    async with httpx.AsyncClient(timeout=25) as client:
        token = await _subscriptions_access_token(client)
        response = await client.get(
            f"{settings.paypal_subscriptions_base_url}/v1/billing/subscriptions",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            params=params,
        )
        response.raise_for_status()
        payload = response.json()

    raw_subscriptions = payload.get("subscriptions", [])
    subscriptions = [normalize_subscription(item) for item in raw_subscriptions if isinstance(item, dict)]
    links = payload.get("links", []) if isinstance(payload.get("links", []), list) else []
    has_next = any(isinstance(link, dict) and link.get("rel") == "next" for link in links)
    has_previous = any(isinstance(link, dict) and link.get("rel") in {"prev", "previous"} for link in links)
    # A full page is a safe fallback when PayPal omits HATEOAS pagination links.
    if not links and len(subscriptions) == page_size:
        has_next = True
    return {
        "subscriptions": subscriptions,
        "page": page,
        "page_size": page_size,
        "status_filter": status_value,
        "has_next": has_next,
        "has_previous": has_previous or page > 1,
        "links": links,
    }


async def get_paypal_subscription(subscription_id: str) -> dict[str, Any]:
    """Fetch detailed billing and plan information for one subscription."""
    safe_id = validate_subscription_id(subscription_id)
    async with httpx.AsyncClient(timeout=25) as client:
        token = await _subscriptions_access_token(client)
        response = await client.get(
            f"{settings.paypal_subscriptions_base_url}/v1/billing/subscriptions/{safe_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            params={"fields": "plan,last_failed_payment"},
        )
        response.raise_for_status()
        payload = response.json()
    return normalize_subscription(payload, include_plan=True)
