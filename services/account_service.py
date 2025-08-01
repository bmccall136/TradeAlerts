import logging
from datetime import datetime

# reuse the pyetrade client instantiated in market_service
from .market_service import client

logger = logging.getLogger(__name__)


def get_cash() -> float:
    """
    Fetches total available cash by listing accounts (XML) and retrieving balances (XML).
    """
    import xml.etree.ElementTree as ET

    # derive root URL
    root = client.base_url.rstrip('/')
    if root.endswith('/v1/market'):
        root = root[:-len('/v1/market')]

    # 1) List accounts (XML)
    list_url = f"{root}/v1/accounts/list"
    resp = client.session.get(list_url, params={"needBalances": "true"})
    resp.raise_for_status()
    # parse XML response
    root_el = ET.fromstring(resp.text)
    # namespace-agnostic findall for accountIdKey
    acct_keys = [el.text for el in root_el.findall('.//accountIdKey')]

    total = 0.0
    # 2) For each account, fetch its balance (XML)
    for acct_key in acct_keys:
        bal_url = f"{root}/v1/accounts/{acct_key}/balance"
        bresp = client.session.get(bal_url, params={"detailFlag": "positions"})
        bresp.raise_for_status()
        btree = ET.fromstring(bresp.text)
        # find all availableCash elements
        for cash_el in btree.findall('.//availableCash'):
            try:
                total += float(cash_el.text)
            except (TypeError, ValueError):
                continue
    return total


def get_position_qty(symbol: str) -> int:
    """Return the current position quantity for a given symbol."""
    positions = client.get_positions()
    entries = positions.get("PositionResponse", {}).get("Position", [])
    for pos in entries:
        if pos.get("symbol") == symbol:
            return int(pos.get("quantity", 0))
    return 0


def get_holdings() -> list[tuple[str, int, float, float]]:
    """
    Return a list of (symbol, qty, avg_price, last_price) for all open positions.
    """
    holdings: list[tuple[str, int, float, float]] = []
    positions = client.get_positions()
    entries = positions.get("PositionResponse", {}).get("Position", [])
    for pos in entries:
        qty = int(pos.get("quantity", 0))
        avg = float(pos.get("averagePrice", 0.0))
        last = 0.0
        if qty:
            market_val = float(pos.get("marketValue", 0.0))
            last = market_val / qty
        holdings.append((pos.get("symbol", ""), qty, avg, last))
    return holdings


def compute_qty(settings, price: float) -> int:
    """
    Decide how many shares to buy by allocating available cash across max_positions.
    """
    cash = get_cash()
    if getattr(settings, 'max_positions', 0) > 0:
        allocation = cash / settings.max_positions
    else:
        allocation = cash
    return int(allocation // price)


def buy_stock(symbol: str, qty: int, price: float, timestamp: datetime) -> None:
    """
    Execute a buy in the sim: deduct cash, record position, etc.
    """
    cash = get_cash()
    cost = qty * price
    # 1) update cash in your DB (implement update_cash separately)
    update_cash(cash - cost)
    # 2) record the new position or increment existing (implement upsert_position separately)
    upsert_position(symbol, qty, price)

    logger.info(f"Bought {qty} {symbol} @ {price:.2f}, cash left {(cash - cost):.2f}")
