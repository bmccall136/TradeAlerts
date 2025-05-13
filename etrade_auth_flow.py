
import os
import json
import webbrowser
from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv

load_dotenv(".env")

CONSUMER_KEY = os.getenv("ETRADE_API_KEY")
CONSUMER_SECRET = os.getenv("ETRADE_API_SECRET")
BASE_URL = "https://api.etrade.com"
REQUEST_TOKEN_URL = f"{BASE_URL}/oauth/request_token"
ACCESS_TOKEN_URL = f"{BASE_URL}/oauth/access_token"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"
TOKEN_FILE = "etrade_tokens.json"

# Step 1: Get Request Token
oauth = OAuth1Session(CONSUMER_KEY, client_secret=CONSUMER_SECRET, callback_uri="oob")
fetch_response = oauth.fetch_request_token(REQUEST_TOKEN_URL)
resource_owner_key = fetch_response.get("oauth_token")
resource_owner_secret = fetch_response.get("oauth_token_secret")

# Step 2: Direct user to authorize
auth_url = f"{AUTHORIZE_URL}?key={CONSUMER_KEY}&token={resource_owner_key}"
print("\n🔑 Visit this URL to authorize access:")
print(auth_url)
webbrowser.open(auth_url)

# Step 3: Get verification code (PIN)
verifier = input("\nEnter the PIN (verifier) from E*TRADE: ")

# Step 4: Exchange for Access Token
oauth = OAuth1Session(
    CONSUMER_KEY,
    client_secret=CONSUMER_SECRET,
    resource_owner_key=resource_owner_key,
    resource_owner_secret=resource_owner_secret,
    verifier=verifier
)
tokens = oauth.fetch_access_token(ACCESS_TOKEN_URL)

# Save tokens to file
with open(TOKEN_FILE, "w") as f:
    json.dump(tokens, f, indent=2)

print("\n✅ Tokens saved to etrade_tokens.json")
print("📌 Add these to your .env file:")
print(f"OAUTH_TOKEN={tokens['oauth_token']}")
print(f"OAUTH_TOKEN_SECRET={tokens['oauth_token_secret']}")
