"""Supervisor + subagent team for delegated B2B procurement.

    QR mandate -> read -> SUPERVISOR -> procurement -> customs -> logistics
        -> compliance -> treasury -> payments -> [INTERRUPT approval] -> capture -> notify

The supervisor owns the plan and dispatches one specialised subagent at a time.
Each subagent only sees the shared state and the mandate guardrails (budget,
per-item cap, scope). Only after the human approves the PayPal order does the
team capture the payment.
"""
from __future__ import annotations

from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from .checkpointer import get_checkpointer
from .mandate import validate_mandate
from .subagents import REGISTRY
from .subagents import payments as payments_agent
from .subagents._shared import audit

PIPELINE = ["procurement", "customs", "logistics", "compliance", "treasury", "payments"]


class B2BState(TypedDict, total=False):
    mandate_token: str
    customer_id: str
    objective: str
    requested_items: list
    budget: float
    per_item_cap: float
    currency: str
    financing: str
    scope: list
    pending: list
    next: str
    items: list
    goods_total: float
    duties_total: float
    tax_total: float
    brokerage_total: float
    shipping_total: float
    fees_total: float
    grand_total: float
    remaining: float
    customs: dict
    logistics: dict
    compliance: dict
    treasury: dict
    payments: list
    order_id: Optional[str]
    approve_url: Optional[str]
    status: str
    message: str
    trace: list


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------
def n_read(s: B2BState) -> dict:
    try:
        d = validate_mandate(s["mandate_token"])
    except Exception as e:
        return {"status": "rechazado", "message": f"Mandato QR inválido: {e}",
                "trace": [{"agent": "supervisor", "summary": "Mandato inválido"}]}

    scope = [a for a in PIPELINE if a in d.get("scope", PIPELINE)]
    trace = audit({}, "supervisor", "Mandato validado y desplegado", {
        "budget": d["budget"], "per_item_cap": d["cap"], "scope": scope})
    return {
        "customer_id": d["cid"],
        "objective": d["obj"],
        "requested_items": d.get("items", []),
        "budget": d["budget"],
        "per_item_cap": d["cap"],
        "currency": d.get("cur", "USD"),
        "financing": d.get("fin", "none"),
        "scope": scope,
        "pending": list(scope),
        "status": "delegado",
        "trace": trace,
    }


def n_supervise(s: B2BState) -> dict:
    if s.get("status") in ("rechazado", "error", "error_captura"):
        return {"next": "end"}

    pending = list(s.get("pending") or [])
    while pending and pending[0] not in REGISTRY:
        pending.pop(0)

    if not pending:
        return {"pending": [], "next": "wait" if s.get("approve_url") else "notify"}

    return {"next": pending[0], "pending": pending[1:]}


def _route(s: B2BState) -> str:
    return s.get("next", "end")


def _worker(name: str):
    fn = REGISTRY[name]

    def node(s: B2BState) -> dict:
        return fn(s)

    return node


# ---------------------------------------------------------------------------
# Human approval + close-out
# ---------------------------------------------------------------------------
def n_wait(s: B2BState) -> dict:
    decision = interrupt({
        "approve_url": s.get("approve_url"),
        "order_id": s.get("order_id"),
        "monto": s.get("grand_total"),
        "currency": s.get("currency", "USD"),
        "breakdown": s.get("treasury", {}),
        "objective": s.get("objective"),
    })
    if decision.get("approved"):
        return {"status": "aprobado", "trace": audit(s, "supervisor", "Aprobación humana recibida")}
    return {"status": "cancelado", "message": "El comprador no aprobó la delegación",
            "trace": audit(s, "supervisor", "Aprobación rechazada")}


def _route_wait(s: B2BState) -> str:
    return "capture" if s.get("status") == "aprobado" else "notify"


def n_capture(s: B2BState) -> dict:
    return payments_agent.capture(s)


def n_notify(s: B2BState) -> dict:
    if s.get("status") == "completado":
        msg = (f"Delegación completada: {s.get('objective')} por "
               f"${s.get('grand_total', 0):,.2f}. Saldo restante del presupuesto: "
               f"${s.get('remaining', 0):,.2f}.")
        return {"message": msg, "trace": audit(s, "supervisor", msg)}
    if not s.get("message"):
        return {"message": "Flujo finalizado sin pago",
                "trace": audit(s, "supervisor", "Flujo finalizado sin pago")}
    return {}


def build_team(checkpointer=None):
    g = StateGraph(B2BState)
    g.add_node("read", n_read)
    g.add_node("supervise", n_supervise)
    for name in REGISTRY:
        g.add_node(name, _worker(name))
    g.add_node("wait", n_wait)
    g.add_node("capture", n_capture)
    g.add_node("notify", n_notify)

    g.set_entry_point("read")
    g.add_conditional_edges("read", lambda s: "end" if s.get("status") == "rechazado" else "supervise",
                            {"supervise": "supervise", "end": END})
    g.add_conditional_edges("supervise", _route, {
        **{name: name for name in REGISTRY},
        "wait": "wait",
        "notify": "notify",
        "end": END,
    })
    for name in REGISTRY:
        g.add_edge(name, "supervise")
    g.add_conditional_edges("wait", _route_wait, {"capture": "capture", "notify": "notify"})
    g.add_edge("capture", "notify")
    g.add_edge("notify", END)
    return g.compile(checkpointer=checkpointer or get_checkpointer())
