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
import math
import json
import sys
import logging
import sqlite3
import threading
import subprocess
import pathlib
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Tuple

from flask import Flask, render_template, jsonify, request, redirect, url_for
from services.contributions import get_total_contributions
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

import sqlite3  # if not already imported at top

def get_recent_news_for_symbol(symbol: str, limit: int = 5) -> list[dict]:
    """
    Read recent news headlines for a symbol from news_events (live.db).

    Schema expectation for news_events:
      id INTEGER PRIMARY KEY
      symbol TEXT
      headline TEXT
      source TEXT
      url TEXT
      published_at TEXT (ISO or 'YYYY-MM-DD HH:MM:SS')
    """
    sym = (symbol or "").upper().strip()
    if not sym:
        return []

    rows: list[dict] = []
    try:
        conn = sqlite3.connect(str(LIVE_DB))
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                symbol,
                headline,
                source,
                url,
                published_at
            FROM news_events
            WHERE UPPER(symbol) = ?
            ORDER BY published_at DESC
            LIMIT ?
            """,
            (sym, int(limit)),
        )
        for s, headline, source, url, published_at in cur.fetchall():
            rows.append(
                {
                    "symbol": s,
                    "headline": headline or "",
                    "source": source or "",
                    "url": url or "",
                    "published_at": published_at or "",
                }
            )
        conn.close()
    except Exception as e:
        # don't crash the dashboard if news lookup fails
        app.logger.error("get_recent_news_for_symbol(%s) failed: %s", sym, e)

    return rows


@app.route("/news/<symbol>")
def view_symbol_news(symbol: str):
    """
    HTML view for a single symbol's news.
    This is what the 📰 buttons on the Live holdings table link to.
    """
    sym = (symbol or "").upper().strip()
    news_rows = get_recent_news_for_symbol(sym, limit=10)

    return render_template(
        "news_view.html",
        symbol=sym,
        news_rows=news_rows,
    )

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

ENABLE_AI_ENTRIES = False  # hard off switch for now
ENABLE_AI_EXITS   = False

def ai_decide_entry(snapshot: dict) -> dict:
    if not ENABLE_AI_ENTRIES:
        return {
            "action": "SKIP",
            "confidence": 0,
            "sizing_hint": "AVOID_ADDING",
            "reason_tags": ["ai_disabled"],
            "comment": "AI advisor disabled; follow base rules only."
        }
    # ... existing OpenAI call ...

def ai_decide_exit(snapshot: dict) -> dict:
    if not ENABLE_AI_EXITS:
        return {
            "action": "HOLD",
            "confidence": 0,
            "sizing_hint": "AVOID_ADDING",
            "reason_tags": ["ai_disabled"],
            "comment": "AI exit advisor disabled; follow sell_guard rules only."
        }
    # ... existing OpenAI call ...

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
        buying_power = explicit_bp
        value = buying_power + positions_value

    # --- Unrealized ALL P&L from holdings table ---
    total_unreal_pl = round(
        sum(_safe_float(h.get("total_pl"), 0.0) for h in holdings_rows), 2
    )
    total_unreal_pct = (
        round((total_unreal_pl / positions_value) * 100.0, 2)
        if positions_value > 0 else 0.0
    )

    return {
        "buying_power": round(buying_power, 2),
        "positions_value": round(positions_value, 2),
        "value": round(value, 2),

        # NEW: full unrealized (ALL)
        "unrealized_pl": total_unreal_pl,
        "unrealized_pl_pct": total_unreal_pct,
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
      open_date TEXT  -- "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS"
      close_date TEXT -- "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS"
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
        sql = """
            SELECT
              COALESCE(SUM(gain), 0.0)       AS gain,
              COALESCE(SUM(total_cost), 0.0) AS total_cost
            FROM realized_trades
            WHERE date(close_date) >= date(?)
              AND date(close_date) <= date(?)
              AND (symbol IS NULL OR symbol != 'GEVO')
        """
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
def _enrich_trades_from_realized(trades: list[dict]) -> list[dict]:
    """
    For SELL trades that have price_paid == 0 (or missing), patch them using
    realized_trades from live.db so Recent Trades shows correct Price Paid and P&L.

    Matching strategy:
      - key = (symbol, close_date truncated to seconds)
      - use trade['time_utc'] or trade['time'] for the timestamp
    """
    if not trades:
        return trades

    # Build an index of realized_trades keyed by (SYMBOL, CLOSE_TS)
    try:
        conn = sqlite3.connect(str(LIVE_DB))
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                symbol,
                close_date,
                qty,
                cost_share,
                total_cost,
                gain
            FROM realized_trades
            """
        )
        realized_index: dict[tuple[str, str], dict] = {}

        def _norm_ts(s: str | None) -> str:
            if not s:
                return ""
            s = str(s).replace("T", " ")
            return s[:19]  # "YYYY-MM-DD HH:MM:SS"

        for sym, close_date, qty, cost_share, total_cost, gain in cur.fetchall():
            key = (str(sym or "").upper(), _norm_ts(close_date))
            realized_index[key] = {
                "qty": float(qty or 0.0),
                "cost_share": float(cost_share or 0.0),
                "total_cost": float(total_cost or 0.0),
                "gain": float(gain or 0.0),
            }

        conn.close()
    except Exception as exc:
        log.error("_enrich_trades_from_realized: failed to read realized_trades: %s", exc)
        return trades

    def _norm_ts_trade(t: dict) -> str:
        ts = t.get("time_utc") or t.get("time") or ""
        ts = str(ts).replace("T", " ")
        return ts[:19]

    enriched: list[dict] = []

    for t in trades:
        action = (t.get("action") or t.get("side") or "").upper()
        if action != "SELL":
            enriched.append(t)
            continue

        price_paid = t.get("price_paid")
        # Only patch clearly bogus values
        if price_paid not in (None, 0, 0.0):
            enriched.append(t)
            continue

        sym = (t.get("symbol") or "").upper()
        if not sym:
            enriched.append(t)
            continue

        key = (sym, _norm_ts_trade(t))
        r = realized_index.get(key)
        if not r:
            enriched.append(t)
            continue

        qty = t.get("qty")
        try:
            qty_f = float(qty or r["qty"] or 0.0)
        except Exception:
            qty_f = float(r["qty"] or 0.0)

        cost_share = r["cost_share"]
        total_cost = r["total_cost"] or (cost_share * qty_f)
        gain = r["gain"]

        if qty_f <= 0 or cost_share <= 0:
            enriched.append(t)
            continue

        pl = gain
        pl_pct = (pl / total_cost * 100.0) if total_cost > 0 else 0.0

        t2 = dict(t)
        t2["price_paid"] = round(cost_share, 4)
        t2["pl"] = round(pl, 2)
        t2["pl_pct"] = round(pl_pct, 2)
        enriched.append(t2)

    return enriched

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
                "has_news": False,
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

@app.route("/news/latest")
@always_json
def news_latest():
    rows = fetch_latest_news()
    return {"ok": True, "items": rows}

@app.route("/news/symbol/<symbol>")
@always_json
def news_for_symbol(symbol):
    rows = fetch_news_for_symbol(symbol)
    return {"ok": True, "items": rows}


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

@app.route("/live/ai_toggle", methods=["POST"])
@always_json
def live_ai_toggle():
    """
    Toggle AI Advisor on/off for Day mode via the UI.
    """
    try:
        body = request.get_json(force=True, silent=True) or {}
        enabled = bool(body.get("enabled"))
    except Exception:
        enabled = False

    # Load current day settings
    day_settings_path = Path("C:/TradeAlerts/live_settings_day.json")
    data = json.loads(day_settings_path.read_text(encoding="utf-8"))

    ai_cfg = data.get("ai") or {}
    ai_cfg["enabled"] = enabled
    data["ai"] = ai_cfg

    day_settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    return {
        "ai": {
            "enabled": ai_cfg["enabled"],
            "use_entries": ai_cfg.get("use_entries", True),
            "use_exits": ai_cfg.get("use_exits", True),
        },
    }

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
    # --- NAV (Net Account Value) ---
    # Prefer E*TRADE's own computed netAccountValue or nav from the
    # summary. Only fall back to a derived value if those are missing.
    cash_balance = _safe_float(
        comp.get("cashBalance"),
        _safe_float(acct_summary_raw.get("cash_balance"), 0.0),
    )
    net_cash = _safe_float(comp.get("netCash"), 0.0)

    nav = _safe_float(
        comp.get("netAccountValue") or acct_summary_raw.get("nav")
    )

    # If nav wasn't present or came back non-finite, derive a best-effort
    # value from cash + positions, adjusted by net_cash if we have it.
    if not math.isfinite(nav) or nav <= 0:
        effective_cash = cash_balance
        if math.isfinite(net_cash):
            effective_cash = cash_balance - net_cash
        nav = round(effective_cash + positions_value, 2)

    nav = round(nav, 2)
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
    # --- UI buying power choice ---
    # For your cash / PDT account, E*TRADE reports:
    #   cash_balance = 2012.77  (what you can really deploy)
    #   available_funds = 12.77 (tiny computed BP)
    #
    # For the left tile we want the *cash_balance* number.
    acct_mode = (acct_summary_raw.get("raw", {})
                 .get("accountType", "")).upper()
    if acct_mode in {"PDT_ACCOUNT", "CASH", "CASH_ACCOUNT"}:
        ui_buying_power = cash_balance
    else:
        # margin or weird cases – fall back sensibly
        cash_balance = account.get("cash_balance")

        available_funds = account.get("available_funds")
        ui_buying_power = available_funds if available_funds is not None else cash_balance

    # ---------- 5) UNREALIZED & DAY P&L ----------
    total_cost = 0.0
    total_value = 0.0
    day_unreal = 0.0

    # use the same rows you use for the holdings table
    for h in holdings:
        qty = _safe_float(h.get("qty"), 0.0)
        paid = _safe_float(h.get("price_paid"), 0.0)
        last = _safe_float(h.get("last_price"), 0.0)

        total_cost += qty * paid
        total_value += qty * last
        day_unreal += _safe_float(h.get("day_pl"), 0.0)

    # ALL-TIME unrealized in dollars
    total_unreal_pl = round(total_value - total_cost, 2) if total_cost > 0 else 0.0

    # For the "All Time" % tile, measure against the original project stake
    # (8/22/2025 baseline), not just current open-position cost.
    base_for_unreal = START_CASH_BASELINE
    if base_for_unreal > 0:
        total_unreal_pct = round((total_unreal_pl / base_for_unreal) * 100.0, 2)
    else:
        total_unreal_pct = 0.0

    # keep day unreal in case we want it later
    day_unrealized_pnl = round(day_unreal, 2)
    day_unrealized_pnl_pct = (
        round((day_unrealized_pnl / nav) * 100.0, 2) if nav > 0 else 0.0
    )


    # ---------- 6) TRADES TABLE (for history) ----------
    start = (request.args.get("start") or "").strip()
    days = request.args.get("days", type=int)
    max_count = request.args.get("max", default=5000, type=int)

    trades = load_trades_merged(
        days=days,
        start_iso=start,
        max_count=max_count,
    ) or []

    # Fix SELL trades that are missing proper cost basis / P&L
    trades = _enrich_trades_from_realized(trades)

    if debug:
        debug_raw["trades_raw"] = trades

    # ---------- 7) REALIZED P&L BUCKETS (from live.db) ----------
    realized_obj = realized_buckets_from_live_db(str(LIVE_DB)) or {}

    # ---------- 8) VALUE / TRADEALERTS NAV (BP + positions) ----------
    # nav_ta = TradeAlerts computed NAV: cash we can deploy (BP) + positions value.
    # This matches the 4,381.31 number you see on the web UI when you’re all in cash.
    nav_ta = round(float(ui_buying_power) + float(positions_value), 2)

    # ---------- 9) ABOUT / SINCE START (NAV_TA + contributions) ----------
    start_cash = START_CASH_BASELINE
    start_date = START_DATE_BASELINE

    try:
        net_contrib = float(get_total_contributions(start_date))
    except Exception:
        net_contrib = 0.0

    # True gain = NAV_TA − start_cash − contributions
    total_gain = round(nav_ta - start_cash - net_contrib, 2)

    # Percent = gain / (start_cash + contributions)
    denom = start_cash + net_contrib
    total_gain_pct = round((total_gain / denom * 100.0), 2) if denom > 0 else 0.0

    about = {
        "start_cash": start_cash,
        "start_date": start_date,
        "net_contrib": round(net_contrib, 2),
        "since_pnl": total_gain,       # <- this feeds the hero blurb
        "since_pct": total_gain_pct,
    }

    # ---------- 10) VALUE OBJECT FOR LEFT TILE ----------
    # Keep the left tile showing the raw broker NAV (2,927.61) so you can still
    # see exactly what the API is giving us, but expose nav_ta as "value".
    value_obj = {
        "net_account_value": nav,      # broker NAV from get_account_summary()
        "positions_value": positions_value,
        "buying_power": ui_buying_power,
        "value": nav_ta,              # TA computed NAV (BP + PV)
    }

    # ---------- 11) METRICS / VALUE FOR TILES ----------
    metrics = {
        # Left tile
        "net_account_value": nav,
        "nav_ta": nav_ta,             # TA-computed NAV (for debugging / future UI)
        "buying_power": ui_buying_power,
        "positions_value": positions_value,

        # Center tile: Day vs All-Time
        # Day = today's move (sum of daysGain / day_pl)
        # All Time = full unrealized based on cost vs current value
        "day_unrealized_pnl": day_unrealized_pnl,
        "day_unrealized_pnl_pct": day_unrealized_pnl_pct,
        "unrealized_pl": total_unreal_pl,
        "unrealized_pl_pct": total_unreal_pct,

        # Hero blurb “since start” (NAV-based)
        "total_gain_nav": total_gain,
        "total_gain_nav_pct": total_gain_pct,
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





