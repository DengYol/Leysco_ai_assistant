"""
debug_import.py  —  run this FIRST to find the real import error.

    python app/debug_import.py

This prints the full traceback so you can see exactly what is broken.
"""
import sys, os

_APP_DIR  = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_APP_DIR)
for _p in (_ROOT_DIR, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

print("sys.path[0:4]:", sys.path[:4])
print()

# ── Try every possible import form ────────────────────────────────────────────
import traceback

for mod in ("app.action_router", "action_router"):
    print(f"Trying:  import {mod}")
    try:
        import importlib
        m = importlib.import_module(mod)
        print(f"  ✓  SUCCESS  →  {m}")
        print(f"  ActionRouter = {getattr(m, 'ActionRouter', 'NOT FOUND')}")
        break
    except Exception:
        print(f"  ✗  FAILED:")
        traceback.print_exc()
    print()