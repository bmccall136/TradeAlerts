# -*- coding: utf-8 -*-
"""
TradeAlerts – LIVE Dashboard

- VALUE = Buying Power + Positions Value
- Holdings & account info from services.etrade_service
- Realized P&L buckets read from live.db (realized_trades)
- All % = cumulative_gain / LIVE_APP_STARTING_EQUITY
- Day/Week/LW/Month % = gain / total_cost
- Exclude GEVO
- ET timezone; weeks are Mon–Fri
- "All" window since 2025-08-22

This file exposes:
- /live        : HTML shell
- /live/status : JSON the Live UI expects
- /auth/etrade/reconnect, /checkpoint helpers
"""
# services
from __future__ import annotations
from services import etrade_service as et
from services.trade_source import load_trades_merged
import os
import sys
import logging
import sqlite3
import threading
import subprocess
import pathlib
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Tuple
from services import etrade_service as et
from services.trade_source import load_trades_merged
from flask import Flask, render_template, jsonify, request, redirect, url_for
import logging, os

log = logging.getLogger(__name__)

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    redirect,
    url_for,
    current_app,
)
from dotenv import load_dotenv

# -----------------------------------------------------------------------------#
# Path / env setup
# -----------------------------------------------------------------------------#

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

load_dotenv()

try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

LIVE_DB = os.environ.get("LIVE_DB", r"C:\TradeAlerts\live.db")

ALL_START_DATE = date(2025, 8, 22)
LIVE_APP_STARTING_EQUITY = 367.76  # your original starting amount
IGNORED_TICKERS = {"GEVO"}

# --- DB paths ---
SIM_DB = os.path.join(ROOT, "simulation.db")
BACKTEST_DB = os.path.join(ROOT, "backtest.db")
LIVE_DB = os.environ.get("LIVE_DB", os.path.join(ROOT, "live.db"))

# --- Live tracking config ---
PROJECT_START_DATE = date(2025, 8, 22)
LIVE_APP_STARTING_EQUITY = 367.76
START_CASH = LIVE_APP_STARTING_EQUITY  # used for "All" realized %

IGNORED_TICKERS = {"GEVO"}

# --- Auth / reconnect flags ---
NEED_AUTH_FLAG = Path("need_oauth.flag")

# --- Checkpoint script ---
CHECKPOINT_BAT = r"C:\TradeAlerts\checkpoint.bat"  # adjust if needed

# -----------------------------------------------------------------------------#
# Flask app + logging
# -----------------------------------------------------------------------------#

app = Flask(__name__)


def setup_logging(app: Flask) -> None:
    app.logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    if not any(isinstance(h, logging.StreamHandler) for h in app.logger.handlers):
        app.logger.addHandler(ch)


setup_logging(app)
log = app.logger

# -----------------------------------------------------------------------------#
# Import service layer
# -----------------------------------------------------------------------------#

from services import etrade_service as et  # canonical E*TRADE wrapper

try:
    from services.trade_source import load_trades_merged
except ImportError:
    def load_trades_merged(
        days: int | None = None,
        start_iso: str | None = None,
        max_count: int = 5000,
    ):
        return []

# -----------------------------------------------------------------------------#
# Helpers
# -----------------------------------------------------------------------------#


def always_json(f):
    """Decorator: make view always return JSON + catch exceptions."""
    from functools import wraps

    @wraps(f)
    def _wrap(*args, **kwargs):
        try:
            out = f(*args, **kwargs)
            if isinstance(out, (dict, list)):
                return jsonify(out)
            return out
        except Exception as e:
            log.exception("always_json wrapped error: %s", e)
            return jsonify({"ok": False, "error": str(e)}), 500

    return _wrap


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _et_midnight(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time(), tzinfo=ET)


def _et_eod(d: date) -> datetime:
    return datetime.combine(d, datetime.max.time(), tzinfo=ET)

def _normalize_account(summ: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten/normalize account summary so UI logic is stable.
    Expected to receive whatever et.get_account_summary() returns.
    We try multiple possible keys for NAV & buying power.
    """
    ui = summ.get("ui") or {}

    # Buying power / available funds
    bp = _safe_float(
        summ.get("buying_power")
        or summ.get("available_funds")
        or ui.get("available_funds")
        or ui.get("cashAvailableForInvestment")
        or ui.get("marginBuyingPower")
        or ui.get("cashBuyingPower")
        or 0.0
    )

    # Net Account Value (NAV)
    nav = _safe_float(
        summ.get("nav")
        or summ.get("net_account_value")
        or ui.get("netAccountValue")
        or ui.get("net_account_value")
        or 0.0
    )

    return {
        "account_id":            summ.get("account_id") or ui.get("account_id"),
        "account_key":           summ.get("account_key") or ui.get("account_key"),
        "account_type":          summ.get("account_type") or ui.get("account_type"),
        "account_type_display":  summ.get("account_type_display") or ui.get("account_type_display"),
        "available_funds":       bp,
        "nav":                   nav,
    }

def compute_value_card(account_ui: Dict[str, Any],
                       holdings_rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    VALUE tile logic:

    - If NAV present: use it directly as 'value'.
      Positions Value = sum of holdings
      Buying Power:
         - prefer E*TRADE cash/BP if provided
         - otherwise NAV - PositionsValue (>= 0)
    - If NAV missing: fall back to BP + PositionsValue.
    """
    positions_value = round(
        sum(_safe_float(h.get("value"), 0.0) for h in holdings_rows), 2
    )

    nav = _safe_float(
        account_ui.get("nav")
        or account_ui.get("net_account_value")
        or account_ui.get("NetAccountValue"),
        0.0,
    )

    explicit_bp = _safe_float(
        account_ui.get("available_funds")
        or account_ui.get("cashPurchasingPower")
        or account_ui.get("cash_available_for_investment")
        or account_ui.get("buying_power"),
        0.0,
    )

    if nav > 0:
        buying_power = explicit_bp if explicit_bp > 0 else max(0.0, nav - positions_value)
        value = nav
    else:
        # fallback: old behavior
        buying_power = explicit_bp
        value = buying_power + positions_value

    return {
        "buying_power": round(buying_power, 2),
        "positions_value": round(positions_value, 2),
        "value": round(value, 2),
    }


def realized_buckets_from_live_db(db_path: str) -> Dict[str, Dict[str, float]]:
    """
    Read realized_trades and produce:
      {key: {"pnl": amt, "pct": percent}}

    Rules:
      - Day/Week/LW/Month pct = gain / total_cost * 100
      - All pct = cumulative_gain / LIVE_APP_STARTING_EQUITY * 100
      - Exclude GEVO
      - ET timezone; week is Mon–Fri; All since ALL_START_DATE
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
                WHERE symbol NOT IN ({})
                  AND close_date BETWEEN ? AND ?
            """.format(",".join("?" * len(IGNORED_TICKERS))),
            tuple(IGNORED_TICKERS) + (s, e)
            ).fetchall()
        finally:
            con.close()
        return rows

    def acc(rows: List[sqlite3.Row]) -> Tuple[float, float]:
        g = c = 0.0
        for r in rows:
            g += _safe_float(r["gain"], 0.0)
            c += _safe_float(r["total_cost"], 0.0)
        return g, c

    day_start   = _et_midnight(now.date())
    week_start  = _et_midnight(now.date() - timedelta(days=now.weekday()))
    last_week_end = week_start - timedelta(microseconds=1)
    last_week_start = _et_midnight(
        last_week_end.date() - timedelta(days=last_week_end.weekday())
    )
    month_start = _et_midnight(now.replace(day=1).date())
    all_start   = _et_midnight(ALL_START_DATE)

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
            base = LIVE_APP_STARTING_EQUITY
            pct = (g / base * 100.0) if base > 0 else 0.0
        else:
            pct = (g / c * 100.0) if c > 0 else 0.0

        out[key] = {"pnl": round(g, 2), "pct": round(pct, 2)}

    return out

def _normalize_positions_payload(raw: Any) -> List[Dict[str, Any]]:
    """
    Normalize E*TRADE positions into:
        {symbol, qty, price_paid, last_price}
    Accepts either:
      - already-normalized rows, or
      - raw E*TRADE portfolio JSON.
    """
    rows: List[Dict[str, Any]] = []
    if not raw:
        return rows

    # Already normalized?
    if (
        isinstance(raw, list)
        and raw
        and isinstance(raw[0], dict)
        and "symbol" in raw[0]
    ):
        for r in raw:
            rows.append(
                {
                    "symbol": str(r.get("symbol", "")).upper(),
                    "qty": _safe_float(r.get("qty"), 0.0),
                    "price_paid": _safe_float(r.get("price_paid"), 0.0),
                    "last_price": _safe_float(r.get("last_price"), 0.0),
                }
            )
        return rows

    # Raw E*TRADE shape
    try:
        pr = raw.get("PortfolioResponse", {}).get("AccountPortfolio", [])
        if isinstance(pr, dict):
            pr = [pr]
        for acct in pr:
            for pos in acct.get("Position", []):
                sym = str(
                    pos.get("symbolDescription")
                    or pos.get("symbol")
                    or ""
                ).upper()
                if not sym:
                    continue

                qty = _safe_float(pos.get("quantity"), 0.0)
                paid = _safe_float(
                    pos.get("pricePaid")
                    or pos.get("costPerShare")
                    or pos.get("averagePrice")
                    or 0.0
                )
                last = _safe_float(
                    (pos.get("Quick") or {}).get("lastTrade")
                    or (pos.get("All") or {}).get("lastTrade")
                    or pos.get("lastTrade")
                    or 0.0
                )
                rows.append(
                    {
                        "symbol": sym,
                        "qty": qty,
                        "price_paid": paid,
                        "last_price": last,
                    }
                )
    except Exception as e:
        log.exception("normalize positions failed: %s", e)

    return rows


def _build_holdings_from_positions(
    pos_rows: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], float]:
    """
    From normalized positions rows, compute holdings rows with:
      symbol, qty, price_paid, last_price, value,
      day_pl, day_pl_pct, total_pl, total_pl_pct.

    Returns (holdings, positions_value).
    """
    holdings: List[Dict[str, Any]] = []
    positions_value = 0.0

    for r in pos_rows:
        sym = str(r.get("symbol", "")).upper()
        if not sym or sym in IGNORED_TICKERS:
            continue

        qty = _safe_float(r.get("qty"), 0.0)
        paid = _safe_float(r.get("price_paid"), 0.0)
        last = _safe_float(r.get("last_price"), 0.0)

        value = round(qty * last, 2)
        positions_value += value

        cost = qty * paid
        total_pl = round(value - cost, 2) if qty else 0.0
        total_pl_pct = round((total_pl / cost) * 100.0, 2) if cost > 0 else 0.0

        # day_pl are 0 unless you wire in prevClose; keep placeholders.
        day_pl = 0.0
        day_pl_pct = 0.0

        holdings.append(
            {
                "symbol": sym,
                "qty": qty,
                "price_paid": round(paid, 4),
                "last_price": round(last, 4),
                "value": value,
                "day_pl": day_pl,
                "day_pl_pct": day_pl_pct,
                "total_pl": total_pl,
                "total_pl_pct": total_pl_pct,
            }
        )

    return holdings, round(positions_value, 2)



# -----------------------------------------------------------------------------#


def _etrade_log_wrap() -> None:
    """Sync NEED_AUTH_FLAG with et.need_oauth if the wrapper exposes it."""
    try:
        if getattr(et, "need_oauth", False):
            NEED_AUTH_FLAG.write_text("1", encoding="utf-8")
        else:
            if NEED_AUTH_FLAG.exists():
                NEED_AUTH_FLAG.unlink(missing_ok=True)
    except Exception:
        pass


@app.route("/auth/etrade/reconnect", methods=["GET"])
def etrade_reconnect():
    """
    Launch auth_shortcut.py in a new console so user can complete PIN flow.
    """
    try:
        exe = sys.executable
        script = os.path.join(ROOT, "auth_shortcut.py")
        if not os.path.exists(script):
            return jsonify({"ok": False, "error": "auth_shortcut.py not found"}), 404

        if os.name == "nt":
            # Windows: spawn new console
            subprocess.Popen(
                [exe, "-u", script],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                cwd=ROOT,
            )
        else:
            # *nix: background thread
            threading.Thread(
                target=lambda: os.system(f"{exe} -u {script} &"),
                daemon=True,
            ).start()

        return jsonify({"ok": True})
    except Exception as e:
        log.exception("etrade_reconnect failed: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500

# -----------------------------------------------------------------------------#
# Checkpoint trigger
# -----------------------------------------------------------------------------#


@app.route("/checkpoint", methods=["GET"])
@always_json
def run_checkpoint():
    try:
        if not os.path.exists(CHECKPOINT_BAT):
            return {"ok": False, "error": f"Missing {CHECKPOINT_BAT}"}
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", CHECKPOINT_BAT],
            cwd=str(pathlib.Path(CHECKPOINT_BAT).parent),
            creationflags=0x00000008,  # CREATE_NEW_CONSOLE
        )
        return {"ok": True, "launched": CHECKPOINT_BAT}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# -----------------------------------------------------------------------------#
# Jinja / navbar helpers
# -----------------------------------------------------------------------------#


@app.context_processor
def _inject_nav_flags():
    try:
        vfs = set(current_app.view_functions.keys())
    except Exception:
        vfs = set()

    has_sim = "simulation_view" in vfs
    has_back = "backtest_view" in vfs
    has_checkpoint = "run_checkpoint" in vfs

    # Auth URL: prefer reconnect endpoint
    try:
        auth_url = url_for("etrade_reconnect")
    except Exception:
        auth_url = "/auth/etrade/reconnect"

    checkpoint_url = None
    if has_checkpoint:
        try:
            checkpoint_url = url_for("run_checkpoint")
        except Exception:
            checkpoint_url = "/checkpoint"

    return {
        "HAS_SIM": has_sim,
        "HAS_BACK": has_back,
        "HAS_CHECKPOINT": has_checkpoint,
        "AUTH_URL": auth_url,
        "CHECKPOINT_URL": checkpoint_url,
    }

# -----------------------------------------------------------------------------#
# Routes
# -----------------------------------------------------------------------------#


@app.route("/")
def index():
    return redirect(url_for("live_view"))


@app.route("/live")
def live_view():
    """
    Initial HTML shell. JS immediately calls /live/status.
    Tolerant of upstream errors.
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
@always_json
def live_status():
    """
    Returns the JSON the Live UI expects.

    Query params:
      - start=YYYY-MM-DD  : earliest trade date (for table)
      - days=N            : fallback lookback window
      - debug=1           : include raw E*TRADE payloads
    """
    from flask import request, current_app
    from services import etrade_service as et
    from services.trade_source import load_trades_merged

    debug = request.args.get("debug", "0") == "1"

    # --------------------------------------------------
    # 1) ACCOUNT SUMMARY (RAW FROM E*TRADE)
    # --------------------------------------------------
    acct_summary_raw = {}
    etrade_ok = False
    debug_raw = {}

    try:
        # This is your canonical wrapper: do NOT pass debug kwarg.
        acct_summary_raw = et.get_account_summary() or {}
        etrade_ok = True
    except Exception as e:
        current_app.logger.exception("account summary error: %s", e)

    # Fall back so we can always index into something
    raw_ui = acct_summary_raw.get("raw") or acct_summary_raw or {}

    comp = (raw_ui.get("Computed") or {})
    # Buying Power: tie directly to E*TRADE cashBuyingPower
    cash_bp = _safe_float(
        comp.get("cashBuyingPower",
                 comp.get("cashAvailableForInvestment", 0.0))
    )

    # Cash balance candidates for NAV calc
    cash_bal = _safe_float(
        comp.get("cashBalance",
                 comp.get("settledCashForInvestment",
                          comp.get("netCash", 0.0)))
    )

    # --------------------------------------------------
    # 2) POSITIONS -> HOLDINGS + POSITIONS VALUE
    # --------------------------------------------------
    holdings = []
    positions_value = 0.0

    try:
        raw_positions = et.get_positions() or {}
        if debug:
            debug_raw["positions_raw"] = raw_positions
        pos_rows = _normalize_positions_payload(raw_positions)
        holdings, positions_value = _build_holdings_from_positions(pos_rows)
    except Exception as e:
        current_app.logger.exception("positions error: %s", e)

    positions_value = _safe_float(positions_value)

    # --------------------------------------------------
    # 3) NAV: PULL / DERIVE FROM RAW E*TRADE
    # --------------------------------------------------
    # Prefer explicit values if E*TRADE gives them.
    api_nav = 0.0
    if "netAccountValue" in comp:
        api_nav = _safe_float(comp.get("netAccountValue", 0.0))
    elif "accountBalance" in comp:
        api_nav = _safe_float(comp.get("accountBalance", 0.0))

    # If those are zero/absent, derive:
    # for a cash account NAV ≈ cash_balance + positions_value
    if not api_nav:
        api_nav = cash_bal + positions_value

    nav = round(api_nav, 2)
    bp = round(cash_bp, 2)
    pv = round(positions_value, 2)

    # --------------------------------------------------
    # 4) NORMALIZED ACCOUNT OBJECT (WHAT UI READS)
    # --------------------------------------------------
    account = {
        "account_id": acct_summary_raw.get("account_id")
                      or raw_ui.get("accountId"),
        "account_key": acct_summary_raw.get("account_key")
                       or raw_ui.get("accountIdKey")
                       or acct_summary_raw.get("account_key"),
        "account_type": acct_summary_raw.get("account_type")
                        or raw_ui.get("accountType"),
        "account_type_display": acct_summary_raw.get("account_type_display")
                                or raw_ui.get("accountMode"),
        # Expose these two exactly how we want UI to use them:
        "available_funds": bp,   # Buying power
        "nav": nav,              # Net Account Value
    }

    if debug:
        debug_raw["acct_summary_raw"] = acct_summary_raw

    # --------------------------------------------------
    # 5) UNREALIZED P&L (FROM HOLDINGS ONLY)
    # --------------------------------------------------
    total_cost = 0.0
    for h in holdings:
        qty = _safe_float(h.get("qty"), 0.0)
        paid = _safe_float(h.get("price_paid"), 0.0)
        total_cost += qty * paid

    unrealized_pnl = round(pv - total_cost, 2)
    unrealized_pnl_pct = round(
        (unrealized_pnl / total_cost * 100.0), 2
    ) if total_cost > 0 else 0.0

    # --------------------------------------------------
    # 6) REALIZED BUCKETS (FROM live.db)
    # --------------------------------------------------
    realized_obj = realized_buckets_from_live_db(LIVE_DB)

    # --------------------------------------------------
    # 7) TRADES TABLE
    # --------------------------------------------------
    start = request.args.get("start", "").strip()
    days = request.args.get("days", type=int)
    max_count = request.args.get("max", default=5000, type=int)

    trades = load_trades_merged(
        days=days,
        start_iso=start,
        max_count=max_count
    ) or []

    # --------------------------------------------------
    # 8) ABOUT / SINCE STATS
    # --------------------------------------------------
    # Using your original starting equity
    START_CASH = 367.76
    START_DATE = "2025-08-22"

    all_bucket = realized_obj.get("all", {}) if isinstance(realized_obj, dict) else {}
    since_pnl = _safe_float(all_bucket.get("pnl", 0.0))
    since_pct = round(
        (since_pnl / START_CASH * 100.0), 2
    ) if START_CASH > 0 else 0.0

    about = {
        "start_cash": START_CASH,
        "start_date": START_DATE,
        "since_pnl": round(since_pnl, 2),
        "since_pct": since_pct,
    }

    # --------------------------------------------------
    # 9) METRICS / VALUE CARD PAYLOAD
    # --------------------------------------------------
    metrics = {
        "buying_power": bp,
        "net_account_value": nav,
        "positions_value": pv,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_pct": unrealized_pnl_pct,
        "realized_buckets": realized_obj,
    }

    value_obj = {
        "buying_power": bp,
        "positions_value": pv,
        "net_account_value": nav,
        # For the big left tile, treat NAV as "value"
        "value": nav,
    }

    # --------------------------------------------------
    # 10) TOTAL GAIN SINCE PROJECT START (BASED ON NAV)
    # --------------------------------------------------
    START_CASH = 367.76
    START_DATE = "2025-08-22"

    total_gain = round(nav - START_CASH, 2)
    total_gain_pct = round((total_gain / START_CASH * 100.0), 2) if START_CASH > 0 else 0.0

    metrics["total_gain_nav"] = total_gain
    metrics["total_gain_nav_pct"] = total_gain_pct

    needs_reconnect = bool(
        getattr(et, "need_oauth", False)
        or os.path.exists(str(NEED_AUTH_FLAG))
    )

    payload = {
        "ok": True,
        "etrade_ok": etrade_ok,
        "needs_reconnect": needs_reconnect,
        "account": account,
        "value": value_obj,
        "metrics": metrics,
        "holdings": holdings,
        "realized": realized_obj,
        "trades": trades,
        "about": about,
    }

    if debug:
        payload["debug_raw"] = debug_raw

    return payload

# -----------------------------------------------------------------------------#
# Entrypoint
# -----------------------------------------------------------------------------#

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
