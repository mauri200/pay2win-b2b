"""Treasury subagent: budget allocation, fee guardrails and payment schedule."""
from __future__ import annotations

from .. import config
from ._shared import audit, money

AGENT = "treasury"


def _schedule(total: float, financing: str) -> list:
    if financing == "pay_in_4":
        n = 4
        labels = [f"Cuota {i}/4" for i in range(1, n + 1)]
    else:
        n = 2
        labels = ["Anticipo 30%", "Saldo 70%"]
        weights = [0.30, 0.70]
        amounts = [money(total * w) for w in weights]
        amounts[-1] = money(total - sum(amounts[:-1]))
        return [{"label": l, "amount": a} for l, a in zip(labels, amounts)]

    part = money(total / n)
    amounts = [part] * (n - 1)
    amounts.append(money(total - sum(amounts)))
    return [{"label": l, "amount": a} for l, a in zip(labels, amounts)]


def run(state: dict) -> dict:
    goods = money(state.get("goods_total"))
    duties = money(state.get("duties_total"))
    tax = money(state.get("tax_total"))
    shipping = money(state.get("shipping_total"))
    brokerage = money(state.get("brokerage_total"))
    payment_fee = money(goods * config.PAYMENT_FEE_RATE)
    fees_total = money(brokerage + payment_fee)

    grand = money(goods + duties + tax + shipping + fees_total)
    budget = money(state.get("budget"))
    remaining = money(budget - grand)

    if grand > budget:
        return {
            "grand_total": grand,
            "fees_total": fees_total,
            "remaining": remaining,
            "status": "rechazado",
            "message": (f"El costo total ${grand:,.2f} excede el monto delegado "
                        f"(${budget:,.2f}). Guardrail de tesorería activado."),
            "treasury": {"grand_total": grand, "payment_fee": payment_fee,
                         "fees_total": fees_total, "remaining": remaining,
                         "schedule": [], "payment_mode": "blocked"},
            "trace": audit(state, AGENT, "Presupuesto insuficiente; no se crea pago",
                           {"grand_total": grand, "budget": budget}),
        }

    schedule = _schedule(grand, state.get("financing", "none"))
    mode = "simulated" if config.SIMULATE_PAYMENTS else "paypal_sandbox"
    summary = (f"${grand:,.2f} autorizado dentro de ${budget:,.2f} · "
               f"saldo ${remaining:,.2f} · {len(schedule)} pago(s)")
    return {
        "grand_total": grand,
        "fees_total": fees_total,
        "remaining": remaining,
        "status": "tesoreria_ok",
        "treasury": {
            "goods": goods,
            "duties": duties,
            "tax": tax,
            "shipping": shipping,
            "brokerage": brokerage,
            "payment_fee": payment_fee,
            "fees_total": fees_total,
            "grand_total": grand,
            "budget": budget,
            "remaining": remaining,
            "schedule": schedule,
            "payment_mode": mode,
        },
        "trace": audit(state, AGENT, summary, {"schedule": schedule}),
    }
