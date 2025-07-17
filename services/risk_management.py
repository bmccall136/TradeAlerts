# services/risk_management.py
from datetime import date, datetime
from dateutil import parser

def check_stop_loss(price: float, entry_price: float, stop_loss_pct: float) -> bool:
    """
    True if price has hit or fallen below the entry_price * (1 - stop_loss_pct).
    """
    return price <= entry_price * (1 - stop_loss_pct)


def wash_sale_prohibited(
    symbol: str,
    current_date: datetime,
    trade_log: list[dict],
    days: int = 30
) -> bool:
    """
    Return True if a previous SELL for `symbol` occurred within the last `days`.
    """
    last_sale = next(
        (t["time"] for t in reversed(trade_log)
         if t["symbol"] == symbol and t["action"] == "SELL"),
        None
    )
    if not last_sale:
        return False

    # normalize to datetime
    if isinstance(last_sale, str):
        try:
            last_sale = datetime.fromisoformat(last_sale)
        except ValueError:
            last_sale = parser.parse(last_sale)

    return (current_date - last_sale).days < days


def funds_not_settled(
    symbol: str,
    current_date: datetime,
    trade_log: list[dict],
    settlement_days: int = 2
) -> bool:
    """
    True if the most recent BUY for `symbol` has not yet settled (T+settlement_days).
    """
    last_buy = next(
        (t["time"] for t in reversed(trade_log)
         if t["symbol"] == symbol and t["action"] == "BUY"),
        None
    )
    if not last_buy:
        return False

    # normalize to date
    if isinstance(last_buy, str):
        try:
            dt = datetime.fromisoformat(last_buy)
        except ValueError:
            dt = parser.parse(last_buy)
    else:
        dt = last_buy

    buy_date = dt.date() if isinstance(dt, datetime) else dt
    days_since = (date.today() - buy_date).days

    return days_since < settlement_days


def enforce_wash_sale(
    symbol: str,
    trade_log: list[dict],
    buy_date: datetime,
    days: int = 30
) -> bool:
    """Alias: True if the wash sale rule blocks buying today."""
    return wash_sale_prohibited(symbol, buy_date, trade_log, days)


def enforce_settlement(
    symbol: str,
    trade_log: list[dict],
    current_time: datetime,
    settlement_days: int = 2
) -> bool:
    """Alias: True if funds from the last buy haven’t settled yet."""
    return funds_not_settled(symbol, current_time, trade_log, settlement_days)
