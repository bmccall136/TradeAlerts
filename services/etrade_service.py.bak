# services/etrade_service.py
from pathlib import Path
import logging
from typing import Optional

import requests
from services.etrade_auth_helper import get_etrade_session, get_api_host

log = logging.getLogger("etrade")
FLAG = Path("need_oauth.flag")

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

# ==== LIVE account + positions (uses your auth helper) =======================
from typing import Any, Dict, List

def _dig(d: Any, *path):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return None
        kk = next((k for k in cur.keys() if str(k).lower() == str(p).lower()), None)
        cur = cur.get(kk) if kk else None
    return cur

def _num(x):
    try:
        return float(x)
    except Exception:
        return None

def _first_account_key(j: Dict[str, Any]) -> str:
    """
    Return the FIRST alphanumeric accountIdKey found in the accounts list response.
    DO NOT fall back to numeric accountId here (that causes 400s).
    """
    found = None

    def walk(x):
        nonlocal found
        if found is not None:
            return
        if isinstance(x, dict):
            # prefer accountIdKey ONLY
            for k, v in x.items():
                if str(k).lower() == "accountidkey":
                    found = str(v)
                    return
            # keep walking
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(j)
    if not found:
        raise RuntimeError("No accountIdKey found in accounts list response")
    return found
def _normalize_balance_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize E*TRADE balance JSON to {account_type, buying_power, settled_cash, ...}"""
    def dig(d, *path):
        cur = d
        for p in path:
            if not isinstance(cur, dict):
                return None
            kk = next((k for k in cur if str(k).lower() == str(p).lower()), None)
            cur = cur.get(kk) if kk else None
        return cur

    def num(x):
        try: return float(x)
        except Exception: return None

    root = raw or {}
    br   = dig(root, "BalanceResponse") or dig(root, "balanceResponse") or root
    bal  = dig(br, "accountBalance") or br
    comp = dig(br, "Computed") or dig(root, "Computed") or {}
    cash = dig(br, "Cash") or dig(root, "Cash") or {}
    rtv  = dig(comp, "RealTimeValues") or dig(root, "RealTimeValues") or {}

    out = {
        "account_type": (dig(root,"accountType") or dig(br,"accountType") or dig(bal,"accountType") or "Cash"),
        "buying_power": 0.0,
        "settled_cash": 0.0,
        "raw": raw,
    }

    # Buying power: prefer Computed fields, then fallbacks
    bp = (
        num(dig(comp, "cashAvailableForWithdrawal")) or
        num(dig(comp, "cashAvailableForInvestment")) or
        num(dig(comp, "cashBuyingPower")) or
        num(dig(comp, "marginBuyingPower")) or
        num(dig(bal,  "buyingPower")) or
        num(dig(bal,  "availableFundsForTrading")) or
        num(dig(root, "buyingPower"))
    )
    if bp is not None: out["buying_power"] = bp

    # Settled cash: money market balance and related computed fields
    sc = (
        num(dig(cash, "moneyMktBalance")) or
        num(dig(comp, "totalAvailableForWithdrawal")) or
        num(dig(comp, "cashBalance")) or
        num(dig(comp, "settledCashForInvestment")) or
        num(dig(bal,  "settledCash")) or
        num(dig(bal,  "cashBalance")) or
        num(dig(root, "settledCash")) or
        num(dig(root, "cashBalance"))
    )
    if sc is not None: out["settled_cash"] = sc

    # Extras (nice to show on the page)
    eq = (num(dig(rtv, "totalAccountValue")) or
          num(dig(bal, "accountValue")) or
          num(dig(bal, "netAccountValue")))
    if eq is not None: out["equity_value"] = eq

    nl = (num(dig(rtv, "netMv")) or
          num(dig(bal, "netLiquidation")) or
          num(dig(bal, "netMarketValue")))
    if nl is not None: out["net_liq"] = nl

    # Maskable ID if you want to show it
    acct_id = dig(br, "accountId") or dig(root, "accountId")
    if acct_id: out["account_id"] = str(acct_id)

    return out

def get_account_summary() -> dict:
    """
    Live balances from E*TRADE.
    - GET /v1/accounts/list.json -> accountIdKey
    - GET /v1/accounts/{key}/balance.json (try param variants)
    - Extract from BalanceResponse.Computed / Cash (what your payload uses)
    """
    import requests

    sess = get_etrade_session()
    base = get_api_host().rstrip("/")

    # 1) Required accountIdKey (alphanumeric)
    r1 = sess.get(f"{base}/v1/accounts/list.json", timeout=10)
    r1 = _handle_etrade_resp(r1)
    acct_key = _first_account_key(r1.json())
    log.info("[ET] Using accountIdKey: %s", acct_key)

    # 2) Hit balance endpoint (variants to avoid 400s)
    urls = [
        f"{base}/v1/accounts/{acct_key}/balance.json?instType=BROKERAGE&realTimeNAV=true",
        f"{base}/v1/accounts/{acct_key}/balance.json?instType=BROKERAGE",
        f"{base}/v1/accounts/{acct_key}/balance.json?realTimeNAV=true",
        f"{base}/v1/accounts/{acct_key}/balance.json",
        f"{base}/v1/accounts/{acct_key}/balances.json?instType=BROKERAGE&realTimeNAV=true",
    ]

    last_err = None
    j2 = None
    for url in urls:
        try:
            r2 = sess.get(url, timeout=12)
            if r2.status_code in (401, 403):
                _handle_etrade_resp(r2)  # marks need_oauth.flag and raises
            if r2.status_code == 400:
                log.warning("[ET] 400 from %s :: %s", url, (r2.text or "")[:200])
                continue
            r2.raise_for_status()
            j2 = r2.json()
            log.info("[ET] balance OK via %s", url)
            break
        except requests.HTTPError as e:
            last_err = e
        except Exception as e:
            last_err = e
    if j2 is None:
        if last_err:
            raise last_err
        raise RuntimeError("E*TRADE balance request failed for all variants.")

    # 3) DIRECT extraction from your payload shape
    br   = _dig(j2, "BalanceResponse") or j2
    comp = _dig(br, "Computed") or {}
    cash = _dig(br, "Cash") or {}
    rtv  = _dig(comp, "RealTimeValues") or {}

    def pick(*vals):
        for v in vals:
            n = _num(v)
            if n is not None:
                return n
        return None

    acct_type = (_dig(br, "accountType") or "Cash")

    buying_power = pick(
        _dig(comp, "cashAvailableForWithdrawal"),
        _dig(comp, "cashAvailableForInvestment"),
        _dig(comp, "cashBuyingPower"),
        _dig(comp, "marginBuyingPower"),
        _dig(br,  "buyingPower"),
    )

    settled_cash = pick(
        _dig(cash, "moneyMktBalance"),
        _dig(comp, "totalAvailableForWithdrawal"),
        _dig(comp, "cashBalance"),
        _dig(br,  "settledCash"),
        _dig(br,  "cashBalance"),
    )

    equity_value = pick(
        _dig(rtv, "totalAccountValue"),
        _dig(br,  "accountValue"),
        _dig(br,  "netAccountValue"),
    )

    net_liq = pick(
        _dig(rtv, "netMv"),
        _dig(br,  "netLiquidation"),
        _dig(br,  "netMarketValue"),
    )

    out = {
        "account_type": str(acct_type),
        "buying_power": float(buying_power or 0.0),
        "settled_cash": float(settled_cash or 0.0),
        "raw": j2,
    }
    if equity_value is not None: out["equity_value"] = float(equity_value)
    if net_liq      is not None: out["net_liq"]      = float(net_liq)

    log.info("[ET] normalized: BP=%.2f SC=%.2f EQ=%s NL=%s",
             out["buying_power"], out["settled_cash"],
             out.get("equity_value"), out.get("net_liq"))
    return out
def get_positions() -> List[dict]:
    sess = get_etrade_session()
    base = get_api_host().rstrip("/")

    r1 = sess.get(f"{base}/v1/accounts/list.json", timeout=10)
    r1 = _handle_etrade_resp(r1)
    acct_key = _first_account_key(r1.json())

    r2 = sess.get(f"{base}/v1/accounts/{acct_key}/portfolio.json", params={"count": 200}, timeout=15)
    r2 = _handle_etrade_resp(r2)
    j = r2.json()

    pr = _dig(j, "PortfolioResponse") or j
    acct = _dig(pr, "AccountPortfolio")
    if isinstance(acct, list):
        acct = acct[0]
    positions = []
    pos_list = (acct or {}).get("Position") or (acct or {}).get("position") if isinstance(acct, dict) else None
    if not isinstance(pos_list, list):
        return positions

    for p in pos_list:
        sym = (p.get("symbol")
               or _dig(p, "Product", "symbol")
               or p.get("symbolDescription")
               or "")
        qty = _num(p.get("qty")) or _num(p.get("quantity")) or 0.0
        last = (_num(p.get("lastTrade"))
                or _num(p.get("lastPrice"))
                or (_num(p.get("marketValue"))/qty if qty and _num(p.get("marketValue")) else None)
                or 0.0)
        # pricePaid is usually total cost basis -> convert to per-share
        price_paid_total = (_num(p.get("pricePaid")) or _num(p.get("cost")) or 0.0)
        per_share = (price_paid_total/qty) if qty else 0.0
        if per_share == 0.0 and _num(p.get("pricePaid")):  # already per-share
            per_share = float(p["pricePaid"])

        positions.append({
            "symbol": str(sym).upper(),
            "qty": int(qty or 0),
            "price_paid": float(per_share or 0.0),
            "last_price": float(last or 0.0),
        })
    return positions
