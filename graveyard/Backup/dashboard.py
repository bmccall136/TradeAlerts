from dotenv import load_dotenv

load_dotenv()

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import csv
import io
import json
import logging
import os
import sqlite3
import subprocess
import threading
from collections import namedtuple
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from dateutil.relativedelta import relativedelta

from services.etrade_service import fetch_etrade_quote
from services.realized_buckets import realized_buckets_from_live_db

NEED_AUTH_FLAG = Path("need_oauth.flag")

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    from backports.zoneinfo import ZoneInfo  # if running older Pythons

ET = ZoneInfo("America/New_York")

import os
import re
import sys
from functools import wraps
from pathlib import Path

import pandas as pd
from flask import Flask, Response, current_app, jsonify, redirect, render_template, request, url_for
from services.realized_pl import summarize as summarize_realized, recent_trades as live_recent_trades

import services.label_config as label_config
# --- standard imports ---
import os
from functools import lru_cache
from datetime import datetime, timedelta, timezone

# --- DB paths (keep before any functions that use them) ---
SIM_DB     = os.path.join(os.getcwd(), "simulation.db")
BACKTEST_DB = os.path.join(os.getcwd(), "backtest.db")
# Prefer env override; default to your Windows path for live
LIVE_DB    = os.environ.get("LIVE_DB", r"C:\TradeAlerts\live.db")


def mask_account_id(account_id: str) -> str:
    # For numeric IDs: show last 4, e.g., ••••3458
    if account_id.isdigit():
        return f"••••{account_id[-4:]}"
    # For keys: show 4+ellipsis+4, e.g., kW8L…C8iWA
    if len(account_id) > 9:
        return f"{account_id[:4]}…{account_id[-5:]}"
    return account_id


def format_account_badge(acct: dict) -> str:
    # acct should have 'accountId' (numeric) and/or 'accountIdKey' (opaque)
    numeric = (acct.get("accountId") or "").strip()
    key = (acct.get("accountIdKey") or "").strip()
    label_id = numeric or key or "?"
    acct_type = (acct.get("accountType") or "").upper()  # e.g., "MARGIN"
    return f"{acct_type} • {mask_account_id(label_id)}"


def setup_logging(app: Flask) -> None:
    # Guard: configure once, only in the reloader child when debug=True
    if getattr(app, "_logging_configured", False):
        return
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    logdir = Path(r"C:\TradeAlerts\logs")
    logdir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s")

    # App logger -> file (rotate) + console
    app.logger.handlers.clear()
    app.logger.setLevel(logging.INFO)

    try:
        # Safer rotation on Windows if available:
        from concurrent_log_handler import ConcurrentRotatingFileHandler as RFH
    except Exception:
        from logging.handlers import RotatingFileHandler as RFH

    fh = RFH(
        logdir / "dashboard.log",
        maxBytes=10_000_000,
        backupCount=7,
        encoding="utf-8",
        delay=True,
    )  # delay=True: don't hold the file open
    fh.setFormatter(fmt)
    app.logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    app.logger.addHandler(sh)

    # Quiet Werkzeug (avoid double writes & rotations)
    wz = logging.getLogger("werkzeug")
    wz.handlers.clear()
    wz.setLevel(logging.WARNING)

    # Optional: quiet noisy libs
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    app._logging_configured = True


# CALL IT ONCE, RIGHT AFTER app IS CREATED:
def _compat_get_positions(*_args, **_kwargs):
    import services.etrade_service as et

    return et.get_positions()


def parse_max_qty_from_msg(msg: str):
    m = re.search(
        r"maximum allowable quantity was estimated to be\s+(\d+)", msg or "", re.I
    )
    return int(m.group(1)) if m else None


def place_buy_with_preview_fallback(broker, symbol, qty, limit_px):
    ok, err = broker.preview_buy(
        symbol, qty, limit_px
    )  # whatever your preview wrapper returns
    if ok:
        return broker.place_buy(symbol, qty, limit_px)

    # 8400 insufficient funds -> try the â€œallowedâ€ quantity if present
    if getattr(err, "code", None) == 8400:
        max_q = parse_max_qty_from_msg(getattr(err, "message", ""))
        if max_q and 1 <= max_q < qty:
            return broker.place_buy(symbol, max_q, limit_px)
    # otherwise bubble up / skip
    raise err


def pick_qty(limit_px, acct, max_per_trade):
    """
    limit_px: float
    acct: dict from et.get_account_summary() or balances endpoint
    max_per_trade: e.g. 150.0 dollars
    """

    def _f(x):
        try:
            return float(x) if x is not None else 0.0
        except:
            return 0.0

    # Prefer the tightest/most conservative figure
    candidates = [
        _f(acct.get("available_funds")),
        _f(acct.get("cashAvailableForInvestment")),  # some payloads use this
        _f(acct.get("cash_balance")),
        _f(acct.get("settled_cash")),
    ]
    avail = (
        min(c for c in candidates if c > 0) if any(c > 0 for c in candidates) else 0.0
    )

    # Safety buffer so tiny price wiggles or fees donâ€™t cause a preview reject
    buffer_dollars = 3.00
    spend_cap = max(0.0, min(avail, float(max_per_trade)) - buffer_dollars)

    if limit_px <= 0 or spend_cap <= 0:
        return 0
    return int(spend_cap // float(limit_px))


def always_json(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            rv = f(*args, **kwargs)
        except Exception as e:
            current_app.logger.exception("[LIVE] /live/status crashed")
            return jsonify({"ok": False, "error": str(e)}), 500
        # Normalize all return shapes to a valid Flask response
        if rv is None:
            return jsonify({"ok": False}), 200
        if isinstance(rv, Response):
            return rv
        if isinstance(rv, tuple):
            body = rv[0]
            if isinstance(body, (dict, list, tuple)):
                return (jsonify(body), *rv[1:])
            return rv
        if isinstance(rv, (dict, list, tuple)):
            return jsonify(rv), 200
        return rv

    return wrapper


# import all label dicts from centralized config
# ---Load environment variables ------------------------------------------------------------------------------------------------------------------
from dotenv import load_dotenv

load_dotenv()
# --- HOTFIX: unify env + signer and call E*TRADE directly --------------------
import os

from dotenv import find_dotenv, load_dotenv

# Ensure .env is loaded in THIS process (Flask)
load_dotenv(find_dotenv(), override=True)


# Mirror env names both ways so old/new code paths see them
def _alias(a, b):
    va, vb = os.getenv(a), os.getenv(b)
    if va and not vb:
        os.environ[b] = va
    if vb and not va:
        os.environ[a] = vb


for A, B in [
    ("OAUTH_TOKEN", "ETRADE_OAUTH_TOKEN"),
    ("OAUTH_TOKEN_SECRET", "ETRADE_OAUTH_TOKEN_SECRET"),
    ("ETRADE_CONSUMER_KEY", "CONSUMER_KEY"),
    ("ETRADE_CONSUMER_SECRET", "CONSUMER_SECRET"),
]:
    _alias(A, B)

os.environ.setdefault("ETRADE_API_HOST", "https://api.etrade.com")

# ------------ Core Flask imports ---------------------------------------------------------------------------------------------------------------------------
import os

from flask import (
    Flask,
    flash,
    session,
)

from services.market_service import fetch_data_with_timeout, get_symbols
from services.settings_schema import SimulationSettings, extract_simulation_settings
from services.settings_service import load_settings, save_settings

# ---------€ Service imports ------------------------------------------------------------------------------------------------------------------------------
from services.trading_helpers import (
    get_cash,
    get_cash_ledger,
    get_holdings,
    get_realized_pl,
    get_stored_cash,
    get_trades,
    init_backtest_db,
    set_cash,
    setup_simulation_db,
)

try:
    from services.broker_api import fetch_live_data
except ImportError:
    fetch_live_data = None
import os
from pathlib import Path

from flask import Flask, send_file
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# --- loud E*TRADE logging wrapper (module-scope; not inside live_status) ---
_ET_LOG_WRAPPED = False
from functools import lru_cache


from functools import lru_cache
from datetime import datetime, timedelta, timezone

def _fifo_realized_today(trades):
    import datetime as _dt

    def _to_f(x):
        try:
            if x is None:
                return None
            if isinstance(x, (int, float)):
                return float(x)
            return float(str(x).replace(",", "").strip())
        except Exception:
            return None

    def _safe_float(x, d=0.0):
        try:
            return float(x)
        except Exception:
            return float(d)

    def _to_ts(val) -> int:
        """Epoch milliseconds from mixed inputs (int ms/s, ISO, or ET string)."""
        try:
            if isinstance(val, (int, float)):
                v = float(val)
                return int(v if v > 10_000_000_000 else v * 1000)
            s = str(val or "")
            if " " in s and "T" not in s:
                s = s.replace(" ", "T")
            if "Z" not in s and "+" not in s:
                s += "Z"
            dt = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
        except Exception:
            return 0

    today = _dt.datetime.utcnow().date()
    lots = {}  # sym -> [[qty, px], ...] FIFO
    realized_today = 0.0
    realized_basis = 0.0
    enriched = []

    # process buys -> sells in chronological order
    rows = sorted(
        trades or [],
        key=lambda r: _to_ts(r.get("time_utc") or r.get("time") or r.get("time_et")),
    )

    for t in rows:
        sym = (t.get("symbol") or "").upper()
        side = (t.get("action") or "").upper()
        qty = int(_safe_float(t.get("qty")))
        px = _to_f(t.get("price"))
        ts = _to_ts(t.get("time_utc") or t.get("time") or t.get("time_et"))
        date = _dt.datetime.utcfromtimestamp(ts / 1000.0).date() if ts else today

        if not sym or qty <= 0 or (px or 0) <= 0:
            enriched.append(dict(t))
            continue

        lots.setdefault(sym, [])

        if side == "BUY":
            lots[sym].append([qty, px])
            row = dict(t)
            row["price_paid"] = _to_f(row.get("price_paid")) or px
            row["pl"] = _to_f(row.get("pl")) or 0.0
            row["pl_pct"] = _to_f(row.get("pl_pct")) or 0.0
            enriched.append(row)
            continue

        if side == "SELL":
            remain = qty
            basis_cost = 0.0
            basis_shares = 0

            while remain > 0 and lots[sym]:
                lot_qty, lot_px = lots[sym][0]
                take = min(remain, lot_qty)
                basis_cost += take * lot_px
                basis_shares += take
                lot_qty -= take
                remain -= take
                if lot_qty == 0:
                    lots[sym].pop(0)
                else:
                    lots[sym][0][0] = lot_qty

            avg_basis = (basis_cost / basis_shares) if basis_shares else 0.0
            pnl = (px - avg_basis) * basis_shares if basis_shares else 0.0
            pnl_pct = ((px / avg_basis - 1.0) * 100.0) if avg_basis else 0.0

            row = dict(t)
            if avg_basis:
                row["price_paid"] = round(avg_basis, 2)
            row["pl"] = round(pnl, 2)
            row["pl_pct"] = round(pnl_pct, 2)
            enriched.append(row)

            if date == today and basis_shares:
                realized_today += pnl
                realized_basis += avg_basis * basis_shares
            continue

        # any other action: pass through
        enriched.append(dict(t))

    realized_today_pct = (
        round((realized_today / realized_basis * 100.0), 2)
        if realized_basis > 0
        else 0.0
    )
    return enriched, round(realized_today, 2), realized_today_pct


# near the top of dashboard.py
import zoneinfo


def _safe_float(x):
    try:
        return float(x)
    except:
        return 0.0


_TZ_ET = zoneinfo.ZoneInfo("America/New_York")


def _to_dt_local(t, tz=None):
    tz = tz or _et()
    if t is None:
        return None
    try:
        n = float(t)
        if n > 10_000_000_000:
            return datetime.fromtimestamp(n / 1000.0, tz)
    except Exception:
        pass
    s = str(t).strip()
    if not s:
        return None
    if "T" in s:
        s = s.replace("T", " ")
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
    except Exception:
        return None


def _etrade_log_wrap():
    """Wrap etrade_service get_quotes/get_quote so we SEE calls in Flask logs."""
    global _ET_LOG_WRAPPED
    if _ET_LOG_WRAPPED:
        return
    try:
        from services import etrade_service as et
    except Exception:
        return

    import functools

    def _wrap(name):
        fn = getattr(et, name, None)
        if not callable(fn):
            return

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                # current_app is available when called from a request (like live_status)
                from flask import current_app

                if current_app and current_app.logger:
                    current_app.logger.info(
                        "[E*TRADE.%s] CALL args=%s kwargs=%s", name, args, kwargs
                    )
            except Exception:
                pass

            result = fn(*args, **kwargs)

            try:
                from flask import current_app

                if current_app and current_app.logger:
                    current_app.logger.info(
                        "[E*TRADE.%s] OK -> %s", name, type(result).__name__
                    )
            except Exception:
                pass

            return result

        setattr(et, name, wrapper)

    for nm in ("get_quotes", "get_quote"):
        _wrap(nm)

    _ET_LOG_WRAPPED = True


# before any get_cash()/buy()/sell() calls:
setup_simulation_db()

# ------ Dynamic Unicode font registration ------------------------------------------------------------------------------------------------
if os.name == "nt":  # Windows
    font_path = r"C:\Windows\Fonts\seguiemj.ttf"  # Segoe UI Emoji
else:  # macOS/Linux
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

try:
    pdfmetrics.registerFont(TTFont("UnicodeFont", font_path))
    unicode_font_name = "UnicodeFont"
except Exception as e:
    print(f"[WARN] Unicode font load failed ({e}), falling back to Helvetica")
    unicode_font_name = "Helvetica"
# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------€

# Pick a Unicode font path based on platform
if os.name == "nt":  # Windows
    # Segoe UI Emoji ships with Windows 10+ and covers ðŸš€ðŸ“Š etc.
    font_path = r"C:\Windows\Fonts\seguiemj.ttf"
else:
    # Linux fallback
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Try to register it; if that fails, fall back to built-in Helvetica
try:
    unicode_font_name = "UnicodeFont"
except Exception as e:
    print(f"[WARN] Unicode font registration failed ({e}), falling back to Helvetica")
    unicode_font_name = "Helvetica"

# Register DejaVu Sans (bundled with most systems) for full Unicode support:
# Make a paragraph style that uses DejaVuSans:
unicode_style = ParagraphStyle(
    "Unicode", parent=getSampleStyleSheet()["Normal"], fontName="DejaVuSans"
)
unicode_title = ParagraphStyle(
    "UnicodeTitle",
    parent=getSampleStyleSheet()["Title"],
    fontName="DejaVuSans",
    fontSize=24,
    alignment=1,  # center
)

IGNORED_TICKERS = {
    s.upper() for s in (os.getenv("IGNORE_TICKERS", "GEVO").split(",") if True else [])
}

# --- cash sync check ---
try:
    ledger = get_cash_ledger()
    stored = get_cash()
    if abs(ledger - stored) > 0.01:
        print(f"[CASH] MISMATCH: ledger=${ledger:.2f} stored=${stored:.2f}")
        # Optionally fix it right here:
        # set_cash(ledger)
except Exception as e:
    print(f"[CASH] check failed: {e}")

# near the top of dashboard.py
_is_scanner_running = False
_needs_auth = False

# LIVE (production) endpoints only
REQUEST_TOKEN_URL = "https://api.etrade.com/oauth/request_token"
ACCESS_TOKEN_URL = "https://api.etrade.com/oauth/access_token"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"


from pathlib import Path

FLAG = Path("need_oauth.flag")

setup_simulation_db()
# ------------ Database file paths ------------------------------------------------------------------------------------------------------------------
SIM_DB = os.path.join(os.getcwd(), "simulation.db")
BACKTEST_DB = os.path.join(os.getcwd(), "backtest.db")

# ------------ Timeframe presets & simulation defaults ------------------------------------------------
TIMEFRAME_DELTAS = {
    "1mo": {"months": 1},
    "3mo": {"months": 3},
    "6mo": {"months": 6},
    "1y": {"years": 1},
}
DEFAULT_STARTING_CASH = 10000.0
DEFAULT_MAX_PER_TRADE = 1000.0

# ------------ E*TRADE OAuth configuration (production only) ------------------------------
OAUTH_HOST = "https://api.etrade.com"
REQUEST_TOKEN_URL = f"{OAUTH_HOST}/oauth/request_token"
ACCESS_TOKEN_URL = f"{OAUTH_HOST}/oauth/access_token"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
KEY_OAUTH_TOKEN = "OAUTH_TOKEN"
KEY_OAUTH_TOKEN_SECRET = "OAUTH_TOKEN_SECRET"

# ------------ OAuth routes ------------------------------------------------------------------------------------------------------------------------------------
from requests_oauthlib import OAuth1Session

print("LOADING settings_service.py from", __file__)
stored = get_stored_cash()

from services.etrade_auth_helper import clear_need_auth_flag, save_tokens

# LIVE endpoints
REQUEST_TOKEN_URL = "https://api.etrade.com/oauth/request_token"
ACCESS_TOKEN_URL = "https://api.etrade.com/oauth/access_token"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"

# ---- LIVE HTTP FALLBACK (no flags, no broker import) -----------------

# services/etrade_service.py
import os

BASE_URL = os.getenv("ETRADE_API_HOST", "https://api.etrade.com")  # ensure PROD

# --- also in services/etrade_service.py ---
# at top of dashboard.py
from datetime import UTC

# --- small helpers -----------------------------------------------------------
# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# FIFO cost-basis + Realized P&L buckets (ET timezone aware)
# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
from zoneinfo import ZoneInfo

_TZ_ET = ZoneInfo("America/New_York")


def _to_ts(x) -> int:
    """Epoch ms from epoch s/ms or ISO/ET 'YYYY-MM-DD HH:MM:SS'."""
    if x is None or x == "":
        return 0
    # epoch seconds / ms
    try:
        n = float(str(x).strip())
        return int(n if n > 10_000_000_000 else n * 1000)
    except Exception:
        pass
    s = str(x).strip().replace("T", " ").replace("Z", "")
    try:
        return int(
            datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_TZ_ET).timestamp()
            * 1000
        )
    except Exception:
        try:
            return int(
                datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=_TZ_ET).timestamp()
                * 1000
            )
        except Exception:
            return 0


def _to_dt_local(x):
    """ET datetime from any of the time fields we emit."""
    ts = _to_ts(x)
    return datetime.fromtimestamp(ts / 1000.0, _TZ_ET) if ts else None


def _as_float(x, default=0.0):
    try:
        if isinstance(x, str):
            x = x.replace("$", "").replace(",", "").strip()
        return float(x)
    except Exception:
        return float(default)


def fifo_enrich_trades(trades):
    """
    Return (enriched_trades, realized_today, realized_today_pct).
    Enriches SELL rows with FIFO cost basis -> price_paid, pl, pl_pct.
    """
    lots = {}  # sym -> [[qty, px], ...] FIFO
    enriched = []
    realized_today = 0.0
    realized_basis = 0.0
    today = datetime.now(_et()).date()


def _safe_float(val, default: float = 0.0) -> float:
    """
    Parse floats safely from numbers/strings like '$145.85', '1,234.56', or None.
    Returns `default` on any failure.
    """
    if val is None:
        return default
    try:
        if isinstance(val, str):
            s = val.strip().replace("$", "").replace(",", "")
            if s == "":
                return default
            return float(s)
        return float(val)
    except Exception:
        return default


def _fmt_trade_time(ts) -> str:
    """Return a nice local time string from E*TRADE timestamps."""
    if ts in (None, "", 0):
        return ""
    try:
        # numeric? (ms or sec)
        if isinstance(ts, (int, float)) or (isinstance(ts, str) and ts.isdigit()):
            v = float(ts)
            if v > 1e12:  # ms -> sec
                v /= 1000.0
            dt = datetime.fromtimestamp(v, tz=UTC)
        else:
            # ISO-ish (handle trailing Z)
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        # last resort: just echo the value
        return str(ts)


def get_recent_trades_and_realized(days: int = 2):
    """
    Returns:
      trades: [{time, symbol, action, qty, price, amount}]
      realized: float  (best-effort; uses API gain if available, else 0)
    """
    orders = list_executed_orders(days)
    trades = []

    # ---- normalize orders into simple trades list ----
    # Adjust keys to your existing JSON shapes if needed.
    for o in orders.get("OrderListResponse", {}).get("orders", []):
        ts = o.get("placedTime") or o.get("executedTime") or o.get("updateTime")
        for leg in o.get("orderLegs", []):
            sym = (leg.get("symbol") or "").upper()
            side = leg.get("side") or o.get("orderAction")  # "BUY"/"SELL"
            for ex in leg.get("executions") or []:
                price = float(ex.get("avgExecPrice") or ex.get("price") or 0)
                qty = int(ex.get("quantity") or 0)
                amt = round(price * qty * (1 if side == "SELL" else -1), 2)
                trades.append(
                    {
                        "time": ts,
                        "symbol": sym,
                        "action": side,
                        "qty": qty,
                        "price": price,
                        "amount": amt,
                    }
                )

    # ---- realized P&L (best available) ----
    realized = 0.0
    tx = list_trade_transactions(days)
    for t in tx.get("TransactionListResponse", {}).get("transactions", []):
        # Many payloads include either explicit gain/loss OR just cash amounts.
        gain = t.get("gainLoss") or t.get("gain") or None
        if gain is not None:
            try:
                realized += float(gain)
                continue
            except Exception:
                pass
        # If no explicit gain, we don------™t synthesize here (needs lot cost basis).
        # Leave it 0.0 rather than guessing. Your tax-lot endpoint (if enabled)
        # can be used later for exact realized.
        # Tip: If you already store avg cost per symbol in your DB, you can
        # compute realized for fully-closed symbols here.

    # newest-first
    trades.sort(key=lambda x: str(x["time"]), reverse=True)
    return trades, round(realized, 2)


from zoneinfo import ZoneInfo


def _to_dt_local(ts, tz="America/New_York"):
    if ts in (None, ""):
        return None
    tzinfo = ZoneInfo(tz)
    # epoch sec/millis
    try:
        iv = int(str(ts))
        return datetime.fromtimestamp(
            iv / (1000 if iv > 10_000_000_000 else 1), tz=tzinfo
        )
    except Exception:
        pass
    s = str(ts).strip().replace("T", " ").replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=tzinfo)
        except Exception:
            pass
    try:
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=tzinfo) if dt.tzinfo is None else dt.astimezone(tzinfo)
    except Exception:
        return None


# --- Realized P&L bucket helpers --------------------------------------------
from zoneinfo import ZoneInfo

_TZ_ET = ZoneInfo("America/New_York")


def _to_dt_local(ts, tz=_TZ_ET):
    """Accepts epoch sec/ms or 'YYYY-MM-DD HH:MM:SS' (naive = ET)."""
    if ts in (None, ""):
        return None
    # epoch?
    try:
        n = int(str(ts))
        return datetime.fromtimestamp(n / (1000 if n > 10_000_000_000 else 1), tz)
    except Exception:
        pass
    s = str(ts).strip().replace("T", " ").replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=tz)
        except Exception:
            continue
    try:
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)
    except Exception:
        return None


# Sum unrealized P&L from your holdings rows
def _sum_unrealized_from_holdings(holdings):
    tot = 0.0
    for h in holdings or []:
        try:
            qty = float(h.get("qty") or 0)
            last = float(h.get("last") or 0)
            paid = float(h.get("price_paid") or 0)
            tot += (last - paid) * qty
        except Exception:
            pass
    return round(tot, 2)


# Sum realized P&L from your recent-trades rows (SELL only)
# Set the start date here (or read from config/env if you prefer)
REALIZED_SINCE = "2025-08-22"


def _sum_realized_from_trades(trades, since_str=REALIZED_SINCE):
    # very forgiving parser for your ------œTime (ET)------ strings
    def _parse_dt(s):
        if not s:
            return None
        s = str(s).replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(s[: len(fmt)], fmt)
            except Exception:
                continue
        return None

    since_dt = _parse_dt(since_str) or datetime.min
    tot = 0.0
    for t in trades or []:
        try:
            if str(t.get("side", "")).upper() != "SELL":
                continue
            tdt = _parse_dt(t.get("time_et") or t.get("time") or t.get("ts"))
            if tdt and tdt < since_dt:
                continue
            qty = float(t.get("qty") or 0)
            price = float(t.get("price") or 0)
            paid = float(t.get("price_paid") or 0)
            tot += (price - paid) * qty
        except Exception:
            pass
    return round(tot, 2)


def _get(path: str, params=None) -> dict:
    # path like "/portfolio.json"
    return (
        b.get_account(
            path if path.startswith("/") else "/" + path.lstrip(), params or {}
        )
        or {}
    )


def fetch_etrade_quote(symbol: str):
    j = _get(f"/v1/market/quote/{symbol}.json").json()
    try:
        qd = j["QuoteResponse"]["QuoteData"][0]
        all = qd.get("All", {})
        last = (
            (all.get("ExtendedHourQuoteDetail", {}) or {}).get("lastPrice")
            or all.get("lastTrade")
            or all.get("closePrice")
        )
        return float(last)
    except Exception:
        return j


# --- Flask app ---
app = Flask(__name__)
setup_logging(app)


@app.route("/debug/oauth")
def debug_oauth():
    import os

    last4 = lambda v: (v[-4:] if v else None)
    return {
        "host": os.getenv("ETRADE_API_HOST") or "https://api.etrade.com",
        "ck": last4(
            os.getenv("ETRADE_CONSUMER_KEY")
            or os.getenv("CONSUMER_KEY")
            or os.getenv("ETRADE_API_KEY")
        ),
        "tok": last4(os.getenv("OAUTH_TOKEN") or os.getenv("ETRADE_OAUTH_TOKEN")),
        "sec": last4(
            os.getenv("OAUTH_TOKEN_SECRET") or os.getenv("ETRADE_OAUTH_TOKEN_SECRET")
        ),
    }


@app.route("/etrade/pin", methods=["GET"])
def etrade_pin_form():
    auth_url = session.get("auth_url")
    if not auth_url or not session.get("req_token") or not session.get("req_secret"):
        # kick off a fresh request token silently, then render the form
        ck = os.getenv("ETRADE_CONSUMER_KEY") or os.getenv("ETRADE_API_KEY")
        cs = os.getenv("ETRADE_CONSUMER_SECRET") or os.getenv("ETRADE_API_SECRET")
        oauth = OAuth1Session(ck, client_secret=cs, callback_uri="oob")
        resp = oauth.fetch_request_token(REQUEST_TOKEN_URL)
        session["req_token"] = resp["oauth_token"]
        session["req_secret"] = resp["oauth_token_secret"]
        auth_url = f"{AUTHORIZE_URL}?key={ck}&token={resp['oauth_token']}"
        session["auth_url"] = auth_url
    return render_template("etrade_pin.html", auth_url=auth_url)


@app.route("/etrade/pin", methods=["POST"])
def etrade_handle_pin():
    verifier = request.form["oauth_verifier"].strip()
    req_token = session.pop("req_token", None)
    req_secret = session.pop("req_secret", None)

    ck = os.getenv("ETRADE_CONSUMER_KEY") or os.getenv("ETRADE_API_KEY")
    cs = os.getenv("ETRADE_CONSUMER_SECRET") or os.getenv("ETRADE_API_SECRET")
    if not (ck and cs and req_token and req_secret and verifier):
        flash("OAuth step missing data. Please start again.", "danger")
        return redirect(url_for("etrade_start_auth"))

    oauth = OAuth1Session(
        ck,
        client_secret=cs,
        resource_owner_key=req_token,
        resource_owner_secret=req_secret,
        verifier=verifier,
    )
    tokens = oauth.fetch_access_token(ACCESS_TOKEN_URL)

    save_tokens(tokens["oauth_token"], tokens["oauth_token_secret"])
    clear_need_auth_flag()

    flash("---œ… E*TRADE authenticated!", "success")
    return redirect(url_for("simulation_view"))


# --- quote helpers for last/prev-close ---------------------------------
def _qnum(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", "0"):
            try:
                return float(v)
            except Exception:
                pass
    return None


def get_last_and_prev(symbol: str, fallback_price: float):
    last = prev = None
    q = fetch_etrade_quote(symbol)
    # A) quote ---†’ last / prev (or derive prev from day delta)
    if isinstance(q, dict):
        last = _qnum(q, "lastTrade", "lastPrice", "intradayLast", "close", "closePrice")
        prev = _qnum(
            q,
            "previousClose",
            "prevClose",
            "priorClose",
            "closePrevDay",
            "closePricePrev",
        )

        # ---† derive prev if missing
        if prev is None and last is not None:
            day_delta = _qnum(
                q,
                "netChange",
                "changeClose",
                "closeNetChange",
                "todaysChangeDollar",
                "change",
                "todaysChange",
            )
            if day_delta is not None:
                prev = float(last) - float(day_delta)
    else:
        try:
            last = float(q)
        except Exception:
            last = None

    # B) fallback: 2-day history
    if prev is None or last is None:
        try:
            try:
                from services.market_service import fetch_data_with_timeout
            except Exception:
                from services.data_fetch import (
                    fetch_data_with_timeout,
                )  # alt module name
            df = fetch_data_with_timeout(symbol, "2d")
            if df is not None:
                import pandas as pd

                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(-1)
                close_col = next(
                    (c for c in df.columns if str(c).lower() == "close"), None
                )
                if close_col:
                    if last is None and len(df) >= 1:
                        last = float(df[close_col].iloc[-1])
                    if prev is None and len(df) >= 2:
                        prev = float(df[close_col].iloc[-2])
        except Exception:
            pass

    if last is None:
        last = float(fallback_price or 0.0)
    return float(last), (None if prev is None else float(prev))


@app.route("/auth/etrade/reconnect", methods=["POST", "GET"])
def auth_etrade_reconnect():
    script = os.path.abspath("auth_shortcut.py")
    if not os.path.exists(script):
        return ("Auth shortcut not found.", 404)
    try:
        if os.name == "nt":
            CREATE_NEW_CONSOLE = 0x00000010
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(
                [sys.executable, script],
                creationflags=CREATE_NEW_CONSOLE | DETACHED_PROCESS,
            )
        else:
            subprocess.Popen([sys.executable, script])
        return ("OK", 200)
    except Exception as e:
        return (f"Failed to launch OAuth flow: {e}", 500)


def get_realized_pl_sum():
    """Legacy alias -> compute realized P&L from the trade ledger."""
    return compute_realized_pnl(get_trades())


def compute_realized_pnl(trades) -> float:
    realized = 0.0
    for t in trades or []:
        if isinstance(t, dict):
            action = (t.get("action") or "").upper()
            if action in {"SELL", "SELL_TO_CLOSE"}:
                realized += float(t.get("pl") or t.get("pnl") or 0.0)
        else:
            # tuple: (trade_time, symbol, action, qty, price, pl, ...)
            action = (str(t[2]) if len(t) > 2 else "").upper()
            if action in {"SELL", "SELL_TO_CLOSE"}:
                try:
                    realized += float(t[5] if len(t) > 5 else 0.0)
                except (TypeError, ValueError):
                    pass
    return realized

# --- Realized P&L buckets used by the Live dashboard -------------------------
from datetime import datetime, timedelta, timezone

def realized_buckets_from_trades(trades):
    """
    Aggregate realized P&L into: week, last_week, month, all.
    Uses SELL rows with 'pl' (realized P&L) and a cost basis to compute
    pct = pnl / cost * 100.
    Accepts any of these timestamp fields on each trade:
      - time_ms (epoch ms, UTC)
      - time_utc ("%Y-%m-%d %H:%M:%S", UTC)
      - time (naive ET string "%Y-%m-%d %H:%M:%S")
    """
    def _et():
        # your file already has _TZ_ET / ET equivalents; this keeps it self-contained
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo("America/New_York")
        except Exception:
            return timezone(timedelta(hours=-4))  # crude fallback

    now = datetime.now(_et())

    # week starts Monday 00:00 ET
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_start
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    acc = {
        "week": {"pnl": 0.0, "cost": 0.0},
        "last_week": {"pnl": 0.0, "cost": 0.0},
        "month": {"pnl": 0.0, "cost": 0.0},
        "all": {"pnl": 0.0, "cost": 0.0},
    }

    def _ts(t):
        if t.get("time_ms"):
            try:
                return datetime.fromtimestamp(float(t["time_ms"]) / 1000.0, tz=timezone.utc).astimezone(_et())
            except Exception:
                pass
        if t.get("time_utc"):
            try:
                return datetime.strptime(t["time_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(_et())
            except Exception:
                pass
        if t.get("time"):
            try:
                # treat as ET
                return datetime.strptime(t["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=_et())
            except Exception:
                pass
        return None

    for tr in trades or []:
        if (tr.get("action") or "").upper() != "SELL":
            continue
        ts = _ts(tr)
        if ts is None:
            continue

        pnl = float(tr.get("pl") or 0.0)

        # Prefer a gross notional if present; else price_paid * qty
        amt = tr.get("amount")
        if amt is not None:
            try:
                cost = abs(float(amt))
            except Exception:
                cost = 0.0
        else:
            try:
                price_paid = float(tr.get("price_paid") or 0.0)
                qty = float(tr.get("qty") or 0.0)
                cost = abs(price_paid * qty)
            except Exception:
                cost = 0.0

        acc["all"]["pnl"] += pnl
        acc["all"]["cost"] += cost
        if ts >= month_start:
            acc["month"]["pnl"] += pnl
            acc["month"]["cost"] += cost
        if last_week_start <= ts < last_week_end:
            acc["last_week"]["pnl"] += pnl
            acc["last_week"]["cost"] += cost
        if ts >= week_start:
            acc["week"]["pnl"] += pnl
            acc["week"]["cost"] += cost

    def _out(key):
        pnl = round(acc[key]["pnl"], 2)
        pct = round((pnl / acc[key]["cost"] * 100.0), 2) if acc[key]["cost"] > 0 else 0.0
        return {"pnl": pnl, "pct": pct}

    return {"week": _out("week"), "last_week": _out("last_week"),
            "month": _out("month"), "all": _out("all")}

# backward-compat wrapper (old code calls this name)
def summarize_realized_buckets(trades):
    return realized_buckets_from_trades(trades)

# --- end helper ----------------------------------------------------------------

def realized_pct(realized_pnl: float, starting_cash: float) -> float:
    return (realized_pnl / starting_cash * 100.0) if starting_cash else 0.0


@app.context_processor
def inject_label_config():
    return {
        "timeframe_labels": label_config.timeframe_labels,
        "sma_length_labels": label_config.sma_length_labels,
        "rsi_len_labels": label_config.rsi_len_labels,
        "rsi_overbought_labels": label_config.rsi_overbought_labels,
        "rsi_oversold_labels": label_config.rsi_oversold_labels,
        "macd_fast_labels": label_config.macd_fast_labels,
        "macd_slow_labels": label_config.macd_slow_labels,
        "macd_signal_labels": label_config.macd_signal_labels,
        "bb_length_labels": label_config.bb_length_labels,
        "bb_std_labels": label_config.bb_std_labels,
        "vol_mult_labels": label_config.vol_mult_labels,
        "vwap_labels": label_config.vwap_labels,
        "trailing_stop_pct_labels": label_config.trailing_stop_pct_labels,
        "sell_after_days_labels": label_config.sell_after_days_labels,
    }


@app.context_processor
def inject_indicator_labels():
    return {
        # ------ SMA lengths ------
        "sma_labels": {
            10: "SMA (10)",
            20: "SMA (20)",
            50: "SMA (50)",
        },
        # ------ RSI lengths ------
        "rsi_len_options": {
            7: "RSI (7)",
            14: "RSI (14)",
            21: "RSI (21)",
        },
        "rsi_len_labels": {
            7: "RSI (7)",
            14: "RSI (14)",
            21: "RSI (21)",
        },
        # ------ RSI thresholds ------
        "rsi_ob_labels": {
            70: "Overbought ---‰¥ 70",
            80: "Overbought ---‰¥ 80",
            90: "Overbought ---‰¥ 90",
        },
        "rsi_os_labels": {
            30: "Oversold ---‰¤ 30",
            20: "Oversold ---‰¤ 20",
            10: "Oversold ---‰¤ 10",
        },
        # ------ MACD EMA labels ------
        "macd_fast_labels": {
            5: "Fast EMA 5",
            8: "Fast EMA 8",
            12: "Fast EMA 12",
        },
        "macd_slow_labels": {
            17: "Slow EMA 17",
            26: "Slow EMA 26",
            35: "Slow EMA 35",
        },
        "macd_signal_labels": {
            5: "Signal EMA 5",
            9: "Signal EMA 9",
            12: "Signal EMA 12",
        },
        # ------ (Optional) MACD presets ------
        "macd_presets": {
            (12, 26, 9): "MACD (12,26,9)",
            (5, 35, 5): "MACD (5,35,5)",
            (8, 17, 9): "MACD (8,17,9)",
        },
        # ------ Bollinger Bands ------
        "bb_length_labels": {
            20: "BB Length 20",
            50: "BB Length 50",
            100: "BB Length 100",
        },
        "bb_std_labels": {
            2.0: "Std Dev Ã—2",
            2.5: "Std Dev Ã—2.5",
            3.0: "Std Dev Ã—3",
        },
        # ------ Volume multiplier ------
        "vol_multiplier_labels": {
            1.0: "Vol ---‰¥ 1Ã— Avg",
            1.5: "Vol ---‰¥ 1.5Ã— Avg",
            2.0: "Vol ---‰¥ 2Ã— Avg",
        },
        # ------ VWAP thresholds ------
        "vwap_threshold_labels": {
            0.0: "VWAP+ ---‰¥ $0.00",
            0.5: "VWAP+ ---‰¥ $0.50",
            1.0: "VWAP+ ---‰¥ $1.00",
        },
        # ------ ATR % filters ------
        "atr_labels": {
            0.5: "ATR ---‰¥ 0.5%",
            1.0: "ATR ---‰¥ 1.0%",
            1.5: "ATR ---‰¥ 1.5%",
        },
        # ------ Daily range % filters ------
        "range_labels": {
            0.5: "Range ---‰¥ 0.5%",
            1.0: "Range ---‰¥ 1.0%",
            1.5: "Range ---‰¥ 1.5%",
        },
        # ------ Pre-market gap-up % filters ------
        "gap_labels": {
            1.0: "Gap ---‰¥ 1.0%",
            2.0: "Gap ---‰¥ 2.0%",
            3.0: "Gap ---‰¥ 3.0%",
        },
    }


def fetch_current_price(symbol):
    try:
        price = fetch_etrade_quote(symbol)
        return float(price)
    except Exception as e:
        logging.warning(f"[PRICE] {symbol}: E*TRADE fetch failed ({e})")
        raise


def extract_backtest_settings(args):
    # figure out end_date = today, start_date = today - timeframe
    tf = args.get("timeframe", "6mo")
    today = date.today()
    delta = TIMEFRAME_DELTAS.get(tf, {"months": 6})
    start = today - relativedelta(**delta)
    end = today


# ------ 1) Define your settings tuples ------------------------------------------------------------------------------------------------------------


BacktestSettings = namedtuple(
    "BacktestSettings",
    [
        # date & capital
        "start_date",
        "end_date",
        "starting_cash",
        "max_per_trade",
        "timeframe",
        # core entry toggles
        "sma_on",
        "rsi_on",
        "macd_on",
        "bb_on",
        "vol_on",
        "vwap_on",
        "news_on",
        # core numeric parameters
        "sma_length",
        "rsi_len",
        "rsi_overbought",
        "rsi_oversold",
        "macd_fast",
        "macd_slow",
        "macd_signal",
        "bb_length",
        "bb_std",
        "vol_multiplier",
        "vwap_threshold",
        # advanced entry flags
        "rsi_slope_on",
        "macd_hist_on",
        "bb_breakout_on",
        "price_sma_on",
        "atr_on",
        "atr_pct",
        "range_on",
        "range_pct",
        "gap_on",
        "gap_pct",
        # exit behavior
        "single_entry_only",
        "use_trailing_stop",
        "trailing_stop_pct",
        "sell_after_days",
        "stop_loss_pct",
        "take_profit_pct",
    ],
)

SimulationSettings = namedtuple(
    "SimulationSettings",
    [
        # ------ entry toggles ------
        "sma_on",
        "rsi_on",
        "macd_on",
        "bb_on",
        "vol_on",
        "vwap_on",
        "news_on",
        # ------ entry numeric ------
        "sma_length",
        "rsi_len",
        "rsi_overbought",
        "rsi_oversold",
        "macd_fast",
        "macd_slow",
        "macd_signal",
        "bb_length",
        "bb_std",
        "vol_multiplier",
        "vwap_threshold",
        # ------ advanced entry filters ------
        "atr_on",
        "atr_pct",
        "range_on",
        "range_pct",
        "gap_on",
        "gap_pct",
        "price_sma_on",
        # ------ extra entry/exit toggles ------
        "rsi_slope_on",
        "macd_hist_on",
        "bb_breakout_on",
        "single_entry_only",
        "use_trailing_stop",
        # ------ exit behavior ------
        "trailing_stop_pct",
        "sell_after_days",
        "stop_loss_pct",
        "take_profit_pct",
        # ------ capital settings ------
        "starting_cash",
        "max_per_trade",
    ],
)

# ------ 2) Extract backtest settings from args ------------------------------------------------------------------------------------


def extract_backtest_settings(args):
    return BacktestSettings(
        # date & capital
        start_date=args.get("start_date"),
        end_date=args.get("end_date"),
        starting_cash=float(args.get("starting_cash", 10000)),
        max_per_trade=float(args.get("max_per_trade", 1000)),
        timeframe=args.get("timeframe"),
        # core entry filters
        sma_on="sma_on" in args,
        rsi_on="rsi_on" in args,
        macd_on="macd_on" in args,
        bb_on="bb_on" in args,
        vol_on="vol_on" in args,
        vwap_on="vwap_on" in args,
        news_on="news_on" in args,
        rsi_slope_on="rsi_slope_on" in args,
        macd_hist_on="macd_hist_on" in args,
        bb_breakout_on="bb_breakout_on" in args,
        price_sma_on="price_sma_on" in args,
        atr_on="atr_on" in args,
        range_on="range_on" in args,
        gap_on="gap_on" in args,
        # core numeric parameters
        sma_length=int(args.get("sma_length", 20)),
        rsi_len=int(args.get("rsi_len", 14)),
        rsi_overbought=int(args.get("rsi_ob", 70)),
        rsi_oversold=int(args.get("rsi_os", 30)),
        macd_fast=int(args.get("macd_fast", 12)),
        macd_slow=int(args.get("macd_slow", 26)),
        macd_signal=int(args.get("macd_signal", 9)),
        bb_length=int(args.get("bb_length", 20)),
        bb_std=float(args.get("bb_std", 2.0)),
        vol_multiplier=float(args.get("vol_multiplier", 1.0)),
        vwap_threshold=float(args.get("vwap_threshold", 0.0)),
        # advanced entry filters
        atr_pct=float(args.get("atr_pct", 1.0)) / 100,
        range_pct=float(args.get("range_pct", 1.0)) / 100,
        gap_pct=float(args.get("gap_pct", 2.0)) / 100,
        # exit behavior
        single_entry_only="single_entry_only" in args,
        use_trailing_stop="use_trailing_stop" in args,
        trailing_stop_pct=float(args.get("trailing_stop_pct", 0.0)),
        sell_after_days=int(args.get("sell_after_days"))
        if args.get("sell_after_days")
        else None,
        stop_loss_pct=float(args.get("stop_loss_pct") or 0.0),
        take_profit_pct=float(args.get("take_profit_pct") or 0.0),
    )


# ------ 3) Extract simulation settings from args ------------------------------------------------------------------------------


def load_your_symbols():
    # reads your SP500 list
    settings = extract_simulation_settings(cfg)

    # make sure you load or define your symbols before calling the loop
    with open("sp500_symbols.txt") as f:
        symbols = [line.strip() for line in f if line.strip()]

    # pass both settings and symbols
    run_simulation_loop(settings, symbols)


BACKTEST_DB = "backtest.db"


from pathlib import Path

from services.risk_management import enforce_settlement, enforce_wash_sale
from services.settings_schema import BacktestSettings, extract_backtest_settings

# ------------ Persistence ------------------------------------------------------------------------------------------------------------------------------------------
SETTINGS_FILE = Path(__file__).parent / "settings.json"

TIMEFRAME_DELTAS = {
    "1d": timedelta(days=1),
    "1h": timedelta(hours=1),
    "15m": timedelta(minutes=15),
    # ------¦etc------¦
}


def load_settings(defaults: dict = None) -> dict:
    """
    Load dashboard settings from JSON, then overlay them onto `defaults` if provided.
    """
    saved = {}
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text())
        except json.JSONDecodeError:
            saved = {}

    if defaults is None:
        return saved
    merged = defaults.copy()
    merged.update(saved)
    return merged


def save_settings(settings: dict) -> None:
    """
    Persist the given settings dict to JSON.
    """
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))


@app.route("/backtest", methods=["GET", "POST"])
@app.route("/backtest", methods=["GET", "POST"])
def backtest_view():
    defaults = BacktestSettings().__dict__
    settings_dict = load_settings(defaults)
    settings = extract_backtest_settings(request.values)

    trades, summary = None, None
    if request.method == "POST":
        save_settings(settings.__dict__)
        delta_args = TIMEFRAME_DELTAS[settings.timeframe]
        settings.start_date = datetime.now().date() - relativedelta(**delta_args)
        settings.end_date = datetime.now().date()

        symbols = get_symbols(simulation=True)
        trades, summary = run_full_backtest(
            settings,
            symbols,
            wash_sale=enforce_wash_sale,
            settlement=enforce_settlement,
        )
        summary = SimpleNamespace(**summary)

    return render_template(
        "backtest.html",
        settings=settings,
        trades=trades,
        summary=summary,
    )


@app.route("/scanner_status")
def scanner_status():
    return jsonify(running=_is_scanner_running, needs_auth=_needs_auth)


from services.settings_service import TIMEFRAME_DELTAS, load_settings, save_settings
from settings import BACKTEST_DB


@app.route("/run_backtest", methods=["POST"])
def run_backtest_route():
    # 1) Build a BacktestSettings from the form
    settings = extract_backtest_settings(request.form)
    # 2) Override the two numeric fields directly
    settings.starting_cash = float(
        request.form.get("starting_cash", settings.starting_cash)
    )
    settings.max_per_trade = float(
        request.form.get("max_per_trade", settings.max_per_trade)
    )

    # 3) Reset the backtest DB
    init_backtest_db()

    # 4) Run the backtest
    symbols = get_symbols(simulation=True)
    result = run_full_backtest(
        settings, symbols, wash_sale=enforce_wash_sale, settlement=enforce_settlement
    )

    # 5) Normalize result
    if not (isinstance(result, tuple) and len(result) == 2):
        flash(
            "---š ï¸ Backtest didn------™t produce any data------”showing an empty run",
            "warning",
        )
        trades = []
        summary = {
            "total_pnl": 0.0,
            "num_trades": 0,
            "wins": 0,
            "losses": 0,
            "by_symbol": {},
        }
    else:
        trades, summary = result

    # 6) Log this run
    conn = sqlite3.connect(BACKTEST_DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO backtest_runs (started_at, settings_json) VALUES (?, ?)",
        (datetime.utcnow().isoformat(), json.dumps(asdict(settings))),
    )
    run_id = cur.lastrowid

    for t in trades:
        cur.execute(
            """
            INSERT INTO backtest_trades
              (run_id, symbol, date, action, price, qty, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                t["symbol"],
                t["date"],
                t["action"],
                t["price"],
                t["qty"],
                t["pnl"],
            ),
        )
    conn.commit()
    conn.close()

    flash("---œ… Backtest run complete!")

    # 7) Render the same template------”labels come from your context processor
    return render_template(
        "backtest.html",
        settings=settings,
        trades=trades,
        summary=SimpleNamespace(**summary),
    )


@app.route("/stop_scanner", methods=["POST"])
def stop_scanner():
    global _is_scanner_running
    stop_simulation()
    _is_scanner_running = False
    flash("---›” Simulation stopped", "danger")
    return redirect(url_for("simulation"))


@app.route("/run-checkpoint")
def run_checkpoint():
    bat_path = os.path.join(os.getcwd(), "checkpoint.bat")  # Adjust path if needed
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "cmd.exe", "/k", bat_path], shell=True
        )
        return redirect(url_for("index"))
    except Exception as e:
        return f"Error executing batch: {e}", 500


### ------------------------------------------ ALERTS (LIST & CLEAR) ------------------------------------------ ###


@app.route("/nuke_db", methods=["POST"])
def nuke_db():
    try:
        result = subprocess.run(
            ["python", "init_alerts_db.py"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            flash("---œ… Database nuked and recreated!", "success")
        else:
            flash(f"---Œ Nuke failed: {result.stderr}", "danger")
    except Exception as e:
        flash(f"---Œ Error nuking DB: {e}", "danger")
    return redirect(url_for("index"))


import os

from flask import make_response
from reportlab.lib.styles import getSampleStyleSheet

@app.route("/export_backtest_pdf")
def export_backtest_pdf():
    # 1) rebuild settings & run backtest
    settings = extract_backtest_settings(request.args)

    # DEBUG: log out the settings we received
    app.logger.debug(f"PDF export settings: {settings}")

    # 2) Load symbols and run backtest
    symbols = get_symbols(simulation=True)
    trades, summary_dict = run_full_backtest(settings, symbols)
    summary = SimpleNamespace(**summary_dict)

    # ------¦ rest of your export logic ------¦

    # 2) PDF setup
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()

    # Ensure you have registered a Unicode-capable font earlier:
    #   pdfmetrics.registerFont(TTFont('UnicodeFont', font_path))
    #   unicode_font_name = 'UnicodeFont'
    unicode_title = ParagraphStyle(
        "UnicodeTitle",
        parent=styles["Title"],
        fontName=unicode_font_name,
        fontSize=24,
        alignment=1,
    )
    unicode_style = ParagraphStyle(
        "Unicode", parent=styles["Normal"], fontName=unicode_font_name
    )

    elems = []

    # 3) ðŸš--- Title
    elems.append(Spacer(1, 12))
    elems.append(Paragraph("ðŸš--- TradeAlerts ðŸš---", unicode_title))
    elems.append(Spacer(1, 12))

    # 4) Summary table
    summary_data = [
        ["Starting Cash", f"${settings.starting_cash:.2f}"],
        ["Total P&L", f"${summary.total_pnl:.2f}"],
        ["Current Cash", f"${settings.starting_cash + summary.total_pnl:.2f}"],
        ["P&L %", f"{(summary.total_pnl / settings.starting_cash * 100):.2f}%"],
        ["Total Trades", str(summary.num_trades)],
        ["Win %", f"{summary.win_rate_pct:.1f}%"],
        ["Avg P/L / Trade", f"${summary.avg_pnl_per_trade:.2f}"],
        ["Best Trade", f"${summary.best_trade_pnl:.2f}"],
        ["Worst Trade", f"${summary.worst_trade_pnl:.2f}"],
    ]
    tbl = Table(summary_data, hAlign="CENTER")
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (1, 0), "#a8d8ea"),
                ("TEXTCOLOR", (0, 0), (1, 0), "white"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    elems.append(tbl)
    elems.append(Spacer(1, 12))

    # 5) Enabled indicators (human-readable)
    indicator_labels = []

    # Core toggles:
    if settings.sma_on:
        indicator_labels.append(f"SMA ({settings.sma_length})")
    if settings.rsi_on:
        indicator_labels.append(f"RSI ({settings.rsi_len})")
    if settings.macd_on:
        indicator_labels.append(
            f"MACD ({settings.macd_fast},{settings.macd_slow},{settings.macd_signal})"
        )
    if settings.bb_on:
        indicator_labels.append(f"BB ({settings.bb_length},Ïƒ={settings.bb_std})")
    if settings.vol_on:
        indicator_labels.append(f"Vol ---‰¥ {settings.vol_multiplier}Ã—")
    if settings.vwap_on:
        indicator_labels.append("VWAP+")
    if settings.news_on:
        indicator_labels.append("News")

    # Advanced entry filters:
    if getattr(settings, "rsi_slope_on", False):
        indicator_labels.append("RSI Slope ---¤´")
    if getattr(settings, "macd_hist_on", False):
        indicator_labels.append("MACD Hist ðŸ“Š")
    if getattr(settings, "bb_breakout_on", False):
        indicator_labels.append("BB Breakout ðŸ’¥")
    if getattr(settings, "price_sma_on", False):
        indicator_labels.append(f"Price>SMA({settings.sma_length})")
    if getattr(settings, "atr_on", False):
        indicator_labels.append(f"ATR ---‰¥ {settings.atr_pct*100:.1f}%")
    if getattr(settings, "range_on", False):
        indicator_labels.append(f"Range ---‰¥ {settings.range_pct*100:.1f}%")
    if getattr(settings, "gap_on", False):
        indicator_labels.append(f"Gap ---‰¥ {settings.gap_pct*100:.1f}%")

    elems.append(Paragraph("Enabled Indicators:", styles["Heading3"]))
    elems.append(Spacer(1, 6))
    elems.append(Paragraph(", ".join(indicator_labels), unicode_style))
    elems.append(Spacer(1, 12))

    # 6) Trade log
    data = [["Symbol", "Date", "Action", "Price", "Qty", "P/L"]] + [
        [
            t["symbol"],
            t["date"],
            t["action"],
            f"{t['price']:.2f}",
            str(t["qty"]),
            f"{t['pnl']:.2f}" if t.get("pnl") is not None else "",
        ]
        for t in trades
    ]
    trade_tbl = Table(data, hAlign="CENTER")
    trade_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ]
        )
    )
    elems.append(trade_tbl)

    # 7) Finish and send
    doc.build(elems)
    buf.seek(0)
    return send_file(
        buf, mimetype="application/pdf", download_name="backtest_report.pdf"
    )


@app.route("/clear_all", methods=["POST"])
def clear_all_alerts():
    print("---œ… /clear_all route hit")
    conn = sqlite3.connect(ALERTS_DB)
    conn.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/clear/<int:id>", methods=["POST"])
def clear_alert(id):
    try:
        conn = sqlite3.connect(ALERTS_DB)
        conn.execute("DELETE FROM alerts WHERE id=?", (id,))
        conn.commit()
        conn.close()
        print(f"---œ… Cleared alert #{id}")
        return jsonify({"success": True})
    except Exception as e:
        print(f"---Œ Error clearing alert #{id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/launch_auth", methods=["POST"])
def launch_auth():
    try:
        subprocess.Popen(
            ["start", "cmd", "/k", "python", "etrade_auth_flow.py"], shell=True
        )
        flash("ðŸ”‘ E*TRADE Auth flow launched in new window.", "info")
    except Exception as e:
        flash(f"---Œ Error launching E*TRADE Auth: {e}", "danger")
    return redirect(url_for("index"))


# ------ 2) run_backtest: wipe + run + log to DB ------------------------------------------------------------------------------------------------------------

# at top of Dashboard.py
BACKTEST_DB = os.path.join(os.getcwd(), "backtest.db")


from services.trading_helpers import setup_simulation_db  # you already have this


@app.route("/simulation/reset", methods=["POST"])
def nuke_simulation_db():
    # re------initialize your simulation schema
    setup_simulation_db()
    flash("Simulation DB reset!", "success")
    return redirect(url_for("simulation"))


@app.route("/reset_backtest", methods=["POST"])
def reset_backtest():
    subprocess.run(["python", "init_backtest_db.py"], check=True)
    flash("---œ… Backtest DB reset!", "success")
    return redirect(url_for("backtest_view"))


def simulation():
    raw_trades = get_trades()
    formatted_trades = []

    # DEBUG: inspect first trade to see its shape
    if raw_trades:
        print("ðŸ” raw_trades[0] =", raw_trades[0])

    for t in raw_trades:
        # Case A: dict
        if isinstance(t, dict):
            trade_time = t.get("trade_time") or t.get("timestamp")
            symbol = t.get("symbol")
            action = t.get("action")
            qty = t.get("qty")
            # coerce to numeric so Jinja sees real numbers
            price_str = t.get("price")
            pnl_str = t.get("pnl") or t.get("pl")
            price = float(t.get("price"))
            pl = float(t.get("pnl") or t.get("pl"))

        # Case B: tuple
        elif isinstance(t, tuple):
            # Adjust this unpack order to match your service------™s return
            trade_time, symbol, action, qty, price, pnl = t

        else:
            # Unexpected type; skip
            continue

    formatted_trades.append(
        {
            "timestamp": t.get("timestamp"),
            "symbol": t.get("symbol"),
            "action": t.get("action"),
            "qty": int(t.get("qty")),
            "price": price,
            "pl": pl,
        }
    )

    return render_template(
        "simulation.html",
        cash=cash,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        realized_pnl_pct=realized_pnl_pct,
        realized_pnl=realized_pnl,
        holdings=formatted_holdings,
        history=formatted_trades,
    )


# dashboard.py
from services.etrade_service import fetch_etrade_quote


@app.route("/simulation/status")
def simulation_status():
    quotes = []
    for symbol, qty, avg_cost, last in get_holdings():
        try:
            lp = fetch_etrade_quote(symbol)
        except Exception:
            lp = last
        quotes.append({"symbol": symbol, "last_price": float(lp)})
    return {"ok": True, "quotes": quotes}


@app.route("/export/simulation")
def export_simulation():
    # --- always-safe locals ---
    cash = get_cash()
    holdings = get_holdings()
    trades = get_trades()

    realized_pnl = 0.0
    unrealized_pnl = 0.0
    realized_pnl_pct = 0.0  # will be computed later
    unrealized_pnl_pct = 0.0

    # --- time formatter ---
    def format_trade_time(ts):
        from datetime import datetime

        if isinstance(ts, datetime):
            return ts.strftime("%Y-%m-%d %H:%M:%S")
        try:
            dt = datetime.fromisoformat(str(ts))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(ts).split(".")[0]

    # ---- Prepare holdings as dicts for calculations ----
    holding_dicts = []
    for h in holdings:
        if isinstance(h, dict):
            symbol = h.get("symbol", "")
            qty = h.get("qty", 0)
            price_paid = h.get("price_paid", 0.0)
            last_price = h.get("last_price", 0.0)
        else:  # tuple fallback
            symbol = h[0] if len(h) > 0 else ""
            qty = h[1] if len(h) > 1 else 0
            price_paid = h[2] if len(h) > 2 else 0.0
            last_price = h[3] if len(h) > 3 else 0.0

        change = change_pct = total_gain = day_gain = value = 0.0
        try:
            price_paid = float(price_paid)
            qty = int(qty)
            # always prefer live from E*TRADE
            live = float(fetch_etrade_quote(symbol) or last_price or price_paid or 0.0)
            last_price = live
            change = last_price - price_paid
            change_pct = (change / price_paid * 100.0) if price_paid else 0.0
            total_gain = change * qty
            day_gain = (
                total_gain  # TODO: replace with true day gain if you track prev_close
            )
            value = last_price * qty
        except Exception as e:
            print(f"[EXPORT] Error for symbol {symbol}: {e}")

        holding_dicts.append(
            {
                "symbol": symbol,
                "qty": qty,
                "price_paid": price_paid,
                "last_price": last_price,
                "change": change,
                "change_pct": change_pct,
                "day_gain": day_gain,
                "total_gain": total_gain,
                "value": value,
            }
        )

    # ---- Recompute unrealized P&L from holdings ----
    unrealized_pnl = round(sum(h.get("total_gain", 0.0) for h in holding_dicts), 2)
    total_cost_basis = sum(
        (h["qty"] or 0) * (h["price_paid"] or 0.0) for h in holding_dicts
    )
    unrealized_pnl_pct = (
        round((unrealized_pnl / total_cost_basis * 100.0), 2)
        if total_cost_basis
        else 0.0
    )

    # ---- Build trade history & realized P&L ----
    history = []
    for t in trades:
        if isinstance(t, dict):
            pl_val = float(t.get("pl") or t.get("pnl") or 0.0)
            trade_time = t.get("trade_time") or t.get("timestamp") or t.get("time")
            history.append(
                {
                    "time": format_trade_time(trade_time),
                    "symbol": t.get("symbol"),
                    "action": t.get("action"),
                    "qty": t.get("qty"),
                    "price": t.get("price"),
                    "pl": pl_val,
                }
            )
        else:
            trade_time, symbol, action, qty, price, pl = t[:6]
            try:
                pl_val = float(pl)
            except (TypeError, ValueError):
                pl_val = 0.0
            history.append(
                {
                    "time": format_trade_time(trade_time),
                    "symbol": symbol,
                    "action": action,
                    "qty": qty,
                    "price": price,
                    "pl": pl_val,
                }
            )

    # Use the same calculation as the dashboard
    realized_pnl = compute_realized_pnl(trades)

    realized_pnl_pct = realized_pct(realized_pnl, start_cash)

    # ---- Now that _starting_cash is set, compute realized % ----
    realized_pnl_pct = (realized_pnl / start_cash * 100.0) if start_cash else 0.0
    # ---- CSV export ----
    import csv
    import io

    si = io.StringIO()
    cw = csv.writer(si)

    cw.writerow(["Cash", f"${cash:.2f}"])
    cw.writerow(["Unrealized P&L", f"${unrealized_pnl:.2f}"])
    cw.writerow(["Unrealized P&L %", f"{unrealized_pnl_pct:.2f}%"])
    cw.writerow(["Realized P&L", f"${realized_pnl:.2f}"])
    cw.writerow(["Realized P&L %", f"{realized_pnl_pct:.2f}%"])
    cw.writerow([])

    cw.writerow(["-- HOLDINGS --"])
    cw.writerow(
        [
            "symbol",
            "last_price",
            "change",
            "change_pct",
            "qty",
            "price_paid",
            "day_gain",
            "total_gain",
            "value",
        ]
    )
    for h in holding_dicts:
        cw.writerow(
            [
                h["symbol"],
                f"${(h['last_price'] or 0.0):.2f}",
                f"${(h['change'] or 0.0):.2f}",
                f"{(h['change_pct'] or 0.0):.1f}%",
                int(h["qty"] or 0),
                f"${(h['price_paid'] or 0.0):.2f}",
                f"${(h['day_gain'] or 0.0):.2f}",
                f"${(h['total_gain'] or 0.0):.2f}",
                f"${(h['value'] or 0.0):.2f}",
            ]
        )

    cw.writerow([])
    cw.writerow(["-- TRADES --"])
    cw.writerow(["timestamp", "symbol", "action", "qty", "price", "pl", "pl_pct"])
    for t in history:
        try:
            qty = int(t["qty"] or 0)
            price_val = float(t["price"] or 0.0)
            pl_val = float(t["pl"] or 0.0)
            pl_pct = (pl_val / (price_val * qty) * 100.0) if price_val and qty else 0.0
        except (TypeError, ValueError):
            qty = 0
            price_val = 0.0
            pl_val = 0.0
            pl_pct = 0.0

        cw.writerow(
            [
                t["time"],
                t["symbol"],
                t["action"],
                qty,
                f"{price_val:.2f}",
                f"{pl_val:.2f}",
                f"{pl_pct:.2f}%",
            ]
        )

    resp = make_response(si.getvalue())
    resp.headers["Content-Disposition"] = "attachment; filename=simulation.csv"
    resp.headers["Content-type"] = "text/csv"
    return resp


@app.route("/start_scanner", methods=["POST"])
def start_scanner():
    global _is_scanner_running

    setup_simulation_db()
    symbols = get_symbols(simulation=True)
    _is_scanner_running = True
    t = threading.Thread(target=run_simulation_loop, args=(sim_settings,), daemon=True)
    t.start()

    flash("---–¶ï¸ Simulation started (DB nuked first)", "success")
    return redirect(
        url_for("simulation", starting_cash=starting_cash, max_per_trade=max_per_trade)
    )


# near the top of Dashboard.py
DEFAULT_STARTING_CASH = 10000.0
DEFAULT_MAX_PER_TRADE = 1000.0

from services.trading_helpers import (
    get_cash,
)

# at the very top, with your other imports


# at the top of Dashboard.py, make sure cost_basis is defined as we did earlier
def cost_basis(symbol):
    """
    Returns the average price paid per share for all BUY trades of a given symbol.
    """
    trades = get_trades()
    total_qty = 0
    total_cost = 0.0
    for t in trades:
        if isinstance(t, dict):
            sym = t.get("symbol")
            action = t.get("action")
            qty = t.get("qty", 0)
            price = t.get("price", 0.0)
        elif isinstance(t, (tuple, list)):
            # (timestamp, symbol, action, qty, price, pl)
            _, sym, action, qty, price, *_ = t
        else:
            continue

        try:
            qty = int(qty)
            price = float(price)
        except Exception:
            continue

        if sym == symbol and action.upper() == "BUY":
            total_qty += qty
            total_cost += qty * price

    return (total_cost / total_qty) if total_qty else 0.0


from flask import Blueprint

from services.trading_helpers import (
    get_cash,
    setup_simulation_db,
)

sim_bp = Blueprint("simulation", __name__)
from services.trading_helpers import get_cash


@sim_bp.route("/simulation/reset", methods=["POST"])
def reset_sim():
    # 1) Rebuild all tables:
    setup_simulation_db()

    # 2) Load your JSON config and apply starting cash:
    cfg = json.load(open("simulation_config.json"))
    settings = extract_simulation_settings(cfg)
    set_cash(settings.starting_cash)
    logging.info(f"[SIM] Seed cash set to: ${get_cash():.2f}")
    return redirect(url_for("simulation.simulation"))


import pytz

from services.trading_helpers import (
    get_cash,
)


# --- helpers -------------------------------------------------
def _quote_prev_close(q):
    """Try to pull 'previous close' from an E*TRADE quote dict."""
    if isinstance(q, dict):
        for k in (
            "previousClose",
            "prevClose",
            "priorClose",
            "closePrevDay",
            "closePricePrev",
            "prevDayClose",
        ):
            v = q.get(k)
            if v not in (None, 0, "0", ""):
                try:
                    return float(v)
                except:
                    pass
    return None


# --- route ---------------------------------------------------
@app.route("/simulation")
def simulation_view():
    def format_trade_time(ts):
        try:
            # Parse whatever type we get into a datetime
            if not isinstance(ts, datetime):
                ts = datetime.fromisoformat(str(ts).split(".")[0])

            # Convert UTC ---†’ Eastern
            eastern = pytz.timezone("America/New_York")
            if ts.tzinfo is None:
                ts = pytz.UTC.localize(ts)  # assume stored in UTC
            ts = ts.astimezone(eastern)

            return ts.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(ts).split(".")[0]

    # Load settings FIRST so it's available everywhere

    # 1) pull cash
    cash = get_cash()

    # 2) pull raw holdings
    raw = get_holdings()

    # 3) normalize holdings
    holdings = [
        {
            "symbol": s,
            "qty": int(q or 0),
            "price_paid": float(ac or 0.0),
            "last_price": float(lp or 0.0),
            "day_gain": 0.0,
            "total_gain": 0.0,
            "change": 0.0,
            "change_pct": 0.0,
            "value": 0.0,
        }
        for (s, q, ac, lp) in raw
    ]

    # 4) enrich each holding
    for h in holdings:
        try:
            symbol = h["symbol"]
            qty = int(h["qty"] or 0)
            price_paid = float(h["price_paid"] or 0.0)

            last, prev_close = get_last_and_prev(symbol, price_paid)

            # change from cost basis (what your Change / Change % columns show)
            change_from_cost = last - price_paid
            change_from_cost_pct = (
                (change_from_cost / price_paid * 100.0) if price_paid else 0.0
            )

            # day change = last - previous close (if we have prev)
            day_change = (last - prev_close) if prev_close is not None else 0.0

            # write back to row
            h["last_price"] = round(last, 2)
            h["change"] = round(change_from_cost, 2)
            h["change_pct"] = round(change_from_cost_pct, 1)
            h["day_gain"] = round(day_change * qty, 2)
            h["total_gain"] = round(change_from_cost * qty, 2)
            h["value"] = round(last * qty, 2)

        except Exception as e:
            print(f"[SIM] Error updating holding {h.get('symbol','?')}: {e}")

    # 5) SUMMARY NUMBERS
    total_cost_basis = sum(h["qty"] * float(h["price_paid"]) for h in holdings)
    unrealized_pnl = round(sum(float(h.get("total_gain") or 0.0) for h in holdings), 2)
    unrealized_pnl_pct = (
        round(unrealized_pnl / total_cost_basis * 100.0, 2) if total_cost_basis else 0.0
    )

    # 6) TRADE HISTORY
    history = []
    for t in get_trades():
        if isinstance(t, dict):
            pl_val = float(t.get("pl") or t.get("pnl") or 0.0)
            trade_time = t.get("trade_time") or t.get("timestamp") or t.get("time")
            history.append(
                {
                    "time": format_trade_time(trade_time),
                    "symbol": t.get("symbol"),
                    "action": t.get("action"),
                    "qty": t.get("qty"),
                    "price": t.get("price"),
                    "pl": pl_val,
                }
            )
        else:
            trade_time, symbol, action, qty, price, pl = t[:6]
            try:
                pl_val = float(pl)
            except (TypeError, ValueError):
                pl_val = 0.0
            history.append(
                {
                    "time": format_trade_time(trade_time),
                    "symbol": symbol,
                    "action": action,
                    "qty": qty,
                    "price": price,
                    "pl": pl_val,
                }
            )

    realized_pnl = round(get_realized_pl_sum(), 2)
    start_cash = get_starting_cash_safe()
    realized_pnl_pct = (realized_pnl / start_cash * 100.0) if start_cash else 0.0
    total_buy_cost = sum(
        (t.get("qty") or 0) * (t.get("price") or 0.0)
        for t in history
        if t.get("action") == "BUY"
    )

    # --- Realized P&L & % (from trade history; % uses starting cash) ---
    realized_pnl = compute_realized_pnl(get_trades())

@app.route("/simulation/buy", methods=["POST"])
def simulation_buy():
    try:
        data = request.get_json(force=True)
        symbol = data.get("symbol")
        qty = int(data.get("qty", 1))

        # 1) Validate
        if not symbol or qty <= 0:
            return jsonify(success=False, error="Invalid symbol or quantity"), 400
        quote_data = fetch_etrade_quote(symbol)
        if isinstance(quote_data, dict):
            # tweak these keys if your API returns different field names
            price = float(
                quote_data.get("lastTrade") or quote_data.get("closePrice") or 0
            )
        else:
            price = float(quote_data)

        current_app.logger.info(f"ðŸ’² Using E*TRADE price for {symbol}: {price}")

        # 3) Perform the buy with the live price
        result = buy_stock(symbol, qty, price)
        if result:
            return jsonify(success=True), 200
        else:
            current_app.logger.error("---Œ buy_stock() returned False")
            return jsonify(success=False, error="buy_stock() returned False"), 500

    except Exception as e:
        current_app.logger.exception("ðŸš¨ Exception in simulation_buy")
        return jsonify(success=False, error=str(e)), 500

    flash("---œ… Backtest run complete!", "success")
    return redirect(url_for("backtest_view", **request.form))


@app.route("/simulation/reset", methods=["POST"])
def reset_simulation():
    # read the default starting cash from a hidden form field or query string
    default_cash = float(request.form.get("starting_cash", 10000))
    set_cash(default_cash)
    # clear out any trades/holdings if you want
    nuke_simulation_db()
    flash(f"Simulation reset: cash back to ${default_cash:,.2f}", "info")
    return redirect(url_for("simulation"))


@app.route("/simulation/sell", methods=["POST"])
def simulation_sell():
    data = request.get_json()
    symbol = data.get("symbol")
    qty = int(data.get("qty", 0))
    if not symbol or qty <= 0:
        return jsonify({"error": "Invalid symbol or quantity"}), 400

    try:
        price = get_etrade_price(symbol)
        sell_stock(symbol, qty, price)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(
        {"success": True, "cash": get_cash(), "realized_pl": get_realized_pl()}
    ), 200


@app.route("/export_alerts")
def export_alerts():
    # pull your alerts from the DB (or your service)
    alerts = get_alerts()

    # Build CSV in memory
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Symbol", "Last Match", "Filters"])

    # Adjust these keys to whatever your alert dict actually uses:
    for a in alerts:
        last = a.get("last_match_time")  # or .get('timestamp') if that's your field
        filters = ";".join(a.get("matched_filters", []))
        writer.writerow([a["symbol"], last, filters])

    # Return as downloadable attachment
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=alerts.csv"},
    )


@app.route("/export_backtest")
def export_backtest():
    # 1) Rebuild the BacktestSettings from the same query-string
    settings = extract_backtest_settings(request.args)

    # 2) Open your backtest.db
    conn = sqlite3.connect(BACKTEST_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 3) Grab the most recent run_id (order by started_at, not timestamp)
    row = cur.execute(
        "SELECT id FROM backtest_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        flash("---Œ No backtest run in the database to export.", "warning")
        return redirect(url_for("backtest_view"))
    run_id = row["id"]

    # 4) Pull all trade rows for that run
    trades = cur.execute(
        """SELECT symbol, date, action, price, qty, pnl
           FROM backtest_trades
           WHERE run_id = ?
           ORDER BY date""",
        (run_id,),
    ).fetchall()
    conn.close()

    # 5) Build the CSV in memory
    buf = io.StringIO()
    writer = csv.writer(buf)

    # 5a) Dump your settings first
    writer.writerow(["# Backtest Settings"])
    for key, val in settings._asdict().items():
        writer.writerow([key, val])
    writer.writerow([])

    # 5b) Dump the trades
    writer.writerow(["Symbol", "Date", "Type", "Price", "Qty", "P/L"])
    for t in trades:
        writer.writerow(
            [t["symbol"], t["date"], t["action"], t["price"], t["qty"], t["pnl"]]
        )

    # 6) Return as an attachment
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=backtest.csv"},
    )


# in dashboard.py
from services.trading_helpers import get_cash, get_cash_ledger, setup_simulation_db


def check_cash_sync():
    try:
        ledger = get_cash_ledger()
        stored = get_cash()
        if abs(ledger - stored) > 0.01:
            app.logger.warning(
                f"[CASH] MISMATCH: ledger=${ledger:.2f} stored=${stored:.2f}"
            )
            # Optional: set_cash(ledger)
    except Exception as e:
        app.logger.error(f"[CASH] check failed: {e}")


# Run once on first real request (Flask 3-safe)
@app.before_request
def _run_cash_sync_once():
    if not getattr(app, "_cash_synced", False):
        check_cash_sync()
        app._cash_synced = True


@app.route("/admin/cash/reconcile", methods=["POST", "GET"])
def reconcile_cash():
    try:
        ledger = get_cash_ledger()
        set_cash(ledger)
        return f"Stored cash set to ${ledger:.2f}\n", 200
    except Exception as e:
        app.logger.exception(e)
        return f"Reconcile failed: {e}\n", 500


@app.route("/")
def index():
    setup_simulation_db()


    # --- Helper for formatting trade times (single definition) ---
    def format_trade_time(ts):
        from datetime import datetime

        if isinstance(ts, datetime):
            return ts.strftime("%Y-%m-%d %H:%M:%S")
        try:
            dt = datetime.fromisoformat(str(ts))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(ts).split(".")[0]

    raw = get_holdings()
    holdings = []

    for symbol, qty, avg_cost, lp in raw:
        try:
            live = float(fetch_etrade_quote(symbol) or 0.0)
        except Exception:
            live = float(lp or 0.0)

        # Pull 2 days to get prev close
        last_close = prev_close = None
        try:
            hist = fetch_data_with_timeout(symbol, "2d")
            if hist is not None:
                if isinstance(hist.columns, pd.MultiIndex):
                    hist.columns = hist.columns.get_level_values(-1)
                hist.columns = [str(c) for c in hist.columns]
                col_close = next(
                    (c for c in hist.columns if c.lower() == "close"), None
                )
                if col_close:
                    if len(hist) >= 1:
                        last_close = float(hist[col_close].iloc[-1])
                    if len(hist) >= 2:
                        prev_close = float(hist[col_close].iloc[-2])
        except Exception:
            pass

        display_price = live or last_close or prev_close or float(avg_cost or 0.0)

        # Intraday change (today vs yesterday close)
        if live and last_close is not None:
            day_base = last_close
            change_day = display_price - last_close
        else:
            # fallback: flat day change if we can------™t get last_close
            day_base = last_close if last_close is not None else float(avg_cost or 0.0)
            ref_prev = prev_close if prev_close is not None else day_base
            change_day = day_base - ref_prev

        gain_per_share = display_price - float(avg_cost or 0.0)
        holdings.append(
            {
                "symbol": symbol,
                "qty": int(qty or 0),
                "price_paid": float(avg_cost or 0.0),
                "last_price": round(display_price, 2),
                "change": round(gain_per_share, 2),  # since entry
                "change_pct": round((gain_per_share / avg_cost * 100.0), 1)
                if avg_cost
                else 0.0,
                "day_gain": round(change_day * int(qty or 0), 2),  # intraday P/L
                "total_gain": round(gain_per_share * int(qty or 0), 2),
                "value": round(display_price * int(qty or 0), 2),
            }
        )

    return redirect(url_for("simulation_view"))

    cash = round(get_cash(), 2)
    unrealized_pnl = round(sum(h["total_gain"] for h in holdings), 2)
    total_cost_basis = sum(h["qty"] * h["price_paid"] for h in holdings)
    unrealized_pnl_pct = (
        round((unrealized_pnl / total_cost_basis * 100), 2) if total_cost_basis else 0.0
    )


IGNORED_TICKERS = {"GEVO"}  # hide on Live


def _get_num(d: dict, paths, default=0.0):
    for path in paths:
        cur = d
        try:
            for key in path.split("."):
                if cur is None:
                    raise KeyError
                if isinstance(cur, list):
                    cur = cur[0]
                else:
                    cur = cur.get(key)
            if cur not in (None, "", "-", "NA"):
                return float(cur)
        except Exception:
            continue
    return float(default)


def _deepget(d: dict, path: str):
    cur = d
    for key in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            cur = cur[0] if cur else None
        elif isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return None
    return cur


def _get_str(d: dict, paths, default=""):
    for path in paths:
        cur = d
        try:
            for key in path.split("."):
                if cur is None:
                    raise KeyError
                if isinstance(cur, list):
                    cur = cur[0]
                else:
                    cur = cur.get(key)
            if cur is not None:
                return str(cur)
        except Exception:
            continue
    return default


# dashboard.py


def _normalize_positions_payload(payload) -> list[dict]:
    """
    Accepts either your own list-of-rows or raw E*TRADE portfolio JSON and
    returns: [{symbol, qty, price_paid, last_price}]
    """
    # If caller already gave us normalized rows, keep them
    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict) and payload[0].get("symbol"):
            return payload

    # Defensive unwrapping of common shapes
    root = payload or {}
    if (
        isinstance(root, dict)
        and "positions" in root
        and isinstance(root["positions"], dict)
    ):
        root = root["positions"]

    pr = {}
    if isinstance(root, dict):
        pr = (
            root.get("PortfolioResponse")
            or root.get("portfolio")
            or root.get("Portfolio")
            or {}
        )

    ap = pr.get("AccountPortfolio", [])
    if isinstance(ap, dict):
        ap = [ap]

    out: list[dict] = []
    for acct in ap:
        pos = acct.get("Position", [])
        if isinstance(pos, dict):
            pos = [pos]

        for p in pos:
            prod = (p.get("Product") or {}) if isinstance(p, dict) else {}
            sym = str(prod.get("symbol") or prod.get("Symbol") or "").upper()

            # quantities / cost
            qty = p.get("quantity") or p.get("qty")
            avg = (
                p.get("pricePaid")
                or p.get("avgPrice")
                or p.get("averagePrice")
                or p.get("costPerShare")
            )

            # last price can be in several places; include Quick.lastTrade
            last = (
                p.get("lastPrice")
                or p.get("closePrice")
                or (p.get("Quick") or {}).get("lastTrade")
                or None
            )

            # Parse safely
            try:
                qty = int(round(float(qty or 0)))
            except Exception:
                qty = 0
            try:
                avg = float(avg) if avg is not None else None
            except Exception:
                avg = None
            try:
                last = float(last) if last is not None else None
            except Exception:
                last = None

            # Only emit rows that at least have a symbol and a nonzero qty
            if sym and qty:
                out.append(
                    {
                        "symbol": sym,
                        "qty": qty,
                        "price_paid": avg,
                        "last_price": last,
                    }
                )

    return out


from services.etrade_service import get_account_summary, get_positions

# --- Account normalizer (works with E*TRADE balance + list payloads) ---


def _afloat(v, default=0.0):
    try:
        if v in (None, "", "-", "NA"):
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _dig(d, path, default=None):
    """Walk dot-paths; handles [0] lists implicitly."""
    cur = d
    for key in path.split("."):
        if isinstance(cur, list):
            cur = cur[0] if cur else {}
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def _build_holdings_from_positions(positions):
    """Return (rows, unrealized_pnl, cost_basis, positions_value)."""
    rows = []
    for pos in positions or []:
        sym = (pos.get("symbol") or "").upper()
        if sym in IGNORED_TICKERS:
            continue

        qty = int(pos.get("qty") or 0)
        last = float(pos.get("last_price") or 0.0)
        avg = float(pos.get("price_paid") or 0.0)

        # day gain: prefer broker-provided, else (last - prev_close) * qty
        day_gain = 0.0
        try:
            day_gain = float(
                pos.get("todaysGainLoss") or pos.get("todaysGainLossBase") or 0.0
            )
        except Exception:
            pass
        if not day_gain:
            pc = (
                pos.get("previous_close")
                or pos.get("prev_close")
                or pos.get("close_prev")
            )
            try:
                pc = float(pc)
                if pc:
                    day_gain = (last - pc) * qty
            except Exception:
                pass

        change = (last - avg) if avg else 0.0
        total_gain = (last - avg) * qty if (qty and avg) else 0.0
        value = last * qty

        rows.append(
            {
                "symbol": sym,
                "qty": qty,
                "last_price": round(last, 4),
                "price_paid": round(avg, 4),
                "change": round(change, 4),
                "change_pct": (change / avg * 100.0) if avg else 0.0,
                "day_gain": round(day_gain, 2),
                "total_gain": round(total_gain, 2),
                "value": round(value, 2),
            }
        )

    unrealized = round(sum(r["total_gain"] for r in rows), 2)
    cost_basis = sum((r["price_paid"] or 0.0) * (r["qty"] or 0) for r in rows)
    positions_value = round(sum(r["value"] for r in rows), 2)
    return rows, unrealized, cost_basis, positions_value
    _acct = acct if isinstance(acct, dict) else {}
    comp = _acct.get("Computed") or {}
    cash = _acct.get("Cash") or {}
    rtv = _acct.get("RealTimeValues") or comp.get("RealTimeValues") or {}

    nav = _first_num(
        rtv.get("totalAccountValue"),
        comp.get("totalAccountValue"),
        comp.get("accountTotal"),
    )


def _normalize_account(raw: dict) -> dict:
    src = (raw or {}).get("BalanceResponse") or (raw or {})
    comp = src.get("Computed") or {}
    cash_blk = src.get("Cash") or {}
    rtv = comp.get("RealTimeValues") or src.get("RealTimeValues") or {}

    def _afloat(x):
        try:
            return round(float(x), 2)
        except Exception:
            return 0.0

    buying_power = _afloat(
        comp.get("cashBuyingPower")
        or comp.get("marginBuyingPower")
        or comp.get("cashAvailableForInvestment")
        or src.get("buyingPower")
    )

    settled_cash = _afloat(
        comp.get("cashAvailableForWithdrawal")
        or comp.get("settledCashForInvestment")
        or comp.get("netCash")
        or comp.get("cashBalance")
        or cash_blk.get("moneyMktBalance")
        or src.get("cash")
        or src.get("cashBalance")
    )

    equity_value = _afloat(
        (rtv or {}).get("totalAccountValue")
        or src.get("netAccountValue")
        or src.get("totalAccountValue")
    )
    if not equity_value:
        equity_value = settled_cash or buying_power

    account_id = str(src.get("accountIdKey") or src.get("accountId") or "")
    account_type = src.get("accountType") or src.get("accountMode") or "Cash"

    return {
        "buying_power": buying_power,
        "settled_cash": settled_cash,
        "equity_value": equity_value,
        "account_id": account_id,
        "account_type": str(account_type),
    }


# ------ LIVE DASHBOARD ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


@app.route("/live", methods=["GET"])
def live_view():
    # Account (safe normalization)
    try:
        raw_summary = get_account_summary() or {}
        account = _normalize_account(
            raw_summary if isinstance(raw_summary, dict) else {}
        )
    except Exception:
        account = {}

    # Positions -> holdings for first paint (JS will refresh anyway)
    try:
        raw_positions = get_positions() or []
        positions = _normalize_positions_payload(raw_positions)
        holdings, _, _, _ = _build_holdings_from_positions(positions)
    except Exception:
        holdings = []

    # Patch in live last prices so the first paint isn't all $0.00
    try:

        def _norm(sym: str) -> str:
            return (sym or "").replace(" ", "").upper()

        symbols = {_norm(h.get("symbol")) for h in holdings if h.get("symbol")}
        quotes = {}
        try:
            # Prefer the module wrapper if present
            from services import etrade_service as et

            if hasattr(et, "get_quotes_batch"):
                quotes = et.get_quotes_batch(symbols) or {}
        except Exception:
            quotes = {}

        if not quotes:
            # Fallback through broker shim
            from services.broker import get_broker

            b = get_broker("LIVE")
            try:
                fresh = b._et.first_account_id_key()
                if fresh and fresh != getattr(b, "_account_id_key", None):
                    log.warning("[LIVE] setting accountIdKey -> %s", fresh)
                    b._account_id_key = fresh
            except Exception as e:
                log.warning("[LIVE] could not pre-refresh account id key: %s", e)

            # capture original
            _original_et_get = b._et._get

            def _shimmed_get(path, params=None):
                params = params or {}
                norm = str(path or "")

                # strip any "/accounts/<id>/" prefix coming in
                if norm.startswith("/accounts/"):
                    parts = norm.split("/", 3)
                    if len(parts) >= 4:
                        norm = "/" + parts[3]

                # never prefix these:
                if (
                    norm == "/accounts/list.json"
                    or norm.startswith("/oauth/")
                    or norm.startswith("/market/")
                ):
                    return _original_et_get(norm, params)

                aid = getattr(b, "_account_id_key", None) or getattr(
                    b, "account_id_key", None
                )
                if aid:
                    return _original_et_get(f"/accounts/{aid}{norm}", params)
                return _original_et_get(norm, params)

            b._et._get = _shimmed_get
            quotes = b._et.get_quotes_batch(symbols) or {}
            qmap = broker.get_quotes_batch(syms)
            current_app.logger.info("[LIVE] qmap keys: %s", sorted(list(qmap.keys())))

        def _lookup(qu: dict, sym: str):
            # handle BF-B vs BF.B, etc.
            variants = [sym, sym.replace("-", "."), sym.replace(".", "-")]
            for v in variants:
                if v in qu:
                    return qu[v]
            return None

        for h in holdings:
            sym = _norm(h.get("symbol"))
            last = _lookup(quotes, sym)
            if isinstance(last, (int, float)) and last > 0:
                h["last_price"] = float(last)
                q = float(h.get("qty") or h.get("quantity") or 0)
                paid = float(h.get("price_paid") or h.get("avg_price") or 0)
                h["value"] = round(q * h["last_price"], 2)
                if paid:
                    h["day_change"] = round(h["last_price"] - paid, 2)
                    h["change_pct"] = round(((h["last_price"] / paid) - 1.0) * 100.0, 2)
    except Exception:
        pass

    # Render with empty trades and no KPI math ------” JS fills everything from /live/status
    return render_template(
        "live.html",
        account=account,
        account_type=(account.get("account_type") or "Cash"),
        holdings=holdings,
        trades=[],  # important: don't seed with SIM/history here
    )

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_TZ_ET = ZoneInfo("America/New_York")  # if not already defined at top-level

# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# LIVE STATUS (E*TRADE-only)
# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
@app.route("/live/status")
@always_json
def live_status():
    """
    Returns the JSON the Live UI expects.
    Supports:
      - ?start=YYYY-MM-DD (ET midnight lower bound; e.g. 2025-08-22)
      - ?days=N (fallback lookback window; clamped)
      - ?debug=1 (adds _debug block)
    """
    try:
        import datetime as _dt
        import json
        import os

        from flask import current_app, request

        from services import etrade_service as et

        # E*TRADE logging wrap (safe to no-op)
        try:
            _etrade_log_wrap()
        except Exception:
            pass

        # ---------------- Timezone (ET) ----------------
        try:
            from zoneinfo import ZoneInfo as _ZoneInfo

            _ET = _ZoneInfo("America/New_York")
        except Exception:
            _ET = _dt.timezone(_dt.timedelta(hours=-5))  # crude ET fallback

        def _log(level, msg, *args):
            try:
                if log:
                    getattr(log, level)(msg, *args)
            except Exception:
                pass

        open_since: dict = {}
        holdings: list = []
        # ---------------- Query params -----------------
        start_iso = (request.args.get("start") or "").strip()
        days = request.args.get("days", type=int)
        debug_level = int(request.args.get("debug") or 0)
        max_count = int(request.args.get("max") or 5000)  # <- NEW

        # ---------------- Trades (single unified source) -----------------
        try:
            # --- Trades: single source -> local list we can safely reference everywhere ---
            from services.trade_source import load_trades_merged

            trades_rows = load_trades_merged(
                days=days,
                start_iso=start_iso,
                max_count=max_count,
            )

            # Use a stable local name for helpers (not a free 'enriched' name)
            _trades_enriched = list(trades_rows or [])
            # --- HOTFIX: make sure we have a stable "enriched" list before any helpers use it ---

            # If you already create `enriched` above, we'll use it; otherwise fall back to raw rows.
            try:
                enr = enriched  # may not exist yet
            except NameError:
                enr = None

            # If you have a FIFO enricher, you can uncomment this block to prefer its output.
            # try:
            #     enr2, _rv1, _rv2, _rv3 = _fifo_enrich_and_daytrades(trades_rows)
            #     if enr2: enr = enr2
            # except Exception:
            #     pass

            _trades_enriched = list(enr or trades_rows or [])

            from datetime import datetime
            from zoneinfo import ZoneInfo
            _TZ_ET = ZoneInfo("America/New_York")

            def _to_ms_for_compare(ts):
                """Return epoch-ms from ms/sec/iso/'YYYY-MM-DD HH:MM:SS' (assume ET when naive)."""
                try:
                    if isinstance(ts, (int, float)) or (isinstance(ts, str) and ts.isdigit()):
                        v = float(ts)
                        return int(v if v > 1e12 else v * 1000.0)
                    s = str(ts or "").strip()
                    if not s:
                        return None
                    if "T" in s or " " in s:
                        dt = datetime.fromisoformat(s.replace("T", " ").split(".")[0])
                    else:
                        dt = datetime.fromisoformat(s)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=_TZ_ET)
                    return int(dt.timestamp() * 1000.0)
                except Exception:
                    return None

            def _sell_pl_through(cutoff_date, rows=_trades_enriched):
                """Sum realized P/L for SELLs with trade date <= cutoff_date (ET)."""
                try:
                    tot = 0.0
                    for tr in rows:
                        side = (tr.get("action") or tr.get("side") or "").upper()
                        if side != "SELL":
                            continue
                        ts_ms = (
                            _to_ms_for_compare(tr.get("time_ms"))
                            or _to_ms_for_compare(tr.get("time_utc"))
                            or _to_ms_for_compare(tr.get("time"))
                        )
                        if not ts_ms:
                            continue
                        d_et = datetime.fromtimestamp(ts_ms / 1000.0, tz=_TZ_ET).date()
                        if d_et <= cutoff_date:
                            tot += float(tr.get("pl") or tr.get("pnl") or 0.0)
                    return round(tot, 2)
                except Exception:
                    return 0.0

            # If not defined elsewhere, keep this tiny helper:
            try:
                START_CASH
            except NameError:
                START_CASH = 0.0

            def _equity_on(d):
                return round(START_CASH + _sell_pl_through(d) + _positions_value_asof(d), 2)

        except Exception:
            if log:
                log.exception("[LIVE] trades merged failed")
            trades_rows = []

        # NOTE:
        #   - Do NOT recompute 'days' here (no 'start_s' / 'req_days').
        #   - Do NOT call transactions_as_trades() or recent_executions_as_trades() anymore.
        #   - All date math happens inside trade_source.load_trades_merged().

        # ---------------- Helpers ----------------------
        # services/live_status_helpers.py (or inline in your live status route)
        from services.etrade_service import account_identity, get_account_summary

        def build_account_for_ui() -> dict:
            ident = (
                account_identity() or {}
            )  # {'account_id', 'account_id_key', 'account_type_display', ...}
            summ = (
                get_account_summary() or {}
            )  # may include 'ui' sub-dict with balances
            ui = summ.get("ui") or {}

            acct_id = ident.get("account_id") or ui.get("account_id") or ""
            acct_key = ident.get("account_id_key") or ui.get("account_key") or ""

            return {
                # IDs (correctly typed)
                "account_id": acct_id,  # numeric like "153737458"
                "account_key": acct_key,  # opaque like "kW8L...C8iWA"
                # Labels / type
                "account_type": ident.get("account_type")
                or ui.get("account_type")
                or "",
                "account_type_display": ident.get("account_type_display")
                or ui.get("account_type_display")
                or "",
                # Balances (pick first non-null among common fields)
                "buying_power": ui.get("available_funds")
                or ui.get("marginBuyingPower")
                or summ.get("buying_power")
                or 0,
                "equity_value": ui.get("netAccountValue")
                or summ.get("equity_value")
                or 0,
                "settled_cash": ui.get("cashAvailableForInvestment")
                or summ.get("settled_cash")
                or 0,
                # keep the raw ui if you want
                "ui": ui,
            }

        def _num(x):
            """Best-effort float, else None."""
            try:
                return float(str(x).replace(",", "").strip())
            except Exception:
                return None

        def _pick_last_prev(q):
            """
            Accepts q as either:
              - simple dict like {'last': 123.4, 'prev': 122.0}, or
              - raw-ish E*TRADE 'QuoteData' / 'All' shapes, or
              - a bare number (last), or string.
            Returns (last, prev) as floats or (None, None).
            """
            # bare number/string
            if isinstance(q, (int, float, str)):
                return (_num(q), None)

            if not isinstance(q, dict):
                return (None, None)

            # normalized map already?
            if "last" in q or "prev" in q:
                return (_num(q.get("last")), _num(q.get("prev")))

            # try common E*TRADE shapes
            # 1) top-level 'All'
            allb = q.get("All") or q.get("all") or {}
            last = _num(allb.get("lastTrade") or allb.get("lastPrice"))
            prev = _num(allb.get("previousClose") or allb.get("priorClose"))

            # take extended-hours last if present
            eh = allb.get("ExtendedHourQuoteDetail") or {}
            eh_last = _num(eh.get("lastPrice"))
            if eh_last is not None:
                last = eh_last if eh_last is not None else last

            # 2) sometimes values live at the top level
            if last is None:
                for k in ("lastTrade", "lastPrice", "close", "last"):
                    v = q.get(k)
                    nv = _num(v)
                    if nv is not None:
                        last = nv
                        break

            if prev is None:
                for k in ("previousClose", "priorClose"):
                    v = q.get(k)
                    nv = _num(v)
                    if nv is not None:
                        prev = nv
                        break

            return (last, prev)

        def _to_f(x):
            try:
                if x is None:
                    return None
                if isinstance(x, (int, float)):
                    return float(x)
                return float(str(x).replace(",", "").strip())
            except Exception:
                return None

        def _safe_float(x, d=0.0):
            try:
                return float(x)
            except Exception:
                return float(d)

        def _to_ms_for_compare(val) -> int:
            """
            Robust convert various time reps to epoch ms.
            Accepts: epoch seconds, epoch ms, ISO (with/without Z), 'YYYY-MM-DD HH:MM:SS'.
            """
            try:
                if val is None:
                    return 0
                # numeric?
                if isinstance(val, (int, float)):
                    v = float(val)
                    return int(v if v > 10_000_000_000 else v * 1000)
                s = str(val).strip()
                if not s:
                    return 0
                # digits only?
                if s.isdigit():
                    v = float(s)
                    return int(v if v > 10_000_000_000 else v * 1000)
                # 'YYYY-MM-DD HH:MM:SS' -> ISO
                if " " in s and "T" not in s:
                    s = s.replace(" ", "T")
                # add 'Z' if no tz
                if "Z" not in s and "+" not in s:
                    s += "Z"
                dt = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
                return int(dt.timestamp() * 1000)
            except Exception:
                return 0

        def _fmt_et(ms_or_any) -> str:
            """Format a timestamp in ET as 'YYYY-MM-DD HH:MM:SS'."""
            try:
                ms = _to_ms_for_compare(ms_or_any)
                if ms <= 0:
                    return ""
                return _dt.datetime.fromtimestamp(ms / 1000.0, tz=_ET).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            except Exception:
                return ""

        def _dig_etrade_quotes_to_map(payload):
            """
            Parse E*TRADE quote payload -> {SYM: {'last': float, 'prev': float|None}}
            Works across both multi-quote and single-quote shapes.
            """
            out = {}

            def _put(sym, last, prev):
                last_f = _to_f(last)
                if sym and last_f is not None:
                    key = str(sym).upper()
                    rec = {"last": last_f, "prev": _to_f(prev)}
                    out[key] = rec
                    # dot/dash dual for tickers like BRK.B or BRK-B
                    if "." in key:
                        out[key.replace(".", "-")] = rec
                    if "-" in key:
                        out[key.replace("-", ".")] = rec

            def visit(node):
                if isinstance(node, dict):
                    sym = node.get("symbol") or (node.get("Product") or {}).get(
                        "symbol"
                    )
                    last = prev = None

                    allblk = node.get("All") or node.get("all")
                    intr = node.get("Intraday") or node.get("intraday")

                    if isinstance(allblk, dict):
                        last = allblk.get("lastTrade") or allblk.get("lastPrice")
                        prev = allblk.get("previousClose") or allblk.get("priorClose")
                        eh = allblk.get("ExtendedHourQuoteDetail") or {}
                        eh_last = _to_f(eh.get("lastPrice"))
                        if eh_last is not None:
                            last = eh_last

                    if last is None and isinstance(intr, dict):
                        last = intr.get("lastTrade") or intr.get("lastPrice")

                    if last is None:
                        for k in ("lastTrade", "lastPrice", "close", "last"):
                            v = node.get(k)
                            if _to_f(v) is not None:
                                last = v
                                break

                    if prev is None:
                        for k in ("previousClose", "priorClose"):
                            v = node.get(k)
                            if _to_f(v) is not None:
                                prev = v
                                break

                    if sym and last is not None:
                        _put(sym, last, prev)
                    for v in node.values():
                        visit(v)
                elif isinstance(node, (list, tuple)):
                    for v in node:
                        visit(v)

            try:
                if isinstance(payload, (bytes, bytearray)):
                    payload = json.loads(payload.decode("utf-8", "ignore"))
                elif isinstance(payload, str):
                    payload = json.loads(payload)
            except Exception:
                pass

            visit(payload or {})
            return out

        def _collect_holdings(raw_positions):
            """Extract [{'symbol','qty','price_paid'}] from E*TRADE positions blob."""
            out = []

            def visit(n):
                if isinstance(n, dict):
                    prod = n.get("Product") or n.get("product") or {}
                    sym = n.get("symbol") or prod.get("symbol")
                    qty = (
                        n.get("quantity")
                        or n.get("qty")
                        or n.get("positionQty")
                        or n.get("longQty")
                        or n.get("longQuantity")
                        or n.get("positionQuantity")
                    )
                    avg = (
                        n.get("pricePaid")
                        or n.get("avgPrice")
                        or n.get("averagePrice")
                        or n.get("costPerShare")
                        or n.get("costBasisPerShare")
                    )
                    if sym and qty:
                        try:
                            q = _safe_float(qty)
                            if q > 0:
                                out.append(
                                    {
                                        "symbol": str(sym).upper(),
                                        "qty": q,
                                        "price_paid": _to_f(avg),
                                    }
                                )
                        except Exception:
                            pass
                    for v in n.values():
                        visit(v)
                elif isinstance(n, (list, tuple)):
                    for v in n:
                        visit(v)

            visit(raw_positions or [])
            return out

        def _fifo_enrich_and_daytrades(trades):
            """
            Enrich trades with FIFO basis and compute day-trade stats.
            A 'day trade' = any SELL whose FIFO-closed shares all came from BUY lots
            opened on the same ET calendar day as the SELL.

            Returns:
                enriched_trades (list[dict]),
                realized_today_val (float),
                realized_today_pct (float),
                daytrade_stats (dict) -> {"pdt5": {"dates": {YYYY-MM-DD: {"count": int}}, "total": int}}
            """
            # ---------- setup ----------
            lots = {}  # sym -> [[qty, px, buy_date], ...]
            today_et = _dt.datetime.now(tz=_ET).date()

            realized_val = 0.0
            realized_basis = 0.0
            enriched = []
            daytrades = []  # {"date": date, "pl": float, "qty": int}

            # Oldest -> newest for FIFO consumption
            chron = sorted(trades, key=lambda t: _to_ms_for_compare(t.get("time_ms")))

            # ---------- FIFO enrich ----------
            for t in chron:
                ts_ms = _to_ms_for_compare(t.get("time_ms"))
                t_date = (
                    _dt.datetime.fromtimestamp(ts_ms / 1000.0, tz=_ET).date()
                    if ts_ms else today_et
                )
                sym  = (t.get("symbol") or "").upper()
                side = (t.get("action") or t.get("side") or "").upper()
                qty  = int(_safe_float(t.get("qty")))
                px   = _to_f(t.get("price"))

                if not sym or qty <= 0 or (px or 0) <= 0:
                    enriched.append({**t})
                    continue

                lots.setdefault(sym, [])

                if side == "BUY":
                    lots[sym].append([qty, px, t_date])
                    enriched.append({**t, "price_paid": px, "pl": 0.0, "pl_pct": 0.0})
                    continue

                if side != "SELL":
                    enriched.append({**t})
                    continue

                # SELL: consume FIFO; track if all matched lots are same-day
                remain = qty
                basis_cost = 0.0
                basis_sh = 0
                same_day = True

                while remain > 0 and lots[sym]:
                    lot_qty, lot_px, lot_date = lots[sym][0]
                    take = min(remain, lot_qty)
                    basis_cost += take * lot_px
                    basis_sh   += take
                    if lot_date != t_date:
                        same_day = False
                    lot_qty -= take
                    remain  -= take
                    if lot_qty == 0:
                        lots[sym].pop(0)
                    else:
                        lots[sym][0][0] = lot_qty

                avg_basis = (basis_cost / basis_sh) if basis_sh else 0.0
                pnl       = (px - avg_basis) * basis_sh if basis_sh else 0.0
                pnl_pct   = ((px / avg_basis - 1.0) * 100.0) if avg_basis else 0.0

                if t_date == today_et:
                    realized_val   += pnl
                    realized_basis += avg_basis * basis_sh

                if basis_sh > 0 and same_day:
                    daytrades.append({"date": t_date, "pl": pnl, "qty": basis_sh})

                enriched.append({**t, "price_paid": avg_basis, "pl": pnl, "pl_pct": pnl_pct})

            # newest -> oldest for UI
            enriched.sort(key=lambda r: _to_ms_for_compare(r.get("time_ms")), reverse=True)

            realized_pct = (realized_val / realized_basis * 100.0) if realized_basis > 0 else 0.0

            # ---------- PDT stats (last 5 trading days) ----------
            from datetime import date, timedelta

            def _is_trading_day(d: date) -> bool:
                return d.weekday() < 5  # Mon-Fri

            def _last_n_trading_days(n: int, end: date | None = None) -> list[date]:
                end = end or today_et
                out, cur = [], end
                while len(out) < n:
                    if _is_trading_day(cur):
                        out.append(cur)
                    cur -= timedelta(days=1)
                return list(reversed(out))

            # count daytrades per day
            by_date = {}
            for drec in daytrades:
                k = drec["date"].isoformat()
                rec = by_date.setdefault(k, {"count": 0, "profitable": 0})
                rec["count"] += 1
                if (drec.get("pl") or 0) > 0:
                    rec["profitable"] += 1

            window = _last_n_trading_days(5)
            pdt_total = 0
            pdt_map = {}
            for d in window:
                k = d.isoformat()
                c = by_date.get(k, {"count": 0})
                pdt_map[k] = {"count": c["count"]}
                pdt_total += c["count"]

            daytrade_stats = {"pdt5": {"dates": pdt_map, "total": pdt_total}}

            return (
                enriched,
                round(realized_val, 2),
                round(realized_pct, 2),
                daytrade_stats,
            )

        # ------------------- Account + Positions + Quotes (robust) -------------------

        from services import broker as _broker

        b = _broker.get_broker("LIVE")

        def _first_num(*vals):
            for v in vals:
                try:
                    if v is not None:
                        return float(v)
                except Exception:
                    pass
            return None

        def _build_positions_table(holdings, qmap, inv):
            """
            Returns (rows, unrealized, cost_basis, positions_value).
            Populates last/prev_close via qmap when not present on holdings.
            """
            rows = []
            qmap = qmap or {}

            def _f(x):
                try:
                    return float(x or 0)
                except Exception:
                    return 0.0

            def _first_num(*vals):
                for v in vals:
                    try:
                        if v is not None:
                            return float(v)
                    except Exception:
                        pass
                return None

            unrealized = 0.0
            cost_basis = 0.0
            positions_value = 0.0

            for pos in holdings or []:
                sym = (pos.get("symbol") or "").upper()
                qty = int(_f(pos.get("qty")))
                avg = _f(pos.get("price_paid")) or None

                q = qmap.get(sym) or {}
                allq = q.get("All") or {}
                # last price from several places (incl. nested "All")
                last = _first_num(
                    pos.get("last_price"),
                    q.get("last"),
                    q.get("lastTrade"),
                    q.get("close"),
                    q.get("previous_close"),
                    q.get("previousClose"),
                    allq.get("lastTrade"),
                    allq.get("last"),
                )

                # previous close (primary) + robust fallbacks
                prev_close = _first_num(
                    q.get("previous_close"),
                    q.get("previousClose"),
                    q.get("prev"),
                    allq.get("previousClose"),
                    allq.get("previousClosePrice"),
                    allq.get("close"),
                )

                # if still missing, back-solve from changeClose
                if prev_close in (None, 0) and last is not None:
                    delta = _first_num(q.get("changeClose"), allq.get("changeClose"))
                    if delta is not None:
                        prev_close = last - delta

                # Value
                value = (
                    round((last or 0.0) * qty, 2)
                    if (last is not None and qty)
                    else None
                )

                # Totals (vs. cost basis)
                total_pl = (
                    ((last - avg) * qty) if (last is not None and avg and qty) else None
                )
                total_pl_pct = (
                    (((last - avg) / avg) * 100.0)
                    if (last is not None and avg)
                    else None
                )

                # Day (vs. previous close)
                day_pl = (
                    ((last - prev_close) * qty)
                    if (last is not None and prev_close is not None and qty)
                    else None
                )
                day_pl_pct = (
                    (((last - prev_close) / prev_close) * 100.0)
                    if (last is not None and prev_close not in (None, 0))
                    else None
                )
                # Fallbacks if prev_close wasn't usable
                if day_pl_pct is None:
                    dpp = _first_num(
                        q.get("changeClosePercentage"),
                        allq.get("changeClosePercentage"),
                    )
                    if dpp is not None:
                        day_pl_pct = float(dpp)

                if day_pl is None:
                    # If we have the absolute day change, multiply by qty
                    dc = _first_num(q.get("changeClose"), allq.get("changeClose"))
                    if dc is not None and qty:
                        day_pl = float(dc) * qty
                    # Or derive from pct if we have last
                    elif day_pl_pct is not None and last is not None and qty:
                        day_pl = (last * (day_pl_pct / 100.0)) * qty

                # Legacy ------œchange/percent------ (kept so nothing else breaks)
                change = (last - avg) if (last is not None and avg) else 0.0
                change_pct = ((change / avg) * 100.0) if avg else 0.0

                rows.append(
                    {
                        "symbol": sym,
                        "qty": qty,
                        "opened_et": pos.get("opened_et") or pos.get("open_time"),
                        "last_price": round(last, 4) if last is not None else None,
                        "price_paid": round(avg, 4) if avg is not None else None,
                        # ---œ… what the Holdings table shows
                        "day_pl": round(day_pl, 2) if day_pl is not None else None,
                        "day_pl_pct": round(day_pl_pct, 2)
                        if day_pl_pct is not None
                        else None,
                        "total_pl": round(total_pl, 2)
                        if total_pl is not None
                        else None,
                        "total_pl_pct": (
                            round(total_pl_pct, 2) if total_pl_pct is not None else None
                        ),
                        # keep existing fields
                        "change": round(change, 4) if avg is not None else 0.0,
                        "change_pct": change_pct,
                        "value": value,
                    }
                )

                if total_pl is not None:
                    unrealized += total_pl
                if avg is not None and qty:
                    cost_basis += avg * qty
                if value is not None:
                    positions_value += value

            return (
                rows,
                round(unrealized, 2),
                round(cost_basis, 2),
                round(positions_value, 2),
            )

            # Totals
            total_pl = (
                ((last - avg) * qty) if (last is not None and avg and qty) else None
            )
            total_pl_pct = (
                ((last - avg) / avg * 100.0) if (last is not None and avg) else None
            )

            # Day (vs previous close)
            day_pl = (
                ((last - prev_close) * qty)
                if (last is not None and prev_close is not None and qty)
                else None
            )
            day_pl_pct = (
                ((last - prev_close) / prev_close * 100.0)
                if (last is not None and prev_close not in (None, 0))
                else None
            )

            # Keep your existing change fields too (optional)
            change = (last - avg) if (last is not None and avg) else 0.0

            rows.append(
                {
                    "symbol": sym,
                    "qty": qty,
                    "last_price": round(last, 4) if last is not None else None,
                    "last": round(last, 4)
                    if last is not None
                    else None,  # alias for template
                    "price_paid": round(avg, 4) if avg else None,
                    # what the template expects for holdings P&L:
                    "day_pl": round(day_pl, 2) if day_pl is not None else None,
                    "day_pl_pct": round(day_pl_pct, 2)
                    if day_pl_pct is not None
                    else None,
                    "total_pl": round(total_pl, 2) if total_pl is not None else None,
                    "total_pl_pct": round(total_pl_pct, 2)
                    if total_pl_pct is not None
                    else None,
                    # keep prior names so nothing else breaks
                    "change": round(change, 4) if avg else 0.0,
                    "change_pct": (change / avg * 100.0) if avg else 0.0,
                    "value": round(last * qty, 2)
                    if (last is not None and qty)
                    else None,
                }
            )

            unrealized = round(sum(f(r.get("total_gain")) for r in rows), 2)
            cost_basis = round(
                sum(f(r.get("price_paid")) * f(r.get("qty")) for r in rows), 2
            )
            positions_value = round(sum(f(r.get("value")) for r in rows), 2)
            return rows, unrealized, cost_basis, positions_value

        # --------------- Positions / Holdings (direct via etrade_service) ----------

        holdings: list[dict] = []
        inv: dict[str, float] = {}
        qmap: dict[str, dict] = {}

        # tolerant normalizer for the raw E*TRADE portfolio blob
        def _normalize_positions_payload(payload) -> list[dict]:
            pr = (payload or {}).get("PortfolioResponse") or {}
            aps = pr.get("AccountPortfolio") or []
            if isinstance(aps, dict):
                aps = [aps]

            rows: list[dict] = []
            for ap in aps:
                pos = ap.get("Position") or []
                if isinstance(pos, dict):
                    pos = [pos]
                for p in pos:
                    prod = p.get("Product") or {}
                    sym = (prod.get("symbol") or p.get("symbol") or "").upper()
                    qty = (
                        p.get("quantity")
                        or p.get("longQty")
                        or p.get("positionQuantity")
                        or 0
                    )
                    paid = (
                        p.get("pricePaid")
                        or p.get("avgPrice")
                        or p.get("averagePrice")
                        or p.get("costPerShare")
                        or p.get("costBasisPerShare")
                    )
                    last = (
                        p.get("lastPrice")
                        or (p.get("Quick") or {}).get("lastTrade")
                        or (p.get("All") or {}).get("lastTrade")
                    )
                    try:
                        qty = int(float(qty or 0))
                    except Exception:
                        qty = 0

                    rows.append(
                        {
                            "symbol": sym,
                            "qty": qty,
                            "price_paid": (
                                float(paid) if paid not in (None, "") else None
                            ),
                            "last_price": (
                                float(last) if last not in (None, "") else None
                            ),
                        }
                    )
            return rows

        # fetch raw positions directly from the service layer
        try:
            raw_positions = et.get_positions() or {}
        except Exception as e:
            _log("warning", "[LIVE] get_positions failed: %s", e)
            raw_positions = {}

        # build holdings rows + inventory map
        try:
            holdings = _normalize_positions_payload(raw_positions)
            inv = {
                r["symbol"]: float(r["qty"])
                for r in holdings
                if r.get("symbol") and r.get("qty")
            }
        except Exception as e:
            _log("warning", "[LIVE] positions normalize error: %s", e)
            holdings, inv = [], {}

        # ---- Quotes: prefer helper; no placeholders, no extra calls ----
        try:
            # symbols from current holdings
            syms = sorted(
                {
                    (r.get("symbol") or "").upper()
                    for r in (holdings or [])
                    if r.get("symbol")
                }
            )
            qmap: dict[str, dict[str, float]] = {}

            if syms:
                # one batch call; do NOT call get_quotes() elsewhere in this path
                try:
                    qmap = et.get_quotes_map(syms) or {}
                except Exception as e:
                    _log("warning", "[LIVE] get_quotes_map error: %s", e)
                    qmap = {}

                # if you have any pre-fetched quote payload available locally, merge it here
                # via _merge_quotes(payload, "local-payload")  (optional, safe no-op if none)
        except Exception as e:
            _log("warning", "[LIVE] quotes map failed: %s", e)
            qmap = {}

        from datetime import datetime, timedelta, timezone

        # ---- Realized P&L buckets: Week / Last Week / Month / All -------------------
        from zoneinfo import ZoneInfo

        _ET = ZoneInfo("America/New_York")

        from zoneinfo import ZoneInfo

        _ET = ZoneInfo("America/New_York")

        def _trade_dt_et(trow):
            """
            Returns an ET-aware datetime for a trade row. Supports:
              - epoch ms/seconds in time_ms/time_utc
              - 'YYYY-MM-DD HH:MM:SS' in time or time_et
              - ISO 8601 in time_utc
            """
            from datetime import datetime, timezone

            val = (
                trow.get("time_ms")
                or trow.get("time_utc")
                or trow.get("time")
                or trow.get("time_et")
            )
            if val is None:
                return None
            # epoch?
            try:
                v = float(val)
                ts_ms = v if v > 10_000_000_000 else v * 1000.0
                return datetime.fromtimestamp(
                    ts_ms / 1000.0, tz=timezone.utc
                ).astimezone(_TZ_ET)
            except Exception:
                pass
            # string parse
            s = str(val).strip().replace("T", " ")
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(s, fmt)
                    return dt.replace(tzinfo=_ET)
                except Exception:
                    continue
            # ISO with Z/offset
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_ET)
                return dt.astimezone(_TZ_ET)
            except Exception:
                return None


            def _ts(t):
                # prefer ms ---†’ utc, then time_utc, then naive ET 'time'
                if t.get("time_ms"):
                    return datetime.fromtimestamp(
                        float(t["time_ms"]) / 1000.0, tz=timezone.utc
                    ).astimezone(_et())
                if t.get("time_utc"):
                    try:
                        return (
                            datetime.strptime(t["time_utc"], "%Y-%m-%d %H:%M:%S")
                            .replace(tzinfo=timezone.utc)
                            .astimezone(_et())
                        )
                    except Exception:
                        pass
                if t.get("time"):  # treat as ET
                    try:
                        return datetime.strptime(
                            t["time"], "%Y-%m-%d %H:%M:%S"
                        ).replace(tzinfo=_et())
                    except Exception:
                        pass
                return None

            for tr in trades or []:
                if (tr.get("action") != "SELL") or (tr.get("pl") is None):
                    continue
                ts = _ts(tr)
                if ts is None:
                    continue

                pnl = float(tr.get("pl") or 0.0)
                # If you store a gross notional in `amount`, use that as cost basis;
                # otherwise fall back to price_paid * qty.
                amt = tr.get("amount")
                if amt is not None:
                    cost = abs(float(amt))
                else:
                    price_paid = float(tr.get("price_paid") or 0.0)
                    qty = float(tr.get("qty") or 0.0)
                    cost = abs(price_paid * qty)

                # all-time
                acc["all"]["pnl"] += pnl
                acc["all"]["cost"] += cost
                # month to date
                if ts >= month_start:
                    acc["month"]["pnl"] += pnl
                    acc["month"]["cost"] += cost
                # last week (full prior week)
                if last_week_start <= ts < last_week_end:
                    acc["last_week"]["pnl"] += pnl
                    acc["last_week"]["cost"] += cost
                # this week to date
                if ts >= week_start:
                    acc["week"]["pnl"] += pnl
                    acc["week"]["cost"] += cost

            def _out(k):
                pnl = round(acc[k]["pnl"], 2)
                pct = (
                    round((pnl / acc[k]["cost"] * 100.0), 2)
                    if acc[k]["cost"] > 0
                    else 0.0
                )
                return {"pnl": pnl, "pct": pct}

            return {
                "week": _out("week"),
                "last_week": _out("last_week"),
                "month": _out("month"),
                "all": _out("all"),
            }
        def _merge_quotes(raw, tag: str):
            if quotes_dbg is not None:

                def _glimpse(obj):
                    try:
                        if isinstance(obj, dict):
                            return {"type": "dict", "keys": list(obj.keys())[:8]}
                        if isinstance(obj, (list, tuple)):
                            return {"type": "list", "len": len(obj)}
                        s = str(obj)
                        return (s[:160] + "------¦") if len(s) > 160 else s
                    except Exception:
                        return "<glimpse-failed>"

                quotes_dbg.append({"tag": tag, "glimpse": _glimpse(raw)})

            parsed = _dig_etrade_quotes_to_map(raw) or {}
            if parsed:
                qmap.update(parsed)
                return True
            return False

        def _infer_open_times(holdings, trades_rows):
            """
            For each symbol we currently hold (qty>0), walk its trades oldest->newest
            and remember the first BUY after the last time size dropped to 0.
            Returns {SYM: opened_time_display_ET}.
            """
            # index trades by symbol, oldest -> newest
            by_sym: dict[str, list[dict]] = {}
            for tr in sorted(
                trades_rows or [],
                key=lambda x: _to_ms_for_compare(
                    x.get("time_ms") or x.get("time") or x.get("time_utc")
                ),
            ):
                s = (tr.get("symbol") or "").upper()
                if not s:
                    continue
                by_sym.setdefault(s, []).append(tr)

            out: dict[str, str] = {}
            for h in holdings or []:
                s = (h.get("symbol") or "").upper()
                qty_now = int(_safe_float(h.get("qty")) or 0)
                if not s or qty_now <= 0:
                    continue

                pos = 0
                opened_et = None  # string we’ll display in the UI
                for tr in by_sym.get(s, []):
                    side = (tr.get("action") or "").upper()
                    q = int(_safe_float(tr.get("qty")) or 0)

                    if side == "BUY":
                        prev = pos
                        pos += q
                        if prev <= 0 and pos > 0:
                            # prefer the already-formatted ET time if present
                            opened_et = tr.get("time") or _fmt_et(
                                tr.get("time_ms") or tr.get("time_utc")
                            )
                    elif side == "SELL":
                        pos -= q
                        if pos <= 0:
                            opened_et = None  # flat; next BUY re-opens

                # if we still hold shares, keep the last opened_et we saw
                if pos > 0 and opened_et:
                    out[s] = opened_et

            return out

        # ---- B# ---- Build the symbol request set from holdings + inv ----
        syms = sorted(
            {
                *(
                    str(r.get("symbol") or r.get("sym") or "").upper()
                    for r in (holdings or [])
                    if (r.get("symbol") or r.get("sym"))
                ),
                *{str(s).upper() for s in (inv or {}).keys()},
            }
        )
        syms = [s for s in syms if s]  # drop empties

        if syms:
            _log("info", "[LIVE] requesting quotes for %s", syms)

            # one batch call
            try:
                qmap = et.get_quotes_map(syms) if hasattr(et, "get_quotes_map") else {}
            except Exception as e:
                _log("warning", "[LIVE] get_quotes_map error: %s", e)
                qmap = {}

            # fallback: only fetch singles for missing symbols
            missing = [s for s in syms if s not in qmap]
            for s in missing:
                try:
                    raw = et.get_quote(s, detailFlag="ALL")
                    _merge_quotes(raw, f"single:{s}")  # merges into qmap if parseable
                except Exception as ee:
                    _log("warning", "[LIVE] get_quote(%s) error: %s", s, ee)

        # ---- Account balances/meta (via service) ----
        try:
            aid = et.account_id_key()
            acct_raw = et.get_balances(aid) or {}
        except Exception as e:
            _log("warning", "[LIVE] balances fetch failed: %s", e)
            acct_raw = {}

        try:
            account_norm = et._normalize_account(acct_raw) or {}
        except Exception:
            account_norm = {}

        account = {
            "account_id": aid,
            "account_key": aid,
            "account_type": None,  # optional to fill elsewhere
            "buying_power": account_norm.get("buying_power") or 0,
            "available_to_withdraw": account_norm.get("available_to_withdraw") or 0,
            "equity_value": account_norm.get("equity_value") or 0,
            "settled_cash": account_norm.get("settled_cash") or 0,
        }

        # ---- Metrics scaffold (must exist before we assign to it) ----
        metrics = {
            "cash_balance": float(
                account.get("cashAvailableForWithdrawal")
                or account.get("cashAvailableForInvestment")
                or account.get("cashBalance")
                or 0.0
            ),
            "positions_value": 0.0,
            "total_value": 0.0,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "realized_pnl": 0.0,
            "realized_pnl_pct": 0.0,
            "daytrades_pdt5": {"total": 0, "dates": {}},
            "realized_buckets": {
                "week": {"pnl": 0.0, "pct": 0.0},
                "last_week": {"pnl": 0.0, "pct": 0.0},
                "month": {"pnl": 0.0, "pct": 0.0},
                "all": {"pnl": 0.0, "pct": 0.0},
            },
        }
        # ---- Rollups from holdings (safe even if holdings is empty) ----
        positions_value = round(sum(_safe_float(h.get("value")) for h in holdings), 2)

        cost_basis_sum = round(
            sum(
                _safe_float(h.get("price_paid")) * _safe_float(h.get("qty"))
                for h in holdings
            ),
            2,
        )

        unrealized = round(
            sum(
                (_safe_float(h.get("last_price")) - _safe_float(h.get("price_paid")))
                * _safe_float(h.get("qty"))
                for h in holdings
            ),
            2,
        )

        upct = (
            round((unrealized / cost_basis_sum * 100.0), 2) if cost_basis_sum else 0.0
        )

        # ---- Compute metrics from current rows / qmap fallback ----
        rows, unrealized, cost_basis, positions_value = _build_positions_table(
            holdings, qmap, inv
        )  # your existing helper

        metrics["positions_value"] = positions_value
        if not metrics.get("cash_balance"):
            metrics["cash_balance"] = account["settled_cash"] or 0
        metrics["total_value"] = round(
            (metrics["cash_balance"] or 0) + (metrics["positions_value"] or 0), 2
        )
        metrics["unrealized_pnl"] = unrealized
        metrics["unrealized_pnl_pct"] = (
            round((unrealized / cost_basis) * 100, 2) if cost_basis else 0
        )

        # ---- Debug fill-ins if you have a _debug dict ----
        try:
            _debug = _debug  # keep existing if present
        except NameError:
            _debug = {}
        _debug.update(
            {
                "qmap_keys": sorted(list(qmap.keys())),
                "requested": syms,
                "cost_basis_sum": cost_basis,
                "positions_value": positions_value,
            }
        )

        # Expose for your final response assembly:
        holdings = rows

        # --------------- Trades (from merged source) ---------------
        IGNORE = {
            s.strip().upper()
            for s in (os.getenv("LIVE_IGNORE_SYMBOLS") or "GEVO").split(",")
            if s.strip()
        }
        mapped = []

        for t in trades_rows or []:
            sym = (t.get("symbol") or "").upper()
            if not sym or sym in IGNORE:
                continue

            side = (t.get("side") or t.get("action") or "").upper()
            if side.startswith("BUY"):
                side = "BUY"
            elif side.startswith("SELL"):
                side = "SELL"

            qty = int(_safe_float(t.get("qty")))
            px = _to_f(t.get("price"))

            ts_ms = _to_ms_for_compare(t.get("time_ms") or t.get("time"))
            mapped.append(
                {
                    "time": _fmt_et(ts_ms),
                    "time_ms": ts_ms,
                    "time_utc": t.get("time") or "",
                    "symbol": sym,
                    "action": side,
                    "qty": qty,
                    "price": px,
                    "amount": _to_f(t.get("amount")),
                    "price_paid": _to_f(t.get("price_paid") or t.get("pricePaid")),
                    "pl": _to_f(t.get("pl")),
                    "pl_pct": _to_f(t.get("pl_pct")),
                }
            )

        # newest -> oldest
        mapped.sort(key=lambda r: _to_ms_for_compare(r.get("time_ms")), reverse=True)

        # FIFO enrich + PDT stats + today's realized
        enriched_trades, realized_today_val, realized_today_pct, daytrade_stats = (
            _fifo_enrich_and_daytrades(mapped)
        )

        # Optional: compute realized_buckets (week/last_week/month/all) if you have a helper
        try:
            realized_buckets = summarize_realized_buckets(trades_enriched)
            if "realized_buckets" not in metrics: metrics["realized_buckets"] = realized_buckets
        except Exception:
            realized_buckets = {
                "week": {"pnl": 0.0, "pct": 0.0},
                "last_week": {"pnl": 0.0, "pct": 0.0},  # <------” add
                "month": {"pnl": 0.0, "pct": 0.0},
                "all": {"pnl": 0.0, "pct": 0.0},
            }

        # Dedup + normalize trade rows
        IGNORE = {
            s.strip().upper()
            for s in (os.getenv("LIVE_IGNORE_SYMBOLS") or "GEVO").split(",")
            if s.strip()
        }
        seen, mapped = set(), []
        seen, mapped = set(), []
        for t in trades_rows or []:
            sym = (t.get("symbol") or "").upper()
            if sym in IGNORE:
                continue
            side = (t.get("side") or t.get("action") or "").upper()
            if side.startswith("BUY"):
                side = "BUY"
            elif side.startswith("SELL"):
                side = "SELL"
            qty = int(_safe_float(t.get("qty")))
            px = _to_f(t.get("price"))

            # Timestamp: prefer time_ms; else fall back to time/time_utc
            ts_ms = _to_ms_for_compare(
                t.get("time_ms") or t.get("time") or t.get("time_utc")
            )
            minute_bucket = int(ts_ms / 60000) if ts_ms else 0
            key = (minute_bucket, sym, side, qty, round(px or 0.0, 2))
            if key in seen:
                continue
            seen.add(key)

            mapped.append(
                {
                    "time": _fmt_et(ts_ms),  # ET display
                    "time_ms": ts_ms,  # for sorting / filtering
                    "time_utc": t.get("time") or t.get("time_utc") or "",
                    "symbol": sym,
                    "action": side,
                    "qty": qty,
                    "price": px,
                    "amount": _to_f(t.get("amount")),
                    # pass through P&L fields if service already computed
                    "price_paid": _to_f(t.get("price_paid") or t.get("pricePaid")),
                    "pl": _to_f(t.get("pl")),
                    "pl_pct": _to_f(t.get("pl_pct")),
                }
            )

        def _open_since_map(trades):
            """
            Build {SYM: earliest_open_lot_time_ms} from FIFO across BUY/SELL trades.
            Uses trade['time_ms'] and trade['action'] ('BUY'/'SELL').
            """
            lots = {}  # sym -> list of [qty, px, time_ms]
            for t in sorted(trades, key=lambda x: _to_ms_for_compare(x.get("time_ms"))):
                sym = (t.get("symbol") or "").upper()
                side = (t.get("action") or "").upper()
                qty = int(_safe_float(t.get("qty")))
                tms = _to_ms_for_compare(t.get("time_ms"))
                px = _to_f(t.get("price"))
                if not sym or qty <= 0:
                    continue
                lots.setdefault(sym, [])
                if side == "BUY":
                    lots[sym].append([qty, px, tms])
                elif side == "SELL":
                    remain = qty
                    while remain > 0 and lots[sym]:
                        lq, lpx, lts = lots[sym][0]
                        take = min(remain, lq)
                        lq -= take
                        remain -= take
                        if lq == 0:
                            lots[sym].pop(0)
                        else:
                            lots[sym][0][0] = lq
            # earliest remaining lot time for each symbol
            out = {}
            for sym, stk in lots.items():
                if stk:
                    out[sym] = min((r[2] or 0) for r in stk if r and len(r) >= 3)
            return out

        # --- always initialize so it's in scope even on failures
        open_since = {}

        try:
            # use the chronological, pre-enriched list ("mapped") ------” that's enough
            open_since = _open_since_map(mapped) if mapped else {}
        except Exception as e:
            _log("warning", "[LIVE] open_since_map failed: %s", e)
            open_since = {}

        # --- BEFORE you start enriching holdings, add: ---
        open_since = {}  # make sure it exists even if we fail to build it

        try:
            import datetime as _dt

            from services.trading_helpers import get_trades

            def _to_ms(val):
                try:
                    if isinstance(val, (int, float)):
                        v = float(val)
                        return int(v if v > 10_000_000_000 else v * 1000)
                    s = str(val or "")
                    if " " in s and "T" not in s:
                        s = s.replace(" ", "T")
                    if "Z" not in s and "+" not in s:
                        s += "Z"
                    return int(
                        _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
                        * 1000
                    )
                except Exception:
                    return 0

            for t in get_trades() or []:
                sym = (t.get("symbol") or "").upper()
                act = (t.get("action") or "").upper()
                ts = (
                    t.get("time_ms")
                    or t.get("time_utc")
                    or t.get("time")
                    or t.get("timestamp")
                )
                ms = _to_ms(ts)
                if act == "SELL":
                    open_since.pop(sym, None)  # back to flat
                elif act == "BUY" and sym:
                    open_since.setdefault(sym, ms)  # first BUY since flat
        except Exception as e:
            current_app.logger.warning(
                "[LIVE] holdings enrichment failed building open_since: %s", e
            )
            open_since = {}  # keep it safe

        # Enrich with FIFO, then normalize rounding
        trades_enriched, realized_today, realized_today_pct, dt_stats = (
            _fifo_enrich_and_daytrades(mapped)
        )

        opened_map = _infer_open_times(holdings, trades_enriched)
        for h in holdings:
            s = (h.get("symbol") or "").upper()
            if s in opened_map:
                opened = opened_map[s]
                h["opened_et"] = opened
                h["open_time"] = opened  # legacy key expected by UI

        # Realized P&L buckets (now that SELL rows have FIFO price_paid)
        try:
            realized_buckets = summarize_realized_buckets(trades_enriched)
        except Exception:
            current_app.logger.exception("realized_buckets summarize failed")
            realized_buckets = {
                "week": {"pnl": 0.0, "pct": 0.0},
                "last_week": {"pnl": 0.0, "pct": 0.0},
                "month": {"pnl": 0.0, "pct": 0.0},
                "all": {"pnl": 0.0, "pct": 0.0},
            }

        for t in trades_enriched:
            if "price_paid" in t and t["price_paid"] is not None:
                t["price_paid"] = round(_safe_float(t["price_paid"]) or 0.0, 2)
            if "pl" in t and t["pl"] is not None:
                t["pl"] = round(_safe_float(t["pl"]) or 0.0, 2)
            if "pl_pct" in t and t["pl_pct"] is not None:
                t["pl_pct"] = round(_safe_float(t["pl_pct"]) or 0.0, 2)

        open_since = _open_since_map(mapped)  # or trades_enriched; mapped is fine

        # --- NEW: realized over the whole lookback window (after start cutoff) ---
        realized_total = round(
            sum(
                _safe_float(t.get("pl"))
                for t in trades_enriched
                if (t.get("action") == "SELL" and t.get("pl") is not None)
            ),
            2,
        )

        realized_basis_total = sum(
            (_safe_float(t.get("price_paid")) or 0.0) * int(_safe_float(t.get("qty")))
            for t in trades_enriched
            if (t.get("action") == "SELL" and t.get("price_paid") is not None)
        )

        realized_total_pct = (
            round((realized_total / realized_basis_total * 100.0), 2)
            if realized_basis_total > 0
            else 0.0
        )

        for h in holdings:
            s = (h.get("symbol") or "").upper()
            if s in opened_map:
                opened = opened_map[s]
                h["opened_et"] = opened  # new name you introduced
                h["open_time"] = opened  # legacy name the UI expects
        # --------------- Equity fallback ---------------
        if not account.get("equity_value"):
            eq = round(
                (account.get("settled_cash") or 0.0) + (positions_value or 0.0), 2
            )
            account["equity_value"] = eq

        # --------------- Payload -----------------------
        cash_balance = float(
            account.get("buying_power") or account.get("available_to_withdraw") or 0.0
        )
        total_value = round(positions_value + cash_balance, 2)

        payload = {
            "ok": True,
            "days": days,
            "account": account,
            "kpis": {
                "realized": realized_buckets,   # <- week/last_week/month/all with pnl & pct
                "realized_today": realized_today_val,
                "realized_today_pct": realized_today_pct,
            },
            "holdings": holdings,
            "trades": trades_enriched,
            "metrics": {
                "positions_value": positions_value,
                "unrealized_pnl": unrealized,
                "unrealized_pnl_pct": upct,
                "realized_pnl": realized_total,
                "realized_pnl_pct": realized_total_pct,
                "total_value": total_value,
                "cash_balance": (
                    account.get("cashAvailableForWithdrawal")
                    or account.get("cashBalance")
                    or 0.0
                ),
                "daytrades_pdt5": (dt_stats or {}).get("pdt5"),
                "realized_buckets": realized_buckets,
            },
        }
        if debug_level:
            payload.setdefault("_debug", {})
            payload["_debug"].update(
                {
                    "positions_count": len(holdings or []),
                    "sample_position": (holdings[0] if holdings else {}),
                    "qmap_keys": sorted(list(qmap.keys())),
                }
            )

        # -------- account block --------
        ident = account_identity() or {}
        summ  = get_account_summary() or {}

        base_ui = (summ.get("ui") or {}) if isinstance(summ.get("ui"), dict) else {}
        acc_id  = (
            ident.get("account_id")
            or base_ui.get("account_id")
            or base_ui.get("accountId")
            or summ.get("account_id")
        )
        acc_key = (
            ident.get("account_id_key")
            or base_ui.get("account_key")
            or base_ui.get("accountIdKey")
            or summ.get("account_key")
        )
        ui = {**base_ui, "account_id": acc_id, "account_key": acc_key}

        payload["account"] = {
            "account_id": acc_id,
            "account_key": acc_key,
            "account_type": ident.get("account_type"),
            "account_type_display": ident.get("account_type_display"),
            "buying_power": summ.get("buying_power") or 0,
            "settled_cash": summ.get("settled_cash") or 0,
            "equity_value": summ.get("equity_value") or 0,
            "ui": ui,
        }

        # API health flag used by the green/red dot
        acct = payload["account"]
        payload["etrade_ok"] = bool(
            acct.get("account_id")
            or (acct.get("equity_value") not in (None, 0))
            or (acct.get("buying_power") is not None)
            or bool(holdings)
            or bool(qmap)
        )

        # -------- P&L buckets (single source for card + headline) --------
        import os
        from services.realized_pl import LIVE_DB
        from services.realized_buckets import realized_buckets_from_live_db

        payload.setdefault("metrics", {})
        payload.setdefault("kpis", {})

        PROJECT_START = os.environ.get("PROJECT_START") or os.environ.get("START_DATE", "2025-08-22")
        START_CASH    = float(os.environ.get("START_CASH", "392.67"))
        PANDL_TILE_MODE = os.environ.get("PANDL_TILE_MODE", "realized").lower()  # realized | total

        def _zero_buckets():
            return {
                "week":      {"pnl": 0.0, "pct": 0.0},
                "last_week": {"pnl": 0.0, "pct": 0.0},
                "month":     {"pnl": 0.0, "pct": 0.0},
                "all":       {"pnl": 0.0, "pct": 0.0},
            }

        # 1) Realized buckets since PROJECT_START from live.db (schema auto-detected)
        try:
            rbuckets = realized_buckets_from_live_db(
                LIVE_DB, since=PROJECT_START, start_cash=START_CASH
            ) or _zero_buckets()
            current_app.logger.info(
                "[REALIZED] db since=%s start_cash=%.2f -> ALL=$%.2f (%.2f%%)",
                PROJECT_START, START_CASH, rbuckets["all"]["pnl"], rbuckets["all"]["pct"]
            )
        except Exception as _e:
            current_app.logger.warning("[REALIZED] DB error: %s", _e)
            rbuckets = None

        # 2) Fallback ONLY if db failed: use equity (“Ben”) buckets *if they exist*,
        #    otherwise zeros. (Do NOT overwrite db numbers.)
        if rbuckets is None:
            rbuckets = locals().get("ben_buckets", _zero_buckets())
            current_app.logger.info("[REALIZED] source=fallback_equity all=$%.2f", rbuckets["all"]["pnl"])

        # 3) Optional: show TOTAL (realized + current unrealized snapshot) on the tile
        if PANDL_TILE_MODE == "total":
            u_now = float(payload.get("metrics", {}).get("unrealized_pnl", 0.0))
            rbuckets = {
                k: {
                    "pnl": round(v.get("pnl", 0.0) + u_now, 2),
                    "pct": round(((v.get("pnl", 0.0) + u_now) / START_CASH * 100.0), 2) if START_CASH else 0.0,
                }
                for k, v in rbuckets.items()
            }
            current_app.logger.info("[P&L TILE] mode=TOTAL unrealized_now=%.2f all=$%.2f", u_now, rbuckets["all"]["pnl"])
        else:
            current_app.logger.info("[P&L TILE] mode=REALIZED all=$%.2f", rbuckets["all"]["pnl"])

        # 4) Publish ONE source everywhere (card + headline)
        payload["metrics"]["realized_buckets"] = rbuckets
        payload["kpis"]["realized"]            = rbuckets
        payload["metrics"]["realized_pnl"]     = rbuckets["all"]["pnl"]
        payload["metrics"]["realized_pnl_pct"] = rbuckets["all"]["pct"]

        # ---- headline meta uses the same buckets ----
        APP_NAME = os.environ.get("APP_NAME", "TradeAlerts")
        payload["about"] = {
            "start_cash": START_CASH,
            "start_date": PROJECT_START,
            "since_pnl":  rbuckets["all"]["pnl"],
            "since_pct":  rbuckets["all"]["pct"],
            "app_name":   APP_NAME,
            "authors":    ["Ben McCall", "Max"],
        }
        # ---------------------------------------------------------------------------

        from datetime import datetime, timedelta, date
        from zoneinfo import ZoneInfo
        _ET = ZoneInfo("America/New_York")

        START_CASH = float(os.environ.get("START_CASH", "392.67"))

        def _ms(v):
            try:
                f = float(v or 0)
                return int(f if f > 10_000_000_000 else f * 1000)
            except Exception:
                return None

        def _et_date_from_ms(ms):
            return datetime.fromtimestamp(ms/1000.0, tz=_ET).date()

        # Bind the currently computed enriched rows at *definition time* so we don't rely on a global.
        _enriched_candidate = None
        try:
            _enriched_candidate = enriched  # may not exist yet
        except NameError:
            _enriched_candidate = None

        _trades_enriched = list(_enriched_candidate or trades_rows or [])

        def _sell_pl_through(cutoff_date, rows=None):
            rows = _trades_enriched if rows is None else rows
            total = 0.0
            for tr in rows:
                if (tr.get("action") == "SELL") and tr.get("time"):
                    # keep your existing date parse logic here
                    # include only trades with trade_date <= cutoff_date
                    # and add tr["pl"] (or "gain") to total
                    try:
                        p = float(tr.get("pl") or tr.get("pnl") or tr.get("gain") or 0.0)
                    except Exception:
                        p = 0.0
                    # (your existing date filter logic) -> if within range:
                    total += p
            return round(total, 2)


        def _holdings_asof(cutoff_date, rows=None):
            rows = _trades_enriched if rows is None else rows
            lots = {}  # sym -> qty held after consuming buys/sells up to cutoff_date
            # (use your existing FIFO or simple net-qty logic as of cutoff_date)
            for tr in rows:
                # filter by date <= cutoff_date, then update lots
                pass
            return lots

        def _equity_on(cutoff_date, rows=None):
            rows = _trades_enriched if rows is None else rows
            return round(
                START_CASH
                + _sell_pl_through(cutoff_date, rows=rows)
                + _positions_value_asof(cutoff_date, rows=rows),
                2,
            )

        def _fetch_close_on(sym: str, d: date) -> float | None:
            """Close on d (ET) or latest prior trading day. Very lightweight cache."""
            key = (sym, d)
            if key in _close_cache:
                return _close_cache[key]
            try:
                # Reuse a data helper you already ship (daily data is fine):
                # services.market_service.fetch_data_with_timeout(symbol, "6mo") returns a pandas DF
                from services.market_service import fetch_data_with_timeout
                df = fetch_data_with_timeout(sym, "6mo")
                # Find the last row with date <= d
                if df is not None and len(df):
                    # Try common date column names
                    col_date = next((c for c in df.columns if str(c).lower() in ("date","time","datetime","index")), None)
                    col_close = next((c for c in df.columns if str(c).lower() in ("close","adj close","adj_close","c")), None)
                    if col_date and col_close:
                        # normalize to date
                        series = df[[col_date, col_close]].copy()
                        series[col_date] = series[col_date].apply(lambda x: (x.date() if hasattr(x, "date") else date.fromisoformat(str(x)[:10])))
                        series = series[series[col_date] <= d].sort_values(col_date)
                        if len(series):
                            px = float(series.iloc[-1][col_close])
                            _close_cache[key] = px
                            return px
            except Exception:
                pass
            return None

        def _positions_value_asof(d: date) -> float:
            tot = 0.0
            pos = _holdings_asof(d)
            for s, q in pos.items():
                px = _fetch_close_on(s, d)
                if px is not None:
                    tot += q * px
            return round(tot, 2)

        # --- PATCH: allow keyword args like rows=rows without breaking ---
        _old__positions_value_asof = _positions_value_asof
        def _positions_value_asof(cutoff_date, **_):
            # Forward to the original implementation, ignoring any extra kwargs
            return _old__positions_value_asof(cutoff_date)
        # --- end PATCH ---

        def _pct(start_v: float, end_v: float) -> float:
            if start_v <= 0: 
                return 0.0
            return round((end_v - start_v) / start_v * 100.0, 2)

        # ---- build Ben buckets on EQUITY (cash+positions) ----
        today = datetime.now(_ET).date()

        # week-to-date
        week_start = today - timedelta(days=today.weekday())        # Monday
        week_start_eod_prev = week_start - timedelta(days=1)
        wk_start = _equity_on(week_start_eod_prev)
        wk_end   = _equity_on(today)
        wk_delta = round(wk_end - wk_start, 2)
        wk_pct   = _pct(wk_start, wk_end)

        # last week (Mon..Sun)
        lw_end   = week_start - timedelta(days=1)                    # last Sunday
        lw_start = lw_end - timedelta(days=6)                        # last Monday
        lws      = _equity_on(lw_start - timedelta(days=1))
        lwe      = _equity_on(lw_end)
        lw_delta = round(lwe - lws, 2)
        lw_pct   = _pct(lws, lwe)

        # month-to-date
        m_start  = today.replace(day=1)
        ms_cash  = _equity_on(m_start - timedelta(days=1))
        me_cash  = _equity_on(today)
        m_delta  = round(me_cash - ms_cash, 2)
        m_pct    = _pct(ms_cash, me_cash)

        # all-time
        all_start = START_CASH
        all_end   = _equity_on(today)
        all_delta = round(all_end - all_start, 2)
        all_pct   = _pct(all_start, all_end)

        # ---- FINAL: lock headline to the tile's buckets -----------------------------
        try:
            # read exactly what the tile shows
            _all = payload.get("metrics", {}).get("realized_buckets", {}).get("all", {}) or {}
            _all_pnl = round(float(_all.get("pnl", 0.0)), 2)

            # use bucket pct if present; else recompute from START_CASH for consistency
            _all_pct = _all.get("pct")
            if _all_pct is None:
                _all_pct = round((_all_pnl / START_CASH * 100.0), 2) if START_CASH else 0.0
            else:
                _all_pct = round(float(_all_pct), 2)

            about = payload.setdefault("about", {})
            about["since_pnl"] = _all_pnl
            about["since_pct"] = _all_pct

            current_app.logger.info("[REALIZED] headline synced: ALL=$%.2f (%.2f%%)", _all_pnl, _all_pct)
        except Exception as _e:
            current_app.logger.warning("[REALIZED] headline sync failed: %s", _e)
        # ----------------------------------------------------------------------------
        
        # ensure headline uses the same source as the tile
        about = payload.setdefault("about", {})
        rb_all = (payload.get("metrics", {})
                         .get("realized_buckets", {})
                         .get("all", {}))
        if "since_pnl" not in about:
            about["since_pnl"] = float(rb_all.get("pnl", 0.0))
        if "since_pct" not in about:
            about["since_pct"] = float(rb_all.get("pct", 0.0))


        return payload


    except Exception as e:
        try:
            current_app.logger.exception("[LIVE] /live/status crashed")
        except Exception:
            pass
        return {"ok": False, "error": str(e)}



@app.route("/live/quotes")
@always_json
def live_quotes():
    """Lightweight endpoint to troubleshoot quote parsing."""
    from flask import request

    from services import etrade_service as et

    syms = [
        s.strip().upper()
        for s in (request.args.get("syms") or "").split(",")
        if s.strip()
    ]
    if not syms:
        return {"error": "pass ?syms=AAPL,MSFT"}

    out = {"requested": syms}
    try:
        # raw = et.get_quotes(syms, detailFlag="ALL")
        qmap = get_quotes_map(sorted(set(syms))) or {}

        out["multi_type"] = type(raw).__name__
        # Reuse the same parser as live_status:
        out["multi_qmap"] = (
            lambda p: (
                lambda _dig: _dig(p)
            )  # inline small parser to avoid import cycles
        )(None)  # stub (we return raw for inspection instead)
        out["raw_multi"] = raw  # let you inspect if needed
    except Exception as e:
        out["multi_error"] = str(e)

    singles = {}
    for s in syms:
        try:
            r = et.get_quote(s, detailFlag="ALL")
            singles[s] = r
        except Exception as e:
            singles[s] = {"error": str(e)}
    out["singles"] = singles
    return out


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
