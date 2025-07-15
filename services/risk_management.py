# services/risk_management.py
import logging
from dateutil import parser
from datetime import date
from datetime import datetime


def check_stop_loss(price: float, entry_price: float, stop_loss_pct: float) -> bool:
    """
    Returns True if the current price has fallen to or below the stop-loss threshold.
    """
    return price <= entry_price * (1 - stop_loss_pct)

def wash_sale_prohibited(symbol: str, current_date: datetime, trade_log: list[dict]) -> bool:
    # find the most recent *sale* of this symbol
    last_sale_date = None
    for trade in reversed(trade_log):
        if trade["symbol"] == symbol and trade["action"] == "SELL":
            last_sale_date = trade["time"]
            break
    if not last_sale_date:
        return False
    # make sure we have a datetime, not a string
    if isinstance(last_sale_date, str):
        try:
            # adjust this if you used a different iso format
            last_sale_date = datetime.fromisoformat(last_sale_date)
        except ValueError:
            # fallback: try generic parsing
            from dateutil import parser
            last_sale_date = parser.parse(last_sale_date)

    # how many days since that sale?
    delta_days = (current_date - last_sale_date).days


def funds_not_settled(symbol: str, current_date: datetime, trade_log: list[dict]) -> bool:
    """
    Return True if there’s a BUY for `symbol` in trade_log whose settlement
    period (T+2 by default) hasn’t elapsed as of today.
    """
    # find the most recent *buy* of this symbol
    trade_date = None
    for trade in reversed(trade_log):
        if trade["symbol"] == symbol and trade["action"] == "BUY":
            trade_date = trade["time"]
            break
    if not trade_date:
        return False

    # ── normalize trade_date into a date object ──
    # (this block MUST be indented inside the function!)
    if isinstance(trade_date, str):
        try:
            td = datetime.fromisoformat(trade_date)
        except ValueError:
            td = parser.parse(trade_date)
    else:
        td = trade_date

    # if we got a datetime, convert to date
    if isinstance(td, datetime):
        td = td.date()

    # now calculate days since trade
    delta_days = (date.today() - td).days

    # assume T+2 settlement
    settlement_days = getattr(trade, "settlement_days", 2)
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
