
from flask import Flask, render_template, redirect, url_for, jsonify
from datetime import datetime, timezone
from static_bp import static_bp  # serves /static/<asset> via style.css, etc.

app = Flask(__name__)
app.register_blueprint(static_bp)

# --- Routes ------------------------------------------------------------------

@app.route("/")
def index():
    # Go straight to the live view
    return redirect(url_for("live_view"))

@app.route("/view")
@app.route("/live")
def live_view():
    """Render the Live dashboard shell (JS will populate via /live/status)."""
    # We pass the bare minimum; the template is resilient and will fetch JSON.
    return render_template("live.html")

@app.route("/live/status")
def live_status():
    """Return minimal JSON so the Live page paints even with no data."""
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    payload = {
        "ok": True,
        "ts": now,
        "live": {
            "buying_power": 0.0,
            "positions_value": 0.0,
            "equity_value": 0.0,
            "account": "—",
            "account_type": "Cash",
        },
        "pnl": {
            "unrealized": 0.0,
            "unrealized_pct": 0.0,
        },
        "realized": {
            "day": 0.0, "day_pct": 0.0,
            "week": 0.0, "week_pct": 0.0,
            "last_week": 0.0, "last_week_pct": 0.0,
            "month": 0.0, "month_pct": 0.0,
            "all": 0.0, "all_pct": 0.0,
        },
        "holdings": [],
        "trades": [],
        "market_window": "OPEN",
    }
    return jsonify(payload)

# --- Main --------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
