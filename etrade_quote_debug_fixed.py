
import os
import json
import requests
from dotenv import load_dotenv
from requests_oauthlib import OAuth1

load_dotenv(".env")

auth = OAuth1(
    os.getenv("ETRADE_API_KEY"),
    os.getenv("ETRADE_API_SECRET"),
    os.getenv("OAUTH_TOKEN"),
    os.getenv("OAUTH_TOKEN_SECRET")
)
print("OAUTH_TOKEN =", os.getenv("OAUTH_TOKEN"))
print("OAUTH_TOKEN_SECRET =", os.getenv("OAUTH_TOKEN_SECRET"))
print("ETRADE_API_KEY =", os.getenv("ETRADE_API_KEY"))
print("ETRADE_API_SECRET =", os.getenv("ETRADE_API_SECRET"))
print("ETRADE_ENV =", os.getenv("ETRADE_ENV"))

symbols_to_test = ["SPY", "AAPL", "MSFT", "GOOG", "AMZN", "MMM"]

for symbol in symbols_to_test:
    print(f"🔍 Fetching quote for {symbol}...")
    url = f"https://api.etrade.com/v1/market/quote/{symbol}.json"
    try:
        res = requests.get(url, auth=auth)
        print(f"Status Code: {res.status_code}")
        if res.status_code != 200:
            print("RAW RESPONSE:", res.text)
        data = res.json()
        quote = data.get("QuoteResponse", {}).get("QuoteData", [{}])[0]
        print(json.dumps(quote, indent=2))
        print("-" * 60)
    except Exception as e:
        print(f"❌ Error fetching {symbol}: {e}")
