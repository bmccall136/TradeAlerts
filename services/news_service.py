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
    Returns list of dicts [{ title, url }] or empty list on error.
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
        return [
            {"title": art["title"], "url": art["url"]}
            for art in data.get("articles", [])
        ]
    except Exception:
        return []

def news_sentiment(symbol, count=3):
    """
    Return (avg_sentiment, first_url). avg_sentiment ∈ [–1,1], url or ''.
    """
    headlines = fetch_latest_headlines(symbol, count)
    if not headlines:
        return 0.0, ""
    analyzer = SentimentIntensityAnalyzer()
    scores = [analyzer.polarity_scores(h["title"])["compound"] for h in headlines]
    avg = sum(scores) / len(scores)
    first_url = headlines[0]["url"]
    return avg, first_url
