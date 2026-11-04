"""QR único = orden de compra parametrizada y firmada (JWT).
No lleva monto: lleva intención, preferencia de financiamiento y un TOPE de gasto
(la guardia de confianza: el agente nunca puede cobrar más de max_amount)."""
import time
import jwt
import qrcode
from .config import QR_SECRET


def crear_token(customer_id: str, query: str, financing: str = "pay_in_4",
                max_amount: float = 500.0, ttl: int = 900) -> str:
    payload = {
        "cid": customer_id,
        "q": query,
        "fin": financing,
        "max": max_amount,
        "exp": int(time.time()) + ttl,
    }
    return jwt.encode(payload, QR_SECRET, algorithm="HS256")


def validar_token(token: str) -> dict:
    return jwt.decode(token, QR_SECRET, algorithms=["HS256"])  # lanza si expiró/alterado


def guardar_qr_png(token: str, path: str = "pay2win_qr.png") -> str:
    qrcode.make(f"pay2win://buy?t={token}").save(path)
    return path
