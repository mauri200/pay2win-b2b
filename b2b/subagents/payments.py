"""Payments subagent: creates the PayPal order, waits for approval, captures.

Reuses the existing PayPal agent toolkit used by the consumer flow when
credentials are configured. If they are missing, it simulates the order so the
B2B team can run end-to-end in demo mode.
"""
from __future__ import annotations

import re
import uuid

from .. import config
from ._shared import audit, money

AGENT = "payments"


def _simulated() -> tuple[str, str]:
    # 17-char sandbox-looking order id + approval URL.
    oid = "SBX" + uuid.uuid4().hex[:14].upper()
    return oid, f"https://www.sandbox.paypal.com/checkoutnow?token={oid}"


def _create_real(state: dict) -> tuple[str | None, str | None, str]:
    try:
        from app.graph import _run_agent  # lazy: avoids loading toolkit unless needed
    except Exception as exc:  # pragma: no cover - depends on local install
        return None, None, f"No se pudo cargar el PayPal toolkit ({exc})"

    items = "; ".join(f"{i['qty']} x '{i['name']}' at {i['unit_price']:.2f}"
                      for i in state.get("items", []))
    prompt = (
        f"Create a PayPal order in {state.get('currency', 'USD')} for a B2B purchase with "
        f"these line items: {items}. The order total must be exactly "
        f"{state.get('grand_total', 0):.2f}. Use return_url https://example.com/return and "
        "cancel_url https://example.com/cancel. Reply with the order id and the payer approval link."
    )
    try:
        out = _run_agent(prompt)
    except Exception as exc:
        return None, None, f"Fallo al crear la orden real ({exc})"

    link = re.search(r"https://www\.(?:sandbox\.)?paypal\.com/[^\s\"')>]+", out)
    oid = re.search(r"\b[0-9A-Z]{17}\b", out)
    if not link or not oid:
        return None, None, "La orden real no devolvió id/link; se usa simulación"
    return oid.group(0), link.group(0), ""


def run(state: dict) -> dict:
    amount = money(state.get("grand_total"))
    mode = "simulated"
    oid = link = None
    note = ""

    if not config.SIMULATE_PAYMENTS:
        oid, link, note = _create_real(state)
        if oid and link:
            mode = "paypal_sandbox"

    if not oid:
        oid, link = _simulated()
        mode = "simulated"

    record = {
        "order_id": oid,
        "approve_url": link,
        "amount": amount,
        "currency": state.get("currency", "USD"),
        "mode": mode,
        "created": __import__("time").strftime("%H:%M:%S"),
    }
    payments = list(state.get("payments") or []) + [record]
    treasury = {**(state.get("treasury") or {}), "payment_mode": mode}

    summary = f"Orden {oid} por ${amount:,.2f} ({'simulada' if mode == 'simulated' else 'PayPal sandbox'})"
    if note:
        summary += f" · {note}"
    return {
        "order_id": oid,
        "approve_url": link,
        "payments": payments,
        "treasury": treasury,
        "status": "esperando_aprobacion",
        "trace": audit(state, AGENT, summary, {"order_id": oid, "mode": mode}),
    }


def capture(state: dict) -> dict:
    """Capture after the human approves. Called by the team graph."""
    oid = state.get("order_id")
    mode = (state.get("treasury") or {}).get("payment_mode", "simulated")

    if mode != "paypal_sandbox":
        summary = f"Pago simulado capturado · {oid}"
        payments = list(state.get("payments") or [])
        if payments:
            payments[-1] = {**payments[-1], "captured": True}
        return {
            "status": "completado",
            "message": f"Pago aprobado y capturado · ${state.get('grand_total', 0):,.2f} (simulado)",
            "payments": payments,
            "trace": audit(state, AGENT, summary, {"order_id": oid, "mode": mode}),
        }

    from .. import paypal_client

    estado = paypal_client.order_status(oid)
    if estado == "COMPLETED":
        ok = True
    elif estado == "APPROVED":
        ok, detail, _ = paypal_client.capture_order(oid)
        if not ok:
            return {
                "status": "error_captura",
                "message": f"La orden {oid} no se pudo capturar: {detail}",
                "trace": audit(state, AGENT, f"Error de captura: {detail}"),
            }
        estado = paypal_client.order_status(oid)
        ok = estado == "COMPLETED"
    else:
        return {
            "status": "error_captura",
            "message": (f"PayPal todavía reporta la orden {oid} como {estado}. "
                        "Ábrela, apruébala como comprador sandbox y vuelve a intentar."),
            "trace": audit(state, AGENT, f"Captura bloqueada: orden en estado {estado}"),
        }

    payments = list(state.get("payments") or [])
    if payments:
        payments[-1] = {**payments[-1], "captured": ok, "paypal_status": estado}
    return {
        "status": "completado" if ok else "error_captura",
        "message": ("Pago completado y verificado por PayPal" if ok
                    else f"La orden quedó en estado {estado}; no se cobró"),
        "payments": payments,
        "trace": audit(state, AGENT, f"Captura {oid} → {estado}"),
    }
