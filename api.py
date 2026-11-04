"""API opcional (FastAPI): uvicorn api:api --reload"""
import uuid
from fastapi import FastAPI
from langgraph.types import Command
from app.qr import crear_token
from app.graph import build_app

api = FastAPI(title="Pay2Win paycon")
graph = build_app()


@api.post("/qr")
def make_qr(customer_id: str, query: str, financing: str = "pay_in_4", max_amount: float = 500):
    return {"token": crear_token(customer_id, query, financing, max_amount)}


@api.post("/scan")
def scan(token: str):
    tid = str(uuid.uuid4())
    res = graph.invoke({"qr_token": token}, {"configurable": {"thread_id": tid}})
    if res.get("__interrupt__"):
        return {"thread_id": tid, "status": "esperando_aprobacion", **res["__interrupt__"][0].value}
    return {"thread_id": tid, "status": res.get("status"), "message": res.get("message")}


@api.post("/resume/{thread_id}")
def resume(thread_id: str, approved: bool = True):
    res = graph.invoke(Command(resume={"approved": approved}),
                       {"configurable": {"thread_id": thread_id}})
    return {"status": res.get("status"), "message": res.get("message")}
