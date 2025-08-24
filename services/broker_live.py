# services/broker_live.py
import os, logging
from requests_oauthlib import OAuth1Session

# ✅ Load .env so CK/CS/AT/AS are available when running outside your launcher
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(), override=True)
except Exception:
    pass

log = logging.getLogger("broker_live")

BASE = os.getenv("ETRADE_BASE", "https://api.etrade.com/v1")
CK   = os.getenv("ETRADE_CONSUMER_KEY") or os.getenv("ETRADE_API_KEY")
CS   = os.getenv("ETRADE_CONSUMER_SECRET") or os.getenv("ETRADE_API_SECRET")
AT   = os.getenv("OAUTH_TOKEN")
AS   = os.getenv("OAUTH_TOKEN_SECRET")

_ACCOUNT_ID_KEY = None

def _sesh() -> OAuth1Session:
    if not all([CK, CS, AT, AS]):
        raise RuntimeError("Missing E*TRADE OAuth env (CK/CS/AT/AS). Reconnect API.")
    return OAuth1Session(
        CK,
        client_secret=CS,
        resource_owner_key=AT,
        resource_owner_secret=AS
    )

def _normalize_accounts_list(j: dict) -> list[dict]:
    """
    E*TRADE shape:
      AccountListResponse -> Accounts -> Account (list or dict)
    Normalize that to a list of account dicts.
    """
    alr = (j or {}).get("AccountListResponse", {}) or {}
    acc = alr.get("Accounts") or {}
    if isinstance(acc, dict) and "Account" in acc:
        acc = acc["Account"]
    if isinstance(acc, dict):
        acc = [acc]
    if not isinstance(acc, list):
        acc = []
    return acc

def get_account_id_key(force: bool = False) -> str:
    """
    Returns the accountIdKey. Honors env override:
      ETRADE_ACCOUNT_ID_KEY or ACCOUNT_ID_KEY
    """
    global _ACCOUNT_ID_KEY
    if _ACCOUNT_ID_KEY and not force:
        return _ACCOUNT_ID_KEY

    # ✅ Allow explicit override (handy in dev / CI)
    env_key = os.getenv("ETRADE_ACCOUNT_ID_KEY") or os.getenv("ACCOUNT_ID_KEY")
    if env_key:
        _ACCOUNT_ID_KEY = env_key
        log.info("[LIVE] Using accountIdKey from env: %s", _ACCOUNT_ID_KEY)
        return _ACCOUNT_ID_KEY

    s = _sesh()
    r = s.get(f"{BASE}/accounts/list.json", headers={"Accept": "application/json"})
    r.raise_for_status()
    data = r.json() or {}

    accounts = _normalize_accounts_list(data)
    if not accounts:
        raise RuntimeError(f"No accounts returned from E*TRADE. Raw={data!r}")

    # Prefer a brokerage account if present
    pick = next(
        (a for a in accounts if str(a.get("accountType", "")).upper().startswith("BROKER")),
        accounts[0]
    )
    key = pick.get("accountIdKey") or pick.get("accountId")
    if not key:
        raise RuntimeError(f"accountIdKey missing in accounts/list. Picked={pick!r}")

    _ACCOUNT_ID_KEY = key
    log.info("[LIVE] Using accountIdKey=%s", _ACCOUNT_ID_KEY)
    return _ACCOUNT_ID_KEY

def get_quote(symbols: str) -> dict:
    s = _sesh()
    r = s.get(f"{BASE}/market/quote/{symbols}.json", params={"detailFlag": "ALL"})
    r.raise_for_status()
    return r.json()

# --- preview/place (unchanged) ---
def preview_equity_order(accountIdKey: str, *, 
                         action: str | None = None,
                         side: str | None = None,             # alias
                         symbol: str,
                         qty: int | None = None,
                         quantity: int | None = None,         # alias
                         priceType: str | None = None,
                         price: float | None = None,          # alias for limit
                         limitPrice: float | None = None,
                         stopPrice: float | None = None,
                         term: str = "GOOD_FOR_DAY") -> dict:
    # normalize
    action = (action or side)
    if not action:
        raise ValueError("action/side is required")
    qty = qty if qty is not None else quantity
    if qty is None:
        raise ValueError("qty/quantity is required")

    if priceType is None:
        priceType = "LIMIT" if (price is not None or limitPrice is not None) else "MARKET"
    if limitPrice is None and price is not None:
        limitPrice = price

    if priceType in ("LIMIT", "STOP_LIMIT") and limitPrice is None:
        raise ValueError("limitPrice (or price) required for LIMIT/STOP_LIMIT")
    if priceType in ("STOP", "STOP_LIMIT") and stopPrice is None:
        raise ValueError("stopPrice required for STOP/STOP_LIMIT")

    body = {
      "PreviewOrderRequest": {
        "orderType": "EQ",
        "clientOrderId": f"ta-{symbol}-{action.lower()}",
        "Order": [{
          "allOrNone": False,
          "priceType": str(priceType).upper(),
          "orderTerm": str(term).upper(),
          "marketSession": "REGULAR",
          **({"limitPrice": float(limitPrice)} if limitPrice is not None else {}),
          **({"stopPrice":  float(stopPrice)}  if stopPrice  is not None else {}),
          "Instrument": [{
            "orderAction": str(action).upper(),
            "quantityType": "QUANTITY",
            "quantity": int(qty),
            "Product": {"securityType": "EQ", "symbol": str(symbol).upper()}
          }]
        }]
      }
    }
    s = _sesh()
    r = s.post(f"{BASE}/accounts/{accountIdKey}/orders/preview.json", json=body)
    if r.status_code != 200:
        raise RuntimeError(f"preview_equity_order {r.status_code}: {r.text}")
    return r.json()

def place_from_preview(accountIdKey: str, preview_json: dict) -> dict:
    # tolerate key casing and dict/list shapes
    pr = (preview_json.get("PreviewOrderResponse")
          or preview_json.get("previewOrderResponse")
          or {})
    preview_ids = (pr.get("PreviewIds")
                   or pr.get("previewIds")
                   or [])
    if isinstance(preview_ids, dict):
        preview_ids = [preview_ids]

    pv = (preview_ids or [{}])[0].get("previewId")
    ords = (pr.get("Order") or pr.get("order") or [])

    if not pv or not ords:
        raise RuntimeError(f"Preview response missing previewId/Order: {preview_json}")

    body = {
      "PlaceOrderRequest": {
        "orderType": "EQ",
        "clientOrderId": (
            pr.get("clientOrderId")
            or pr.get("ClientOrderId")
            or f"ta-{pv}"
        ),
        "PreviewIds": [{"previewId": str(pv)}],
        "Order": ords,  # carry through exactly what was previewed
      }
    }

    s = _sesh()
    r = s.post(f"{BASE}/accounts/{accountIdKey}/orders/place.json", json=body)

    # E*TRADE often returns 201 Created on success
    if r.status_code not in (200, 201):
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise RuntimeError(f"place_from_preview {r.status_code}: {detail}")

    return r.json()
def market_buy(symbol: str, qty: int) -> dict:
    acct = get_account_id_key()
    p = preview_equity_order(acct, action="BUY", symbol=symbol, qty=qty, priceType="MARKET")
    return place_from_preview(acct, p)

def market_sell(symbol: str, qty: int) -> dict:
    acct = get_account_id_key()
    p = preview_equity_order(acct, action="SELL", symbol=symbol, qty=qty, priceType="MARKET")
    return place_from_preview(acct, p)

def place_stop(symbol: str, qty: int, stop_price: float) -> dict:
    acct = get_account_id_key()
    p = preview_equity_order(acct, action="SELL", symbol=symbol, qty=qty,
                             priceType="STOP", stopPrice=stop_price)
    return place_from_preview(acct, p)

def place_limit(symbol: str, qty: int, limit_price: float) -> dict:
    acct = get_account_id_key()
    p = preview_equity_order(acct, action="SELL", symbol=symbol, qty=qty,
                             priceType="LIMIT", limitPrice=limit_price)
    return place_from_preview(acct, p)

def place_stop_limit(symbol: str, qty: int, stop_price: float, limit_price: float) -> dict:
    acct = get_account_id_key()
    p = preview_equity_order(acct, action="SELL", symbol=symbol, qty=qty,
                             priceType="STOP_LIMIT", stopPrice=stop_price, limitPrice=limit_price)
    return place_from_preview(acct, p)
