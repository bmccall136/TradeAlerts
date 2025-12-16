# services/execution_service.py

from datetime import datetime

from services.trading_helpers import (
    get_cash,
    insert_position,
    insert_trade,
    remove_position,
    set_cash,
)


def calculate_qty(settings, market):
    """How many shares to buy given per-trade cap & remaining cash."""
    price = market["price"]
    max_dollars = min(settings.max_per_trade, get_cash())
    return int(max_dollars // price)


def buy_stock(symbol, qty, price):
    """Debit cash, record a trade, and track an open position."""
    cost = qty * price
    cash = get_cash()
    if cost > cash:
        raise ValueError("Insufficient cash")
    set_cash(cash - cost)
    insert_trade(symbol, qty, price, side="BUY")
    insert_position(symbol, qty, entry_time=datetime.utcnow(), entry_price=price)


def sell_stock(symbol, qty, price):
    """Credit cash, record a sell trade, and close out the position."""
    proceeds = qty * price
    set_cash(get_cash() + proceeds)
    insert_trade(symbol, qty, price, side="SELL")
    remove_position(symbol)


def evaluate_exit(position, settings):
    """
    Return True if your exit criteria are met.
    E.g. trailing stop:
      current_price < (peak_price * (1 - settings.trailing_stop_pct))
    """
    current = position["price"]
    peak = position["peak_price"]
    pct_down = (peak - current) / peak
    return pct_down >= settings.trailing_stop_pct
