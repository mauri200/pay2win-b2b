"""Pay2Win B2B API.

Run:  uvicorn b2b.api:api --reload --port 8001
Docs: http://localhost:8001/docs
Dashboard: http://localhost:8001/  (built React app when available)
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_groq import ChatGroq
from langgraph.types import Command
from pydantic import BaseModel, Field

from . import config, ledger, paypal_client, webhooks
from .channel3 import Channel3Provider, product_catalog_snapshot
from .mandate import create_mandate, mandate_qr_data_uri, validate_mandate
from .team import build_team

api = FastAPI(title="Pay2Win B2B", version="1.0")
team = build_team()

BASE = Path(__file__).resolve().parent
DIST = BASE / "dashboard" / "dist"
STATIC = BASE / "static"

if (DIST / "assets").exists():
    api.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ScanIn(BaseModel):
    token: str


class ApproveIn(BaseModel):
    approved: bool = True


class ChatIn(BaseModel):
    message: str
    budget: Optional[float] = None
    per_item_cap: Optional[float] = None
    financing: str = "pay_in_4"


class LineItem(BaseModel):
    name: str = Field(description="Exact product the business wants to buy")
    qty: int = Field(1, description="Quantity")


class Intent(BaseModel):
    objective: str = Field(description="Short English summary of the purchase objective")
    items: List[LineItem] = Field(default_factory=list)
    budget: Optional[float] = Field(None, description="Total budget in USD if stated")
    per_item_cap: Optional[float] = Field(None, description="Max price per unit if stated")
    financing: str = Field("pay_in_4", description="pay_in_4 unless paying in full")
    reply: str = Field(description="One friendly sentence in Spanish")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _run(token: str) -> dict:
    tid = str(uuid.uuid4())
    try:
        res = team.invoke({"mandate_token": token}, {"configurable": {"thread_id": tid}})
    except Exception as e:
        raise HTTPException(500, str(e))
    intr = res.get("__interrupt__")
    info = intr[0].value if intr else None
    return ledger.upsert(tid, res, info)


def _chat_heuristic(message: str, budget: Optional[float], cap: Optional[float],
                    financing: str) -> Intent:
    m = re.search(r"(?:budget|presupuesto|hasta|m[aá]ximo|max)\D{0,12}\$?\s*([\d.,]+)", message, re.I)
    found = None
    if m:
        found = float(m.group(1).replace(",", ""))
    else:
        m2 = re.search(r"\$\s*([\d.,]+)", message)
        if m2:
            found = float(m2.group(1).replace(",", ""))
    total = found or budget
    reply = (f"Entendido. Delegaré hasta ${total:,.2f} y el equipo se encarga del resto."
             if total else "¿Cuánto dinero quieres delegar? Indica un presupuesto total.")
    return Intent(objective=message, budget=total, per_item_cap=cap,
                  financing=financing if financing in ("pay_in_4", "none") else "pay_in_4",
                  reply=reply)


def _extract_intent(body: ChatIn) -> Intent:
    if not config.GROQ_API_KEY:
        return _chat_heuristic(body.message, body.budget, body.per_item_cap, body.financing)
    try:
        llm = ChatGroq(model=config.GROQ_MODEL, temperature=0).with_structured_output(Intent)
        names = ", ".join(p["name"] for p in product_catalog_snapshot())
        it = llm.invoke(
            "You are a B2B procurement planner. Extract the purchase objective, exact items "
            f"and quantities, total budget, per-item cap and financing. Known wholesale catalog: {names}. "
            f"If no budget is stated use none.\nRequest: {body.message}"
        )
        if it.budget is None:
            it.budget = body.budget
        if it.per_item_cap is None:
            it.per_item_cap = body.per_item_cap
        return it
    except Exception:
        return _chat_heuristic(body.message, body.budget, body.per_item_cap, body.financing)


def _mandate_payload(token: str, objective: str, budget: float, cap: float,
                     financing: str, currency: str, scope: list) -> dict:
    provider = Channel3Provider(currency=currency)
    preview = provider.resolve(objective, max_price=cap)
    return {
        "token": token,
        "png": mandate_qr_data_uri(token),
        "objective": objective,
        "budget": round(budget, 2),
        "per_item_cap": round(cap, 2),
        "financing": financing,
        "currency": currency,
        "scope": scope,
        "channel3_live": provider.live,
        "preview": [{"name": i["name"], "qty": i["qty"], "unit_price": i["unit_price"],
                     "supplier": i["supplier"], "stock": i["stock"], "source": i["source"]}
                    for i in preview],
    }


def _create_token(objective: str, budget: float, cap: Optional[float], financing: str,
                  currency: str, scope: Optional[str], items: Optional[list],
                  customer_id: str) -> dict:
    try:
        token = create_mandate(customer_id, objective, budget, cap or budget,
                               financing, currency, scope, items)
        d = validate_mandate(token)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return _mandate_payload(token, d["obj"], d["budget"], d["cap"], d["fin"],
                            d["cur"], d["scope"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@api.get("/")
def home():
    if (DIST / "index.html").exists():
        return FileResponse(DIST / "index.html")
    return FileResponse(STATIC / "index.html")


@api.get("/api/b2b/health")
def health():
    return {
        "ok": True,
        "channel3": "live" if config.CHANNEL3_API_KEY else "fallback-catalog",
        "paypal": "sandbox" if not config.SIMULATE_PAYMENTS else "simulated",
        "paypal_webhook": "signature-verified" if config.PAYPAL_WEBHOOK_ID else "unverified-demo",
        "external_notify": bool(config.NOTIFY_WEBHOOK_URL),
        "groq": bool(config.GROQ_API_KEY),
        "subagents": list(config.ALL_SUBAGENTS),
    }


@api.get("/api/b2b/catalog")
def catalog():
    return product_catalog_snapshot()


@api.get("/api/b2b/qr")
def make_qr(objective: str, budget: float = 5000, per_item_cap: Optional[float] = None,
            financing: str = "pay_in_4", currency: str = config.DEFAULT_CURRENCY,
            scope: Optional[str] = config.DEFAULT_SCOPE, customer_id: str = "CUST_DEMO"):
    return _create_token(objective, budget, per_item_cap, financing, currency,
                         scope, None, customer_id)


@api.post("/api/b2b/chat")
def chat(body: ChatIn):
    intent = _extract_intent(body)
    if not intent.budget:
        return {"reply": intent.reply, "mandate": None}

    cap = intent.per_item_cap or intent.budget
    objective = intent.objective or body.message
    items = [{"name": i.name, "qty": i.qty} for i in (intent.items or [])]
    try:
        payload = _create_token(objective, float(intent.budget), cap,
                                intent.financing, config.DEFAULT_CURRENCY,
                                config.DEFAULT_SCOPE, items, "CUST_DEMO")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"No se pudo crear el mandato: {e}")
    return {"reply": intent.reply, "mandate": payload}


@api.post("/api/b2b/start")
def start(body: ScanIn):
    return _run(body.token)


@api.post("/api/b2b/approve/{tid}")
def approve(tid: str, body: ApproveIn):
    row = ledger.get(tid)
    if not row:
        raise HTTPException(404, "Delegación desconocida")

    # A real sandbox order must be approved in PayPal before we resume the
    # graph. Otherwise the capture call fails and PayPal never sends its
    # sandbox email notification.
    if body.approved and row.get("payment_mode") == "paypal_sandbox" and row.get("order_id"):
        estado = paypal_client.order_status(row["order_id"])
        if estado not in ("APPROVED", "COMPLETED"):
            raise HTTPException(
                409,
                f"PayPal todavía reporta la orden {row['order_id']} como {estado}. "
                "Abre el link de aprobación, paga como comprador sandbox y vuelve a pulsar Approve.",
            )

    try:
        res = team.invoke(Command(resume={"approved": body.approved}),
                          {"configurable": {"thread_id": tid}})
    except Exception as e:
        raise HTTPException(500, str(e))
    return ledger.upsert(tid, res)


@api.get("/api/b2b/orders")
def orders():
    return ledger.all_orders()


@api.get("/api/b2b/orders/{tid}")
def order(tid: str):
    row = ledger.get(tid)
    if not row:
        raise HTTPException(404, "Delegación desconocida")
    return row


# ---------------------------------------------------------------------------
# PayPal webhooks
# ---------------------------------------------------------------------------
@api.post("/api/b2b/paypal/webhook")
async def paypal_webhook(request: Request):
    """Receive PayPal events (e.g. PAYMENT.CAPTURE.COMPLETED).

    Register this URL in the PayPal developer dashboard:
    https://<public-host>/api/b2b/paypal/webhook
    """
    raw = await request.body()
    try:
        event = json.loads(raw)
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    headers = {k.lower(): v for k, v in request.headers.items()}
    result = webhooks.handle_event(event, headers)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Webhook rejected"))
    return result


@api.get("/api/b2b/paypal/events")
def paypal_events():
    return ledger.payment_events()


@api.get("/api/b2b/paypal/order/{order_id}")
def paypal_order(order_id: str):
    """Live PayPal status for one order (handy while testing sandbox)."""
    try:
        data = paypal_client.get_order(order_id)
    except Exception as exc:
        raise HTTPException(502, f"No se pudo consultar la orden: {exc}")
    return {
        "order_id": data.get("id", order_id),
        "status": data.get("status"),
        "intent": data.get("intent"),
        "create_time": data.get("create_time"),
        "purchase_units": data.get("purchase_units", []),
    }
