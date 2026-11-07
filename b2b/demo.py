"""CLI demo for the B2B agent team.

    python -m b2b.demo

Creates a signed delegation mandate, lets the supervisor dispatch subagents,
pauses for PayPal approval and captures the payment (simulated when no PayPal
credentials are configured).
"""
import uuid

from langgraph.types import Command

from . import ledger
from .mandate import create_mandate, save_mandate_qr
from .team import build_team


def main() -> None:
    team = build_team()

    token = create_mandate(
        customer_id="CUST_MAU",
        objective="Compra 20 laptops empresariales y 10 monitores 4K para la nueva oficina",
        budget=50000,
        per_item_cap=1500,
        financing="pay_in_4",
    )
    print("Mandato QR guardado en:", save_mandate_qr(token))

    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
    res = team.invoke({"mandate_token": token}, cfg)
    tid = cfg["configurable"]["thread_id"]
    intr = res.get("__interrupt__")
    ledger.upsert(tid, res, intr[0].value if intr else None)

    print("\n--- Decisiones del equipo ---")
    for t in res.get("trace", []):
        print(f"  [{t['agent']}] {t['summary']}")

    if not intr:
        print("\nSin pago:", res.get("status"), "-", res.get("message"))
        return

    info = intr[0].value
    print(f"\nAprueba ${info['monto']:,.2f} en PayPal:")
    print(info["approve_url"])
    input("\nCuando termines de aprobar en sandbox, presiona Enter... ")

    final = team.invoke(Command(resume={"approved": True}), cfg)
    ledger.upsert(tid, final)
    print("\nEstado:", final.get("status"))
    print(final.get("message"))


if __name__ == "__main__":
    main()
