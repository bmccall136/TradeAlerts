# services/etrade_service.py
from pathlib import Path
import logging
from typing import Optional

import requests
from services.etrade_auth_helper import get_etrade_session, get_api_host

log = logging.getLogger("etrade")
FLAG = Path("need_oauth.flag")

# ---- flag helpers -----------------------------------------------------------
def _mark_need_auth() -> None:
    try:
        FLAG.touch()
        log.warning("E*TRADE auth flag set (401/403)")
    except Exception:
        pass

def _clear_need_auth() -> None:
    try:
        if FLAG.exists():
            FLAG.unlink()
            log.info("E*TRADE auth flag cleared (2xx)")
    except Exception:
        pass

def _handle_etrade_resp(resp: requests.Response) -> requests.Response:
    """Set/clear the flag and raise on error; return resp on success."""
    if resp.ok:           # 200–299
        _clear_need_auth()
        return resp
    if resp.status_code in (401, 403):
        _mark_need_auth()
    resp.raise_for_status()
    return resp  # not reached, but keeps type checkers happy

# ---- public helpers ---------------------------------------------------------
# top of file (you already have log = logging.getLogger("etrade"))
log.setLevel(logging.INFO)  # make sure we emit

def fetch_etrade_quote(symbol: str) -> float:
    sess = get_etrade_session()
    url  = f"{get_api_host()}/v1/market/quote/{symbol}.json"
    log.info("[QUOTE] GET %s %s", url, symbol)           # <— log before call
    resp = sess.get(url, params={"detailFlag": "ALL"}, timeout=10)
    resp = _handle_etrade_resp(resp)
    data = resp.json() or {}
    qd = (data.get("QuoteResponse", {}).get("QuoteData")) or []
    price = 0.0
    if qd:
        q0 = qd[0]
        price = q0.get("All", {}).get("lastTrade") or q0.get("lastTrade") or 0.0
    try:
        price = float(price)
    except (TypeError, ValueError):
        price = 0.0
    log.info("[QUOTE] %s last=%s status=%s", symbol, price, resp.status_code)  # <— log result
    return price

def get_etrade_name(symbol: str) -> str:
    """Best-effort security name; falls back to symbol on error."""
    try:
        sess = get_etrade_session()
        url  = f"{get_api_host()}/v1/market/quote/{symbol}.json"
        resp = sess.get(url, params={"detailFlag": "ALL"}, timeout=10)
        resp = _handle_etrade_resp(resp)
        data = resp.json() or {}
        qd = (data.get("QuoteResponse", {}).get("QuoteData")) or []
        if qd:
            return qd[0].get("description", symbol) or symbol
    except Exception as e:
        log.warning("Name fetch error for %s: %s", symbol, e)
    return symbol

def safe_fetch_price(symbol: str, fallback: Optional[float] = 0.0) -> float:
    """Service-layer safe wrapper (NO Flask redirects here)."""
    try:
        return fetch_etrade_quote(symbol)
    except requests.HTTPError as e:
        # 401/403 already marked by _handle_etrade_resp
        log.warning("[PRICE] %s fetch failed: %s", symbol, getattr(e.response, "status_code", None))
        return float(fallback or 0.0)
    except Exception as e:
        log.warning("[PRICE] %s fetch error: %s", symbol, e)
        return float(fallback or 0.0)

# --- Broker compatibility shims (do NOT change your existing code above) ---

def get_account_summary() -> dict:
    """
    Broker expects this function. Delegate to your existing implementation.
    """
    # Try a few common shapes; keep the first one that exists in YOUR file.
    try:
        # If you already have a module-level function
        return account_summary()  # type: ignore[name-defined]
    except Exception:
        pass
    try:
        # If you use a client class
        client = EtradeClient()  # type: ignore[name-defined]
        return client.get_account_summary()
    except Exception:
        pass
    # If none of the above exist, fail loudly (safer than a silent stub)
    raise RuntimeError(
        "etrade_service.get_account_summary() not wired: "
        "add a delegate here to your real account summary function."
    )

def preview_equity_order(
    side: str, symbol: str, qty: int,
    order_type: str = "MARKET", price: float | None = None
) -> dict:
    """
    Broker expects a preview function. Delegate to what you already have.
    """
    side = str(side).upper()
    # Common per-side helpers
    if side == "BUY":
        try:
            return preview_buy(symbol, int(qty), order_type=order_type, price=price)  # type: ignore[name-defined]
        except Exception:
            pass
    elif side == "SELL":
        try:
            return preview_sell(symbol, int(qty), order_type=order_type, price=price)  # type: ignore[name-defined]
        except Exception:
            pass
    # Single generic preview
    try:
        return preview_order(side=side, symbol=symbol, qty=int(qty),
                             order_type=order_type, price=price)  # type: ignore[name-defined]
    except Exception:
        pass

    raise RuntimeError(
        "etrade_service.preview_equity_order() not wired: "
        "delegate to your preview_buy/preview_sell/preview_order."
    )

def place_equity_order(preview: dict) -> dict:
    """
    Broker expects a place function. Use your existing place_* helpers.
    """
    side   = str(preview.get("side", "")).upper()
    symbol = preview.get("symbol")
    qty    = int(preview.get("qty", 0))
    otype  = preview.get("order_type", "MARKET")
    price  = preview.get("price")

    if side == "BUY":
        try:
            return place_buy(symbol, qty, order_type=otype, price=price)  # type: ignore[name-defined]
        except Exception:
            pass
    elif side == "SELL":
        try:
            return place_sell(symbol, qty, order_type=otype, price=price)  # type: ignore[name-defined]
        except Exception:
            pass
    try:
        return place_order(side=side, symbol=symbol, qty=qty, order_type=otype, price=price)  # type: ignore[name-defined]
    except Exception:
        pass

    raise RuntimeError(
        "etrade_service.place_equity_order() not wired: "
        "delegate to your place_buy/place_sell/place_order."
    )

# === LIVE ACCOUNT SUMMARY (real) ==============================================
import logging, os
from typing import Any, Dict

_log = logging.getLogger("etrade_bal")

def _num(v):
    try:
        return float(v)
    except Exception:
        return None

def _dig(d: dict, *keys):
    # case-insensitive get (supports nested)
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        # try exact, then case-insensitive
        if k in cur:
            cur = cur[k]
            continue
        lk = next((kk for kk in cur.keys() if str(kk).lower() == str(k).lower()), None)
        cur = cur.get(lk) if lk else None
    return cur

def _any(d: dict, candidates):
    for path in candidates:
        # path as tuple of nested keys, e.g. ("BalanceResponse","accountBalance","buyingPower")
        node = d
        for p in path if isinstance(path, (list, tuple)) else (path,):
            if isinstance(node, dict):
                lk = next((kk for kk in node.keys() if str(kk).lower() == str(p).lower()), None)
                node = node.get(lk) if lk else None
            else:
                node = None
            if node is None:
                break
        if node is not None:
            n = _num(node)
            if n is not None:
                return n
    return None

def _normalize_balance_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accepts whatever your client/REST returns and extracts a unified shape.
    We search common E*TRADE shapes, but also fall back to best-effort keys.
    """
    if raw is None:
        return {}

    # common containers from E*TRADE:
    # - {"BalanceResponse": {"accountBalance": {...}}}
    # - {"balance": {...}}
    # - flat dict with keys already present
    root = raw
    br = _dig(root, "BalanceResponse") or _dig(root, "balanceResponse") or root
    acct_bal = _dig(br, "accountBalance") or br

    # Try to pick a type string
    account_type = (
        _dig(root, "accountType")
        or _dig(br, "accountType")
        or _dig(acct_bal, "accountType")
        or os.getenv("ETRADE_ACCOUNT_TYPE")
        or "Cash"
    )

    # Buying power candidates
    buying_power = _any(root, [
        ("BalanceResponse","accountBalance","buyingPower"),
        ("balance","buyingPower"),
        ("accountBalance","buyingPower"),
        "buyingPower",
        ("BalanceResponse","accountBalance","availableFundsForTrading"),
        ("accountBalance","availableFundsForTrading"),
        "availableFundsForTrading",
        ("accountBalance","fundsForOpenOrdersCash"),
        ("accountBalance","marginBuyingPower"),
        "marginBuyingPower",
    ])

    # Settled cash / cash balance candidates
    settled_cash = _any(root, [
        ("BalanceResponse","accountBalance","settledCash"),
        ("accountBalance","settledCash"),
        "settledCash",
        ("accountBalance","cashBalance"),
        "cashBalance",
    ])

    # Nice-to-haves if present
    cash_balance = _any(root, [
        ("accountBalance","cashBalance"), "cashBalance"
    ])
    margin_bp = _any(root, [
        ("accountBalance","marginBuyingPower"), "marginBuyingPower"
    ])
    equity_value = _any(root, [
        ("accountBalance","accountValue"), "accountValue", ("accountBalance","netAccountValue"), "netAccountValue"
    ])
    net_liq = _any(root, [
        ("accountBalance","netMarketValue"), "netMarketValue", ("accountBalance","netLiquidation"), "netLiquidation"
    ])

    out = {
        "account_type": str(account_type),
        "buying_power": float(buying_power or 0.0),
        "settled_cash": float(settled_cash or 0.0),
    }
    if cash_balance is not None: out["cash_balance"] = float(cash_balance)
    if margin_bp   is not None: out["margin_bp"]    = float(margin_bp)
    if equity_value is not None: out["equity_value"] = float(equity_value)
    if net_liq     is not None: out["net_liq"]      = float(net_liq)
    out["raw"] = raw  # keep raw for debugging if you want
    return out

def get_account_summary() -> dict:
    """
    Returns a normalized balance dict with:
      - account_type
      - buying_power
      - settled_cash
    plus any extras we could find. Tries your existing client first.
    """
    # 1) If you already have a client with a balance call, use it
    try:
        client = EtradeClient()  # type: ignore[name-defined]
        # Try the most likely method names in your codebase:
        for meth in ("get_account_summary", "get_account_balance", "account_summary", "balance"):
            if hasattr(client, meth):
                raw = getattr(client, meth)()
                return _normalize_balance_payload(raw)
    except Exception as e:
        _log.debug(f"[LIVE] client balance path failed: {e}")

    # 2) If you have a requests Session with OAuth, call REST endpoints
    try:
        sess = None
        if "get_oauth_session" in globals():
            sess = globals()["get_oauth_session"]()  # type: ignore[operator]
        elif "oauth_session" in globals():
            sess = globals()["oauth_session"]  # type: ignore[index]

        if sess is not None:
            base = os.getenv("ETRADE_API_BASE", "https://api.etrade.com")
            # accounts list -> pick first accountIdKey
            r1 = sess.get(f"{base}/v1/accounts/list.json")
            r1.raise_for_status()
            j1 = r1.json()
            # Try find the first accountIdKey
            accounts = (
                _dig(j1, "AccountListResponse", "Accounts") or
                _dig(j1, "Accounts") or j1
            )
            # Handle both dict and list shapes
            acct_key = None
            if isinstance(accounts, dict):
                for v in accounts.values():
                    if isinstance(v, list) and v:
                        acct_key = _dig(v[0], "accountIdKey") or _dig(v[0], "accountId")
                        break
            if acct_key is None and isinstance(accounts, list) and accounts:
                acct_key = _dig(accounts[0], "accountIdKey") or _dig(accounts[0], "accountId")
            if acct_key is None:
                raise RuntimeError("Could not find accountIdKey in accounts response")

            r2 = sess.get(f"{base}/v1/accounts/{acct_key}/balance.json")
            r2.raise_for_status()
            j2 = r2.json()
            return _normalize_balance_payload(j2)
    except Exception as e:
        _log.debug(f"[LIVE] REST balance path failed: {e}")

    # 3) Nothing worked — hard fail (safer than silent zeros)
    raise RuntimeError(
        "get_account_summary() couldn't call your client or REST. "
        "Wire one of: EtradeClient.get_account_summary()/get_account_balance() "
        "or provide get_oauth_session() that returns an OAuth-signed requests.Session."
    )
