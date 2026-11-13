

"""Transactional SQLite inventory for AgentPay's first-party demo catalog.

Channel3 offers are intentionally not quantity-managed: Channel3 currently gives
AgentPay an availability signal, not an authoritative retailer stock count.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
import sqlite3

from .state_store import _LOCK, _connect


class InventoryError(ValueError):
    """A stock operation cannot be completed safely."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expire_due_reservations(conn: sqlite3.Connection, now: str) -> int:
    """Release expired reservations in the caller's transaction."""
    rows = conn.execute(
        "SELECT reservation_id FROM inventory_reservations "
        "WHERE status='RESERVED' AND expires_at <= ?",
        (now,),
    ).fetchall()
    expired_count = 0
    for reservation in rows:
        reservation_id = reservation["reservation_id"]
        items = conn.execute(
            "SELECT product_id, quantity FROM inventory_reservation_items WHERE reservation_id=?",
            (reservation_id,),
        ).fetchall()
        for item in items:
            conn.execute(
                "UPDATE inventory_items SET reserved=MAX(0, reserved-?), updated_at=? WHERE product_id=?",
                (item["quantity"], now, item["product_id"]),
            )
            conn.execute(
                "INSERT INTO inventory_movements(product_id, action, quantity, reference, note, created_at) "
                "VALUES(?, 'EXPIRE_RELEASE', ?, ?, 'Checkout reservation expired', ?)",
                (item["product_id"], item["quantity"], reservation_id, now),
            )
        conn.execute(
            "UPDATE inventory_reservations SET status='EXPIRED', completed_at=? WHERE reservation_id=?",
            (now, reservation_id),
        )
        expired_count += 1
    return expired_count


def initialize_inventory(products: Iterable[dict[str, Any]]) -> None:
    """Create inventory tables and seed finite-stock demo products exactly once."""
    now = _now()
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS inventory_items ("
                "product_id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL DEFAULT '', "
                "merchant TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'demo', "
                "on_hand INTEGER NOT NULL CHECK(on_hand >= 0), "
                "reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved >= 0 AND reserved <= on_hand), "
                "low_stock_threshold INTEGER NOT NULL DEFAULT 3 CHECK(low_stock_threshold >= 0), "
                "updated_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS inventory_reservations ("
                "reservation_id TEXT PRIMARY KEY, order_id TEXT UNIQUE, status TEXT NOT NULL, "
                "created_at TEXT NOT NULL, expires_at TEXT NOT NULL, completed_at TEXT)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS inventory_reservation_items ("
                "reservation_id TEXT NOT NULL, product_id TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity > 0), "
                "PRIMARY KEY(reservation_id, product_id))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS inventory_movements ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT NOT NULL, action TEXT NOT NULL, "
                "quantity INTEGER NOT NULL, reference TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', "
                "created_at TEXT NOT NULL)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inventory_movements_created ON inventory_movements(created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inventory_reservations_status_expiry ON inventory_reservations(status, expires_at)")

            for product in products:
                if not isinstance(product, dict):
                    continue
                product_id = str(product.get("id") or "").strip()
                stock = product.get("stock")
                source = str(product.get("source") or "demo")
                # Do not invent quantity for Channel3 or any product without finite stock.
                if not product_id or source == "channel3" or isinstance(stock, bool) or not isinstance(stock, int) or stock < 0:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO inventory_items "
                    "(product_id, name, category, merchant, source, on_hand, reserved, low_stock_threshold, updated_at) "
                    "VALUES(?,?,?,?,?,?,0,3,?)",
                    (
                        product_id,
                        str(product.get("name") or product_id)[:200],
                        str(product.get("category") or "")[:100],
                        str(product.get("merchant") or "")[:160],
                        source,
                        stock,
                        now,
                    ),
                )
                # Keep descriptive metadata fresh without resetting the stored stock.
                conn.execute(
                    "UPDATE inventory_items SET name=?, category=?, merchant=?, updated_at=? WHERE product_id=?",
                    (
                        str(product.get("name") or product_id)[:200],
                        str(product.get("category") or "")[:100],
                        str(product.get("merchant") or "")[:160],
                        now,
                        product_id,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def get_available_stock(product_id: str) -> int | None:
    """Return DB available units, or None when this is not quantity-managed inventory."""
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _expire_due_reservations(conn, _now())
            row = conn.execute(
                "SELECT on_hand, reserved FROM inventory_items WHERE product_id=?",
                (product_id,),
            ).fetchone()
            conn.commit()
            return None if row is None else max(0, int(row["on_hand"]) - int(row["reserved"]))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def reserve_inventory(items: Iterable[dict[str, Any]], reservation_id: str, expires_minutes: int = 30) -> bool:
    """Atomically reserve finite-stock items. Returns False when all items are availability-only."""
    requested: dict[str, int] = {}
    for item in items:
        product_id = str(item.get("product_id") or "").strip()
        quantity = item.get("quantity")
        if not product_id or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise InventoryError("Invalid inventory line item.")
        requested[product_id] = requested.get(product_id, 0) + quantity

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    expires_at = (now_dt + timedelta(minutes=max(1, min(expires_minutes, 120)))).isoformat()
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _expire_due_reservations(conn, now)
            tracked: list[tuple[str, int]] = []
            for product_id, quantity in requested.items():
                row = conn.execute(
                    "SELECT on_hand, reserved, name FROM inventory_items WHERE product_id=?",
                    (product_id,),
                ).fetchone()
                if row is None:
                    # Channel3/third-party offers have availability, not exact quantities.
                    continue
                available = int(row["on_hand"]) - int(row["reserved"])
                if quantity > available:
                    raise InventoryError(
                        f"Insufficient available inventory for {row['name']}. "
                        f"Available: {max(0, available)}, requested: {quantity}."
                    )
                tracked.append((product_id, quantity))

            if not tracked:
                conn.commit()
                return False

            conn.execute(
                "INSERT INTO inventory_reservations(reservation_id, order_id, status, created_at, expires_at) "
                "VALUES(?, NULL, 'RESERVED', ?, ?)",
                (reservation_id, now, expires_at),
            )
            for product_id, quantity in tracked:
                conn.execute(
                    "INSERT INTO inventory_reservation_items(reservation_id, product_id, quantity) VALUES(?,?,?)",
                    (reservation_id, product_id, quantity),
                )
                conn.execute(
                    "UPDATE inventory_items SET reserved=reserved+?, updated_at=? WHERE product_id=?",
                    (quantity, now, product_id),
                )
                conn.execute(
                    "INSERT INTO inventory_movements(product_id, action, quantity, reference, note, created_at) "
                    "VALUES(?, 'RESERVE', ?, ?, 'Reserved for PayPal checkout', ?)",
                    (product_id, quantity, reservation_id, now),
                )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def attach_inventory_reservation(reservation_id: str, order_id: str) -> None:
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE inventory_reservations SET order_id=? WHERE reservation_id=? AND status='RESERVED'",
                (order_id, reservation_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def release_inventory_reservation_by_id(reservation_id: str, reason: str = "Checkout creation failed") -> dict[str, Any]:
    return _release_reservation(reservation_id=reservation_id, reason=reason)


def release_inventory_reservation(order_id: str, reason: str = "Checkout was not completed") -> dict[str, Any]:
    return _release_reservation(order_id=order_id, reason=reason)


def _release_reservation(
    reservation_id: str | None = None,
    order_id: str | None = None,
    reason: str = "Checkout was not completed",
) -> dict[str, Any]:
    now = _now()
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if reservation_id:
                row = conn.execute("SELECT * FROM inventory_reservations WHERE reservation_id=?", (reservation_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM inventory_reservations WHERE order_id=?", (order_id,)).fetchone()
            if row is None:
                conn.commit()
                return {"released": False, "status": "NOT_TRACKED"}
            if row["status"] != "RESERVED":
                conn.commit()
                return {"released": False, "status": row["status"]}
            items = conn.execute(
                "SELECT product_id, quantity FROM inventory_reservation_items WHERE reservation_id=?",
                (row["reservation_id"],),
            ).fetchall()
            for item in items:
                conn.execute(
                    "UPDATE inventory_items SET reserved=MAX(0, reserved-?), updated_at=? WHERE product_id=?",
                    (item["quantity"], now, item["product_id"]),
                )
                conn.execute(
                    "INSERT INTO inventory_movements(product_id, action, quantity, reference, note, created_at) "
                    "VALUES(?, 'RELEASE', ?, ?, ?, ?)",
                    (item["product_id"], item["quantity"], row["reservation_id"], reason[:200], now),
                )
            conn.execute(
                "UPDATE inventory_reservations SET status='RELEASED', completed_at=? WHERE reservation_id=?",
                (now, row["reservation_id"]),
            )
            conn.commit()
            return {"released": True, "status": "RELEASED", "line_count": len(items)}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def extend_inventory_reservation(order_id: str, expires_minutes: int = 30) -> bool:
    """Keep a valid checkout hold alive while the buyer is completing PayPal capture."""
    now_dt = datetime.now(timezone.utc)
    expires_at = (now_dt + timedelta(minutes=max(1, min(expires_minutes, 120)))).isoformat()
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status FROM inventory_reservations WHERE order_id=?",
                (order_id,),
            ).fetchone()
            if row is None:
                # No quantity-managed items were in this order (for example, Channel3-only).
                conn.commit()
                return True
            if row["status"] != "RESERVED":
                raise InventoryError(
                    f"Inventory reservation is {row['status']}; create a new checkout instead of capturing this order."
                )
            conn.execute(
                "UPDATE inventory_reservations SET expires_at=? WHERE order_id=? AND status='RESERVED'",
                (expires_at, order_id),
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def complete_inventory_reservation(order_id: str) -> dict[str, Any]:
    """Deduct on-hand stock after verified PayPal capture; safe to call repeatedly."""
    now = _now()
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM inventory_reservations WHERE order_id=?", (order_id,)).fetchone()
            if row is None:
                conn.commit()
                return {"deducted": False, "status": "NOT_TRACKED"}
            if row["status"] == "COMMITTED":
                conn.commit()
                return {"deducted": False, "status": "ALREADY_COMMITTED"}
            if row["status"] != "RESERVED":
                conn.commit()
                return {"deducted": False, "status": row["status"]}

            items = conn.execute(
                "SELECT product_id, quantity FROM inventory_reservation_items WHERE reservation_id=?",
                (row["reservation_id"],),
            ).fetchall()
            for item in items:
                current = conn.execute(
                    "SELECT on_hand, reserved, name FROM inventory_items WHERE product_id=?",
                    (item["product_id"],),
                ).fetchone()
                if current is None or int(current["on_hand"]) < item["quantity"] or int(current["reserved"]) < item["quantity"]:
                    raise InventoryError(f"Inventory reconciliation failed for product {item['product_id']} after capture.")
            for item in items:
                conn.execute(
                    "UPDATE inventory_items SET on_hand=on_hand-?, reserved=reserved-?, updated_at=? WHERE product_id=?",
                    (item["quantity"], item["quantity"], now, item["product_id"]),
                )
                conn.execute(
                    "INSERT INTO inventory_movements(product_id, action, quantity, reference, note, created_at) "
                    "VALUES(?, 'SALE', ?, ?, 'Deducted after verified PayPal capture', ?)",
                    (item["product_id"], item["quantity"], order_id, now),
                )
            conn.execute(
                "UPDATE inventory_reservations SET status='COMMITTED', completed_at=? WHERE reservation_id=?",
                (now, row["reservation_id"]),
            )
            conn.commit()
            return {"deducted": True, "status": "COMMITTED", "line_count": len(items)}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def adjust_inventory(product_id: str, delta: int, note: str = "Operator stock adjustment") -> dict[str, Any]:
    if isinstance(delta, bool) or not isinstance(delta, int) or delta == 0:
        raise InventoryError("Adjustment delta must be a non-zero whole number.")
    now = _now()
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _expire_due_reservations(conn, now)
            row = conn.execute(
                "SELECT on_hand, reserved, name FROM inventory_items WHERE product_id=?",
                (product_id,),
            ).fetchone()
            if row is None:
                raise InventoryError("Product is not in AgentPay's quantity-managed inventory.")
            new_on_hand = int(row["on_hand"]) + delta
            if new_on_hand < int(row["reserved"]):
                raise InventoryError(
                    f"Adjustment would take on-hand stock below reserved stock ({row['reserved']} units reserved)."
                )
            if new_on_hand < 0:
                raise InventoryError("Inventory cannot become negative.")
            conn.execute(
                "UPDATE inventory_items SET on_hand=?, updated_at=? WHERE product_id=?",
                (new_on_hand, now, product_id),
            )
            conn.execute(
                "INSERT INTO inventory_movements(product_id, action, quantity, reference, note, created_at) "
                "VALUES(?, 'ADJUSTMENT', ?, '', ?, ?)",
                (product_id, delta, (note or "Operator stock adjustment")[:200], now),
            )
            conn.commit()
            return get_inventory_item(product_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def get_inventory_item(product_id: str) -> dict[str, Any] | None:
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM inventory_items WHERE product_id=?", (product_id,)).fetchone()
            return _serialize_inventory_item(row) if row else None
        finally:
            conn.close()


def _serialize_inventory_item(row: sqlite3.Row) -> dict[str, Any]:
    on_hand = int(row["on_hand"])
    reserved = int(row["reserved"])
    available = max(0, on_hand - reserved)
    threshold = int(row["low_stock_threshold"])
    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "category": row["category"],
        "merchant": row["merchant"],
        "source": row["source"],
        "on_hand": on_hand,
        "reserved": reserved,
        "available": available,
        "low_stock_threshold": threshold,
        "stock_status": "OUT_OF_STOCK" if available == 0 else ("LOW_STOCK" if available <= threshold else "IN_STOCK"),
        "updated_at": row["updated_at"],
    }


def inventory_snapshot() -> dict[str, Any]:
    now = _now()
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _expire_due_reservations(conn, now)
            item_rows = conn.execute("SELECT * FROM inventory_items ORDER BY name COLLATE NOCASE").fetchall()
            reservation_rows = conn.execute(
                "SELECT reservation_id, order_id, status, created_at, expires_at, completed_at "
                "FROM inventory_reservations ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
            movement_rows = conn.execute(
                "SELECT id, product_id, action, quantity, reference, note, created_at "
                "FROM inventory_movements ORDER BY id DESC LIMIT 30"
            ).fetchall()
            items = [_serialize_inventory_item(row) for row in item_rows]
            reservations = [dict(row) for row in reservation_rows]
            movements = [dict(row) for row in movement_rows]
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    summary = {
        "sku_count": len(items),
        "on_hand": sum(item["on_hand"] for item in items),
        "reserved": sum(item["reserved"] for item in items),
        "available": sum(item["available"] for item in items),
        "low_stock_count": sum(item["stock_status"] == "LOW_STOCK" for item in items),
        "out_of_stock_count": sum(item["stock_status"] == "OUT_OF_STOCK" for item in items),
    }
    return {"summary": summary, "items": items, "reservations": reservations, "movements": movements, "generated_at": now}
