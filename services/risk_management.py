# services/risk_management.py
from datetime import date, datetime
from dateutil import parser
from datetime import datetime, timedelta

def count_day_trades(trade_log, min_equity=25000, account_equity=0):
    """
    Count the number of day trades in the last 5 business days.
    Returns count and whether PDT rule is triggered (assuming margin acct).
    """
    # Only check if below PDT min equity threshold
    if account_equity >= min_equity:
        return 0, False

    # Group trades by day and symbol
    day_trades = {}
    for t in trade_log:
        date = t['trade_time'][:10]  # 'YYYY-MM-DD'
        symbol = t['symbol']
        action = t['action'].upper()
        if date not in day_trades:
            day_trades[date] = {}
        if symbol not in day_trades[date]:
            day_trades[date][symbol] = set()
        day_trades[date][symbol].add(action)
    
    # Count days with both BUY and SELL
    total_day_trades = []
    today = datetime.utcnow().date()
    five_days_ago = today - timedelta(days=7)  # pad a weekend just in case

    for date, syms in day_trades.items():
        dt = datetime.strptime(date, "%Y-%m-%d").date()
        if five_days_ago <= dt <= today:
            for acts in syms.values():
                if "BUY" in acts and "SELL" in acts:
                    total_day_trades.append(dt)
    
    # PDT if >=4 in last 5 business days
    pdt_flag = len(total_day_trades) >= 4
    return len(total_day_trades), pdt_flag

def daily_loss_cap_breached(trade_log, holdings, max_daily_loss=-1000):
    """
    Returns True if realized + unrealized loss today is <= cap (negative cap).
    """
    today = datetime.utcnow().date()
    realized = sum(
        float(t["pnl"] or 0)
        for t in trade_log
        if t["action"].upper() == "SELL" and
           datetime.fromisoformat(t["trade_time"]).date() == today
    )
    unrealized = sum(
        (h["last_price"] - h["price_paid"]) * h["qty"]
        for h in holdings
    )
    total = realized + unrealized
    return total <= max_daily_loss  # e.g., if cap is -$1000, will halt at -$1000

def check_trailing_stop(current_price, highest_price, trailing_stop_pct):
    """
    Returns True if current price falls below trailing stop threshold.
    """
    stop_price = highest_price * (1 - trailing_stop_pct / 100.0)
    return current_price <= stop_price

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
    def get_trade_time(t):
        return t.get("time") or t.get("trade_time") or t.get("timestamp")

    last_sale = next(
        (get_trade_time(t) for t in reversed(trade_log)
         if isinstance(t, dict)
         and t.get("symbol") == symbol
         and t.get("action") == "SELL"
         and get_trade_time(t) is not None),
        None
    )
    if not last_sale:
        return False

    # normalize to datetime
    if isinstance(last_sale, str):
        try:
            last_sale = datetime.fromisoformat(last_sale)
        except Exception:
            from dateutil import parser
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
        (t.get("trade_time") for t in reversed(trade_log)
         if isinstance(t, dict) and t.get("symbol") == symbol and t.get("action") == "BUY" and t.get("trade_time") is not None),
        None
    )
    if not last_buy:
        return False

    # normalize to date
    if isinstance(last_buy, str):
        try:
            dt = datetime.fromisoformat(last_buy)
        except ValueError:
            from dateutil import parser
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
