import os
import requests
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

# Ensure VADER lexicon is available
nltk.download('vader_lexicon', quiet=True)

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
NEWSAPI_URL = "https://newsapi.org/v2/everything"

def fetch_sentiment_for(symbol, count=3):
    """
    Alias for news_sentiment(), so scanners importing
    fetch_sentiment_for() continue to work.
    """
    return news_sentiment(symbol, count)

    services/news_service.py
def fetch_latest_headlines(symbol, count=3):
    """
    Fetch the latest `count` headlines for a given symbol via NewsAPI.org.
    Returns a list of dicts with `title` and `url` keys, or an empty list on error.
    """
    try:
        params = {
            "q":        symbol,
            "apiKey":   NEWSAPI_KEY,
            "language": "en",
            "sortBy":   "publishedAt",
            "pageSize": count
        }
        resp = requests.get(NEWSAPI_URL, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        # Return structured headlines instead of plain strings
        return [
            {
                "title": article.get("title", ""),
                "url":   article.get("url", "")
            }
            for article in data.get("articles", [])
        ]
    except Exception:
        return []

# Add to services/news_service.py

def get_latest_news_for_symbol(symbol):
    """
    Returns a dummy news dict for testing.
    Replace with real implementation to fetch news.
    """
    # Example: you could integrate with Yahoo, Finnhub, or NewsAPI here
    return {
        'url': f'https://www.google.com/search?q={symbol}+stock+news',
        'headline': f'Latest news for {symbol}'
    }
