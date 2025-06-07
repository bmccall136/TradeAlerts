import os
import requests
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

# Ensure VADER lexicon is available
nltk.download('vader_lexicon', quiet=True)

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
NEWSAPI_URL = "https://newsapi.org/v2/everything"

def fetch_latest_headlines(symbol, count=3):
    """
    Fetch the latest 'count' headlines for a given symbol via NewsAPI.org.
    Returns an empty list on any error (e.g., unauthorized).
    """
    try:
        params = {
            "q": symbol,
            "apiKey": NEWSAPI_KEY,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": count
        }
        resp = requests.get(NEWSAPI_URL, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return [article["title"] for article in data.get("articles", [])]
    except Exception:
        # On error, return no headlines
        return []

def news_sentiment(symbol, count=3):
    """
    Return the average VADER sentiment compound score for recent headlines.
    If fetching headlines fails or none are found, returns 0.0.
    """
    headlines = fetch_latest_headlines(symbol, count)
    if not headlines:
        return 0.0
    analyzer = SentimentIntensityAnalyzer()
    scores = [analyzer.polarity_scores(headline)["compound"] for headline in headlines]
    return sum(scores) / len(scores)

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
