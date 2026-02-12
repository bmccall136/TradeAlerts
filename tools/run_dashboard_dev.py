import sys
from pathlib import Path

# Ensure project root (C:\TradeAlerts) is importable even when launched from tools\
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import importlib
from flask import Flask

m = importlib.import_module("dashboard")

app = None
for k, v in vars(m).items():
    if isinstance(v, Flask):
        app = v
        print("FOUND Flask app as:", k)
        break

if app is None:
    raise SystemExit("ERROR: No Flask app instance found in dashboard module globals.")

print("STARTING dev server on 0.0.0.0:5001")
app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False)
