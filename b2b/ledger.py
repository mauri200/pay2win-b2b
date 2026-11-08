"""Persistent payment ledger + audit trail for the B2B dashboard."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone

from . import db

_JSON_COLUMNS = {
    "items",
    "customs",
    "logistics",
    "compliance",
    "treasury",
    "payments",
    "trace",
    "state_json",
}

_DB_COLUMNS = [
    "thread_id",
    "created_at",
    "created_ts",
    "updated_at",
    "customer_id",
    "objective",
    "budget",
    "per_item_cap",
    "currency",
    "financing",
    "status",
    "grand_total",
    "remaining",
    "order_id",
    "approve_url",
    "payment_mode",
    "items",
    "customs",
    "logistics",
    "compliance",
    "treasury",
    "payments",
    "trace",
    "message",
    "items_count",
    "suppliers",
    "goods_total",
    "duties_total",
    "tax_total",
    "shipping_total",
    "fees_total",
    "state_json",
]


def _money(value) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _dump(value):
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _load(value, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _hhmmss(value) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone().strftime("%H:%M:%S")
    except ValueError:
        return str(value)[:8]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(cur, raw) -> dict:
    if isinstance(raw, sqlite3.Row):
        return dict(raw)
    names = [column[0] for column in cur.description]
    return dict(zip(names, raw))


def _row_from_db(cur, raw) -> dict:
    data = _as_dict(cur, raw)
    return {
        "thread_id": data.get("thread_id"),
        "created": _hhmmss(data.get("created_at")),
        "created_ts": data.get("created_ts"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "customer_id": data.get("customer_id"),
        "objective": data.get("objective"),
        "currency": data.get("currency") or "USD",
        "budget": _money(data.get("budget")),
        "per_item_cap": _money(data.get("per_item_cap")),
        "items_count": int(data.get("items_count") or 0),
        "suppliers": data.get("suppliers") or "",
        "goods_total": _money(data.get("goods_total")),
        "duties_total": _money(data.get("duties_total")),
        "tax_total": _money(data.get("tax_total")),
        "shipping_total": _money(data.get("shipping_total")),
        "fees_total": _money(data.get("fees_total")),
        "grand_total": _money(data.get("grand_total")),
        "remaining": _money(data.get("remaining")),
        "financing": data.get("financing"),
        "status": data.get("status"),
        "message": data.get("message"),
        "order_id": data.get("order_id"),
        "approve_url": data.get("approve_url"),
        "payment_mode": data.get("payment_mode"),
        "items": _load(data.get("items"), []),
        "customs": _load(data.get("customs"), {}),
        "logistics": _load(data.get("logistics"), {}),
        "compliance": _load(data.get("compliance"), {}),
        "treasury": _load(data.get("treasury"), {}),
        "payments": _load(data.get("payments"), []),
        "trace": _load(data.get("trace"), []),
    }


def _event_from_db(cur, raw) -> dict:
    data = _as_dict(cur, raw)
    return {
        "ts": _hhmmss(data.get("received_at")),
        "event_type": data.get("event_type"),
        "event_id": data.get("event_id"),
        "order_id": data.get("order_id"),
        "verified": bool(data.get("verified")),
        "detail": data.get("detail"),
        "amount": _money(data.get("amount")),
    }


def _attach_events(cur, row: dict) -> dict:
    order_id = row.get("order_id")
    if not order_id:
        return row
    p = db.placeholder()
    cur.execute(
        f"SELECT * FROM paypal_events WHERE order_id = {p} "
        "ORDER BY received_at DESC, id DESC LIMIT 20",
        (order_id,),
    )
    events = [_event_from_db(cur, raw) for raw in cur.fetchall()]
    if events:
        row["paypal_events"] = list(reversed(events))
        row["last_paypal_event"] = events[0]
    return row


def _build_row(tid: str, state: dict, interrupt_info: dict | None) -> dict:
    items = state.get("items", []) or []
    treasury = state.get("treasury") or {}
    row = {
        "thread_id": tid,
        "customer_id": state.get("customer_id"),
        "objective": state.get("objective"),
        "currency": state.get("currency", "USD"),
        "budget": _money(state.get("budget")),
        "per_item_cap": _money(state.get("per_item_cap")),
        "items_count": sum(int(i.get("qty", 1)) for i in items),
        "suppliers": ", ".join(sorted({i.get("supplier", "") for i in items
                                       if i.get("supplier")})),
        "goods_total": _money(state.get("goods_total")),
        "duties_total": _money(state.get("duties_total")),
        "tax_total": _money(state.get("tax_total")),
        "shipping_total": _money(state.get("shipping_total")),
        "fees_total": _money(state.get("fees_total")),
        "grand_total": _money(state.get("grand_total")),
        "remaining": _money(state.get("remaining")),
        "financing": state.get("financing"),
        "status": state.get("status"),
        "message": state.get("message"),
        "order_id": state.get("order_id"),
        "approve_url": state.get("approve_url"),
        "payment_mode": treasury.get("payment_mode"),
        "items": items,
        "customs": state.get("customs", {}),
        "logistics": state.get("logistics", {}),
        "compliance": state.get("compliance", {}),
        "treasury": treasury,
        "payments": state.get("payments", []),
        "trace": state.get("trace", []),
    }
    if interrupt_info:
        row["status"] = "esperando_aprobacion"
        row["order_id"] = interrupt_info.get("order_id") or row.get("order_id")
        row["approve_url"] = interrupt_info.get("approve_url") or row.get("approve_url")
        row["grand_total"] = _money(interrupt_info.get("monto", row.get("grand_total")))
    return row


def upsert(tid: str, state: dict, interrupt_info: dict | None = None) -> dict:
    """Create/update one dashboard row from the current graph state."""
    db.init_db()
    state = state or {}
    now = _now_iso()
    row = _build_row(tid, state, interrupt_info)

    with db.connection() as conn:
        cur = conn.cursor()
        p = db.placeholder()
        cur.execute(
            f"SELECT created_at, created_ts FROM delegations WHERE thread_id = {p}",
            (tid,),
        )
        existing = cur.fetchone()
        if existing:
            created_at, created_ts = existing[0], existing[1]
        else:
            created_at, created_ts = now, time.time()

        row["created_at"] = created_at
        row["created_ts"] = created_ts
        row["updated_at"] = now
        values = {**row, "state_json": state}

        params = []
        for column in _DB_COLUMNS:
            value = values.get(column)
            if column in _JSON_COLUMNS:
                value = _dump(value)
            params.append(value)

        placeholders = ", ".join([p] * len(_DB_COLUMNS))
        updates = ", ".join(f"{column} = excluded.{column}"
                            for column in _DB_COLUMNS if column != "thread_id")
        cur.execute(
            f"INSERT INTO delegations ({', '.join(_DB_COLUMNS)}) "
            f"VALUES ({placeholders}) ON CONFLICT (thread_id) DO UPDATE SET {updates}",
            params,
        )
        _attach_events(cur, row)

    row["created"] = _hhmmss(created_at)
    return row


def get(tid: str) -> dict | None:
    db.init_db()
    with db.connection() as conn:
        cur = conn.cursor()
        p = db.placeholder()
        cur.execute(f"SELECT * FROM delegations WHERE thread_id = {p}", (tid,))
        raw = cur.fetchone()
        if not raw:
            return None
        row = _row_from_db(cur, raw)
        return _attach_events(cur, row)


def all_orders() -> list:
    db.init_db()
    with db.connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM delegations ORDER BY created_ts DESC")
        rows = [_row_from_db(cur, raw) for raw in cur.fetchall()]

        order_ids = sorted({row["order_id"] for row in rows if row.get("order_id")})
        if order_ids:
            p = db.placeholder()
            placeholders = ", ".join([p] * len(order_ids))
            cur.execute(
                f"SELECT * FROM paypal_events WHERE order_id IN ({placeholders}) "
                "ORDER BY received_at DESC, id DESC",
                order_ids,
            )
            events_by_order: dict[str, list] = {}
            for raw in cur.fetchall():
                event = _event_from_db(cur, raw)
                events_by_order.setdefault(event.get("order_id"), []).append(event)

            for row in rows:
                events = events_by_order.get(row.get("order_id"))
                if events:
                    row["paypal_events"] = list(reversed(events[:20]))
                    row["last_paypal_event"] = events[0]
        return rows


def record_payment_event(event_type: str, event_id: str | None, order_id: str | None,
                         verified: bool, detail: str, amount: float | None,
                         payload: dict | None = None) -> list:
    """Store one PayPal webhook event and return the matching thread ids."""
    db.init_db()
    received_at = _now_iso()
    values = (
        event_id,
        event_type,
        order_id,
        bool(verified),
        detail,
        _money(amount),
        _dump(payload),
        received_at,
    )
    with db.connection() as conn:
        cur = conn.cursor()
        p = db.placeholder()
        columns = ("event_id, event_type, order_id, verified, detail, amount, "
                   "payload, received_at")
        placeholders = ", ".join([p] * 8)
        conflict = " ON CONFLICT (event_id) DO NOTHING" if event_id else ""
        cur.execute(
            f"INSERT INTO paypal_events ({columns}) VALUES ({placeholders}){conflict}",
            values,
        )

        matched = []
        if order_id:
            cur.execute(
                f"SELECT thread_id FROM delegations WHERE order_id = {p}",
                (order_id,),
            )
            matched = [raw[0] for raw in cur.fetchall()]
        return matched


def payment_events() -> list:
    db.init_db()
    with db.connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM paypal_events ORDER BY received_at DESC, id DESC LIMIT 200"
        )
        return [_event_from_db(cur, raw) for raw in cur.fetchall()]


def init_db() -> None:
    db.init_db()
