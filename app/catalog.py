"""Catálogo demo (reemplazable por scraping/API real)."""
import difflib

CATALOGO = [
    {"sku": "LAP-DELL-I7", "name": "Laptop Dell i7", "price": 450.00},
    {"sku": "PHN-PIXEL", "name": "Smartphone Pixel", "price": 320.00},
    {"sku": "HDP-NOISE", "name": "Audífonos Noise Cancelling", "price": 89.90},
    {"sku": "MON-4K", "name": "Monitor 4K 27 pulgadas", "price": 279.00},
    {"sku": "TV-OLED", "name": "TV OLED 65 pulgadas", "price": 1899.00},
]


def buscar(query: str):
    nombres = [p["name"].lower() for p in CATALOGO]
    m = difflib.get_close_matches(query.lower(), nombres, n=1, cutoff=0.2)
    if not m:
        return None
    return next(p for p in CATALOGO if p["name"].lower() == m[0])
