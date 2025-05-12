import os
import json
import webbrowser
from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv

load_dotenv("etrade.env")

ETRADE_API_KEY = os.getenv("ETRADE_API_KEY")
ETRADE_API_SECRET = os.getenv("ETRADE_API_SECRET")
CALLBACK_URI = "oob"

REQUEST_TOKEN_URL = "https://api.etrade.com/oauth/request_token"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"
ACCESS_TOKEN_URL = "https://api.etrade.com/oauth/access_token"

print("🔑 Requesting token...")
oauth = OAuth1Session(ETRADE_API_KEY, client_secret=ETRADE_API_SECRET, callback_uri=CALLBACK_URI)
fetch_response = oauth.fetch_request_token(REQUEST_TOKEN_URL)

resource_owner_key = fetch_response.get("oauth_token")
resource_owner_secret = fetch_response.get("oauth_token_secret")
print("✅ Got request token.")

authorization_url = f"{AUTHORIZE_URL}?key={ETRADE_API_KEY}&token={resource_owner_key}"
print("\n🌐 Open this URL in your browser and authorize the app:")
print(authorization_url)
webbrowser.open(authorization_url)

verifier = input("\nEnter the verification code from the website: ")

oauth = OAuth1Session(
    ETRADE_API_KEY,
    client_secret=ETRADE_API_SECRET,
    resource_owner_key=resource_owner_key,
    resource_owner_secret=resource_owner_secret,
    verifier=verifier
)
access_token_response = oauth.fetch_access_token(ACCESS_TOKEN_URL)

access_token = access_token_response.get("oauth_token")
access_token_secret = access_token_response.get("oauth_token_secret")

print("\n✅ Access token obtained!")
print("OAUTH_TOKEN =", access_token)
print("OAUTH_TOKEN_SECRET =", access_token_secret)

# Save to etrade.env
with open("etrade.env", "a") as f:
    f.write(f"\nOAUTH_TOKEN={access_token}\n")
    f.write(f"OAUTH_TOKEN_SECRET={access_token_secret}\n")

print("\n💾 Saved access tokens to etrade.env")
