import os
import requests
from requests_oauthlib import OAuth1
from dotenv import load_dotenv
import time
from dotenv import load_dotenv
load_dotenv()

print("OAUTH_TOKEN =", os.getenv("OAUTH_TOKEN"))
print("OAUTH_TOKEN_SECRET =", os.getenv("OAUTH_TOKEN_SECRET"))
print("ETRADE_API_KEY =", os.getenv("ETRADE_API_KEY"))
print("ETRADE_API_SECRET =", os.getenv("ETRADE_API_SECRET"))
print("ETRADE_ENV =", os.getenv("ETRADE_ENV"))

load_dotenv("etrade.env")

ETRADE_API_KEY = os.getenv("ETRADE_API_KEY")
ETRADE_API_SECRET = os.getenv("ETRADE_API_SECRET")
OAUTH_TOKEN = os.getenv("OAUTH_TOKEN")
OAUTH_TOKEN_SECRET = os.getenv("OAUTH_TOKEN_SECRET")

auth = OAuth1(ETRADE_API_KEY, ETRADE_API_SECRET, OAUTH_TOKEN, OAUTH_TOKEN_SECRET)
BASE_URL = "https://api.etrade.com/v1/market/quote"

with open("sp500_symbols.txt") as f:
    SYMBOLS = [line.strip().replace(".", "-") for line in f if line.strip()]

for symbol in SYMBOLS:
    url = f"{BASE_URL}/{symbol}.json"
    try:
        response = requests.get(url, auth=auth, params={"detailFlag": "ALL"})
        response.raise_for_status()
        print(f"✅ {symbol} OK")
    except requests.exceptions.HTTPError as e:
        print(f"❌ {symbol} failed: {e}")
    except Exception as ex:
        print(f"❌ {symbol} unexpected error: {ex}")
    time.sleep(0.25)
