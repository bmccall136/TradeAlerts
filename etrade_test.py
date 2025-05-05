import os
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session

# Load environment variables
load_dotenv("etrade.env")

ETRADE_API_KEY = os.getenv("ETRADE_API_KEY")
ETRADE_API_SECRET = os.getenv("ETRADE_API_SECRET")
ACCESS_TOKEN = os.getenv("ETRADE_ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ETRADE_ACCESS_TOKEN_SECRET")
ETRADE_ENV = os.getenv("ETRADE_ENV", "sandbox")

# Determine correct URL
base_url = "https://api.etrade.com" if ETRADE_ENV == "production" else "https://apisb.etrade.com"
quote_url = f"{base_url}/v1/market/quote/AAPL.json"

# Set up authenticated session
oauth = OAuth1Session(
    ETRADE_API_KEY,
    client_secret=ETRADE_API_SECRET,
    resource_owner_key=ACCESS_TOKEN,
    resource_owner_secret=ACCESS_TOKEN_SECRET,
)

# Make API call
print("🔄 Requesting AAPL quote from:", quote_url)
response = oauth.get(quote_url)

# Show status and result
print("Status Code:", response.status_code)
print("Response:")
print(response.text)
