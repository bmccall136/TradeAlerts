import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import yfinance as yf
import pandas as pd
import pytz

logger = logging.getLogger(__name__)
ET = pytz.timezone("US/Eastern")

def fetch_data_with_timeout(sym, period='1d', interval='5m', timeout=10):
    def _fetch():
        try:
            return yf.download(
                sym,
                period=period,
                interval=interval,
                auto_adjust=False,
                progress=False,
                threads=False
            )
        except Exception as e:
            logger.error(f"[ERROR] Yahoo download {sym} failed: {e}")
            return None

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_fetch)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            logger.error(f"[ERROR] Yahoo download {sym} timed out after {timeout}s")
            return None


def fetch_intraday_vwap(symbol: str) -> float:
    """
    Fetch today's 1‑minute bars for `symbol` and return the intraday VWAP.
    """
    now_et     = datetime.now(ET)
    today_start= now_et.replace(hour=0, minute=0, second=0, microsecond=0)

    raw = fetch_data_with_timeout(
        symbol,
        period="1d",
        interval="1m"
    )
    if raw is None or raw.empty:
        raise ValueError(f"No intraday data for {symbol}")

    df = raw
    # flatten MultiIndex from yfinance (('SYM','Open'), …)
    if isinstance(df.columns, pd.MultiIndex):
        # take the second level name
        df.columns = df.columns.get_level_values(1)

    # lowercase everything
    df.columns = [col.lower() for col in df.columns]

    for col in ("high", "low", "close", "volume"):
        if col not in df:
            raise KeyError(f"Missing {col} in intraday data for {symbol}")

    df["pv"]      = df["close"] * df["volume"]
    df["cum_pv"]  = df["pv"].cumsum()
    df["cum_vol"] = df["volume"].cumsum()

    return float(df["cum_pv"].iat[-1] / df["cum_vol"].iat[-1])
