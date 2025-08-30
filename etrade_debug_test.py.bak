
import os
import logging
import requests
from requests_oauthlib import OAuth1
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Extract environment variables
consumer_key = os.getenv("ETRADE_API_KEY")
consumer_secret = os.getenv("ETRADE_API_SECRET")
oauth_token = os.getenv("OAUTH_TOKEN")
oauth_token_secret = os.getenv("OAUTH_TOKEN_SECRET")

# Set up logging
logging.basicConfig(level=logging.INFO)

# Create OAuth1 auth object
auth = OAuth1(
    consumer_key,
    client_secret=consumer_secret,
    resource_owner_key=oauth_token,
    resource_owner_secret=oauth_token_secret,
    signature_method="HMAC-SHA1",
)

# Define the endpoint and symbol
symbol = "AAPL"
url = f"https://api.etrade.com/v1/market/quote/{symbol}.json"

# Make the request
logging.info(f"Requesting quote for {symbol} from {url}")
response = requests.get(url, auth=auth)

# Output detailed response info
print("=== HTTP STATUS ===")
print(response.status_code)
print("=== HEADERS ===")
print(dict(response.headers))
print("=== BODY ===")
print(response.text)
