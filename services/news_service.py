import os
import logging
import requests
from datetime import datetime, timedelta
from textblob import TextBlob

logger = logging.getLogger(__name__)
NEWSAPI_KEY = os.getenv('NEWSAPI_KEY')


def fetch_latest_headlines(symbol, count=5):
    """
    Fetch the most recent news headlines for `symbol` via NewsAPI.
    """
    if not NEWSAPI_KEY:
        logger.error("NEWSAPI_KEY not set in environment")
        return []

    url = 'https://newsapi.org/v2/everything'
    params = {
        'q': symbol,
        'apiKey': NEWSAPI_KEY,
        'pageSize': count,
        'sortBy': 'publishedAt',
        'language': 'en',
    }
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        articles = resp.json().get('articles', [])
        return [a['title'] for a in articles]
    except Exception as e:
        logger.error(f"Error fetching news for {symbol}", exc_info=e)
        return []


def news_sentiment(symbol, count=5):
    """
    Compute a simple average polarity across the latest `count` headlines.
    """
    headlines = fetch_latest_headlines(symbol, count)
    if not headlines:
        return 0.0

    scores = []
    for h in headlines:
        blob = TextBlob(h)
        scores.append(blob.sentiment.polarity)
    sentiment = sum(scores) / len(scores)
    return sentiment


# alias so market_service (and any other code) can import this name
analyze_sentiment = news_sentiment
