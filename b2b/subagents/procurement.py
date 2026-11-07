"""Procurement subagent: turns a delegated objective into stock-checked items.

Uses Channel3 (via Channel3Provider) for live product discovery and stock, with
the local wholesale catalog as fallback. Enforces the per-item spending cap.
"""
from __future__ import annotations

from ..channel3 import Channel3Provider
from ._shared import audit, money

AGENT = "procurement"


def _objective(state: dict) -> str:
    requested = state.get("requested_items") or []
    if not requested:
        return state.get("objective", "")
    segments = []
    for item in requested:
        if isinstance(item, dict):
            name = item.get("name") or item.get("query") or ""
            qty = int(item.get("qty") or 1)
            segments.append(f"{name} x {qty}")
        else:
            segments.append(str(item))
    return ", ".join(segments)


def run(state: dict) -> dict:
    cap = float(state["per_item_cap"])
    provider = Channel3Provider(currency=state.get("currency"))
    items = provider.resolve(_objective(state), max_price=cap,
                             customer_id=state.get("customer_id", "CUST_DEMO"))

    if not items:
        return {
            "status": "rechazado",
            "message": "No se encontraron productos para el objetivo delegado",
            "trace": audit(state, AGENT, "Sin coincidencias en Channel3/catálogo local"),
        }

    valid = []
    dropped = []
    for item in items:
        if item["unit_price"] > cap:
            dropped.append(f"{item['name']} (${item['unit_price']:.2f} > tope ${cap:.2f})")
            continue
        if item["stock"] <= 0:
            dropped.append(f"{item['name']} (sin stock)")
            continue
        if item["qty"] > item["stock"]:
            item = {**item, "qty": item["stock"]}
        valid.append(item)

    if not valid:
        return {
            "status": "rechazado",
            "message": "Ningún producto cumple el tope por ítem o el stock disponible: "
                       + "; ".join(dropped),
            "trace": audit(state, AGENT, "Todos los ítems fueron rechazados", {"dropped": dropped}),
        }

    goods_total = money(sum(i["unit_price"] * i["qty"] for i in valid))
    live = any(i["source"] == "channel3" for i in valid)
    summary = (f"{len(valid)} línea(s), {sum(i['qty'] for i in valid)} unidades, "
               f"${goods_total:,.2f} vía {'Channel3' if live else 'catálogo local'}")
    return {
        "items": valid,
        "goods_total": goods_total,
        "status": "abastecimiento_ok",
        "trace": audit(state, AGENT, summary, {
            "items": [{"name": i["name"], "qty": i["qty"], "supplier": i["supplier"],
                       "source": i["source"], "stock": i["stock"]} for i in valid],
            "dropped": dropped,
        }),
    }
