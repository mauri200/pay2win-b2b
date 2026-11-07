"""Customs subagent: HS classification, duties, import taxes and permits."""
from __future__ import annotations

from .. import config
from ._shared import audit, money

AGENT = "customs"


def run(state: dict) -> dict:
    lines, permits = [], []
    duties_total = tax_total = 0.0

    for item in state.get("items", []):
        goods = item["unit_price"] * item["qty"]
        imported = item.get("origin", "US") != "US"
        duty = goods * float(item.get("duty_rate", 0.0)) if imported else 0.0
        tax = (goods + duty) * config.VAT_RATE if imported else 0.0

        duties_total += duty
        tax_total += tax
        if item.get("restricted"):
            permits.append(f"Permiso especial: {item['name']} (HS {item['hs_code']})")

        lines.append({
            "name": item["name"],
            "hs_code": item["hs_code"],
            "origin": item.get("origin", ""),
            "goods": money(goods),
            "duty": money(duty),
            "tax": money(tax),
            "duty_rate": item.get("duty_rate", 0.0),
        })

    brokerage = config.BROKERAGE_FEE if lines else 0.0
    summary = (f"Clasificadas {len(lines)} líneas · aranceles ${duties_total:,.2f} · "
               f"impuestos ${tax_total:,.2f} · corretaje ${brokerage:,.2f}")
    return {
        "duties_total": money(duties_total),
        "tax_total": money(tax_total),
        "brokerage_total": money(brokerage),
        "customs": {
            "lines": lines,
            "permits": permits,
            "incoterm": "DDP",
            "brokerage": money(brokerage),
        },
        "trace": audit(state, AGENT, summary, {"permits": permits}),
    }
