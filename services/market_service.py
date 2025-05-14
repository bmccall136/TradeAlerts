# services/market_service.py

import os
import requests
import pandas as pd
import yfinance as yf
from config import Config

# E*TRADE API endpoint (configure in config.py)
ETRADE_BASE_URL = Config.ETRADE_BASE_URL

def fetch_etrade_price(symbol: str) -> float:
    """
    Fetches the latest market price for `symbol` from E*TRADE API.
    Falls back to Yahoo Finance if the E*TRADE call fails or is not configured.
    """
    try:
        # Replace with real E*TRADE OAuth call if available
        url = f"{ETRADE_BASE_URL}/{symbol}.json"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        # Assuming the JSON has a field 'lastTradePrice'
        return float(data.get('lastTradePrice'))
    except Exception:
        # Fallback to Yahoo Finance
        ticker = yf.Ticker(symbol)
        df = ticker.history(period='1d', interval='1m')
        if not df.empty:
            return float(df['Close'].iloc[-1])
        raise

def fetch_yahoo_intraday(symbol: str, period: str = '5d', interval: str = '5m') -> pd.DataFrame:
    """
    Fetch intraday OHLCV data for a symbol from Yahoo Finance.
    Returns a pandas DataFrame indexed by datetime.
    """
    df = yf.Ticker(symbol).history(period=period, interval=interval)
    if not df.empty:
        df.index = pd.to_datetime(df.index)
    return df
