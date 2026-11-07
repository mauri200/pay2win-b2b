"""PayPal webhook handling for the B2B module.

Verifies the PayPal transmission signature (when PAYPAL_WEBHOOK_ID is set),
records the event in the in-memory ledger so the dashboard can display it, and
optionally forwards a short notification to a Slack-compatible webhook URL.

PayPal docs: /v1/notifications/verify-webhook-signature
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from . import config, ledger, paypal_client

log = logging.getLogger("b2b.webhooks")

_HEADERS = (
    "paypal-auth-algo",
    "paypal-cert-url",
    "paypal-transmission-id",
    "paypal-transmission-sig",
    "paypal-transmission-time",
)


def _access_token() -> Optional[str]:
    return paypal_client.access_token()


def verify_signature(event: dict, headers: dict) -> tuple[bool, str]:
    """Validate the PayPal webhook signature.

    Returns (verified, detail). When PAYPAL_WEBHOOK_ID is not configured the
    event is accepted as unverified so the flow stays demoable offline.
    """
    if not config.PAYPAL_WEBHOOK_ID:
        return False, "PAYPAL_WEBHOOK_ID not set; accepted without verification (demo mode)"

    missing = [h for h in _HEADERS if not headers.get(h)]
    if missing:
        return False, "Missing PayPal signature headers: " + ", ".join(missing)

    token = _access_token()
    if not token:
        return False, "Cannot authenticate with PayPal to verify the signature"

    body = {
        "auth_algo": headers["paypal-auth-algo"],
        "cert_url": headers["paypal-cert-url"],
        "transmission_id": headers["paypal-transmission-id"],
        "transmission_sig": headers["paypal-transmission-sig"],
        "transmission_time": headers["paypal-transmission-time"],
        "webhook_id": config.PAYPAL_WEBHOOK_ID,
        "webhook_event": event,
    }
    base = config.PAYPAL_API_BASE.rstrip("/")
    try:
        r = requests.post(
            f"{base}/v1/notifications/verify-webhook-signature",
            json=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # pragma: no cover - network dependent
        log.warning("PayPal signature verification failed: %s", exc)
        return False, f"Signature verification request failed: {exc}"

    status = data.get("verification_status")
    return status == "SUCCESS", f"verification_status={status}"


def order_id_from_event(event: dict) -> Optional[str]:
    """Best-effort extraction of the PayPal order id from any event type."""
    resource = event.get("resource") or {}
    related = (resource.get("supplementary_data") or {}).get("related_ids") or {}
    if related.get("order_id"):
        return related["order_id"]
    if resource.get("order_id"):
        return resource["order_id"]
    event_type = event.get("event_type", "")
    if event_type.startswith("CHECKOUT.ORDER") and resource.get("id"):
        return resource["id"]
    return None


def _event_amount(event: dict) -> Optional[float]:
    resource = event.get("resource") or {}
    candidates = [resource.get("amount")]
    candidates.extend((unit or {}).get("amount") for unit in resource.get("purchase_units") or [])
    for amount in candidates:
        if not isinstance(amount, dict):
            continue
        value = amount.get("value")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            continue
    return None


def _forward(event_type: str, order_id: Optional[str], amount: Optional[float]) -> None:
    """Optional Slack-compatible notification (B2B_NOTIFY_WEBHOOK_URL)."""
    url = config.NOTIFY_WEBHOOK_URL
    if not url:
        return
    text = f"PayPal {event_type}"
    if order_id:
        text += f" · order {order_id}"
    if amount is not None:
        text += f" · ${amount:,.2f}"
    try:
        requests.post(url, json={"text": text}, timeout=10)
    except Exception as exc:  # pragma: no cover - network dependent
        log.warning("External notification failed: %s", exc)


def handle_event(event: dict, headers: dict) -> dict:
    """Verify, record and optionally forward one PayPal webhook event."""
    event_type = event.get("event_type", "UNKNOWN")
    event_id = event.get("id")
    order_id = order_id_from_event(event)
    verified, detail = verify_signature(event, headers)

    if config.PAYPAL_WEBHOOK_ID and not verified:
        log.warning("Rejected PayPal webhook %s: %s", event_type, detail)
        return {
            "ok": False,
            "error": detail,
            "event_type": event_type,
            "order_id": order_id,
        }

    matched = ledger.record_payment_event(
        event_type=event_type,
        event_id=event_id,
        order_id=order_id,
        verified=verified,
        detail=detail,
        amount=_event_amount(event),
    )
    _forward(event_type, order_id, _event_amount(event))
    log.info("PayPal webhook %s for order %s (verified=%s, rows=%d)",
             event_type, order_id, verified, len(matched))
    return {
        "ok": True,
        "verified": verified,
        "verification": detail,
        "event_id": event_id,
        "event_type": event_type,
        "order_id": order_id,
        "matched": matched,
    }
