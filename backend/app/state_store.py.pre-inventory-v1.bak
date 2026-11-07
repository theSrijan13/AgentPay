"""Small SQLite state store for prototype payment/refund lifecycle.

For a multi-instance production deployment, replace this with a managed database and
transactional locking. PayPal credentials and raw HTTP response bodies are never stored.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .config import settings

_LOCK = threading.RLock()
_DB_VALUE = settings.agentpay_db_path or "agentpay.db"
_DB_PATH = Path(_DB_VALUE).expanduser() if _DB_VALUE != ":memory:" else None
_MEMORY_URI = "file:agentpay_shared?mode=memory&cache=shared"
_MEMORY_ANCHOR: sqlite3.Connection | None = None
if _DB_PATH is not None and not _DB_PATH.is_absolute():
    _DB_PATH = Path(__file__).resolve().parents[1] / _DB_PATH


def _connect() -> sqlite3.Connection:
    global _MEMORY_ANCHOR
    if _DB_PATH is None:
        # Keep an anchor connection open so connections to the shared-memory database
        # survive between operations even though each operation closes its connection.
        if _MEMORY_ANCHOR is None:
            _MEMORY_ANCHOR = sqlite3.connect(_MEMORY_URI, uri=True, timeout=5, check_same_thread=False)
        conn = sqlite3.connect(_MEMORY_URI, uri=True, timeout=5, check_same_thread=False)
    else:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


with _LOCK:
    _conn = _connect()
    _conn.execute("CREATE TABLE IF NOT EXISTS payment_orders (order_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    _conn.execute("CREATE TABLE IF NOT EXISTS paypal_webhook_events (event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    _conn.execute("CREATE TABLE IF NOT EXISTS post_purchase_runs (order_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    _conn.commit()
    _conn.close()


_PERSISTED_ORDER_FIELDS = (
    "status", "items", "total", "currency", "capture_id", "capture_request_id",
    "refunds", "refunded_total", "refund_status", "updated_at",
)


def _stored_order(record: dict[str, Any]) -> dict[str, Any]:
    clean = {key: record[key] for key in _PERSISTED_ORDER_FIELDS if key in record}
    clean.setdefault("refunds", [])
    clean.setdefault("refunded_total", "0.00")
    # These are intentionally memory-only to avoid persisting full third-party
    # responses that may include more personal/transaction metadata than needed.
    clean["create_response"] = None
    clean["capture_response"] = None
    return clean


def load_payment_orders() -> dict[str, dict[str, Any]]:
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute("SELECT order_id, payload FROM payment_orders").fetchall()
            return {row["order_id"]: json.loads(row["payload"]) for row in rows}
        finally:
            conn.close()


def save_payment_order(order_id: str, record: dict[str, Any]) -> None:
    payload = json.dumps(_stored_order(record), separators=(",", ":"), ensure_ascii=False)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO payment_orders(order_id, payload, updated_at) VALUES(?,?,CURRENT_TIMESTAMP) "
                "ON CONFLICT(order_id) DO UPDATE SET payload=excluded.payload, updated_at=CURRENT_TIMESTAMP",
                (order_id, payload),
            )
            conn.commit()
        finally:
            conn.close()


def record_webhook_once(event_id: str, event_type: str) -> bool:
    """Return True only for the first verified delivery of a PayPal event ID."""
    if not event_id:
        return True
    with _LOCK:
        conn = _connect()
        try:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO paypal_webhook_events(event_id, event_type) VALUES(?,?)",
                (event_id, event_type[:120]),
            )
            conn.commit()
            return cursor.rowcount == 1
        finally:
            conn.close()


def save_automation_run(order_id: str, run: dict[str, Any]) -> None:
    payload = json.dumps(run, separators=(",", ":"), ensure_ascii=False)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO post_purchase_runs(order_id, payload, updated_at) VALUES(?,?,CURRENT_TIMESTAMP) "
                "ON CONFLICT(order_id) DO UPDATE SET payload=excluded.payload, updated_at=CURRENT_TIMESTAMP",
                (order_id, payload),
            )
            conn.commit()
        finally:
            conn.close()


def load_automation_runs(limit: int = 20) -> list[dict[str, Any]]:
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT payload FROM post_purchase_runs ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
            return [json.loads(row["payload"]) for row in rows]
        finally:
            conn.close()
