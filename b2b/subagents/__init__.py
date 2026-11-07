"""Specialised B2B subagents dispatched by the supervisor."""

from . import compliance, customs, logistics, payments, procurement, treasury

# name -> callable(state) -> state delta
REGISTRY = {
    "procurement": procurement.run,
    "customs": customs.run,
    "logistics": logistics.run,
    "compliance": compliance.run,
    "treasury": treasury.run,
    "payments": payments.run,
}

__all__ = ["REGISTRY"]
