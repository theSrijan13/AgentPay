#!/usr/bin/env python3
"""Apply AgentPay Inventory Management v1 to an existing AgentPay project.

Run from an extracted inventory-v1 patch folder located at the AgentPay project root:
    python scripts/apply_inventory_v1.py
The script backs up each edited file before patching it and is idempotent.
"""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "backend/app/main.py"
STATE = ROOT / "backend/app/state_store.py"
APP = ROOT / "frontend/src/App.tsx"


def backup(path: Path) -> None:
    backup_path = path.with_name(path.name + ".pre-inventory-v1.bak")
    if not backup_path.exists():
        shutil.copy2(path, backup_path)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match for {label}; found {count}.")
    return source.replace(old, new, 1)



def regex_replace_once(source: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, source, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Expected exactly one regex match for {label}; found {count}.")
    return updated


def patch_main(source: str) -> str:
    if "from .inventory_service import (" in source:
        return source

    source = replace_once(
        source,
        "from .state_store import load_payment_orders, record_webhook_once, save_payment_order\n",
        "from .state_store import load_payment_orders, record_webhook_once, save_payment_order\n"
        "from .inventory_service import (\n"
        "    InventoryError, adjust_inventory, attach_inventory_reservation,\n"
        "    complete_inventory_reservation, extend_inventory_reservation,\n"
        "    get_available_stock, initialize_inventory, inventory_snapshot,\n"
        "    release_inventory_reservation, release_inventory_reservation_by_id, reserve_inventory,\n"
        ")\n",
        "inventory service import",
    )

    source = replace_once(
        source,
        "EVENTS: list[dict[str, Any]] = []\n",
        "EVENTS: list[dict[str, Any]] = []\n\n"
        "# Seed finite-stock demo products once; SQLite remains the source of truth afterwards.\n"
        "initialize_inventory(PRODUCT_BY_ID.values())\n",
        "inventory initialization",
    )

    # Replace stock validation with a database-backed, duplicate-line-safe check.
    validate_start = source.find("def validate_items(items, budget=None):")
    validate_end = source.find('@app.post("/api/cart/validate")', validate_start)
    if validate_start < 0 or validate_end < 0:
        raise RuntimeError("Could not find validate_items() in backend/app/main.py.")
    block = source[validate_start:validate_end]
    block = regex_replace_once(
        block,
        r'    total = Decimal\("0\.00"\)\n(?:[ \t]*\n)*    for item in items:',
        '    total = Decimal("0.00")\n    requested_quantity_by_id: dict[str, int] = {}\n    for item in items:',
        "duplicate-safe quantity accumulator",
    )
    block = regex_replace_once(
        block,
        r'        stock = product\.get\("stock"\)\n(?:[ \t]*\n)*        if stock is not None and item\.quantity > stock:\n(?:[ \t]*\n)*            raise HTTPException\(status_code=400, detail=f"Insufficient stock for .+?"\)',
        '        requested_quantity = requested_quantity_by_id.get(product["id"], 0) + item.quantity\n'
        '        requested_quantity_by_id[product["id"]] = requested_quantity\n'
        '        live_available = get_available_stock(product["id"])\n'
        '        stock = live_available if live_available is not None else product.get("stock")\n'
        '        if stock is not None and requested_quantity > stock:\n'
        '            raise HTTPException(status_code=400, detail=f"Insufficient stock for product[\'name\']")',
        "database-backed stock validation",
    )
    source = source[:validate_start] + block + source[validate_end:]

    # Reserve stock atomically before a PayPal order is created.
    create_start = source.find('@app.post("/api/payments/create-order")')
    create_end = source.find('@app.post("/api/payments/capture/{order_id}")', create_start)
    if create_start < 0 or create_end < 0:
        raise RuntimeError("Could not find the PayPal create-order and capture routes.")
    block = source[create_start:create_end]
    block = regex_replace_once(
        block,
        r'    request_id = str\(uuid\.uuid4\(\)\)\n(?:[ \t]*\n)*    try:\n(?:[ \t]*\n)*        result = await create_order\(f"\{total:\.2f\}", items, currency="USD", request_id=request_id\)',
        '    inventory_reservation_id = str(uuid.uuid4())\n'
        '    try:\n'
        '        inventory_reserved = reserve_inventory(items, inventory_reservation_id, expires_minutes=30)\n'
        '    except InventoryError as exc:\n'
        '        raise HTTPException(status_code=409, detail=str(exc)) from exc\n\n'
        '    request_id = str(uuid.uuid4())\n'
        '    try:\n'
        '        result = await create_order(f"{total:.2f}", items, currency="USD", request_id=request_id)',
        "pre-PayPal inventory reservation",
    )

    # Release the reservation on every known order-creation failure path.
    for exception_line in (
        '    except PayPalError as exc:\n',
        '    except httpx.HTTPStatusError as exc:\n',
        '    except httpx.RequestError as exc:\n',
    ):
        if exception_line not in block:
            raise RuntimeError(f"Could not find {exception_line.strip()} in create-order route.")
        block = block.replace(
            exception_line,
            exception_line
            + '        if inventory_reserved:\n'
            + '            try:\n'
            + '                release_inventory_reservation_by_id(inventory_reservation_id, "PayPal order creation failed")\n'
            + '            except Exception:\n'
            + '                pass\n',
            1,
        )

    block = regex_replace_once(
        block,
        r'    if not order_id:\n(?:[ \t]*\n)*        raise HTTPException\(status_code=502, detail="PayPal did not return an order ID\."\)(?:\n(?:[ \t]*\n)*)?',
        '    if not order_id:\n'
        '        if inventory_reserved:\n'
        '            release_inventory_reservation_by_id(inventory_reservation_id, "PayPal did not return an order ID")\n'
        '        raise HTTPException(status_code=502, detail="PayPal did not return an order ID.")\n'
        '    if inventory_reserved:\n'
        '        attach_inventory_reservation(inventory_reservation_id, order_id)\n',
        "attach inventory reservation to PayPal order",
    )

    block = replace_once(
        block,
        '        "status": "CREATED", "items": items, "total": f"{total:.2f}",\n',
        '        "status": "CREATED", "items": items, "total": f"{total:.2f}",\n'
        '        "inventory_reservation_id": inventory_reservation_id if inventory_reserved else None,\n'
        '        "inventory_status": "RESERVED" if inventory_reserved else "AVAILABILITY_ONLY",\n',
        "persist inventory reservation metadata",
    )
    source = source[:create_start] + block + source[create_end:]

    # Extend a hold immediately before capture; deduct only after PayPal confirms COMPLETED.
    capture_start = source.find('@app.post("/api/payments/capture/{order_id}")')
    capture_end = source.find('@app.get("/api/orders/{order_id}")', capture_start)
    if capture_start < 0 or capture_end < 0:
        raise RuntimeError("Could not find payments_capture() in backend/app/main.py.")
    block = source[capture_start:capture_end]
    block = regex_replace_once(
        block,
        r'    try:\n(?:[ \t]*\n)*        result = await capture_order\(order_id, request_id=record\["capture_request_id"\]\)',
        '    try:\n'
        '        extend_inventory_reservation(order_id, expires_minutes=30)\n'
        '    except Exception as exc:\n'
        '        await track_event("inventory_reservation_extend_error", "Could not extend the inventory hold before PayPal capture.", {"order_id": order_id, "error_type": type(exc).__name__})\n'
        '        raise HTTPException(status_code=503, detail="Could not verify the inventory reservation. Retry capture after checking inventory status.") from exc\n\n'
        '    try:\n'
        '        result = await capture_order(order_id, request_id=record["capture_request_id"])',
        "extend inventory hold before capture",
    )
    block = regex_replace_once(
        block,
        r'    record\["capture_id"\] = captures\[0\]\.get\("id"\)\n(?:[ \t]*\n)*    record\["updated_at"\] = datetime\.now\(timezone\.utc\)\.isoformat\(\)',
        '    record["capture_id"] = captures[0].get("id")\n'
        '    try:\n'
        '        inventory_result = complete_inventory_reservation(order_id)\n'
        '        record["inventory_status"] = inventory_result.get("status", "UNKNOWN")\n'
        '        if inventory_result.get("deducted"):\n'
        '            await track_event("inventory_stock_deducted", "Inventory was deducted after verified PayPal capture.", {"order_id": order_id, "line_count": inventory_result.get("line_count")})\n'
        '    except Exception as inventory_exc:\n'
        '        record["inventory_status"] = "RECONCILIATION_REQUIRED"\n'
        '        await track_event("inventory_capture_reconciliation_error", "PayPal capture completed but inventory needs operator reconciliation.", {"order_id": order_id, "error_type": type(inventory_exc).__name__})\n'
        '    record["updated_at"] = datetime.now(timezone.utc).isoformat()',
        "deduct inventory after successful capture",
    )
    source = source[:capture_start] + block + source[capture_end:]

    # Keep webhook capture completion idempotent with the synchronous capture route.
    webhook_start = source.find('@app.post("/api/paypal/webhook")')
    webhook_end = source.find('@app.get("/api/automation/status")', webhook_start)
    if webhook_start < 0 or webhook_end < 0:
        raise RuntimeError("Could not find PayPal webhook route.")
    block = source[webhook_start:webhook_end]
    block = regex_replace_once(
        block,
        r'            matched_record\["capture_id"\] = resource\.get\("id"\) or matched_record\.get\("capture_id"\)\n(?:[ \t]*\n)*            matched_record\["updated_at"\] = datetime\.now\(timezone\.utc\)\.isoformat\(\)',
        '            matched_record["capture_id"] = resource.get("id") or matched_record.get("capture_id")\n'
        '            try:\n'
        '                inventory_result = complete_inventory_reservation(matched_order_id)\n'
        '                matched_record["inventory_status"] = inventory_result.get("status", "UNKNOWN")\n'
        '                if inventory_result.get("deducted"):\n'
        '                    await track_event("inventory_stock_deducted", "Inventory was deducted after verified PayPal capture webhook.", {"order_id": matched_order_id, "line_count": inventory_result.get("line_count")})\n'
        '            except Exception as inventory_exc:\n'
        '                matched_record["inventory_status"] = "RECONCILIATION_REQUIRED"\n'
        '                await track_event("inventory_webhook_reconciliation_error", "Verified PayPal capture webhook arrived but inventory needs operator reconciliation.", {"order_id": matched_order_id, "error_type": type(inventory_exc).__name__})\n'
        '            matched_record["updated_at"] = datetime.now(timezone.utc).isoformat()',
        "webhook inventory deduction",
    )
    source = source[:webhook_start] + block + source[webhook_end:]

    # Operator-only inventory dashboard and stock adjustment endpoints.
    marker = '@app.get("/api/subscriptions")'
    if marker not in source:
        raise RuntimeError("Could not find insertion point before subscription routes.")
    inventory_routes = '''@app.get("/api/inventory")
async def get_inventory(request: Request):
    """Operator-only inventory snapshot, including reservation and movement history."""
    require_admin_token(request)
    snapshot = inventory_snapshot()
    await track_event("inventory_viewed", "Operator viewed the AgentPay inventory dashboard.", {
        "sku_count": snapshot["summary"]["sku_count"],
        "available": snapshot["summary"]["available"],
        "reserved": snapshot["summary"]["reserved"],
    })
    return snapshot


@app.post("/api/inventory/adjust")
async def inventory_adjust(request: Request):
    """Operator-only manual inventory correction or replenishment."""
    require_admin_token(request)
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Request body must be a JSON object.")
    product_id = str(payload.get("product_id") or "").strip()
    delta = payload.get("delta")
    note = str(payload.get("note") or "Operator stock adjustment")[:200]
    if not product_id:
        raise HTTPException(status_code=422, detail="product_id is required.")
    if isinstance(delta, bool) or not isinstance(delta, int) or delta == 0:
        raise HTTPException(status_code=422, detail="delta must be a non-zero whole number.")
    try:
        item = adjust_inventory(product_id, delta, note)
    except InventoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await track_event("inventory_adjusted", "Operator adjusted AgentPay demo inventory.", {
        "product_id": product_id, "delta": delta, "available": item["available"],
    })
    return {"item": item}


@app.post("/api/inventory/reservations/{order_id}/release")
async def inventory_release_reservation(order_id: str, request: Request):
    """Explicit operator release for a checkout known to have been abandoned."""
    require_admin_token(request)
    result = release_inventory_reservation(order_id, "Operator released an abandoned checkout")
    await track_event("inventory_reservation_operator_release", "Operator released an inventory reservation.", {
        "order_id": order_id, "status": result.get("status"),
    })
    return result


'''
    source = replace_once(source, marker, inventory_routes + marker, "inventory API routes")
    return source


def patch_state_store(source: str) -> str:
    if '"inventory_reservation_id"' in source:
        return source
    return replace_once(
        source,
        '    "refunds", "refunded_total", "refund_status", "updated_at",\n',
        '    "refunds", "refunded_total", "refund_status", "updated_at",\n'
        '    "inventory_reservation_id", "inventory_status",\n',
        "persist inventory metadata in payment records",
    )


def patch_app(source: str) -> str:
    if "import InventoryManagement from './InventoryManagement'" in source:
        return source
    source = replace_once(
        source,
        "import AgentPaySubscriptionCheckout from './AgentPaySubscriptionCheckout'\n",
        "import AgentPaySubscriptionCheckout from './AgentPaySubscriptionCheckout'\n"
        "import InventoryManagement from './InventoryManagement'\n",
        "inventory component import",
    )
    source = replace_once(
        source,
        '      <button className="nav-item" onClick={() => document.getElementById(\'subscription-center\')?.scrollIntoView({ behavior: \'smooth\', block: \'start\' })}><Repeat2 size={17} /> Subscriptions</button>\n',
        '      <button className="nav-item" onClick={() => document.getElementById(\'subscription-center\')?.scrollIntoView({ behavior: \'smooth\', block: \'start\' })}><Repeat2 size={17} /> Subscriptions</button>\n'
        '      <button className="nav-item" onClick={() => document.getElementById(\'inventory-management\')?.scrollIntoView({ behavior: \'smooth\', block: \'start\' })}><ShoppingBag size={17} /> Inventory</button>\n',
        "inventory sidebar navigation",
    )
    source = replace_once(
        source,
        '      <section id="subscription-center" className="subscription-center">\n'
        '        <AgentPaySubscriptionCheckout />\n'
        '        <SubscriptionManagement adminToken={adminToken} />\n'
        '      </section>\n',
        '      <section id="subscription-center" className="subscription-center">\n'
        '        <AgentPaySubscriptionCheckout />\n'
        '        <SubscriptionManagement adminToken={adminToken} />\n'
        '      </section>\n'
        '      <InventoryManagement adminToken={adminToken} />\n',
        "inventory dashboard placement",
    )
    return source


def main() -> int:
    for path in (MAIN, STATE, APP):
        if not path.exists():
            print(f"Missing required file: {path}", file=sys.stderr)
            return 2

    backup(MAIN)
    backup(STATE)
    backup(APP)

    try:
        main_source = patch_main(MAIN.read_text())
        state_source = patch_state_store(STATE.read_text())
        app_source = patch_app(APP.read_text())
    except Exception as exc:
        print(f"Patch was not applied: {exc}", file=sys.stderr)
        print("Original files were backed up with .pre-inventory-v1.bak suffixes.", file=sys.stderr)
        return 1

    MAIN.write_text(main_source)
    STATE.write_text(state_source)
    APP.write_text(app_source)
    print("AgentPay Inventory Management v1 patch applied.")
    print("Created backups: main.py.pre-inventory-v1.bak, state_store.py.pre-inventory-v1.bak, App.tsx.pre-inventory-v1.bak")
    print("Next: run backend tests, then npm run build in frontend/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
