# -*- coding: utf-8 -*-
"""
TradeAlerts â€“ LIVE Dashboard

- VALUE = Buying Power + Positions Value
- Holdings & account info from services.etrade_service
- Realized P&L buckets read from live.db (realized_trades)
- All % = cumulative_gain / LIVE_APP_STARTING_EQUITY
- Day/Week/LW/Month % = gain / total_cost
- Exclude GEVO
- ET timezone; weeks are Monâ€“Fri
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
from flask import Flask, render_template, jsonify, request, redirect, url_forfrom services.contributions import get_total_contributions
from services.event_log import log_event


import logging, os
from datetime import datetime
from zoneinfo import ZoneInfo
from services import live_guardrails as gr

# live guardrails holds opened_at for live trades
try:
    from services import live_guardrails as gr
except ImportError:
    gr = None  # if not available, we'll just show "â€”"

ETZ = ZoneInfo("America/New_York")

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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LIVE_MODE_FILE = os.path.join(os.path.dirname(__file__), "live_mode.txt")
VALID_LIVE_MODES = {"DAY", "SWING"}
ALL_START_DATE = date(2025, 8, 22)
LIVE_APP_STARTING_EQUITY =  392.67  # your original starting amount
IGNORED_TICKERS = {"GEVO"}

# --- DB paths ---
LIVE_DB = os.environ.get("LIVE_DB", os.path.join(ROOT, "live.db"))

# --- Live tracking config ---
PROJECT_START_DATE = date(2025, 8, 22)
LIVE_APP_STARTING_EQUITY =  392.67
START_CASH = LIVE_APP_STARTING_EQUITY  # used for "All" realized %

IGNORED_TICKERS = {"GEVO"}

# --- Auth / reconnect flags ---
NEED_AUTH_FLAG = Path("need_oauth.flag")

# --- Checkpoint script ---
CHECKPOINT_BAT = r"C:\TradeAlerts\checkpoint.bat"  # adjust if needed

# -----------------------------------------------------------------------------#
# Flask app + logging
# -----------------------------------------------------------------------------#

# --- Live baseline config (Money Machine) ---
START_CASH_BASELINE  = 392.67   # 8/22/2025 confirmed baseline NAV start
START_DATE_BASELINE  = "2025-08-22"

app = Flask(__name__)

import os

# --- E*TRADE reconnect flag (need_oauth.flag) ---
FLAG_FILE = os.path.join(os.path.dirname(__file__), "need_oauth.flag")


def read_flag_file() -> bool:
    """
    Returns True if the reconnect flag file exists, False otherwise.
    Safe fallback if anything weird happens.
    """
    try:
        return os.path.exists(FLAG_FILE)
    except Exception:
        return False

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
import datetime as _dt

try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _ET = _ZoneInfo("America/New_York")
except Exception:
    _ET = _dt.timezone(_dt.timedelta(hours=-5))  # crude ET fallback

def _read_live_mode() -> str:
    """Return current live mode: 'DAY' or 'SWING'."""
    try:
        with open(LIVE_MODE_FILE, "r", encoding="utf-8") as f:
            value = f.read().strip().upper()
            if value in VALID_LIVE_MODES:
                return value
    except FileNotFoundError:
        pass
    return LIVE_MODE_DEFAULT


def _write_live_mode(mode: str) -> str:
    """Persist live mode to disk and return normalized value."""
    mode = (mode or "").upper()
    if mode not in VALID_LIVE_MODES:
        raise ValueError(f"Invalid live mode: {mode!r}")
    with open(LIVE_MODE_FILE, "w", encoding="utf-8") as f:
        f.write(mode)
    return mode

def _realized_buckets_from_trades(trades):
    """
    Build Day / Week / Last Week / Month / All realized P&L buckets
    directly from the trades list returned by E*TRADE.

    BUCKET RULES (all in ET):
      - Day:        close_date == today
      - Week:       this Monday .. today
      - Last Week:  previous Monday .. previous Sunday
      - Month:      first of this month .. today
      - All:        2025-08-22 .. today

    Amount  = sum of pl
    Percent = Amount / total cost basis of those sells (price_paid * qty).
    """
    today = _dt.datetime.now(_ET).date()
    this_monday = today - _dt.timedelta(days=today.weekday())
    last_monday = this_monday - _dt.timedelta(days=7)
    last_sunday = this_monday - _dt.timedelta(days=1)
    month_start = today.replace(day=1)
    start_all = _dt.date(2025, 8, 22)

    buckets = {
        "day": {"pnl": 0.0, "cost": 0.0},
        "week": {"pnl": 0.0, "cost": 0.0},
        "last_week": {"pnl": 0.0, "cost": 0.0},
        "month": {"pnl": 0.0, "cost": 0.0},
        "all": {"pnl": 0.0, "cost": 0.0},
    }

    for t in trades:
        if t.get("action") != "SELL":
            continue
        pl = t.get("pl")
        if pl is None:
            continue

        qty = t.get("qty") or 0.0
        price_paid = t.get("price_paid") or 0.0
        cost = float(qty) * float(price_paid)

        # Parse trade time (prefer time_utc)
        ts = t.get("time_utc") or t.get("time")
        d = None
        if ts:
            try:
                dt = _dt.datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_ET)
                d = dt.astimezone(_ET).date()
            except Exception:
                try:
                    dt = _dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    d = dt.date()
                except Exception:
                    d = today  # worst-case fallback

        if d is None:
            continue

        # All (since start date)
        if d >= start_all:
            buckets["all"]["pnl"] += pl
            buckets["all"]["cost"] += cost

        # Today
        if d == today:
            buckets["day"]["pnl"] += pl
            buckets["day"]["cost"] += cost

        # This week (Mon..today)
        if this_monday <= d <= today:
            buckets["week"]["pnl"] += pl
            buckets["week"]["cost"] += cost

        # Last week (previous Mon..Sun)
        if last_monday <= d <= last_sunday:
            buckets["last_week"]["pnl"] += pl
            buckets["last_week"]["cost"] += cost

        # This month
        if d >= month_start:
            buckets["month"]["pnl"] += pl
            buckets["month"]["cost"] += cost

    def _finish(b):
        pnl = round(float(b["pnl"]), 2)
        cost = float(b["cost"])
        pct = round((pnl / cost) * 100.0, 2) if cost > 0 else 0.0
        return {"pnl": pnl, "pct": pct}

    return {
        "day": _finish(buckets["day"]),
        "week": _finish(buckets["week"]),
        "last_week": _finish(buckets["last_week"]),
        "month": _finish(buckets["month"]),
        "all": _finish(buckets["all"]),
    }

from services import live_guardrails as gr
from zoneinfo import ZoneInfo
ETZ = ZoneInfo("America/New_York")

def get_opened_at_map():
    """
    Map SYMBOL -> opened_at as ET-aware datetime, from live_guardrails.
    Used by both Sell Guard and dashboard so they agree.
    """
    out = {}
    if gr is None:
        return out

    try:
        for e in gr.list_open_entries():
            sym = (e.get("symbol") or "").upper()
            ts = e.get("opened_at")
            if not sym or not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=ETZ)
                else:
                    dt = dt.astimezone(ETZ)
                out[sym] = dt
            except Exception:
                continue
    except Exception as ex:
        print("get_opened_at_map error:", ex)

    return out

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
    Compute realized gain buckets (Day / Week / Last Week / Month / All)
    from live.db -> realized_trades.

    Schema expectation for realized_trades:
      id INTEGER PRIMARY KEY
      symbol TEXT
      action TEXT
      qty REAL
      open_date TEXT  -- "YYYY-MM-DD"
      close_date TEXT -- "YYYY-MM-DD"
      price_share REAL
      proceeds REAL
      cost_share REAL
      total_cost REAL
      gain REAL
      term TEXT

    Rules:
      * GEVO is excluded (defensive filter even though CSV sync already skips it).
      * "Day"       : trades with close_date == today (ET).
      * "Week"      : trades with close_date in the current Mon–Sun week.
      * "Last Week" : trades in the prior Mon–Sun week.
      * "Month"     : trades with close_date in the current calendar month.
      * "All"       : all trades since ALL_START_DATE.
    Percentages:
      * Day / Week / Last Week / Month: gain ÷ cost in that bucket.
      * All: cumulative_gain ÷ START_CASH.
    """
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
    except Exception as exc:
        print(f"[realized] failed to open DB {db_path}: {exc}")
        return {}

    def _f(x) -> float:
        try:
            return float(x)
        except Exception:
            return 0.0

    def bucket(start, end) -> Tuple[float, float]:
        """
        Inclusive date window [start, end] where start/end are date objects.
        Returns (gain, total_cost).
        """
        s = start.isoformat()
        e = end.isoformat()
        sql = (
            "SELECT COALESCE(SUM(gain), 0.0), "
            "       COALESCE(SUM(total_cost), 0.0) "
            "FROM realized_trades "
            "WHERE close_date >= ? AND close_date <= ? "
            "  AND (symbol IS NULL OR symbol != 'GEVO')"
        )
        try:
            cur.execute(sql, (s, e))
            row = cur.fetchone() or (0.0, 0.0)
        except Exception as exc:
            print(f"[realized] query failed for window {s}..{e}: {exc}")
            return 0.0, 0.0
        return _f(row[0]), _f(row[1])

    # ---------- Date windows (ET) ----------
    now_et = _dt.datetime.now(ET)
    today = now_et.date()

    # Current week (Mon..Sun)
    dow = today.weekday()  # Mon=0 .. Sun=6
    week_start = today - _dt.timedelta(days=dow)
    week_end = week_start + _dt.timedelta(days=6)

    # Previous week
    last_week_end = week_start - _dt.timedelta(days=1)
    last_week_start = last_week_end - _dt.timedelta(days=6)

    # Current month (1st -> today)
    month_start = today.replace(day=1)
    month_end = today

    # All (project start -> today)
    all_start = ALL_START_DATE
    all_end = today

    buckets: Dict[str, Dict[str, float]] = {}

    # Day
    day_gain, day_cost = bucket(today, today)
    day_pct = round((day_gain / day_cost) * 100.0, 2) if day_cost > 0 else 0.0
    buckets["day"] = {"pnl": round(day_gain, 2), "pct": day_pct}

    # Week (current)
    week_gain, week_cost = bucket(week_start, week_end)
    week_pct = round((week_gain / week_cost) * 100.0, 2) if week_cost > 0 else 0.0
    buckets["week"] = {"pnl": round(week_gain, 2), "pct": week_pct}

    # Last week
    lw_gain, lw_cost = bucket(last_week_start, last_week_end)
    lw_pct = round((lw_gain / lw_cost) * 100.0, 2) if lw_cost > 0 else 0.0
    buckets["last_week"] = {"pnl": round(lw_gain, 2), "pct": lw_pct}

    # Month (current)
    mon_gain, mon_cost = bucket(month_start, month_end)
    mon_pct = round((mon_gain / mon_cost) * 100.0, 2) if mon_cost > 0 else 0.0
    buckets["month"] = {"pnl": round(mon_gain, 2), "pct": mon_pct}

    # All (since project start, using START_CASH as baseline)
    all_gain, _all_cost = bucket(all_start, all_end)
    all_pct = round((all_gain / START_CASH) * 100.0, 2) if START_CASH > 0 else 0.0
    buckets["all"] = {"pnl": round(all_gain, 2), "pct": all_pct}

    try:
        conn.close()
    except Exception:
        pass

    return buckets

def _normalize_positions_payload(raw: dict) -> list[dict]:
    """
    Normalize E*TRADE positions into a simple list:

    [
      {
        "symbol": "DOW",
        "qty": 1,
        "price_paid": 22.15,
        "last_price": 22.31,
        "day_pl": 0.21,
        "day_pl_pct": 0.95,
        "prior_close": 22.10,
      },
      ...
    ]
    """
    rows: list[dict] = []
    if not raw:
        return rows

    pr = (raw.get("PortfolioResponse") or {}).get("AccountPortfolio") or []
    if isinstance(pr, dict):
        pr = [pr]

    for acct in pr:
        poss = acct.get("Position") or []
        if isinstance(poss, dict):
            poss = [poss]

        for pos in poss:
            prod = pos.get("Product") or {}
            sym = (prod.get("symbol")
                   or (prod.get("productId") or {}).get("symbol")
                   or pos.get("symbol")
                   or "").strip().upper()
            if not sym:
                continue

            qty = _safe_float(
                pos.get("quantity")
                or pos.get("longQuantity")
                or pos.get("positionQty")
                or 0.0
            )
            if qty <= 0:
                continue

            q = pos.get("Quick") or {}
            allf = pos.get("All") or {}

            price_paid = _safe_float(
                pos.get("pricePaid")
                or pos.get("averagePrice")
                or pos.get("costPerShare")
                or 0.0
            )

            last_price = _safe_float(
                q.get("lastTrade")
                or allf.get("lastTrade")
                or pos.get("lastTrade")
                or pos.get("marketValue") and (pos.get("marketValue") / max(qty, 1))
                or 0.0
            )

            # ---- Day P&L from E*TRADE ----
            # E*TRADE gives:
            #   daysGain     -> dollar P&L for the position (already * qty)
            #   daysGainPct  -> percent move for the position
            day_pl = _safe_float(
                pos.get("daysGain")
                or q.get("todayGainLoss")
                or q.get("todayGainLossBase")
                or 0.0
            )

            day_pl_pct = _safe_float(
                pos.get("daysGainPct")
                or q.get("todayGainLossPct")
                or 0.0
            )

            # Prior close / ref for fallback calc if needed later
            prior_close = _safe_float(
                pos.get("adjPrevClose")
                or q.get("priorClose")
                or q.get("closePrice")
                or allf.get("closePrice")
                or 0.0
            )

            rows.append(
                {
                    "symbol": sym,
                    "qty": qty,
                    "price_paid": price_paid,
                    "last_price": last_price,
                    "day_pl": day_pl,
                    "day_pl_pct": day_pl_pct,
                    "prior_close": prior_close,
                }
            )

    return rows

def _build_holdings_from_positions(
    pos_rows: list[dict],
) -> tuple[list[dict], float]:
    """
    From normalized positions rows, compute holdings rows with:
      symbol, opened_et, qty, price_paid, last_price, value,
      day_pl, day_pl_pct, total_pl, total_pl_pct.
    """
    from services import live_guardrails as gr
    from datetime import datetime
    from zoneinfo import ZoneInfo

    ETZ = ZoneInfo("America/New_York")

    # map of symbol -> opened_at from guardrails
    opened_map: dict[str, datetime] = {}
    try:
        for e in gr.list_open_entries():
            sym = (e.get("symbol") or "").upper()
            ts = e.get("opened_at")
            if not sym or not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=ETZ)
                else:
                    dt = dt.astimezone(ETZ)
                opened_map[sym] = dt
            except Exception:
                continue
    except Exception:
        pass

    holdings: list[dict] = []
    positions_value = 0.0

    for r in pos_rows:
        sym = (r.get("symbol") or "").upper()
        if not sym:
            continue

        qty = _safe_float(r.get("qty"), 0.0)
        paid = _safe_float(r.get("price_paid"), 0.0)
        last = _safe_float(r.get("last_price"), 0.0)
        if qty <= 0 or last <= 0:
            continue

        opened_dt = opened_map.get(sym)
        opened_str = opened_dt.strftime("%Y-%m-%d %H:%M") if opened_dt else "â€”"

        value = round(qty * last, 2)
        positions_value += value

        cost = qty * paid
        total_pl = round(value - cost, 2) if cost > 0 else 0.0
        total_pl_pct = round((total_pl / cost) * 100.0, 2) if cost > 0 else 0.0

        day_pl = _safe_float(r.get("day_pl"), 0.0)
        day_pl_pct = _safe_float(r.get("day_pl_pct"), 0.0)

        holdings.append(
            {
                "symbol": sym,
                "opened_et": opened_str,
                "qty": qty,
                "price_paid": round(paid, 4),
                "last_price": round(last, 4),
                "value": value,
                "day_pl": round(day_pl, 2),
                "day_pl_pct": round(day_pl_pct, 2),
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


@app.context_processor
def inject_status():
    return {"needs_reconnect": read_flag_file()}

# -----------------------------------------------------------------------------#
# Routes
# -----------------------------------------------------------------------------#


@app.route("/")
def index():
    return redirect(url_for("live_view"))

@app.route("/live/mode", methods=["GET", "POST"])
@always_json
def live_mode():
    """
    Get or set the Live trading mode (DAY or SWING).

    GET  -> {"ok": true, "mode": "DAY"}
    POST -> {"ok": true, "mode": "SWING"}  (with JSON body {"mode": "SWING"})
    """
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        mode = data.get("mode") or ""
        try:
            mode = _write_live_mode(mode)
        except ValueError:
            return {"ok": False, "error": "invalid_mode"}, 400
        return {"ok": True, "mode": mode}

    # GET: just report current mode
    return {"ok": True, "mode": _read_live_mode()}

@app.route("/live")
def live_view():
    """
    Initial HTML shell. JS immediately calls /live/status.
    Tolerant of upstream errors.
    """
    try:
        _etrade_log_wrap()

        # ---- balances ----
        acct_summary = et.get_account_summary() or {}
        account = _normalize_account(acct_summary) or {}

        # Raw fields from summary
        cash_balance = float(acct_summary.get("cash_balance") or acct_summary.get("nav") or 0.0)
        buying_power = float(
            acct_summary.get("available_funds")
            or account.get("buying_power")
            or 0.0
        )

        # ---- positions / holdings ----
        raw_positions = et.get_positions() or {}
        pos_rows = _normalize_positions_payload(raw_positions)

        # NOTE: _build_holdings_from_positions already returns (rows, total_mv)
        holdings, positions_value = _build_holdings_from_positions(pos_rows)

        # ---- effective NAV = cash + positions ----
        effective_nav = round(cash_balance + float(positions_value or 0.0), 2)

        # Update the account dict that the template uses
        account.update({
            "nav": effective_nav,                        # should match E*TRADE NAV (≈ 4444.26)
            "positions_value": round(positions_value or 0.0, 2),
            "cash_balance": round(cash_balance, 2),
            "buying_power": round(buying_power, 2),
            # Optional debug fields if you want them later:
            "raw_nav_from_summary": float(acct_summary.get("nav") or 0.0),
        })

    except Exception as e:
        log.exception("live_view error: %s", e)
        account, holdings = {}, []

    return render_template("live.html", account=account, holdings=holdings)


@app.route("/live/status")
@always_json
def live_status():
    """
    JSON feed for the Live UI.

    Query params:
      - start=YYYY-MM-DD  : earliest trade date (for table)
      - days=N            : fallback lookback
      - max=N             : max trades
      - debug=1           : include raw payloads
    """
    from flask import request, current_app
    from services import etrade_service as et
    from services.trade_source import load_trades_merged
    from services.trading_helpers import realized_buckets_from_live_db

    debug = request.args.get("debug", "0") == "1"
    debug_raw: dict[str, Any] = {}
    etrade_ok = False

    # ---------- 1) ACCOUNT SUMMARY (raw balances) ----------
    acct_summary_raw: dict[str, Any] = {}
    try:
        acct_summary_raw = et.get_account_summary() or {}
        etrade_ok = True
    except Exception as e:
        current_app.logger.exception("account summary error: %s", e)

    raw = acct_summary_raw.get("raw") or {}
    if debug:
        debug_raw["acct_summary_raw"] = acct_summary_raw

    comp = raw.get("Computed") or {}

    # Buying power = what you can actually deploy
    buying_power = _safe_float(
        comp.get("cashAvailableForInvestment")
        or comp.get("cashBuyingPower")
        or acct_summary_raw.get("available_funds")
        or 0.0
    )

    # ---------- 2) POSITIONS -> HOLDINGS + POSITIONS VALUE ----------
    holdings: list[dict] = []
    positions_value = 0.0

    try:
        raw_positions = et.get_positions() or {}
        if debug:
            debug_raw["positions_raw"] = raw_positions

        pos_rows = _normalize_positions_payload(raw_positions)
        holdings, positions_value = _build_holdings_from_positions(pos_rows)
    except Exception as e:
        current_app.logger.exception("positions error: %s", e)

    positions_value = _safe_float(positions_value, 0.0)

    # ---------- 3) APPROX NAV USING CASH BALANCE + NET CASH ----------
    # E*TRADE UI:
    #   Cash row ~= cashBalance - netCash
    #   NAV      ~= Cash row + positions_value
    cash_balance = _safe_float(
        comp.get("cashBalance"),
        _safe_float(acct_summary_raw.get("cash_balance"), 0.0),
    )
    net_cash = _safe_float(comp.get("netCash"), 0.0)

    effective_cash = cash_balance - net_cash
    nav = round(effective_cash + positions_value, 2)

    buying_power = round(buying_power, 2)
    positions_value = round(positions_value, 2)

    # ---------- 4) NORMALIZED ACCOUNT OBJECT ----------
    account = {
        "account_id": (
            acct_summary_raw.get("account_id")
            or raw.get("accountId")
        ),
        "account_key": (
            acct_summary_raw.get("account_key")
            or raw.get("accountIdKey")
            or raw.get("accountKey")
        ),
        "account_type": (
            acct_summary_raw.get("account_type")
            or raw.get("accountType")
        ),
        "account_type_display": (
            acct_summary_raw.get("account_type_display")
            or raw.get("accountMode")
        ),
        "nav": nav,
        "available_funds": buying_power,
    }

    # ---------- 5) UNREALIZED & DAY P&L ----------
    total_cost = 0.0
    day_unreal = 0.0

    for h in holdings:
        qty = _safe_float(h.get("qty"), 0.0)
        paid = _safe_float(h.get("price_paid"), 0.0)
        total_cost += qty * paid
        day_unreal += _safe_float(h.get("day_pl"), 0.0)

    unrealized_pnl = positions_value - total_cost if total_cost > 0 else 0.0
    unrealized_pnl_pct = (unrealized_pnl / total_cost * 100.0) if total_cost > 0 else 0.0

    day_unrealized_pnl = day_unreal
    day_unrealized_pnl_pct = (day_unrealized_pnl / nav * 100.0) if nav > 0 else 0.0

    # ---------- 6) TRADES TABLE (for history) ----------
    start = (request.args.get("start") or "").strip()
    days = request.args.get("days", type=int)
    max_count = request.args.get("max", default=5000, type=int)

    trades = load_trades_merged(
        days=days,
        start_iso=start,
        max_count=max_count,
    ) or []

    if debug:
        debug_raw["trades_raw"] = trades

    # ---------- 7) REALIZED P&L BUCKETS (from live.db) ----------
    realized_obj = realized_buckets_from_live_db(str(LIVE_DB)) or {}

    # ---------- 8) ABOUT / SINCE START (NAV + contributions) ----------
    START_CASH = START_CASH_BASELINE
    START_DATE = START_DATE_BASELINE

    try:
        net_contrib = float(get_total_contributions(START_DATE))
    except Exception:
        net_contrib = 0.0

    # True gain = NAV − start_cash − contributions
    total_gain = round(nav - START_CASH - net_contrib, 2)

    # Percent = gain / (start_cash + contributions)
    denom = START_CASH + net_contrib
    total_gain_pct = round((total_gain / denom * 100.0), 2) if denom > 0 else 0.0

    about = {
        "start_cash": START_CASH,
        "start_date": START_DATE,
        "net_contrib": round(net_contrib, 2),
        "since_pnl": total_gain,
        "since_pct": total_gain_pct,
    }

    # ---------- 9) OVERRIDE 'ALL' BUCKET TO MATCH HERO ----------
    all_bucket = realized_obj.get("all") or {}
    all_bucket["pnl"] = total_gain
    all_bucket["pct"] = total_gain_pct
    realized_obj["all"] = all_bucket

    # ---------- 10) VALUE OBJECT FOR LEFT TILE ----------
    value_obj = {
        "net_account_value": nav,
        "positions_value": positions_value,
        "buying_power": buying_power,
        "value": nav,  # historical alias
    }

    # ---------- 11) METRICS / VALUE FOR TILES ----------
    metrics = {
        # Left tile
        "net_account_value": nav,
        "buying_power": buying_power,
        "positions_value": positions_value,

        # Center tile (unrealized)
        "day_unrealized_pnl": day_unrealized_pnl,
        "day_unrealized_pnl_pct": day_unrealized_pnl_pct,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_pct": unrealized_pnl_pct,

        # Hero blurb “since start” (NAV-based)
        "total_gain_nav": total_gain,
        "total_gain_nav_pct": total_gain_pct,

        # Right tile: realized P&L buckets (with All overridden above)
        "realized_buckets": realized_obj,
    }

    # ---------- 12) AUTH / STATUS ----------
    needs_reconnect = bool(
        getattr(et, "need_oauth", False)
        or os.path.exists(str(NEED_AUTH_FLAG))
    )

    payload: dict[str, Any] = {
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





