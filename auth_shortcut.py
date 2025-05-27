import os
from requests_oauthlib import OAuth1Session
from dotenv import set_key

REQUEST_TOKEN_URL = "https://api.etrade.com/oauth/request_token"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"
ACCESS_TOKEN_URL = "https://api.etrade.com/oauth/access_token"

CONSUMER_KEY = os.getenv("CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("CONSUMER_SECRET")

def run_auth_flow():
    session = OAuth1Session(CONSUMER_KEY, client_secret=CONSUMER_SECRET, callback_uri='oob')
    fetch_response = session.fetch_request_token(REQUEST_TOKEN_URL)
    resource_owner_key = fetch_response.get("oauth_token")
    resource_owner_secret = fetch_response.get("oauth_token_secret")

    print("\n🔑 Visit this URL to authorize access:")
    print(f"{AUTHORIZE_URL}?key={CONSUMER_KEY}&token={resource_owner_key}\n")
    verifier = input("Enter the PIN (verifier) from E*TRADE: ").strip()

    session = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=resource_owner_key,
        resource_owner_secret=resource_owner_secret,
        verifier=verifier,
    )
    tokens = session.fetch_access_token(ACCESS_TOKEN_URL)

    access_token = tokens.get("oauth_token")
    access_secret = tokens.get("oauth_token_secret")

    print("\n✅ Tokens obtained:")
    print("OAUTH_TOKEN=", access_token)
    print("OAUTH_TOKEN_SECRET=", access_secret)

    # Auto-update .env
    env_path = ".env"
    set_key(env_path, "OAUTH_TOKEN", access_token)
    set_key(env_path, "OAUTH_TOKEN_SECRET", access_secret)
    print("\n📌 .env file updated.")

if __name__ == "__main__":
    run_auth_flow()