import os
import requests
import logging

import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

# Ensure VADER lexicon is available
nltk.download('vader_lexicon', quiet=True)

# NewsAPI configuration
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
NEWSAPI_URL = "https://newsapi.org/v2/everything"

def fetch_latest_headlines(symbol: str, count: int = 3) -> list[dict]:
    """
    Fetch the latest `count` headlines for a given symbol via NewsAPI.org.
    Returns a list of dicts with 'title' and 'url' keys, or an empty list on error.
    Treats HTTP 429 as a rate-limit warning.
    """
    if not NEWSAPI_KEY:
        logging.error("NEWSAPI_KEY not set; cannot fetch headlines.")
        return []

    params = {
        "q":        symbol,
        "apiKey":   NEWSAPI_KEY,
        "language": "en",
        "sortBy":   "publishedAt",
        "pageSize": count
    }
    try:
        resp = requests.get(NEWSAPI_URL, params=params, timeout=5)
        # Raise on 4xx/5xx (except we’ll catch 429 specially)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as he:
        status = he.response.status_code if he.response is not None else None
        if status == 429:
            # Rate‐limited: not a hard error, just skip news for now
            logging.warning(f"{symbol}: rate limited by NewsAPI (429); skipping news until reset.")
            return []
        else:
            logging.error(f"HTTP error fetching news for {symbol}: {he}")
            return []
    except Exception as e:
        logging.error(f"Error fetching news for {symbol}: {e}")
        return []

    try:
        data = resp.json()
        articles = data.get("articles", [])
        headlines = []
        for a in articles:
            title = a.get("title", "").strip()
            url   = a.get("url", "")
            if title and url:
                headlines.append({"title": title, "url": url})
        return headlines
    except Exception as e:
        logging.error(f"Failed parsing news JSON for {symbol}: {e}")
        return []

def news_sentiment(symbol: str, count: int = 3) -> float:
    """
    Compute average VADER compound sentiment over the latest headlines.
    Returns a float in [-1.0, 1.0], or 0.0 if no headlines.
    """
    headlines = fetch_latest_headlines(symbol, count)
    if not headlines:
        return 0.0

    sia = SentimentIntensityAnalyzer()
    scores = [sia.polarity_scores(item["title"])["compound"] for item in headlines]
    return sum(scores) / len(scores)

def fetch_sentiment_for(symbol: str, count: int = 3) -> float:
    """
    Alias for news_sentiment(), preserving backwards compatibility.
    """
    return news_sentiment(symbol, count)
