from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterable
import sys
import json
import logging
from .etrade_auth_flow import get_oauth_session


log = logging.getLogger(__name__)

from services.broker_live import (
    BASE as _BASE,  # https://api.etrade.com/v1
)

# Reuse the proven live session + base URL from broker_live
from services.broker_live import (
    _sesh,  # OAuth1 session
    get_account_id_key,  # robust accountIdKey
)
from services.broker_live import (
    get_quote as _get_quote,  # raw quotes
)

log = logging.getLogger("etrade_service")

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from services.broker_live import get_account_id_key as _get_aid

try:
    import zoneinfo  # Py3.9+
except Exception:
    zoneinfo = None


try:
    import zoneinfo
except Exception:
    zoneinfo = None

# --- time helpers (Eastern) ---

try:
    import zoneinfo
except Exception:
    zoneinfo = None


try:
    import zoneinfo
except Exception:
    zoneinfo = None

from zoneinfo import ZoneInfo
import os
import json
from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv

load_dotenv("etrade.env")

ETRADE_BASE_URL = "https://api.etrade.com"
TOKEN_FILE = "etrade_tokens.json"
ET = ZoneInfo("America/New_York")
# Dot-ticker fixes + normalizer
# --- symbol + traversal helpers ---
_DOT_TICKER_FIXES = {
    # add any broker quirks here if needed
    # "BRK-B": "BRK.B",
}
# --- OPEN ORDERS / AVAILABILITY ------------------------------------------------

# aliases so legacy calls don't blow up


# ---------- OPEN ORDERS (robust) ----------
def get_open_orders(account_id_key: str, days: int = 14) -> dict:
    """
    Return the raw open-orders payload. Try no dates first (most compatible),
    then fall back to a recent window with both YYYY-MM-DD and MM/DD/YYYY.
    """
    import datetime as _dt

    # 1) no dates – many tenants accept this and avoid 400s
    try:
        return _eget(
            f"/accounts/{account_id_key}/orders.json",
            params={"status": "OPEN"},
        )
    except Exception:
        pass

    end = _dt.date.today()
    start = end - _dt.timedelta(days=max(1, int(days)))

    params_list = [
        {
            "fromDate": start.strftime("%Y-%m-%d"),
            "toDate": end.strftime("%Y-%m-%d"),
            "status": "OPEN",
        },
        {
            "fromDate": start.strftime("%m/%d/%Y"),
            "toDate": end.strftime("%m/%d/%Y"),
            "status": "OPEN",
        },
    ]

    last_exc: Exception | None = None
    for params in params_list:
        try:
            return _eget(
                f"/accounts/{account_id_key}/orders.json",
                params=params,
            )
        except Exception as exc:
            last_exc = exc

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unable to fetch open-orders payload")
# Backwards-compat alias for older callers
def list_orders(
    account_id_key: str | None = None,
    status: str | None = None,
    days: int = 14,
) -> dict:
    """
    Backwards-compat wrapper used by older code.

    * account_id_key – if None, we fall back to the default live account.
    * status        – currently ignored; we always request OPEN orders.
    * days          – look-back window in days used by get_open_orders().
    """
    if account_id_key is None:
        account_id_key = get_default_account_id_key()

    # We ignore `status` for now and always return OPEN orders.
    return get_open_orders(account_id_key=account_id_key, days=days)

    # 2) date window – try both formats
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return _eget(
                f"/accounts/{account_id_key}/orders.json",
                params={
                    "status": "OPEN",
                    "fromDate": start.strftime(fmt),
                    "toDate": end.strftime(fmt),
                },
            )
        except Exception:
            continue

    # 3) last resort – bubble the error for visibility
    return _eget(f"/accounts/{account_id_key}/orders.json", params={"status": "OPEN"})

# services/etrade_service.py (add)
import time
import requests
# --- ADD THIS near other imports/helpers ---
from typing import Any

# --- ADD near your other helpers ---
from typing import Any

def _safen(d: Any, *path, default=None, cast=float):
    try:
        for p in path:
            d = d[p] if isinstance(d, list) else d.get(p)
        return default if d is None else cast(d)
    except Exception:
        return default

# services/etrade_service.py

def get_buying_power(account_id_key=None):
    """
    Return true buying power from E*TRADE:
      - For margin accounts: marginBuyingPower
      - For cash accounts:  cashAvailableForInvestment
    Falls back sanely if fields move.
    """
    if account_id_key is None:
        account_id_key = get_default_account_id_key()

    # Standard brokerage balances endpoint
    path = f"/v1/accounts/{account_id_key}/balance.json?instType=BROKERAGE"
    resp = etrade_get(path)
    resp.raise_for_status()
    data = resp.json().get("BalanceResponse", {})

    margin = data.get("margin", {}) or {}
    comp = data.get("Computed", {}) or {}

    # Preferred:
    margin_bp = margin.get("marginBuyingPower")
    cash_bp = comp.get("cashAvailableForInvestment")

    def _to_float(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    margin_bp = _to_float(margin_bp)
    cash_bp = _to_float(cash_bp)

    if margin_bp > 0:
        return margin_bp
    if cash_bp > 0:
        return cash_bp

    # Fallbacks if E*TRADE shuffles fields
    net_cash = _to_float(comp.get("netCash"))
    if net_cash > 0:
        return net_cash

    raise RuntimeError(f"Unable to determine buying power from balances payload: {data}")

def get_account_nav(session=None):
    """
    Return E*TRADE Net Account Value (real-time).
    Prefers accountIdKey, falls back to numeric id.
    """
    sess = session or get_session()
    acct = get_primary_account() or {}
    key  = acct.get("accountIdKey")
    num  = acct.get("accountId")
    params = {"instType": "BROKERAGE", "realTimeNAV": "Y"}

    def _extract(j):
        return (
            _safen(j, "BalanceResponse", "response", "netAccountValue") or
            _safen(j, "BalanceResponse", "response", "accountBalance", 0, "netAccountValue") or
            _safen(j, "balanceResponse", "netAccountValue") or
            _safen(j, "AccountBalanceResponse", "netAccountValue")
        )

    if key:
        try:
            j = sess.get(f"/v1/accounts/{key}/balance", params=params).json()
            nav = _extract(j)
            if nav is not None: return float(nav)
        except Exception:
            pass
    if num:
        j = sess.get(f"/v1/accounts/{num}/balance", params=params).json()
        nav = _extract(j)
        if nav is not None: return float(nav)
    return None

def _clean_instruments_for_place(instr_list):
    """
    Take Instrument[] from a preview response and strip fields that
    cause E*TRADE venue errors (reserveOrder, reserveQuantity, cancelQuantity).
    """
    cleaned = []
    for ins in instr_list or []:
        # Shallow copy so we don't mutate the original preview dict
        ins_copy = dict(ins)
        for k in ("reserveOrder", "reserveQuantity", "cancelQuantity"):
            ins_copy.pop(k, None)
        cleaned.append(ins_copy)
    return cleaned

def fetch_balances_resilient(sess, account_id_key: str, account_id_numeric: str, retries: int = 3):
    urls = [
        f"https://api.etrade.com/v1/accounts/{account_id_key}/balance.json?instType=BROKERAGE",
        f"https://api.etrade.com/v1/accounts/{account_id_key}/balance.json",
        f"https://api.etrade.com/v1/accounts/{account_id_numeric}/balance.json?instType=BROKERAGE",
        f"https://api.etrade.com/v1/accounts/{account_id_numeric}/balance.json",
    ]
    last_err = None
    for url in urls:
        for attempt in range(retries):
            try:
                r = sess.get(url, timeout=15, headers={"Accept": "application/json"})
                if r.status_code >= 500:
                    raise requests.HTTPError(f"{r.status_code} {r.text}")
                r.raise_for_status()
                j = r.json() or {}
                bal = j.get("BalanceResponse") or j.get("balanceResponse") or j
                return bal
            except Exception as e:
                last_err = e
                time.sleep(0.8 * (attempt + 1))  # light backoff
        # try next URL form
    raise RuntimeError(f"All balance endpoints failed; last error: {last_err}")

def open_sell_qty_map(account_id_key: str) -> dict[str, float]:
    """
    Build {SYMBOL: reserved_qty} from OPEN sell orders.
    We traverse generically so minor schema changes don’t break us.
    """
    raw = get_open_orders(account_id_key) or {}
    out: dict[str, float] = {}

    def _to_f(x):
        try:
            if x is None:
                return 0.0
            return float(str(x).replace(",", "").strip())
        except Exception:
            return 0.0

    def _put(sym, qty):
        if not sym:
            return
        key = str(sym).upper()
        out[key] = out.get(key, 0.0) + max(0.0, _to_f(qty))

    def _walk(n, status_hint: str | None = None):
        # We’re flexible about where status/action/qty/symbol live.
        if isinstance(n, dict):
            st = (n.get("orderStatus") or n.get("status") or status_hint or "").upper()
            action = (n.get("orderAction") or n.get("action") or "").upper()
            sym = n.get("symbol") or (n.get("Product") or {}).get("symbol")

            # quantities (prefer remaining if present)
            qty = (
                n.get("remainingQuantity")
                or n.get("remainingQty")
                or n.get("orderedQuantity")
                or n.get("quantity")
                or n.get("qty")
            )

            # If this node clearly looks like an order-leg, process it.
            if action.startswith("SELL") and (
                st in ("OPEN", "WORKING", "PARTIALLY_FILLED", "")
            ):
                # adjust for partial fills if we can see it
                filled = _to_f(
                    n.get("filledQuantity") or n.get("executedQuantity") or 0
                )
                if qty is not None:
                    rem = _to_f(qty) - max(0.0, filled)
                    _put(sym, rem)

            # Recurse
            for v in n.values():
                _walk(v, st or status_hint)

        elif isinstance(n, (list, tuple)):
            for v in n:
                _walk(v, status_hint)

    _walk(raw)
    # Normalize any tiny negatives to zero
    return {k: (v if v > 0 else 0.0) for k, v in out.items()}


# --- add near imports ---
import threading

_QUOTE_CACHE = {"key": None, "asof": 0.0, "data": None}
_QUOTE_LOCK = threading.Lock()


def _norm_syms(symbols):
    if isinstance(symbols, (list, tuple, set)):
        syms = [str(s).replace(".", "-").upper().strip() for s in symbols if s]
    else:
        syms = [str(symbols).replace(".", "-").upper().strip()]
    # stable, deduped
    return tuple(sorted(dict.fromkeys(syms)))


def _cache_get(key: tuple, ttl: float = 2.0):
    now = time.time()
    with _QUOTE_LOCK:
        if _QUOTE_CACHE["key"] == key and (now - _QUOTE_CACHE["asof"]) < ttl:
            return _QUOTE_CACHE["data"]
    return None


def _cache_put(key: tuple, data):
    with _QUOTE_LOCK:
        _QUOTE_CACHE.update({"key": key, "asof": time.time(), "data": data})


def available_to_sell(account_id_key: str, symbol: str) -> int:
    """
    Clamp what we attempt to sell to: long_qty(symbol) - reserved_open_sell_qty(symbol)
    """
    sym = (symbol or "").upper()
    long_map = long_qty_map() or {}
    open_map = open_sell_qty_map(account_id_key) or {}
    avail = int(max(0.0, float(long_map.get(sym, 0.0)) - float(open_map.get(sym, 0.0))))
    return avail


def long_qty_map() -> dict[str, float]:
    """
    Return {SYM: qty_available} using positions.
    Prefer 'available' qty if E*TRADE provides it; else fall back to long qty.
    """
    out = {}
    raw = get_positions() or []

    def visit(n):
        if isinstance(n, dict):
            prod = n.get("Product") or n.get("product") or {}
            sym = _sym_upper(n.get("symbol") or prod.get("symbol"))
            if sym:
                q = _dig_available_qty(n)
                if q is not None:
                    out[sym] = float(q)
            for v in n.values():
                visit(v)
        elif isinstance(n, (list, tuple)):
            for v in n:
                visit(v)

    visit(raw)
    return out


def _normalize_account(raw):
    """
    Normalize E*TRADE balances to fields the UI expects.
    - buying_power            -> marginBuyingPower | cashBuyingPower | buyingPower
    - available_to_withdraw   -> cashAvailableForWithdrawal
    - settled_cash            -> alias of available_to_withdraw (UI uses this id)
    - equity_value            -> netAccountValue (aka Net Account Value)
    """

    def _dig(node, names):
        # recursive lookup by key name anywhere in the blob
        if node is None:
            return None
        if isinstance(node, dict):
            for k, v in node.items():
                if k in names and v is not None:
                    return v
            for v in node.values():
                found = _dig(v, names)
                if found is not None:
                    return found
        elif isinstance(node, (list, tuple)):
            for v in node:
                found = _dig(v, names)
                if found is not None:
                    return found
        return None

    def _to_f(x):
        try:
            if x is None:
                return None
            return float(str(x).replace(",", "").strip())
        except Exception:
            return None

    r = raw or {}

    buying_power = _to_f(
        _dig(r, {"marginBuyingPower", "cashBuyingPower", "buyingPower"})
    )

    available_to_withdraw = _to_f(
        _dig(r, {"cashAvailableForWithdrawal"})  # this is what the site shows
    )

    # Keep the old key the UI currently reads
    settled_cash = available_to_withdraw

    equity_value = _to_f(
        _dig(r, {"netAccountValue", "netAssets", "netValue", "totalAccountValue"})
    )

    out = {
        "buying_power": buying_power,
        "available_to_withdraw": available_to_withdraw,
        "settled_cash": settled_cash,
        "equity_value": equity_value,
    }

    # retain a few optional helpers/fallbacks if present
    cash_balance = _f(
        comp.get("cashBalance")
        or bal.get("cashBalance"),
        0.0,
    )

    out = dict(base)
    out.update({
        "nav": nav,
        "available_funds": available,
        "cash_balance": cash_balance,
        "raw": raw if isinstance(raw, dict) else {},
    })
    return out


def available_to_sell(account_id_key: str, symbol: str) -> int:
    """
    Integer shares actually free to sell now:
      available_from_positions(sym) - open_sell_reserved(sym), floored at 0.
    """
    sym = _sym_upper(symbol)
    long_map = long_qty_map()
    open_map = open_sell_qty_map(account_id_key)
    avail = max(0.0, float(long_map.get(sym, 0.0)) - float(open_map.get(sym, 0.0)))
    return int(avail // 1)  # ensure whole shares


def _normalize_symbol(sym: str) -> str:
    if not sym:
        return sym
    s = sym.upper().strip()
    # prefer dot for class shares; ET accepts both but we normalize once
    if "-" in s and len(s.split("-")[-1]) <= 2:
        s = s.replace("-", ".")
    return _DOT_TICKER_FIXES.get(s, s)


def _visit(node, fn):
    """Depth-first walk calling fn(dict_node)."""
    if isinstance(node, dict):
        fn(node)
        for v in node.values():
            _visit(v, fn)
    elif isinstance(node, (list, tuple)):
        for v in node:
            _visit(v, fn)


def list_open_orders(symbol: str | None = None) -> list[dict]:
    aid = account_id_key()
    s = get_oauth_session()
    r = s.get(
        f"https://api.etrade.com/v1/accounts/{aid}/orders.json",
        params={"status": "OPEN", "count": 50, "sortOrder": "DESC"},
        timeout=15,
    )
    if r.status_code == 204:
        return []
    r.raise_for_status()
    j = r.json() or {}
    orders = (j.get("OrdersResponse") or {}).get("Order") or []
    if isinstance(orders, dict):
        orders = [orders]
    rows = []
    for o in orders:
        for d in o.get("OrderDetail") or []:
            for ins in d.get("Instrument") or []:
                prod = ins.get("Product") or {}
                sym = (prod.get("symbol") or "").upper()
                if symbol and sym != str(symbol).upper():
                    continue
                rows.append(
                    {
                        "symbol": sym,
                        "action": (ins.get("orderAction") or "").upper(),
                        "qty": int(
                            float(
                                ins.get("quantity") or ins.get("orderedQuantity") or 0
                            )
                            or 0
                        ),
                    }
                )
    return rows


def get_balances(account_id_key: str) -> dict:
    return _get(
        f"/accounts/{account_id_key}/balance.json",
        params={"instType": "BROKERAGE", "realTimeNAV": "true"},
    )

def get_default_account_id_key():
    ident = account_identity()
    key = ident.get("account_id_key")
    if not key:
        raise RuntimeError("No account_id_key in E*TRADE identity response")
    return key

# ---- Identity (numeric id + key + type) -------------------------------------
def account_identity():
    """
    Fetch primary E*TRADE account identity via /v1/accounts/list.json.
    Returns a dict:
      {
        "account_id": ...,
        "account_id_key": ...,
        "account_type": ...,
        "account_type_display": ...
      }
    """
    sess = get_oauth_session()
    url = f"{ETRADE_BASE_URL}/v1/accounts/list.json"
    r = sess.get(url, timeout=15)
    r.raise_for_status()
    j = r.json()

    accounts = (
        j.get("AccountListResponse", {})
         .get("Accounts", {})
         .get("Account", [])
    )

    if not accounts:
        raise RuntimeError("No accounts returned from E*TRADE /v1/accounts/list.json")

    # pick first margin/brokerage/individual, else first
    pick = None
    for a in accounts:
        t = (a.get("accountType") or "").upper()
        if "BROKERAGE" in t or "INDIVIDUAL" in t or "MARGIN" in t:
            pick = a
            break
    if pick is None:
        pick = accounts[0]

    return {
        "account_id": pick.get("accountId"),
        "account_id_key": pick.get("accountIdKey"),
        "account_type": pick.get("accountType"),
        "account_type_display": pick.get("accountDesc") or pick.get("accountType"),
    }

def account_id_key() -> str:
    """
    Return the E*TRADE accountIdKey used in URLs like
    /v1/accounts/{accountIdKey}/...
    Order of attempts:
      1) Env var (ETRADE_ACCOUNT_ID_KEY or ACCOUNT_ID_KEY)
      2) broker_live.get_account_id_key()  (you import this as _get_aid)
      3) Discover via /v1/accounts/list.json
    Caches success into os.environ so subsequent calls are cheap.
    """
    # 1) environment
    aid = os.getenv("ETRADE_ACCOUNT_ID_KEY") or os.getenv("ACCOUNT_ID_KEY") or ""
    if aid:
        return aid

    # 2) helper from broker_live (already imported as _get_aid)
    try:
        aid = (_get_aid() or "").strip()
        if aid:
            os.environ["ETRADE_ACCOUNT_ID_KEY"] = aid
            return aid
    except Exception:
        pass

    # 3) discover via API
    try:
        sess = get_oauth_session()
        r = sess.get("https://api.etrade.com/v1/accounts/list.json", timeout=15)
        r.raise_for_status()
        j = r.json() or {}
        accounts = j.get("AccountListResponse", {}).get("Accounts", {}).get(
            "Account", []
        ) or j.get("accounts", [])
        for a in accounts:
            key = a.get("accountIdKey") or a.get("accountIdKeyValue")
            if key:
                os.environ["ETRADE_ACCOUNT_ID_KEY"] = key  # cache for this process
                return key
    except Exception as e:
        log.exception("account_id_key(): discovery via accounts/list failed: %s", e)

    raise RuntimeError(
        "ETRADE_ACCOUNT_ID_KEY not found. Set it (or wire broker_live.get_account_id_key), "
        "or ensure OAuth is valid so /v1/accounts/list.json can be queried."
    )

def get_nav_on_date(account_key: str, date_str: str):
    """
    Return net account value (NAV) for a specific date, or None.

    account_key: E*TRADE accountIdKey, e.g. 'kW8LbkuGisPCK9Ey7C8iWA'
    date_str: 'YYYY-MM-DD'
    """
    try:
        sess = get_oauth_session()
    except Exception as e:
        log.error("get_nav_on_date: failed to get OAuth session: %s", e, exc_info=True)
        return None

    base = os.getenv("ETRADE_BASE_URL", "https://api.etrade.com")
    # Use account *key*, not bare account number
    url = f"{base}/v1/accounts/{account_key}/balance.json"

    # E*TRADE historical balance uses view=PERIOD with yyyymmdd dates
    ymd = date_str.replace("-", "")
    params = {
        "view": "PERIOD",
        "startDate": ymd,
        "endDate": ymd,
    }

    try:
        r = sess.get(url, params=params, timeout=15)
    except Exception as e:
        log.error("get_nav_on_date: request error: %s", e, exc_info=True)
        return None

    if r.status_code != 200:
        # This is the critical diagnostic you were asking for
        log.error(
            "get_nav_on_date: HTTP %s for %s params=%s body=%s",
            r.status_code, url, params, r.text[:500]
        )
        return None

    try:
        data = r.json()
    except ValueError:
        log.error("get_nav_on_date: non-JSON response: %r", r.text[:500])
        return None

    # E*TRADE balance shapes can vary a bit; handle both dict & list forms
    br = data.get("BalanceResponse") if isinstance(data, dict) else None

    if isinstance(br, dict):
        computed = br.get("Computed") or {}
    elif isinstance(br, list) and br and isinstance(br[0], dict):
        computed = (br[0].get("Computed") or {})
    else:
        log.error("get_nav_on_date: unexpected payload shape: %r", data)
        return None

    # Try the usual NAV-ish fields in a safe order
    for key in ("netAccountValue", "accountBalance", "accountBalanceValue"):
        v = computed.get(key)
        if v not in (None, ""):
            try:
                return float(v)
            except (TypeError, ValueError):
                pass

    log.warning("get_nav_on_date: NAV not found in Computed block: %r", computed)
    return None


def _now_et():
    if zoneinfo:
        try:
            return datetime.now(zoneinfo.ZoneInfo("America/New_York"))
        except Exception:
            pass
    return datetime.now(UTC)


def _is_same_et_day(ts: datetime) -> bool:
    return ts.astimezone(_now_et().tzinfo).date() == _now_et().date()


from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def _parse_any_ts(ts):
    """
    epoch seconds/ms, digit strings, or ISO; returns aware UTC datetime or None.
    """
    if ts is None or ts == "":
        return None
    try:
        # numeric / digit-string
        if isinstance(ts, (int, float)):
            t = float(ts)
        else:
            s = str(ts).strip()
            if s.isdigit():
                t = float(s)
            else:
                try:
                    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                except Exception:
                    from dateutil import parser as _p

                    dt = _p.parse(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt.astimezone(UTC)
        if t > 10_000_000_000:  # ms → s
            t /= 1000.0
        if t < 0:
            return None
        return datetime.fromtimestamp(t, tz=UTC)
    except Exception:
        return None


def get_quote(symbol: str, detailFlag: str | None = None) -> dict:
    """
    Raw single-quote JSON from E*TRADE. Delegates to broker_live.get_quote,
    but tolerates implementations that don't accept detailFlag.
    """
    sym = str(symbol).strip().upper()
    try:
        # Try passing the flag positionally if provided
        return (
            _get_quote(sym, detailFlag) if detailFlag is not None else _get_quote(sym)
        )
    except TypeError:
        # Older broker_live.get_quote has no detailFlag param — just call without it
        return _get_quote(sym) or {}
    except Exception:
        return {}


# --- E*TRADE quotes: batch fetch ---
def get_quotes(symbols, detailFlag: str | None = None, **kwargs) -> dict:
    syms = _norm_syms(symbols)
    key = (syms, detailFlag or "ALL")
    hit = _cache_get(key, ttl=2.0)
    if hit is not None:
        return hit
    # existing body: build csv *from syms* and make the HTTP call...
    csv = ",".join(syms)
    # ... existing request/parse into `resp` ...
    # finally:
    _cache_put(key, resp or {})
    return resp or {}


# Optional: a convenience that returns a normalized {SYM: {"last":..,"prev":..}}
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def _fmt_mmddyyyy(dt: datetime) -> str:
    return dt.astimezone(ET).strftime("%m%d%Y")


# --- Build symbol -> {last: float} map for the UI ---


def _num(x):
    """Coerce API values to float or None (also unwraps dict shapes like {'value': 123.45})."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, dict):
        for k in ("value", "raw", "amount"):
            if k in x:
                return _num(x[k])
        return None
    try:
        s = str(x).replace(",", "").strip()
        return float(s) if s else None
    except Exception:
        return None


def get_quotes_map(symbols: list[str]) -> dict[str, dict[str, float]]:
    resp = get_quotes(symbols, detailFlag="ALL")
    qr = (resp or {}).get("QuoteResponse") or {}
    if qr.get("Messages"):
        return {}

    qd = qr.get("QuoteData")
    if not qd:
        return {}
    qlist = [qd] if isinstance(qd, dict) else [x for x in qd if isinstance(x, dict)]

    out: dict[str, dict[str, float]] = {}
    for item in qlist:
        prod = item.get("Product") or {}
        sym = (prod.get("symbol") or "").upper()
        allb = item.get("All") or {}
        intr = item.get("intraday") or {}
        quick = item.get("Quick") or {}

        last = (
            allb.get("lastTrade")
            or intr.get("lastTrade")
            or quick.get("lastTrade")
            or allb.get("lastPrice")
            or quick.get("lastPrice")
        )
        prev = (
            allb.get("previousClose")
            or quick.get("previousClose")
            or allb.get("priorClose")
            or quick.get("priorClose")
            or allb.get("close")
            or quick.get("close")
        )

        # If prev still missing, try to back-solve from netChange
        if prev is None:
            net = allb.get("netChange") or quick.get("netChange")
            if (last is not None) and (net is not None):
                try:
                    prev = float(last) - float(net)
                except Exception:
                    prev = None

        try:
            if sym and last is not None:
                out[sym] = {"last": float(last)}
                if prev is not None:
                    out[sym]["prev"] = float(prev)
        except (TypeError, ValueError):
            pass
    return out


# --- executed orders (count-based) -------------------------------------------
def list_executed_orders_recent(count: int = 50) -> dict:
    acct = account_id_key()
    sess = get_oauth_session()
    url = f"https://api.etrade.com/v1/accounts/{acct}/orders.json"
    params = {
        "status": "EXECUTED",
        "count": max(1, min(int(count or 50), 50)),
        "sortOrder": "DESC",
    }
    r = sess.get(url, params=params, headers={"Accept": "application/json"}, timeout=15)
    r.raise_for_status()
    return r.json() or {}


def extract_funds(bal: dict):
    comp = (
        (bal or {}).get("computedBalance", {}) or (bal or {}).get("Computed", {}) or {}
    )
    # Buying power
    bp = (
        comp.get("marginBuyingPower")
        or comp.get("cashBuyingPower")
        or comp.get("buyingPower")
        or comp.get("cashAvailableForWithdrawal")
    )
    # Settled cash
    settled = (
        comp.get("settledCash")
        or comp.get("cashAvailableForWithdrawal")
        or comp.get("cashBalance")
    )
    try:
        return (
            float(bp) if bp is not None else None,
            float(settled) if settled is not None else None,
        )
    except Exception:
        return (None, None)


# --- numeric helper (guard) ---
try:
    _to_f
except NameError:

    def _to_f(x):
        try:
            if x is None:
                return None
            if isinstance(x, (int, float)):
                return float(x)
            return float(str(x).replace(",", "").strip())
        except Exception:
            return None


def _enrich_with_transactions(rows, days=30):
    """
    For SELL rows, fill price_paid / pl / pl_pct using Transactions data
    (uses gainLoss when available). Mutates rows in place.
    """
    try:
        txj = list_trade_transactions_range(days)
        txs = _normalize_tx_list(txj)
    except Exception:
        txs = []

    # Prebuild simplified view of tx SELLs
    candidates = []
    for t in txs:
        br = t.get("brokerage") or {}
        prod = br.get("product") or {}
        sym = (t.get("symbol") or prod.get("symbol") or "").upper()
        gl = t.get("gainLoss") or t.get("gain")
        try:
            qty = int(abs(float(br.get("quantity") or 0)))
        except Exception:
            qty = 0
        dt = _parse_any_ts(t.get("transactionDate") or t.get("time") or t.get("date"))
        if sym and qty and dt:
            candidates.append({"symbol": sym, "qty": qty, "dt": dt, "gl": gl})

    for r in rows:
        # BUY: show price paid and zero P&L
        if r.get("action") == "BUY":
            r["price_paid"] = r.get("price")
            r["pl"] = 0.0
            r["pl_pct"] = 0.0
            continue

        if r.get("action") != "SELL":
            continue

        # Find nearest SELL transaction by symbol/qty (same day window)
        best = None
        best_delta = None
        for c in candidates:
            if c["symbol"] != r["symbol"] or c["qty"] != int(r["qty"]):
                continue
            delta = abs((c["dt"] - r["_dt"]).total_seconds())
            if best is None or delta < best_delta:
                best, best_delta = c, delta

        if best and best.get("gl") is not None:
            try:
                pl = float(best["gl"])
                qty = float(r["qty"] or 0.0)
                px = float(r.get("price") or 0.0)
                price_paid = round(px - (pl / qty), 2) if qty else 0.0
                denom = price_paid * qty
                r["price_paid"] = price_paid
                r["pl"] = round(pl, 2)
                r["pl_pct"] = round((pl / denom) * 100.0, 2) if denom else 0.0
            except Exception:
                pass
        else:
            # No tx match — at least don’t leave blanks
            r["price_paid"] = 0.0
            r["pl"] = 0.0
            r["pl_pct"] = 0.0


# --- BEGIN: realized P&L buckets --------------------------------------------
from zoneinfo import ZoneInfo


def _to_dt_utc(ts):
    if not ts:
        return None
    # ts can be epoch (sec/ms) or ISO
    try:
        tsv = int(str(ts))
        if tsv > 10_000_000_000:
            return datetime.fromtimestamp(tsv / 1000, tz=ZoneInfo("UTC"))
        return datetime.fromtimestamp(tsv, tz=ZoneInfo("UTC"))
    except Exception:
        try:
            s = str(ts).replace("Z", "+00:00")
            return datetime.fromisoformat(s).astimezone(ZoneInfo("UTC"))
        except Exception:
            return None


def recent_executions_as_trades(count: int = 50) -> list[dict]:
    """
    Newest→oldest EXECUTED trades from Orders API, with ET time and P&L where possible.
    """

    # Normalize orders payload
    def _normalize_orders_list(j: dict) -> list:
        if not j:
            return []
        if "OrdersResponse" in j:
            data = j["OrdersResponse"] or {}
            orders = data.get("Order") or data.get("Orders") or []
        else:
            olr = (j.get("OrderListResponse") or j.get("orderListResponse") or {}) or {}
            orders = olr.get("orders") or olr.get("Order") or []
        if isinstance(orders, dict):
            orders = [orders]
        return orders

    j = list_executed_orders_recent(count)
    orders = _normalize_orders_list(j)

    rows: list[dict] = []
    for o in orders:
        o_ts = (
            o.get("executedTime")
            or o.get("placeTime")
            or o.get("placedTime")
            or o.get("orderTime")
            or o.get("updateTime")
        )

        details = o.get("OrderDetail") or o.get("orderDetail") or []
        if isinstance(details, dict):
            details = [details]
        if not details:
            details = [{}]

        for d in details:
            ts = d.get("filledTime") or d.get("executedTime") or o_ts
            dt_utc = _parse_any_ts(ts) or datetime.now(UTC)
            dt_et = dt_utc.astimezone(ET)

            instrs = d.get("Instrument") or d.get("instrument") or []
            if isinstance(instrs, dict):
                instrs = [instrs]

            for ins in instrs:
                prod = ins.get("Product") or ins.get("product") or {}
                sym = (prod.get("symbol") or ins.get("symbol") or "").upper()
                if not sym:
                    continue

                side = (
                    ins.get("orderAction")
                    or d.get("orderAction")
                    or o.get("orderAction")
                    or ""
                ).upper() or "BUY"

                qty = (
                    ins.get("filledQuantity")
                    or d.get("filledQuantity")
                    or ins.get("orderedQuantity")
                    or d.get("orderedQuantity")
                    or ins.get("quantity")
                    or d.get("quantity")
                    or 0
                )
                try:
                    qty = float(qty or 0)
                except Exception:
                    qty = 0.0
                if qty == 0.0:
                    continue

                price = (
                    ins.get("averageExecutionPrice")
                    or d.get("averageExecutionPrice")
                    or ins.get("limitPrice")
                    or d.get("limitPrice")
                    or ins.get("price")
                    or d.get("price")
                )
                px = _to_f(price)
                if px is None:
                    execs = (
                        ins.get("executions")
                        or ins.get("Execution")
                        or d.get("executions")
                        or []
                    )
                    if isinstance(execs, dict):
                        execs = [execs]
                    for ex in execs:
                        px = _to_f(
                            ex.get("avgExecPrice")
                            or ex.get("execPrice")
                            or ex.get("price")
                        )
                        if px is not None:
                            break
                if px is None:
                    continue

                rows.append(
                    {
                        # 24h ET to match your table; no AM/PM, no zone suffix
                        "time": dt_et.strftime("%Y-%m-%d %H:%M:%S"),
                        "time_et": dt_et.strftime("%Y-%m-%d %H:%M:%S"),
                        "time_utc": dt_utc.isoformat(),
                        "symbol": sym,
                        "action": side,
                        "qty": int(qty) if float(qty).is_integer() else qty,
                        "price": round(px, 2),
                        "amount": round(
                            px * qty * (1.0 if side == "SELL" else -1.0), 2
                        ),
                        "_dt": dt_utc,
                    }
                )

    if not rows:
        # fallback so UI isn't empty
        tx_rows, _ = get_today_trades_and_realized(3)
        for r in tx_rows:
            dt_utc = _parse_any_ts(r.get("time")) or datetime.now(UTC)
            dt_et = dt_utc.astimezone(ET)
            r["_dt"] = dt_utc
            r["time"] = dt_et.strftime("%Y-%m-%d %H:%M:%S")
        rows = tx_rows

    # newest → oldest
    rows.sort(key=lambda r: r["_dt"], reverse=True)

    # Fill price_paid / pl / pl_pct
    _enrich_with_transactions(rows, days=30)  # 21–30 is safe; 30 is simplest

    for r in rows:
        r.pop("_dt", None)
    return rows


# --- BEGIN: public quotes() shim for sell_guard --------------------------------


def _extract_price_fields(q: dict, use_extended: bool = False):
    """
    Normalize E*TRADE quote payloads (regular or extended-hours) into
    { last, bid, ask, time_utc }.
    """
    if not isinstance(q, dict):
        return None

    # Known locations in E*TRADE responses
    regular = q.get("All") or q.get("QuoteData") or q
    ext = q.get("ExtendedHourQuoteDetail") or q.get("Extended") or {}

    src = ext if use_extended and isinstance(ext, dict) else regular

    def _flt(x):
        try:
            return float(x)
        except Exception:
            return None

    last = _flt(
        src.get("lastTrade")
        or src.get("LastTrade")
        or src.get("lastPrice")
        or src.get("LastPrice")
        or src.get("last")
    )
    bid = _flt(src.get("bid") or src.get("Bid"))
    ask = _flt(src.get("ask") or src.get("Ask"))

    # Timestamps show up variably; prefer UTC if present
    ts = (
        src.get("dateTimeUTC")
        or src.get("timeUTC")
        or src.get("TimeUTC")
        or regular.get("dateTimeUTC")
        or regular.get("timeUTC")
        or regular.get("TimeUTC")
    )
    # Fallbacks (epoch millis / seconds)
    if not ts:
        ts = (
            src.get("time")
            or src.get("Time")
            or regular.get("time")
            or regular.get("Time")
        )

    dt_utc = None
    if ts:
        try:
            # E*TRADE sometimes returns epoch millis
            tsv = int(ts)
            if tsv > 10_000_000_000:  # millis
                dt_utc = datetime.fromtimestamp(tsv / 1000, tz=UTC)
            else:  # seconds
                dt_utc = datetime.fromtimestamp(tsv, tz=UTC)
        except Exception:
            # ISO or unknown formats
            try:
                dt_utc = datetime.fromisoformat(
                    str(ts).replace("Z", "+00:00")
                ).astimezone(UTC)
            except Exception:
                dt_utc = None

    return {
        "last": last,
        "bid": bid,
        "ask": ask,
        "time_utc": dt_utc.isoformat() if dt_utc else None,
    }


def quotes(symbols, use_extended: bool = False, per_symbol_fetch=None):
    """
    Public: return normalized quotes for a list of symbols.

    Output shape:
      {
        "AAPL": {"last": 228.12, "bid": 228.10, "ask": 228.13, "time_utc": "…"},
        ...
      }

    Implementation notes:
    - Uses a provided `per_symbol_fetch(sym)` if given; otherwise tries
      `fetch_etrade_quote(sym)` from this module.
    - Parses multiple E*TRADE shapes robustly (All/ExtendedHourQuoteDetail/etc).
    """
    if not symbols:
        return {}

    # Prefer a direct per-symbol fetch helper if caller injects one
    if per_symbol_fetch and callable(per_symbol_fetch):
        fetch_fn = per_symbol_fetch
    else:
        # Use an existing function in this module if present
        try:
            fetch_fn = globals().get("fetch_etrade_quote")
            if not callable(fetch_fn):
                raise AttributeError("fetch_etrade_quote missing")
        except Exception as e:
            raise AttributeError(
                "quotes(): no valid quote fetch function available; "
                "ensure fetch_etrade_quote(sym) exists in etrade_service.py"
            ) from e

    out = {}
    for sym in symbols:
        try:
            raw = fetch_fn(sym)
            norm = _extract_price_fields(raw or {}, use_extended=use_extended)
            out[sym] = norm or {
                "last": None,
                "bid": None,
                "ask": None,
                "time_utc": None,
            }
        except Exception:
            # Never explode the caller; provide a null record so the guard can log/skips
            out[sym] = {"last": None, "bid": None, "ask": None, "time_utc": None}
    return out


# --- END: public quotes() shim for sell_guard ----------------------------------


def transactions_as_trades(days: int = 3) -> list[dict]:
    """
    /transactions -> simple trade rows with cost basis & P&L when available.
    Fields: time(ms), symbol, action(BUY/SELL), qty, price, amount, price_paid, pl, pl_pct
    """
    j = list_trade_transactions_range(days)
    txs = (j.get("TransactionListResponse") or {}).get("Transaction") or []
    if isinstance(txs, dict):
        txs = [txs]

    out: list[dict] = []
    for t in txs:
        br = t.get("brokerage") or {}
        prod = br.get("product") or {}
        sym = (prod.get("symbol") or "").upper()
        if not sym:
            continue

        # Type / side / qty / price
        typ = str(t.get("transactionType") or "").upper()  # "BOUGHT" / "SOLD"
        qty_raw = br.get("quantity") or 0
        try:
            qty_val = int(float(qty_raw))
        except:
            qty_val = 0
        side = "SELL" if (qty_val < 0 or typ.startswith("SOLD")) else "BUY"
        qty = abs(qty_val)

        try:
            price = float(br.get("price") or 0.0)
        except:
            price = 0.0

        # Broker cashflow (+ for SELL, - for BUY) if they provide it
        try:
            amount = float(t.get("amount"))
        except:
            amount = round(price * qty * (1 if side == "SELL" else -1), 2)

        # Gain/loss is sometimes provided (esp. for closed sells)
        gl = t.get("gainLoss") or t.get("gain")

        price_paid = None
        pl = None
        pl_pct = None

        if side == "SELL" and qty > 0:
            # Back out cost basis per share from gainLoss when present
            if gl is not None:
                try:
                    pl = float(gl)
                    price_paid = round(price - (pl / qty), 2)
                    denom = (price_paid or 0.0) * qty
                    pl_pct = round((pl / denom) * 100.0, 2) if denom else 0.0
                except:
                    pass
        else:
            # For BUY, "price paid" is simply the trade price; realized P&L is 0 now
            price_paid = round(price, 2)
            pl = 0.0
            pl_pct = 0.0

        # Timestamp (ms since epoch if present)
        try:
            ts = int(t.get("transactionDate") or 0)
        except:
            ts = 0

        row = {
            "time": ts,
            "symbol": sym,
            "action": side,
            "qty": qty,
            "price": price,
            "amount": round(amount, 2),
            "price_paid": price_paid,  # <- for your table
            "pricePaid": price_paid,  # <- dual key for UI compatibility
            "pl": pl,
            "pl_pct": pl_pct,
        }
        out.append(row)

    out.sort(key=lambda x: x["time"], reverse=True)
    return out


_ET = timezone(timedelta(hours=-5))  # you likely already have a _today_et()


def _today_et():
    # If you already have this, keep using yours
    return datetime.now(_ET).date()


def _prev_business_days(n, end_date=None):
    d = end_date or _today_et()
    days = []
    while len(days) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:  # Mon–Fri; (skip holidays unless you maintain a list)
            days.append(d)
    return list(reversed(days))  # oldest -> newest


def pdt_window_dates():
    """Return the set of ET dates in the current rolling 5-business-day window (including today if weekday)."""
    today = _today_et()
    dates = [today] if today.weekday() < 5 else []
    dates = _prev_business_days(5 - len(dates), end_date=today) + dates
    return set(dates)


def recompute_pdt_counts(executed_orders_payload):
    """
    Build fresh per-date day trade counts *only for* the current PDT window.
    You can adapt this to your existing structure.
    """
    win = pdt_window_dates()
    counts = {}  # {date: count}
    # Your payload shape looks like et.list_executed_orders(days=...) -> OrdersResponse.Order[].OrderDetail[].Instrument[]
    orders = (executed_orders_payload.get("OrdersResponse") or {}).get("Order") or []
    # Build {date_et: [(sym, action, qty)]}
    by_date = {}
    for o in orders:
        for d in o.get("OrderDetail") or []:
            # normalize ET date from your timestamps
            dt = datetime.fromtimestamp(
                (d.get("executedTime") or d.get("placedTime") or 0) / 1000, tz=_ET
            ).date()
            if dt not in win:
                continue
            for ins in d.get("Instrument") or []:
                sym = (ins.get("Product") or {}).get("symbol") or ""
                act = (ins.get("orderAction") or "").upper()
                qty = (
                    float(ins.get("filledQuantity") or ins.get("orderedQuantity") or 0)
                    or 0.0
                )
                by_date.setdefault(dt, []).append((sym, act, qty))

    # Count day trades per date: simple approximation — any symbol with at least one BUY and one SELL that day
    for dt, rows in by_date.items():
        actions_by_sym = {}
        for sym, act, _ in rows:
            actions_by_sym.setdefault(sym, set()).add(act)
        counts[dt.isoformat()] = sum(
            1 for acts in actions_by_sym.values() if "BUY" in acts and "SELL" in acts
        )

    return counts


def _mmddyyyy(d) -> str:
    return d.strftime("%m%d%Y")


def _ymd(d):
    return d.strftime("%Y-%m-%d")


def _normalize_orders_list(j: dict) -> list:
    """
    E*TRADE returns either:
      - OrdersResponse -> Order (list)
      - OrderListResponse -> orders / Order (varies by tenant)
    Normalize to a list of orders.
    """
    if not j:
        return []
    if "OrdersResponse" in j:
        data = j["OrdersResponse"] or {}
        orders = data.get("Order") or data.get("Orders") or []
    else:
        olr = (j.get("OrderListResponse") or j.get("orderListResponse") or {}) or {}
        orders = olr.get("orders") or olr.get("Order") or []
    if isinstance(orders, dict):
        orders = [orders]
    return orders


def get_today_trades_cashflow():
    """
    Live intraday proxy built from EXECUTED orders (no posting delay).
    Amount sign: SELL = +, BUY = -.
    """
    j = list_executed_orders_recent(50)
    orders = _normalize_orders_list(j)
    trades, cash = [], 0.0

    for o in orders:
        # Details block
        details = o.get("OrderDetail") or o.get("orderDetail") or []
        if isinstance(details, dict):
            details = [details]
        for od in details:
            ts_raw = (
                od.get("executedTime") or od.get("placedTime") or od.get("updateTime")
            )
            ts = _parse_any_ts(ts_raw)

            # Only keep today's fills (ET timezone)
            if not _is_same_et_day(ts):
                continue

            insts = od.get("Instrument") or od.get("instrument") or []
            if isinstance(insts, dict):
                insts = [insts]

            for ins in insts:
                side = (ins.get("orderAction") or "").upper()  # BUY/SELL
                qty = int(ins.get("filledQuantity") or ins.get("orderedQuantity") or 0)
                price = float(
                    ins.get("averageExecutionPrice") or od.get("limitPrice") or 0.0
                )
                sym = ((ins.get("Product") or {}).get("symbol") or "").upper()

                if qty and price:
                    amt = price * qty * (1 if side == "SELL" else -1)
                    trades.append(
                        {
                            "time": ts.isoformat(),
                            "symbol": sym,
                            "action": side,
                            "qty": qty,
                            "price": price,
                            "amount": round(amt, 2),
                        }
                    )
                    cash += amt

    trades.sort(key=lambda x: x["time"], reverse=True)
    return trades, round(cash, 2)


def list_executed_orders_today() -> dict:
    acct = account_id_key()
    sess = get_oauth_session()
    d = _today_et()
    url = f"https://api.etrade.com/v1/accounts/{acct}/orders.json"
    params = {
        "fromDate": _mmddyyyy(d),
        "toDate": _mmddyyyy(d),
        "status": "EXECUTED",
        "count": 50,
        "sortOrder": "DESC",
    }
    r = sess.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json() or {}


def list_trade_transactions_range(days: int = 3) -> dict:
    acct = account_id_key()
    sess = get_oauth_session()
    end = _now_et()
    start = end - timedelta(days=max(1, int(days)))
    url = f"https://api.etrade.com/v1/accounts/{acct}/transactions.json"
    params = {
        "startDate": _fmt_mmddyyyy(start),
        "endDate": _fmt_mmddyyyy(end),
        "category": "TRADE",
        "count": 50,  # E*TRADE enforces 1..50
    }
    r = sess.get(url, params=params, headers={"Accept": "application/json"}, timeout=15)
    if r.status_code != 200:
        # surface broker message
        try:
            body = r.json()
        except Exception:
            body = r.text
        raise RuntimeError(f"transactions call failed ({r.status_code}): {body}")
    return r.json() or {}


def _normalize_tx_list(j: dict) -> list:
    """
    TransactionListResponse -> Transaction (list or dict).
    """
    tlr = (
        j.get("TransactionListResponse") or j.get("transactionListResponse") or {}
    ) or {}
    txs = (tlr.get("Transaction") or tlr.get("transactions") or []) or []
    if isinstance(txs, dict):
        txs = [txs]
    return txs


def get_today_trades_and_realized(days_back: int = 3):
    """
    'Official' realized comes from transactions, but most tenants do NOT include
    gain/loss intraday. We still return a properly-populated trades list for today.
    """
    j = list_trade_transactions_range(days_back)
    txs = _normalize_tx_list(j)
    trades, realized = [], 0.0

    for t in txs:
        ts = _parse_any_ts(t.get("transactionDate") or t.get("time") or t.get("date"))
        if not _is_same_et_day(ts):
            continue

        br = t.get("brokerage") or {}
        prod = br.get("product") or {}
        sym = (t.get("symbol") or prod.get("symbol") or "").upper()

        qty_raw = br.get("quantity")  # sells often negative
        try:
            qty_val = int(float(qty_raw or 0))
        except Exception:
            qty_val = 0
        side = (
            "SELL"
            if (
                qty_val < 0
                or str(t.get("transactionType", "")).upper().startswith("SOLD")
            )
            else "BUY"
        )
        qty = abs(qty_val)

        price = 0.0
        try:
            price = float(br.get("price") or 0.0)
        except Exception:
            pass

        # Cash amount (proceeds) as returned by broker (already signed)
        try:
            amt = float(t.get("amount"))
        except Exception:
            amt = price * qty * (1 if side == "SELL" else -1)

        # 'gainLoss' is rarely present intraday; keep summing if provided
        gl = t.get("gainLoss") or t.get("gain")
        if gl is not None:
            try:
                realized += float(gl)
            except Exception:
                pass

        trades.append(
            {
                "time": ts.isoformat(),
                "symbol": sym,
                "action": side,
                "qty": qty,
                "price": price,
                "amount": round(amt, 2),
            }
        )

    trades.sort(key=lambda x: x["time"], reverse=True)
    return trades, round(realized, 2)


def list_executed_orders(days: int = 5) -> dict:
    acct = account_id_key()
    sess = get_oauth_session()
    end = _today_et()
    start = end - timedelta(days=days)
    url = f"https://api.etrade.com/v1/accounts/{acct}/orders.json"
    params = {
        "fromDate": _mmddyyyy(start),
        "toDate": _mmddyyyy(end),
        "status": "EXECUTED",
        "count": 50,  # safe cap
        "sortOrder": "DESC",
    }
    r = sess.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def list_trade_transactions(days: int = 5) -> dict:
    aid = account_id_key()
    ses = get_oauth_session()
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    url = f"{API_BASE}/accounts/{aid}/transactions.json"
    params = {
        "startDate": _ymd(start),
        "endDate": _ymd(end),
        "category": "TRADE",
        "count": 200,
    }
    r = ses.get(url, params=params, timeout=15)
    if r.status_code == 204:
        return {}
    r.raise_for_status()
    return _json_or_empty(r)


def get_recent_trades_and_realized(days: int = 5):
    """
    Returns (trades_list, realized_sum_float) for the last `days`.
    trades_list items: {time, symbol, action, qty, price, amount}
    """
    # Executions -> recent trades
    orders = list_executed_orders(days) or {}
    raw_orders = (orders.get("OrderListResponse", {}) or {}).get("orders", []) or []
    trades = []
    for o in raw_orders:
        ts = o.get("executedTime") or o.get("placedTime") or o.get("updateTime")
        for leg in o.get("orderLegs") or []:
            sym = (leg.get("symbol") or "").upper()
            side = (leg.get("side") or o.get("orderAction") or "").upper()
            for ex in leg.get("executions") or []:
                price = float(ex.get("avgExecPrice") or ex.get("price") or 0)
                qty = int(ex.get("quantity") or 0)
                trades.append(
                    {
                        "time": ts,
                        "symbol": sym,
                        "action": side,  # BUY / SELL
                        "qty": qty,
                        "price": price,
                        "amount": round(price * qty * (1 if side == "SELL" else -1), 2),
                    }
                )
    trades.sort(key=lambda x: str(x.get("time") or ""), reverse=True)
    trades = trades[:50]

    # Transactions -> realized P&L sum
    realized = 0.0
    tx = list_trade_transactions(days) or {}
    for t in (tx.get("TransactionListResponse", {}) or {}).get(
        "transactions", []
    ) or []:
        gl = t.get("gainLoss") or t.get("gain")
        try:
            if gl is not None:
                realized += float(gl)
        except Exception:
            pass

    return trades, round(realized, 2)


from datetime import timedelta

# ---- Canonical helpers (no self-imports, no class dependency) ---------------

_sess_cache = None


import os
import json
from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv

load_dotenv("etrade.env")

ETRADE_BASE_URL = "https://api.etrade.com"
TOKEN_FILE = "etrade_tokens.json"


def _load_tokens():
    if not os.path.exists(TOKEN_FILE):
        raise RuntimeError(
            "E*TRADE tokens not found. Run etrade_auth_flow.py or use the reconnect button."
        )
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)


def get_oauth_session():
    consumer_key = os.getenv("ETRADE_API_KEY")
    consumer_secret = os.getenv("ETRADE_API_SECRET")
    if not consumer_key or not consumer_secret:
        raise RuntimeError("Missing ETRADE_API_KEY / ETRADE_API_SECRET in etrade.env")

    tokens = _load_tokens()
    oauth_token = tokens.get("oauth_token")
    oauth_token_secret = tokens.get("oauth_token_secret")
    if not oauth_token or not oauth_token_secret:
        raise RuntimeError("etrade_tokens.json missing oauth_token / oauth_token_secret")

    return OAuth1Session(
        consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=oauth_token,
        resource_owner_secret=oauth_token_secret,
    )


def account_identity():
    """
    Fetch primary E*TRADE account identity via /v1/accounts/list.json.
    Returns:
      {
        "account_id": ...,
        "account_id_key": ...,
        "account_type": ...,
        "account_type_display": ...
      }
    """
    sess = get_oauth_session()
    url = f"{ETRADE_BASE_URL}/v1/accounts/list.json"
    r = sess.get(url, timeout=15)
    r.raise_for_status()
    j = r.json()

    accounts = (
        j.get("AccountListResponse", {})
         .get("Accounts", {})
         .get("Account", [])
    )

    if not accounts:
        raise RuntimeError("No accounts returned from E*TRADE /v1/accounts/list.json")

    pick = None
    for a in accounts:
        t = (a.get("accountType") or "").upper()
        if "BROKERAGE" in t or "INDIVIDUAL" in t or "MARGIN" in t:
            pick = a
            break
    if pick is None:
        pick = accounts[0]

    return {
        "account_id": pick.get("accountId"),
        "account_id_key": pick.get("accountIdKey"),
        "account_type": pick.get("accountType"),
        "account_type_display": pick.get("accountDesc") or pick.get("accountType"),
    }


def get_default_account_id_key() -> str:
    ident = account_identity()
    key = ident.get("account_id_key")
    if not key:
        raise RuntimeError("No account_id_key in E*TRADE identity response")
    return key


def get_positions():
    """
    Return raw positions payload from E*TRADE.
    dashboard.py will normalize via _normalize_positions_payload.
    """
    acct_key = get_default_account_id_key()
    sess = get_oauth_session()

    url = f"{ETRADE_BASE_URL}/v1/accounts/{acct_key}/portfolio.json"
    params = {
        "view": "QUICK",
        "sortBy": "MARKET_VALUE",
        "sortOrder": "DESC",
        "count": 500,
    }

    r = sess.get(url, params=params, timeout=15)

    if r.status_code == 204 or not (r.text or "").strip():
        return {}

    r.raise_for_status()
    return r.json()

# Optional alias if other code uses it
get_account_id_key = account_id_key

# ---- Canonical helpers (no self-imports, no duplicates) --------------------
_sess_cache = None


# --- replace your list_trade_transactions_today() with this ---
def list_trade_transactions_today() -> dict:
    acct = account_id_key()
    sess = get_oauth_session()
    et_today = _today_et()

    url = f"https://api.etrade.com/v1/accounts/{acct}/transactions.json"

    attempts = [
        # a) strict today w/ category filter
        {
            "startDate": _mmddyyyy(et_today),
            "endDate": _mmddyyyy(et_today),
            "transactionCategory": "TRADE",
            "count": 50,
            "sortOrder": "DESC",
        },
        # b) strict today without category (some accounts don’t expose the filter)
        {
            "startDate": _mmddyyyy(et_today),
            "endDate": _mmddyyyy(et_today),
            "count": 50,
            "sortOrder": "DESC",
        },
        # c) widen window (yesterday→today) w/ category
        {
            "startDate": _mmddyyyy(et_today - timedelta(days=1)),
            "endDate": _mmddyyyy(et_today),
            "transactionCategory": "TRADE",
            "count": 50,
            "sortOrder": "DESC",
        },
    ]

    last_resp = None
    for params in attempts:
        p = {k: v for k, v in params.items() if v is not None}
        r = sess.get(url, params=p, timeout=15)
        last_resp = r
        if r.status_code == 200:
            try:
                return r.json() or {}
            except Exception:
                return {}
        # keep trying only if it’s a 400 (bad params); bail on other codes
        if r.status_code != 400:
            break

    body = ""
    try:
        body = last_resp.text[:300]
    except Exception:
        pass
    raise RuntimeError(f"transactions call failed ({last_resp.status_code}): {body}")

    def _g(d, *keys):
        """get first present key; supports ('instrument','symbol') path."""
        for k in keys:
            if isinstance(k, tuple):
                node = d.get(k[0], {})
                if node.get(k[1]) is not None:
                    return node[k[1]]
            elif d.get(k) is not None:
                return d[k]
        return None

    trades = []
    for o in orders:
        ts = _g(o, "executedTime", "placedTime", "orderTime", "updateTime")
        legs = o.get("orderLegCollection") or o.get("orderLegs") or []
        for leg in legs:
            sym = (_g(leg, "symbol", ("instrument", "symbol")) or "").upper()
            side = (
                _g(leg, "side", "orderAction") or _g(o, "orderAction") or ""
            ).upper()
            execs = leg.get("executions") or leg.get("execution") or []
            for ex in execs:
                qty = _g(ex, "quantity", "execQuantity", "filledQuantity") or 0
                try:
                    qty = int(float(qty))
                except:
                    qty = 0
                px = _g(ex, "avgExecPrice", "price", "execPrice") or 0.0
                try:
                    px = float(px)
                except:
                    px = 0.0
                tstamp = _g(ex, "time", "execTime") or ts
                trades.append(
                    {
                        "time": tstamp,
                        "symbol": sym,
                        "action": side or "TRADE",
                        "qty": qty,
                        "price": px,
                        # convenient cash-flow sign for UI P&L column
                        "amount": round((px * qty) * (1 if side == "SELL" else -1), 2),
                    }
                )

    trades.sort(key=lambda x: str(x["time"]), reverse=True)
    trades = trades[:count]

    # ---------- Realized via closed gain/loss; fallback to transactions ----------
    realized = 0.0
    try:
        url_gl = (
            f"https://api.etrade.com/v1/accounts/{acct}/gainloss/closedpositions.json"
        )
        rgl = sess.get(
            url_gl, params={"startDate": _ymd(start), "endDate": _ymd(end)}, timeout=15
        )
        if rgl.ok:
            gj = rgl.json() or {}
            rows = (
                gj.get("ClosedPositions", {}).get("closedPosition", [])
                or gj.get("closedPosition", [])
                or []
            )
            for row in rows:
                val = _g(row, "realizedGainLoss", "gainLoss", "gainloss")
                if val is not None:
                    try:
                        realized += float(val)
                    except:
                        pass
    except Exception:
        pass

    if realized == 0.0:
        # Fallback approximation from transactions
        url_tx = f"https://api.etrade.com/v1/accounts/{acct}/transactions.json"
        ptx = {"startDate": _ymd(start), "endDate": _ymd(end), "count": 200}
        rtx = sess.get(url_tx, params=ptx, timeout=15)
        if rtx.ok:
            tj = rtx.json() or {}
            items = (
                tj.get("TransactionListResponse", {}).get("transactions", [])
                or tj.get("transactions", [])
                or []
            )
            for t in items:
                action = (
                    _g(t, "action", "transactionType", "description") or ""
                ).upper()
                try:
                    if "SELL" in action:
                        realized += float(
                            _g(t, "netProceeds", "amount", "netAmount") or 0.0
                        )
                    elif "BUY" in action:
                        realized -= float(_g(t, "amount", "netAmount") or 0.0)
                except:
                    pass

    return trades, round(realized, 2)


def list_recent_trades(days: int = 5) -> list[dict[str, Any]]:
    """
    Recently executed trades via Orders API; falls back to Transactions API.
    """
    et, aid = _svc()
    end = datetime.utcnow()
    start = end - timedelta(days=max(1, days))
    out: list[dict[str, Any]] = []

    # Primary: Orders (EXECUTED)
    try:
        params = {
            "fromDate": start.strftime("%Y-%m-%d"),
            "toDate": end.strftime("%Y-%m-%d"),
            "status": "EXECUTED",
            "count": 200,
            "sortOrder": "DESC",
        }
        resp = et._get(f"/accounts/{aid}/orders.json", params=params)
        orders = (resp.get("OrdersResponse") or {}).get("Order") or []
        if isinstance(orders, dict):
            orders = [orders]

        for o in orders:
            details = o.get("OrderDetail") or []
            if isinstance(details, dict):
                details = [details]
            for d in details:
                status = (d.get("status") or "").upper()
                if status not in {
                    "EXECUTED",
                    "FILLED",
                    "PARTIALLY_EXECUTED",
                    "PARTIAL",
                }:
                    continue
                when = (
                    d.get("executedTime")
                    or d.get("placedTime")
                    or o.get("placedTime")
                    or ""
                )
                instrs = d.get("Instrument") or []
                if isinstance(instrs, dict):
                    instrs = [instrs]
                for ins in instrs:
                    prod = ins.get("Product") or {}
                    sym = (prod.get("symbol") or "").upper()
                    action = (
                        ins.get("orderAction")
                        or d.get("orderAction")
                        or o.get("orderAction")
                        or ""
                    ).upper()
                    qty = (
                        ins.get("filledQuantity")
                        or d.get("filledQuantity")
                        or ins.get("quantity")
                        or 0
                    )
                    px = (
                        ins.get("averageExecutionPrice")
                        or d.get("averageExecutionPrice")
                        or ins.get("limitPrice")
                        or 0.0
                    )
                    try:
                        qty = int(float(qty or 0))
                    except Exception:
                        qty = 0
                    try:
                        px = float(px or 0.0)
                    except Exception:
                        px = 0.0
                    if sym and qty:
                        out.append(
                            {
                                "time": str(when),
                                "symbol": sym,
                                "action": action or "BUY",
                                "qty": qty,
                                "price": px,
                                "pl": 0.0,
                            }
                        )
        if out:
            out.sort(key=lambda x: str(x.get("time", "")), reverse=True)
            return out
    except Exception as e:
        log.exception("orders fetch failed: %s", e)

    # Fallback: Transactions
    try:
        tparams = {
            "startDate": start.strftime("%Y-%m-%d"),
            "endDate": end.strftime("%Y-%m-%d"),
        }
        raw = (
            _eget(f"/accounts/{account_id_key}/orders.json", params={"status": "OPEN"})
            or {}
        )
        items = (data.get("TransactionListResponse") or {}).get("Transaction") or []
        if isinstance(items, dict):
            items = [items]
        for t in items:
            sym = (
                t.get("symbol") or (t.get("Product") or {}).get("symbol") or ""
            ).upper()
            qty = t.get("quantity") or t.get("qty") or 0
            if not sym or not qty:
                continue
            act = (
                t.get("transactionType") or t.get("type") or t.get("subType") or ""
            ).upper()
            if not act:
                desc = (t.get("description") or "").upper()
                act = "SELL" if "SELL" in desc else ("BUY" if "BUY" in desc else "")
            px = t.get("price") or t.get("tradePrice") or 0.0
            ts = t.get("transactionDate") or t.get("date") or t.get("time") or ""
            try:
                qty = int(float(qty))
            except Exception:
                qty = 0
            try:
                px = float(px or 0.0)
            except Exception:
                px = 0.0
            if act in {"BUY", "SELL", "BUY_TO_COVER", "SELL_SHORT"}:
                out.append(
                    {
                        "time": str(ts),
                        "symbol": sym,
                        "action": act,
                        "qty": qty,
                        "price": px,
                        "pl": 0.0,
                    }
                )
        out.sort(key=lambda x: str(x.get("time", "")), reverse=True)
        return out
    except Exception as e:
        log.exception("transactions fallback failed: %s", e)

    return out


# ---------------- HTTP helpers (always go through broker_live session) ----------------
# --- NEW helpers (put near your other small helpers) --------------------------
def _uf(x):
    """safe float"""
    try:
        return float(x)
    except Exception:
        return None


def _sym_upper(x):
    return (str(x or "")).strip().upper()


def _dig_available_qty(pos: dict) -> float | None:
    """
    Try multiple keys E*TRADE uses for 'shares you can sell now' on an equity position.
    Falls back to long quantity if no explicit available key exists.
    """
    cand_keys = [
        "availableQty",
        "availableQuantity",
        "availQty",
        "openQty",  # common variants
        "longAvailableQty",
        "longAvailableQuantity",
    ]
    # long/position qty fallbacks
    long_keys = [
        "longQty",
        "longQuantity",
        "positionQty",
        "positionQuantity",
        "quantity",
    ]

    # look for explicit 'available' first
    for k in cand_keys:
        v = pos.get(k)
        fv = _uf(v)
        if fv is not None:
            return max(0.0, fv)

    # fall back to long qty if nothing else
    for k in long_keys:
        v = pos.get(k)
        fv = _uf(v)
        if fv is not None:
            return max(0.0, fv)

    return None


def _eget(path: str, params: dict | None = None):
    s = _sesh()
    r = s.get(
        f"{_BASE}{path}", params=params or {}, headers={"Accept": "application/json"}
    )
    r.raise_for_status()
    return r


def _epost(path, body):
    """
    Small helper for POSTs that:
      - uses the signed OAuth session
      - raises on HTTP >= 400 **including the request payload** so callers
        (sell_guard, live loop, etc.) can see exactly what we sent.
    """
    s = get_oauth_session()
    url = f"https://api.etrade.com/v1{path}"

    try:
        r = s.post(
            url,
            json=body,
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        # Transport / session failure before HTTP status
        raise RuntimeError(
            f"etrade POST {path} transport error: {e!r} | payload={body!r}"
        )

    if r.status_code >= 400:
        try:
            err = r.json()
        except Exception:
            err = (r.text or "").strip()

        raise RuntimeError(
            f"etrade POST {path} -> {r.status_code}: {err} | payload={body!r}"
        )

    # Happy path – best effort JSON decode
    try:
        return r.json()
    except Exception:
        return {"raw_text": r.text}


# Back-compat aliases (catch any legacy calls)
_get = _eget
_post = _epost

# ─────────────────────────────────────────────────────────────────────────────
# OAuth liveness + keepalive (append near end of services/etrade_service.py)
# ─────────────────────────────────────────────────────────────────────────────
import threading
from datetime import timedelta, timezone

try:
    from zoneinfo import ZoneInfo  # py>=3.9
except Exception:
    ZoneInfo = None

_ET = ZoneInfo("America/New_York") if ZoneInfo else timezone(timedelta(hours=-5))

_AUTH_DEAD = False
_last_api_hit = 0.0


class AuthExpiredError(RuntimeError):
    pass


def _is_auth_error(exc: Exception | str) -> bool:
    s = str(exc)
    # E*TRADE tends to use 401/Unauthorized or oauth_problem messages when auth dies
    return (
        "oauth_problem" in s.lower()
        or "token_rejected" in s.lower()
        or "unauthorized" in s.lower()
        or "401" in s
    )


# Save originals to wrap
_orig__eget = _eget
_orig__epost = _epost


def _wrap_eget(path: str, params: dict | None = None):
    global _last_api_hit, _AUTH_DEAD
    try:
        r = _orig__eget(path, params)
        _last_api_hit = time.time()
        return r
    except Exception as e:
        if _is_auth_error(e):
            _AUTH_DEAD = True
        raise


def _wrap_epost(path: str, body: dict):
    global _last_api_hit, _AUTH_DEAD
    try:
        r = _orig__epost(path, body)
        _last_api_hit = time.time()
        return r
    except Exception as e:
        if _is_auth_error(e):
            _AUTH_DEAD = True
        raise


# Swap in wrappers so all higher-level funcs benefit
_eget = _wrap_eget
_epost = _wrap_epost


def auth_ok() -> bool:
    """
    Best-effort: returns False if we’ve observed an OAuth failure since last re-auth.
    (Daily midnight ET expiration still requires manual re-auth.)
    """
    if _AUTH_DEAD:
        return False
    return True


def keepalive_daemon(interval_min: int = 60):
    """Ping a cheap endpoint periodically to avoid inactivity expiry (best-effort)."""
    global _AUTH_DEAD
    while True:
        try:
            # sleep first so we don't hammer at import time
            time.sleep(max(60, int(interval_min * 60)))
            if _AUTH_DEAD:
                continue
            # This endpoint is light and widely permitted; we ignore the body.
            _eget("/accounts/list.json")
        except Exception as e:
            # If auth-related, flip the flag; otherwise just swallow and retry later.
            if _is_auth_error(e):
                _AUTH_DEAD = True


# Start the keepalive thread unless explicitly disabled
try:
    if os.getenv("ETRADE_KEEPALIVE", "1").lower() not in ("0", "false", "no"):
        threading.Thread(target=keepalive_daemon, args=(60,), daemon=True).start()
except Exception:
    pass

# ---------------- Account helpers ----------------


def _primary_account_id() -> str:
    """Use env override if present, else discover via accounts/list."""
    return (
        os.getenv("ETRADE_ACCOUNT_ID_KEY")
        or os.getenv("ACCOUNT_ID_KEY")
        or get_account_id_key()
    )


# ---------------- Quotes ----------------


def _extract_last_price(qd: dict) -> float | None:
    if not isinstance(qd, dict):
        return None
    blocks = [qd.get("All") or {}, qd.get("Intraday") or {}, qd]
    for d in blocks:
        for key in ("lastTrade", "lastPrice", "close", "previousClose"):
            v = d.get(key)
            try:
                if v is not None:
                    return float(v)
            except Exception:
                pass
    return None

# wherever you compute funds
def compute_cash_fields(bal: dict) -> tuple[float, float]:
    # prefer buying power, then available, then settled
    def _f(x): 
        try: return float(x)
        except: return None

    fields = {
        "cashBuyingPower": _f(bal.get("cashBuyingPower")),
        "cashAvailableForWithdrawal": _f(bal.get("cashAvailableForWithdrawal")),
        "settledCash": _f(bal.get("settledCash")),
        "cashBalance": _f(bal.get("cashBalance")),
    }
    # Pick best estimates
    buying_power = next((v for k,v in fields.items() if v is not None and k in ("cashBuyingPower","cashAvailableForWithdrawal")), None)
    settled = next((v for k,v in fields.items() if v is not None and k in ("settledCash","cashAvailableForWithdrawal","cashBuyingPower","cashBalance")), None)
    return (settled or 0.0, buying_power or 0.0)

def get_funds():
    sess = get_oauth_session()
    ident = account_identity()
    try:
        bal = fetch_balances_resilient(sess, ident["account_id_key"], ident["account_id"])
        settled, bp = compute_cash_fields(bal)
        return settled, bp, bal
    except Exception as e:
        # fail CLOSED
        log.error("BALANCES: %s", e)
        return 0.0, 0.0, None

def fetch_etrade_quote(symbols: str | Iterable[str]) -> float | dict[str, float] | None:
    """
    If given a single symbol (str) -> returns the last price float (or None).
    If given an iterable -> returns {symbol: last_price} for those found.
    """
    if isinstance(symbols, str):
        sym_list = [symbols.strip().upper()]
        single = True
    else:
        sym_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
        single = False

    if not sym_list:
        return None if single else {}

    data = _get_quote(",".join(sym_list)) or {}
    resp = data.get("QuoteResponse") or data.get("QuotesResponse") or {}
    items = resp.get("QuoteData") or []
    if isinstance(items, dict):
        items = [items]

    out: dict[str, float] = {}
    for qd in items:
        prod = qd.get("Product") or {}
        sym = (prod.get("symbol") or "").upper()
        px = _extract_last_price(qd)
        if sym and (px is not None):
            out[sym] = px

    return out.get(sym_list[0]) if single else out


# ---------------- Portfolio / Balances (backwards-compatible API) ----------------


# --- Portfolio / Balances (backwards-compatible API) ---

import logging
import requests

log = logging.getLogger(__name__)

ETRADE_BASE_URL = "https://api.etrade.com"  # keep whatever you already use


def get_default_account() -> dict:
    """
    Resolve the default/brokerage account to use.
    Tries your existing account_identity() helper; adjust mapping if needed.
    """
    ident = account_identity()  # you already have this
    if not ident:
        raise RuntimeError("No account_identity() data returned from E*TRADE")

    # Support both legacy flat + nested shapes.
    # Example expected keys:
    #   account_id, account_id_key, account_type, account_type_display
    acct = {}

    # Flat style
    if ident.get("account_id_key") or ident.get("accountIdKey"):
        acct = {
            "account_id": ident.get("account_id") or ident.get("accountId"),
            "account_id_key": ident.get("account_id_key") or ident.get("accountIdKey"),
            "account_type": ident.get("account_type") or ident.get("accountType"),
            "account_type_display": ident.get("account_type_display") or ident.get("accountTypeDesc"),
        }
        return acct

    # If your account_identity returns list-style Accounts, pick first brokerage.
    accounts = (
        ident.get("Accounts", {}).get("Account", [])
        or ident.get("AccountList", [])
        or []
    )
    if not isinstance(accounts, list):
        accounts = [accounts]

    if not accounts:
        raise RuntimeError("No accounts returned from E*TRADE")

    # Prefer INDIVIDUAL / BROKERAGE type
    preferred = None
    for a in accounts:
        t = (a.get("accountType") or a.get("account_type") or "").upper()
        if "BROKERAGE" in t or "INDIVIDUAL" in t:
            preferred = a
            break
    acct = preferred or accounts[0]

    return {
        "account_id": acct.get("accountId") or acct.get("account_id"),
        "account_id_key": acct.get("accountIdKey") or acct.get("account_id_key"),
        "account_type": acct.get("accountType") or acct.get("account_type"),
        "account_type_display": acct.get("accountDesc") or acct.get("account_type_display"),
    }


# ---------------- Portfolio / Balances (normalized) ----------------

# ===== CANONICAL ACCOUNT SUMMARY (OVERRIDES EARLIER VERSIONS) =====

# ===== CANONICAL ACCOUNT SUMMARY (OVERRIDES EARLIER VERSIONS) =====

# ===== CANONICAL ACCOUNT SUMMARY (OVERRIDES EARLIER VERSIONS) =====

def get_account_summary(account_id_key: str | None = None) -> dict:
    """
    Normalized snapshot of balances for the dashboard.

    Returns:
      {
        "account_id": str | None,
        "account_key": str | None,
        "account_type": str | None,
        "account_type_display": str | None,
        "nav": float,              # Net Account Value (or best approximation)
        "available_funds": float,  # cash / buying power (what you can actually deploy)
        "cash_balance": float,     # total cash balance from E*TRADE (can include unsettled)
        "settled_cash": float,     # settled cash for investment (if E*TRADE reports it)
        "raw": dict,               # raw balances payload (may be {}),
      }

    Never raises on HTTP errors; always returns a well-shaped dict so callers
    (dashboard, live loop, etc.) never blow up.
    """

    # ---------- helpers ----------
    def _f(v, default: float = 0.0) -> float:
        try:
            if v is None or v == "":
                return float(default)
            return float(str(v).replace(",", ""))
        except Exception:
            return float(default)

    def _extract_balance_view(raw: dict) -> dict | None:
        """
        Accepts a variety of E*TRADE balance shapes and returns the inner
        "one account" dict, or None if we can't recognize it.
        """
        if not isinstance(raw, dict):
            return None

        bal = raw.get("BalanceResponse") or raw.get("balanceResponse") or raw

        # Common shape: { "BalanceResponse": { "balance": [ { ... } ] } }
        if isinstance(bal, dict) and isinstance(bal.get("balance"), list) and bal["balance"]:
            bal = bal["balance"][0]

        return bal if isinstance(bal, dict) else None

    def _dig_nav(node):
        """Deep search for NAV-like fields anywhere in the balance payload."""
        if node is None:
            return None
        if isinstance(node, dict):
            for k, v in node.items():
                if k in (
                    "netAccountValue",
                    "netAssets",
                    "netValue",
                    "totalAccountValue",
                    "accountValue",
                ) and v not in (None, ""):
                    return v
            for v in node.values():
                found = _dig_nav(v)
                if found is not None:
                    return found
        elif isinstance(node, (list, tuple)):
            for v in node:
                found = _dig_nav(v)
                if found is not None:
                    return found
        return None

    # ---------- locate account identifiers ----------
    try:
        ident = account_identity() or {}
    except Exception:
        ident = {}

    aid_key = (account_id_key
               or ident.get("account_id_key")
               or ident.get("accountIdKey")
               or "").strip() or None

    aid_num = (ident.get("account_id")
               or ident.get("accountId")
               or "").strip() or None

    # we always return these, even if balances fail
    base = {
        "account_id": aid_num,
        "account_key": aid_key,
        "account_type": ident.get("accountType") or ident.get("account_type"),
        "account_type_display": (
            ident.get("accountDescription")
            or ident.get("accountDesc")
            or ident.get("description")
        ),
    }

    # If we somehow have no IDs at all, just bail with zeros.
    if not aid_key and not aid_num:
        out = dict(base)
        out.update({
            "nav": 0.0,
            "available_funds": 0.0,
            "cash_balance": 0.0,
            "settled_cash": 0.0,
            "raw": {},
        })
        return out

    sess = get_oauth_session()

    raw: dict = {}

    # ---------- 1) Try resilient helper if present ----------
    if "fetch_balances_resilient" in globals():
        try:
            candidate = fetch_balances_resilient(
                sess,
                aid_key or aid_num,
                aid_num or aid_key,
            )
            if isinstance(candidate, dict) and candidate:
                raw = candidate
        except Exception:
            raw = {}

    # ---------- 2) Fallback: direct /balance.json calls ----------
    if not raw:
        candidates = [c for c in (aid_key, aid_num) if c]
        for acct in candidates:
            try:
                url = f"{ETRADE_BASE_URL}/v1/accounts/{acct}/balance.json"
                r = sess.get(
                    url,
                    headers={"Accept": "application/json"},
                    timeout=15,
                )
                # treat non-200 as "no data", do NOT raise
                if r.status_code == 200 and (r.text or "").strip():
                    maybe = r.json() or {}
                    if isinstance(maybe, dict) and maybe:
                        raw = maybe
                        break
            except Exception:
                continue

    # ---------- 3) Parse balances ----------
    bal = _extract_balance_view(raw)

    if not bal:
        out = dict(base)
        out.update({
            "nav": 0.0,
            "available_funds": 0.0,
            "cash_balance": 0.0,
            "settled_cash": 0.0,
            "raw": {},
        })
        return out

    comp = (bal.get("Computed")
            or bal.get("computedBalance")
            or {})

    # --- Core fields from E*TRADE ---
    cash_balance = _f(
        comp.get("cashBalance")
        or bal.get("cashBalance"),
        0.0,
    )

    # Settled cash for investment (if E*TRADE reports it – often 0 in practice)
    settled_cash = _f(
        comp.get("settledCashForInvestment")
        or bal.get("settledCashForInvestment"),
        0.0,
    )

    # ---------- NAV (Net Account Value) ----------
    # First try the obvious fields on the primary balance dict
    nav = _f(
        comp.get("netAccountValue")
        or bal.get("netAccountValue")
        or comp.get("totalAccountValue")
        or bal.get("totalAccountValue")
        or comp.get("accountValue")
        or bal.get("accountValue"),
        0.0,
    )

    # If the direct fields aren't populated, try a deep search over the full payload
    if nav == 0.0:
        deep_nav = _dig_nav(raw)
        if deep_nav is not None:
            nav = _f(deep_nav, 0.0)

    # Fallback NAV:
    # If the standard NAV fields are missing/zero, try cashBuyingPower / totalBuyingPower,
    # which for a flat cash account should match "Net Account Value" on E*TRADE.
    if nav == 0.0:
        nav_from_bp = _f(
            comp.get("cashBuyingPower")
            or bal.get("cashBuyingPower")
            or comp.get("totalBuyingPower")
            or bal.get("totalBuyingPower"),
            0.0,
        )
        if nav_from_bp > 0.0:
            nav = nav_from_bp
        else:
            nav = cash_balance

    # --- Buying power / available funds ---
    # For a cash account, the cleanest "what can I actually deploy" is netCash,
    # with fallbacks to cashBuyingPower / cashAvailableForInvestment, etc.
    net_cash = _f(
        comp.get("netCash")
        or bal.get("netCash"),
        0.0,
    )

    cash_bp = _f(
        comp.get("cashBuyingPower")
        or bal.get("cashBuyingPower"),
        0.0,
    )

    alt_bp = _f(
        comp.get("cashAvailableForInvestment")
        or bal.get("cashAvailableForInvestment")
        or comp.get("totalBuyingPower")
        or bal.get("totalBuyingPower"),
        0.0,
    )

    # Prefer netCash if present, otherwise fall back through the others.
    available = net_cash or cash_bp or alt_bp or cash_balance

    out = dict(base)
    out.update({
        "nav": nav,
        "available_funds": available,
        "cash_balance": cash_balance,
        "settled_cash": settled_cash,
        "raw": raw if isinstance(raw, dict) else {},
    })
    return out

import logging
from requests_oauthlib import OAuth1Session
import os
from dotenv import load_dotenv

load_dotenv("etrade.env")

log = logging.getLogger(__name__)

CONSUMER_KEY = os.getenv("ETRADE_API_KEY")
CONSUMER_SECRET = os.getenv("ETRADE_API_SECRET")
OAUTH_TOKEN = os.getenv("OAUTH_TOKEN")
OAUTH_TOKEN_SECRET = os.getenv("OAUTH_TOKEN_SECRET")
ETRADE_BASE_URL = "https://api.etrade.com"


def _oauth_session():
    """
    Single place to create an authenticated E*TRADE session.
    """
    if not all([CONSUMER_KEY, CONSUMER_SECRET, OAUTH_TOKEN, OAUTH_TOKEN_SECRET]):
        raise RuntimeError("Missing E*TRADE OAuth credentials (.env)")

    return OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=OAUTH_TOKEN,
        resource_owner_secret=OAUTH_TOKEN_SECRET,
    )


def get_positions():
    """
    Return raw positions payload from E*TRADE.

    dashboard.py will normalize via _normalize_positions_payload,
    so we just hand back the E*TRADE PortfolioResponse JSON.
    """
    acct_key = get_default_account_id_key()
    sess = get_oauth_session()

    url = f"{ETRADE_BASE_URL}/v1/accounts/{acct_key}/portfolio.json"
    params = {
        "view": "QUICK",
        "sortBy": "MARKET_VALUE",
        "sortOrder": "DESC",
        "count": 500,
    }

    r = sess.get(url, params=params, timeout=15)

    # Guard: E*TRADE sometimes 204 or blank body
    if r.status_code == 204 or not (r.text or "").strip():
        return {}

    r.raise_for_status()
    return r.json()

def preview_equity_order(
    account_id_key: str,
    symbol: str,
    qty: int,
    price: float | None,
    *,
    action: str = "BUY",
    price_type: str = "LIMIT",
    order_term: str = "GOOD_FOR_DAY",
    market_session: str = "REGULAR",
    stop_price: float | None = None,
    offset_type: str | None = None,
    offset_value: float | None = None,
    client_order_id: str | None = None,
) -> dict:
    """
    Builds a PreviewOrderRequest for E*TRADE equities.

    RULES:
      - MARKET:     no limitPrice/stopPrice
      - LIMIT:      limitPrice = price
      - STOP:       stopPrice  = (stop_price or price)  <-- important fix
      - STOP_LIMIT: limitPrice = price, stopPrice = stop_price (both required)
      - TRAILING_*: set offsetType/offsetValue
    """
    action = (action or "BUY").upper()
    pt = (price_type or ("LIMIT" if price is not None else "MARKET")).upper()

    # --- IMPORTANT: map legacy callers that pass STOP trigger as "price"
    if pt in {"STOP", "STOP_MARKET"} and stop_price is None and price is not None:
        stop_price = float(price)
        price = None  # ensure we don't accidentally send limitPrice for STOP

    order: dict = {
        "allOrNone": False,
        "priceType": pt,
        "orderTerm": order_term,
        "marketSession": market_session,
        "Instrument": [
            {
                "Product": {"securityType": "EQ", "symbol": _normalize_symbol(symbol)},
                "orderAction": action,
                "quantityType": "QUANTITY",
                "quantity": str(int(qty)),
            }
        ],
    }

    # Prices
    if pt in {"LIMIT", "STOP_LIMIT"} and price is not None:
        order["limitPrice"] = f"{float(price):.2f}"
    if pt in {"STOP", "STOP_MARKET", "STOP_LIMIT"}:
        if stop_price is None:
            raise ValueError("stop_price required for STOP/STOP_LIMIT orders")
        order["stopPrice"] = f"{float(stop_price):.2f}"

    # Trailing stop fields
    if pt in {"TRAILING_STOP_PRCT", "TRAILING_STOP_CNST"}:
        if offset_value is None:
            raise ValueError("offset_value required for trailing stops")
        order["offsetType"] = offset_type or pt
        order["offsetValue"] = float(offset_value)

    body = {
        "PreviewOrderRequest": {
            "orderType": "EQ",
            "clientOrderId": client_order_id or f"live-{int(time.time()*1000)}",
            "Order": [order],
        }
    }
    return _epost(f"/accounts/{account_id_key}/orders/preview.json", body)


def place_equity_order(preview: dict, qty: float | None = None) -> dict:
    """Place an equity order given a preview response.

    This is the contract used by sell_guard.py:

        prev = preview(acct_key, sym, qty, price_type, limit_or_none)
        et.place_equity_order(prev, qty=qty)

    * `preview` must be the raw dict returned by preview_equity_order()
      (or the /orders/preview.json endpoint).
    * `qty` is currently only used for logging / future safety; the
      actual quantity comes from the preview Instrument block.
    """  # noqa: D401
    pr = (preview or {}).get("PreviewOrderResponse") or {}
    orders = pr.get("Order") or []
    if not orders:
        raise RuntimeError("preview response missing Order[]")

    order = orders[0]
    preview_ids = pr.get("PreviewIds") or []
    if not preview_ids:
        raise RuntimeError("preview response missing PreviewIds[]")
    preview_id = preview_ids[0].get("previewId")
    if not preview_id:
        raise RuntimeError("previewId not found in preview")

    # Pull out Instruments and clean preview-only fields
    instr = order.get("Instrument") or []
    instr = _clean_instruments_for_place(instr)
    if not instr:
        raise RuntimeError("preview missing Instrument for order placement")

    # Best-effort symbol just for logging / clientOrderId
    symbol = ""
    try:
        prod = (instr[0].get("Product") or {})
        symbol = str(prod.get("symbol") or "").upper().strip()
    except Exception:  # noqa: BLE001
        symbol = ""

    # priceType / term / session come from the preview, with safe defaults
    price_type = order.get("priceType") or "MARKET"
    order_term = order.get("orderTerm") or "GOOD_FOR_DAY"
    mkt_session = order.get("marketSession") or "REGULAR"

    # Carry forward limit/stop prices only if they exist in the preview
    clean_order: dict = {
        "Instrument": instr,
        "marketSession": mkt_session,
        "orderTerm": order_term,
        "priceType": price_type,
    }
    if "limitPrice" in order and order.get("limitPrice") is not None:
        clean_order["limitPrice"] = float(order["limitPrice"])
    if "stopPrice" in order and order.get("stopPrice") is not None:
        clean_order["stopPrice"] = float(order["stopPrice"])

    # Discover account key the same way other helpers do
    try:
        acct_key = get_default_account_id_key()
    except Exception:
        # Fallback to env if helper is unavailable
        from_env = (
            os.getenv("ETRADE_ACCOUNT_ID_KEY")
            or os.getenv("ACCOUNT_ID_KEY")
        )
        if not from_env:
            raise RuntimeError(
                "account_id_key not configured for place_equity_order"
            )
        acct_key = from_env

    body = {
        "PlaceOrderRequest": {
            "orderType": pr.get("orderType") or "EQ",
            "clientOrderId": f"{symbol or 'EQ'}-{int(time.time() * 1000)}",
            "PreviewIds": [{"previewId": preview_id}],
            "Order": [clean_order],
        }
    }

    path_key = f"/accounts/{acct_key}/orders/place.json"
    last_err: Exception | None = None

    # 500 / code 100 is a transient venue issue – we simply retry
    for outer in range(1, 1 + 4):
        try:
            resp = _epost(path_key, body)
            if 200 <= resp.status_code < 300:
                return resp.json()

            if resp.status_code == 500:
                try:
                    err_json = resp.json() or {}
                except Exception:  # noqa: BLE001
                    err_json = {}
                err = (err_json or {}).get("Error") or {}
                code = str(err.get("code")) if err else None
                if code == "100":
                    _lg.warning(
                        "place_equity_order transient venue error for %s (outer=%s): %s",
                        symbol or "?",
                        outer,
                        err,
                    )
                    # Retry with the same body; if it keeps failing we'll
                    # eventually bubble the error up to the caller.
                    continue

            # Non-OK / non-transient response
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001
            last_err = e
            _lg.warning(
                "place_equity_order failed for %s (outer=%s): %s",
                symbol or "?",
                outer,
                e,
            )

    if last_err is not None:
        raise last_err
    raise RuntimeError("place_equity_order failed with unknown error")
def list_recent_trades(days: int = 5) -> list[dict[str, Any]]:
    """
    Return recently executed trades (BUY/SELL) using the Orders API,
    and fall back to the Transactions API if needed.
    """
    et, aid = _svc()
    end = datetime.utcnow()
    start = end - timedelta(days=max(1, days))

    # ── Primary: Orders API (most reliable for executed fills)
    params = {
        "fromDate": start.strftime("%Y-%m-%d"),
        "toDate": end.strftime("%Y-%m-%d"),
        "status": "EXECUTED",  # executed orders only
        "count": 100,
        "sortOrder": "DESC",
    }
    out: list[dict[str, Any]] = []

    try:
        resp = et._get(f"/accounts/{aid}/orders.json", params=params)
        orr = resp.get("OrdersResponse", {}) or resp
        orders = orr.get("Order") or []
        if isinstance(orders, dict):
            orders = [orders]

        for o in orders:
            details = o.get("OrderDetail") or o.get("orderDetail") or []
            if isinstance(details, dict):
                details = [details]

            for d in details:
                status = (d.get("status") or "").upper()
                if status not in {
                    "EXECUTED",
                    "FILLED",
                    "PARTIALLY_EXECUTED",
                    "PARTIAL",
                }:
                    continue

                instrs = d.get("Instrument") or d.get("instrument") or []
                if isinstance(instrs, dict):
                    instrs = [instrs]

                # pick a timestamp; executedTime when available
                tstamp = (
                    d.get("executedTime")
                    or d.get("placedTime")
                    or o.get("placedTime")
                    or ""
                )

                for ins in instrs:
                    prod = ins.get("Product") or ins.get("product") or {}
                    sym = (prod.get("symbol") or "").upper()
                    action = (
                        ins.get("orderAction")
                        or d.get("orderAction")
                        or o.get("orderAction")
                        or ""
                    ).upper()

                    qty = (
                        ins.get("filledQuantity")
                        or d.get("filledQuantity")
                        or ins.get("quantity")
                        or d.get("quantity")
                        or 0
                    )
                    try:
                        qty = int(float(qty or 0))
                    except Exception:
                        qty = 0

                    price = (
                        ins.get("averageExecutionPrice")
                        or d.get("averageExecutionPrice")
                        or ins.get("limitPrice")
                        or d.get("limitPrice")
                        or 0.0
                    )
                    try:
                        price = float(price or 0.0)
                    except Exception:
                        price = 0.0

                    if sym and qty:
                        out.append(
                            {
                                "time": str(tstamp),
                                "symbol": sym,
                                "action": action or ("BUY" if qty > 0 else "SELL"),
                                "qty": qty,
                                "price": price,
                                "pl": 0.0,  # P/L is not provided at order level; keep 0 for now
                            }
                        )

        if out:
            out.sort(key=lambda x: str(x.get("time", "")), reverse=True)
            return out

    except Exception as e:
        log.exception("orders fetch failed: %s", e)

    # ── Fallback: Transactions API (more permissive filter)
    try:
        tparams = {
            "startDate": start.strftime("%Y-%m-%d"),
            "endDate": end.strftime("%Y-%m-%d"),
        }
        raw = (
            _eget(f"/accounts/{account_id_key}/orders.json", params={"status": "OPEN"})
            or {}
        )

        tr = data.get("TransactionListResponse", {}) or data
        items = tr.get("Transaction") or tr.get("Transactions") or []
        if isinstance(items, dict):
            items = [items]

        for t in items:
            sym = (
                t.get("symbol") or (t.get("Product") or {}).get("symbol") or ""
            ).upper()
            qty = t.get("quantity") or t.get("qty") or 0
            if not sym or not qty:
                continue  # skip non-trade entries

            act = (
                t.get("transactionType") or t.get("type") or t.get("subType") or ""
            ).upper()
            if not act:
                desc = (t.get("description") or "").upper()
                act = "SELL" if "SELL" in desc else ("BUY" if "BUY" in desc else "")

            price = t.get("price") or t.get("tradePrice") or t.get("amount") or 0.0
            pl = t.get("gain") or t.get("pnl") or 0.0
            ts = t.get("transactionDate") or t.get("date") or t.get("time") or ""

            try:
                qty = int(float(qty))
            except Exception:
                qty = 0
            try:
                price = float(price or 0.0)
            except Exception:
                price = 0.0
            try:
                pl = float(pl or 0.0)
            except Exception:
                pl = 0.0

            if act in {"BUY", "SELL", "BUY_TO_COVER", "SELL_SHORT"}:
                out.append(
                    {
                        "time": str(ts),
                        "symbol": sym,
                        "action": act,
                        "qty": qty,
                        "price": price,
                        "pl": pl,
                    }
                )

        out.sort(key=lambda x: str(x.get("time", "")), reverse=True)
        return out

    except Exception as e:
        log.exception("transactions fallback failed: %s", e)

    return out


# ======= Backwards-compat shim for LiveBroker =======


# Give broker.py a concrete class with the methods it expects.
class ETradeService:
    def __init__(self):
        pass

    # broker.py calls: self._et.first_account_id_key()
    def first_account_id_key(self) -> str:
        # function provided earlier in this module
        return account_id_key()

    # broker.py calls: self._et.get_balances(account_id_key)
    def get_balances(self, account_id_key: str) -> dict:
        # map to your function-style summary/balances fetch
        return get_account_summary(account_id_key)


# Provide a RateLimitError name so broker.py can import/catch it even if
# this module never raises it. (Harmless if unused.)
class RateLimitError(Exception):
    pass


# Ensure public API names exist for importers
try:
    ETradeService
except NameError:
    # If your concrete class is named differently, alias it here:
    # ETradeService = ETradeClient  # or ETradeAPI
    pass

try:
    RateLimitError
except NameError:

    class RateLimitError(Exception):
        """Raised when E*TRADE rate limits are encountered."""

        pass

# =====================================================
# Convenience re-exports for external modules
# =====================================================

# Define get_positions_raw alias for backward compatibility
try:
    get_positions_raw
except NameError:
    # fall back to the standard get_positions if raw version not defined
    get_positions_raw = get_positions

# Expose helpers on the ETradeService class
ETradeService.get_positions = staticmethod(get_positions_raw)
ETradeService.get_account_summary = staticmethod(get_account_summary)

# Module-level aliases (so dashboard.py can do et.get_account_summary)
get_positions = get_positions_raw
get_account_summary = get_account_summary

__all__ = ["ETradeService", "RateLimitError"]
