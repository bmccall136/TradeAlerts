import yfinance as yf
from config import Config
import requests

ETRADE_BASE_URL = Config.ETRADE_BASE_URL

def fetch_etrade_quote(symbol):
    """
    Fetch a market quote for `symbol` using the E*TRADE API.
    Returns JSON or raises an exception on error.
    """
    url = f"{ETRADE_BASE_URL}/{symbol}.json"
    # TODO: attach OAuth headers
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def fetch_yahoo_intraday(symbol, interval='5m', range_='1d'):
    """
    Fetch intraday price data from Yahoo Finance using the yfinance library.
    Returns a dict with last_price, timestamps, and prices arrays.
    """
    ticker = yf.Ticker(symbol)
    # period should match range_ (e.g., '1d', '5d'), interval like '5m'
    hist = ticker.history(period=range_, interval=interval)
    if hist.empty:
        return {'last_price': None, 'timestamps': [], 'prices': []}
    # Convert pandas objects to serializable types
    timestamps = [ts.to_pydatetime() for ts in hist.index]
    prices = hist['Close'].tolist()
    last_price = float(prices[-1])
    return {
        'last_price': last_price,
        'timestamps': timestamps,
        'prices': prices
    }
