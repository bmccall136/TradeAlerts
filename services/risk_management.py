# services/risk_management.py

from datetime import date


def check_stop_loss(price: float, entry_price: float, stop_loss_pct: float) -> bool:
    """
    Returns True if the current price has fallen to or below the stop-loss threshold.
    """
    return price <= entry_price * (1 - stop_loss_pct)


def wash_sale_prohibited(current_date: date, last_sale_date: date, days_window: int = 30) -> bool:
    """
    Returns True if a buy would violate the wash sale rule.
    Wash sales are prohibited if purchased within `days_window` days before or after a sale.
    """
    delta_days = (current_date - last_sale_date).days
    return abs(delta_days) <= days_window


def funds_not_settled(trade_date: date, settlement_days: int = 2) -> bool:
    """
    Returns True if funds from a trade on `trade_date` are not yet settled.
    Settlement occurs `settlement_days` after the trade date.
    """
    delta_days = (date.today() - trade_date).days
    return delta_days < settlement_days

def enforce_wash_sale(symbol, trade_log, buy_date, days=30):
    """
    Return True if the wash-sale rule prohibits buying this symbol on buy_date.
    """
    return wash_sale_prohibited(symbol, buy_date, trade_log, days)

def enforce_settlement(current_time, trade_time, settlement_days=2):
    """
    Return True if funds are not yet settled (i.e. you cannot trade again).
    """
    return funds_not_settled(current_time, trade_time, settlement_days)
