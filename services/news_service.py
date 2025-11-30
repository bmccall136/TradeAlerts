import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import nltk
import requests
from nltk.sentiment.vader import SentimentIntensityAnalyzer

# Ensure VADER lexicon is available
nltk.download("vader_lexicon", quiet=True)

# --- NewsAPI configuration ---------------------------------------------------

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
NEWSAPI_URL = "https://newsapi.org/v2/everything"

# --- DB configuration (log into live.db) -------------------------------------

DB_PATH = os.environ.get("LIVE_DB", r"C:\TradeAlerts\live.db")

DDL_NEWS_TABLE = """
CREATE TABLE IF NOT EXISTS news_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,        -- ISO8601 UTC timestamp / publishedAt
    symbol TEXT NOT NULL,    -- e.g. 'AAPL'
    headline TEXT,           -- news title
    source TEXT,             -- publisher name
    url TEXT,                -- article URL
    raw_json TEXT            -- full JSON blob from API
);

CREATE INDEX IF NOT EXISTS idx_news_symbol_ts
    ON news_events(symbol, ts DESC);
"""

# --- “Bad news” heuristics ---------------------------------------------------

NEGATIVE_KEYWORDS = [
    "downgrade",
    "cuts rating",
    "cuts price target",
    "slashed",
    "misses estimates",
    "misses earnings",
    "profit warning",
    "warning on earnings",
    "guidance cut",
    "guidance lowered",
    "plunge",
    "plunges",
    "tumble",
    "tumbles",
    "selloff",
    "crash",
    "crashes",
    "lawsuit",
    "sec charges",
    "fraud",
    "investigation",
    "probe",
    "recall",
    "halts trading",
    "trading halted",
    "bankruptcy",
    "chapter 11",
]


def _ensure_news_schema(conn: sqlite3.Connection) -> None:
    """Create news_events table/index if missing."""
    conn.executescript(DDL_NEWS_TABLE)


def _log_headlines_to_db(symbol: str, articles: List[Dict[str, Any]]) -> int:
    """
    Persist raw NewsAPI articles into news_events in live.db.
    Returns number of rows inserted.
    """
    if not articles:
        return 0

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        _ensure_news_schema(conn)

        sym = symbol.upper()
        inserted = 0

        for a in articles:
            # Prefer publishedAt from NewsAPI if present
            ts = a.get("publishedAt")
            if not ts:
                ts = (
                    datetime.now(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z")
                )

            headline = (a.get("title") or "").strip()
            src = (a.get("source") or {}).get("name")
            url = a.get("url")

            cur.execute(
                """
                INSERT INTO news_events (ts, symbol, headline, source, url, raw_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ts, sym, headline, src, url, json.dumps(a, ensure_ascii=False)),
            )
            inserted += 1

        conn.commit()
        return inserted

    except Exception as e:
        logging.error(f"Failed logging news for {symbol} into DB: {e}")
        return 0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Public API – fetch & sentiment
# --------------------------------------------------------------------------- #


def fetch_latest_headlines(symbol: str, count: int = 3) -> List[Dict[str, Any]]:
    """
    Fetch the latest `count` headlines for a given symbol via NewsAPI.org.
    Returns a list of dicts with at least 'title' and 'url' keys, or an empty
    list on error.

    Side effect: on success, raw articles are logged into the news_events
    table inside live.db.
    """
    if not NEWSAPI_KEY:
        logging.error("NEWSAPI_KEY not set; cannot fetch headlines.")
        return []

    # Restrict to stock/market context to avoid “fart walks” etc.
    query = (
        f'"{symbol}" AND '
        "(stock OR shares OR ETF OR earnings OR downgrade OR upgrade OR guidance OR outlook)"
    )

    params = {
        "q": query,
        "searchIn": "title,description",
        "apiKey": NEWSAPI_KEY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": count,
    }

    try:
        resp = requests.get(NEWSAPI_URL, params=params, timeout=5)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as he:
        status = he.response.status_code if he.response is not None else None
        if status == 429:
            logging.warning(
                f"{symbol}: rate limited by NewsAPI (429); skipping news until reset."
            )
            return []
        logging.error(f"HTTP error fetching news for {symbol}: {he}")
        return []
    except Exception as e:
        logging.error(f"Error fetching news for {symbol}: {e}")
        return []

    try:
        data = resp.json()
        articles = data.get("articles", []) or []

        # Log full article payloads into live.db
        _log_headlines_to_db(symbol, articles)

        # Return a trimmed list for callers:
        headlines: List[Dict[str, Any]] = []
        for a in articles:
            title = (a.get("title") or "").strip()
            url = a.get("url", "")
            if not title or not url:
                continue
            headlines.append(
                {
                    "title": title,
                    "url": url,
                    "source": (a.get("source") or {}).get("name"),
                    "publishedAt": a.get("publishedAt"),
                }
            )
        return headlines
    except Exception as e:
        logging.error(f"Failed parsing news JSON for {symbol}: {e}")
        return []


def news_sentiment(symbol: str, count: int = 3) -> float:
    """
    Compute average VADER compound sentiment over the latest headlines.
    Returns a float in [-1.0, 1.0], or 0.0 if no headlines.

    Note: this will also log headlines into live.db via fetch_latest_headlines().
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


# --------------------------------------------------------------------------- #
# Public API – DB readers / “bad news” flag for Sell Guard
# --------------------------------------------------------------------------- #


def recent_news_for_symbol(symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Read the most recent `limit` news rows for a symbol from news_events.
    Does NOT call NewsAPI – purely DB read.
    """
    conn: sqlite3.Connection | None = None
    rows: List[Tuple[str, str, str, str]] = []
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ts, headline, source, url
            FROM news_events
            WHERE symbol = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (symbol.upper(), limit),
        )
        rows = cur.fetchall()
    except Exception as e:
        logging.error(f"Error reading news for {symbol} from DB: {e}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    out: List[Dict[str, Any]] = []
    for ts, headline, source, url in rows:
        out.append(
            {
                "ts": ts,
                "headline": headline,
                "source": source,
                "url": url,
            }
        )
    return out


_sia: SentimentIntensityAnalyzer | None = None


def _get_sia() -> SentimentIntensityAnalyzer:
    global _sia
    if _sia is None:
        _sia = SentimentIntensityAnalyzer()
    return _sia


def _headline_looks_bad(headline: str, compound_threshold: float = -0.25) -> bool:
    """
    Heuristic: “bad” if it contains a negative keyword OR sentiment is quite negative.
    """
    if not headline:
        return False

    text = headline.lower()

    for kw in NEGATIVE_KEYWORDS:
        if kw in text:
            return True

    # Sentiment check
    sia = _get_sia()
    score = sia.polarity_scores(headline)["compound"]
    return score <= compound_threshold


def has_fresh_bad_news(
    symbol: str,
    lookback_minutes: int = 120,
    max_rows: int = 20,
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Return (flag, rows) where:
      - flag = True if there's at least one "bad" headline within lookback window
      - rows = list of bad headline dicts (ts, headline, source, url)

    Pure DB read; does NOT call the API (assumes something else is populating
    news_events in the background).
    """
    rows = recent_news_for_symbol(symbol, limit=max_rows)
    if not rows:
        return False, []

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=lookback_minutes)

    bad_rows: List[Dict[str, Any]] = []
    for row in rows:
        ts_str = row["ts"]
        try:
            # Handle "2025-11-28T18:00:00Z" -> add +00:00
            ts_norm = ts_str.replace("Z", "+00:00")
            ts = datetime.fromisoformat(ts_norm)
        except Exception:
            # If parsing fails, just skip the time filter and use keyword/sentiment
            ts = now

        if ts < cutoff:
            # Older than lookback window
            continue

        if _headline_looks_bad(row["headline"] or ""):
            bad_rows.append(row)

    return (len(bad_rows) > 0), bad_rows
