import json
import logging
import os

import yfinance as yf
import pandas as pd

from .alert_service import insert_alert
from .indicators import calculate_macd, compute_rsi, compute_bollinger
from .news_service import news_sentiment  # this already exists in news_service

logger = logging.getLogger(__name__)


def load_sp500_list():
    """
    Try to load the S&P 500 symbols from Wikipedia. Returns a list of tickers.
    """
    WIKI_URL = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    try:
        df = pd.read_html(WIKI_URL, header=0)[0]
        # Wikipedia table uses dots in tickers (e.g. BRK.B) – change to dash
        symbols = df['Symbol'].str.replace(r'\.', '-', regex=True).tolist()
        logger.info(f"Loaded {len(symbols)} S&P 500 symbols from Wikipedia")
        return symbols
    except Exception as e:
        logger.warning("Could not fetch S&P 500 list from Wikipedia, falling back to local file", exc_info=e)
        fn = os.path.join(os.path.dirname(__file__), '..', 'sp500_symbols.txt')
        try:
            with open(fn) as f:
                symbols = [s.strip() for s in f if s.strip()]
                logger.info(f"Loaded {len(symbols)} S&P 500 symbols from local file")
                return symbols
        except FileNotFoundError:
            logger.error(f"No local fallback file found at {fn}")
            return []


def get_symbols(simulation=False):
    """
    Return the list of symbols to scan.
    For live (simulation=False) we always scan the current S&P 500.
    """
    if simulation:
        # your existing simulation-based symbol loading here
        # e.g. read from your simulation db
        return load_symbols_from_simulation_db()

    return load_sp500_list()


def fetch_data(sym, period='1d', interval='5m'):
    """
    Fetch OHLC + indicators for a single symbol, decide if it triggers an alert.
    """
    # --- (keep your existing fetch_data code here, unchanged) ---
    # at the end you call insert_alert(...) and log via logger.info
    ...
