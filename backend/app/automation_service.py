"""Post-purchase notification workflow with optional Zapier Catch Hook integration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from .config import settings
from .state_store import load_automation_runs, save_automation_run


async def dispatch_purchase_completed(
    order_id: str, record: dict[str, Any], *, allow_retry: bool = False
) -> dict[str, Any]:
    """Create one post-purchase run per order; send an event only when configured.

    This sends a notification/automation event, not a retailer order. Set a Zapier
    Catch Hook URL only after deciding which downstream Zap actions should run.
    """
    existing = next((run for run in load_automation_runs(100) if run.get("order_id") == order_id), None)
    if existing and (existing.get("status") == "sent" or not allow_retry):
        # Do not replay a successful delivery. Failed/preview attempts can be retried
        # only through the explicit operator endpoint. Downstream workflows should
        # deduplicate the stable X-AgentPay-Event-ID value.
        return existing

    items = []
    for item in record.get("items", [])[:30]:
        items.append({
            "product_id": str(item.get("product_id", ""))[:160],
            "name": str(item.get("name", ""))[:127],
            "quantity": int(item.get("quantity", 1)),
            "unit_price": str(item.get("unit_price", "0.00")),
            "merchant": str(item.get("merchant", ""))[:120] if item.get("merchant") else None,
        })
    event = {
        "event": "agentpay.payment.completed",
        "event_id": f"agentpay-payment-completed-{order_id}",
        "environment": "sandbox",
        "order_id": order_id,
        "capture_id": record.get("capture_id"),
        "status": record.get("status", "COMPLETED"),
        "amount": str(record.get("total", "0.00")),
        "currency": str(record.get("currency", "USD")),
        "items": items,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    url = settings.zapier_webhook_url.strip()
    if not url:
        run = {
            "order_id": order_id, "status": "preview_only",
            "message": "Payment receipt event recorded locally. Configure ZAPIER_WEBHOOK_URL to trigger an external workflow.",
            "event": event, "timestamp": event["created_at"],
        }
        save_automation_run(order_id, run)
        return run

    # Keep webhook destination private: never log the URL or return it to the browser.
    if not url.startswith("https://"):
        run = {
            "order_id": order_id, "status": "failed",
            "message": "Automation URL must use HTTPS. Update ZAPIER_WEBHOOK_URL and restart FastAPI.",
            "timestamp": event["created_at"],
        }
        save_automation_run(order_id, run)
        return run

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "X-AgentPay-Event": "agentpay.payment.completed",
                    "X-AgentPay-Event-ID": event["event_id"],
                },
                json=event,
            )
        response.raise_for_status()
        run = {
            "order_id": order_id, "status": "sent",
            "message": "Post-purchase event delivered to the configured automation webhook.",
            "http_status": response.status_code, "timestamp": event["created_at"],
        }
    except httpx.HTTPStatusError as exc:
        run = {
            "order_id": order_id, "status": "failed",
            "message": f"Automation webhook returned HTTP {exc.response.status_code}. Check the configured Zapier hook and downstream Zap.",
            "timestamp": event["created_at"],
        }
    except httpx.RequestError as exc:
        run = {
            "order_id": order_id, "status": "failed",
            "message": f"Automation webhook could not be reached ({type(exc).__name__}).",
            "timestamp": event["created_at"],
        }
    save_automation_run(order_id, run)
    return run


def automation_status() -> dict[str, Any]:
    # Return only workflow summary fields to the browser. The underlying persisted
    # event includes item metadata for the operator workflow, but it is not necessary
    # to expose that payload on the public status endpoint.
    runs = []
    for run in load_automation_runs(10):
        runs.append({
            "order_id": run.get("order_id"),
            "status": run.get("status", "unknown"),
            "message": run.get("message", ""),
            "timestamp": run.get("timestamp"),
            "http_status": run.get("http_status"),
        })
    configured = bool(settings.zapier_webhook_url.strip())
    return {
        "configured": configured,
        "mode": "zapier_webhook" if configured else "preview_only",
        "message": "Zapier webhook configured; successful Sandbox captures trigger a post-purchase event." if configured else "Local receipt preview is enabled. Add ZAPIER_WEBHOOK_URL to backend/.env to deliver events to Zapier.",
        "runs": runs,
    }
