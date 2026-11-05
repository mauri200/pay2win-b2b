"""Cart graph: one signed mandate -> quote all items -> ONE PayPal order -> ONE approval -> capture."""
import re, time
from typing import TypedDict, Optional
import jwt
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
from . import config
from .catalog import buscar
from .graph import _run_agent, _estado_orden


class CartState(TypedDict, total=False):
    mandate_token: str
    items: list
    budget: float
    per_item_cap: float
    financing: str
    final_price: float
    product_name: str
    order_id: Optional[str]
    approve_url: Optional[str]
    status: str
    message: str


def crear_mandato(cid, items, financing, budget, cap, ttl=900):
    return jwt.encode({"cid": cid, "items": items, "fin": financing, "budget": budget,
                       "cap": cap, "exp": int(time.time()) + ttl}, config.QR_SECRET, algorithm="HS256")


def n_read(s):
    try:
        d = jwt.decode(s["mandate_token"], config.QR_SECRET, algorithms=["HS256"])
    except Exception as e:
        return {"status": "rechazado", "message": f"Invalid mandate: {e}"}
    return {"items": d["items"], "budget": float(d["budget"]), "per_item_cap": float(d["cap"]),
            "financing": d["fin"], "status": "qr_ok"}


def n_quote(s):
    found = [buscar(n) for n in s["items"]]
    if not all(found):
        return {"status": "rechazado", "message": "A product is not in the catalog"}
    over = [p["name"] for p in found if p["price"] > s["per_item_cap"]]
    total = round(sum(p["price"] for p in found), 2)
    if over:
        return {"status": "rechazado", "message": f"Over the per-item cap (${s['per_item_cap']:.2f}): " + ", ".join(over)}
    if total > s["budget"]:
        return {"status": "rechazado", "message": f"Cart total ${total:.2f} exceeds the mandate budget (${s['budget']:.2f})"}
    return {"items": [{"name": p["name"], "price": p["price"]} for p in found], "final_price": total,
            "product_name": " + ".join(p["name"] for p in found), "status": "cotizado"}


def n_paylater(s):
    ok = s["financing"] == "pay_in_4" and config.PAYLATER_MIN <= s["final_price"] <= config.PAYLATER_MAX
    return {"financing": s["financing"] if ok else "none"}


def n_order(s):
    lines = "; ".join(f"1 x '{i['name']}' at {i['price']:.2f}" for i in s["items"])
    out = _run_agent(
        f"Create ONE PayPal order in USD with these line items: {lines}. The order total must be exactly "
        f"{s['final_price']:.2f}. Use return_url https://example.com/return and cancel_url https://example.com/cancel. "
        "Reply with the order id and the payer approval link.")
    link = re.search(r"https://www\.(?:sandbox\.)?paypal\.com/[^\s\"')>]+", out)
    oid = re.search(r"\b[0-9A-Z]{17}\b", out)
    if not link or not oid:
        return {"status": "error", "message": "Could not create the order. Output: " + out[-400:]}
    return {"order_id": oid.group(0), "approve_url": link.group(0), "status": "esperando_aprobacion"}


def n_wait(s):
    d = interrupt({"approve_url": s["approve_url"], "order_id": s["order_id"], "monto": s["final_price"]})
    return {"status": "aprobado"} if d.get("approved") else {"status": "cancelado", "message": "The buyer did not approve"}


def n_capture(s):
    _run_agent(f"Capture the approved PayPal order {s['order_id']}.")
    est = _estado_orden(s["order_id"])
    ok = est == "COMPLETED"
    return {"status": "completado" if ok else "error_captura",
            "message": "Payment completed" if ok else f"Order ended in status {est}; nothing was charged"}


def n_notify(s):
    if s["status"] != "completado":
        return {}
    msg = f"Done! {len(s['items'])} items for ${s['final_price']:.2f} in one order. Payment confirmed by PayPal."
    if s["financing"] == "pay_in_4":
        msg += f" Pay in 4 was available at checkout (${s['final_price']/4:.2f} per installment)."
    return {"message": msg}


def build_cart_app():
    g = StateGraph(CartState)
    for n, f in [("read", n_read), ("quote", n_quote), ("paylater", n_paylater), ("order", n_order),
                 ("wait", n_wait), ("capture", n_capture), ("notify", n_notify)]:
        g.add_node(n, f)
    g.set_entry_point("read")
    g.add_conditional_edges("read", lambda s: "end" if s["status"] == "rechazado" else "quote", {"quote": "quote", "end": END})
    g.add_conditional_edges("quote", lambda s: "end" if s["status"] == "rechazado" else "paylater", {"paylater": "paylater", "end": END})
    g.add_edge("paylater", "order")
    g.add_conditional_edges("order", lambda s: "end" if s["status"] == "error" else "wait", {"wait": "wait", "end": END})
    g.add_conditional_edges("wait", lambda s: "capture" if s["status"] == "aprobado" else "end", {"capture": "capture", "end": END})
    g.add_edge("capture", "notify")
    g.add_edge("notify", END)
    return g.compile(checkpointer=MemorySaver())
