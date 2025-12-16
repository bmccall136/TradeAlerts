from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol


class Broker(Protocol):
    # read-only
    def get_account(self) -> dict[str, Any]: ...
    def get_positions(self) -> Iterable[dict[str, Any]]: ...
    def last_price(self, symbol: str) -> float: ...

    # trading
    def buy(self, symbol: str, qty: int, price: float) -> bool: ...
    def sell(self, symbol: str, qty: int, price: float) -> bool: ...


# ---------- Simulation adapter (maps to trading_helpers) ----------
from services.etrade_service import fetch_etrade_quote  # you already use this
from services.trading_helpers import (
    buy_stock,
    get_cash,
    get_holdings,
    sell_stock,
)


class SimBroker:
    def get_account(self) -> dict[str, Any]:
        return {
            "buying_power": get_cash(),
            "settled_cash": get_cash(),
            "equity_value": 0.0,
        }

    def get_positions(self):
        # map your tuple schema -> dict
        for sym, qty, avg, lp in get_holdings() or []:
            yield {"symbol": sym, "qty": qty, "avg_cost": avg, "last_price": lp}

    def last_price(self, symbol: str) -> float:
        q = fetch_etrade_quote(symbol)
        return float(
            q
            if isinstance(q, (int, float))
            else (q.get("last_price") or q.get("lastTrade") or 0.0)
        )

    def buy(self, symbol: str, qty: int, price: float) -> bool:
        return bool(buy_stock(symbol, qty, price))

    def sell(self, symbol: str, qty: int, price: float) -> bool:
        return bool(sell_stock(symbol, qty, price))


# ---------- Live adapter (E*TRADE) ----------
from services import etrade_service as et


class ETradeBroker:
    def get_account(self) -> dict[str, Any]:
        # you already normalize in dashboard; reuse that helper if you want
        return et.get_account_summary() or {}

    def get_positions(self):
        return et.get_positions() or []

    def last_price(self, symbol: str) -> float:
        q = et.fetch_etrade_quote(symbol)
        return float(
            q
            if isinstance(q, (int, float))
            else (q.get("last_price") or q.get("lastTrade") or 0.0)
        )

    def buy(self, symbol: str, qty: int, price: float) -> bool:
        # implement via your existing etrade_service order function
        return et.place_market_buy(
            symbol, qty
        )  # or place_limit_buy(symbol, qty, price)

    def sell(self, symbol: str, qty: int, price: float) -> bool:
        return et.place_market_sell(symbol, qty)
