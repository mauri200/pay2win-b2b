"""Grafo LangGraph de Pay2Win paycon.

QR -> cotizar -> verificar Pay Later -> crear orden (PayPal agent toolkit)
   -> INTERRUPT (el comprador aprueba en PayPal y elige Pay Later) -> capturar -> notificar
"""
import re
import requests
from typing import TypedDict, Optional
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langgraph.types import interrupt, Command
from paypal_agent_toolkit.langchain.toolkit import PayPalToolkit
from paypal_agent_toolkit.shared.configuration import Configuration, Context

from . import config
from .qr import validar_token
from .catalog import buscar


class PayState(TypedDict, total=False):
    qr_token: str
    customer_id: str
    product_query: str
    product_name: str
    final_price: float
    max_amount: float
    financing: str            # pay_in_4 | paypal_credit | none
    order_id: Optional[str]
    approve_url: Optional[str]
    status: str
    message: str


# ---------- PayPal agent toolkit + LLM (Groq) ----------
_toolkit = PayPalToolkit(
    client_id=config.PAYPAL_CLIENT_ID,
    secret=config.PAYPAL_CLIENT_SECRET,
    configuration=Configuration(
        actions={"orders": {"create": True, "get": True, "capture": True}},
        context=Context(sandbox=True),
    ),
)
_tools = _toolkit.get_tools()
_llm = ChatGroq(model=config.GROQ_MODEL, temperature=0)
_paypal_agent = create_react_agent(_llm, _tools)


def _run_agent(prompt: str) -> str:
    res = _paypal_agent.invoke({"messages": [("user", prompt)]})
    # concatenamos todo (incluye salidas de las tools) para extraer id/links
    return "\n".join(str(m.content) for m in res["messages"])


# ---------- Nodos ----------
def n_leer_qr(s: PayState) -> PayState:
    try:
        d = validar_token(s["qr_token"])
    except Exception as e:  # expirado o alterado
        return {"status": "rechazado", "message": f"QR inválido: {e}"}
    return {
        "customer_id": d["cid"], "product_query": d["q"],
        "financing": d["fin"], "max_amount": float(d["max"]),
        "status": "qr_ok",
    }


def n_cotizar(s: PayState) -> PayState:
    p = buscar(s["product_query"])
    if not p:
        return {"status": "rechazado", "message": "Producto no encontrado"}
    if p["price"] > s["max_amount"]:  # guardia de gasto
        return {"status": "rechazado",
                "message": f"${p['price']} excede el tope autorizado en el QR (${s['max_amount']})"}
    return {"product_name": p["name"], "final_price": p["price"], "status": "cotizado"}


def n_verificar_paylater(s: PayState) -> PayState:
    if s["financing"] != "none" and config.PAYLATER_MIN <= s["final_price"] <= config.PAYLATER_MAX:
        return {"status": "elegible_paylater"}
    return {"status": "pago_directo", "financing": "none"}


def n_crear_orden(s: PayState) -> PayState:
    cuotas = ""
    if s["financing"] == "pay_in_4":
        cuotas = f" (el comprador podrá elegir Pay Later: 4 cuotas de ${s['final_price']/4:.2f})"
    out = _run_agent(
        f"Create a PayPal order in USD for 1 x '{s['product_name']}' with total {s['final_price']:.2f}{cuotas}. "
        "Use return_url https://example.com/return and cancel_url https://example.com/cancel. "
        "Then reply with the order id and the payer approval link."
    )
    link = re.search(r"https://www\.(?:sandbox\.)?paypal\.com/[^\s\"')>]+", out)
    oid = re.search(r"\b[0-9A-Z]{17}\b", out)
    if not link or not oid:
        return {"status": "error", "message": "No se pudo crear la orden. Salida: " + out[-400:]}
    return {"order_id": oid.group(0), "approve_url": link.group(0), "status": "esperando_aprobacion"}


def n_esperar_aprobacion(s: PayState) -> PayState:
    # PAUSA: el grafo se congela aquí hasta que se reanude con Command(resume=...)
    decision = interrupt({"approve_url": s["approve_url"], "order_id": s["order_id"],
                          "monto": s["final_price"]})
    if decision.get("approved"):
        return {"status": "aprobado"}
    return {"status": "cancelado", "message": "El comprador no aprobó"}

def _estado_orden(order_id: str) -> str:
    base = "https://api-m.sandbox.paypal.com"
    tok = requests.post(
        f"{base}/v1/oauth2/token", data={"grant_type": "client_credentials"},
        auth=(config.PAYPAL_CLIENT_ID, config.PAYPAL_CLIENT_SECRET), timeout=20,
    ).json()["access_token"]
    r = requests.get(f"{base}/v2/checkout/orders/{order_id}",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    return r.json().get("status", "UNKNOWN")


def n_capturar(s: PayState) -> PayState:
    _run_agent(f"Capture the approved PayPal order {s['order_id']}.")
    estado = _estado_orden(s["order_id"])
    ok = estado == "COMPLETED"
    return {"status": "completado" if ok else "error_captura",
            "message": "Pago completado" if ok else f"La orden quedó en estado {estado}; no se cobró"}
def _estado_orden(order_id: str) -> str:
    base = "https://api-m.sandbox.paypal.com"
    tok = requests.post(
        f"{base}/v1/oauth2/token", data={"grant_type": "client_credentials"},
        auth=(config.PAYPAL_CLIENT_ID, config.PAYPAL_CLIENT_SECRET), timeout=20,
    ).json()["access_token"]
    r = requests.get(f"{base}/v2/checkout/orders/{order_id}",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    return r.json().get("status", "UNKNOWN")


def n_capturar(s: PayState) -> PayState:
    _run_agent(f"Capture the approved PayPal order {s['order_id']}.")
    estado = _estado_orden(s["order_id"])
    ok = estado == "COMPLETED"
    return {"status": "completado" if ok else "error_captura",
            "message": "Pago completado" if ok else f"La orden quedó en estado {estado}; no se cobró"}


def n_notificar(s: PayState) -> PayState:
    if s["status"] == "completado":
        msg = f"¡Listo! {s['product_name']} por ${s['final_price']:.2f}."
        if s["financing"] == "pay_in_4":
            msg += f" Si elegiste Pay Later: 4 cuotas de ${s['final_price']/4:.2f}."
        return {"message": msg}
    return {}


# ---------- Ruteo ----------
def _tras_qr(s): return "fin" if s["status"] == "rechazado" else "cotizar"
def _tras_cotizar(s): return "fin" if s["status"] == "rechazado" else "paylater"
def _tras_orden(s): return "fin" if s["status"] == "error" else "esperar"
def _tras_espera(s): return "capturar" if s["status"] == "aprobado" else "fin"


def build_app():
    g = StateGraph(PayState)
    g.add_node("leer_qr", n_leer_qr)
    g.add_node("cotizar", n_cotizar)
    g.add_node("paylater", n_verificar_paylater)
    g.add_node("crear_orden", n_crear_orden)
    g.add_node("esperar", n_esperar_aprobacion)
    g.add_node("capturar", n_capturar)
    g.add_node("notificar", n_notificar)

    g.set_entry_point("leer_qr")
    g.add_conditional_edges("leer_qr", _tras_qr, {"cotizar": "cotizar", "fin": END})
    g.add_conditional_edges("cotizar", _tras_cotizar, {"paylater": "paylater", "fin": END})
    g.add_edge("paylater", "crear_orden")
    g.add_conditional_edges("crear_orden", _tras_orden, {"esperar": "esperar", "fin": END})
    g.add_conditional_edges("esperar", _tras_espera, {"capturar": "capturar", "fin": END})
    g.add_edge("capturar", "notificar")
    g.add_edge("notificar", END)
    return g.compile(checkpointer=MemorySaver())
