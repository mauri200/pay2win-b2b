"""Compliance subagent: sanctions screening, KYC and restricted-goods control."""
from __future__ import annotations

from ..channel3 import DENYLISTED_ORIGINS, DENYLISTED_SUPPLIERS
from ._shared import audit

AGENT = "compliance"


def run(state: dict) -> dict:
    items = state.get("items", [])
    flags, blocked = [], []

    for item in items:
        supplier = str(item.get("supplier", "")).strip().lower()
        origin = str(item.get("origin", "")).upper()
        if supplier in DENYLISTED_SUPPLIERS:
            blocked.append(f"Proveedor en lista de sanciones: {item['supplier']}")
        if origin in DENYLISTED_ORIGINS:
            blocked.append(f"Origen restringido: {origin} ({item['name']})")
        if item.get("restricted"):
            flags.append(f"Requiere permiso de exportación: {item['name']}")

    risk = min(100, 10 * len(flags) + (100 if blocked else 0))
    status = "blocked" if blocked else ("review" if flags else "pass")

    if blocked:
        return {
            "status": "rechazado",
            "message": "Compliance bloqueó la delegación: " + "; ".join(sorted(set(blocked))),
            "compliance": {"status": status, "risk_score": risk, "flags": flags,
                           "blocked": sorted(set(blocked))},
            "trace": audit(state, AGENT, "Delegación bloqueada por sanciones", {"blocked": blocked}),
        }

    summary = ("Verificación aprobada" if not flags
               else f"Aprobada con {len(flags)} permiso(s) pendiente(s)")
    return {
        "compliance": {"status": status, "risk_score": risk, "flags": flags, "blocked": []},
        "trace": audit(state, AGENT, summary, {"flags": flags}),
    }
