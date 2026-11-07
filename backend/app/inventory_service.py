# """Inventory Management Service — AgentPay v1.

# Provides transactional stock reservation, payment-confirmed deduction,
# reservation expiry, and movement history backed by the existing SQLite store.

# Design:
# - Demo catalog products with a numeric `stock` field get full reservation tracking.
# - Channel3 products have InStock/OutOfStock availability only; no quantity tracking.
# - All mutations run inside a threading.RLock + SQLite BEGIN IMMEDIATE for concurrency safety.
# """
# from __future__ import annotations

# import sqlite3
# import uuid
# from datetime import datetime, timedelta, timezone
# from typing import Any

# from .state_store import _LOCK, _connect

# # Reservation TTL — stock is released automatically after this window.
# RESERVATION_TTL_MINUTES = 15


# # ---------------------------------------------------------------------------
# # Schema bootstrap (called once at startup)
# # ---------------------------------------------------------------------------

# def init_inventory_schema() -> None:
#     """Create inventory tables if they don't exist yet."""
#     with _LOCK:
#         conn = _connect()
#         try:
#             conn.executescript("""
#                 CREATE TABLE IF NOT EXISTS inventory (
#                     product_id   TEXT PRIMARY KEY,
#                     name         TEXT NOT NULL DEFAULT '',
#                     available_qty INTEGER NOT NULL DEFAULT 0,
#                     reserved_qty  INTEGER NOT NULL DEFAULT 0,
#                     sold_qty      INTEGER NOT NULL DEFAULT 0,
#                     updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
#                 );

#                 CREATE TABLE IF NOT EXISTS inventory_reservations (
#                     reservation_id TEXT PRIMARY KEY,
#                     order_id       TEXT NOT NULL,
#                     product_id     TEXT NOT NULL,
#                     quantity       INTEGER NOT NULL,
#                     status         TEXT NOT NULL DEFAULT 'PENDING',
#                     expires_at     TEXT NOT NULL,
#                     created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
#                     updated_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
#                 );

#                 CREATE TABLE IF NOT EXISTS inventory_movements (
#                     id            INTEGER PRIMARY KEY AUTOINCREMENT,
#                     product_id    TEXT NOT NULL,
#                     movement_type TEXT NOT NULL,
#                     quantity      INTEGER NOT NULL,
#                     order_id      TEXT,
#                     note          TEXT,
#                     created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
#                 );
#             """)
#             conn.commit()
#         finally:
#             conn.close()


# def seed_inventory_from_catalog() -> None:
#     """Seed inventory table from the demo catalog on first run.

#     Safe to call on every startup — existing rows are not overwritten.
#     Channel3 products are excluded (no numeric stock).
#     """
#     from .catalog import PRODUCTS  # local import to avoid circular deps

#     with _LOCK:
#         conn = _connect()
#         try:
#             conn.execute("BEGIN IMMEDIATE")
#             for product in PRODUCTS:
#                 pid = product.get("id")
#                 stock = product.get("stock")
#                 if pid and stock is not None:
#                     # INSERT OR IGNORE — never overwrite existing tracked rows.
#                     conn.execute(
#                         "INSERT OR IGNORE INTO inventory"
#                         " (product_id, name, available_qty, reserved_qty, sold_qty)"
#                         " VALUES (?, ?, ?, 0, 0)",
#                         (pid, product.get("name", pid), int(stock)),
#                     )
#                     # Record initial stock movement only if the row is new.
#                     if conn.execute(
#                         "SELECT changes()"
#                     ).fetchone()[0]:
#                         conn.execute(
#                             "INSERT INTO inventory_movements"
#                             " (product_id, movement_type, quantity, note)"
#                             " VALUES (?, 'INITIAL', ?, 'Seeded from demo catalog')",
#                             (pid, int(stock)),
#                         )
#             conn.commit()
#         except Exception:
#             conn.rollback()
#             raise
#         finally:
#             conn.close()


# # ---------------------------------------------------------------------------
# # Read helpers
# # ---------------------------------------------------------------------------

# def get_all_inventory() -> list[dict[str, Any]]:
#     """Return current inventory status for every tracked product."""
#     with _LOCK:
#         conn = _connect()
#         try:
#             rows = conn.execute(
#                 "SELECT product_id, name, available_qty, reserved_qty, sold_qty, updated_at"
#                 " FROM inventory ORDER BY product_id"
#             ).fetchall()
#             return [dict(r) for r in rows]
#         finally:
#             conn.close()


# def get_product_inventory(product_id: str) -> dict[str, Any] | None:
#     """Return inventory for a single product, or None if not tracked."""
#     with _LOCK:
#         conn = _connect()
#         try:
#             row = conn.execute(
#                 "SELECT product_id, name, available_qty, reserved_qty, sold_qty, updated_at"
#                 " FROM inventory WHERE product_id = ?",
#                 (product_id,),
#             ).fetchone()
#             return dict(row) if row else None
#         finally:
#             conn.close()


# def get_movement_history(
#     product_id: str | None = None, limit: int = 50
# ) -> list[dict[str, Any]]:
#     """Return movement log, optionally filtered to one product."""
#     limit = max(1, min(int(limit), 200))
#     with _LOCK:
#         conn = _connect()
#         try:
#             if product_id:
#                 rows = conn.execute(
#                     "SELECT id, product_id, movement_type, quantity, order_id, note, created_at"
#                     " FROM inventory_movements WHERE product_id = ?"
#                     " ORDER BY id DESC LIMIT ?",
#                     (product_id, limit),
#                 ).fetchall()
#             else:
#                 rows = conn.execute(
#                     "SELECT id, product_id, movement_type, quantity, order_id, note, created_at"
#                     " FROM inventory_movements ORDER BY id DESC LIMIT ?",
#                     (limit,),
#                 ).fetchall()
#             return [dict(r) for r in rows]
#         finally:
#             conn.close()


# def get_reservations(order_id: str | None = None) -> list[dict[str, Any]]:
#     """Return active reservations, optionally filtered by order."""
#     with _LOCK:
#         conn = _connect()
#         try:
#             if order_id:
#                 rows = conn.execute(
#                     "SELECT * FROM inventory_reservations WHERE order_id = ?",
#                     (order_id,),
#                 ).fetchall()
#             else:
#                 rows = conn.execute(
#                     "SELECT * FROM inventory_reservations"
#                     " WHERE status = 'PENDING' ORDER BY created_at DESC"
#                 ).fetchall()
#             return [dict(r) for r in rows]
#         finally:
#             conn.close()


# # ---------------------------------------------------------------------------
# # Stock operations
# # ---------------------------------------------------------------------------

# def reserve_stock(order_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
#     """Reserve stock for a list of items tied to an order.

#     items: list of {"product_id": str, "quantity": int}

#     Returns the list of created reservation records.
#     Raises ValueError if any product has insufficient available stock.
#     Only demo-catalog products (tracked in inventory table) are reserved;
#     Channel3 availability-only products are skipped silently.
#     """
#     now = datetime.now(timezone.utc)
#     expires_at = (now + timedelta(minutes=RESERVATION_TTL_MINUTES)).isoformat()
#     now_iso = now.isoformat()

#     with _LOCK:
#         conn = _connect()
#         try:
#             conn.execute("BEGIN IMMEDIATE")

#             # Expire stale reservations first (best-effort, inside same transaction).
#             _expire_stale_reservations_conn(conn, now_iso)

#             reservations: list[dict[str, Any]] = []
#             for item in items:
#                 pid = item["product_id"]
#                 qty = item["quantity"]

#                 row = conn.execute(
#                     "SELECT available_qty FROM inventory WHERE product_id = ?",
#                     (pid,),
#                 ).fetchone()
#                 if row is None:
#                     # Channel3 / untracked product — skip reservation
#                     continue

#                 available = row["available_qty"]
#                 if qty > available:
#                     conn.rollback()
#                     raise ValueError(
#                         f"Insufficient stock for product {pid}: "
#                         f"requested {qty}, available {available}."
#                     )

#                 # Deduct from available, add to reserved.
#                 conn.execute(
#                     "UPDATE inventory"
#                     " SET available_qty = available_qty - ?,"
#                     "     reserved_qty  = reserved_qty  + ?,"
#                     "     updated_at = ?"
#                     " WHERE product_id = ?",
#                     (qty, qty, now_iso, pid),
#                 )

#                 rid = str(uuid.uuid4())
#                 conn.execute(
#                     "INSERT INTO inventory_reservations"
#                     " (reservation_id, order_id, product_id, quantity, status, expires_at, created_at, updated_at)"
#                     " VALUES (?, ?, ?, ?, 'PENDING', ?, ?, ?)",
#                     (rid, order_id, pid, qty, expires_at, now_iso, now_iso),
#                 )
#                 conn.execute(
#                     "INSERT INTO inventory_movements"
#                     " (product_id, movement_type, quantity, order_id, note)"
#                     " VALUES (?, 'RESERVE', ?, ?, 'Reserved for order')",
#                     (pid, qty, order_id),
#                 )
#                 reservations.append({
#                     "reservation_id": rid,
#                     "order_id": order_id,
#                     "product_id": pid,
#                     "quantity": qty,
#                     "status": "PENDING",
#                     "expires_at": expires_at,
#                 })

#             conn.commit()
#             return reservations
#         except ValueError:
#             raise
#         except Exception:
#             conn.rollback()
#             raise
#         finally:
#             conn.close()


# def confirm_stock(order_id: str) -> int:
#     """Convert PENDING reservations for an order into sold stock.

#     Called after PayPal confirms COMPLETED capture.
#     Returns number of reservation rows confirmed.
#     """
#     now_iso = datetime.now(timezone.utc).isoformat()

#     with _LOCK:
#         conn = _connect()
#         try:
#             conn.execute("BEGIN IMMEDIATE")
#             rows = conn.execute(
#                 "SELECT reservation_id, product_id, quantity"
#                 " FROM inventory_reservations"
#                 " WHERE order_id = ? AND status = 'PENDING'",
#                 (order_id,),
#             ).fetchall()

#             confirmed = 0
#             for row in rows:
#                 pid, qty = row["product_id"], row["quantity"]
#                 conn.execute(
#                     "UPDATE inventory"
#                     " SET reserved_qty = reserved_qty - ?,"
#                     "     sold_qty     = sold_qty     + ?,"
#                     "     updated_at = ?"
#                     " WHERE product_id = ?",
#                     (qty, qty, now_iso, pid),
#                 )
#                 conn.execute(
#                     "UPDATE inventory_reservations"
#                     " SET status = 'CONFIRMED', updated_at = ?"
#                     " WHERE reservation_id = ?",
#                     (now_iso, row["reservation_id"]),
#                 )
#                 conn.execute(
#                     "INSERT INTO inventory_movements"
#                     " (product_id, movement_type, quantity, order_id, note)"
#                     " VALUES (?, 'CONFIRM', ?, ?, 'Stock deducted after payment confirmed')",
#                     (pid, qty, order_id),
#                 )
#                 confirmed += 1

#             conn.commit()
#             return confirmed
#         except Exception:
#             conn.rollback()
#             raise
#         finally:
#             conn.close()


# def release_reservation(order_id: str, reason: str = "Manual release") -> int:
#     """Release PENDING reservations for an order back to available stock.

#     Returns number of rows released.
#     """
#     now_iso = datetime.now(timezone.utc).isoformat()

#     with _LOCK:
#         conn = _connect()
#         try:
#             conn.execute("BEGIN IMMEDIATE")
#             rows = conn.execute(
#                 "SELECT reservation_id, product_id, quantity"
#                 " FROM inventory_reservations"
#                 " WHERE order_id = ? AND status = 'PENDING'",
#                 (order_id,),
#             ).fetchall()

#             released = 0
#             for row in rows:
#                 pid, qty = row["product_id"], row["quantity"]
#                 conn.execute(
#                     "UPDATE inventory"
#                     " SET available_qty = available_qty + ?,"
#                     "     reserved_qty  = MAX(0, reserved_qty - ?),"
#                     "     updated_at = ?"
#                     " WHERE product_id = ?",
#                     (qty, qty, now_iso, pid),
#                 )
#                 conn.execute(
#                     "UPDATE inventory_reservations"
#                     " SET status = 'RELEASED', updated_at = ?"
#                     " WHERE reservation_id = ?",
#                     (now_iso, row["reservation_id"]),
#                 )
#                 conn.execute(
#                     "INSERT INTO inventory_movements"
#                     " (product_id, movement_type, quantity, order_id, note)"
#                     " VALUES (?, 'RELEASE', ?, ?, ?)",
#                     (pid, qty, order_id, reason),
#                 )
#                 released += 1

#             conn.commit()
#             return released
#         except Exception:
#             conn.rollback()
#             raise
#         finally:
#             conn.close()


# def expire_old_reservations() -> int:
#     """Sweep expired PENDING reservations and release their stock.

#     Should be called periodically (e.g. on each /api/cart/validate request).
#     Returns number of reservations expired.
#     """
#     now_iso = datetime.now(timezone.utc).isoformat()

#     with _LOCK:
#         conn = _connect()
#         try:
#             conn.execute("BEGIN IMMEDIATE")
#             expired = _expire_stale_reservations_conn(conn, now_iso)
#             conn.commit()
#             return expired
#         except Exception:
#             conn.rollback()
#             raise
#         finally:
#             conn.close()


# def _expire_stale_reservations_conn(conn: sqlite3.Connection, now_iso: str) -> int:
#     """Internal: expire stale reservations using an already-open connection."""
#     rows = conn.execute(
#         "SELECT reservation_id, order_id, product_id, quantity"
#         " FROM inventory_reservations"
#         " WHERE status = 'PENDING' AND expires_at < ?",
#         (now_iso,),
#     ).fetchall()

#     for row in rows:
#         pid, qty, oid = row["product_id"], row["quantity"], row["order_id"]
#         conn.execute(
#             "UPDATE inventory"
#             " SET available_qty = available_qty + ?,"
#             "     reserved_qty  = MAX(0, reserved_qty - ?),"
#             "     updated_at = ?"
#             " WHERE product_id = ?",
#             (qty, qty, now_iso, pid),
#         )
#         conn.execute(
#             "UPDATE inventory_reservations"
#             " SET status = 'EXPIRED', updated_at = ?"
#             " WHERE reservation_id = ?",
#             (now_iso, row["reservation_id"]),
#         )
#         conn.execute(
#             "INSERT INTO inventory_movements"
#             " (product_id, movement_type, quantity, order_id, note)"
#             " VALUES (?, 'RELEASE', ?, ?, 'Reservation expired after 15 minutes')",
#             (pid, qty, oid),
#         )

#     return len(rows)


# def adjust_stock(
#     product_id: str, delta: int, note: str = "Admin adjustment"
# ) -> dict[str, Any]:
#     """Add or subtract available stock (admin only).

#     delta > 0 → add stock, delta < 0 → remove stock.
#     Raises ValueError if adjustment would make available_qty negative.
#     """
#     now_iso = datetime.now(timezone.utc).isoformat()

#     with _LOCK:
#         conn = _connect()
#         try:
#             conn.execute("BEGIN IMMEDIATE")
#             row = conn.execute(
#                 "SELECT available_qty FROM inventory WHERE product_id = ?",
#                 (product_id,),
#             ).fetchone()
#             if row is None:
#                 raise ValueError(f"Product {product_id} is not tracked in inventory.")
#             new_qty = row["available_qty"] + delta
#             if new_qty < 0:
#                 raise ValueError(
#                     f"Adjustment would make available stock negative "
#                     f"({row['available_qty']} + {delta} = {new_qty})."
#                 )
#             conn.execute(
#                 "UPDATE inventory SET available_qty = ?, updated_at = ?"
#                 " WHERE product_id = ?",
#                 (new_qty, now_iso, product_id),
#             )
#             movement_type = "ADJUST_IN" if delta >= 0 else "ADJUST_OUT"
#             conn.execute(
#                 "INSERT INTO inventory_movements"
#                 " (product_id, movement_type, quantity, note)"
#                 " VALUES (?, ?, ?, ?)",
#                 (product_id, movement_type, abs(delta), note),
#             )
#             conn.commit()
#             return get_product_inventory(product_id)  # type: ignore[return-value]
#         except ValueError:
#             conn.rollback()
#             raise
#         except Exception:
#             conn.rollback()
#             raise
#         finally:
#             conn.close()

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
