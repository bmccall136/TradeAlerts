# services/broker_live.py
import os, logging
from requests_oauthlib import OAuth1Session

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
    return OAuth1Session(CK, client_secret=CS,
                         resource_owner_key=AT, resource_owner_secret=AS)

def get_account_id_key(force=False) -> str:
    global _ACCOUNT_ID_KEY
    if _ACCOUNT_ID_KEY and not force:
        return _ACCOUNT_ID_KEY
    s = _sesh()
    r = s.get(f"{BASE}/accounts/list.json")  # 401 => need reauth
    r.raise_for_status()
    data = r.json() or {}
    lst  = (data.get("AccountListResponse", {}) or {}).get("Accounts", []) or []
    # pick first brokerage account
    if not lst:
        raise RuntimeError("No accounts returned from E*TRADE.")
    # typically {'accountIdKey': '...', 'accountType': 'BROKERAGE', ...}
    _ACCOUNT_ID_KEY = lst[0].get("accountIdKey")
    if not _ACCOUNT_ID_KEY:
        raise RuntimeError("accountIdKey missing in accounts/list.")
    log.info("[LIVE] Using accountIdKey=%s", _ACCOUNT_ID_KEY)
    return _ACCOUNT_ID_KEY

def get_quote(symbols: str) -> dict:
    s = _sesh()
    r = s.get(f"{BASE}/market/quote/{symbols}.json",
              params={"detailFlag":"ALL"})
    r.raise_for_status()
    return r.json()

def preview_equity_order(accountIdKey: str, *,
                         action: str, symbol: str, qty: int,
                         priceType: str = "MARKET",
                         limitPrice: float | None = None,
                         stopPrice: float  | None = None,
                         term: str = "GOOD_FOR_DAY") -> dict:
    """
    action: BUY | SELL | SELL_SHORT | BUY_TO_COVER
    priceType: MARKET | LIMIT | STOP | STOP_LIMIT
    """
    body = {
      "PreviewOrderRequest": {
        "orderType": "EQ",
        "ClientOrderId": f"ta-{symbol}-{action.lower()}",
        "Order": [{
          "orderAction": action,
          "priceType": priceType,
          "quantity": qty,
          "marketSession": "REGULAR",
          "allOrNone": False,
          "reserveOrder": False,
          "Instrument": [{
            "Product": {"securityType": "EQ", "symbol": symbol}
          }],
          **({"limitPrice": float(limitPrice)} if limitPrice else {}),
          **({"stopPrice":  float(stopPrice)}  if stopPrice  else {}),
        }],
        "term": term
      }
    }
    s = _sesh()
    r = s.post(f"{BASE}/accounts/{accountIdKey}/orders/preview.json", json=body)
    r.raise_for_status()
    return r.json()

def place_from_preview(accountIdKey: str, preview_json: dict) -> dict:
    """
    Echo back what preview returned (including previewId).
    """
    pr = preview_json.get("PreviewOrderResponse") or {}
    pv = (pr.get("PreviewIds") or [{}])[0].get("previewId")
    ords = pr.get("Order") or []
    if not pv or not ords:
        raise RuntimeError("Preview response missing previewId/Order")

    body = {
      "PlaceOrderRequest": {
        "orderType": "EQ",
        "PreviewIds": [{"previewId": pv}],
        "Order": ords  # use server-validated order block
      }
    }
    s = _sesh()
    r = s.post(f"{BASE}/accounts/{accountIdKey}/orders/place.json", json=body)
    r.raise_for_status()
    return r.json()

# Convenience one-liners
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
