import logging
import pandas as pd
from .etrade_service import fetch_etrade_quote
from .news_service import fetch_latest_headlines, analyze_sentiment
from .indicators import calculate_macd, compute_rsi, compute_bollinger

logger = logging.getLogger(__name__)

WIKI_SNP_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def get_symbols(simulation: bool = False):
    """
    Returns the list of symbols to scan:
    - If `simulation=True`, pulls from your simulation DB.
    - Otherwise, scrapes the current S&P 500 list from Wikipedia.
    """
    if simulation:
        from .simulation_service import get_simulation_symbols
        return get_simulation_symbols()

    # scrape with pandas
    try:
        tables = pd.read_html(WIKI_SNP_URL, attrs={"id": "constituents"})
        df = tables[0]
        # Wikipedia uses e.g. "BRK.B" – convert dots to dashes
        symbols = df["Symbol"].str.replace(r"\.", "-", regex=True).tolist()
        return symbols
    except Exception as e:
        logger.error(f"Failed to load S&P 500 list: {e}")
        return []


def analyze_symbol(symbol: str):
    """
    Fetches quote + computes triggers + (if Prime) pulls news sentiment.
    Returns alert dict or None.
    """
    try:
        price = fetch_etrade_quote(symbol)
    except Exception as e:
        logger.error(f"{symbol}: error fetching price: {e}")
        return None

    triggers = []

    # MACD
    try:
        if calculate_macd(symbol):
            triggers.append("MACD")
    except Exception as e:
        logger.error(f"{symbol}: MACD error: {e}")

    # RSI
    try:
        if compute_rsi(symbol):
            triggers.append("RSI")
    except Exception as e:
        logger.error(f"{symbol}: RSI error: {e}")

    # Bollinger
    try:
        upper, lower = compute_bollinger(symbol)
        if price > upper:
            triggers.append("Bollinger↑")
        elif price < lower:
            triggers.append("Bollinger↓")
    except Exception as e:
        logger.error(f"{symbol}: Bollinger error: {e}")

    # Only pull news for Prime candidates
    sentiment = None
    if len(triggers) >= 3:
        try:
            headlines = fetch_latest_headlines(symbol)
            sentiment = analyze_sentiment(headlines)
            if sentiment and sentiment > 0.05:
                triggers.append("News 📰")
        except Exception as e:
            logger.error(f"{symbol}: News error: {e}")

    # Only Prime (3+ triggers) produces an alert
    if len(triggers) < 3:
        return None

    return {
        "symbol": symbol,
        "price": price,
        "triggers": triggers,
        "alert_type": "Prime",
        "confidence": 100,
        "sentiment": sentiment,
    }
