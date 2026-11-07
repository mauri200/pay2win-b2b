"""Channel3 product/stock provider with an offline B2B fallback.

Live path: POST https://api.trychannel3.com/v1/search (see the channel3-api
skill). The API key never leaves the server. When CHANNEL3_API_KEY is missing
(or the call fails) we fall back to a deterministic local wholesale catalog so
the whole team stays demoable offline.

Channel3 is used for product discovery + offer availability ("stock"). We then
augment its offers with the B2B attributes the customs/logistics subagents need
(HS code, duty rate, weight, origin) using a keyword heuristic.
"""
from __future__ import annotations

import difflib
import re
from typing import Optional

import requests

from . import config

# ---------------------------------------------------------------------------
# Offline wholesale catalog (also used to infer trade attributes for live hits)
# ---------------------------------------------------------------------------
B2B_CATALOG = [
    {"sku": "LAP-PRO-14", "name": "Laptop Pro 14 i7 32GB", "price": 1180.00, "stock": 240,
     "supplier": "TechSource Global", "origin": "CN", "hs_code": "8471.30",
     "duty_rate": 0.00, "weight_kg": 1.6, "category": "electronics", "restricted": False},
    {"sku": "LAP-ENT-15", "name": "Enterprise Laptop 15 i5 16GB", "price": 760.00, "stock": 520,
     "supplier": "Nova Devices", "origin": "VN", "hs_code": "8471.30",
     "duty_rate": 0.00, "weight_kg": 1.9, "category": "electronics", "restricted": False},
    {"sku": "SRV-1U", "name": "Rack Server 1U 64GB ECC", "price": 2450.00, "stock": 60,
     "supplier": "DataCore Industries", "origin": "TW", "hs_code": "8471.50",
     "duty_rate": 0.00, "weight_kg": 12.5, "category": "electronics", "restricted": False},
    {"sku": "NET-48P", "name": "48-Port PoE Network Switch", "price": 640.00, "stock": 180,
     "supplier": "NetLink Supply", "origin": "CN", "hs_code": "8517.62",
     "duty_rate": 0.035, "weight_kg": 4.2, "category": "electronics", "restricted": False},
    {"sku": "SCN-2D", "name": "Industrial 2D Barcode Scanner", "price": 145.00, "stock": 900,
     "supplier": "ScanWorks Ltd", "origin": "MY", "hs_code": "8471.60",
     "duty_rate": 0.00, "weight_kg": 0.4, "category": "electronics", "restricted": False},
    {"sku": "MON-4K-B", "name": "27 inch 4K Business Monitor", "price": 289.00, "stock": 410,
     "supplier": "PixelView Co", "origin": "CN", "hs_code": "8528.52",
     "duty_rate": 0.05, "weight_kg": 5.4, "category": "electronics", "restricted": False},
    {"sku": "SOL-PANEL", "name": "Solar Panel 550W Monocrystalline", "price": 210.00, "stock": 300,
     "supplier": "GreenGrid Energy", "origin": "CN", "hs_code": "8541.43",
     "duty_rate": 0.08, "weight_kg": 27.0, "category": "energy", "restricted": False},
    {"sku": "BAT-LIION", "name": "Lithium Battery Pack 48V 100Ah", "price": 980.00, "stock": 75,
     "supplier": "VoltStream", "origin": "CN", "hs_code": "8507.60",
     "duty_rate": 0.075, "weight_kg": 46.0, "category": "energy", "restricted": True},
    {"sku": "CHR-ERG", "name": "Ergonomic Office Chair Mesh", "price": 132.00, "stock": 650,
     "supplier": "ComfortLine", "origin": "PL", "hs_code": "9401.31",
     "duty_rate": 0.03, "weight_kg": 14.0, "category": "furniture", "restricted": False},
    {"sku": "DSK-STAND", "name": "Standing Desk 160x80 Electric", "price": 410.00, "stock": 160,
     "supplier": "ComfortLine", "origin": "PL", "hs_code": "9403.30",
     "duty_rate": 0.045, "weight_kg": 32.0, "category": "furniture", "restricted": False},
    {"sku": "PKG-IND", "name": "Industrial Packaging Film Roll", "price": 24.00, "stock": 5000,
     "supplier": "PackRight", "origin": "MX", "hs_code": "3923.21",
     "duty_rate": 0.06, "weight_kg": 2.1, "category": "supplies", "restricted": False},
    {"sku": "PRN-LASER", "name": "Enterprise Laser Printer A3", "price": 520.00, "stock": 120,
     "supplier": "PrintHub", "origin": "JP", "hs_code": "8443.32",
     "duty_rate": 0.02, "weight_kg": 18.0, "category": "electronics", "restricted": False},
]

# Suppliers that compliance must block in the demo sanctions screen.
DENYLISTED_SUPPLIERS = {"shadow trade intl", "sanctioned parts co"}
DENYLISTED_ORIGINS = {"KP", "IR", "SY"}

# Keyword → trade attributes used when a live Channel3 product has no local twin.
_TRADE_HINTS = [
    (("laptop", "notebook", "chromebook"), "8471.30", 0.00, 1.8, "electronics", False),
    (("server", "rack"), "8471.50", 0.00, 12.0, "electronics", False),
    (("switch", "router", "network"), "8517.62", 0.035, 4.0, "electronics", False),
    (("scanner", "barcode"), "8471.60", 0.00, 0.5, "electronics", False),
    (("monitor", "display", "screen"), "8528.52", 0.05, 5.0, "electronics", False),
    (("printer",), "8443.32", 0.02, 18.0, "electronics", False),
    (("solar", "panel"), "8541.43", 0.08, 27.0, "energy", False),
    (("battery", "lithium"), "8507.60", 0.075, 46.0, "energy", True),
    (("chair", "seating"), "9401.31", 0.03, 14.0, "furniture", False),
    (("desk", "table"), "9403.30", 0.045, 32.0, "furniture", False),
    (("packaging", "film", "wrap"), "3923.21", 0.06, 2.0, "supplies", False),
]


def infer_trade_attributes(title: str) -> dict:
    low = (title or "").lower()
    for keywords, hs, duty, weight, category, restricted in _TRADE_HINTS:
        if any(k in low for k in keywords):
            return {"hs_code": hs, "duty_rate": duty, "weight_kg": weight,
                    "category": category, "restricted": restricted}
    return {"hs_code": "9999.99", "duty_rate": 0.05, "weight_kg": 2.0,
            "category": "general", "restricted": False}


# Minimal ES→EN product vocabulary so a Spanish B2B objective matches the
# English Channel3/catalog titles.
_SYNONYMS = {
    "portatil": "laptop", "portatiles": "laptop", "laptops": "laptop",
    "monitor": "monitor", "monitores": "monitor", "pantalla": "monitor", "pantallas": "monitor",
    "escaner": "scanner", "escaneres": "scanner", "escanner": "scanner",
    "codigo": "barcode", "codigos": "barcode", "barra": "barcode", "barras": "barcode",
    "silla": "chair", "sillas": "chair", "escritorio": "desk", "escritorios": "desk", "mesa": "desk",
    "servidor": "server", "servidores": "server", "red": "network", "redes": "network",
    "bateria": "battery", "baterias": "battery", "litio": "lithium",
    "panel": "panel", "paneles": "panel", "solar": "solar", "solares": "solar",
    "impresora": "printer", "impresoras": "printer",
    "empaque": "packaging", "empaques": "packaging", "embalaje": "packaging",
}


def _stems(text: str) -> list:
    """Very small bilingual stemmer: laptops→laptop, monitores→monitor, etc."""
    out = []
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if len(word) > 3:
            for suffix in ("es", "s"):
                if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                    word = word[: -len(suffix)]
                    break
        out.append(_SYNONYMS.get(word, word))
    return out


def _match_local(query: str) -> Optional[dict]:
    qtokens = _stems(query)
    best, best_score = None, 0
    for p in B2B_CATALOG:
        htokens = _stems(p["name"])
        score = sum(1 for t in qtokens if any(
            t == h or (len(t) >= 4 and (t in h or h in t)) for h in htokens))
        if score > best_score:
            best, best_score = p, score
    if best and best_score > 0:
        return best
    # Last resort: fuzzy match on the whole string.
    names = [p["name"].lower() for p in B2B_CATALOG]
    hit = difflib.get_close_matches(query.lower(), names, n=1, cutoff=0.18)
    if hit:
        return next(p for p in B2B_CATALOG if p["name"].lower() == hit[0])
    return None


def _split_segments(objective: str) -> list[str]:
    parts = re.split(r",|;|\band\b|\by\b|\+", objective)
    return [p.strip() for p in parts if p and p.strip()]


_QTY_RE = re.compile(r"\b(\d{1,5})\s*(?:x|units?|pcs?|pieces?|unidades?|equipos?)?\b", re.I)


def _segment_qty(segment: str) -> tuple[int, str]:
    m = _QTY_RE.search(segment)
    if not m:
        return 1, segment
    qty = max(1, int(m.group(1)))
    cleaned = (segment[:m.start()] + segment[m.end():]).strip()
    return qty, cleaned or segment


class Channel3Provider:
    """Product discovery + stock via Channel3, local fallback otherwise."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 currency: Optional[str] = None, country: Optional[str] = None):
        self.api_key = api_key if api_key is not None else config.CHANNEL3_API_KEY
        self.base_url = (base_url or config.CHANNEL3_BASE_URL).rstrip("/")
        self.currency = currency or config.DEFAULT_CURRENCY
        self.country = country or config.DEFAULT_COUNTRY

    @property
    def live(self) -> bool:
        return bool(self.api_key)

    # -- Channel3 search -----------------------------------------------------
    def search(self, query: str, max_price: Optional[float] = None, limit: int = 5,
               user_id: str = "CUST_DEMO") -> Optional[list]:
        if not self.live:
            return None
        body = {
            "query": query,
            "limit": max(1, min(limit, 30)),
            "config": {"mode": config.CHANNEL3_MODE, "country": self.country,
                       "currency": self.currency},
        }
        if max_price:
            body["filters"] = {"price": {"max_price": float(max_price)}}
        try:
            r = requests.post(
                f"{self.base_url}/v1/search",
                json=body,
                headers={"x-api-key": self.api_key, "x-user-id": user_id},
                timeout=25,
            )
            r.raise_for_status()
            payload = r.json()
        except Exception:
            return None
        products = payload.get("products", payload.get("data", [])) or []
        return self._normalize(products)

    def _normalize(self, products: list) -> list:
        out = []
        for p in products:
            offers = p.get("offers") or []
            in_stock = [o for o in offers if o.get("availability", "InStock") != "OutOfStock"]
            offer = min(in_stock, key=lambda o: (o.get("price") or {}).get("price", 1e12)) if in_stock else None
            if not offer:
                continue
            price_obj = offer.get("price") or {}
            title = p.get("title") or p.get("name") or "Unnamed product"
            trade = infer_trade_attributes(title)
            out.append({
                "sku": p.get("id") or p.get("sku") or "",
                "product_id": p.get("id"),
                "name": title,
                "price": float(price_obj.get("price", 0) or 0),
                "currency": price_obj.get("currency", self.currency),
                "stock": 999 if offer.get("availability", "InStock") == "InStock" else 0,
                "supplier": offer.get("domain") or "Channel3 merchant",
                "origin": "CN",
                "url": offer.get("url"),
                "source": "channel3",
                **trade,
            })
        return out

    # -- High level: objective -> requested line items -----------------------
    def resolve(self, objective: str, max_price: Optional[float] = None,
                customer_id: str = "CUST_DEMO") -> list:
        """Turn a free-text B2B objective into items with qty and stock."""
        items = []
        for segment in _split_segments(objective) or [objective]:
            qty, query = _segment_qty(segment)
            candidates = self.search(query, max_price=max_price, user_id=customer_id)
            source = "channel3"
            if not candidates:
                local = _match_local(query)
                candidates = [local] if local else []
                source = "local"
            if not candidates:
                continue
            best = candidates[0]
            item = {
                "name": best["name"],
                "sku": best.get("sku", ""),
                "product_id": best.get("product_id"),
                "qty": qty,
                "unit_price": round(float(best["price"]), 2),
                "supplier": best.get("supplier", "unknown"),
                "origin": best.get("origin", "CN"),
                "hs_code": best.get("hs_code", "9999.99"),
                "duty_rate": float(best.get("duty_rate", 0.05)),
                "weight_kg": float(best.get("weight_kg", 2.0)),
                "category": best.get("category", "general"),
                "restricted": bool(best.get("restricted", False)),
                "stock": int(best.get("stock", 0)),
                "url": best.get("url"),
                "source": best.get("source", source),
            }
            items.append(item)
        return items


def product_catalog_snapshot() -> list:
    """Small snapshot used by the dashboard / chat prompt."""
    return [{"sku": p["sku"], "name": p["name"], "price": p["price"],
             "stock": p["stock"], "supplier": p["supplier"]} for p in B2B_CATALOG]
