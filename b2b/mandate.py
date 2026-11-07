"""Signed delegation mandate - the B2B version of the single signed QR.

Same primitives as app/qr.py (HS256 JWT + TTL), extended with the B2B
delegation envelope: objective, total budget, per-item cap, currency, allowed
subagents and an optional item list. The buyer only delegates money; the team
decides how to spend it inside these hard limits.
"""
import base64
import io
import time
from typing import Iterable, Optional

import jwt
import qrcode

from . import config


def _as_list(scope: Optional[Iterable[str]]) -> list:
    if not scope:
        return list(config.ALL_SUBAGENTS)
    if isinstance(scope, str):
        items = [s.strip() for s in scope.split(",") if s.strip()]
    else:
        items = [str(s).strip() for s in scope if str(s).strip()]
    allowed = [s for s in items if s in config.ALL_SUBAGENTS]
    return allowed or list(config.ALL_SUBAGENTS)


def create_mandate(
    customer_id: str,
    objective: str,
    budget: float,
    per_item_cap: Optional[float] = None,
    financing: str = "pay_in_4",
    currency: str = config.DEFAULT_CURRENCY,
    scope: Optional[Iterable[str]] = None,
    items: Optional[list] = None,
    ttl: int = config.DEFAULT_TTL,
) -> str:
    """Create the signed mandate token embedded in the QR."""
    budget = round(float(budget), 2)
    if budget <= 0:
        raise ValueError("budget must be greater than 0")
    if budget > config.MAX_DELEGATION:
        raise ValueError(f"budget exceeds the platform delegation limit (${config.MAX_DELEGATION:,.2f})")
    cap = round(float(per_item_cap), 2) if per_item_cap else budget
    if cap <= 0:
        raise ValueError("per_item_cap must be greater than 0")

    payload = {
        "typ": "b2b_mandate",
        "cid": customer_id,
        "obj": objective.strip(),
        "budget": budget,
        "cap": cap,
        "cur": currency,
        "fin": financing,
        "scope": _as_list(scope),
        "items": items or [],
        "exp": int(time.time()) + int(ttl),
    }
    return jwt.encode(payload, config.QR_SECRET, algorithm="HS256")


def validate_mandate(token: str) -> dict:
    """Validate signature + expiry and normalise the envelope."""
    data = jwt.decode(token, config.QR_SECRET, algorithms=["HS256"])
    if data.get("typ") != "b2b_mandate":
        raise ValueError("token is not a B2B mandate")
    data["budget"] = float(data["budget"])
    data["cap"] = float(data.get("cap", data["budget"]))
    data["scope"] = _as_list(data.get("scope"))
    return data


def mandate_qr_data_uri(token: str) -> str:
    buf = io.BytesIO()
    qrcode.make(f"pay2win://b2b?t={token}").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def save_mandate_qr(token: str, path: str = "b2b_mandate_qr.png") -> str:
    qrcode.make(f"pay2win://b2b?t={token}").save(path)
    return path
