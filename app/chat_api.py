"""Chat endpoints: Groq turns a request into a mandate; the cart graph executes it."""
import base64, io, uuid
from typing import List, Optional
import qrcode
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langgraph.types import Command
from . import config
from .catalog import CATALOGO, buscar
from .cart_graph import build_cart_app, crear_mandato


class Intent(BaseModel):
    items: List[str] = Field(default_factory=list, description="Exact catalog product names the user wants; repeat a name for quantities")
    budget: Optional[float] = Field(None, description="Total budget in USD, only if the user stated one")
    per_item_cap: Optional[float] = Field(None, description="Max price per item in USD, only if stated")
    financing: str = Field("pay_in_4", description="pay_in_4 unless the user asks to pay in full (then none)")
    reply: str = Field(description="One short friendly sentence in English")


class ChatIn(BaseModel):
    message: str


class StartIn(BaseModel):
    token: str


def make_router(ORDERS, _guardar):
    r = APIRouter(prefix="/api")
    app = build_cart_app()
    llm = ChatGroq(model=config.GROQ_MODEL, temperature=0).with_structured_output(Intent)
    names = ", ".join(p["name"] for p in CATALOGO)

    @r.post("/chat")
    def chat(body: ChatIn):
        try:
            it = llm.invoke(f"You are a shopping agent. Catalog: {names}. Extract what the user wants to buy "
                            f"(exact catalog names), budget, per-item cap and financing.\nUser: {body.message}")
        except Exception as e:
            raise HTTPException(500, f"LLM error: {e}")
        found = [p for p in (buscar(n) for n in it.items) if p]
        if not found:
            return {"reply": "I couldn't match any product from our catalog. Try: " + names, "mandate": None}
        fin = it.financing if it.financing in ("pay_in_4", "none") else "pay_in_4"
        total = round(sum(p["price"] for p in found), 2)
        budget = it.budget or total
        cap = it.per_item_cap or max(p["price"] for p in found)
        token = crear_mandato("CUST_DEMO", [p["name"] for p in found], fin, budget, cap)
        buf = io.BytesIO()
        qrcode.make(f"pay2win://mandate?t={token}").save(buf, format="PNG")
        return {"reply": it.reply, "mandate": {
            "items": [{"name": p["name"], "price": p["price"]} for p in found], "total": total,
            "budget": budget, "per_item_cap": cap, "financing": fin, "token": token,
            "png": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}}

    @r.post("/cart/start")
    def start(body: StartIn):
        tid = str(uuid.uuid4())
        try:
            res = app.invoke({"mandate_token": body.token}, {"configurable": {"thread_id": tid}})
        except Exception as e:
            raise HTTPException(500, str(e))
        return _guardar(tid, res)

    @r.post("/cart/resume/{tid}")
    def resume(tid: str):
        if tid not in ORDERS:
            raise HTTPException(404, "Unknown order")
        try:
            res = app.invoke(Command(resume={"approved": True}), {"configurable": {"thread_id": tid}})
        except Exception as e:
            raise HTTPException(500, str(e))
        return _guardar(tid, res)

    return r
