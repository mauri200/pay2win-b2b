"""Thin PayPal REST client used by the B2B payment subagent and webhooks.

The Pay Later / order creation flow still goes through the LangChain ReAct
agent (same as the consumer app), but capture and status checks use the REST API
directly so a payment is actually captured — and PayPal can emit its sandbox
email notification — with a deterministic call.
"""
from __future__ import annotations

import time
import uuid
from typing import Optional

import requests

from . import config

_TOKEN: dict[str, tuple[str, float]] = {}


def _base() -> str:
    return config.PAYPAL_API_BASE.rstrip("/")


def access_token(force: bool = False) -> Optional[str]:
    """Client-credentials token, cached until shortly before expiry."""
    if not force:
        cached = _TOKEN.get("token")
        if cached and cached[1] > time.time() + 30:
            return cached[0]
    if not (config.PAYPAL_CLIENT_ID and config.PAYPAL_CLIENT_SECRET):
        return None
    try:
        r = requests.post(
            f"{_base()}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(config.PAYPAL_CLIENT_ID, config.PAYPAL_CLIENT_SECRET),
            timeout=20,
        )
        r.raise_for_status()
        payload = r.json()
    except Exception:
        return None
    token = payload.get("access_token")
    if token:
        _TOKEN["token"] = (token, time.time() + int(payload.get("expires_in", 300)))
    return token


def _headers() -> dict:
    token = access_token()
    if not token:
        raise RuntimeError("No se pudo autenticar con PayPal (revisa las credenciales)")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_order(order_id: str) -> dict:
    r = requests.get(f"{_base()}/v2/checkout/orders/{order_id}", headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


def order_status(order_id: str) -> str:
    try:
        return get_order(order_id).get("status", "UNKNOWN")
    except Exception:
        return "UNKNOWN"


def capture_order(order_id: str) -> tuple[bool, str, dict]:
    """Capture an approved order. Returns (ok, status_or_error, raw_response)."""
    try:
        r = requests.post(
            f"{_base()}/v2/checkout/orders/{order_id}/capture",
            headers={**_headers(), "PayPal-Request-Id": str(uuid.uuid4())},
            json={},
            timeout=30,
        )
    except Exception as exc:
        return False, f"Error de red al capturar: {exc}", {}

    try:
        data = r.json()
    except Exception:
        data = {}
    if r.status_code >= 400:
        detail = data.get("message") or data.get("details") or f"HTTP {r.status_code}"
        return False, str(detail), data
    return True, data.get("status", "COMPLETED"), data
