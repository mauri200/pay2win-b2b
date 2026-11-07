"""Logistics subagent: shipping mode, consolidated cost and ETA."""
from __future__ import annotations

from ._shared import audit, money

AGENT = "logistics"


def _quote(weight_kg: float) -> dict:
    if weight_kg <= 0:
        return {"carrier": "N/A", "mode": "none", "cost": 0.0, "eta_days": 0}
    if weight_kg < 5:
        return {"carrier": "UPS Express", "mode": "courier", "cost": 25.0, "eta_days": 3}
    if weight_kg < 50:
        return {"carrier": "DHL Air Freight", "mode": "air", "cost": max(60.0, 8.0 * weight_kg), "eta_days": 6}
    return {"carrier": "Maersk Ocean", "mode": "ocean", "cost": max(150.0, 2.5 * weight_kg), "eta_days": 24}


def run(state: dict) -> dict:
    items = state.get("items", [])
    weight = round(sum(float(i.get("weight_kg", 0)) * int(i.get("qty", 1)) for i in items), 2)
    suppliers = {i.get("supplier") for i in items if i.get("supplier")}
    quote = _quote(weight)

    discount = 0.08 if len(suppliers) > 1 else 0.0
    shipping = money(quote["cost"] * (1 - discount))

    summary = (f"{quote['carrier']} · {weight} kg · ${shipping:,.2f} · "
               f"ETA {quote['eta_days']} días" + (" · consolidado" if discount else ""))
    return {
        "shipping_total": shipping,
        "logistics": {
            **quote,
            "cost": shipping,
            "gross_cost": money(quote["cost"]),
            "total_weight_kg": weight,
            "consolidation_discount": discount,
            "consolidated": bool(discount),
            "incoterm": "DDP",
        },
        "trace": audit(state, AGENT, summary),
    }
