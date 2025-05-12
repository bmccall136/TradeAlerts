import os
import json
import webbrowser
from requests_oauthlib import OAuth1Session

CONSUMER_KEY = "1e0978925ddea6a6addb5436e6ff2164"
CONSUMER_SECRET = "0fdac4a22a68112d7e855281bab9df70af85cfd023206d15d75bcf51f1390bc2"
BASE_URL = "https://api.etrade.com"

REQUEST_TOKEN_URL = f"{BASE_URL}/oauth/request_token"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"
ACCESS_TOKEN_URL = f"{BASE_URL}/oauth/access_token"

oauth = OAuth1Session(CONSUMER_KEY, client_secret=CONSUMER_SECRET, callback_uri="oob")

tokens = oauth.fetch_request_token(REQUEST_TOKEN_URL)
resource_owner_key = tokens.get("oauth_token")
resource_owner_secret = tokens.get("oauth_token_secret")

auth_url = f"{AUTHORIZE_URL}?key={CONSUMER_KEY}&token={resource_owner_key}"
print("\n🌐 Visit this URL to authorize:\n")
print(auth_url)
webbrowser.open(auth_url)

verifier = input("\n🔐 Enter the verifier code provided by E*TRADE: ")

oauth = OAuth1Session(
    CONSUMER_KEY,
    client_secret=CONSUMER_SECRET,
    resource_owner_key=resource_owner_key,
    resource_owner_secret=resource_owner_secret,
    verifier=verifier,
)

access_tokens = oauth.fetch_access_token(ACCESS_TOKEN_URL)

with open("etrade.env", "w") as f:
    f.write(f"ETRADE_ENV=production\n")
    f.write(f"ETRADE_API_KEY={CONSUMER_KEY}\n")
    f.write(f"ETRADE_API_SECRET={CONSUMER_SECRET}\n")
    f.write(f"OAUTH_TOKEN={resource_owner_key}\n")
    f.write(f"OAUTH_TOKEN_SECRET={resource_owner_secret}\n")
    f.write(f"ETRADE_ACCESS_TOKEN={access_tokens['oauth_token']}\n")
    f.write(f"ETRADE_ACCESS_TOKEN_SECRET={access_tokens['oauth_token_secret']}\n")

print("\n✅ Access tokens obtained and saved to etrade.env!")
