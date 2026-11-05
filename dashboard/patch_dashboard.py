"""OPTIONAL (production only). Run from the project root after `npm run build`:
   python patch_dashboard.py   -> serves the React dashboard at /dashboard"""
from pathlib import Path
p = Path("api.py"); t = p.read_text(encoding="utf-8")
if "/dashboard" in t:
    print("already patched")
else:
    t += '''

from fastapi.staticfiles import StaticFiles
if (Path(__file__).parent / "dashboard" / "dist").exists():
    api.mount("/dashboard", StaticFiles(directory=str(Path(__file__).parent / "dashboard" / "dist"), html=True), name="dashboard")
'''
    p.write_text(t, encoding="utf-8"); print("api.py patched")
