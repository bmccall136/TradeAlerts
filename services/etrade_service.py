from __future__ import annotations
import os, time, logging
from typing import Iterable

# Reuse the proven live session + base URL from broker_live
from services.broker_live import (
    _sesh,                   # OAuth1 session
    get_account_id_key,      # robust accountIdKey
    BASE as _BASE,           # https://api.etrade.com/v1
    get_quote as _get_quote, # raw quotes
)

log = logging.getLogger("etrade_service")

from typing import Any, Dict, List, Tuple

import os
from services.broker_live import _sesh, get_account_id_key as _get_aid

from datetime import datetime, timedelta, timezone
try:
    import zoneinfo  # Py3.9+
except Exception:
    zoneinfo = None

from datetime import datetime, timedelta, timezone
try:
    import zoneinfo
except Exception:
    zoneinfo = None

# --- time helpers (Eastern) ---
from datetime import datetime, timezone
try:
    import zoneinfo
except Exception:
    zoneinfo = None

from datetime import datetime, timedelta, timezone
try:
    import zoneinfo
except Exception:
    zoneinfo = None

def _now_et():
    if zoneinfo:
        try:
            return datetime.now(zoneinfo.ZoneInfo("America/New_York"))
        except Exception:
            pass
    return datetime.now(timezone.utc)

def _is_same_et_day(ts: datetime) -> bool:
    return ts.astimezone(_now_et().tzinfo).date() == _now_et().date()

def _parse_any_ts(ts) -> datetime:
    if ts is None:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        if isinstance(ts, (int, float)):
            if ts > 10_000_000_000:
                ts = ts / 1000.0
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
        s = str(ts).strip()
        if s.isdigit():
            iv = int(s)
            if iv > 10_000_000_000:
                iv = iv // 1000
            return datetime.fromtimestamp(iv, tz=timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)

def _fmt_mmddyyyy(dt: datetime) -> str:
    return dt.astimezone(_now_et().tzinfo).strftime("%m%d%Y")
# --- Fallback: build trade rows from the Transactions API  -------------------
def transactions_as_trades(days: int = 3):
    j = list_trade_transactions_range(days)  # your existing function that returned a big JSON
    out = []
    txs = (j.get("TransactionListResponse", {}).get("Transaction") or [])
    for t in txs:
        b = (t.get("brokerage") or {})
        prod = (b.get("product") or {})
        sym = (prod.get("symbol") or "").upper()
        if not sym:
            continue
        qty = int(abs(float(b.get("quantity") or 0)))
        px  = float(b.get("price") or 0.0)
        side = "SELL" if str(t.get("transactionType") or "").lower().startswith("sold") else \
               "BUY"  if str(t.get("transactionType") or "").lower().startswith("bought") else ""
        out.append({
            "time": t.get("transactionDate"),  # epoch ms
            "symbol": sym, "action": side, "qty": qty, "price": px
        })
    # newest first helps UI look nicer
    out.sort(key=lambda r: (r["time"] or 0), reverse=True)
    return out

def transactions_as_trades(days: int = 3) -> list[dict]:
    """
    Turn /transactions into simple trade rows (BUY/SELL only).
    Fields returned: time(ms), symbol, action (BUY/SELL), qty, price, amount (cashflow).
    """
    j = list_trade_transactions_range(days)  # you already have this function
    txs = (j.get("TransactionListResponse", {}) or {}).get("Transaction") or []
    if isinstance(txs, dict):
        txs = [txs]

    out = []
    for t in txs:
        typ = (t.get("transactionType") or "").upper()
        br = t.get("brokerage") or {}
        prod = br.get("product") or {}
        sym  = (prod.get("symbol") or "").upper()
        if typ not in ("SOLD", "BOUGHT") or not sym:
            continue
        qty   = abs(int(br.get("quantity") or 0))
        price = float(br.get("price") or 0)
        ts    = int(t.get("transactionDate") or 0)  # ms since epoch
        out.append({
            "time": ts,
            "symbol": sym,
            "action": "SELL" if typ == "SOLD" else "BUY",
            "qty": qty,
            "price": price,
            "amount": float(t.get("amount") or 0.0),  # + sell cash, - buy cash
        })

    out.sort(key=lambda x: x["time"], reverse=True)
    return out

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
# --- recent executed orders -> simple trades list (fallback for UI) ------------
# --- executed orders (count-based) -------------------------------------------
# --- recent executed orders -> simple trades list (fast, near-real-time) -----
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
    comp = (bal or {}).get("computedBalance", {}) or (bal or {}).get("Computed", {}) or {}
    # Buying power
    bp = comp.get("marginBuyingPower") \
         or comp.get("cashBuyingPower") \
         or comp.get("buyingPower") \
         or comp.get("cashAvailableForWithdrawal")
    # Settled cash
    settled = comp.get("settledCash") \
             or comp.get("cashAvailableForWithdrawal") \
             or comp.get("cashBalance")
    try:
        return (float(bp) if bp is not None else None,
                float(settled) if settled is not None else None)
    except Exception:
        return (None, None)

def recent_executions_as_trades(count: int = 50) -> list[dict]:
    """
    Return a list of trade dicts from recent EXECUTED orders:
      {time, symbol, action, qty, price, amount}
    'amount' is signed cashflow (+ for SELL, - for BUY).
    """
    j = list_executed_orders_recent(count)
    orders = (j or {}).get("OrdersResponse", {}).get("Order", []) or []
    if isinstance(orders, dict):
        orders = [orders]

    def _ms_to_iso(ms):
        try:
            from datetime import datetime, timezone
            return datetime.fromtimestamp(int(ms)/1000, tz=timezone.utc).isoformat()
        except Exception:
            return None

    out: list[dict] = []
    for o in orders:
        details = o.get("OrderDetail") or []
        if isinstance(details, dict):
            details = [details]
        for d in details:
            ts = d.get("executedTime") or d.get("placedTime")
            prc = float(d.get("averageExecutionPrice") or d.get("limitPrice") or 0) or 0.0
            instruments = d.get("Instrument") or []
            if isinstance(instruments, dict):
                instruments = [instruments]
            for ins in instruments:
                sym = ((ins.get("Product") or {}).get("symbol") or "").upper()
                act = (ins.get("orderAction") or "").upper()  # SELL / BUY
                qty = int(round(float(ins.get("filledQuantity") or ins.get("orderedQuantity") or 0)))
                if not sym or not qty:
                    continue
                amount = round(prc * qty * (1 if act == "SELL" else -1), 2)
                out.append({
                    "time":   _ms_to_iso(ts),   # ISO string in UTC
                    "symbol": sym,
                    "action": act,
                    "qty":    qty,
                    "price":  prc,
                    "amount": amount,
                })

    out.sort(key=lambda x: x.get("time") or "", reverse=True)
    return out


# --- transactions -> trades (backup feed; also includes BUY+SELL) -------------
def transactions_as_trades(days: int = 3) -> list[dict]:
    j = list_trade_transactions_range(days)  # you already have this helper
    txs = (j.get("TransactionListResponse", {}) or {}).get("Transaction", []) or []
    if isinstance(txs, dict):
        txs = [txs]

    out: list[dict] = []
    for t in txs:
        b  = t.get("brokerage") or {}
        pr = b.get("product") or {}
        sym = (pr.get("symbol") or "").upper()
        qty_raw = int(b.get("quantity") or 0)
        px = float(b.get("price") or 0)
        typ = str(t.get("transactionType") or "").upper()  # "BOUGHT"/"SOLD"
        side = "SELL" if (qty_raw < 0 or typ.startswith("SOLD")) else "BUY"
        qty = abs(qty_raw)
        ts = 0
        try:
            ts = int(t.get("transactionDate") or 0)
        except Exception:
            pass
        amount = round(px * qty * (1 if side == "SELL" else -1), 2)
        if sym and qty > 0:
            out.append({
                "time":   ts,
                "symbol": sym,
                "action": side,
                "qty":    qty,
                "price":  px,
                "amount": amount,
            })

    out.sort(key=lambda t: t["time"])
    return out
def _today_et():
    return _now_et().date()

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
            ts_raw = (od.get("executedTime") or od.get("placedTime") or
                      od.get("updateTime"))
            ts = _parse_any_ts(ts_raw)

            # Only keep today's fills (ET timezone)
            if not _is_same_et_day(ts):
                continue

            insts = od.get("Instrument") or od.get("instrument") or []
            if isinstance(insts, dict):
                insts = [insts]

            for ins in insts:
                side  = (ins.get("orderAction") or "").upper()     # BUY/SELL
                qty   = int(ins.get("filledQuantity")
                           or ins.get("orderedQuantity") or 0)
                price = float(ins.get("averageExecutionPrice")
                              or od.get("limitPrice") or 0.0)
                sym   = ((ins.get("Product") or {}).get("symbol") or "").upper()

                if qty and price:
                    amt = price * qty * (1 if side == "SELL" else -1)
                    trades.append({
                        "time":   ts.isoformat(),
                        "symbol": sym,
                        "action": side,
                        "qty":    qty,
                        "price":  price,
                        "amount": round(amt, 2),
                    })
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
        "toDate":   _mmddyyyy(d),
        "status":   "EXECUTED",
        "count":    50,
        "sortOrder": "DESC",
    }
    r = sess.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json() or {}

def list_trade_transactions_range(days: int = 3) -> dict:
    acct = account_id_key()
    sess = get_oauth_session()
    end  = _now_et()
    start = end - timedelta(days=max(1, int(days)))
    url = f"https://api.etrade.com/v1/accounts/{acct}/transactions.json"
    params = {
        "startDate": _fmt_mmddyyyy(start),
        "endDate":   _fmt_mmddyyyy(end),
        "category":  "TRADE",
        "count":     50,   # E*TRADE enforces 1..50
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
    tlr = (j.get("TransactionListResponse") or j.get("transactionListResponse") or {}) or {}
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

        br  = (t.get("brokerage") or {})
        prod = (br.get("product") or {})
        sym = (t.get("symbol") or prod.get("symbol") or "").upper()

        qty_raw = br.get("quantity")  # sells often negative
        try:
            qty_val = int(float(qty_raw or 0))
        except Exception:
            qty_val = 0
        side = "SELL" if (qty_val < 0 or str(t.get("transactionType","")).upper().startswith("SOLD")) else "BUY"
        qty  = abs(qty_val)

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

        trades.append({
            "time": ts.isoformat(),
            "symbol": sym,
            "action": side,
            "qty": qty,
            "price": price,
            "amount": round(amt, 2),
        })

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
        "toDate":   _mmddyyyy(end),
        "status":   "EXECUTED",
        "count":    50,          # safe cap
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
        "endDate":   _ymd(end),
        "category":  "TRADE",
        "count":     200,
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
        for leg in (o.get("orderLegs") or []):
            sym  = (leg.get("symbol") or "").upper()
            side = (leg.get("side") or o.get("orderAction") or "").upper()
            for ex in (leg.get("executions") or []):
                price = float(ex.get("avgExecPrice") or ex.get("price") or 0)
                qty   = int(ex.get("quantity") or 0)
                trades.append({
                    "time":   ts,
                    "symbol": sym,
                    "action": side,            # BUY / SELL
                    "qty":    qty,
                    "price":  price,
                    "amount": round(price * qty * (1 if side == "SELL" else -1), 2),
                })
    trades.sort(key=lambda x: str(x.get("time") or ""), reverse=True)
    trades = trades[:50]

    # Transactions -> realized P&L sum
    realized = 0.0
    tx = list_trade_transactions(days) or {}
    for t in (tx.get("TransactionListResponse", {}) or {}).get("transactions", []) or []:
        gl = t.get("gainLoss") or t.get("gain")
        try:
            if gl is not None:
                realized += float(gl)
        except Exception:
            pass

    return trades, round(realized, 2)

from datetime import datetime, timedelta
# ---- Canonical helpers (no self-imports, no class dependency) ---------------
import os

_sess_cache = None

def get_oauth_session():
    """Return an OAuth-signed requests.Session (cached)."""
    global _sess_cache
    if _sess_cache is not None:
        return _sess_cache
    try:
        # Use your existing live factory if you have it
        from services.broker_live import get_oauth_session as _factory
        _sess_cache = _factory()
        return _sess_cache
    except Exception as e:
        # No other safe fallback here—fail loudly so you know to wire it up
        raise RuntimeError(
            "get_oauth_session(): no session factory found. "
            "Expose services.broker_live.get_oauth_session() "
            "or restore your previous session builder."
        ) from e


def account_id_key() -> str:
    """
    Return the E*TRADE accountIdKey used in URLs like
    /v1/accounts/{accountIdKey}/....  No self-imports, no class dependency.
    """
    # 1) Environment variable (recommended)
    aid = os.getenv("ETRADE_ACCOUNT_ID_KEY") or ""
    if aid:
        return aid

    # 2) Try a helper you might already have
    try:
        from services.broker_live import get_account_id_key as _get
        aid = _get() or ""
        if aid:
            return aid
    except Exception:
        pass

    # 3) Ask the API for the first account (requires OAuth session)
    try:
        sess = get_oauth_session()
        r = sess.get("https://api.etrade.com/v1/accounts/list.json", timeout=15)
        r.raise_for_status()
        j = r.json() or {}
        accounts = (
            j.get("AccountListResponse", {})
             .get("Accounts", {})
             .get("Account", [])
            or j.get("accounts", [])
        )
        for a in accounts:
            key = a.get("accountIdKey") or a.get("accountIdKeyValue")
            if key:
                return key
    except Exception:
        pass

    raise RuntimeError(
        "ETRADE_ACCOUNT_ID_KEY not found. Set it in the environment "
        "or provide services.broker_live.get_account_id_key()."
    )

# Optional alias if other code uses it
get_account_id_key = account_id_key

# ---- Canonical helpers (no self-imports, no duplicates) --------------------
_sess_cache = None
from datetime import datetime

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
            "endDate":   _mmddyyyy(et_today),
            "transactionCategory": "TRADE",
            "count": 50,
            "sortOrder": "DESC",
        },
        # b) strict today without category (some accounts don’t expose the filter)
        {
            "startDate": _mmddyyyy(et_today),
            "endDate":   _mmddyyyy(et_today),
            "count": 50,
            "sortOrder": "DESC",
        },
        # c) widen window (yesterday→today) w/ category
        {
            "startDate": _mmddyyyy(et_today - timedelta(days=1)),
            "endDate":   _mmddyyyy(et_today),
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
            sym = (_g(leg, "symbol", ("instrument","symbol")) or "").upper()
            side = (_g(leg, "side", "orderAction") or _g(o, "orderAction") or "").upper()
            execs = leg.get("executions") or leg.get("execution") or []
            for ex in execs:
                qty = _g(ex, "quantity", "execQuantity", "filledQuantity") or 0
                try: qty = int(float(qty))
                except: qty = 0
                px  = _g(ex, "avgExecPrice", "price", "execPrice") or 0.0
                try: px = float(px)
                except: px = 0.0
                tstamp = _g(ex, "time", "execTime") or ts
                trades.append({
                    "time":   tstamp,
                    "symbol": sym,
                    "action": side or "TRADE",
                    "qty":    qty,
                    "price":  px,
                    # convenient cash-flow sign for UI P&L column
                    "amount": round((px * qty) * (1 if side == "SELL" else -1), 2),
                })

    trades.sort(key=lambda x: str(x["time"]), reverse=True)
    trades = trades[:count]

    # ---------- Realized via closed gain/loss; fallback to transactions ----------
    realized = 0.0
    try:
        url_gl = f"https://api.etrade.com/v1/accounts/{acct}/gainloss/closedpositions.json"
        rgl = sess.get(url_gl, params={"startDate": _ymd(start), "endDate": _ymd(end)}, timeout=15)
        if rgl.ok:
            gj = rgl.json() or {}
            rows = (
                gj.get("ClosedPositions", {}).get("closedPosition", []) or
                gj.get("closedPosition", []) or []
            )
            for row in rows:
                val = _g(row, "realizedGainLoss", "gainLoss", "gainloss")
                if val is not None:
                    try: realized += float(val)
                    except: pass
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
                tj.get("TransactionListResponse", {}).get("transactions", []) or
                tj.get("transactions", []) or []
            )
            for t in items:
                action = (_g(t, "action", "transactionType", "description") or "").upper()
                try:
                    if "SELL" in action:
                        realized += float(_g(t, "netProceeds", "amount", "netAmount") or 0.0)
                    elif "BUY" in action:
                        realized -= float(_g(t, "amount", "netAmount") or 0.0)
                except: pass

    return trades, round(realized, 2)

def get_quotes_map(symbols: List[str]) -> Dict[str, Dict[str, float]]:
    """Return {SYM: {'last': x, 'prev_close': y}} using E*TRADE quotes."""
    out: Dict[str, Dict[str, float]] = {}
    if not symbols:
        return out

    et, _ = _svc()
    uniq = sorted({s.upper() for s in symbols if s})
    syms_csv = ",".join(uniq)
    try:
        data = et._get(f"/market/quote/{syms_csv}.json", params={"detailFlag": "ALL"})
        qd = (data.get("QuoteResponse") or {}).get("QuoteData") or []
        if isinstance(qd, dict):
            qd = [qd]
        for q in qd:
            prod = q.get("Product") or {}
            sym = (prod.get("symbol") or "").upper()
            allf = q.get("All") or {}
            last = allf.get("lastTrade") or allf.get("lastTradePrice") or allf.get("price") or 0.0
            prev = allf.get("previousClose") or allf.get("prevClose") or allf.get("close") or 0.0
            try:
                out[sym] = {"last": float(last or 0.0), "prev_close": float(prev or 0.0)}
            except Exception:
                pass
    except Exception as e:
        log.exception("quotes fetch failed: %s", e)
    return out

def list_recent_trades(days: int = 5) -> List[Dict[str, Any]]:
    """
    Recently executed trades via Orders API; falls back to Transactions API.
    """
    et, aid = _svc()
    end = datetime.utcnow()
    start = end - timedelta(days=max(1, days))
    out: List[Dict[str, Any]] = []

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
                if status not in {"EXECUTED", "FILLED", "PARTIALLY_EXECUTED", "PARTIAL"}:
                    continue
                when = d.get("executedTime") or d.get("placedTime") or o.get("placedTime") or ""
                instrs = d.get("Instrument") or []
                if isinstance(instrs, dict):
                    instrs = [instrs]
                for ins in instrs:
                    prod = ins.get("Product") or {}
                    sym = (prod.get("symbol") or "").upper()
                    action = (ins.get("orderAction") or d.get("orderAction") or o.get("orderAction") or "").upper()
                    qty = ins.get("filledQuantity") or d.get("filledQuantity") or ins.get("quantity") or 0
                    px = ins.get("averageExecutionPrice") or d.get("averageExecutionPrice") or ins.get("limitPrice") or 0.0
                    try: qty = int(float(qty or 0))
                    except Exception: qty = 0
                    try: px = float(px or 0.0)
                    except Exception: px = 0.0
                    if sym and qty:
                        out.append({"time": str(when), "symbol": sym, "action": action or "BUY", "qty": qty, "price": px, "pl": 0.0})
        if out:
            out.sort(key=lambda x: str(x.get("time","")), reverse=True)
            return out
    except Exception as e:
        log.exception("orders fetch failed: %s", e)

    # Fallback: Transactions
    try:
        tparams = {"startDate": start.strftime("%Y-%m-%d"), "endDate": end.strftime("%Y-%m-%d")}
        data = et._get(f"/accounts/{aid}/transactions.json", params=tparams)
        items = (data.get("TransactionListResponse") or {}).get("Transaction") or []
        if isinstance(items, dict):
            items = [items]
        for t in items:
            sym = (t.get("symbol") or (t.get("Product") or {}).get("symbol") or "").upper()
            qty = t.get("quantity") or t.get("qty") or 0
            if not sym or not qty:
                continue
            act = (t.get("transactionType") or t.get("type") or t.get("subType") or "").upper()
            if not act:
                desc = (t.get("description") or "").upper()
                act = "SELL" if "SELL" in desc else ("BUY" if "BUY" in desc else "")
            px = t.get("price") or t.get("tradePrice") or 0.0
            ts = t.get("transactionDate") or t.get("date") or t.get("time") or ""
            try: qty = int(float(qty))
            except Exception: qty = 0
            try: px = float(px or 0.0)
            except Exception: px = 0.0
            if act in {"BUY","SELL","BUY_TO_COVER","SELL_SHORT"}:
                out.append({"time": str(ts), "symbol": sym, "action": act, "qty": qty, "price": px, "pl": 0.0})
        out.sort(key=lambda x: str(x.get("time","")), reverse=True)
        return out
    except Exception as e:
        log.exception("transactions fallback failed: %s", e)

    return out

# ---------------- HTTP helpers (always go through broker_live session) ----------------

def _eget(path: str, params: dict | None = None):
    s = _sesh()
    r = s.get(f"{_BASE}{path}", params=params or {}, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r

def _epost(path, body):
    url = f"https://api.etrade.com/v1{path}"
    r = _oauth_session.post(url, json=body, headers={"Content-Type": "application/json"})
    if r.status_code >= 400:
        # Surface the server’s error payload for debugging
        err_txt = None
        try:
            err_txt = r.json()
        except Exception:
            err_txt = r.text
        raise RuntimeError(f"etrade POST {path} -> {r.status_code}: {err_txt}")
    return r.json()

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
        prod = (qd.get("Product") or {})
        sym  = (prod.get("symbol") or "").upper()
        px   = _extract_last_price(qd)
        if sym and (px is not None):
            out[sym] = px

    return out.get(sym_list[0]) if single else out

# ---------------- Portfolio / Balances (backwards-compatible API) ----------------

def get_account_summary() -> dict:
    """
    Return E*TRADE balances JSON and also add convenience keys:
      - buying_power
      - settled_cash
    """
    aid = _primary_account_id()
    r = _eget(f"/accounts/{aid}/balance.json", {"instType": "BROKERAGE"})
    j = r.json() or {}

    br = j.get("BalanceResponse", {}) or {}
    comp = br.get("Computed", {}) or {}
    cash = br.get("Cash", {}) or {}

    buying_power = (
        comp.get("cashBuyingPower")
        or comp.get("cashAvailableForInvestment")
        or comp.get("availableFundsForTrading")
        or comp.get("marginBuyingPower")
        or 0.0
    )
    settled_cash = comp.get("netCash") or cash.get("moneyMktBalance") or 0.0

    out = dict(j)
    try:
        out["buying_power"] = float(buying_power or 0.0)
    except Exception:
        out["buying_power"] = 0.0
    try:
        out["settled_cash"] = float(settled_cash or 0.0)
    except Exception:
        out["settled_cash"] = 0.0
    return out

from datetime import datetime, timedelta

API_BASE = "https://api.etrade.com/v1"

def _json_or_empty(resp):
    try:
        txt = (resp.text or "").strip()
        if not txt:
            return {}
        return resp.json()
    except Exception:
        return {}

def get_positions():
    acct = account_id_key()
    sess = get_oauth_session()
    url = f"https://api.etrade.com/v1/accounts/{acct}/portfolio.json"
    params = {"instType": "BROKERAGE"}
    r = sess.get(url, params=params, timeout=15)

    # E*TRADE sometimes returns empty/whitespace or 204; guard JSON parsing
    if r.status_code == 204 or not (r.text or "").strip():
        return []
    r.raise_for_status()
    try:
        j = r.json()
    except ValueError:
        return []  # be tolerant, return empty positions on bad payloads
    return j
def _normalize_symbol(sym: str) -> str:
    return _DOT_TICKER_FIXES.get(sym, sym)

def preview_equity_order(account_id_key: str, symbol: str, qty: int, price: float | None, *, price_type="LIMIT"):
    # E*TRADE likes numbers as strings in requests; stick to that to avoid type fussiness
    qty_s   = str(int(qty))
    lim_s   = f"{price:.2f}" if (price_type == "LIMIT" and price is not None) else "0"

    body = {
        "PreviewOrderRequest": {
            "orderType": "EQ",
            "clientOrderId": f"live-{int(time.time()*1000)}",
            "Order": [{
                "allOrNone": False,
                "priceType": "MARKET" if price_type.upper() == "MARKET" else "LIMIT",
                "orderTerm": "GOOD_FOR_DAY",
                "marketSession": "REGULAR",
                "stopPrice": "" if price_type.upper() != "STOP" else lim_s,
                **({"limitPrice": lim_s} if price_type.upper() == "LIMIT" else {}),
                "Instrument": [{
                    "Product": { "securityType": "EQ", "symbol": _normalize_symbol(symbol) },
                    "orderAction": "BUY",
                    "quantityType": "QUANTITY",
                    "quantity": qty_s
                }]
            }]
        }
    }
    return _epost(f"/accounts/{account_id_key}/orders/preview.json", body)

def place_equity_order(preview_resp: dict, qty: int | None = None) -> dict:
    aid = _primary_account_id()

    pr = preview_resp.get("PreviewOrderResponse") or {}
    orders = pr.get("Order") or []
    if not orders:
        raise RuntimeError(f"preview response missing Order: {preview_resp}")

    order = orders[0]
    instr = order.get("Instrument") or []
    if qty is not None and instr:
        instr[0]["quantity"] = int(qty)

    # robust previewId grab across response shapes
    pid = None
    for k, v in pr.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "previewId" in v[0]:
            pid = v[0]["previewId"]
            break
        if isinstance(v, dict) and "previewId" in v:
            pid = v["previewId"]
            break
    if not pid:
        pid = pr.get("previewId")

    place_body = {
        "PlaceOrderRequest": {
            "Order": [{
                "orderType": order.get("orderType", "EQ"),
                "clientOrderId": order.get("clientOrderId"),
                "priceType": order.get("priceType"),
                **({"limitPrice": order.get("limitPrice")} if order.get("priceType") in {"LIMIT", "STOP_LIMIT"} else {}),
                **({"stopPrice":  order.get("stopPrice")}  if order.get("priceType") in {"STOP", "STOP_LIMIT"} else {}),
                "orderTerm": order.get("orderTerm", "GOOD_FOR_DAY"),
                "marketSession": order.get("marketSession", "REGULAR"),
                "allOrNone": bool(order.get("allOrNone", False)),
                "Instrument": instr,
                **({"PreviewIds": [{"previewId": pid}]} if pid else {}),
            }]
        }
    }

    r = _epost(f"/accounts/{aid}/orders/place.json", place_body)
    return r.json()

def list_recent_trades(days: int = 5) -> List[Dict[str, Any]]:
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
        "status": "EXECUTED",     # executed orders only
        "count": 100,
        "sortOrder": "DESC",
    }
    out: List[Dict[str, Any]] = []

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
                if status not in {"EXECUTED", "FILLED", "PARTIALLY_EXECUTED", "PARTIAL"}:
                    continue

                instrs = d.get("Instrument") or d.get("instrument") or []
                if isinstance(instrs, dict):
                    instrs = [instrs]

                # pick a timestamp; executedTime when available
                tstamp = d.get("executedTime") or d.get("placedTime") or o.get("placedTime") or ""

                for ins in instrs:
                    prod = ins.get("Product") or ins.get("product") or {}
                    sym = (prod.get("symbol") or "").upper()
                    action = (ins.get("orderAction") or d.get("orderAction") or o.get("orderAction") or "").upper()

                    qty = (
                        ins.get("filledQuantity") or d.get("filledQuantity") or
                        ins.get("quantity") or d.get("quantity") or 0
                    )
                    try:
                        qty = int(float(qty or 0))
                    except Exception:
                        qty = 0

                    price = (
                        ins.get("averageExecutionPrice") or d.get("averageExecutionPrice") or
                        ins.get("limitPrice") or d.get("limitPrice") or 0.0
                    )
                    try:
                        price = float(price or 0.0)
                    except Exception:
                        price = 0.0

                    if sym and qty:
                        out.append({
                            "time":  str(tstamp),
                            "symbol": sym,
                            "action": action or ("BUY" if qty > 0 else "SELL"),
                            "qty":    qty,
                            "price":  price,
                            "pl":     0.0,  # P/L is not provided at order level; keep 0 for now
                        })

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
        data = et._get(f"/accounts/{aid}/transactions.json", params=tparams)
        tr = data.get("TransactionListResponse", {}) or data
        items = tr.get("Transaction") or tr.get("Transactions") or []
        if isinstance(items, dict):
            items = [items]

        for t in items:
            sym = (t.get("symbol") or (t.get("Product") or {}).get("symbol") or "").upper()
            qty = t.get("quantity") or t.get("qty") or 0
            if not sym or not qty:
                continue  # skip non-trade entries

            act = (t.get("transactionType") or t.get("type") or t.get("subType") or "").upper()
            if not act:
                desc = (t.get("description") or "").upper()
                act = "SELL" if "SELL" in desc else ("BUY" if "BUY" in desc else "")

            price = t.get("price") or t.get("tradePrice") or t.get("amount") or 0.0
            pl = t.get("gain") or t.get("pnl") or 0.0
            ts = t.get("transactionDate") or t.get("date") or t.get("time") or ""

            try: qty = int(float(qty))
            except Exception: qty = 0
            try: price = float(price or 0.0)
            except Exception: price = 0.0
            try: pl = float(pl or 0.0)
            except Exception: pl = 0.0

            if act in {"BUY", "SELL", "BUY_TO_COVER", "SELL_SHORT"}:
                out.append({
                    "time":   str(ts),
                    "symbol": sym,
                    "action": act,
                    "qty":    qty,
                    "price":  price,
                    "pl":     pl,
                })

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

    # broker.py MAY call preview explicitly (it mostly jumps straight to place)
    def preview_equity_order(
        self,
        account_id_key: str,
        symbol: str,
        qty: int,
        limit_price: float,
        **kwargs
    ) -> dict:
        # Uses your existing function; kwargs (action, etc.) are ignored for now
        return preview_equity_order(account_id_key, symbol, qty, limit_price)

    # broker.py calls: self._et.place_equity_order(action=..., symbol=..., qty=..., limit_price=...)
    # We accept those kwargs, run a preview, then place using the preview response.
    def place_equity_order(self, **kwargs) -> dict:
        # Prefer a supplied preview response if one is given.
        preview_resp = kwargs.get("preview_resp")

        if preview_resp is None:
            aid = kwargs.get("account_id_key") or account_id_key()
            symbol = kwargs["symbol"]
            qty = int(kwargs["qty"])
            limit_price = kwargs.get("limit_price")
            # Run a preview using your function-style API
            preview_resp = preview_equity_order(aid, symbol, qty, limit_price)

        # Your function-style placer expects a preview response (and optional qty override)
        return place_equity_order(preview_resp, qty=kwargs.get("qty"))


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

__all__ = ["ETradeService", "RateLimitError"]
