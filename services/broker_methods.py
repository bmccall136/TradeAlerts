# services/broker_methods.py
# Adds balance accessors to LiveBroker so the live loop can size by "Available to Trade".
import os
import logging

LOG = logging.getLogger("broker_methods")

# --- Try to import your existing broker + E*TRADE adapter ---
try:
    from services.broker import LiveBroker
except Exception as e:
    LiveBroker = None
    LOG.error("Could not import LiveBroker from services.broker: %s", e)

# Your E*TRADE service module name has varied over time; try common names.
_et = None
for modname in ("services.etrade_service", "etrade_service"):
    try:
        _tmp = __import__(modname, fromlist=["*"])
        _et = _tmp
        break
    except Exception:  # pragma: no cover
        continue

def _resolve_account_key(broker_obj=None) -> str | None:
    """
    Resolve an accountIdKey robustly:
    - ENV override: ACCOUNT_ID_KEY or ETRADE_ACCOUNT_ID_KEY
    - broker field: broker_obj.account_id_key / broker_obj.accountIdKey
    - etrade_service fallbacks: get_primary_account(), list_accounts(), get_accounts()
    """
    env = os.environ.get("ACCOUNT_ID_KEY") or os.environ.get("ETRADE_ACCOUNT_ID_KEY")
    if env:
        return env

    if broker_obj:
        for a in ("account_id_key", "accountIdKey", "acct_key", "account_key"):
            if hasattr(broker_obj, a) and getattr(broker_obj, a):
                return getattr(broker_obj, a)

    if _et:
        # Try a handful of common helpers, ignore shape errors
        for fn in ("get_primary_account", "get_default_account", "primary_account"):
            try:
                f = getattr(_et, fn)
                d = f()
                if isinstance(d, dict):
                    for k in ("accountIdKey", "account_id_key", "key"):
                        if k in d and d[k]:
                            return d[k]
            except Exception:
                pass

        for fn in ("list_accounts", "get_accounts", "accounts"):
            try:
                f = getattr(_et, fn)
                arr = f()
                # accept list or dict{'Accounts': [...]}
                if isinstance(arr, dict):
                    for k in ("Accounts", "accounts", "data"):
                        if k in arr and isinstance(arr[k], list):
                            arr = arr[k]
                            break
                if isinstance(arr, list):
                    for row in arr:
                        if not isinstance(row, dict):
                            continue
                        for k in ("accountIdKey", "account_id_key", "key"):
                            if k in row and row[k]:
                                return row[k]
            except Exception:
                pass

    return None


def _fetch_balances(account_id_key: str | None):
    """
    Call your E*TRADE balance endpoint via whatever helper exists.
    Returns a dict (best-effort normalized). On failure, {}.
    """
    if not _et or not account_id_key:
        return {}

    # Try common balance functions
    fn_names = ("get_balances", "get_balance", "balance", "fetch_balances")
    for fn in fn_names:
        try:
            f = getattr(_et, fn)
        except Exception:
            continue
        try:
            b = f(account_id_key)
            if isinstance(b, dict):
                return b
            # sometimes wrappers return ('ok', dict) style:
            if isinstance(b, (list, tuple)) and b and isinstance(b[-1], dict):
                return b[-1]
        except Exception as e:
            LOG.warning("balances call %s failed: %s", fn, e)
    return {}


def _as_float(v):
    try:
        if v is None:
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            # strip $ and commas if present
            v2 = v.replace("$", "").replace(",", "").strip()
            return float(v2)
    except Exception:
        return 0.0
    return 0.0


def _dig(d: dict, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    return cur if cur is not None else default


def _parse_available_to_trade(bal: dict) -> float:
    """
    Best-effort extraction of 'Available to Trade' (cash account) or
    sensible live-usable funds (prefers cash-based over margin).
    """
    # Common E*TRADE shapes we’ve seen
    candidates = [
        ("availableToTrade",),
        ("cashAvailableForInvestment",),
        ("Cash", "availableToTrade"),
        ("Cash", "cashAvailableForInvestment"),
        ("BalanceResponse", "availableToTrade"),
        ("BalanceResponse", "cashAvailableForInvestment"),
        ("Computed", "availableToTrade"),
    ]
    for path in candidates:
        v = _dig(bal, *path)
        f = _as_float(v)
        if f > 0:
            return f

    # Fall back to buying power fields as a last resort
    bp = _parse_buying_power(bal)
    return _as_float(bp)


def _parse_buying_power(bal: dict) -> float:
    candidates = [
        ("buyingPower",),
        ("marginBuyingPower",),
        ("BalanceResponse", "buyingPower"),
        ("BalanceResponse", "marginBuyingPower"),
        ("Computed", "buyingPower"),
    ]
    for path in candidates:
        v = _dig(bal, *path)
        f = _as_float(v)
        if f > 0:
            return f
    return 0.0


def _parse_settled_cash(bal: dict) -> float:
    candidates = [
        ("settledCash",),
        ("settledCashForInvestment",),
        ("Cash", "settledCash"),
        ("BalanceResponse", "settledCash"),
        ("Computed", "settledCash"),
    ]
    for path in candidates:
        v = _dig(bal, *path)
        f = _as_float(v)
        if f > 0:
            return f
    return 0.0


def _get_bal_triplet(broker_obj=None):
    ak = _resolve_account_key(broker_obj)
    if not ak:
        LOG.warning("No account_id_key could be resolved; returning zeros.")
        return 0.0, 0.0, 0.0

    bal = _fetch_balances(ak)
    if not isinstance(bal, dict) or not bal:
        LOG.warning("Balances unavailable or not a dict; returning zeros.")
        return 0.0, 0.0, 0.0

    att = _parse_available_to_trade(bal)
    bp  = _parse_buying_power(bal)
    sc  = _parse_settled_cash(bal)
    return float(att), float(bp), float(sc)


def _lb_get_buying_power(self) -> float:
    att, bp, _ = _get_bal_triplet(self)
    # Prefer AvailableToTrade for cash-account sizing; fallback to BP
    return att if att > 0 else bp


def _lb_get_settled_cash(self) -> float:
    _, __, sc = _get_bal_triplet(self)
    return sc


def _lb_get_positions_value(self) -> float:
    """
    If your LiveBroker already has a portfolio or positions accessor,
    prefer that. Otherwise, try falling back to balances->positionsValue.
    """
    # If the broker exposes a positions value directly, use it
    for a in ("positions_value", "positionsValue", "get_positions_value"):
        if hasattr(self, a):
            try:
                v = getattr(self, a)
                v = v() if callable(v) else v
                return _as_float(v)
            except Exception:
                pass

    # Parse from balances if present
    ak = _resolve_account_key(self)
    bal = _fetch_balances(ak)
    pv = 0.0
    for path in (("positionsValue",),
                 ("BalanceResponse", "positionsValue"),
                 ("Computed", "positionsValue")):
        v = _dig(bal, *path)
        pv = max(pv, _as_float(v))
    return pv


def patch_live_broker():
    if LiveBroker is None:
        LOG.error("LiveBroker class not found; cannot patch.")
        return

    # Inject only if missing (safe re-imports)
    if not hasattr(LiveBroker, "get_buying_power"):
        setattr(LiveBroker, "get_buying_power", _lb_get_buying_power)
    if not hasattr(LiveBroker, "get_settled_cash"):
        setattr(LiveBroker, "get_settled_cash", _lb_get_settled_cash)
    if not hasattr(LiveBroker, "get_positions_value"):
        setattr(LiveBroker, "get_positions_value", _lb_get_positions_value)

    LOG.info("[broker_methods] LiveBroker patched with balance getters.")


# Apply at import time (side effect import)
try:
    patch_live_broker()
except Exception as e:
    LOG.error("Failed to patch LiveBroker: %s", e)
