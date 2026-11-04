"""Pay2Win paycon - API + UI.  Local: uvicorn api:api --reload  ->  http://localhost:8000"""
import base64, io, time, uuid
from pathlib import Path

import qrcode
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from langgraph.types import Command

from app.qr import crear_token
from app.graph import build_app

api = FastAPI(title="Pay2Win paycon", version="1.0")
graph = build_app()
ORDERS: dict[str, dict] = {}          # historial en memoria (demo)
STATIC = Path(__file__).parent / "static"


class ScanIn(BaseModel):
    token: str


class ResumeIn(BaseModel):
    approved: bool = True


def _guardar(tid: str, res: dict) -> dict:
    row = ORDERS.setdefault(tid, {"thread_id": tid, "creado": time.strftime("%H:%M:%S")})
    intr = res.get("__interrupt__")
    row.update(
        producto=res.get("product_name"), monto=res.get("final_price"),
        financiamiento=res.get("financing"), mensaje=res.get("message"),
        estado="esperando_aprobacion" if intr else res.get("status"),
    )
    if intr:
        row["approve_url"] = intr[0].value["approve_url"]
        row["order_id"] = intr[0].value["order_id"]
    return row


@api.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@api.get("/api/qr")
def make_qr(query: str, max_amount: float = 500, financing: str = "pay_in_4",
            customer_id: str = "CUST_DEMO"):
    token = crear_token(customer_id, query, financing, max_amount)
    buf = io.BytesIO()
    qrcode.make(f"pay2win://buy?t={token}").save(buf, format="PNG")
    return {"token": token, "png": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}


@api.post("/api/scan")
def scan(body: ScanIn):
    tid = str(uuid.uuid4())
    try:
        res = graph.invoke({"qr_token": body.token}, {"configurable": {"thread_id": tid}})
    except Exception as e:
        raise HTTPException(500, str(e))
    return _guardar(tid, res)


@api.post("/api/resume/{tid}")
def resume(tid: str, body: ResumeIn):
    if tid not in ORDERS:
        raise HTTPException(404, "Orden desconocida")
    try:
        res = graph.invoke(Command(resume={"approved": body.approved}),
                           {"configurable": {"thread_id": tid}})
    except Exception as e:
        raise HTTPException(500, str(e))
    return _guardar(tid, res)


@api.get("/api/orders")
def orders():
    return list(reversed(list(ORDERS.values())))
