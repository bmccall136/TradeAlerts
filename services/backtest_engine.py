# services/backtest_engine.py

from services.settings_schema import BacktestSettings
from services.trading_helpers import init_backtest_db


def run_full_backtest(settings: BacktestSettings, symbols, **kwargs):
    """
    Initialize the backtest DB and run the backtest.
    Any keyword args (e.g. wash_sale, settlement) are swallowed so you
    can pass them without error.
    Returns: (trades_list, summary_dict)
    """
    # (Re)create the backtest schema
    init_backtest_db()

    # TODO: implement the backtest logic here...

    # For now, return empty results so it matches what your view expects:
    return [], {}
