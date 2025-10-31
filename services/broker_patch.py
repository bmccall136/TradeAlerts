# C:\TradeAlerts\services\broker_patch.py
import json, os, logging
LOG = logging.getLogger("broker_patch")

def _as_float(v):
    try:
        if v is None: return 0.0
        if isinstance(v, (int, float)): return float(v)
        if isinstance(v, str):
            return float(v.replace("$","").replace(",","").strip())
    except Exception:
        return 0.0
    return 0.0

def _dig(d, *path, default=None):
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default

def _to_dict(bal):
    if isinstance(bal, dict): return bal
    try:
        from requests import Response
        if isinstance(bal, Response):
            try: return bal.json()
            except Exception:
                try: return json.loads(bal.text or "")
                except Exception: return {}
    except Exception:
        pass
    if isinstance(bal, str):
        try: return json.loads(bal)
        except Exception: return {}
    if isinstance(bal, (list, tuple)) and bal and isinstance(bal[-1], dict):
        return bal[-1]
    return {}

def _resolve_account_key(broker_obj=None):
    # env override first
    env = os.environ.get("ACCOUNT_ID_KEY") or os.environ.get("ETRADE_ACCOUNT_ID_KEY")
    if env: return env

    # try attributes on the broker instance
    if broker_obj:
        for a in ("account_id_key","accountIdKey","acct_key","account_key"):
            v = getattr(broker_obj, a, None)
            if v: return v

    # ask etrade_service in several ways
    try:
        from services import etrade_service as et
    except Exception:
        try:
            import etrade_service as et  # fallback if not packaged
        except Exception:
            return None

    for fn in ("get_primary_account","get_default_account","primary_account"):
        f = getattr(et, fn, None)
        if callable(f):
            try:
                d = f()
                if isinstance(d, dict):
                    for k in ("accountIdKey","account_id_key","key"):
                        if d.get(k): return d[k]
            except Exception:
                pass

    for fn in ("list_accounts","get_accounts","accounts"):
        f = getattr(et, fn, None)
        if callable(f):
            try:
                arr = f()
                if isinstance(arr, dict):
                    arr = arr.get("Accounts") or arr.get("accounts") or arr.get("data") or []
                if isinstance(arr, list):
                    for row in arr:
                        if isinstance(row, dict):
                            k = row.get("accountIdKey") or row.get("account_id_key")
                            if k: return k
            except Exception:
                pass
    return None

def _fetch_balances(account_id_key):
    if not account_id_key: return {}
    # call the user’s etrade_service get_balances(account_id_key)
    try:
        from services import etrade_service as et
    except Exception:
        try:
            import etrade_service as et
        except Exception:
            return {}
    for name in ("get_balances","get_balance","balance","fetch_balances"):
        f = getattr(et, name, None)
        if callable(f):
            try:
                raw = f(account_id_key)
                return _to_dict(raw) or {}
            except Exception as e:
                LOG.debug("[broker_patch] balances.%s failed: %s", name, e)
    return {}

def _parse_available_to_trade(bal):
    # Prefer AvailableToTrade; fall back to buying power if not present
    for path in [
        ("availableToTrade",),
        ("Cash", "availableToTrade"),
        ("BalanceResponse", "availableToTrade"),
        ("Computed", "availableToTrade"),
        ("cashAvailableForInvestment",),
        ("Cash", "cashAvailableForInvestment"),
        ("BalanceResponse", "cashAvailableForInvestment"),
    ]:
        v = _as_float(_dig(bal, *path))
        if v > 0: return v
    return _parse_buying_power(bal)

def _parse_buying_power(bal):
    for path in [
        ("buyingPower",),
        ("BalanceResponse", "buyingPower"),
        ("Computed", "buyingPower"),
        ("marginBuyingPower",),
        ("BalanceResponse", "marginBuyingPower"),
    ]:
        v = _as_float(_dig(bal, *path))
        if v > 0: return v
    return 0.0

def _parse_settled_cash(bal):
    for path in [
        ("settledCash",),
        ("Cash", "settledCash"),
        ("BalanceResponse", "settledCash"),
        ("Computed", "settledCash"),
        ("settledCashForInvestment",),
    ]:
        v = _as_float(_dig(bal, *path))
        if v > 0: return v
    return 0.0

# --- Patch LiveBroker at import time ---
try:
    from services.broker import LiveBroker
except Exception:
    # try flat import if user's code isn’t packaged
    from broker import LiveBroker  # type: ignore

def _get_triplet(self=None):
    ak = _resolve_account_key(self)
    if not ak:
        LOG.warning("[broker_patch] no account_id_key; returning zeros")
        return 0.0, 0.0, 0.0
    bal = _fetch_balances(ak) or {}
    att = _parse_available_to_trade(bal)
    bp  = _parse_buying_power(bal)
    sc  = _parse_settled_cash(bal)
    return float(att), float(bp), float(sc)

def _lb_get_buying_power(self):
    # Use AvailableToTrade first for cash accounts; fallback to buyingPower
    att, bp, _ = _get_triplet(self)
    return att if att > 0 else bp

def _lb_get_settled_cash(self):
    _, __, sc = _get_triplet(self)
    return sc

# only add if missing (don’t override user’s own methods)
if not hasattr(LiveBroker, "get_buying_power"):
    setattr(LiveBroker, "get_buying_power", _lb_get_buying_power)
if not hasattr(LiveBroker, "get_settled_cash"):
    setattr(LiveBroker, "get_settled_cash", _lb_get_settled_cash)

LOG.info("[broker_patch] LiveBroker patched (ATT-first; cash-account friendly)")
