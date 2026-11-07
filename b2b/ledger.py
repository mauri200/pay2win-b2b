"""In-memory payment ledger + audit trail for the B2B dashboard (demo only)."""
from __future__ import annotations

import threading
import time

_LOCK = threading.Lock()
ORDERS: dict[str, dict] = {}
PAYMENT_EVENTS: list[dict] = []


def _money(value) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def upsert(tid: str, state: dict, interrupt_info: dict | None = None) -> dict:
    """Create/update one dashboard row from the current graph state."""
    with _LOCK:
        row = ORDERS.setdefault(tid, {
            "thread_id": tid,
            "created": time.strftime("%H:%M:%S"),
            "created_ts": time.time(),
        })
        row.update({
            "customer_id": state.get("customer_id"),
            "objective": state.get("objective"),
            "currency": state.get("currency", "USD"),
            "budget": _money(state.get("budget")),
            "per_item_cap": _money(state.get("per_item_cap")),
            "items_count": sum(int(i.get("qty", 1)) for i in state.get("items", []) or []),
            "suppliers": ", ".join(sorted({i.get("supplier", "") for i in state.get("items", []) or []
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
            "payment_mode": (state.get("treasury") or {}).get("payment_mode"),
            "items": state.get("items", []),
            "customs": state.get("customs", {}),
            "logistics": state.get("logistics", {}),
            "compliance": state.get("compliance", {}),
            "treasury": state.get("treasury", {}),
            "payments": state.get("payments", []),
            "trace": state.get("trace", []),
        })
        if interrupt_info:
            row["status"] = "esperando_aprobacion"
            row["order_id"] = interrupt_info.get("order_id") or row.get("order_id")
            row["approve_url"] = interrupt_info.get("approve_url") or row.get("approve_url")
            row["grand_total"] = _money(interrupt_info.get("monto", row.get("grand_total")))
        return row


def get(tid: str) -> dict | None:
    with _LOCK:
        row = ORDERS.get(tid)
        return dict(row) if row else None


def all_orders() -> list:
    with _LOCK:
        return [dict(r) for r in reversed(list(ORDERS.values()))]


def record_payment_event(event_type: str, event_id: str | None, order_id: str | None,
                         verified: bool, detail: str, amount: float | None) -> list:
    """Store one PayPal webhook event and attach it to matching orders."""
    entry = {
        "ts": time.strftime("%H:%M:%S"),
        "event_type": event_type,
        "event_id": event_id,
        "order_id": order_id,
        "verified": verified,
        "detail": detail,
        "amount": _money(amount),
    }
    with _LOCK:
        PAYMENT_EVENTS.append(entry)
        del PAYMENT_EVENTS[:-200]
        matched = []
        for row in ORDERS.values():
            if order_id and row.get("order_id") == order_id:
                events = row.setdefault("paypal_events", [])
                events.append(entry)
                del events[:-20]
                row["last_paypal_event"] = entry
                matched.append(row["thread_id"])
        return matched


def payment_events() -> list:
    with _LOCK:
        return [dict(e) for e in reversed(PAYMENT_EVENTS)]
