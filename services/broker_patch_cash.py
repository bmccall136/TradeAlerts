# services/broker_patch_cash.py
# Drop-in: ensures LiveBroker has get_buying_power() and get_settled_cash()
# for cash accounts (ATT-first).  You’ll see a log line when it activates.

import logging
from services import broker as _broker

LOG = logging.getLogger("broker_patch_cash")

def _to_float(x):
    try:
        if x is None:
            return 0.0
        if isinstance(x, (int, float)):
            return float(x)
        return float(str(x).replace("$", "").replace(",", "").strip())
    except Exception:
        return 0.0

def _parse_balances(bal):
    if not isinstance(bal, dict):
        return {}
    d = {}
    for k in ("availableToTrade", "buyingPower", "availableFunds"):
        if k in bal:
            d[k] = bal[k]
    for sub in ("accountBalance", "Computed", "BalanceResponse"):
        v = bal.get(sub)
        if isinstance(v, dict):
            for k in ("availableToTrade", "buyingPower", "availableFunds"):
                if k in v:
                    d.setdefault(k, v[k])
    return d

def _fetch_balances_dict(et):
    try:
        key = getattr(et, "_account_id_key", None)
        if not key and hasattr(et, "first_account_id_key"):
            key = et.first_account_id_key()
        if not key:
            return {}
        bal = et.get_balances(key)
        if isinstance(bal, dict):
            return bal
        return {}
    except Exception:
        return {}

try:
    LiveBroker = getattr(_broker, "LiveBroker", None)
    if LiveBroker is None:
        raise AttributeError("LiveBroker not found in services.broker")

    def get_buying_power(self):
        bal = _fetch_balances_dict(self._et)
        d = _parse_balances(bal)
        return _to_float(
            d.get("availableToTrade")
            or d.get("buyingPower")
            or d.get("availableFunds")
        )

    def get_settled_cash(self):
        # For cash accounts, we ignore settled logic.
        return 0.0

    setattr(LiveBroker, "get_buying_power", get_buying_power)
    setattr(LiveBroker, "get_settled_cash", get_settled_cash)

    LOG.info("LiveBroker patched (ATT-first; cash-account friendly)")
except Exception as e:
    LOG.error("broker_patch_cash failed: %s", e)
