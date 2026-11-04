"""Imprime las tools reales del toolkit (nombres y esquemas) para verificar tu versión."""
from app.graph import _tools
for t in _tools:
    print("-", t.name, "|", (t.description or "")[:90])
