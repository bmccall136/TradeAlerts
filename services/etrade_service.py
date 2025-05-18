import os
from requests_oauthlib import OAuth1Session

# Load E*TRADE credentials from environment, supporting various naming conventions
CONSUMER_KEY = (
    os.getenv("ETRADE_CONSUMER_KEY") or
    os.getenv("ETRADE_API_KEY") or
    os.getenv("CONSUMER_KEY")
)
CONSUMER_SECRET = (
    os.getenv("ETRADE_CONSUMER_SECRET") or
    os.getenv("ETRADE_API_SECRET") or
    os.getenv("CONSUMER_SECRET")
)
OAUTH_TOKEN = os.getenv("OAUTH_TOKEN")
OAUTH_TOKEN_SECRET = os.getenv("OAUTH_TOKEN_SECRET")

def fetch_etrade_quote(symbol):
    """
    Fetch the latest trade price for a symbol from the E*TRADE API.
    Falls back to 0.0 if the API call fails or credentials are missing.
    """
    if not all([CONSUMER_KEY, CONSUMER_SECRET, OAUTH_TOKEN, OAUTH_TOKEN_SECRET]):
        raise RuntimeError("E*TRADE credentials not set in environment")
    session = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=OAUTH_TOKEN,
        resource_owner_secret=OAUTH_TOKEN_SECRET
    )
    url = f"https://api.etrade.com/v1/market/quote/{symbol}.json"
    resp = session.get(url)
    resp.raise_for_status()
    data = resp.json()
    quote_data = data.get("quoteResponse", {}).get("quoteData", [])
    if quote_data:
        return float(quote_data[0].get("lastTrade", 0.0))
    return 0.0
