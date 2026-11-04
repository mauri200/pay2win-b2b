"""Demo CLI: genera el QR, lo 'escanea', pausa para aprobar en PayPal sandbox y captura."""
import uuid
from langgraph.types import Command
from app.qr import crear_token, guardar_qr_png
from app.graph import build_app

app = build_app()

token = crear_token(customer_id="CUST_MAU", query="Laptop Dell i7",
                    financing="pay_in_4", max_amount=600.0)
print("QR guardado en:", guardar_qr_png(token))

cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
res = app.invoke({"qr_token": token}, cfg)

intr = res.get("__interrupt__")
if not intr:
    print("Fin sin pago:", res.get("status"), "-", res.get("message"))
    raise SystemExit

info = intr[0].value
print(f"\nAprueba ${info['monto']} en PayPal (elige 'Pay Later' si aparece):\n{info['approve_url']}")
input("\nCuando termines de aprobar en sandbox, presiona Enter... ")

final = app.invoke(Command(resume={"approved": True}), cfg)
print("\nEstado:", final["status"])
print(final.get("message"))
