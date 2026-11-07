"""Configuration for the B2B team.

Reuses the existing project secrets (QR_SECRET, PayPal, Groq) without touching
the original modules. Adds Channel3 and a few B2B-only defaults.
"""
import os

from dotenv import load_dotenv

# Loads the same .env used by the rest of the project.
load_dotenv()

# Reuse the project's signing secret so both flows share the same trust root.
from app.config import (  # noqa: E402  (import after load_dotenv on purpose)
    GROQ_MODEL,
    PAYPAL_CLIENT_ID,
    PAYPAL_CLIENT_SECRET,
    QR_SECRET,
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

CHANNEL3_API_KEY = os.getenv("CHANNEL3_API_KEY", "")
CHANNEL3_BASE_URL = os.getenv("CHANNEL3_BASE_URL", "https://api.trychannel3.com")
CHANNEL3_MODE = os.getenv("CHANNEL3_MODE", "agentic")

DEFAULT_CURRENCY = os.getenv("B2B_CURRENCY", "USD")
DEFAULT_COUNTRY = os.getenv("B2B_COUNTRY", "US")

# Guardrails
MAX_DELEGATION = float(os.getenv("B2B_MAX_DELEGATION", "250000"))
DEFAULT_TTL = int(os.getenv("B2B_MANDATE_TTL", "900"))

# Treasury / fees
PAYMENT_FEE_RATE = float(os.getenv("B2B_PAYMENT_FEE_RATE", "0.029"))
BROKERAGE_FEE = float(os.getenv("B2B_BROKERAGE_FEE", "45"))
VAT_RATE = float(os.getenv("B2B_VAT_RATE", "0.16"))

# Subagents the supervisor can delegate to.
ALL_SUBAGENTS = (
    "procurement",
    "customs",
    "logistics",
    "compliance",
    "treasury",
    "payments",
)

DEFAULT_SCOPE = ",".join(ALL_SUBAGENTS)

# Sandbox / offline behaviour: when PayPal credentials are missing the payment
# subagent runs in simulation mode so the flow stays demoable.
SIMULATE_PAYMENTS = not (PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)

# PayPal webhooks. Set PAYPAL_WEBHOOK_ID to the webhook registered in the
# developer dashboard to enforce signature verification. Without it events are
# accepted unverified so local demos keep working.
PAYPAL_API_BASE = os.getenv("PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com")
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "")

# Optional Slack-compatible incoming webhook for outbound payment alerts.
NOTIFY_WEBHOOK_URL = os.getenv("B2B_NOTIFY_WEBHOOK_URL", "")
