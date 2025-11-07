# -*- coding: utf-8 -*-
"""
TradeAlerts – Dashboard (LIVE-focused)
- VALUE = Buying Power + Positions Value
- Realized P&L buckets read from live.db (realized_trades)
- All % = cumulative_gain / START_CASH
- Day/Week/LW/Month % = gain / total_cost
- Exclude GEVO; ET timezone; weeks are Mon–Fri; All since 2025-08-22
"""

from __future__ import annotations

import os
import sys
import json
import logging
import sqlite3
import threading
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Tuple

from flask import (
    Flask, jsonify, render_template, request, redirect, url_for, abort
)
from dotenv import load_dotenv

# ----- Ensure project root on sys.path -----
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ----- Third-party helpers -----
try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

# ===== Load .env and configure =====
load_dotenv()

# ===== Constants (single source of truth) =====
ET = ZoneInfo("America/New_York")

SIM_DB      = os.path.join(ROOT, "simulation.db")
BACKTEST_DB = os.path.join(ROOT, "backtest.db")
LIVE_DB     = os.environ.get("LIVE_DB", r"C:\TradeAlerts\live.db")

START_CASH     = float(os.environ.get("START_CASH", "392.67"))
ALL_START_ET   = date(2025, 8, 22)
IGNORED_TICKERS = {"GEVO"}

# OAuth helpers (prod)
OAUTH_HOST = "https://api.etrade.com"
REQUEST_TOKEN_URL = f"{OAUTH_HOST}/oauth/request_token"
ACCESS_TOKEN_URL  = f"{OAUTH_HOST}/oauth/access_token"
AUTHORIZE_URL     = "https://us.etrade.com/e/t/etws/authorize"

NEED_AUTH_FLAG = Path("need_oauth.flag")

# ===== Flask app =====
app = Flask(__name__)

# --- JSON helper (fixes NameError: always_json not defined) ---
from functools import wraps
from flask import jsonify

from functools import wraps
from flask import jsonify, current_app

from functools import wraps
from flask import jsonify

def always_json(f):
    @wraps(f)
    def _wrap(*args, **kwargs):
        try:
            out = f(*args, **kwargs)
            # If a view returns (dict|list), jsonify it.
            if isinstance(out, (dict, list)):
                return jsonify(out)
            return out
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    return _wrap

# ---- Navbar helpers for Jinja (hide links if endpoints don't exist) ----
from flask import current_app, url_for

@app.context_processor
def _inject_nav_flags():
    try:
        vfs = set(current_app.view_functions.keys())
    except Exception:
        vfs = set()

    has_sim = "simulation_view" in vfs
    has_back = "backtest_view" in vfs
    has_checkpoint = "run_checkpoint" in vfs

    # Prefer real endpoint if present; otherwise fall back to path
    auth_endpoint = None
    for cand in ("etrade_auth", "etrade_reconnect"):
        if cand in vfs:
            auth_endpoint = cand
            break
    try:
        auth_url = url_for(auth_endpoint) if auth_endpoint else "/etrade/auth"
    except Exception:
        auth_url = "/etrade/auth"

    try:
        checkpoint_url = url_for("run_checkpoint") if has_checkpoint else None
    except Exception:
        checkpoint_url = None

    return {
        "HAS_SIM": has_sim,
        "HAS_BACK": has_back,
        "HAS_CHECKPOINT": has_checkpoint,
        "AUTH_URL": auth_url,
        "CHECKPOINT_URL": checkpoint_url,
    }

# --- Jinja helpers so layout.html can know which endpoints exist ---
from flask import current_app

@app.context_processor
def _inject_endpoint_flags():
    try:
        vfs = set(current_app.view_functions.keys())
    except Exception:
        vfs = set()
    return {
        "HAS_SIM": "simulation_view" in vfs,
        "HAS_BACK": "backtest_view" in vfs,
    }

# ===== Logging (single setup) =====
def setup_logging(app: Flask) -> None:
    app.logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))
    if not any(isinstance(h, logging.StreamHandler) for h in app.logger.handlers):
        app.logger.addHandler(ch)

setup_logging(app)
log = app.logger

# ===== Service-layer imports (existing modules in your project) =====
# These must already exist in C:\TradeAlerts\services\
from services import etrade_service as et  # your canonical E*TRADE wrapper
from services.trade_source import load_trades_merged  # merged recent trades for the table

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None: return default
        return float(x)
    except Exception:
        return default

def _et_midnight(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time(), tzinfo=ET)

def _et_eod(d: date) -> datetime:
    return datetime.combine(d, datetime.max.time(), tzinfo=ET)

def _normalize_account(summ: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten/normalize account summary so UI logic is stable."""
    ui = summ.get("ui") or {}
    out = {
        "account_id":       summ.get("account_id") or ui.get("account_id"),
        "account_key":      summ.get("account_key") or ui.get("account_key"),
        "account_type":     summ.get("account_type") or ui.get("account_type"),
        "account_type_display": summ.get("account_type_display") or ui.get("account_type_display"),
        # We treat available_funds as 'Buying Power' for a cash account
        "available_funds":  _safe_float(ui.get("available_funds", ui.get("cashAvailableForInvestment", 0))),
    }
    return out

def _normalize_positions_payload(raw: Any) -> List[Dict[str, Any]]:
    """
    Accept E*TRADE positions payload and normalize to rows:
    {symbol, qty, price_paid, last_price}
    """
    rows: List[Dict[str, Any]] = []
    if not raw:
        return rows

    # Support both raw E*TRADE shape and already-normalized rows.
    if isinstance(raw, list) and raw and "symbol" in raw[0]:
        # already normalized
        for r in raw:
            rows.append({
                "symbol": str(r.get("symbol", "")).upper(),
                "qty":    _safe_float(r.get("qty"), 0.0),
                "price_paid": _safe_float(r.get("price_paid"), 0.0),
                "last_price": _safe_float(r.get("last_price"), 0.0),
                "open_time": r.get("open_time"),
            })
        return rows

    # Fallback: E*TRADE raw positions format
    try:
        positions = raw.get("PortfolioResponse", {}).get("AccountPortfolio", [])
        if isinstance(positions, dict):
            positions = [positions]
        for acct in positions:
            for pos in acct.get("Position", []):
                sym = str(pos.get("symbolDescription") or pos.get("symbol") or "").upper()
                qty = _safe_float(pos.get("quantity"), 0.0)
                # E*TRADE gives an average price
                paid = _safe_float(pos.get("pricePaid"), 0.0)
                last = _safe_float(
                    pos.get("Quick") and pos["Quick"].get("lastTrade") or
                    pos.get("All") and pos["All"].get("lastTrade") or
                    pos.get("lastTrade"), 0.0
                )
                rows.append({
                    "symbol": sym, "qty": qty, "price_paid": paid, "last_price": last, "open_time": None
                })
    except Exception as e:
        log.exception("normalize positions failed: %s", e)
    return rows

def _build_holdings_from_positions(pos_rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], float]:
    """
    Build holdings rows with 'value' and basic gains; return (rows, positions_value)
    Day gain requires a proper 'change' (last - prevClose); if missing we leave day_gain=0.
    """
    out: List[Dict[str, Any]] = []
    pv = 0.0
    for r in pos_rows:
        sym  = str(r.get("symbol", "")).upper()
        qty  = _safe_float(r.get("qty"), 0.0)
        paid = _safe_float(r.get("price_paid"), 0.0)
        last = _safe_float(r.get("last_price"), 0.0)
        value = round(qty * last, 2)
        pv += value

        total_gain = round((last - paid) * qty, 2) if qty else 0.0

        out.append({
            "symbol": sym,
            "qty": qty,
            "price_paid": round(paid, 4),
            "last_price": round(last, 4),
            "value": value,
            "total_gain": total_gain,
        })
    return out, round(pv, 2)

def compute_value_card(account_ui: Dict[str, Any], holdings_rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """Left KPI: VALUE = Buying Power + Positions Value (only those two rows)."""
    bp = _safe_float(account_ui.get("available_funds"), 0.0)
    pv = round(sum(_safe_float(h.get("value"), 0.0) for h in holdings_rows), 2)
    return {
        "buying_power": round(bp, 2),
        "positions_value": pv,
        "value": round(bp + pv, 2),
    }

def realized_buckets_from_live_db(db_path: str) -> Dict[str, Dict[str, float]]:
    """
    Read realized_trades and produce:
      {key: {"pnl": amt, "pct": percent}}
    Rules:
      - Day/Week/LW/Month: percent = sum(gain)/sum(total_cost) * 100
      - All:               percent = cumulative_gain/START_CASH * 100
      - Exclude GEVO
      - ET timezone; week is Mon–Fri; All since 2025-08-22
    """
    now = datetime.now(ET)

    def q_window(start: datetime, end: datetime) -> List[sqlite3.Row]:
        s = start.strftime("%Y-%m-%d %H:%M:%S")
        e = end.strftime("%Y-%m-%d %H:%M:%S")
        con = sqlite3.connect(db_path); con.row_factory = sqlite3.Row
        try:
            rows = con.execute("""
                SELECT symbol, gain, total_cost, close_date
                FROM realized_trades
                WHERE symbol != 'GEVO' AND close_date BETWEEN ? AND ?
            """, (s, e)).fetchall()
        finally:
            con.close()
        return rows

    def acc(rows: List[sqlite3.Row]) -> Tuple[float, float]:
        g = c = 0.0
        for r in rows:
            try: g += float(r["gain"] or 0.0)
            except: pass
            try: c += float(r["total_cost"] or 0.0)
            except: pass
        return g, c

    day_start  = _et_midnight(now.date())
    week_start = _et_midnight(now.date() - timedelta(days=now.weekday()))
    # last week Mon 00:00:00 .. Fri 23:59:59
    last_week_end = week_start - timedelta(microseconds=1)
    last_week_start = _et_midnight((last_week_end.date() - timedelta(days=last_week_end.weekday())))
    month_start = _et_midnight(now.replace(day=1).date())
    all_start   = _et_midnight(ALL_START_ET)

    windows = {
        "day":       (day_start, now),
        "week":      (week_start, now),
        "last_week": (last_week_start, _et_eod(last_week_start.date() + timedelta(days=4))),
        "month":     (month_start, now),
        "all":       (all_start, now),
    }

    out: Dict[str, Dict[str, float]] = {}
    for key, (ws, we) in windows.items():
        rows = q_window(ws, we)
        g, c = acc(rows)
        if key == "all":
            pct = (g / START_CASH * 100.0) if START_CASH > 0 else 0.0
        else:
            pct = (g / c * 100.0) if c > 0 else 0.0
        out[key] = {"pnl": round(g, 2), "pct": round(pct, 2)}
    return out

# -----------------------------------------------------------------------------
# E*TRADE reconnect helpers
# -----------------------------------------------------------------------------

def _etrade_log_wrap() -> None:
    """
    Mark need_oauth.flag if the last E*TRADE call indicated expired tokens.
    Your etrade_service should set a sticky flag or raise on 401/403.
    """
    try:
        if getattr(et, "need_oauth", False):
            NEED_AUTH_FLAG.write_text("1", encoding="utf-8")
        else:
            if NEED_AUTH_FLAG.exists():
                NEED_AUTH_FLAG.unlink(missing_ok=True)  # py3.8+: ignore if missing
    except Exception:
        pass

@app.route("/auth/etrade/launch")
@always_json
def etrade_auth_launch():
    try:
        import auth_shortcut as _auth
        ok, err = _auth.launch()
        return {"ok": ok, "error": err}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.route("/auth/etrade/reconnect", methods=["GET"])
def etrade_reconnect():
    """
    Convenience: launch your auth_shortcut.py in a new console for the PIN flow.
    """
    try:
        exe = sys.executable
        script = os.path.join(ROOT, "auth_shortcut.py")
        if os.name == "nt":
            # New console on Windows
            os.spawnl(os.P_NOWAIT, exe, exe, "-u", script)
        else:
            threading.Thread(target=lambda: os.system(f"{exe} -u {script} &")).start()
        return jsonify({"ok": True})
    except Exception as e:
        log.exception("reconnect failed: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500

# --- Checkpoint trigger (kept simple; returns ok:true) ---
import os, subprocess, pathlib

CHECKPOINT_BAT = r"C:\TradeAlerts\checkpoint.bat"  # must exist

@app.route("/checkpoint", methods=["GET"])
@always_json
def run_checkpoint():
    try:
        if not os.path.exists(CHECKPOINT_BAT):
            return {"ok": False, "error": f"Missing {CHECKPOINT_BAT}"}, 404
        # Launch without blocking the Flask thread
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", CHECKPOINT_BAT],
            cwd=str(pathlib.Path(CHECKPOINT_BAT).parent),
            creationflags=0x00000008  # CREATE_NEW_CONSOLE
        )
        return {"ok": True, "launched": CHECKPOINT_BAT}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@app.route("/")
def index():
    return redirect(url_for("live_view"))

@app.route("/live")
def live_view():
    """
    Server-render first paint. JS will immediately call /live/status to fill the tiles.
    """
    try:
        _etrade_log_wrap()
        acct_summary = et.get_account_summary() or {}
        account = _normalize_account(acct_summary)
        raw_positions = et.get_positions() or {}
        pos_rows = _normalize_positions_payload(raw_positions)
        holdings, _ = _build_holdings_from_positions(pos_rows)
    except Exception as e:
        log.exception("live_view error: %s", e)
        account, holdings = {}, []

    return render_template("live.html", account=account, holdings=holdings)

@app.route("/live/status")
def live_status():
    """
    Returns the JSON the Live UI expects.
    """
    try:
        _etrade_log_wrap()

        # ---------- Account & positions ----------
        acct_summary = et.get_account_summary() or {}
        account = _normalize_account(acct_summary)

        raw_positions = et.get_positions() or {}
        pos_rows = _normalize_positions_payload(raw_positions)
        holdings, positions_value = _build_holdings_from_positions(pos_rows)

        # ---------- KPI: VALUE ----------
        value_obj = compute_value_card(account, holdings)

        # ---------- KPI: REALIZED ----------
        realized_obj = realized_buckets_from_live_db(LIVE_DB)

        # ---------- Trades (table) ----------
        start = request.args.get("start", "").strip()
        days = request.args.get("days", type=int)
        max_count = request.args.get("max", default=5000, type=int)

        trades = load_trades_merged(days=days, start_iso=start, max_count=max_count) or []

        needs_reconnect = NEED_AUTH_FLAG.exists()

        payload = {
            "ok": True,
            "account": account,
            "value": value_obj,
            "realized": realized_obj,
            "holdings": holdings,
            "trades": trades,
            "needs_reconnect": needs_reconnect,
        }
        return jsonify(payload), 200

    except Exception as e:
        log.exception("live_status error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # Bind on all interfaces; debug on for dev
    app.run(host="0.0.0.0", port=5000, debug=True)
