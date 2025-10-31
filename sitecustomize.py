# C:\TradeAlerts\sitecustomize.py
import logging, os, json

LOG = logging.getLogger("sitecustomize")

def _as_float(v):
    try:
        if v is None: return 0.0
        if isinstance(v, (int, float)): return float(v)
        if isinstance(v, str):
            return float(v.replace("$", "").replace(",", "").strip())
    except Exception:
        return 0.0
    return 0.0

def _dig(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    return cur if cur is not None else default

def _import(name):
    try:
        return __import__(name, fromlist=["*"])
    except Exception as e:
        LOG.debug("import %s failed: %s", name, e)
        return None

def _to_dict(bal):
    """Accept dict OR requests.Response OR string JSON and return a dict."""
    if isinstance(bal, dict):
        return bal
    # requests.Response
    try:
        import requests  # noqa
        from requests import Response
        if isinstance(bal, Response):
            try:
                return bal.json()
            except Exception:
                txt = bal.text or ""
                try:
                    return json.loads(txt)
                except Exception:
                    return {}
    except Exception:
        pass
    # raw JSON string?
    if isinstance(bal, str):
        try:
            return json.loads(bal)
        except Exception:
            return {}
    # list/tuple where the last element is a dict (common pattern)
    if isinstance(bal, (list, tuple)) and bal and isinstance(bal[-1], dict):
        return bal[-1]
    return {}

_et = _import("services.etrade_service") or _import("etrade_service")
_bk = _import("services.broker")

def _resolve_account_key(broker_obj=None):
    env = os.environ.get("ACCOUNT_ID_KEY") or os.environ.get("ETRADE_ACCOUNT_ID_KEY")
    if env: return env
    if broker_obj:
        for a in ("account_id_key","accountIdKey","acct_key","account_key"):
            v = getattr(broker_obj, a, None)
            if v: return v
    et = _et
    if not et: return None

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
    et = _et
    if not et or not account_id_key:
        return {}
    for name in ("get_balances","get_balance","balance","fetch_balances"):
        f = getattr(et, name, None)
        if callable(f):
            try:
                raw = f(account_id_key)
                return _to_dict(raw)
            except Exception as e:
                LOG.debug("balances.%s failed: %s", name, e)
    return {}

def _parse_available_to_trade(bal):
    # Preferred fields for CASH account
    for path in [
        ("availableToTrade",),
        ("cashAvailableForInvestment",),
        ("Cash","availableToTrade"),
        ("Cash","cashAvailableForInvestment"),
        ("BalanceResponse","availableToTrade"),
        ("BalanceResponse","cashAvailableForInvestment"),
        ("Computed","availableToTrade"),
    ]:
        v = _dig(bal, *path)
        f = _as_float(v)
        if f > 0:
            return f
    # Fallback to buying power if ATT not present
    return _parse_buying_power(bal)

def _parse_buying_power(bal):
    for path in [
        ("buyingPower",),
        ("BalanceResponse","buyingPower"),
        ("Computed","buyingPower"),
        ("marginBuyingPower",),
        ("BalanceResponse","marginBuyingPower"),
    ]:
        v = _dig(bal, *path)
        f = _as_float(v)
        if f > 0:
            return f
    return 0.0

def _parse_settled_cash(bal):
    for path in [
        ("settledCash",),
        ("Cash","settledCash"),
        ("BalanceResponse","settledCash"),
        ("Computed","settledCash"),
        ("settledCashForInvestment",),
    ]:
        v = _dig(bal, *path)
        f = _as_float(v)
        if f > 0:
            return f
    return 0.0

def _get_triplet(broker_obj=None):
    ak = _resolve_account_key(broker_obj)
    if not ak:
        LOG.warning("[funds] no account_id_key; using zeros")
        return 0.0, 0.0, 0.0
    bal = _fetch_balances(ak) or {}
    att = _parse_available_to_trade(bal)
    bp  = _parse_buying_power(bal)
    sc  = _parse_settled_cash(bal)
    return float(att), float(bp), float(sc)

def _lb_get_buying_power(self):
    att, bp, _ = _get_triplet(self)
    return att if att > 0 else bp

def _lb_get_settled_cash(self):
    _, __, sc = _get_triplet(self)
    return sc

def _patch_livebroker():
    if not _bk:
        return
    LiveBroker = getattr(_bk, "LiveBroker", None)
    if not LiveBroker:
        return
    if not hasattr(LiveBroker, "get_buying_power"):
        setattr(LiveBroker, "get_buying_power", _lb_get_buying_power)
    if not hasattr(LiveBroker, "get_settled_cash"):
        setattr(LiveBroker, "get_settled_cash", _lb_get_settled_cash)
    LOG.info("[sitecustomize] LiveBroker patched (ATT-first for cash accounts).")

try:
    _patch_livebroker()
except Exception as e:
    LOG.error("sitecustomize patch failed: %s", e)
