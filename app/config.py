import os
from dotenv import load_dotenv

load_dotenv()

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
QR_SECRET = os.getenv("QR_SECRET", "dev-secret")

# Pay Later (Pay in 4) aplica típicamente en este rango (USD). Verifica en tu país/cuenta sandbox.
PAYLATER_MIN = 30.0
PAYLATER_MAX = 1500.0
