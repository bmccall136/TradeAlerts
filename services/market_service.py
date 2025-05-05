import requests
from config import Config

ETRADE_BASE_URL = Config.ETRADE_BASE_URL
YAHOO_BASE_URL  = Config.YAHOO_BASE_URL

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
    Fetch intraday price data from Yahoo Finance.
    interval: '1m','2m','5m', etc.
    range_: '1d','5d', etc.
    """
    params = {'symbol': symbol, 'interval': interval, 'range': range_}
    response = requests.get(YAHOO_BASE_URL, params=params)
    response.raise_for_status()
    return response.json()
