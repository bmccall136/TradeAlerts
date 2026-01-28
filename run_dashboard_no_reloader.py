# run_dashboard_no_reloader.py
import os

# Import your Flask app module
import dashboard

if __name__ == "__main__":
    app = getattr(dashboard, "app", None)
    if app is None:
        raise SystemExit("ERROR: dashboard.app not found")

    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("DASHBOARD_PORT", "5000"))

    # Critical: no reloader, no debug (scheduler-safe)
    app.run(host=host, port=port, debug=False, use_reloader=False)
