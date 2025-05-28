import os
import requests
from dotenv import load_dotenv
from urllib.parse import quote
import logging

# Load your E*TRADE credentials
load_dotenv()

logging.basicConfig(level=logging.INFO)

key = os.getenv("ETRADE_API_KEY")
secret = os.getenv("ETRADE_API_SECRET")
token = os.getenv("OAUTH_TOKEN")
token_secret = os.getenv("OAUTH_TOKEN_SECRET")

# Diagnostic logging
if not all([key, secret, token, token_secret]):
    logging.error("❌ One or more environment variables are missing!")
    exit(1)

symbol = "AAPL"
url = f"https://api.etrade.com/v1/market/quote/{quote(symbol)}.json"

headers = {
    "Authorization": f'OAuth oauth_consumer_key="{key}", oauth_token="{token}"'
}

logging.info(f"Requesting quote for {symbol} from {url}")

try:
    response = requests.get(url, headers=headers)
    print("=== HTTP STATUS ===")
    print(response.status_code)
    print("=== HEADERS ===")
    print(response.headers)
    print("=== BODY ===")
    print(response.text)
except Exception as e:
    logging.error(f"💥 Exception during request: {e}")
