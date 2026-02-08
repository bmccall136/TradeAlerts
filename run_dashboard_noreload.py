@'
import os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

# Ensure import works no matter how Task Scheduler launches us
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Hard-disable Flask/Werkzeug debug + reloader
os.environ["FLASK_ENV"] = "production"
os.environ["FLASK_DEBUG"] = "0"

from dashboard import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
'@ | Set-Content -Path "C:\TradeAlerts\run_dashboard_noreload.py" -Encoding UTF8
