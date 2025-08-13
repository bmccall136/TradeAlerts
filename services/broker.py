"""
Broker adapter layer so the same scan/ranking code can route
to SIM or to E*TRADE with a tiny switch.
"""
from __future__ import annotations
import os
import logging

logger = logging.getLogger("broker")

# --- SIM broker -------------------------------------------------------
class SimBroker:
    """Wraps existing simulation helpers."""
    name = "SIM"

    def get_account_summary(self) -> dict:
        # Sim uses your stored/ledger cash so the UI can still show something
        try:
            from services.trading_helpers import get_cash
            return {"mode": "SIM", "buying_power": float(get_cash()), "settled_cash": float(get_cash())}
        except Exception:
            return {"mode": "SIM", "buying_power": 0.0, "settled_cash": 0.0}

    def buy(self, symbol: str, qty: int, price: float | None = None, order_type: str = "MARKET") -> dict:
        from services.trading_helpers import buy_stock
        if qty <= 0:
            raise ValueError("qty must be >= 1")
        buy_stock(symbol, int(qty), float(price or 0.0))
        return {"mode": "SIM", "status": "FILLED", "symbol": symbol, "qty": int(qty), "price": float(price or 0.0)}

    def sell(self, symbol: str, qty: int | None = None, price: float | None = None, order_type: str = "MARKET") -> dict:
        from services.trading_helpers import sell_stock
        sell_stock(symbol, qty, price)
        return {"mode": "SIM", "status": "FILLED", "symbol": symbol, "qty": int(qty or 0), "price": float(price or 0.0)}


# --- E*TRADE broker ---------------------------------------------------
class EtradeBroker:
    """
    Thin wrapper over your E*TRADE API helpers. This assumes you will expose:
      - get_account_summary() -> dict with buying_power/settled_cash
      - preview_equity_order(side, symbol, qty, order_type="MARKET", price=None)
      - place_equity_order(preview) -> dict
    If those helpers aren't present yet, buy/sell will raise a clear error.
    """
    name = "LIVE"

    def __init__(self):
        # Optional sanity: check env keys present
        ck = os.getenv("ETRADE_CONSUMER_KEY") or os.getenv("ETRADE_API_KEY")
        cs = os.getenv("ETRADE_CONSUMER_SECRET") or os.getenv("ETRADE_API_SECRET")
        if not (ck and cs):
            logger.warning("[LIVE] Missing E*TRADE consumer key/secret in environment")

        try:
            from services.etrade_service import fetch_etrade_quote  # noqa: F401
        except Exception:
            logger.warning("[LIVE] Could not import services.etrade_service; quotes may fail")

    def get_account_summary(self) -> dict:
        try:
            from services.etrade_service import get_account_summary
        except Exception as e:
            logger.warning(f"[LIVE] get_account_summary not available: {e}")
            return {}
        try:
            data = get_account_summary()
            # normalize common keys for the UI
            bp  = float(data.get("buying_power") or data.get("accountBP") or 0.0)
            sc  = float(data.get("settled_cash") or data.get("settledCash") or 0.0)
            typ = data.get("account_type") or data.get("accountType") or ""
            return {"mode": "LIVE", "buying_power": bp, "settled_cash": sc, "account_type": typ, **data}
        except Exception as e:
            logger.error(f"[LIVE] account summary failed: {e}")
            return {}

    def buy(self, symbol: str, qty: int, price: float | None = None, order_type: str = "MARKET") -> dict:
        try:
            from services.etrade_service import preview_equity_order, place_equity_order
        except Exception as e:
            raise RuntimeError("E*TRADE order helpers are not wired yet (need preview_equity_order/place_equity_order).") from e
        if qty <= 0:
            raise ValueError("qty must be >= 1")
        prev = preview_equity_order(side="BUY", symbol=symbol, qty=int(qty), order_type=order_type, price=price)
        return place_equity_order(prev)

    def sell(self, symbol: str, qty: int | None = None, price: float | None = None, order_type: str = "MARKET") -> dict:
        try:
            from services.etrade_service import preview_equity_order, place_equity_order
        except Exception as e:
            raise RuntimeError("E*TRADE order helpers are not wired yet (need preview_equity_order/place_equity_order).") from e
        prev = preview_equity_order(side="SELL", symbol=symbol, qty=int(qty or 0), order_type=order_type, price=price)
        return place_equity_order(prev)


def get_broker(mode: str | None = None):
    """
    mode: "SIM" (default) or "LIVE"
    """
    mode = (mode or os.getenv("BROKER_MODE") or "SIM").upper()
    if mode == "LIVE":
        return EtradeBroker()
    return SimBroker()
