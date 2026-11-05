"""Run once from the project root: python patch_api.py  (adds the chat router to api.py)"""
from pathlib import Path
p = Path("api.py"); t = p.read_text(encoding="utf-8")
if "make_router" in t:
    print("api.py already patched")
else:
    t += "\n\nfrom app.chat_api import make_router\napi.include_router(make_router(ORDERS, _guardar))\n"
    p.write_text(t, encoding="utf-8"); print("api.py patched")
