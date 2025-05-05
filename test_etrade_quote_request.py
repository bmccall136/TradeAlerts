import os
import requests
from requests_oauthlib import OAuth1
from dotenv import load_dotenv

load_dotenv("etrade.env")

ETRADE_API_KEY = os.getenv("ETRADE_API_KEY")
ETRADE_API_SECRET = os.getenv("ETRADE_API_SECRET")
OAUTH_TOKEN = os.getenv("OAUTH_TOKEN")
OAUTH_TOKEN_SECRET = os.getenv("OAUTH_TOKEN_SECRET")

auth = OAuth1(ETRADE_API_KEY, ETRADE_API_SECRET, OAUTH_TOKEN, OAUTH_TOKEN_SECRET)

BASE_URL = "https://api.etrade.com"
QUOTE_URL = f"{BASE_URL}/v1/market/quote/AAPL,MSFT.json"

params = {
    "detailFlag": "ALL",
    "requireEarningsDate": "false",
    "skipMiniOptionsCheck": "true"
}

try:
    print("🚀 Testing fetch for AAPL and MSFT...")
    response = requests.get(QUOTE_URL, auth=auth, params=params)
    response.raise_for_status()
    print("✅ Success:")
    print(response.json())
except requests.exceptions.HTTPError as e:
    print(f"❌ HTTPError: {e}")
    print(f"Response: {e.response.text}")
except Exception as ex:
    print(f"❌ General error: {ex}")
